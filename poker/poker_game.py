import time
from typing import List, Dict, Set, Generator, Optional

import gevent

from .card import Card
from .channel import ChannelError, MessageTimeout, MessageFormatError
from .deck import DeckFactory, Deck
from .player import Player
from .player_server import PlayerServer
from .score_detector import Score, ScoreDetector
from .config import BET_TIMEOUT, TIMEOUT_TOLERANCE


class GameError(Exception):
    pass


class EndGameException(Exception):
    pass


class EndRoundException(Exception):
    pass


class GameFactory:
    def create_game(self, players: List[PlayerServer], room_id: str = None):
        raise NotImplemented


class GameSubscriber:
    def game_event(self, event, event_data):
        # 需要传入事件名称和事件的具体内容
        raise NotImplemented


class GamePlayers:
    def __init__(self, players: List[Player]):
        # Dictionary of players keyed by their ids
        self._players: Dict[int, Player] = {player.id: player for player in players}  # 玩家id-Player字典
        # List of player ids sorted according to the original players list
        self._player_ids: List[int] = [player.id for player in players]  # 玩家id列表
        # List of folder ids
        self._folder_ids: Set[int] = set()  # 弃牌玩家
        # Dead players
        self._dead_player_ids: Set[int] = set()  # 出局玩家

    def fold(self, player_id: int):
        # 弃牌玩家加入弃牌集合
        if player_id not in self._player_ids:
            raise ValueError("Unknown player id")
        self._folder_ids.add(player_id)

    def remove(self, player_id: int):
        # 移除玩家，同事标记为弃牌和已出局
        self.fold(player_id)
        self._dead_player_ids.add(player_id)

    def reset(self):
        # 在游戏的某些环节（如新的一轮开始之前），需要清除上一轮中未出局玩家的弃牌状态，但保留已出局玩家的状态。
        self._folder_ids = set(self._dead_player_ids)

    def round(self, dealer_id: int, reverse=False) -> Generator[Player, None, None]:
        """
        a,b,c,d,e 如果dealer_id是b，那么迭代器返回的结果为c, d, e, a, b
        列表第一位是小盲第二位是大盲最后一位是庄家
        """
        # 按顺序遍历未弃牌玩家
        start_item = (self._player_ids.index(dealer_id) + 1) % len(self._player_ids)  # 保证循环列表中在最后一位时也能取得小盲位索引
        step_multiplier = -1 if reverse else 1  # 根据方向确定步进值
        for i in range(len(self._player_ids)):
            next_item = (start_item + (i * step_multiplier)) % len(self._player_ids)
            player_id = self._player_ids[next_item]
            if player_id not in self._folder_ids:
                yield self._players[player_id]

    def get(self, player_id: int) -> Player:
        # 根据玩家id获取对象
        try:
            return self._players[player_id]
        except KeyError:
            raise ValueError("Unknown player id")

    def get_next(self, dealer_id: int) -> Optional[Player]:
        # 获取下一个未弃牌玩家
        if dealer_id not in self._player_ids:
            raise ValueError("Unknown player id")
        if dealer_id in self._folder_ids:
            raise ValueError("Inactive player")
        start_item = self._player_ids.index(dealer_id)
        for i in range(len(self._player_ids) - 1):
            next_index = (start_item + i + 1) % len(self._player_ids)
            next_id = self._player_ids[next_index]
            if next_id not in self._folder_ids:
                return self._players[next_id]
        return None

    def is_active(self, player_id: int) -> bool:
        # 检查玩家是否弃牌
        if player_id not in self._player_ids:
            raise ValueError("Unknown player id")
        return player_id not in self._folder_ids

    def count_active(self) -> int:
        # 获取未弃牌玩家数量
        return len(self._player_ids) - len(self._folder_ids)

    def count_active_with_money(self) -> int:
        # 获取未弃牌且有金钱的玩家数量
        return len([player for player in self.active if player.money > 0])

    @property
    def all(self) -> List[Player]:
        # 获取所有未出局玩家
        return [self._players[player_id] for player_id in self._player_ids if player_id not in self._dead_player_ids]

    @property
    def folders(self) -> List[Player]:
        # 获取所有弃牌玩家
        return [self._players[player_id] for player_id in self._folder_ids]

    @property
    def dead(self) -> List[Player]:
        # 获取所有出局玩家
        return [self._players[player_id] for player_id in self._dead_player_ids]

    @property
    def active(self) -> List[Player]:
        #
        return [self._players[player_id] for player_id in self._player_ids if player_id not in self._folder_ids]


