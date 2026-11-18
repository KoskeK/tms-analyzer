
from mcstatus import JavaServer
from sqlalchemy import select
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import init_db
from tms_analyzer.shared.models import Server, Report

import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def check_server(ip, server_id):
    try:
        host, error = resolve_minecraft_target(ip)

        if error:
            return Report(
                server_id=server_id,
                online=False,
                player_count=0,
                status=f"DNS Error: {error!r}"
            )

        server = JavaServer.lookup(host)
        status = server.status()

        return Report(
            server_id=server_id,
            online=True,
            player_count=status.players.online,
            status="Normal"
        )

    except Exception as e:
        logging.warning("Error checking server %s: %s", ip, e)

        return Report(
            server_id=server_id,
            online=False,
            player_count=0,
            status=repr(e)
        )


if __name__ == "__main__":
    engine = init_db()

    try:
        with Session(engine) as session:
            servers = session.scalars(
                select(Server).where(Server.enabled == True)
            ).all()
            for server in servers:
                report = check_server(server.ip, server.id)
                session.add(report)

            has_normal = session.scalar(
            select(Report.id)
            .where(
                Report.server_id == server.id,
                Report.status == "Normal",
                Report.id.in_(
                    select(Report.id)
                    .where(Report.server_id == server.id)
                    .order_by(Report.time.desc())
                    .limit(5)
                )
            )
            .limit(1)
        )

            if has_normal is None:
                server.enabled = False
            else:
                server.enabled = True

            session.commit()

    except Exception:
        logging.exception("Scanning failed")
        raise

    finally:
        engine.dispose()
