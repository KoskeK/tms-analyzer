import dbHandler
import scanner

def scan():
    db = dbHandler.dbHandler()
    data = db.get_all_servers()
    print(data)

if __name__ == "__main__":
    db = dbHandler.dbHandler()
    servers = scanner.scan_pages(1)
    for server in servers:
        db.add_server(server["ip"], server["img"], ",".join(server["tags"]), server["version"])
    db.close()