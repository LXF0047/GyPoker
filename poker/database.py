# _*_ coding: utf-8 _*_ 
# @Time : 2024/12/3 21:27 
# @Author : lxf 
# @Version：V 0.1
# @File : database.py
# @desc : 
import sqlite3

# DATABASE_PATH = "/home/pypoker/user.db"
DATABASE_PATH = "database/user.db"
INIT_MONEY = 3000


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


def update_player_in_db(player_data):
    """
    将玩家数据插入或更新到数据库
    :param player_data: 字典形式的玩家数据
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE users
            SET money = ?,
                loan = ?,
                hands = hands + 1
            WHERE id = ?
        """, (player_data["money"], player_data["loan"], player_data["id"]))

        conn.commit()
    except Exception as e:
        print(f"Error updating player data in database: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def reset_player_in_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 将所有数据重置为默认值
        cursor.execute("""
            UPDATE users
            SET money = ?,
                loan = 0,
                hands = 0
        """, (INIT_MONEY,))
        conn.commit()
    except Exception as e:
        print(f"Error reset player data in database: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def reset_players_in_db(player_ids):
    """
    重置指定玩家列表的积分
    :param player_ids: 玩家ID列表
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        placeholders = ', '.join('?' for _ in player_ids)
        sql = f"UPDATE users SET money = ?, loan = 0, hands = 0 WHERE id IN ({placeholders})"
        
        # The first argument is INIT_MONEY, followed by the player IDs
        params = [INIT_MONEY] + player_ids
        cursor.execute(sql, params)
        conn.commit()
    except Exception as e:
        print(f"Error resetting specific players data in database: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def query_all_data(table):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()

        if not rows:
            print("No data found.")
            return

        # 获取列名并排除指定列
        excluded_columns = {"password"}  # 要排除的列
        column_names = [col for col in rows[0].keys() if col not in excluded_columns]

        # 构建 Markdown 表格
        header = "| " + " | ".join(column_names) + " |"
        separator = "| " + " | ".join(["---"] * len(column_names)) + " |"
        rows_data = [
            "| " + " | ".join([str(row[col]) for col in column_names]) + " |"
            for row in rows
        ]

        # 打印 Markdown 表格
        markdown_table = "\n".join([header, separator] + rows_data)
        print(markdown_table)
    except Exception as e:
        print(f"Error querying data from database: {e}")
    finally:
        cursor.close()
        conn.close()


def query_ranking_in_db(player_names=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if player_names:
            placeholders = ', '.join('?' for _ in player_names)
            sql = f"SELECT username, money, loan, hands, id FROM users WHERE username IN ({placeholders})"
            cursor.execute(sql, player_names)
        else:
            cursor.execute("SELECT username, money, loan, hands, id FROM users")
        rows = cursor.fetchall()
        # 结果转为列表
        return [list(row) for row in rows]
    except Exception as e:
        print(f"Error querying data from database: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_ranking_list():
    # 获取排行列表
    daily_ranking = get_daily_ranking()
    active_players = list(daily_ranking.keys())

    if not active_players:
        return []

    all_player_data = query_ranking_in_db(active_players)
    ranking_data = []
    for player_data in all_player_data:
        player_name, player_money, player_loan, player_hands, _ = player_data[0], player_data[1], player_data[2], \
            player_data[3], player_data[4]
        if player_name.startswith('admin'):
            continue
        player_total_money = player_money - (1000 * player_loan)
        avg_profit = 0 if player_hands == 0 else round((player_total_money - INIT_MONEY) / player_hands, 2) * 100
        daily_profit = daily_ranking.get(player_name, 0)
        ranking_data.append((player_name, player_total_money, avg_profit, daily_profit))
    
    # Sort by total money (descending)
    ranking_data = sorted(ranking_data, key=lambda x: x[1], reverse=True)

    return ranking_data



def delete_player_in_db(player_name):
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


def rename_player_in_db(old_name, new_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET username=? WHERE username=?", (new_name, old_name))
        conn.commit()
    except Exception as e:
        print(f"Error renaming player in database: {e}")
    finally:
        cursor.close()
        conn.close()


def change_email_in_db(old_email, new_email):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET email=? WHERE email=?", (new_email, old_email))
        conn.commit()
    except Exception as e:
        print(f"Error update email in database: {e}")
    finally:
        cursor.close()
        conn.close()


def query_player_msg_in_db(player_name, column_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT {column_name} FROM users WHERE username=?", (player_name,))
        result = cursor.fetchone()
        if result is not None:
            return result[0]
    except Exception as e:
        print(f"Error querying player data from database: {e}")
    finally:
        cursor.close()
        conn.close()


def update_player_msg_in_db(player_name, column_name, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"UPDATE users SET {column_name}=? WHERE username=?", (value, player_name))
        conn.commit()
    except Exception as e:
        print(f"Error updating player data in database: {e}")
    finally:
        cursor.close()
        conn.close()


def create_daily_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                start_money FLOAT DEFAULT ?,
                latest_money FLOAT DEFAULT ?,
                "date" DATE DEFAULT (date('now', 'localtime'))
            )
        """, (INIT_MONEY, INIT_MONEY))
        conn.commit()
    except Exception as e:
        print(f"Error creating table in database: {e}")
    finally:
        cursor.close()
        conn.close()


def update_daily_table(username, money):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE daily
            SET latest_money = ?
            WHERE username = ? AND "date" = date('now', 'localtime')
        """, (money, username))
        conn.commit()
    except Exception as e:
        print(f"Error updating daily table in database: {e}")
    finally:
        cursor.close()
        conn.close()


def insert_daily_table(username, start_money, latest_money):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO daily (username, start_money, latest_money, date)
            VALUES (?, ?, ?, date('now', 'localtime'))
        """, (username, start_money, latest_money))
        conn.commit()
    except Exception as e:
        print(f"Error inserting into daily table in database: {e}")
    finally:
        cursor.close()
        conn.close()