class GameScores:
    def __init__(self, score_detector: ScoreDetector):
        self._score_detector: ScoreDetector = score_detector
        self._players_cards: Dict[int, List[Card]] = {}
        self._shared_cards: List[Card] = []

    @property
    def shared_cards(self):
        # 获取公共牌
        return self._shared_cards

    def player_cards(self, player_id: int):
        # 获取玩家手牌
        return self._players_cards[player_id]

    def player_score(self, player_id: int):
        # 计分
        return self._score_detector.get_score(self._players_cards[player_id] + self._shared_cards)

    def assign_cards(self, player_id: int, cards: List[Card]):
        # 分配手牌
        self._players_cards[player_id] = self._score_detector.get_score(cards).cards

    def add_shared_cards(self, cards):
        # 添加公共牌
        self._shared_cards += cards


class GamePots:
    # 奖金池
    class GamePot:
        """
        单个奖金池类，用于存储奖金金额和参与玩家。
        """

        def __init__(self):
            self._money = 0.0
            self._players: List[Player] = []
            # 新增: 记录玩家在此特定底池中的贡献
            self._contributions: Dict[int, float] = {}

        def add_money(self, money: float):
            self._money += money

        def add_player(self, player: Player):
            self._players.append(player)
            # 新增: 初始化玩家贡献
            if player.id not in self._contributions:
                self._contributions[player.id] = 0.0

        # 新增: 添加玩家贡献的方法
        def add_player_contribution(self, player_id: int, amount: float):
            self._contributions[player_id] = self._contributions.get(player_id, 0.0) + amount

        @property
        def money(self) -> float:
            return self._money

        @property
        def players(self) -> List[Player]:
            return self._players

        # 新增: 获取贡献的属性
        @property
        def contributions(self) -> Dict[int, float]:
            return self._contributions

    def __len__(self):
        return len(self._pots)

    def __getitem__(self, item):
        return self._pots[item]

    def __iter__(self):
        return iter(self._pots)

    def __init__(self, game_players: GamePlayers):
        self._game_players = game_players
        self._pots = []
        self._bets = {player.id: 0.0 for player in game_players.all}

    @property
    def bets(self) -> Dict[int, float]:
        return self._bets

    def add_bets(self, bets: Dict[int, float]):
        for player in self._game_players.all:  # self._game_players.all所有未出局玩家的Player列表
            self._bets[player.id] += bets[player.id] if player.id in bets else 0.0

        bets = dict(self._bets)  # 浅拷贝，保证不直接修改self._bets

        # List of players sorted by their bets
        # 按照玩家下注金额从低到高排序
        players = sorted(
            self._game_players.all,
            key=lambda player: bets[player.id]
        )

        self._pots = []  # 清空当前的奖金池

        spare_money = 0.0  # 用于存储未分配的金额（通常来自非活动玩家）

        '''
        处理逻辑
        玩家 ID	活跃状态	下注金额
        P1	活跃	100
        P2	非活动	50
        P3	活跃	200
        P4	活跃	100
        执行逻辑
        
            1.	第一轮：处理 P1 的下注金额 100
            •	当前活跃玩家：P1、P3、P4。
            •	创建一个奖金池，金额为 100 * 3 = 300。
            •	参与玩家：P1、P3、P4。
            •	更新玩家下注金额：
            •	P1：0
            •	P3：100
            •	P4：0
            2.	第二轮：处理 P3 的剩余下注金额 100
            •	当前活跃玩家：P3。
            •	创建一个新的奖金池，金额为 100。
            •	参与玩家：P3。
            •	更新玩家下注金额：
            •	P3：0
            3.	处理非活动玩家 P2 的金额
            •	P2 的 50 会被加入 spare_money，在下一次活跃玩家奖金池分配中使用。
            •	如果所有玩家的下注金额已匹配完毕，spare_money 应为 0。
        
        最终奖金池结果
        奖金池编号	金额	参与玩家
        1	300	P1、P3、P4
        2	100	P3
        '''

        for i, player in enumerate(players):
            if not self._game_players.is_active(player.id):
                # 如果玩家处于非活动状态（例如弃牌或出局），他们的下注金额不会参与任何后续奖金池的分配
                # 这些金额被加入spare_money，作为后续奖金池的补充资金
                spare_money += bets[player.id]
                bets[player.id] = 0.0
            elif bets[player.id] > 0.0:
                # 如果玩家仍然活跃且有下注金额
                pot_bet = bets[player.id]  # 当前玩家下注值
                current_pot = GamePots.GamePot()  # 创建一个新的奖金池
                # 将 spare_money（来自之前非活动玩家的资金）加入当前奖金池
                current_pot.add_money(spare_money)
                spare_money = 0.0  # 重置spare_money为 0，因为它已被分配到当前奖金池
                for j in range(i, len(players)):
                    # 从当前玩家开始，检查后续玩家是否活跃
                    if self._game_players.is_active(players[j].id):
                        # 如果玩家活跃，将其加入当前奖金池的参与者列表
                        current_pot.add_player(players[j])
                        # 新增: 记录活跃玩家对这个特定底池的贡献
                        current_pot.add_player_contribution(players[j].id, pot_bet)
                    # 每个活跃玩家都需要匹配当前的下注金额（pot_bet）
                    current_pot.add_money(pot_bet)
                    bets[players[j].id] -= pot_bet  # 减少玩家的下注金额，记录匹配的部分
                self._pots.append(current_pot)

        if spare_money:
            # The players who bet more is actually inactive
            raise ValueError("Invalid bets")


