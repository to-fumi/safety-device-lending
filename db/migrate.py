import os
import sqlite3

db_path = os.path.join("db", "lending.db")
init_path = os.path.join("db", "init.sql")

if not os.path.exists(init_path):
    print(f"{init_path} not found. No DB created.")
else:
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    with open(init_path, "r", encoding="utf-8") as f:
        sql_script = f.read()
    conn.executescript(sql_script)
    conn.close()
    print(f"DB initialized from {init_path}.")
