import sqlite3
import os

DB_PATH = 'sleep_monitor.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            camera_id TEXT,
            person_id INTEGER,
            image_path TEXT,
            vlm_verdict TEXT DEFAULT 'PENDING',
            email_sent BOOLEAN DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("SQLite Database initialized successfully.")
