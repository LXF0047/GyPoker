import os
from typing import Optional, Tuple

import requests

from .decision import BotDecisionContext, BotDecisionEngine


class RemoteDecisionEngine(BotDecisionEngine):
    """
    Calls an external bot service via HTTP for decisions.

    Env vars:
    - BOT_DECISION_URL: base URL, e.g. http://127.0.0.1:8081
    - BOT_DECISION_TOKEN: optional bearer token
    - BOT_DECISION_TIMEOUT: seconds (float). Applies to connect/read.
    """

    def __init__(self, difficulty: str):
        self._difficulty = difficulty
        self._base_url = os.environ.get("BOT_DECISION_URL", "").rstrip("/")
        self._token = os.environ.get("BOT_DECISION_TOKEN", "")
        timeout_s = os.environ.get("BOT_DECISION_TIMEOUT", "1.2")
        try:
            self._timeout = float(timeout_s)
        except Exception:
            self._timeout = 1.2

    def decide(self, context: BotDecisionContext) -> int:
        if not self._base_url:
            return self._fallback(context)

        url = f"{self._base_url}/decide"
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        payload = {
            "difficulty": self._difficulty,
            "context": context.to_dict(),
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

    def _fallback(self, context: BotDecisionContext) -> int:
        # Safe-ish fallback: check if free; otherwise call small, fold big.
        if context.min_bet == 0:
            return 0
        pot = max(context.pot_total, 1)
        if context.min_bet <= int(pot * 0.2):
            return context.min_bet
        return -1
