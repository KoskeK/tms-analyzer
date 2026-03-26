import sqlite3

class dbHandler:
    def __init__(self):
        self.conn = sqlite3.connect("servers.db")
        self.cursor = self.conn.cursor()
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            img TEXT,
            tags TEXT,
            version TEXT,
            enabled BOOLEAN DEFAULT 1,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            player_count INTEGER,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        )
        """)
        self.conn.commit()

    def add_server(self, ip, img=None, tags=None, version=None):
        self.cursor.execute("INSERT INTO servers (ip, img, tags, version) VALUES (?, ?, ?, ?)", (ip, img, tags, version))
        self.conn.commit()
    
    def update_server(self, server_id, **kwargs):
        fields = []
        values = []
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)
        values.append(server_id)
        self.cursor.execute(f"UPDATE servers SET {', '.join(fields)}, date_updated = CURRENT_TIMESTAMP WHERE id = ?", values)
        self.conn.commit()

    def get_servers(self, key, value):
        self.cursor.execute(f"SELECT * FROM servers WHERE {key} = ?", (value,))
        return self.cursor.fetchall()

    def get_all_servers(self):
        self.cursor.execute("SELECT * FROM servers")
        return self.cursor.fetchall()

    def add_status(self, server_id, player_count):
        self.cursor.execute("INSERT INTO server_status (server_id, player_count) VALUES (?, ?)", (server_id, player_count))
        self.conn.commit()

    def close(self):
        self.conn.close()