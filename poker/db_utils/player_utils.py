# _*_ coding: utf-8 _*_
# @Time : 2026/1/23 14:55
# @Author : lxf
# @Version：V 0.1
# @File : player_utils.py
# @desc : Player management database operations

import sqlite3
import logging
from typing import Optional, Dict, Any
from .base import get_db_connection

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

def update_player_profile(user_id: int, nickname: str = None, password_hash: str = None, avatar: str = None) -> bool:
    """
    Update player profile.
    """
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        # Construct query dynamically based on provided fields
        updates = []
        params = []
        
        if nickname is not None:
            updates.append("nickname = ?")
            params.append(nickname)
            
        if password_hash is not None:
            updates.append("password_hash = ?")
            params.append(password_hash)
            
        if avatar is not None:
            updates.append("avatar = ?")
            params.append(avatar)
            
        if not updates:
            return True # Nothing to update
            
        params.append(user_id)
        
        query = f"UPDATE players SET {', '.join(updates)} WHERE id = ?"
        
        conn.execute(query, tuple(params))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logging.error(f"Error updating player {user_id}: {e}")
        return False
    finally:
        conn.close()