class GameEventDispatcher:
    """
    游戏事件分发
    1.添加、移除玩家。通过_subscribers列表管理
    2.触发事件，为每个玩家广播事件
    """
    def __init__(self, game_id: str, logger):
        self._subscribers: List[GameSubscriber] = []  # 所有订阅者
        self._game_id: str = game_id
        self._logger = logger

    def subscribe(self, subscriber: GameSubscriber):
        # 添加订阅者
        self._subscribers.append(subscriber)

    def unsubscribe(self, subscriber: GameSubscriber):
        # 移除订阅者
        self._subscribers.remove(subscriber)

    def raise_event(self, event: str, event_data: dict):
        """
        将事件名称与内容传给每个玩家（订阅者，GameSubscriber）
        """
        # 触发事件
        event_data["event"] = event
        event_data["game_id"] = self._game_id
        self._logger.debug(
            "\n" +
            ("-" * 80) + "\n"
                         "GAME: {}\nEVENT: {}".format(self._game_id, event) + "\n" +
            str(event_data) + "\n" +
            ("-" * 80) + "\n"
        )
        gevent.joinall([
            gevent.spawn(subscriber.game_event, event, event_data)
            for subscriber in self._subscribers
        ])

    def cards_assignment_event(self, player: Player, cards: List[Card], score: Score):
        # 发牌
        self.raise_event(
            "cards-assignment",
            {
                "target": player.id,
                "cards": [card.dto() for card in cards],
                "score": score.dto()
            }
        )

    def pots_update_event(self, players: List[Player], pots: GamePots):
        # 更新底池
        self.raise_event(
            "pots-update",
            {
                "pots": [
                    {
                        "money": pot.money,
                        "player_ids": [player.id for player in pot.players],
                    }
                    for pot in pots
                ],
                "players": {player.id: player.dto() for player in players}
            }
        )

    def winner_designation_event(self, players: List[Player], pot: GamePots.GamePot, winners: List[Player],
                                 money_split: float, net_win_split: float, upcoming_pots: GamePots, bets: Dict[int, float]):
        # 赢家判定
        self.raise_event(
            "winner-designation",
            {
                "pot": {
                    "money": pot.money,
                    "player_ids": [player.id for player in pot.players],
                    "winner_ids": [winner.id for winner in winners],
                    "money_split": money_split,
                    # 新增: 用于前端显示的净赢金额
                    "net_win_split": net_win_split
                },
                "pots": [
                    {
                        "money": upcoming_pot.money,
                        "player_ids": [player.id for player in upcoming_pot.players]
                    }
                    for upcoming_pot in upcoming_pots
                ],
                "players": {player.id: player.dto() for player in players},
                "bets": bets
            }
        )

    def bet_action_event(self, player: Player, min_bet: float, max_bet: float, bets: Dict[int, float], timeout: int,
                         timeout_epoch: float):
        # 下注动作
        self.raise_event(
            "player-action",
            {
                "action": "bet",
                "player": player.dto(),
                "min_bet": min_bet,
                "max_bet": max_bet,
                "bets": bets,
                "timeout": timeout,
                "timeout_date": time.strftime("%Y-%m-%d %H:%M:%S+0000", time.gmtime(timeout_epoch))
            }
        )

    def bet_event(self, player: Player, bet: float, bet_type: str, bets: Dict[str, float]):
        # 完成下注
        self.raise_event(
            "bet",
            {
                "player": player.dto(),
                "bet": bet,
                "bet_type": bet_type,
                "bets": bets
            }
        )

    def dead_player_event(self, player: Player):
        # 玩家出局
        self.raise_event(
            "dead-player",
            {
                "player": player.dto()
            }
        )

    def fold_event(self, player: Player):
        # 玩家弃牌
        self.raise_event(
            "fold",
            {
                "player": player.dto()
            }
        )

    def showdown_event(self, players: List[Player], scores: GameScores):
        # 摊牌
        self.raise_event(
            "showdown",
            {
                "players": {
                    player.id: {
                        "cards": [card.dto() for card in scores.player_cards(player.id)],
                        "score": scores.player_score(player.id).dto(),
                    }
                    for player in players
                }
            }
        )

    def shared_cards_event(self, new_shared_cards: List[Card]):
        # 发公共牌
        raise NotImplemented

    def new_game_event(self, *args, **kwargs):
        raise NotImplemented

    def game_over_event(self):
        raise NotImplemented

    def update_ranking_event(self, ranking_data):
        raise NotImplemented


