import os
from typing import Optional, Tuple, List, Any

import requests

from .decision import BotDecisionContext, BotDecisionEngine
from ..db_utils.system_utils import get_api_key


class RemoteDecisionEngine(BotDecisionEngine):
    """
    Calls an external bot service via HTTP for decisions.

    Env vars:
    - BOT_DECISION_URL: base URL, e.g. http://127.0.0.1:8081
    - BOT_DECISION_TOKEN: optional bearer token
    - BOT_DECISION_TIMEOUT: seconds (float). Applies to connect/read.
    """

    SUIT_TO_CHAR = {
        0: "S",  # ♠
        3: "H",  # ♥
        2: "D",  # ♦
        1: "C",  # ♣
    }

    RANK_TO_CHAR = {
        2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7",
        8: "8", 9: "9", 10: "T", 11: "J", 12: "Q", 13: "K", 14: "A",
    }

    def __init__(self, difficulty: str):
        self._difficulty = difficulty
        
        # Try to get URL from database first
        db_url = get_api_key("solver")
        if db_url:
            db_url = db_url.rstrip("/")
        
        # Default to local service if env var not set and not in DB
        self._base_url = db_url or os.environ.get("BOT_DECISION_URL", "http://127.0.0.1:8000").rstrip("/")
        self._token = os.environ.get("BOT_DECISION_TOKEN", "")
        timeout_s = os.environ.get("BOT_DECISION_TIMEOUT", "1.2")
        try:
            self._timeout = float(timeout_s)
        except Exception:
            self._timeout = 1.2

    def decide(self, context: BotDecisionContext) -> int:
        if not self._base_url:
            return self._fallback(context)
        
        url = f"{self._base_url}/act"
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        context_dict = context.to_dict()
        
        # Convert cards to backend format
        if "hand" in context_dict:
            context_dict["hand"] = [self._to_backend_card(c) for c in context_dict["hand"]]
        if "board" in context_dict:
            context_dict["board"] = [self._to_backend_card(c) for c in context_dict["board"]]

        payload = {
            "difficulty": self._difficulty,
            "context": context_dict,
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=(self._timeout, self._timeout))
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
        except Exception:
            return self._fallback(context)

        bet = data.get("bet")
        if bet is None:
            return self._fallback(context)
        try:
            return int(round(float(bet)))
        except Exception:
            return self._fallback(context)

    def _to_backend_card(self, card: Any) -> str:
        # card: [rank, suit] or (rank, suit)
        try:
            rank, suit = card
            return f"{self.SUIT_TO_CHAR.get(suit, '?')}{self.RANK_TO_CHAR.get(rank, '?')}"
        except Exception:
            return "??"

    def _fallback(self, context: BotDecisionContext) -> int:
        try:
            # Avoid circular import
            from .registry import BOT_ENGINE_REGISTRY
            easy_engine = BOT_ENGINE_REGISTRY.get("easy")
            # Prevent infinite recursion if "easy" is also RemoteDecisionEngine (though it shouldn't be)
            if easy_engine and not isinstance(easy_engine, RemoteDecisionEngine):
                return easy_engine.decide(context)
        except ImportError:
            pass

        # Safe-ish fallback: check if free; otherwise call small, fold big.
        if context.min_bet == 0:
            return 0
        pot = max(context.pot_total, 1)
        if context.min_bet <= int(pot * 0.2):
            return context.min_bet
        return -1
