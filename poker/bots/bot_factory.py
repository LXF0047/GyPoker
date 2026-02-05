import random
from typing import Optional, Sequence

from ..db_utils import get_players_by_nickname_prefix
from .bot_player import BotPlayerServer


def create_bot_player(logger, difficulty: str, exclude_ids: Sequence[int] = None, exclude_names: Sequence[str] = None) -> Optional[BotPlayerServer]:
    difficulty = difficulty or "easy"
    if difficulty == "normal":
        difficulty = "medium"
    prefix = f"{difficulty}_bot_"
    exclude_ids = set(int(pid) for pid in (exclude_ids or []))
    exclude_names = set(str(name) for name in (exclude_names or []))

    candidates = [
        p for p in get_players_by_nickname_prefix(prefix)
        if int(p["id"]) not in exclude_ids
        and str(p.get("nickname") or p.get("username") or "") not in exclude_names
    ]
    if not candidates:
        return None

    player_data = random.choice(candidates)

    player_id = int(player_data["id"])
    nickname = player_data.get("nickname") or player_data.get("username")
    money = float(player_data.get("chips") or 0)
    avatar = player_data.get("avatar")

    return BotPlayerServer(
        logger=logger,
        id=player_id,
        name=nickname,
        money=money,
        difficulty=difficulty,
        avatar=avatar
    )
