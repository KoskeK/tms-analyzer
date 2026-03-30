import dbHandler
import scanner
from tqdm import tqdm
db = dbHandler.dbHandler()
servers = db.get_all_servers("enabled", True)
pbar = tqdm(total=len(servers), desc="Updating player counts")
for server in servers:
    pbar.update(1)
    ip = server[1]
    player_count = scanner.check_server(ip)
    if player_count["online"]:
        db.add_status(server[0], player_count["players"])
    else:
        db.update_server(server[0], enabled=False)
db.close()
print("Done!")