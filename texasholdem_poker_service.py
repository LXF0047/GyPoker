import logging
import redis
import os

from poker.game_server_redis import GameServerRedis
from poker.game_room import GameRoomFactory
from poker.poker_game_holdem import HoldemPokerGameFactory
from poker.database import start_daily_settlement_scheduler, create_total_scores_table

os.environ["REDIS_URL"] = "redis://localhost:6379/0"


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG if 'DEBUG' in os.environ else logging.INFO)
    logger = logging.getLogger()

    # 创建total_scores表（如果不存在）
    create_total_scores_table()
    
    # 启动每日结算定时任务
    start_daily_settlement_scheduler()

    redis_url = os.environ["REDIS_URL"]
    redis = redis.from_url(redis_url)

    server = GameServerRedis(
        redis=redis,
        connection_channel="texas-holdem-poker:lobby",
        room_factory=GameRoomFactory(
            room_size=10,
            game_factory=HoldemPokerGameFactory(
                big_blind=10.0,
                small_blind=5.0,
                logger=logger,
                game_subscribers=[]
            )
        ),
        logger=logger
    )
    server.start()
