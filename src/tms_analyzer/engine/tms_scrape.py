from invisible_playwright import InvisiblePlaywright
import logging
from bs4 import BeautifulSoup
from sqlalchemy import select, exists
from sqlalchemy.orm import Session
from tms_analyzer.shared.database import init_db
from tms_analyzer.shared.models import Server

def extract_servers(html):
    soup = BeautifulSoup(html, "html.parser")

    servers = []

    # Find the main Minecraft server listing
    table = soup.select_one("table.serverlist")

    if table is None:
        raise ValueError("Could not find table.serverlist in HTML")

    for row in table.select("tbody tr"):

        # Extract IP
        ip_element = row.select_one(
            "td.server-name .server-ip .form-control"
        )

        # Extract version
        version_element = row.select_one(
            'td.server-info a.badge[href^="/version/"]'
        )

        # Extract tags
        tag_elements = row.select(
            'td.server-info span[rel="tag"]'
        )

        # Skip rows without an IP
        if not ip_element:
            continue

        ip = ip_element.get_text(strip=True)

        version = (
            version_element.get_text(strip=True)
            if version_element else None
        )

        tags = [
            tag.get_text(strip=True)
            for tag in tag_elements
            if tag.get_text(strip=True)
        ]

        servers.append(Server(
            ip=ip,
            version=version,
            tags=str(tags),
            enabled=True
        ))

    return servers


def scrape():
    with InvisiblePlaywright(headless=True) as browser:
        with Session(engine) as session:
            while True:
                page = browser.new_page()
                if pageNum == 1:
                    url = "https://topminecraftservers.org/sort/new"
                else:
                    url = f"https://topminecraftservers.org/sort/new/page/{pageNum}"
                page.goto(url)
                page.wait_for_timeout(1000)
                if response.status != 200 or response.url != url:
                    logging.warning(f"Page {url} answered with code {response.status}")
                    browser.close()
                    return
                servers = extract_servers(page.content())
                if not servers:
                    logging.warn(f"No servers found on page {url}, aborting...")
                for server in servers:
                    if session.scalar(exists(Server).where(Server.ip==server.ip)):
                        logging.info(f"Server {server.ip} alredy in the database, ending scraping...")
                        browser.close()
                        return
                    else:
                        session.add(server)
                session.commit()
        browser.close()