def is_player_active_today(username):
    # 查询daily表中是否有username为username的数据且date为今天的数据，如果有返回True，否则返回False
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM daily
            WHERE username = ? AND "date" = date('now', 'localtime')
        """, (username,))
        result = cursor.fetchone()
        if result is not None:
            return True
        else:
            return False
    except Exception as e:
        print(f"Error querying daily table in database: {e}")
    finally:
        cursor.close()
        conn.close()


def update_daily_ranking():
    # 查所有玩家现在的数据
    all_player_data = query_ranking_in_db()
    for player_data in all_player_data:
        player_name, player_money, player_loan, player_hands, player_id = player_data[0], player_data[1], player_data[
            2], \
            player_data[3], player_data[4]
        player_total_money = player_money - (1000 * player_loan)
        if is_player_active_today(player_name):
            update_daily_table(player_name, player_total_money)
        else:
            last_hand = query_latest_hand(player_name)  # 上一次玩的最后积分数，为空则代表是新玩家
            if not last_hand:
                # 新玩家，daily表里没有他的数据
                insert_daily_table(player_name, INIT_MONEY, player_total_money)
            elif player_total_money == last_hand:
                # 两种可能
                # 1.大榜上的玩家，但是今天没玩，不用记录
                # 2.今天玩了，但是这把弃牌了，先不记录，等有变化时候再记录
                continue
            else:
                # 钱有变化，但是今天还没有该玩家的数据，则插入今日数据
                insert_daily_table(player_name, last_hand, player_total_money)


def query_latest_hand(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT latest_money FROM daily
            WHERE username = ?
            ORDER BY date DESC
            LIMIT 1
        """, (username,))
        result = cursor.fetchone()
        if result is not None:
            return result[0]
        else:
            return None
    except Exception as e:
        print(f"Error querying hands table in database: {e}")
    finally:
        cursor.close()
        conn.close()


def get_daily_ranking():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT username, start_money, latest_money, "date" FROM daily
            WHERE date = date('now', 'localtime')
        """
        )
        result = cursor.fetchall()
        result = [list(row) for row in result]
        ranking_data = {}
        for row in result:
            player_name, start_money, latest_money = row[0], row[1], row[2]
            profit = latest_money - start_money
            ranking_data[player_name] = profit
        return ranking_data
    except Exception as e:
        print(f"Error querying daily table in database: {e}")
    finally:
        cursor.close()
        conn.close()


def reset_daily_table():
    # 清空daily表中所有数据
    conn = get_db_connection()
    cursor = conn.cursor()
    # 查询user表中所有username
    usernames = []
    try:
        cursor.execute("""
            SELECT username FROM users
        """
        )
        result = cursor.fetchall()
        for row in result:
            usernames.append(row[0])
        # 清空 daily 表中所有数据
        cursor.execute("DELETE FROM daily")
        insert_data = [(username, INIT_MONEY, INIT_MONEY, '2024-01-01') for username in usernames]
        cursor.executemany("""
            INSERT INTO daily (username, start_money, latest_money, date)
            VALUES (?, ?, ?, ?)
        """, insert_data)

        conn.commit()
        print("已成功重置 daily 表。")
    except Exception as e:
        print(f"Error deleting from daily table in database: {e}")
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    # 删除表
    # drop_tabel('daily')
    # 新建daily表
    # create_daily_table()
    # 重置数据库
    # reset_player_in_db()
    # reset_daily_table()
    # 查询当前所有数据
    query_all_data('users')
    print('=' * 50)
    query_all_data('daily')
    # 查询当前排名
    # res = query_ranking_in_db()
    # print(res)
    # 删除玩家
    # delete_player_in_db('admin4')
    # 重命名玩家
    # rename_player_in_db('赌神', 'Tom Dwan')
    # change_email_in_db('taozhen0109@163.com', 'taozhen')
    # 查询玩家数据
    # print(query_player_msg_in_db('你跟不跟吧', 'money'))
    # 更新玩家数据
    # update_player_msg_in_db('taozhen', 'money', 3000)
    # reset_daily_table()
