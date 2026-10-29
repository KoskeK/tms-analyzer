import httpx
from bs4 import BeautifulSoup
from mcstatus import JavaServer

def scan_pages(num=1):
    response = httpx.get(f"https://minecraft-mp.com/servers/latest/{num}/")

    soup = BeautifulSoup(response.text, "html.parser")

    data = []

    for row in soup.select("tr"):
        # Server IP
        a = row.select_one("div.server-ip-group a.btn-server-ip")
        if not a:
            continue

        ip_text = a.get_text(strip=True)

        img = a.find("img")
        img_src = None
        if img:
            img_src = img.get("src") or img.get("data-src")

        # Tags
        tags_div = row.select_one("div.list-server-tags-scroll")
        tags = []
        if tags_div:
            tags = [tag.get_text(strip=True) for tag in tags_div.find_all("a")]
        
        a_version = row.select_one(
        "a.btn.btn-default.btn-xs.btn-block-xs.btn-version-fade.text-left"
    )
        version_text = a_version.get_text(strip=True) if a_version else None

        # Combine
        data.append({
            "ip": ip_text,
            "img": img_src,
            "tags": tags,
            "enabled": True,
            "version": version_text
        })
    return data

def check_server(ip):
    try:
        server = JavaServer.lookup(ip)
        status = server.status()
        return {
            "ip": ip,
            "online": True,
            "players": status.players.online,
            "max_players": status.players.max,
            "version": status.version.name
        }
    except Exception as e:
        print(f"Error checking server {ip}: {e}")
        return {
            "ip": ip,
            "online": False
        }