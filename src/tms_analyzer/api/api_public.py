from __future__ import annotations
import logging
import os
import re
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError
log = logging.getLogger('api_public')
db_path = os.environ.get('TMS_DB_PATH')
cors_origins = [o.strip() for o in os.environ.get('TMS_CORS_ORIGINS', 'http://localhost:3000,http://localhost:5173').split(',') if o.strip()]
cache_ttl = float(os.environ.get('TMS_CACHE_TTL', '60'))
max_hourly_span_days = 400
max_server_ids = 200
bucket_formats = {'hour': '%Y-%m-%d %H:00:00', 'day': '%Y-%m-%d'}
discovery_formats = {'day': '%Y-%m-%d', 'week': '%Y-W%W', 'month': '%Y-%m'}
err_sql = "(online = 0 OR COALESCE(status, '') != 'Normal')"
dns_sql = "(LOWER(COALESCE(status, '')) LIKE '%dns%' OR LOWER(COALESCE(status, '')) LIKE '%nxdomain%' OR LOWER(COALESCE(status, '')) LIKE '%resolve%' OR LOWER(COALESCE(status, '')) LIKE '%getaddrinfo%' OR LOWER(COALESCE(status, '')) LIKE '%name or service%' OR LOWER(COALESCE(status, '')) LIKE '%noanswer%' OR LOWER(COALESCE(status, '')) LIKE '%no answer%' OR LOWER(COALESCE(status, '')) LIKE '%servfail%')"
timeout_sql = "(LOWER(COALESCE(status, '')) LIKE '%timeout%' OR LOWER(COALESCE(status, '')) LIKE '%timed out%')"

