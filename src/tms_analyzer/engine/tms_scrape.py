
import logging

from invisible_playwright import InvisiblePlaywright
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import init_db
from tms_analyzer.shared.models import Server


BASE_URL = "https://topminecraftservers.org"
START_URL = f"{BASE_URL}/sort/new"

BLOCKED_RESOURCE_TYPES = {
    "image",
    "media",
    "font",
    "stylesheet",
}


def extract_servers(html):
    """Extract Minecraft servers from a listing page."""

    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.serverlist")

    if table is None:
        raise ValueError("Could not find table.serverlist in HTML")

    servers = []

    for row in table.select("tbody tr"):
        ip_element = row.select_one(
            "td.server-name .server-ip .form-control"
        )

        if not ip_element:
            continue

        version_element = row.select_one(
            'td.server-info a.badge[href^="/version/"]'
        )

        tag_elements = row.select(
            'td.server-info span[rel="tag"]'
        )

        url_element = row.select_one(
            "a.visible-sm.visible-md.visible-lg[href]"
        )

        if not url_element:
            continue

        ip = ip_element.get_text(strip=True)

        if not ip:
            continue

        href = url_element.get("href")

        if not href:
            continue

        url = f"{BASE_URL}{href}"

        version = (
            version_element.get_text(strip=True)
            if version_element
            else None
        )

        tags = [
            tag.get_text(strip=True)
            for tag in tag_elements
            if tag.get_text(strip=True)
        ]

        servers.append(
            Server(
                ip=ip,
                version=version,
                tags=str(tags),
                enabled=True,
                url=url,
            )
        )

    return servers


def should_abort_request(route):
    """Block unnecessary browser resources."""

    if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
        route.abort()
    else:
        route.continue_()


def load_existing_servers(session):
    """Load existing IPs and URLs into memory."""

    logging.info("Loading existing servers from database...")

    result = session.execute(
        select(Server.ip, Server.url)
    )

    existing_ips = set()
    existing_urls = set()

    for ip, url in result:
        existing_ips.add(ip)
        existing_urls.add(url)

    logging.info(
        "Loaded %d existing IPs and %d URLs",
        len(existing_ips),
        len(existing_urls),
    )

    return existing_ips, existing_urls


def process_servers(
    session,
    servers,
    existing_ips,
    existing_urls,
):
    """Filter duplicates and insert new servers."""

    new_servers = []

    for server in servers:

        # A previously scraped URL means we've reached old listings.
        if server.url in existing_urls:
            logging.info(
                "Server %s already exists. "
                "Reached previously scraped listings.",
                server.url,
            )
            return False

        # Same IP, different URL: skip it.
        if server.ip in existing_ips:
            logging.debug(
                "Server %s already exists from another source.",
                server.ip,
            )
            continue

        new_servers.append(server)

        # Update sets immediately to prevent duplicates
        # within the same scraping run.
        existing_ips.add(server.ip)
        existing_urls.add(server.url)

    if new_servers:
        session.add_all(new_servers)
        session.commit()

        logging.info(
            "Inserted %d new servers.",
            len(new_servers),
        )

    return True


def scrape():
    engine = init_db()

    with Session(engine) as session:
        existing_ips, existing_urls = load_existing_servers(session)

        with InvisiblePlaywright(headless=True) as browser:
            page = browser.new_page()

            # Block unnecessary resources.
            page.route("**/*", should_abort_request)

            page_num = 1

            while True:

                if page_num == 1:
                    url = START_URL
                else:
                    url = f"{START_URL}/page/{page_num}"

                logging.info("Scraping page %d: %s", page_num, url)

                try:
                    response = page.goto(
                        url,
                        wait_until="domcontentloaded",
                    )

                    if (
                        response is None
                        or response.status != 200
                        or page.url.rstrip("/") != url.rstrip("/")
                    ):
                        status = (
                            response.status
                            if response is not None
                            else "No response"
                        )

                        logging.warning(
                            "Page %s returned %s. Stopping.",
                            url,
                            status,
                        )
                        break

                    html = page.content()

                    servers = extract_servers(html)

                except Exception:
                    logging.exception(
                        "Failed to scrape page %s",
                        url,
                    )
                    break

                if not servers:
                    logging.warning(
                        "No servers found on page %s. Stopping.",
                        url,
                    )
                    break

                logging.info(
                    "Found %d servers on page %d.",
                    len(servers),
                    page_num,
                )

                should_continue = process_servers(
                    session,
                    servers,
                    existing_ips,
                    existing_urls,
                )

                if not should_continue:
                    break

                page_num += 1

    logging.info("Scraping completed.")


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s",
        level=logging.INFO,
    )

    logging.info("Starting Minecraft server scraper...")

    scrape()
