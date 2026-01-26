# _*_ coding: utf-8 _*_ 
# @Time : 2026/1/23 14:23 
# @Author : lxf 
# @Version：V 0.1
# @File : game_round.py
# @desc : Game round and hand management

import sqlite3
import logging
from typing import Optional
from .base import get_db_connection


def get_or_create_table(name: str, max_seats: int = 10) -> Optional[int]:
    """
    Get existing poker table by name or create a new one.
    Returns table_id.
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        # Check if exists
        cursor = conn.execute("SELECT id FROM poker_tables WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            return row['id']

        # Create new
        cursor = conn.execute("INSERT INTO poker_tables (name, max_seats) VALUES (?, ?)", (name, max_seats))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logging.error(f"Error getting/creating table {name}: {e}")
        return None
    finally:
        conn.close()


def create_hand(table_id: int, small_blind: int, big_blind: int) -> Optional[int]:
    """
    Create a new hand record.
    Returns hand_id.
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.execute("""
                              INSERT INTO hands (table_id, small_blind, big_blind, started_at)
                              VALUES (?, ?, ?, unixepoch())
                              """, (table_id, small_blind, big_blind))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logging.error(f"Error creating hand for table {table_id}: {e}")
        return None
    finally:
        conn.close()


def add_hand_player(hand_id: int, player_id: int, seat_no: int, starting_stack: float, position_name: str = None,
                    hole_cards: str = None) -> bool:
    """
    Record a player participating in a hand.
    """
    conn = get_db_connection()
    if not conn:
        return False
    try:
        conn.execute("""
                     INSERT INTO hand_players (hand_id, player_id, seat_no, starting_stack, ending_stack, position_name,
                                               hole_cards)
                     VALUES (?, ?, ?, ?, ?, ?, ?)
                     """, (hand_id, player_id, seat_no, starting_stack, starting_stack, position_name, hole_cards))
        # ending_stack init to starting_stack, will be updated later
        conn.commit()
        return True
    except sqlite3.Error as e:
        logging.error(f"Error adding player {player_id} to hand {hand_id}: {e}")
        return False
    finally:
        conn.close()


def update_hand_player_result(hand_id: int, player_id: int, ending_stack: float, is_winner: bool,
                              hole_cards: str = None) -> bool:
    """
    Update player's result for a hand (ending stack, winner status, hole cards if revealed).
    """
    conn = get_db_connection()
    if not conn:
        return False
    try:
        sql = """
              UPDATE hand_players
              SET ending_stack = ?,
                  is_winner    = ? \
              """
        params = [ending_stack, is_winner]

        if hole_cards:
            sql += ", hole_cards = ?"
            params.append(hole_cards)

        sql += " WHERE hand_id = ? AND player_id = ?"
        params.extend([hand_id, player_id])

        conn.execute(sql, params)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logging.error(f"Error updating result for player {player_id} in hand {hand_id}: {e}")
        return False
    finally:
        conn.close()


def add_hand_action(hand_id: int, player_id: int, street: int, action_num: int, action_type: str, amount: int,
                    pot_before: int) -> bool:
    """
    Record a player's action.
    """
    conn = get_db_connection()
    if not conn:
        return False
    try:
        conn.execute("""
                     INSERT INTO hand_actions (hand_id, player_id, street, action_num, action_type, amount, pot_before)
                     VALUES (?, ?, ?, ?, ?, ?, ?)
                     """, (hand_id, player_id, street, action_num, action_type, amount, pot_before))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logging.error(f"Error adding action for hand {hand_id}: {e}")
        return False
    finally:
        conn.close()


def finish_hand(hand_id: int, board_cards: str, total_pot: int) -> bool:
    """
    Mark hand as finished.
    """
    conn = get_db_connection()
    if not conn:
        return False
    try:
        conn.execute("""
                     UPDATE hands
                     SET ended_at    = unixepoch(),
                         board_cards = ?,
                         total_pot   = ?
                     WHERE id = ?
                     """, (board_cards, total_pot, hand_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logging.error(f"Error finishing hand {hand_id}: {e}")
        return False
    finally:
        conn.close()
