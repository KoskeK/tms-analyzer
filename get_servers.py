import scanner 
import dbHandler

maxCount = 100

db = dbHandler.dbHandler()
for i in range(1, maxCount + 1):
    servers = scanner.scan_pages(i)
    for server in servers:
        db.add_server(server["ip"], server["img"], ",".join(server["tags"]), server["version"])
db.close()
print("Done!")