from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import DATABASE_URL
from tms_analyzer.shared.models import Server, Report

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