class GameWinnersDetector:
    """
    GameWinnersDetector 类用于检测和确定特定奖金池中的赢家。
    功能：
    - 根据玩家的牌组得分判定赢家。
    - 支持多个赢家（如果得分相同，则平分奖金）。
    """
    def __init__(self, game_players: GamePlayers):
        self._game_players: GamePlayers = game_players

    def get_winners(self, players: List[Player], scores: GameScores) -> List[Player]:
        winners = []

        for player in players:
            if not self._game_players.is_active(player.id):
                continue
            if not winners:
                winners.append(player)
            else:
                score_diff = scores.player_score(player.id).cmp(scores.player_score(winners[0].id))
                if score_diff == 0:
                    winners.append(player)
                elif score_diff > 0:
                    winners = [player]

        return winners


class GameBetRounder:
    """
    GameBetRounder 类用于管理扑克游戏中的单轮下注逻辑。

    功能：
    - 计算当前玩家的最大和最小可下注金额。
    - 按顺序执行一轮完整的下注操作。
    - 维护下注的有效性，处理玩家弃牌、下注或全押等情况。

    属性：
    - _game_players (GamePlayers): 管理游戏玩家的对象，用于获取当前活跃玩家信息。
    """
    def __init__(self, game_players: GamePlayers):
        self._game_players: GamePlayers = game_players

    def _get_max_bet(self, dealer: Player, bets: Dict[int, float]) -> float:
        """
        计算当前玩家（dealer）的最大可下注金额。

        参数：
        - dealer (Player): 当前轮到的玩家。
        - bets (Dict[str, float]): 玩家当前的下注状态，键为玩家 ID，值为已下注金额。

        返回：
        - float: 当前玩家的最大可下注金额。
        """
        # Max raise:
        # Maximum amount of money that other players bet (or can still bet) during this round
        try:
            # 计算其他玩家的最大可下注金额
            highest_stake = max(
                player.money + bets[player.id]
                for player in self._game_players.round(dealer.id)
                if player is not dealer
            )
        except ValueError:
            return 0.0

        # 最大下注金额取决于其他玩家的下注金额差和当前玩家的剩余金额
        return min(
            highest_stake - bets[dealer.id],
            dealer.money
        )

    def _get_min_bet(self, dealer: Player, bets: Dict[int, float]) -> float:
        """
        计算当前玩家（dealer）的最小可下注金额。

        参数：
        - dealer (Player): 当前轮到的玩家。
        - bets (Dict[str, float]): 玩家当前的下注状态，键为玩家 ID，值为已下注金额。

        返回：
        - float: 当前玩家的最小可下注金额。
        """
        return min(
            max(bets.values()) - bets[dealer.id],
            dealer.money
        )

    def bet_round(self, dealer_id: int, bets: Dict[int, float], get_bet_function, on_bet_function=None, blind_bet: bool=False) -> Optional[
        PlayerServer]:
        """
        performs a complete bet round
        returns the player who last raised - if nobody raised, then the first one to check
        """
        players_round = list(self._game_players.round(dealer_id))

        if len(players_round) == 0:
            raise GameError("No active players in this game")

        # The starting_player might be inactive. Moving to the first active player
        if len(players_round) == 2:
            # 两个人的时候，第一个人是小盲，第二个人是大盲也是庄家，所以按顺序就又轮到小盲位下注了
            starting_player = players_round[0]
        else:
            # 两人以上对局时，盲注轮就从大盲下一位开始下注，非盲注轮从小盲开始
            starting_player = players_round[2] if blind_bet else players_round[0]

        # 盲注轮第一位和第二位的大小盲注都已完成下注，比较当前玩家金额比上家大的时候就不需要比较大盲下一位和大盲，所以跳过大小盲和大盲+1位
        offset = 2 if blind_bet else 0

        for k, player in enumerate(players_round):
            if player.id not in bets:
                bets[player.id] = 0
            # 检查当前下注是否比上家下注小
            if bets[player.id] < 0 or (k > offset and bets[player.id] < bets[players_round[k - 1].id]):
                # Ensuring the bets dictionary makes sense
                raise ValueError("Invalid bets dictionary")

        best_player = None  # 最后加注的玩家

        while starting_player is not None and starting_player != best_player:
            next_player = self._game_players.get_next(starting_player.id)

            # 计算当前玩家下注的上下限
            max_bet = self._get_max_bet(starting_player, bets)
            min_bet = self._get_min_bet(starting_player, bets)

            if max_bet == 0.0:
                # No bet required to this player (either he is all-in or all other players are all-in)
                bet = 0.0
            else:
                # This player isn't all in, and there's at least one other player who is not all-in
                # 接收下注数据
                bet = get_bet_function(player=starting_player, min_bet=min_bet, max_bet=max_bet, bets=bets)

            if bet == -1:
                self._game_players.fold(starting_player.id)
            else:
                if bet < min_bet or bet > max_bet:
                    raise ValueError("Invalid bet")
                starting_player.take_money(bet)
                bets[starting_player.id] += bet
                if best_player is None or bet > min_bet:
                    best_player = starting_player

            if on_bet_function:
                on_bet_function(starting_player, bet, min_bet, max_bet, bets)

            starting_player = next_player  # 移动到下一个玩家

        # 返回最后一个加注的玩家，如果没有返回第一个过牌的玩家
        return best_player


