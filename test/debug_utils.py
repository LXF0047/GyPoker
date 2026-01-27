# _*_ coding: utf-8 _*_
# @Time : 2026/1/26 00:39 
# @Author : lxf 
# @Version：V 0.1
# @File : debug_utils.py
# @desc : Debug utilities for managing the game database

import sqlite3
import os
from werkzeug.security import generate_password_hash

# Define database path relative to the project root
# This assumes the script is run from the project root or the path is correct relative to CWD
# DB_PATH = "database/poker.sqlite3"
DB_PATH = "/Users/f/Documents/project/GyPoker/database/poker.sqlite3"


def get_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
        return None


def clear_all_data():
    """
    Clears all data from all tables in the database and resets auto-increment counters.
    This effectively resets the game to a clean state.
    """
    if not os.path.exists(DB_PATH):
        print(f"Database file not found at: {DB_PATH}")
        return

    conn = get_db_connection()
    if not conn:
        return

    # List of tables to clear
    tables = [
        "hand_actions",
        "hand_players",
        "hands",
        "chip_transactions",
        "player_daily_stats",
        "player_lifetime_stats",
        "wallet",
        "players",
        "poker_tables",
        "sqlite_sequence"
    ]

    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF;")

        print("Starting database reset...")
        for table in tables:
            cursor.execute(f"DELETE FROM {table}")
            print(f"Cleared table: {table}")

        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON;")
        print("Database reset successfully!")

    except sqlite3.Error as e:
        print(f"Error clearing database: {e}")
        conn.rollback()
    finally:
        conn.close()


def init_system_users():
    """
    Registers two system users: admin1 and admin2 with password 'root'.
    """
    conn = get_db_connection()
    if not conn:
        return

    users = [
        ("admin1", "root", "管理员1"),
        ("admin2", "root", "管理员2")
    ]

    try:
        cursor = conn.cursor()
        for username, password, nickname in users:
            password_hash = generate_password_hash(password)
            # trg_init_player trigger will automatically create the wallet
            cursor.execute("""
                           INSERT INTO players (username, password_hash, nickname)
                           VALUES (?, ?, ?)
                           """, (username, password_hash, nickname))
            print(f"Registered system user: {username} ({nickname})")

        conn.commit()
        print("System users initialized successfully.")
    except sqlite3.IntegrityError:
        print("Error: One or more system users already exist.")
    except sqlite3.Error as e:
        print(f"Error initializing system users: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    # 1. Reset DB
    clear_all_data()
    # 2. Add system users
    init_system_users()
