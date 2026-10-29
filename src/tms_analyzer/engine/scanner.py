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

        # Tags
        tags_div = row.select_one("div.list-server-tags-scroll")
        tags = []
        if tags_div:
            tags = [
                tag.get_text(strip=True)
                for tag in row.select(".btn-tag")
            ]
        
        a_version = row.select_one(
        "a.btn.btn-default.btn-xs.btn-block-xs.btn-version-fade.text-left"
    )
        version_text = a_version.get_text(strip=True) if a_version else None

        # Combine
        data.append({
            "ip": ip_text,
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
        }
    except Exception as e:
        print(f"Error checking server {ip}: {e}")
        return {
            "ip": ip,
            "online": False
        }

if __name__ == "__main__":
    print(scan_pages(2))
    print(scan_pages(10000000))