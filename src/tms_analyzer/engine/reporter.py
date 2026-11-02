from mcstatus import JavaServer
from sqlalchemy import select
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import init_db
from tms_analyzer.shared.models import Server, Report

import tqdm
import logging

def check_server(ip, server_id):
    try:
        server = JavaServer.lookup(ip)
        status = server.status()
        return Report(
            server_id=server_id,
            online=True,
            player_count=status.players.online,
            status="Normal"
        )
    except Exception as e:
        logging.warn(f"Error checking server {ip}: {e}")
        return Report(
            server_id=server_id,
            player_count=0,
            online=False,
            status=e
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