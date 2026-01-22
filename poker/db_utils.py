# _*_ coding: utf-8 _*_
# @Time : 2026/1/23 00:52 
# @Author : lxf 
# @Version：V 0.1
# @File : db_utils.py
# @desc : New database utility functions using the updated schema

import sqlite3
import logging
from typing import Optional, Dict, Any

# Database path (relative to project root)
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

def get_player_by_login_username(username: str) -> Optional[Dict[str, Any]]:
    """
    Find a player by their login username (unique).
    Returns a dict with player info joined with wallet info (chips).
    Mappings:
    - username (login) -> username
    - nickname (display) -> nickname
    - chips -> money
    """
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.execute("""
            SELECT p.id, p.username, p.password_hash, p.nickname, p.avatar, w.chips 
            FROM players p
            LEFT JOIN wallet w ON p.id = w.player_id
            WHERE p.username = ?
        """, (username,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except sqlite3.Error as e:
        logging.error(f"Error fetching player by username {username}: {e}")
        return None
    finally:
        conn.close()

def get_player_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Find a player by their ID.
    Returns a dict with player info joined with wallet info.
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.execute("""
            SELECT p.id, p.username, p.password_hash, p.nickname, p.avatar, w.chips 
            FROM players p
            LEFT JOIN wallet w ON p.id = w.player_id
            WHERE p.id = ?
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except sqlite3.Error as e:
        logging.error(f"Error fetching player by id {user_id}: {e}")
        return None
    finally:
        conn.close()

def create_player(username: str, password_hash: str, nickname: str, avatar: str) -> bool:
    """
    Create a new player.
    Wallet is created automatically via database trigger (trg_init_player).
    
    :param username: Login username (unique)
    :param password_hash: Hashed password
    :param nickname: Display name
    :param avatar: Avatar base64 string or URL
    :return: True if successful, False if username exists or other error
    """
    conn = get_db_connection()
    if not conn:
        return False

    try:
        conn.execute("""
            INSERT INTO players (username, password_hash, nickname, avatar)
            VALUES (?, ?, ?, ?)
        """, (username, password_hash, nickname, avatar))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Username likely already exists
        return False
    except sqlite3.Error as e:
        logging.error(f"Error creating player {username}: {e}")
        return False
    finally:
        conn.close()

def get_api_key(service_name: str) -> Optional[str]:
    """Get API Key for a service."""
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.execute("SELECT api_key FROM api_keys WHERE service_name = ?", (service_name,))
        result = cursor.fetchone()
        return result['api_key'] if result else None
    except sqlite3.Error as e:
        logging.error(f"Error getting api key for {service_name}: {e}")
        return None
    finally:
        conn.close()