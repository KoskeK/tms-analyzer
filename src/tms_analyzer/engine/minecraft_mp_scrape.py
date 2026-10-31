from sqlalchemy import select, exists
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import init_db
from tms_analyzer.shared.models import Server
import os
import httpx
from bs4 import BeautifulSoup
import time
import logging

def scan_pages(num=1):
    if num ==1:
        response = httpx.get(f"https://minecraft-mp.com/servers/latest/")
        logging.info("Scanning https://minecraft-mp.com/servers/latest/")
    else:
        response = httpx.get(f"https://minecraft-mp.com/servers/latest/{num}/")
        logging.info(f"Scanning {f"https://minecraft-mp.com/servers/latest/{num}/"}")
    if response.status_code == 404:
        return

    soup = BeautifulSoup(response.text, "html.parser")

    data = []
    rows = soup.select("tr")
    logging.info(f"Found {len(rows)} servers!")
    for row in rows:
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
            ip=ip_text if ip_text else "broken",
            tags=str(tags) if tags else "broken",
            enabled=True,
            version=version_text if version_text else "broken",
            url=url if url else "broken"
        )
        )
    return data

if __name__ == "__main__":
    engine = init_db()
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
    logging.info("Logging started...")
    logging.info("Engine intiated...")

    with Session(engine) as session:
        logging.info("DB session loaded...")
        pageNum = 1
        logging.info("Scanning started...")
        while True:
            time.sleep(0.2)
            servers = scan_pages(pageNum)
            if servers == None:
                logging.info("The value of scan_pages was None. Breaking the loop")
                break
            else:
                for server in servers:
                    if session.scalar(select(exists(Server).where(Server.ip==server.ip))):
                        logging.info(f"Server {url} found in the DB, stopping the scraping...")
                        break
                    else:
                        session.add(server)
                        logging.info(f"Server {server.ip} added!")
                        session.commit()
            pageNum+=1

    engine.dispose()