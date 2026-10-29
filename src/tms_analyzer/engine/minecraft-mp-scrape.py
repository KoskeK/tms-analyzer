from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import DATABASE_URL
from tms_analyzer.shared.models import Server, Report
from dotenv import load_dotenv
import os
import httpx
from bs4 import BeautifulSoup

def scan_pages(num=1):
    response = httpx.get(f"https://minecraft-mp.com/servers/latest/{num}/")
    if response.status_code == 404:
        return

    soup = BeautifulSoup(response.text, "html.parser")

    data = []

    for row in soup.select("tr"):
        # Server IP
        a = row.select_one("div.server-ip-group a.btn-server-ip")
        if not a:
            continue

        ip_text = a.get_text(strip=True)

        # Tags
        tags_div = row.select_one("div.list-server-tags-scroll")
        tags = []
        if tags_div:
            tags = [
                tag.get_text(strip=True)
                for tag in row.select(".btn-tag")
            ]
        
        url_div = row.select_one("div.server-card")
        if url_div:
            url = f"https://minecraft-mp.com{url_div.select_one("a").get("href")}"
        
        a_version = row.select_one(
        "a.btn.btn-default.btn-xs.btn-block-xs.btn-version-fade.text-left"
    )
        version_text = a_version.get_text(strip=True) if a_version else None

        # Combine
        data.append(
        Server(
            ip=ip_text,
            tags=tags,
            enabled=True,
            version=version_text,
            url=url
        )
        )
    return data

if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)

    with Session(engine) as session:
        pageNum = 1
        while True:
            servers = scan_pages(pageNum)
            if servers == None:
                break
            else:
                for server in servers:
                    if session.scalars(select(Server).where(Server.ip==server.ip)) != None:
                        break
                    else:
                        session.add(server)
                        session.commit()

    engine.dispose()