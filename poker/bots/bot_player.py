from typing import Optional

from .bot_channel import BotChannel
from .registry import get_engine_for_difficulty
from ..player_server import PlayerServer


class BotPlayerServer(PlayerServer):
    def __init__(self, logger, id: int, name: str, money: float, difficulty: str, avatar: Optional[str] = None):
        engine = get_engine_for_difficulty(difficulty)
        super().__init__(
            channel=BotChannel(),
            logger=logger,
            id=id,
            name=name,
            money=money,
            avatar=avatar,
            ready=True,
            is_bot=True,
            bot_difficulty=difficulty
        )
        self.bot_engine = engine

    def ping(self) -> bool:
        return True

    def try_send_message(self, message):
        return True
