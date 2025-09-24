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
    """
    获取新的排行榜数据
    返回格式: (排名, 玩家姓名, 总积分, bb/100 hands, 当日总积分, 当日净胜分)
    按当日净胜分排序
    """
    # 获取当日活跃玩家及其净胜分
    daily_ranking = get_daily_ranking()
    if not daily_ranking:
        return []

    # 获取总积分数据
    total_scores_data = get_all_total_scores()
    total_scores_dict = {row[0]: {'total_score': row[1], 'game_count': row[2]} for row in total_scores_data}

    ranking_data = []
    BIG_BLIND = 10  # 大盲值
    
    for player_name, daily_profit in daily_ranking.items():
        if player_name.startswith('admin'):
            continue
            
        # 总积分
        total_score = total_scores_dict.get(player_name, {}).get('total_score', 0)
        game_count = total_scores_dict.get(player_name, {}).get('game_count', 0)
        
        # bb/100 hands计算: 总积分 / 大盲值 / 游戏次数 * 100
        bb_per_100 = 0
        if game_count > 0:
            bb_per_100 = round((total_score / BIG_BLIND / game_count) * 100, 2)
        
        # 当日总积分 = 初始金额 + 当日净胜分
        daily_total = INIT_MONEY + daily_profit
        
        ranking_data.append((player_name, total_score, bb_per_100, daily_total, daily_profit))
    
    # 按当日净胜分降序排序
    ranking_data = sorted(ranking_data, key=lambda x: x[4], reverse=True)
    
    # 添加排名
    final_ranking = []
    for i, data in enumerate(ranking_data, 1):
        final_ranking.append((i, data[0], data[1], data[2], data[3], data[4]))
    
    return final_ranking



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


def create_total_scores_table():
    """创建总积分历史记录表，支持多种游戏类型"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS total_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                game_type INTEGER DEFAULT 1,
                total_score FLOAT DEFAULT 0,
                game_count INTEGER DEFAULT 0,
                created_date DATE DEFAULT (date('now', 'localtime')),
                updated_date DATE DEFAULT (date('now', 'localtime')),
                UNIQUE(username, game_type)
            )
        """)
        conn.commit()
    except Exception as e:
        print(f"Error creating total_scores table: {e}")
    finally:
        cursor.close()
        conn.close()


def update_total_score_daily(username, daily_profit, game_type=1):
    """每日结算时更新玩家总积分（不增加游戏局数）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 检查是否已存在该玩家的记录
        cursor.execute("""
            SELECT total_score FROM total_scores 
            WHERE username = ? AND game_type = ?
        """, (username, game_type))
        result = cursor.fetchone()
        
        if result:
            # 更新现有记录，只更新总积分，不增加游戏局数
            new_total = result[0] + daily_profit
            cursor.execute("""
                UPDATE total_scores 
                SET total_score = ?, updated_date = date('now', 'localtime')
                WHERE username = ? AND game_type = ?
            """, (new_total, username, game_type))
        else:
            # 插入新记录
            cursor.execute("""
                INSERT INTO total_scores (username, game_type, total_score, game_count)
                VALUES (?, ?, ?, 0)
            """, (username, game_type, daily_profit))
        
        conn.commit()
    except Exception as e:
        print(f"Error updating total score daily: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def update_game_count(username, game_type=1):
    """每局游戏结束后增加游戏局数"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 检查是否已存在该玩家的记录
        cursor.execute("""
            SELECT game_count FROM total_scores 
            WHERE username = ? AND game_type = ?
        """, (username, game_type))
        result = cursor.fetchone()
        
        if result:
            # 更新现有记录的游戏局数
            cursor.execute("""
                UPDATE total_scores 
                SET game_count = game_count + 1, updated_date = date('now', 'localtime')
                WHERE username = ? AND game_type = ?
            """, (username, game_type))
        else:
            # 插入新记录，游戏局数为1
            cursor.execute("""
                INSERT INTO total_scores (username, game_type, total_score, game_count)
                VALUES (?, ?, 0, 1)
            """, (username, game_type))
        
        conn.commit()
    except Exception as e:
        print(f"Error updating game count: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def get_total_score(username, game_type=1):
    """获取玩家总积分"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT total_score FROM total_scores 
            WHERE username = ? AND game_type = ?
        """, (username, game_type))
        result = cursor.fetchone()
        return result[0] if result else 0
    except Exception as e:
        print(f"Error getting total score: {e}")
        return 0
    finally:
        cursor.close()
        conn.close()


def get_all_total_scores(game_type=1):
    """获取所有玩家的总积分数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT username, total_score, game_count FROM total_scores 
            WHERE game_type = ?
            ORDER BY total_score DESC
        """, (game_type,))
        return cursor.fetchall()
    except Exception as e:
        print(f"Error getting all total scores: {e}")
        return []
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
        player_total_money = player_money - (INIT_MONEY * player_loan)
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
        # 重置自增序列
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='daily'")
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


def daily_settlement_task():
    """凌晨1点执行的每日结算任务"""
    try:
        print("开始执行每日结算任务...")
        
        # 获取当日所有玩家的净胜分
        daily_ranking = get_daily_ranking()
        
        # 将当日净胜分累加到总积分
        for username, daily_profit in daily_ranking.items():
            if not username.startswith('admin'):
                update_total_score_daily(username, daily_profit)
                print(f"更新玩家 {username} 总积分，当日净胜分: {daily_profit}")
        
        # 重置daily表（清空所有当日数据）
        reset_daily_table_for_new_day()
        
        print("每日结算任务完成！")
        
    except Exception as e:
        print(f"每日结算任务执行失败: {e}")


def reset_daily_table_for_new_day():
    """重置daily表为新的一天"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 删除所有昨天的数据
        cursor.execute("DELETE FROM daily")
        
        # 重置自增序列
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='daily'")
        
        conn.commit()
        print("daily表已重置为新的一天")
        
    except Exception as e:
        print(f"重置daily表失败: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def start_daily_settlement_scheduler():
    """启动每日结算的定时调度器"""
    import threading
    import time
    from datetime import datetime, time as dt_time
    
    def run_scheduler():
        while True:
            now = datetime.now()
            # 设置目标时间为凌晨1点
            target_time = dt_time(1, 0, 0)  # 01:00:00
            
            # 计算到下一个凌晨1点的秒数
            if now.time() < target_time:
                # 今天的凌晨1点还没到
                target_datetime = now.replace(hour=1, minute=0, second=0, microsecond=0)
            else:
                # 今天的凌晨1点已过，等待明天的凌晨1点
                from datetime import timedelta
                target_datetime = (now + timedelta(days=1)).replace(hour=1, minute=0, second=0, microsecond=0)
            
            # 计算等待时间
            wait_seconds = (target_datetime - now).total_seconds()
            print(f"下次每日结算时间: {target_datetime}, 等待 {wait_seconds/3600:.1f} 小时")
            
            # 等待到指定时间
            time.sleep(wait_seconds)
            
            # 执行每日结算任务
            daily_settlement_task()
    
    # 在后台线程中运行调度器
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    print("每日结算调度器已启动")


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
