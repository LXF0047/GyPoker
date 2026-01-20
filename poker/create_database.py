import sqlite3
from pathlib import Path

# 数据库文件路径
DB_PATH = Path("/Users/f/Downloads/user.db")

# 建表语句
SCHEMA = """
-- NOTE: `sqlite_sequence` is an internal SQLite table used for AUTOINCREMENT.
-- Do NOT create it manually; SQLite will create it automatically when needed.

CREATE TABLE IF NOT EXISTS users
(
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    email    TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT        NOT NULL,
    money    INTEGER DEFAULT 3000,
    loan INTEGER DEFAULT 0,
    hands integer default 0,
    avatar TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    start_money FLOAT DEFAULT 3000,
    latest_money FLOAT,
    date DATE DEFAULT (date('now'))
);
"""

def create_database(db_path: Path, schema_sql: str):
    if db_path.exists():
        print(f"[提示] 数据库文件已存在: {db_path}")
        confirm = input("是否覆盖？(y/N): ").strip().lower()
        if confirm != "y":
            print("已取消创建。")
            return
        db_path.unlink()  # 删除旧文件

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 执行建表
    cursor.executescript(schema_sql)
    conn.commit()
    conn.close()

    print(f"[完成] 数据库已创建: {db_path}")

if __name__ == "__main__":
    create_database(DB_PATH, SCHEMA)