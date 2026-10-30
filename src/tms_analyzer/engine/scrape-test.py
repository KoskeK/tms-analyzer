from tms_analyzer.engine.minecraft_mp_scrape import scan_pages
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import DATABASE_URL
from tms_analyzer.shared.models import Server, Report
from dotenv import load_dotenv
import os
import httpx
from bs4 import BeautifulSoup

if __name__ == "__main__":
    print("Starting test...")
    engine = create_engine(DATABASE_URL)
    print("Database connector engine intialized...")
    with Session(engine) as session:
        print("Database connector session made...")
        pageNum = 2
        servers = scan_pages(pageNum)
        if servers == None:
            print("No servers found on the website...")
        else:
            for server in servers:
                if session.scalars(select(Server).where(Server.ip==server.ip)) != None:
                    print("Server alredy exists in the DB...")
                else:
                    print("Server info scanned, adding to db...")
                    session.add(server)
                    session.commit()
                    print("Server info added...")

    engine.dispose()


