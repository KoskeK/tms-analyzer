import scanner 
import dbHandler
from tqdm import tqdm
import time

maxCount = 100

db = dbHandler.dbHandler()
pbar = tqdm.pbar(total=maxCount, desc="Scanning pages")
for i in range(1, maxCount + 1):
    servers = scanner.scan_pages(i)
    for server in servers:
        db.add_server(server["ip"], server["img"], ",".join(server["tags"]), server["version"])
    pbar.update(1)
    time.sleep(0.5)
db.close()
print("Done!")