from mcstatus import JavaServer
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database import DATABASE_URL
from models import Server, Report

def check_server(ip):
    try:
        server = JavaServer.lookup(ip)
        status = server.status()
        return {
            "ip": ip,
            "online": True,
            "players": status.players.online,
        }
    except Exception as e:
        print(f"Error checking server {ip}: {e}")
        return {
            "ip": ip,
            "online": False
        }

if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)

    with Session(engine) as session:
        # Read all servers
        servers = session.scalars(
            select(Server)
        ).all()

        for server in servers:
            print(server.id, server.ip)

        # Add a new report for the first server
        if servers:
            report = Report(
                server_id=servers[0].id,
                player_count=12,
                online=True,
            )

            session.add(report)
            session.commit()

    engine.dispose()