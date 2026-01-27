import uuid
import json
from typing import Optional, List

import gevent

from .deck import DeckFactory
from .player import Player
from .poker_game import PokerGame, GameFactory, GameError, EndGameException, GamePlayers, \
    GameEventDispatcher, GameSubscriber, GameBetHandler, GameBetRounder
from .score_detector import HoldemPokerScoreDetector
from .db_utils import get_or_create_table, create_hand, add_hand_player, update_hand_player_result, \
    add_hand_action, finish_hand, update_daily_stats, update_player_wallet, auto_topup_chips, get_daily_ranking_list, \
    update_lifetime_stats
from .config import INIT_MONEY, TIMEOUT_TOLERANCE, BET_TIMEOUT, WAIT_AFTER_FLOP_TURN_RIVER
import logging


class HoldemPokerGameFactory(GameFactory):
    def __init__(self, big_blind: float, small_blind: float, logger,
                 game_subscribers: Optional[List[GameSubscriber]] = None):
        self._big_blind: float = big_blind
        self._small_blind: float = small_blind
        self._logger = logger
        self._game_subscribers: List[GameSubscriber] = [] if game_subscribers is None else game_subscribers

    def create_game(self, players: List[Player], room_id: str = None):
        game_id = str(uuid.uuid4())

        event_dispatcher = HoldemPokerGameEventDispatcher(game_id=game_id, logger=self._logger)
        # 游戏管理器中添加订阅者
        for subscriber in self._game_subscribers:
            event_dispatcher.subscribe(subscriber)

        return HoldemPokerGame(
            self._big_blind,
            self._small_blind,
            id=game_id,
            game_players=GamePlayers(players),
            event_dispatcher=event_dispatcher,
            deck_factory=DeckFactory(2),  # 指定2为最小牌面
            score_detector=HoldemPokerScoreDetector(),
            room_id=room_id
        )


class HoldemPokerGameEventDispatcher(GameEventDispatcher):
    """
    游戏事件管理中新增三种事件
    1.新游戏
    2.游戏结束
    3.发公共牌
    """

    def new_game_event(self, game_id, players, dealer_id, big_blind, small_blind):
        self.raise_event(
            "new-game",
            {
                "game_id": game_id,
                "game_type": "texas-holdem",
                "players": [player.dto() for player in players],
                "dealer_id": dealer_id,
                "big_blind": big_blind,
                "small_blind": small_blind
            }
        )

    def game_over_event(self):
        self.raise_event(
            "game-over",
            {}
        )

    def shared_cards_event(self, cards):
        """
        发公共牌
        """
        self.raise_event(
            "shared-cards",
            {
                "cards": [card.dto() for card in cards]  # [('J', '♠'), ...]
            }
        )

    def update_ranking_event(self, ranking_list):
        """
        更新排行榜
        """
        self.raise_event(
            "update-ranking-data",
            {
                "ranking_list": ranking_list
            }
        )


