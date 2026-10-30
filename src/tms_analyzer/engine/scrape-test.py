from tms_analyzer.engine.minecraft_mp_scrape import scan_pages
from sqlalchemy import select, exists
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import init_db
from tms_analyzer.shared.models import Server, Report
from dotenv import load_dotenv
import os
import httpx
from bs4 import BeautifulSoup

if __name__ == "__main__":
    print("Starting test...")
    engine = init_db()
    print("Database connector engine intialized...")
    with Session(engine) as session:
        print("Database connector session made...")
        pageNum = 2
        servers = scan_pages(pageNum)
        if servers == None:
            print("No servers found on the website...")
        else:
            for server in servers:
                if select(exists(Server).where(Server.ip==server.ip)):
                    print(session.scalars(select(Server).where(Server.ip==server.ip)))
                    print("Server alredy exists in the DB...")
                else:
                    print("Server info scanned, adding to db...")
                    session.add(server)
                    session.commit()
                    print("Server info added...")

    engine.dispose()


