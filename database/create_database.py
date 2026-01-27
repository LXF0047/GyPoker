import sqlite3
from pathlib import Path

# 修正后的 DDL
DDL = """
PRAGMA foreign_keys = ON;

-- 1) 玩家基础信息
CREATE TABLE IF NOT EXISTS players (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  username        TEXT NOT NULL UNIQUE,
  password_hash   TEXT NOT NULL,
  nickname        TEXT,
  avatar          TEXT,
  created_at      INTEGER NOT NULL DEFAULT (unixepoch()), -- 存时间戳(Int)比String查询效率高
  last_login_at   INTEGER
);

-- 2) 筹码钱包
CREATE TABLE IF NOT EXISTS wallet (
  player_id       INTEGER PRIMARY KEY,
  chips           INTEGER NOT NULL DEFAULT 3000 CHECK (chips >= 0),
  last_reset_date TEXT NOT NULL DEFAULT (date('now')), 
  updated_at      INTEGER DEFAULT (unixepoch()),
  FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- 3) 牌桌
CREATE TABLE IF NOT EXISTS poker_tables (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT,
  max_seats       INTEGER NOT NULL DEFAULT 10,
  created_at      INTEGER DEFAULT (unixepoch())
);

-- 4) 牌局 (增加 Rake 和 Pot 记录)
CREATE TABLE IF NOT EXISTS hands (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  table_id        INTEGER,
  started_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  ended_at        INTEGER,

  small_blind     INTEGER NOT NULL,
  big_blind       INTEGER NOT NULL,

  total_pot       INTEGER DEFAULT 0, -- 总底池

  board_cards     TEXT, -- 建议存 JSON: ["Ah","Kd","Qs"]，比分开存灵活

  FOREIGN KEY(table_id) REFERENCES poker_tables(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_hands_time ON hands(started_at);

-- 5) 玩家对局详情
CREATE TABLE IF NOT EXISTS hand_players (
  hand_id         INTEGER NOT NULL,
  player_id       INTEGER NOT NULL,
  seat_no         INTEGER NOT NULL,

  starting_stack  INTEGER NOT NULL,
  ending_stack    INTEGER NOT NULL,
  net_chips       INTEGER GENERATED ALWAYS AS (ending_stack - starting_stack) VIRTUAL, -- SQLite 3.31+ 生成列，自动计算，非常方便！

  hole_cards      TEXT,
  position_name   TEXT, -- 'BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'UTG+2', 'UTG+3', 'MP', 'HJ', 'CO' 

  is_winner       BOOLEAN DEFAULT 0, -- 是否赢家

  PRIMARY KEY(hand_id, player_id),
  FOREIGN KEY(hand_id) REFERENCES hands(id) ON DELETE CASCADE,
  FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_hand_seat ON hand_players(hand_id, seat_no);

-- 6) 动作流
CREATE TABLE IF NOT EXISTS hand_actions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  hand_id         INTEGER NOT NULL,
  player_id       INTEGER NOT NULL,

  street          INTEGER NOT NULL, -- 0=Pre, 1=Flop, 2=Turn, 3=River
  action_num      INTEGER NOT NULL, -- 动作序号 1, 2, 3...
  action_type     TEXT NOT NULL,    -- 'bet', 'call'...
  amount          INTEGER DEFAULT 0,

  pot_before      INTEGER,

  FOREIGN KEY(hand_id) REFERENCES hands(id) ON DELETE CASCADE,
  UNIQUE(hand_id, action_num)
);

-- 7) 统计表
CREATE TABLE IF NOT EXISTS player_daily_stats (
  stat_date     TEXT NOT NULL,
  player_id     INTEGER NOT NULL,
  hands_played  INTEGER DEFAULT 0,
  net_chips     INTEGER DEFAULT 0,  -- 净胜筹码

  PRIMARY KEY(stat_date, player_id)
);

-- 8) 筹码流水表
CREATE TABLE IF NOT EXISTS chip_transactions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id   INTEGER NOT NULL,
  tx_time     TEXT NOT NULL DEFAULT (datetime('now')),
  tx_date     TEXT NOT NULL DEFAULT (date('now')), -- 方便按天统计
  tx_type     TEXT NOT NULL CHECK (tx_type IN ('daily_reset','auto_topup','admin_adjust')),
  amount      INTEGER NOT NULL,                    -- 正数表示发放/补充，负数表示扣除
  hand_id     INTEGER,                             -- 可选：关联发生在哪一手之后
  note        TEXT,
  FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
  FOREIGN KEY(hand_id) REFERENCES hands(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_chip_tx_player_date ON chip_transactions(player_id, tx_date);

-- 9) 玩家历史累计（个人页/总榜/画像）
CREATE TABLE IF NOT EXISTS player_lifetime_stats (
  player_id       INTEGER PRIMARY KEY,
  hands_played    INTEGER NOT NULL DEFAULT 0 CHECK (hands_played >= 0),
  net_chips       INTEGER NOT NULL DEFAULT 0,      -- 可为负
  net_bb          REAL    NOT NULL DEFAULT 0.0,    -- 可为负
  total_points    INTEGER NOT NULL DEFAULT 0 CHECK (total_points >= 0),

  -- 历史画像累计字段
  vpip_hands      INTEGER NOT NULL DEFAULT 0 CHECK (vpip_hands >= 0),
  pfr_hands       INTEGER NOT NULL DEFAULT 0 CHECK (pfr_hands >= 0),
  threebet_hands  INTEGER NOT NULL DEFAULT 0 CHECK (threebet_hands >= 0),
  agg_bets_raises INTEGER NOT NULL DEFAULT 0 CHECK (agg_bets_raises >= 0),
  agg_calls       INTEGER NOT NULL DEFAULT 0 CHECK (agg_calls >= 0),
  wtsd_hands      INTEGER NOT NULL DEFAULT 0 CHECK (wtsd_hands >= 0),
  wsd_hands       INTEGER NOT NULL DEFAULT 0 CHECK (wsd_hands >= 0),

  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- 10) api_keys表
CREATE TABLE IF NOT EXISTS api_keys (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  service_name    TEXT NOT NULL,
  api_key         TEXT NOT NULL,
  created_at      DATE
);

-- 触发器：创建账号时的初始化
CREATE TRIGGER IF NOT EXISTS trg_init_player
AFTER INSERT ON players
BEGIN
  INSERT INTO wallet(player_id, chips, last_reset_date)
  VALUES (NEW.id, 3000, date('now'));
END;
"""


# 初始化 DB
def init_db(db_path: str = "poker.sqlite3"):
    conn = sqlite3.connect(db_path)
    # 开启 WAL 模式，这对多人游戏至关重要，防止 database is locked 错误
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.executescript(DDL)
    conn.close()
    print("Database initialized successfully.")


if __name__ == "__main__":
    init_db()