class GameBetHandler:
    """
    GameBetHandler 类用于管理扑克游戏中的下注逻辑。

    功能：
    - 管理玩家的下注轮次。
    - 调用下注处理逻辑并广播下注事件。
    - 处理玩家的下注输入（如超时、弃牌、下注等）。
    - 更新奖金池信息并触发相关事件。

    属性：
    - _game_players (GamePlayers): 游戏玩家管理器，用于获取玩家状态和操作玩家数据。
    - _bet_rounder (GameBetRounder): 下注轮次处理器，负责管理单轮下注逻辑。
    - _event_dispatcher (GameEventDispatcher): 游戏事件分发器，用于触发事件广播。
    - _bet_timeout (int): 玩家下注的超时时间（秒）。
    - _timeout_tolerance (int): 超时容忍时间，允许一定范围内的延迟。
    - _wait_after_round (int): 每轮下注结束后的等待时间（秒）。
    """
    def __init__(self, game_players: GamePlayers, bet_rounder: GameBetRounder, event_dispatcher: GameEventDispatcher,
                 bet_timeout: int, timeout_tolerance: int, wait_after_round: int, on_action_callback=None):
        self._game_players: GamePlayers = game_players
        self._bet_rounder: GameBetRounder = bet_rounder
        self._event_dispatcher: GameEventDispatcher = event_dispatcher
        self._bet_timeout: int = bet_timeout
        self._timeout_tolerance: int = timeout_tolerance
        self._wait_after_round: int = wait_after_round
        self._on_action_callback = on_action_callback

    def any_bet(self, bets: Dict[int, float]) -> bool:
        """
        检查当前是否有任何玩家下注。

        参数：
        - bets (Dict[str, float]): 玩家当前的下注状态。

        返回：
        - bool: 如果至少有一名玩家下注金额大于零，则返回 True。
        """
        return any(k for k in bets if bets[k] > 0)

    def bet_round(self, dealer_id: int, bets: Dict[int, float], pots: GamePots, blind_bet: bool = False):
        """
        执行一轮下注操作。

        参数：
        - dealer_id (str): 当前庄家的玩家 ID。
        - bets (Dict[str, float]): 玩家当前的下注状态。
        - pots (GamePots): 当前奖金池对象。

        返回：
        - PlayerServer: 返回最后加注的玩家。如果没有加注，则返回第一个进行检查的玩家。
        """
        # 调用 bet_rounder 执行下注轮次逻辑
        best_player = self._bet_rounder.bet_round(dealer_id, bets, self.get_bet, self.on_bet, blind_bet)  # [b,c,d,e,a]
        gevent.sleep(self._wait_after_round)
        if self.any_bet(bets):
            pots.add_bets(bets)
            self._event_dispatcher.pots_update_event(self._game_players.active, pots)
        return best_player

    def get_bet(self, player, min_bet: float, max_bet: float, bets: Dict[int, float]) -> Optional[int]:
        """
        获取玩家的下注金额。

        参数：
        - player (Player): 当前下注的玩家。
        - min_bet (float): 当前最小下注金额。
        - max_bet (float): 当前最大下注金额。
        - bets (Dict[str, float]): 玩家当前的下注状态。

        返回：
        - Optional[int]: 玩家下注的金额。如果返回 None，表示玩家未下注或超时。
        """
        timeout_epoch = time.time() + self._bet_timeout
        self._event_dispatcher.bet_action_event(
            player=player,
            min_bet=min_bet,
            max_bet=max_bet,
            bets=bets,
            timeout=self._bet_timeout,
            timeout_epoch=timeout_epoch
        )
        return self.receive_bet(player, min_bet, max_bet, timeout_epoch)

    def receive_bet(self, player, min_bet, max_bet, timeout_epoch) -> Optional[int]:
        """
        接收玩家的下注金额。

        参数：
        - player (Player): 当前下注的玩家。
        - min_bet (float): 当前最小下注金额。
        - max_bet (float): 当前最大下注金额。
        - timeout_epoch (float): 超时时间点（UNIX 时间戳）。

        返回：
        - Optional[int]: 玩家下注的金额。如果返回 None，表示玩家未下注或超时。

        异常：
        - 捕获 MessageTimeout、MessageFormatError 等异常，向玩家发送错误消息。
        """
        try:
            message = player.recv_message(timeout_epoch=timeout_epoch)

            MessageFormatError.validate_message_type(message, "bet")

            if "bet" not in message:
                raise MessageFormatError(attribute="bet", desc="Attribute is missing")

            try:
                bet = round(float(message["bet"]))  # Strip decimals
            except ValueError:
                raise MessageFormatError(attribute="bet", desc="'{}' is not a number".format(message.bet))
            else:
                # Validating bet
                if bet != -1 and (bet < min_bet or bet > max_bet):
                    raise MessageFormatError(
                        attribute="bet",
                        desc="Bet out of range. min: {} max: {}, actual: {}".format(min_bet, max_bet, bet)
                    )
                return bet

        except (ChannelError, MessageFormatError, MessageTimeout) as e:
            player.send_message({"message_type": "error", "error": e.args[0]})
            return -1

    def on_bet(self, player: Player, bet: float, min_bet: float, max_bet: float, bets: Dict[int, float]):
        """
        处理玩家的下注事件并触发相关事件。

        参数：
        - player (Player): 当前下注的玩家。
        - bet (float): 玩家下注的金额。
        - min_bet (float): 当前最小下注金额。
        - max_bet (float): 当前最大下注金额。
        - bets (Dict[str, float]): 玩家当前的下注状态。
        """
        def get_bet_type(bet):
            if bet == 0:
                return "check"
            elif bet == player.money:
                return "all-in"
            elif bet == min_bet:
                return "call"
            else:
                return "raise"

        if bet == -1:
            self._event_dispatcher.fold_event(player)
            # Call callback for fold (bet = -1)
            if self._on_action_callback:
                self._on_action_callback(player, -1, 0, 0, bets)
        else:
            self._event_dispatcher.bet_event(player, bet, get_bet_type(bet), bets)
            if self._on_action_callback:
                self._on_action_callback(player, bet, min_bet, max_bet, bets)


