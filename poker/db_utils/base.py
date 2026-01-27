# _*_ coding: utf-8 _*_
# @Time : 2026/1/23 00:52
# @Author : lxf
# @Version：V 0.1
# @File : base.py
# @desc : Base database connection utilities

import sqlite3
import logging
import os

# Database path (relative to project root)
# Ensure we are pointing to the correct path regardless of where this is imported
# Assuming the project root is 2 levels up from here if run as module, 
# but relying on relative path 'database/poker.sqlite3' from CWD is what the original code did.
DB_PATH = "database/poker.sqlite3"

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for concurrency
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn
    except sqlite3.Error as e:
        logging.error(f"Database connection error: {e}")
        return None
