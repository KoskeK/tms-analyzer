import dbHandler
import scanner
from tqdm import tqdm
db = dbHandler.dbHandler()
servers = db.get_servers("enabled", True)
pbar = tqdm(total=len(servers), desc="Updating player counts")
for server in servers:
    pbar.update(1)
    ip = server[1]
    player_count = scanner.get_player_count(ip)
    if player_count["online"]:
        db.update_player_count(ip, player_count)
    else:
        db.update_server(server[0], ["enabled"], [False])
db.close()
print("Done!")