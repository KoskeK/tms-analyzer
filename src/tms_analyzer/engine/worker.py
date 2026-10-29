from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import DATABASE_URL
from tms_analyzer.shared.models import Server, Report
from tms_analyzer.engine.scanner import scan_pages
from dotenv import load_dotenv
import os

if __name__ == "__main__":

    load_dotenv()

    engine = create_engine(DATABASE_URL)

    with Session(engine) as session:
        pageNum = 1
        while True:
            servers = scan_pages(pageNum)
            if len(servers)<=5:
                break
            else:
                for server in servers:
                    if session.scalars(select(Server).where(Server.ip==server["ip"])) != None:
                        break
                    else:
                        formatted = Server(
                            ip=server["ip"],
                            tags=str(server["tags"]),
                            url=server["url"],
                            version=server["version"]
                        )
                        session.commit()

    engine.dispose()