def _build_engine() -> Engine:
    if db_path:
        posix = Path(db_path).resolve().as_posix()
        engine = create_engine(f'sqlite:///file:{posix}?mode=ro&uri=true', connect_args={'check_same_thread': False})
    else:
        from tms_analyzer.shared.database import init_db
        result = init_db()
        if isinstance(result, tuple):
            result = next((x for x in result if isinstance(x, Engine)), result[0])
        engine = result
        log.warning('TMS_DB_PATH not set; using init_db(). Read-only is enforced via PRAGMA query_only, but init_db() itself may create missing tables.')

    @event.listens_for(engine, 'connect')
    def _readonly(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute('PRAGMA query_only = ON')
        cur.close()
    return engine
engine: Engine = _build_engine()

def get_conn():
    with engine.connect() as conn:
        yield conn

def q(conn: Connection, sql: str, params: Optional[Dict[str, Any]]=None):
    return conn.execute(text(sql), params or {}).mappings().all()
_cache: Dict[str, Tuple[float, Any]] = {}
_cache_lock = threading.Lock()

def cached(key: str, fn: Callable[[], Any], ttl: float=cache_ttl) -> Any:
    now = _time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = fn()
    with _cache_lock:
        _cache[key] = (now, value)
    return value
_tz_suffix = re.compile('(Z|[+-]\\d{2}:?\\d{2})$')

def iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    s = str(value).strip().replace(' ', 'T')
    if 'T' in s and (not _tz_suffix.search(s)):
        s += 'Z'
    return s

def bucket_label(bucket: Optional[str], granularity: str) -> Optional[str]:
    if bucket is None:
        return None
    return iso(bucket) if granularity == 'hour' else bucket

def _sql_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')

def parse_ts(value: str, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(422, f"'{field}' must be YYYY-MM-DD or an ISO-8601 datetime")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def resolve_range(start: Optional[str], end: Optional[str], days: Optional[int], default_days: Optional[int], max_days: Optional[int]=None) -> Tuple[str, str]:
    end_dt = parse_ts(end, 'end') if end else datetime.now(timezone.utc) + timedelta(minutes=1)
    if start:
        start_dt: Optional[datetime] = parse_ts(start, 'start')
    elif days is not None:
        start_dt = None if days == 0 else end_dt - timedelta(days=days)
    elif default_days:
        start_dt = end_dt - timedelta(days=default_days)
    else:
        start_dt = None
    if max_days is not None:
        if start_dt is None or (end_dt - start_dt).days > max_days:
            raise HTTPException(422, f'Range too large for this granularity (max {max_days} days). Pass start/end or days, or use granularity=day.')
    return (_sql_ts(start_dt) if start_dt else '0001-01-01 00:00:00', _sql_ts(end_dt))

def parse_tags(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    s = raw.strip()
    if s.startswith('[') and s.endswith(']'):
        parts = [p.strip().strip('\'"') for p in s[1:-1].split(',')]
    else:
        parts = [p.strip() for p in s.split('|')]
    seen: Dict[str, None] = {}
    for p in parts:
        if p:
            seen.setdefault(p, None)
    return list(seen)

def tag_key(tags: List[str]) -> str:
    return '|'.join(sorted(tags))

def like_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

def parse_id_list(value: Optional[str]) -> List[int]:
    if not value:
        return []
    try:
        ids = [int(x) for x in value.split(',') if x.strip()]
    except ValueError:
        raise HTTPException(422, 'server_ids must be a comma-separated list of integers')
    if len(ids) > max_server_ids:
        raise HTTPException(422, f'At most {max_server_ids} server ids per request')
    return ids

def in_clause(column: str, ids: List[int], prefix: str='sid') -> Tuple[str, Dict[str, int]]:
    params = {f'{prefix}{i}': v for i, v in enumerate(ids)}
    clause = f"{column} IN ({', '.join((':' + k for k in params))})"
    return (clause, params)

class latest_report_out(BaseModel):
    time: Optional[str]
    player_count: Optional[int]
    online: Optional[bool]
    status: Optional[str]

class server_out(BaseModel):
    id: int
    ip: Optional[str]
    url: Optional[str]
    version: Optional[str]
    country: Optional[str]
    enabled: Optional[bool]
    added_time: Optional[str]
    tags: Optional[str]
    tags_list: List[str]
    tag_key: str
    latest: Optional[latest_report_out]

class server_page(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[server_out]

class lifetime_stats_out(BaseModel):
    server_id: int
    first_report: Optional[str]
    last_report: Optional[str]
    last_success_time: Optional[str]
    last_players_time: Optional[str]
    peak_players: Optional[int]
    total_reports: int
    successful_reports: int
    error_reports: int
    failures_since_last_success: int

class lifetime_stats_response(BaseModel):
    generated_at: str
    cache_ttl_seconds: float
    items: List[lifetime_stats_out]

class raw_report(BaseModel):
    id: int
    time: Optional[str]
    player_count: Optional[int]
    online: Optional[bool]
    status: Optional[str]

class server_detail_out(server_out):
    lifetime: Optional[lifetime_stats_out]
    peak_time: Optional[str]
    recent_errors: List[raw_report]

class raw_reports_response(BaseModel):
    server_id: int
    truncated: bool
    items: List[raw_report]

class bucket_stat(BaseModel):
    server_id: int
    bucket: str
    total_reports: int
    successful_reports: int
    error_reports: int
    avg_players: Optional[float]
    median_players: Optional[float]
    peak_players: Optional[int]
    min_players: Optional[int]
    active_hours: int

class bucket_stat_page(BaseModel):
    granularity: str
    limit: int
    offset: int
    next_offset: Optional[int]
    items: List[bucket_stat]

class global_bucket(BaseModel):
    bucket: str
    servers_reporting: int
    servers_with_players: int
    total_players: Optional[float]
    mean_players: Optional[float]
    median_players: Optional[float]
    max_server_peak: Optional[int]
    total_reports: int
    error_reports: int
    error_rate_percent: Optional[float]

class global_stats_response(BaseModel):
    granularity: str
    items: List[global_bucket]

class quality_bucket(BaseModel):
    bucket: str
    total_reports: int
    offline_reports: int
    error_reports: int
    dns_errors: int
    timeout_errors: int
    other_errors: int
    error_rate_percent: Optional[float]

class quality_response(BaseModel):
    granularity: str
    items: List[quality_bucket]

class status_count(BaseModel):
    status: str
    online: Optional[bool]
    count: int
    first_seen: Optional[str]
    last_seen: Optional[str]

class heatmap_cell(BaseModel):
    day_of_week: int
    hour: int
    avg_players: Optional[float]
    report_count: int
    servers: int

class discovery_point(BaseModel):
    period: str
    servers_added: int

class discovery_response(BaseModel):
    granularity: str
    items: List[discovery_point]

class filter_count(BaseModel):
    value: Optional[str]
    count: int

class tag_combo_count(BaseModel):
    tag_key: str
    tags: List[str]
    count: int

class filters_response(BaseModel):
    countries: List[filter_count]
    versions: List[filter_count]
    tags: List[filter_count]
    tag_combinations: List[tag_combo_count]

class meta_response(BaseModel):
    server_time: str
    server_count: int
    enabled_count: int
    report_count: int
    earliest_report: Optional[str]
    latest_report: Optional[str]
    earliest_added: Optional[str]
    latest_added: Optional[str]
    db_size_bytes: Optional[int]
    index_warnings: List[str]
app = FastAPI(title='TMS Analyzer Public API', version='1.0.0', description='Read-only data API for the Minecraft server analytics dashboard.')
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=['GET', 'OPTIONS'], allow_headers=['*'])

@app.exception_handler(OperationalError)
async def _db_error(_request: Request, exc: OperationalError):
    log.exception('Database error')
    return JSONResponse({'detail': 'Database unavailable or query failed'}, status_code=503)

def server_filters(q_text: Optional[str]=Query(None, alias='q', description='Substring match on url/ip'), country: Optional[str]=Query(None, description="Exact country; 'unknown' = NULL/empty"), version: Optional[str]=None, enabled: Optional[bool]=None, tag: Optional[str]=Query(None, description='Exact tag (delimiter-aware, case-sensitive)'), ids: Optional[str]=Query(None, description='Comma-separated server ids'), added_after: Optional[str]=Query(None, description='addedTime >= (UTC)'), added_before: Optional[str]=Query(None, description='addedTime < (UTC)')) -> Tuple[str, Dict[str, Any]]:
    clauses: List[str] = []
    params: Dict[str, Any] = {}
    if q_text:
        clauses.append("(s.url LIKE :q ESCAPE '\\' OR s.ip LIKE :q ESCAPE '\\')")
        params['q'] = f'%{like_escape(q_text)}%'
    if country:
        if country.lower() == 'unknown':
            clauses.append("(s.country IS NULL OR TRIM(s.country) = '')")
        else:
            clauses.append('s.country = :country')
            params['country'] = country
    if version:
        clauses.append('s.version = :version')
        params['version'] = version
    if enabled is not None:
        clauses.append('s.enabled = :enabled')
        params['enabled'] = 1 if enabled else 0
    if tag:
        clauses.append("INSTR('|' || COALESCE(s.tags, '') || '|', :tag_pat) > 0")
        params['tag_pat'] = f'|{tag}|'
    if ids:
        id_list = parse_id_list(ids)
        if id_list:
            c, p = in_clause('s.id', id_list, 'fid')
            clauses.append(c)
            params.update(p)
    if added_after:
        clauses.append('s.addedTime >= :added_after')
        params['added_after'] = _sql_ts(parse_ts(added_after, 'added_after'))
    if added_before:
        clauses.append('s.addedTime < :added_before')
        params['added_before'] = _sql_ts(parse_ts(added_before, 'added_before'))
    return ('WHERE ' + ' AND '.join(clauses) if clauses else '', params)
_server_select = '\nSELECT s.id, s.ip, s.tags, s.url, s.version, s.enabled, s.country, s.addedTime,\n       r.time AS latest_time, r.player_count AS latest_player_count,\n       r.online AS latest_online, r.status AS latest_status\nFROM servers s\nLEFT JOIN reports r ON r.id = (\n    SELECT id FROM reports WHERE server_id = s.id ORDER BY time DESC, id DESC LIMIT 1\n)\n'
_sorts = {'id': 's.id', 'added': 's.addedTime', 'url': 's.url', 'country': 's.country', 'players': 'r.player_count'}

def _server_out(row) -> server_out:
    tags = parse_tags(row['tags'])
    latest = None
    if row['latest_time'] is not None:
        latest = latest_report_out(time=iso(row['latest_time']), player_count=row['latest_player_count'], online=None if row['latest_online'] is None else bool(row['latest_online']), status=row['latest_status'])
    return server_out(id=row['id'], ip=row['ip'], url=row['url'], version=row['version'], country=row['country'], enabled=None if row['enabled'] is None else bool(row['enabled']), added_time=iso(row['addedTime']), tags=row['tags'], tags_list=tags, tag_key=tag_key(tags), latest=latest)

@app.get('/api/servers', response_model=server_page, tags=['servers'])
def list_servers(filters: Tuple[str, Dict[str, Any]]=Depends(server_filters), sort: str=Query('id', pattern='^(id|added|url|country|players)$'), order: str=Query('asc', pattern='^(asc|desc)$'), limit: int=Query(1000, ge=1, le=5000), offset: int=Query(0, ge=0), conn: Connection=Depends(get_conn)):
    where, params = filters
    total = conn.execute(text(f'SELECT COUNT(*) FROM servers s {where}'), params).scalar() or 0
    sql = f'{_server_select} {where} ORDER BY {_sorts[sort]} {order.upper()}, s.id ASC LIMIT :limit OFFSET :offset'
    rows = q(conn, sql, {**params, 'limit': limit, 'offset': offset})
    return server_page(total=total, limit=limit, offset=offset, items=[_server_out(r) for r in rows])

def _lifetime(conn: Connection, server_id: Optional[int]=None) -> Dict[int, lifetime_stats_out]:
    where = 'WHERE server_id = :sid' if server_id is not None else ''
    and_sub = 'AND server_id = :sid' if server_id is not None else ''
    and_outer = 'AND r.server_id = :sid' if server_id is not None else ''
    params = {'sid': server_id} if server_id is not None else {}
    rows = q(conn, f'\n        SELECT server_id,\n               MIN(time) AS first_report,\n               MAX(time) AS last_report,\n               MAX(CASE WHEN online = 1 THEN time END) AS last_success_time,\n               MAX(CASE WHEN online = 1 AND player_count > 0 THEN time END) AS last_players_time,\n               MAX(CASE WHEN online = 1 THEN player_count END) AS peak_players,\n               COUNT(*) AS total_reports,\n               SUM(CASE WHEN online = 1 THEN 1 ELSE 0 END) AS successful_reports,\n               SUM(CASE WHEN {err_sql} THEN 1 ELSE 0 END) AS error_reports\n        FROM reports {where}\n        GROUP BY server_id\n        ', params)
    fails = {r['server_id']: r['n'] for r in q(conn, f"\n            SELECT r.server_id AS server_id, COUNT(*) AS n\n            FROM reports r\n            LEFT JOIN (\n                SELECT server_id, MAX(time) AS t FROM reports\n                WHERE online = 1 {and_sub} GROUP BY server_id\n            ) ls ON ls.server_id = r.server_id\n            WHERE (ls.t IS NULL OR r.time > ls.t) AND {err_sql.replace('online', 'r.online').replace('status', 'r.status')} {and_outer}\n            GROUP BY r.server_id\n            ", params)}
    out: Dict[int, lifetime_stats_out] = {}
    for r in rows:
        sid = r['server_id']
        out[sid] = lifetime_stats_out(server_id=sid, first_report=iso(r['first_report']), last_report=iso(r['last_report']), last_success_time=iso(r['last_success_time']), last_players_time=iso(r['last_players_time']), peak_players=r['peak_players'], total_reports=r['total_reports'] or 0, successful_reports=r['successful_reports'] or 0, error_reports=r['error_reports'] or 0, failures_since_last_success=fails.get(sid, 0))
    return out

@app.get('/api/servers/lifetime-stats', response_model=lifetime_stats_response, tags=['servers'])
def lifetime_stats(conn: Connection=Depends(get_conn)):
    items = cached('lifetime', lambda: list(_lifetime(conn).values()))
    return lifetime_stats_response(generated_at=iso(datetime.now(timezone.utc)) or '', cache_ttl_seconds=cache_ttl, items=items)

def _recent_errors(conn: Connection, server_id: int, limit: int, start_sql: Optional[str]=None):
    extra = 'AND time >= :start' if start_sql else ''
    params: Dict[str, Any] = {'sid': server_id, 'limit': limit}
    if start_sql:
        params['start'] = start_sql
    rows = q(conn, f'SELECT id, time, player_count, online, status FROM reports\n            WHERE server_id = :sid AND {err_sql} {extra}\n            ORDER BY time DESC, id DESC LIMIT :limit', params)
    return [_raw_report(r) for r in rows]

def _raw_report(r) -> raw_report:
    return raw_report(id=r['id'], time=iso(r['time']), player_count=r['player_count'], online=None if r['online'] is None else bool(r['online']), status=r['status'])

@app.get('/api/servers/{server_id}', response_model=server_detail_out, tags=['servers'])
def server_detail(server_id: int, conn: Connection=Depends(get_conn)):
    rows = q(conn, f'{_server_select} WHERE s.id = :sid', {'sid': server_id})
    if not rows:
        raise HTTPException(404, 'Server not found')
    base = _server_out(rows[0])
    lifetime = _lifetime(conn, server_id).get(server_id)
    peak = q(conn, 'SELECT time FROM reports\n           WHERE server_id = :sid AND online = 1 AND player_count IS NOT NULL\n           ORDER BY player_count DESC, time ASC LIMIT 1', {'sid': server_id})
    return server_detail_out(**base.model_dump(), lifetime=lifetime, peak_time=iso(peak[0]['time']) if peak else None, recent_errors=_recent_errors(conn, server_id, 20))

@app.get('/api/servers/{server_id}/reports', response_model=raw_reports_response, tags=['servers'])
def server_reports(server_id: int, start: Optional[str]=None, end: Optional[str]=None, days: Optional[int]=Query(None, ge=0), successful_only: bool=False, order: str=Query('asc', pattern='^(asc|desc)$'), limit: int=Query(5000, ge=1, le=50000), conn: Connection=Depends(get_conn)):
    s, e = resolve_range(start, end, days, default_days=7)
    extra = 'AND online = 1' if successful_only else ''
    rows = q(conn, f'SELECT id, time, player_count, online, status FROM reports\n            WHERE server_id = :sid AND time >= :start AND time < :end {extra}\n            ORDER BY time {order.upper()}, id {order.upper()} LIMIT :limit', {'sid': server_id, 'start': s, 'end': e, 'limit': limit + 1})
    return raw_reports_response(server_id=server_id, truncated=len(rows) > limit, items=[_raw_report(r) for r in rows[:limit]])

@app.get('/api/servers/{server_id}/errors', response_model=List[raw_report], tags=['servers'])
def server_errors(server_id: int, days: Optional[int]=Query(None, ge=1), limit: int=Query(50, ge=1, le=500), conn: Connection=Depends(get_conn)):
    start_sql = None
    if days:
        start_sql, _ = resolve_range(None, None, days, None)
    return _recent_errors(conn, server_id, limit, start_sql)

def bucket_server_stats(conn: Connection, granularity: str, start_sql: str, end_sql: str, server_ids: List[int], include_median: bool, limit: int, offset: int) -> bucket_stat_page:
    params: Dict[str, Any] = {'fmt': bucket_formats[granularity], 'start': start_sql, 'end': end_sql, 'limit': limit + 1, 'offset': offset}
    sid_sql = ''
    if server_ids:
        sid_sql, p = in_clause('server_id', server_ids)
        sid_sql = 'AND ' + sid_sql
        params.update(p)
    median_ctes = ''
    median_join = ''
    median_col = 'NULL AS median_players'
    if include_median:
        median_ctes = '\n        , ranked AS (\n            SELECT server_id, bucket, player_count,\n                   ROW_NUMBER() OVER (PARTITION BY server_id, bucket ORDER BY player_count) AS rn,\n                   COUNT(*) OVER (PARTITION BY server_id, bucket) AS n\n            FROM base WHERE online = 1 AND player_count IS NOT NULL\n        ),\n        med AS (\n            SELECT server_id, bucket, AVG(player_count) AS median_players\n            FROM ranked WHERE rn IN ((n + 1) / 2, (n + 2) / 2)\n            GROUP BY server_id, bucket\n        )'
        median_join = 'LEFT JOIN med ON med.server_id = agg.server_id AND med.bucket = agg.bucket'
        median_col = 'med.median_players AS median_players'
    sql = f"\n    WITH base AS (\n        SELECT server_id, STRFTIME(:fmt, time) AS bucket, time, online, status, player_count\n        FROM reports\n        WHERE time >= :start AND time < :end {sid_sql}\n    ),\n    agg AS (\n        SELECT server_id, bucket,\n               COUNT(*) AS total_reports,\n               SUM(CASE WHEN online = 1 THEN 1 ELSE 0 END) AS successful_reports,\n               SUM(CASE WHEN {err_sql} THEN 1 ELSE 0 END) AS error_reports,\n               AVG(CASE WHEN online = 1 THEN player_count END) AS avg_players,\n               MAX(CASE WHEN online = 1 THEN player_count END) AS peak_players,\n               MIN(CASE WHEN online = 1 THEN player_count END) AS min_players,\n               COUNT(DISTINCT CASE WHEN online = 1 AND player_count > 0\n                                   THEN STRFTIME('%Y-%m-%d %H', time) END) AS active_hours\n        FROM base GROUP BY server_id, bucket\n    )\n    {median_ctes}\n    SELECT agg.*, {median_col}\n    FROM agg {median_join}\n    ORDER BY agg.bucket, agg.server_id\n    LIMIT :limit OFFSET :offset\n    "
    rows = q(conn, sql, params)
    has_more = len(rows) > limit
    items = [bucket_stat(server_id=r['server_id'], bucket=bucket_label(r['bucket'], granularity) or '', total_reports=r['total_reports'], successful_reports=r['successful_reports'] or 0, error_reports=r['error_reports'] or 0, avg_players=None if r['avg_players'] is None else round(r['avg_players'], 3), median_players=r['median_players'], peak_players=r['peak_players'], min_players=r['min_players'], active_hours=r['active_hours'] or 0) for r in rows[:limit]]
    return bucket_stat_page(granularity=granularity, limit=limit, offset=offset, next_offset=offset + limit if has_more else None, items=items)

@app.get('/api/server-stats', response_model=bucket_stat_page, tags=['stats'])
def server_stats(granularity: str=Query('day', pattern='^(hour|day)$'), server_ids: Optional[str]=Query(None, description='Comma-separated; omit for ALL servers'), start: Optional[str]=None, end: Optional[str]=None, days: Optional[int]=Query(None, ge=0), include_median: bool=True, limit: int=Query(50000, ge=1, le=200000), offset: int=Query(0, ge=0), conn: Connection=Depends(get_conn)):
    ids = parse_id_list(server_ids)
    s, e = resolve_range(start, end, days, default_days=7 if granularity == 'hour' else 90, max_days=max_hourly_span_days if granularity == 'hour' else None)
    return bucket_server_stats(conn, granularity, s, e, ids, include_median, limit, offset)

@app.get('/api/servers/{server_id}/series', response_model=bucket_stat_page, tags=['servers'])
def server_series(server_id: int, granularity: str=Query('day', pattern='^(hour|day)$'), start: Optional[str]=None, end: Optional[str]=None, days: Optional[int]=Query(None, ge=0), include_median: bool=True, conn: Connection=Depends(get_conn)):
    s, e = resolve_range(start, end, days, default_days=7 if granularity == 'hour' else 90, max_days=max_hourly_span_days if granularity == 'hour' else None)
    return bucket_server_stats(conn, granularity, s, e, [server_id], include_median, 200000, 0)

@app.get('/api/stats/global', response_model=global_stats_response, tags=['stats'])
def global_stats(granularity: str=Query('day', pattern='^(hour|day)$'), start: Optional[str]=None, end: Optional[str]=None, days: Optional[int]=Query(None, ge=0), filters: Tuple[str, Dict[str, Any]]=Depends(server_filters), conn: Connection=Depends(get_conn)):
    s, e = resolve_range(start, end, days, default_days=7 if granularity == 'hour' else 90, max_days=max_hourly_span_days if granularity == 'hour' else None)
    where, fparams = filters
    server_restrict = ''
    if where:
        server_restrict = f'AND server_id IN (SELECT s.id FROM servers s {where})'
    params = {'fmt': bucket_formats[granularity], 'start': s, 'end': e, **fparams}
    player_rows = q(conn, f'\n        WITH srv AS (\n            SELECT server_id, STRFTIME(:fmt, time) AS bucket,\n                   AVG(player_count) AS avg_p, MAX(player_count) AS peak_p\n            FROM reports\n            WHERE online = 1 AND player_count IS NOT NULL\n              AND time >= :start AND time < :end {server_restrict}\n            GROUP BY server_id, bucket\n        ),\n        ranked AS (\n            SELECT bucket, avg_p,\n                   ROW_NUMBER() OVER (PARTITION BY bucket ORDER BY avg_p) AS rn,\n                   COUNT(*) OVER (PARTITION BY bucket) AS n\n            FROM srv\n        ),\n        med AS (\n            SELECT bucket, AVG(avg_p) AS median_players\n            FROM ranked WHERE rn IN ((n + 1) / 2, (n + 2) / 2)\n            GROUP BY bucket\n        ),\n        agg AS (\n            SELECT bucket,\n                   COUNT(*) AS servers_reporting,\n                   SUM(CASE WHEN avg_p > 0 THEN 1 ELSE 0 END) AS servers_with_players,\n                   SUM(avg_p) AS total_players,\n                   AVG(avg_p) AS mean_players,\n                   MAX(peak_p) AS max_server_peak\n            FROM srv GROUP BY bucket\n        )\n        SELECT agg.*, med.median_players FROM agg JOIN med ON med.bucket = agg.bucket\n        ', params)
    err_rows = q(conn, f'\n        SELECT STRFTIME(:fmt, time) AS bucket,\n               COUNT(*) AS total_reports,\n               SUM(CASE WHEN {err_sql} THEN 1 ELSE 0 END) AS error_reports\n        FROM reports\n        WHERE time >= :start AND time < :end {server_restrict}\n        GROUP BY bucket\n        ', params)
    merged: Dict[str, Dict[str, Any]] = {}
    for r in err_rows:
        merged[r['bucket']] = {'total_reports': r['total_reports'], 'error_reports': r['error_reports'] or 0}
    for r in player_rows:
        merged.setdefault(r['bucket'], {'total_reports': 0, 'error_reports': 0}).update(dict(r))
    items = []
    for bucket in sorted(merged):
        m = merged[bucket]
        total = m.get('total_reports', 0)
        errs = m.get('error_reports', 0)
        items.append(global_bucket(bucket=bucket_label(bucket, granularity) or '', servers_reporting=m.get('servers_reporting', 0) or 0, servers_with_players=m.get('servers_with_players', 0) or 0, total_players=None if m.get('total_players') is None else round(m['total_players'], 2), mean_players=None if m.get('mean_players') is None else round(m['mean_players'], 3), median_players=m.get('median_players'), max_server_peak=m.get('max_server_peak'), total_reports=total, error_reports=errs, error_rate_percent=round(100.0 * errs / total, 2) if total else None))
    return global_stats_response(granularity=granularity, items=items)

@app.get('/api/monitoring-quality', response_model=quality_response, tags=['quality'])
def monitoring_quality(granularity: str=Query('day', pattern='^(hour|day)$'), server_id: Optional[int]=None, start: Optional[str]=None, end: Optional[str]=None, days: Optional[int]=Query(None, ge=0), conn: Connection=Depends(get_conn)):
    s, e = resolve_range(start, end, days, default_days=7 if granularity == 'hour' else 30, max_days=max_hourly_span_days if granularity == 'hour' else None)
    params: Dict[str, Any] = {'fmt': bucket_formats[granularity], 'start': s, 'end': e}
    sid = ''
    if server_id is not None:
        sid = 'AND server_id = :sid'
        params['sid'] = server_id
    rows = q(conn, f'\n        SELECT STRFTIME(:fmt, time) AS bucket,\n               COUNT(*) AS total_reports,\n               SUM(CASE WHEN online = 0 THEN 1 ELSE 0 END) AS offline_reports,\n               SUM(CASE WHEN {err_sql} THEN 1 ELSE 0 END) AS error_reports,\n               SUM(CASE WHEN {err_sql} AND {dns_sql} THEN 1 ELSE 0 END) AS dns_errors,\n               SUM(CASE WHEN {err_sql} AND NOT {dns_sql} AND {timeout_sql} THEN 1 ELSE 0 END) AS timeout_errors\n        FROM reports\n        WHERE time >= :start AND time < :end {sid}\n        GROUP BY bucket ORDER BY bucket\n        ', params)
    items = []
    for r in rows:
        errs = r['error_reports'] or 0
        dns = r['dns_errors'] or 0
        to = r['timeout_errors'] or 0
        items.append(quality_bucket(bucket=bucket_label(r['bucket'], granularity) or '', total_reports=r['total_reports'], offline_reports=r['offline_reports'] or 0, error_reports=errs, dns_errors=dns, timeout_errors=to, other_errors=max(errs - dns - to, 0), error_rate_percent=round(100.0 * errs / r['total_reports'], 2) if r['total_reports'] else None))
    return quality_response(granularity=granularity, items=items)

@app.get('/api/monitoring-quality/statuses', response_model=List[status_count], tags=['quality'])
def status_breakdown(start: Optional[str]=None, end: Optional[str]=None, days: Optional[int]=Query(30, ge=0), limit: int=Query(100, ge=1, le=1000), conn: Connection=Depends(get_conn)):
    s, e = resolve_range(start, end, days, default_days=30)
    rows = q(conn, f"\n        SELECT SUBSTR(COALESCE(status, ''), 1, 200) AS status_text, online,\n               COUNT(*) AS n, MIN(time) AS first_seen, MAX(time) AS last_seen\n        FROM reports\n        WHERE {err_sql} AND time >= :start AND time < :end\n        GROUP BY status_text, online ORDER BY n DESC LIMIT :limit\n        ", {'start': s, 'end': e, 'limit': limit})
    return [status_count(status=r['status_text'], online=None if r['online'] is None else bool(r['online']), count=r['n'], first_seen=iso(r['first_seen']), last_seen=iso(r['last_seen'])) for r in rows]

@app.get('/api/activity-heatmap', response_model=List[heatmap_cell], tags=['stats'])
def activity_heatmap(server_id: Optional[int]=None, start: Optional[str]=None, end: Optional[str]=None, days: Optional[int]=Query(None, ge=0), filters: Tuple[str, Dict[str, Any]]=Depends(server_filters), conn: Connection=Depends(get_conn)):
    s, e = resolve_range(start, end, days, default_days=30)
    where, fparams = filters
    params: Dict[str, Any] = {'start': s, 'end': e, **fparams}
    extra = ''
    if where:
        extra += f'AND server_id IN (SELECT s.id FROM servers s {where})'
    if server_id is not None:
        extra += ' AND server_id = :sid'
        params['sid'] = server_id
    rows = q(conn, f"\n        SELECT CAST(STRFTIME('%w', time) AS INTEGER) AS dow,\n               CAST(STRFTIME('%H', time) AS INTEGER) AS hr,\n               AVG(player_count) AS avg_players,\n               COUNT(*) AS report_count,\n               COUNT(DISTINCT server_id) AS servers\n        FROM reports\n        WHERE online = 1 AND player_count IS NOT NULL\n          AND time >= :start AND time < :end {extra}\n        GROUP BY dow, hr ORDER BY dow, hr\n        ", params)
    return [heatmap_cell(day_of_week=r['dow'], hour=r['hr'], avg_players=None if r['avg_players'] is None else round(r['avg_players'], 3), report_count=r['report_count'], servers=r['servers']) for r in rows]

@app.get('/api/discovery', response_model=discovery_response, tags=['stats'])
def discovery(granularity: str=Query('day', pattern='^(day|week|month)$'), filters: Tuple[str, Dict[str, Any]]=Depends(server_filters), conn: Connection=Depends(get_conn)):
    where, params = filters
    cond = 's.addedTime IS NOT NULL'
    where_sql = f'{where} AND {cond}' if where else f'WHERE {cond}'
    rows = q(conn, f'SELECT STRFTIME(:fmt, s.addedTime) AS period, COUNT(*) AS n\n            FROM servers s {where_sql} GROUP BY period ORDER BY period', {**params, 'fmt': discovery_formats[granularity]})
    return discovery_response(granularity=granularity, items=[discovery_point(period=r['period'], servers_added=r['n']) for r in rows])

@app.get('/api/filters', response_model=filters_response, tags=['meta'])
def filters_endpoint(top_combinations: int=Query(30, ge=1, le=200), conn: Connection=Depends(get_conn)):

    def build() -> filters_response:
        rows = q(conn, 'SELECT country, version, tags FROM servers')
        countries: Dict[Optional[str], int] = {}
        versions: Dict[Optional[str], int] = {}
        tags: Dict[str, int] = {}
        combos: Dict[str, Tuple[List[str], int]] = {}
        for r in rows:
            c = (r['country'] or '').strip() or None
            v = (r['version'] or '').strip() or None
            countries[c] = countries.get(c, 0) + 1
            versions[v] = versions.get(v, 0) + 1
            tl = parse_tags(r['tags'])
            for t in tl:
                tags[t] = tags.get(t, 0) + 1
            if tl:
                key = tag_key(tl)
                prev = combos.get(key)
                combos[key] = (sorted(tl), (prev[1] if prev else 0) + 1)

        def fc(d: Dict[Optional[str], int]) -> List[filter_count]:
            return [filter_count(value=k, count=n) for k, n in sorted(d.items(), key=lambda kv: (-kv[1], kv[0] or ''))]
        return filters_response(countries=fc(countries), versions=fc(versions), tags=fc(tags), tag_combinations=[tag_combo_count(tag_key=k, tags=t, count=n) for k, (t, n) in sorted(combos.items(), key=lambda kv: -kv[1][1])])
    result: filters_response = cached('filters', build)
    return result.model_copy(update={'tag_combinations': result.tag_combinations[:top_combinations]})

def _index_warnings(conn: Connection) -> List[str]:
    warnings: List[str] = []
    try:
        idx = conn.exec_driver_sql("PRAGMA index_list('reports')").fetchall()
        firsts: List[List[str]] = []
        for row in idx:
            cols = [c[2] for c in conn.exec_driver_sql(f"PRAGMA index_info('{row[1]}')").fetchall()]
            firsts.append(cols)
        if not any((c[:2] == ['server_id', 'time'] for c in firsts)):
            warnings.append('No index on reports(server_id, time): latest-report and per-server queries will be slow. Consider: CREATE INDEX idx_reports_server_time ON reports(server_id, time);')
        if not any((c[:1] == ['time'] for c in firsts)):
            warnings.append('No index with leading column reports(time): time-range scans will be slow. Consider: CREATE INDEX idx_reports_time ON reports(time);')
    except Exception:
        log.exception('Could not inspect indexes')
    return warnings

@app.get('/api/meta', response_model=meta_response, tags=['meta'])
def meta(conn: Connection=Depends(get_conn)):

    def build() -> meta_response:
        srv = q(conn, 'SELECT COUNT(*) AS n, SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) AS enabled_n,\n                      MIN(addedTime) AS min_added, MAX(addedTime) AS max_added FROM servers')[0]
        rep = q(conn, 'SELECT COUNT(*) AS n, MIN(time) AS min_t, MAX(time) AS max_t FROM reports')[0]
        size = None
        if db_path and os.path.exists(db_path):
            size = os.path.getsize(db_path)
        return meta_response(server_time=iso(datetime.now(timezone.utc)) or '', server_count=srv['n'] or 0, enabled_count=srv['enabled_n'] or 0, report_count=rep['n'] or 0, earliest_report=iso(rep['min_t']), latest_report=iso(rep['max_t']), earliest_added=iso(srv['min_added']), latest_added=iso(srv['max_added']), db_size_bytes=size, index_warnings=_index_warnings(conn))
    result: meta_response = cached('meta', build)
    return result.model_copy(update={'server_time': iso(datetime.now(timezone.utc)) or ''})

@app.get('/api/health', tags=['meta'])
def health(conn: Connection=Depends(get_conn)):
    conn.execute(text('SELECT 1')).scalar()
    return {'status': 'ok'}
if __name__ == '__main__':
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=os.environ.get('TMS_API_HOST', '0.0.0.0'), port=int(os.environ.get('TMS_API_PORT', '8000')))