class HoldemPokerGame(PokerGame):
    def __init__(self, big_blind, small_blind, *args, **kwargs):
        PokerGame.__init__(self, *args, **kwargs)
        self._big_blind = big_blind
        self._small_blind = small_blind
        self._logger = logging.getLogger()

        self._db_hand_id = None  # 数据库中的牌局ID
        self._db_table_id = None  # 数据库中的桌子ID
        self._street = 0  # 当前圈数 (0: Pre-flop, 1: Flop, 2: Turn, 3: River)
        self._action_num = 0  # 当前局的动作序号
        self._pots = []  # 当前局的底池列表
        self._hand_stats = {}  # 玩家本局统计数据
        self._preflop_raise_count = 0  # 翻前加注次数，用于计算3-bet

    def __check_no_money_players(self):
        # 没钱的自动贷款
        for player in self._game_players.all:
            if player.money < self._big_blind:
                amount = INIT_MONEY
                # 更新数据库并记录交易
                if auto_topup_chips(player.id, amount, self._db_hand_id):
                    player.add_money(amount)
                    self._logger.info(f"为玩家 {player.name} (ID: {player.id}) 自动追加{amount}筹码")
                else:
                    self._logger.error(f"玩家{player.name} (ID: {player.id})自动追加筹码失败")

    def _save_player_data(self):
        # 一手牌结束时保存数据
        for player in self._game_players.all:
            # Daily stats are now updated in _finish_db_hand
            update_player_wallet(player.id, player.money)

    def update_daily_ranking_list(self):
        # 更新每日榜单，根据当日参与玩家的净胜分由高到低排名
        daily_ranking_data = get_daily_ranking_list()
        self._event_dispatcher.update_ranking_event(daily_ranking_data)

    def _reset_ready_state(self):
        for player in self._game_players.all:
            player._ready = False

    def _showdown(self, scores):
        """
        执行摊牌流程，记录进入摊牌的玩家。
        """
        for player in self._game_players.active:
            if player.id in self._hand_stats:
                self._hand_stats[player.id]['wtsd'] = 1
        super()._showdown(scores)

    def _add_shared_cards(self, new_shared_cards, scores):
        """
        添加公共牌并广播事件。
        """
        self._event_dispatcher.shared_cards_event(new_shared_cards)
        # Adds the new shared cards
        scores.add_shared_cards(new_shared_cards)

    def _init_db_record(self, dealer_id):
        """
        在每一手牌开始时，在数据库里创建这手牌的记录，并把参与玩家入局时的初始信息写进去。相当于开局建档
        但是没有添加手牌数据
        """
        if not self._room_id:
            return

        self._db_table_id = get_or_create_table(str(self._room_id))
        if not self._db_table_id:
            return

        self._db_hand_id = create_hand(self._db_table_id, self._small_blind, self._big_blind)

        # 计算玩家位置
        active_players = list(self._game_players.round(dealer_id))
        position_map = {}  # {'玩家id': '位置'}
        count = len(active_players)

        if count == 2:
            position_map[active_players[0].id] = "SB"
            position_map[active_players[1].id] = "BB"
        elif count >= 3:
            position_map[active_players[0].id] = "SB"
            position_map[active_players[1].id] = "BB"
            position_map[active_players[-1].id] = "BTN"
            for i in range(2, count - 1):
                pid = active_players[i].id
                if i == count - 2:
                    position_map[pid] = "CO"
                elif i == 2:
                    position_map[pid] = "UTG"
                else:
                    position_map[pid] = "MP"

        # Record players
        for player in self._game_players.all:
            seat = getattr(player, 'seat', 0)
            if seat is None: 
                seat = 0

            position = position_map.get(player.id, "UNK")

            # 这里没有添加手牌信息，因为Player中没有保存这部分数据
            add_hand_player(
                self._db_hand_id,
                player.id,
                seat,
                player.money,
                position_name=position
            )

    def _create_bet_handler(self):
        """
        Explicitly create bet handler with action callback to ensure recording
        """
        return GameBetHandler(
            game_players=self._game_players,
            bet_rounder=GameBetRounder(self._game_players),
            event_dispatcher=self._event_dispatcher,
            bet_timeout=BET_TIMEOUT,
            timeout_tolerance=TIMEOUT_TOLERANCE,
            wait_after_round=self.WAIT_AFTER_BET_ROUND,
            on_action_callback=self._on_player_action
        )

    def _on_player_action(self, player, bet, min_bet, max_bet, bets, forced_action_type: str = None):
        """记录玩家行动到数据库。

        参数说明：
        - bet: 本次行动投入的筹码（fold 时为 -1）
        - min_bet: 当前需要跟注的最低额（0 表示无人下注，可 check/bet）
        - max_bet: 本次行动可投入的最大额（通常为玩家可用筹码），用于识别 all-in
        - bets: 本轮下注字典（包含各玩家在本轮/本街的下注累计，具体由 bet_handler 维护）
        - forced_action_type: 强制记录的动作类型（例如盲注 'blind'）
        """
        if not self._db_hand_id:
            return

        self._action_num += 1

        # ---- 1) 计算动作类型 ----
        if forced_action_type:
            action_type = forced_action_type
        else:
            # bet == -1 弃牌
            if bet == -1:
                action_type = "fold"
            else:
                # 无人下注：check / bet
                if min_bet == 0:
                    action_type = "check" if bet == 0 else "bet"
                else:
                    # 有下注：call / raise
                    action_type = "call" if bet == min_bet else "raise"

                # all-in 识别：优先用 max_bet（bet_handler 通常会传入玩家可用最大额）
                # 注意：盲注/特殊调用可通过 forced_action_type 绕开该判断
                if max_bet and bet == max_bet and bet > 0:
                    action_type = "all-in"

        # ---- 2) 计算 pot_before ----
        # pot_before = 之前的底池 + 当前圈所有下注累计 - 玩家本次下注（因为bets里包含本次下注后的累计）
        try:
            pot_from_pots = sum(getattr(p, 'money', 0) for p in self._pots)
        except Exception:
            pot_from_pots = 0

        try:
            bet_sum = sum(bets.values()) if bets else 0
        except Exception:
            bet_sum = 0

        pot_before = pot_from_pots + bet_sum
        if bet != -1:
            pot_before -= bet
        if pot_before < 0:
            pot_before = 0

        # ---- 3) 写入数据库（DB 里 amount/pot_before 期望为整数） ----
        amount = 0 if bet == -1 else bet
        try:
            amount = int(amount)
        except Exception:
            amount = int(round(amount))

        try:
            pot_before_i = int(pot_before)
        except Exception:
            pot_before_i = int(round(pot_before))

        if not add_hand_action(
            self._db_hand_id,
            player.id,
            self._street,
            self._action_num,
            action_type,
            amount,
            pot_before_i
        ):
            self._logger.error(f"Failed to record action for player {player.id}")

        # ---- 4) 统计生涯数据指标 ----
        if player.id in self._hand_stats:
            stats = self._hand_stats[player.id]

            # VPIP: 翻前主动入池 (不含大盲 Check/Fold)
            if self._street == 0:
                if action_type in ["call", "bet", "raise", "all-in"]:
                    # 盲注本身的 forced 动作不算 VPIP，除非是大盲位加注或小盲位补齐/加注
                    if forced_action_type != "blind":
                        stats['vpip'] = 1
                    elif action_type in ["raise", "all-in"]:
                        stats['vpip'] = 1
                    elif action_type == "call" and amount > 0:
                        # 比如小盲补齐，amount 会是 small_blind
                        stats['vpip'] = 1

            # PFR: 翻前加注
            if self._street == 0:
                if action_type in ["raise", "all-in"]:
                    # 只有当它是真正的加注时（比当前需要跟的 min_bet 多）
                    if bet > min_bet:
                        stats['pfr'] = 1
                        # 3-bet 追踪
                        self._preflop_raise_count += 1
                        if self._preflop_raise_count == 2:  # 第一次是 Open，第二次是 3-bet
                            stats['threebet'] = 1

            # 激进度统计 (Aggression Factor 相关)
            if action_type in ["bet", "raise", "all-in"]:
                # 如果是 all-in，根据是否大于 min_bet 判定是加注还是跟注
                if action_type == "all-in":
                    if bet > min_bet:
                        stats['agg_bets'] += 1
                    elif bet == min_bet and bet > 0:
                        stats['agg_calls'] += 1
                else:
                    stats['agg_bets'] += 1
            elif action_type == "call":
                stats['agg_calls'] += 1

    def _finish_db_hand(self, pots, scores):
        """
        一手牌结束时更新数据库
        """
        if not self._db_hand_id:
            return

        # 总底池
        total_pot = sum(pot.money for pot in pots) if pots else 0

        # 公共牌
        board_cards_str = json.dumps([c.dto() for c in scores.shared_cards])

        # 更新hands表中的公共牌与总奖池，大小盲在init时已经记录
        finish_hand(self._db_hand_id, board_cards_str, total_pot)

        # Update player results
        # Winners are detected in _detect_winners but here we can check who won from pots or just record final stacks
        # Since _finish_db_hand is called BEFORE _detect_winners finishes money distribution,
        # we might need to call this AFTER money distribution?
        # Actually _detect_winners modifies player.money.
        # So we should call this AFTER _detect_winners.
        # But _detect_winners is called in exception block.

        # Let's see: _detect_winners iterates pots and adds money to winners.
        # So if we call _finish_db_hand AFTER _detect_winners, player.money will be final.
        pass  # Moved logic to play_hand end

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Blinds
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _collect_blinds(self, dealer_id):
        # 检查房间人数
        if self._game_players.count_active() < 2:
            raise GameError("Not enough players")

        # 还在的玩家列表
        active_players = list(self._game_players.round(dealer_id))

        # 下注记录
        bets = {}

        # 小盲位玩家行动
        sb_player = active_players[0]
        sb_player.take_money(self._small_blind)
        bets[sb_player.id] = self._small_blind

        self._event_dispatcher.bet_event(
            player=sb_player,
            bet=self._small_blind,
            bet_type="blind",
            bets=bets
        )
        # 记录小盲位行动
        self._on_player_action(sb_player, self._small_blind, 0, 0, bets, forced_action_type="blind")

        # 大盲位玩家行动
        bb_player = active_players[1]
        bb_player.take_money(self._big_blind)
        bets[bb_player.id] = self._big_blind

        self._event_dispatcher.bet_event(
            player=bb_player,
            bet=self._big_blind,
            bet_type="blind",
            bets=bets
        )

        self._on_player_action(bb_player, self._big_blind, 0, 0, bets, forced_action_type="blind")

        return bets

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Game logic
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def save_player_data(self):
        """
        一手牌结束时保存游戏数据，包括玩家数据、游戏状态等。
        """
        self.__check_no_money_players()  # 检查是否有玩家没钱了
        self._save_player_data()  # 保存用户数据

    def play_hand(self, dealer_id):
        """
        举例：
        玩家列表[a, b, c, d, e]
        dealer_id是b
        """

        def bet_rounder(dealer_id, pots, scores, blind_bets):
            # 一局中的下一轮判断，从翻前到河牌翻完下完注为一局
            next_bet_round = True
            bets = blind_bets

            while True:
                if next_bet_round:
                    # Bet round
                    is_blind_bet_round = True if bets else False
                    self._bet_handler.bet_round(dealer_id, bets, pots, is_blind_bet_round)

                    # Only the pre-flop bet has blind bets
                    bets = {}

                    # Not fun to play alone
                    if self._game_players.count_active() < 2:
                        raise EndGameException

                    # If everyone is all-in (possibly except 1 player) then showdown and skip next bet rounds
                    next_bet_round = self._game_players.count_active_with_money() > 1

                    # There won't be a next bet round: showdown
                    if not next_bet_round:
                        self._showdown(scores)

                yield next_bet_round

        # Initialization
        self._game_players.reset()
        deck = self._deck_factory.create_deck()
        scores = self._create_scores()  # 得分管理器
        self._pots = self._create_pots()
        pots = self._pots

        # DB Init
        self._street = 0
        self._action_num = 0
        self._preflop_raise_count = 0
        self._hand_stats = {
            p.id: {
                'vpip': 0,
                'pfr': 0,
                'threebet': 0,
                'agg_bets': 0,
                'agg_calls': 0,
                'wtsd': 0,
                'wsd': 0
            } for p in self._game_players.all
        }
        self._init_db_record(dealer_id)
        
        # Capture starting stacks for net calculation
        starting_stacks = {p.id: p.money for p in self._game_players.all}

        self._event_dispatcher.new_game_event(
            game_id=self._id,
            players=self._game_players.active,
            dealer_id=dealer_id,
            big_blind=self._big_blind,
            small_blind=self._small_blind
        )

        try:
            # 大小盲自动下注
            blind_bets = self._collect_blinds(dealer_id)  # {c: 5, d: 10}

            # 下注顺序迭代器
            bet_rounds = bet_rounder(dealer_id, pots, scores, blind_bets)

            # 发牌
            self._assign_cards(2, dealer_id, deck, scores)

            # 在数据库中记录每名玩家的手牌
            if self._db_hand_id:
                for player in self._game_players.all:
                    cards = scores.player_cards(player.id)
                    if cards:
                        update_hand_player_result(self._db_hand_id, player.id, player.money, False,
                                                  json.dumps([c.dto() for c in cards]))

            # Pre-flop bet round
            bet_rounds.__next__()

            # Flop
            self._street = 1
            self._add_shared_cards(deck.pop_cards(3), scores)
            gevent.sleep(WAIT_AFTER_FLOP_TURN_RIVER)

            # Flop bet round
            bet_rounds.__next__()

            # Turn
            self._street = 2
            self._add_shared_cards(deck.pop_cards(1), scores)
            gevent.sleep(WAIT_AFTER_FLOP_TURN_RIVER)

            # Turn bet round
            bet_rounds.__next__()

            # River
            self._street = 3
            self._add_shared_cards(deck.pop_cards(1), scores)
            gevent.sleep(WAIT_AFTER_FLOP_TURN_RIVER)

            # River bet round
            if bet_rounds.__next__() and self._game_players.count_active() > 1:
                # There are still active players in the match and no showdown yet
                self._showdown(scores)

            raise EndGameException

        except EndGameException:
            total_pot = sum(pot.money for pot in pots)  # 防止self._detect_winners之后会清空pot
            winner_ids = self._detect_winners(pots, scores)

            # DB Finish Hand
            if self._db_hand_id:
                board_cards = json.dumps([c.dto() for c in scores.shared_cards])
                finish_hand(self._db_hand_id, board_cards, total_pot)

                for player in self._game_players.all:
                    is_winner = player.id in winner_ids
                    update_hand_player_result(self._db_hand_id, player.id, player.money, is_winner)
                    
                    # Update Stats
                    start_stack = starting_stacks.get(player.id, player.money)
                    net_chips = int(player.money - start_stack)
                    
                    # Only update stats for players who actually played (active or all-in at some point)
                    # For now update for everyone in the hand record
                    update_daily_stats(player.id, 1, net_chips)

                    # 生涯数据
                    ps = self._hand_stats.get(player.id, {})
                    # Won at Showdown: 赢了且去了摊牌
                    wsd = 1 if (is_winner and ps.get('wtsd')) else 0
                    
                    # 计算 BB 增益
                    net_bb = net_chips / self._big_blind if self._big_blind > 0 else 0
                    
                    update_lifetime_stats(
                        player.id,
                        hands_played=1,
                        net_chips=net_chips,
                        vpip=ps.get('vpip', 0),
                        pfr=ps.get('pfr', 0),
                        threebet=ps.get('threebet', 0),
                        agg_bets=ps.get('agg_bets', 0),
                        agg_calls=ps.get('agg_calls', 0),
                        wtsd=ps.get('wtsd', 0),
                        wsd=wsd,
                        net_bb=net_bb
                    )

            self._reset_ready_state()  # 重置准备状态

        finally:
            self._event_dispatcher.game_over_event()