class PokerGame:
    """
    - 玩法接口  play_hand
    - 工厂方法
        - 下注  _create_bet_handler
        - 赢家判定
        - 奖池
        - 得分管理
    - 牌组管理
        - 发牌
        - 发送分数
    - 赢家判定
        - 判定赢家
        - 发送赢家信息
        - 摊牌流程
    """

    WAIT_AFTER_CARDS_ASSIGNMENT = 1  # 发牌后等待时间
    WAIT_AFTER_BET_ROUND = 1   # 下注轮次后等待时间
    WAIT_AFTER_SHOWDOWN = 1  # 摊牌后等待时间
    WAIT_AFTER_WINNER_DESIGNATION = 1  # 赢家判定后等待时间

    def __init__(self, id: str, game_players: GamePlayers, event_dispatcher: GameEventDispatcher,
                 deck_factory: DeckFactory, score_detector: ScoreDetector, room_id: str = None):
        self._id: str = id
        self._room_id: str = room_id
        self._game_players: GamePlayers = game_players
        self._event_dispatcher: GameEventDispatcher = event_dispatcher
        self._deck_factory: DeckFactory = deck_factory
        self._score_detector: ScoreDetector = score_detector
        self._bet_handler: GameBetHandler = self._create_bet_handler()
        self._winners_detector: GameWinnersDetector = self._create_winners_detector()

    @property
    def event_dispatcher(self) -> GameEventDispatcher:
        return self._event_dispatcher

    def play_hand(self, dealer_id: int):
        """
        玩法具体实现
        """
        raise NotImplemented

    def save_player_data(self):
        raise NotImplemented
        
    def _on_player_action(self, player, bet, min_bet, max_bet, bets):
        """Callback for player actions, to be overridden for DB logging"""
        pass

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Factory methods
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _create_bet_handler(self) -> GameBetHandler:
        """
        创建下注处理器。
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

    def _create_winners_detector(self) -> GameWinnersDetector:
        """
        创建赢家检测器。

        返回：
        - GameWinnersDetector: 用于检测赢家的组件。
        """
        return GameWinnersDetector(self._game_players)

    def _create_pots(self) -> GamePots:
        """
        创建奖金池管理器。

        返回：
        - GamePots: 负责管理奖金池的组件。
        """
        return GamePots(self._game_players)

    def _create_scores(self) -> GameScores:
        """
        创建得分管理器。

        返回：
        - GameScores: 用于管理玩家得分的组件。
        """
        return GameScores(self._score_detector)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Cards handler
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _assign_cards(self, number_of_cards: int, dealer_id: int, deck: Deck, scores: GameScores):
        """
        给每名玩家分配手牌。

        参数：
        - number_of_cards (int): 每名玩家分配的牌数。
        - dealer_id (str): 当前的庄家 ID。
        - deck (Deck): 当前游戏使用的牌组。
        - scores (GameScores): 管理玩家得分的组件。
        """
        # Assign cards
        for player in self._game_players.round(dealer_id):
            # Distribute cards
            scores.assign_cards(player.id, deck.pop_cards(number_of_cards))
            self._send_player_score(player, scores)
        gevent.sleep(self.WAIT_AFTER_CARDS_ASSIGNMENT)

    def _send_player_score(self, player: Player, scores: GameScores):
        """
        向玩家发送其得分信息。

        参数：
        - player (Player): 当前的玩家。
        - scores (GameScores): 管理玩家得分的组件。
        """
        self._event_dispatcher.cards_assignment_event(
            player=player,
            cards=scores.player_cards(player.id),
            score=scores.player_score(player.id)
        )

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Winners designation
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _game_over_detection(self):
        """
        检测游戏是否结束。如果剩余活跃玩家不足两人，则抛出 EndGameException 异常。

        异常：
        - EndGameException: 如果游戏结束（活跃玩家少于两人）。
        """
        if self._game_players.count_active() < 2:
            raise EndGameException

    def _detect_winners(self, pots: GamePots, scores: GameScores) -> Set[int]:
        """
        检测并分配赢家。

        参数：
        - pots (GamePots): 当前游戏的奖金池管理器。
        - scores (GameScores): 管理玩家得分的组件。
        
        返回：
        - Set[int]: 所有赢家的ID集合。

        异常：
        - GameError: 如果没有玩家可以分配奖金。
        """
        all_winner_ids = set()
        for i, pot in enumerate(reversed(pots)):
            winners = self._winners_detector.get_winners(pot.players, scores)
            try:
                money_split = round(pot.money / len(winners))  # Strip decimals
            except ZeroDivisionError:
                raise GameError("No players left")
            else:
                for winner in winners:
                    # 核心业务逻辑: 给赢家账户加钱，此行不应改动以确保数据正确
                    winner.add_money(money_split)
                    all_winner_ids.add(winner.id)

                # 新增: 为前端显示计算净利润
                # 由于底池的所有赢家对该池的贡献相同，我们只取第一个赢家来计算
                first_winner_contribution = pot.contributions.get(winners[0].id, 0.0)
                net_win_for_display = money_split - first_winner_contribution

                self._event_dispatcher.winner_designation_event(
                    players=self._game_players.active,
                    pot=pot,
                    winners=winners,
                    money_split=money_split,
                    # 新增: 传入用于前端显示的净赢金额
                    net_win_split=net_win_for_display,
                    upcoming_pots=pots[:-(i + 1)],
                    bets=pots.bets
                )

                gevent.sleep(self.WAIT_AFTER_WINNER_DESIGNATION)
        return all_winner_ids

    def _showdown(self, scores: GameScores):
        """
        执行摊牌流程，通知玩家所有的手牌和得分。

        参数：
        - scores (GameScores): 管理玩家得分的组件。
        """
        self._event_dispatcher.showdown_event(self._game_players.active, scores)
        gevent.sleep(self.WAIT_AFTER_SHOWDOWN)
