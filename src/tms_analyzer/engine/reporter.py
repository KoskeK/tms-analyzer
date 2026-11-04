from mcstatus import JavaServer
from sqlalchemy import select
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import init_db
from tms_analyzer.shared.models import Server, Report

import tqdm
import logging

import dns.asyncresolver
import dns.exception

def resolve_minecraft_target(hostname):
    resolver = dns.asyncresolver.Resolver()
    resolver.nameservers = ['1.1.1.1', '8.8.8.8']  # Explicitly use public resolvers
    resolver.timeout = 3.0
    resolver.lifetime = 3.0

    # 1. Try SRV lookup first (if no explicit port)
    try:
        srv_answers = await resolver.resolve(f'_minecraft._tcp.{hostname}', 'SRV')
        for rdata in srv_answers:
            return f"{str(rdata.target).rstrip('.')}:{rdata.port}", None
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout):
        pass  # Fall back to standard A/AAAA record

    # 2. Fallback to A/AAAA record on default port 25565
    try:
        a_answers = await resolver.resolve(hostname, 'A')
        for rdata in a_answers:
            return f"{str(rdata)}:25565", None
    except Exception as e:
        return None, e

def check_server(ip, server_id):
    try:
        host, error = resolve_minecraft_target(ip)
        if not error:
            server = JavaServer.lookup(host)
            status = server.status()
            return Report(
                server_id=server_id,
                online=True,
                player_count=status.players.online,
                status="Normal"
            )
        else:
            return Report(
                server_id=server_id,
                online=True,
                player_count=status.players.online,
                status=repr(error)
            )
    except Exception as e:
        logging.warn(f"Error checking server {ip}: {e}")
        return Report(
            server_id=server_id,
            player_count=0,
            online=False,
            status=repr(e)
        )

if __name__ == "__main__":
    engine = init_db()

    with Session(engine) as session:
        # Read all servers
        servers = session.scalars(
            select(Server)
        ).all()
        pbar = tqdm.tqdm(desc="Scanning server", total=len(servers))

        for server in servers:
            report = check_server(server.ip,server.id)
            session.add(report)
            pbar.update(1)
        session.commit()
    engine.dispose()