# _*_ coding: utf-8 _*_
# @Time : 2026/1/23 14:49 
# @Author : lxf 
# @Version：V 0.1
# @File : chips_operation.py
# @desc : Wallet and chips operations

import pysqlite3 as sqlite3
import logging
from .base import get_db_connection


def update_player_wallet(player_id: int, money: float) -> bool:
    """
    更新玩家钱包中筹码，wallet表
    
    :param player_id: The player's ID
    :param money: The new amount of chips
    :return: True if successful, False otherwise
    """
    conn = get_db_connection()
    if not conn:
        return False

    try:
        conn.execute("""
                     UPDATE wallet
                     SET chips      = ?,
                         updated_at = unixepoch()
                     WHERE player_id = ?
                     """, (money, player_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logging.error(f"Error updating wallet for player {player_id}: {e}")
        return False
    finally:
        conn.close()


def auto_topup_chips(player_id: int, amount: int, hand_id: int = None) -> bool:
    """
    为玩家自动追加筹码
    更新wallet表，更新chip_transactions表

    :param player_id: 玩家id
    :param amount: 追加金额
    :param hand_id: 手牌id
    :return:
    """
    conn = get_db_connection()
    if not conn:
        return False

    try:
        # Start transaction
        cursor = conn.cursor()

        # 1. Update wallet
        cursor.execute("""
                       UPDATE wallet
                       SET chips      = chips + ?,
                           updated_at = unixepoch()
                       WHERE player_id = ?
                       """, (amount, player_id))

        # 2. Record transaction
        cursor.execute("""
                       INSERT INTO chip_transactions (player_id, tx_type, amount, hand_id)
                       VALUES (?, 'auto_topup', ?, ?)
                       """, (player_id, amount, hand_id))

        conn.commit()
        return True
    except sqlite3.Error as e:
        conn.rollback()
        logging.error(f"Error auto-topping up for player {player_id}: {e}")
        return False
    finally:
        conn.close()


def check_and_reset_daily_chips(player_id: int, init_money: int = 3000) -> int:
    """
    检查并执行每日筹码重置。
    如果今天是新的一天（与 last_reset_date 不同），则将筹码重置为 init_money。
    返回当前（可能更新后的）筹码数量。

    :param player_id: 玩家ID
    :param init_money: 初始资金 (默认3000)
    :return: 当前筹码数
    """
    conn = get_db_connection()
    if not conn:
        return 0

    try:
        cursor = conn.cursor()
        
        # 1. 获取当前筹码和上次重置日期
        cursor.execute("SELECT chips, last_reset_date FROM wallet WHERE player_id = ?", (player_id,))
        row = cursor.fetchone()
        
        if not row:
            # 钱包不存在，应该不会发生（有触发器），但防守性编程
            logging.warning(f"Wallet not found for player {player_id}, creating one.")
            cursor.execute("INSERT INTO wallet (player_id, chips, last_reset_date) VALUES (?, ?, date('now'))", 
                           (player_id, init_money))
            conn.commit()
            return init_money

        current_chips = row['chips']
        last_reset_date = row['last_reset_date']
        
        # 获取今天日期 (SQLite date('now') returns 'YYYY-MM-DD' in UTC by default, make sure we use 'localtime' if needed, 
        # or stick to server time. The DDL uses date('now'). Let's match that.)
        cursor.execute("SELECT date('now', 'localtime')") # 使用本地时间更符合用户习惯
        today = cursor.fetchone()[0]
        
        if last_reset_date != today:
            # 需要重置
            logging.info(f"Resetting chips for player {player_id} from {current_chips} to {init_money}. Last reset: {last_reset_date}, Today: {today}")
            
            # 计算差额用于记录 (虽然直接置为3000，但记录变动量可能有用，或者直接记录结果)
            # Schema requires amount. Let's record the *change* or just the new amount? 
            # Logic: We are setting it TO 3000. 
            # If we want 'amount' to reflect the injection/removal: amount = 3000 - current_chips.
            diff = init_money - current_chips
            
            cursor.execute("""
                UPDATE wallet 
                SET chips = ?, 
                    last_reset_date = ?,
                    updated_at = unixepoch()
                WHERE player_id = ?
            """, (init_money, today, player_id))
            
            # 记录流水
            cursor.execute("""
                INSERT INTO chip_transactions (player_id, tx_type, amount, note)
                VALUES (?, 'daily_reset', ?, ?)
            """, (player_id, diff, f"Daily reset from {current_chips} to {init_money}"))
            
            conn.commit()
            return init_money
        else:
            # 今天已经重置过（或登录过），保持原样
            return current_chips
            
    except sqlite3.Error as e:
        conn.rollback()
        logging.error(f"Error checking daily chips for player {player_id}: {e}")
        return 0 # Should ideally handle error better, but returning 0 or current chips is safe fallback
    finally:
        conn.close()
