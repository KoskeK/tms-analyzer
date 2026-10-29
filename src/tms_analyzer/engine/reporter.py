from mcstatus import JavaServer
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database import DATABASE_URL
from models import Server, Report

def check_server(ip, server_id):
    try:
        server = JavaServer.lookup(ip)
        status = server.status()
        return Report(
            server_id=server_id,
            online=True,
            player_count=status.players.online
        )
    except Exception as e:
        print(f"Error checking server {ip}: {e}")
        return Report(
            server_id=server_id,
            player_count=0,
            online=False
        )

if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)

    with Session(engine) as session:
        # Read all servers
        servers = session.scalars(
            select(Server)
        ).all()

        for server in servers:
            session.add(check_server(server.ip))
        session.commit()
    engine.dispose()