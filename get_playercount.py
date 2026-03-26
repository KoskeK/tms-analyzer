import dbHandler
import scanner

db = dbHandler.dbHandler()
servers = db.get_servers()
for server in servers:
    ip = server[0]
    player_count = scanner.get_player_count(ip)
    db.update_player_count(ip, player_count)
db.close()
print("Done!")