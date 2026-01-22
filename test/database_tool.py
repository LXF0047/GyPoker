# _*_ coding: utf-8 _*_
# @Time : 2026/1/22 17:23 
# @Author : lxf 
# @Version：V 0.1
# @File : database_tool.py
# @desc :
import sqlite3

DATABASE_PATH = "database/user.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def drop_tabel(table_name):
    # 删除daily表
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"""
            DROP TABLE {table_name}
        """)
        conn.commit()
    except Exception as e:
        print(f"Error dropping daily table in database: {e}")
    finally:
        cursor.close()
        conn.close()


def delete_player_in_users(player_name):
    # 删除user表中某个玩家
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM users WHERE username=?", (player_name,))
        conn.commit()
    except Exception as e:
        print(f"Error deleting player from database: {e}")
    finally:
        cursor.close()
        conn.close()
