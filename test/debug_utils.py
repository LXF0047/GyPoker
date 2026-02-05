# _*_ coding: utf-8 _*_
# @Time : 2026/1/26 00:39 
# @Author : lxf 
# @Version：V 0.1
# @File : debug_utils.py
# @desc : Debug utilities for managing the game database

import pysqlite3 as sqlite3
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


def init_bot_players():
    """按名字初始化27名机器人玩家"""
    bot_player_names = [
        "Doyle Brunson",
        "Stu Ungar",
        "Johnny Chan",
        "Phil Hellmuth",
        "Phil Ivey",
        "Daniel Negreanu",
        "Erik Seidel",
        "Justin Bonomo",
        "Bryn Kenney",
        "Jason Koon",
        "Stephen Chidwick",
        "Fedor Holz",
        "Tom Dwan",
        "Antonio Esfandiari",
        "Dan Smith",
        "Isaac Haxton",
        "Mikita Badziakouski",
        "Linus Loeliger",
        "Doug Polk",
        "Chip Reese",
        "Johnny Moss",
        "Amarillo Slim Preston",
        "Jennifer Harman",
        "Vanessa Selbst",
        "Patrik Antonius",
        "Viktor Blom",
        "Joe Cada"
    ]
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        for idx, name in enumerate(bot_player_names):
            if idx < 9:
                name_id = "easy_bot_{}".format(idx + 1)
            elif idx < 18:
                name_id = "medium_bot_{}".format(idx - 8)
            else:
                name_id = "hard_bot_{}".format(idx - 17)
            cursor.execute("""
                           INSERT INTO players (username, password_hash, nickname)
                           VALUES (?, ?, ?)
                           """, (name_id, generate_password_hash("root"), name))
        conn.commit()
        print("Bot players initialized successfully.")
    except sqlite3.IntegrityError:
        print("Error: One or more bot players already exist.")
    except sqlite3.Error as e:
        print(f"Error initializing bot players: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    # clear_all_data()
    # init_system_users()
    init_bot_players()
