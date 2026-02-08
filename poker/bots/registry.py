import random
from typing import Dict, List, Tuple

from ..card import Card
from ..score_detector import HoldemPokerScoreDetector, HoldemPokerScore
from .remote_engine import RemoteDecisionEngine

from .decision import BotDecisionContext, BotDecisionEngine


class TableDrivenEasyEngine(BotDecisionEngine):
    """
    基于查表的简单机器人引擎。
    根据手牌强度（Premium, Strong, Speculative）在翻牌前做决定。
    翻牌后根据牌型大小做决定。
    """
    RANK_TO_CHAR = {
        14: "A",
        13: "K",
        12: "Q",
        11: "J",
        10: "T",
        9: "9",
        8: "8",
        7: "7",
        6: "6",
        5: "5",
        4: "4",
        3: "3",
        2: "2",
    }

    # 顶级手牌
    PREMIUM = {
        "AA", "KK", "QQ", "JJ", "TT",
        "AKs", "AKo", "AQs", "AQo", "KQs",
    }
    # 强手牌
    STRONG = {
        "99", "88", "77",
        "AJs", "ATs", "KJs", "QJs", "JTs", "KQo", "AJo",
        "KTs", "QTs", "T9s", "98s",
    }
    # 投机手牌
    SPECULATIVE = {
        "66", "55", "44", "33", "22",
        "A9s", "A8s", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s",
        "87s", "76s", "65s", "54s",
    }

    def decide(self, context: BotDecisionContext) -> int:
        if context.street == 0:
            return self._preflop_decide(context)
        return self._postflop_decide(context)

    def _preflop_decide(self, context: BotDecisionContext) -> int:
        """翻牌前决策逻辑"""
        hand_key = self._hand_key(context.hand)
        if not hand_key:
            return 0 if context.min_bet == 0 else -1

        if hand_key in self.PREMIUM:
            return self._raise(context, 0.9)
        if hand_key in self.STRONG:
            if context.min_bet == 0:
                return self._bet(context, 0.6)
            return self._call_or_fold(context, 0.5)
        if hand_key in self.SPECULATIVE:
            return self._call_or_fold(context, 0.25)

        return 0 if context.min_bet == 0 else -1

    def _postflop_decide(self, context: BotDecisionContext) -> int:
        """翻牌后决策逻辑"""
        score = self._score_hand(context.hand, context.board)
        if not score:
            return 0 if context.min_bet == 0 else -1

        # 两对及以上
        if score.category >= HoldemPokerScore.TWO_PAIR:
            if context.min_bet == 0:
                return self._bet(context, 0.6)
            return self._raise(context, 0.8)
        # 一对
        if score.category == HoldemPokerScore.PAIR:
            return self._call_or_fold(context, 0.4)

        return 0 if context.min_bet == 0 else -1

    def _hand_key(self, hand: List[Tuple[int, int]]) -> str:
        """生成手牌的字符串表示，例如 'AKs', '99'"""
        if not hand or len(hand) < 2:
            return ""
        (r1, s1), (r2, s2) = hand[0], hand[1]
        suited = s1 == s2
        if r1 == r2:
            return f"{self.RANK_TO_CHAR.get(r1, '')}{self.RANK_TO_CHAR.get(r2, '')}"
        high, low = (r1, r2) if r1 > r2 else (r2, r1)
        return f"{self.RANK_TO_CHAR.get(high, '')}{self.RANK_TO_CHAR.get(low, '')}{'s' if suited else 'o'}"

    def _score_hand(self, hand: List[Tuple[int, int]], board: List[Tuple[int, int]]):
        """计算当前手牌和公共牌组成的最佳牌型"""
        if not hand:
            return None
        cards = [Card(rank, suit) for rank, suit in (hand + board)]
        detector = HoldemPokerScoreDetector()
        try:
            return detector.get_score(cards)
        except Exception:
            return None

    def _call_or_fold(self, context: BotDecisionContext, max_ratio: float) -> int:
        """决定跟注还是弃牌，取决于下注额相对于底池的比例"""
        if context.min_bet == 0:
            return 0
        pot = max(context.pot_total, 1)
        if context.min_bet <= pot * max_ratio:
            return context.min_bet
        return -1

    def _bet(self, context: BotDecisionContext, fraction: float) -> int:
        """下注底池的一定比例"""
        pot = max(context.pot_total, 1)
        size = int(pot * fraction)
        if size < 1:
            size = 1
        return self._clamp_bet(context, size)

    def _raise(self, context: BotDecisionContext, fraction: float) -> int:
        """加注底池的一定比例"""
        pot = max(context.pot_total, 1)
        size = int(pot * fraction)
        if context.min_bet > 0:
            size = max(size, int(context.min_bet * 2))
        if size < 1:
            size = 1
        return self._clamp_bet(context, size)

    def _clamp_bet(self, context: BotDecisionContext, size: int) -> int:
        """确保下注金额在合法范围内（最小下注额和最大下注额之间）"""
        if size < context.min_bet:
            size = context.min_bet
        if size > context.max_bet:
            size = context.max_bet
        return int(size)


BOT_ENGINE_REGISTRY: Dict[str, BotDecisionEngine] = {
    "easy": TableDrivenEasyEngine(),
    "medium": RemoteDecisionEngine("medium"),
    "hard": RemoteDecisionEngine("hard"),
}


def get_engine_for_difficulty(difficulty: str) -> BotDecisionEngine:
    """根据难度级别获取对应的机器人引擎"""
    if not difficulty:
        return BOT_ENGINE_REGISTRY["easy"]
    if difficulty == "normal":
        difficulty = "medium"
    return BOT_ENGINE_REGISTRY.get(difficulty, BOT_ENGINE_REGISTRY["easy"])
