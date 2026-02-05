from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class BotDecisionContext:
    room_id: str
    game_id: str
    street: int
    player_id: int
    player_name: str
    seat: int
    hand: List[Dict[str, Any]]
    board: List[Dict[str, Any]]
    players: List[Dict[str, Any]]
    pot_total: int
    street_bets: Dict[int, int]
    min_bet: int
    max_bet: int
    to_call: int
    action_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "room_id": self.room_id,
            "game_id": self.game_id,
            "street": self.street,
            "player_id": self.player_id,
            "player_name": self.player_name,
            "seat": self.seat,
            "hand": self.hand,
            "board": self.board,
            "players": self.players,
            "pot_total": self.pot_total,
            "street_bets": self.street_bets,
            "min_bet": self.min_bet,
            "max_bet": self.max_bet,
            "to_call": self.to_call,
            "action_history": self.action_history,
        }


class BotDecisionEngine:
    """
    Bot decision engine interface.
    Implementations should return a bet amount:
    -1 = fold, 0 = check, min_bet = call, > min_bet = raise (clamped by game)
    """
    def decide(self, context: BotDecisionContext) -> int:
        raise NotImplementedError
