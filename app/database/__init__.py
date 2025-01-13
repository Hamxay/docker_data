from app import db

def get_db_connection():
    import os
    import sqlite3

    current_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(current_dir, 'database.db')

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
