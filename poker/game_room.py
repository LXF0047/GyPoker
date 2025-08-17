import threading
from typing import Dict, List, Optional

import gevent

from .player_server import PlayerServer
from .poker_game import GameSubscriber, GameError, GameFactory


class FullGameRoomException(Exception):
    pass


class DuplicateRoomPlayerException(Exception):
    pass


class UnknownRoomPlayerException(Exception):
    pass


class GameRoomPlayers:
    """管理房间内玩家"""

    def __init__(self, room_size: int):
        self._seats: List[Optional[str]] = [None] * room_size  # 初始化房间座位
        self._players: Dict[str, PlayerServer] = {}  # 玩家id和PlayerServer映射
        self._lock = threading.Lock()

    @property
    def players(self) -> List[PlayerServer]:
        """
        获取当前房间内所有玩家的列表。
        :return: 玩家实例列表
        """
        self._lock.acquire()
        try:
            return [self._players[player_id] for player_id in self._seats if player_id is not None]
        finally:
            self._lock.release()

    @property
    def seats(self) -> List[Optional[str]]:
        """
        获取当前房间的座位状态。
        :return: 座位列表
        """
        self._lock.acquire()
        try:
            return list(self._seats)
        finally:
            self._lock.release()

    def get_player(self, player_id: str) -> PlayerServer:
        """
        获取指定ID的玩家实例。
        :param player_id: 玩家ID
        :return: PlayerServer实例
        :raises UnknownRoomPlayerException: 如果玩家不存在
        """
        self._lock.acquire()
        try:
            return self._players[player_id]
        except KeyError:
            raise UnknownRoomPlayerException
        finally:
            self._lock.release()

    def add_player(self, player: PlayerServer):
        """
        添加玩家
        self._seats列表中添加玩家id
        self._players字典中添加玩家id-玩家实例
        """
        self._lock.acquire()
        try:
            if player.id in self._players:
                raise DuplicateRoomPlayerException

            try:
                free_seat = self._seats.index(None)
            except ValueError:
                raise FullGameRoomException
            else:
                self._seats[free_seat] = player.id
                self._players[player.id] = player
        finally:
            self._lock.release()

    def remove_player(self, player_id: str):
        """
        移除玩家
        self._seats列表中删除玩家id
        self._players中移除该玩家的kv
        """
        self._lock.acquire()
        try:
            seat = self._seats.index(player_id)
        except ValueError:
            raise UnknownRoomPlayerException
        else:
            self._seats[seat] = None
            del self._players[player_id]
        finally:
            self._lock.release()


class GameRoomEventHandler:
    """处理房间内事件"""

    def __init__(self, room_players: GameRoomPlayers, room_id: str, logger):
        """
        初始化房间事件处理器。
        :param room_players: 房间玩家管理实例
        :param room_id: 房间ID
        :param logger: 日志记录器
        """
        self._room_players: GameRoomPlayers = room_players
        self._room_id: str = room_id
        self._logger = logger

    def room_event(self, event, player_id):
        """
        记录和广播房间事件。
        :param event: 事件类型
        :param player_id: 涉及的玩家ID
        """
        self._logger.debug(
            "\n" +
            ("-" * 80) + "\n"
                         "ROOM: {}\nEVENT: {}\nPLAYER: {}\nSEATS:\n - {}".format(
                self._room_id,
                event,
                player_id,
                "\n - ".join([seat if seat is not None else "(empty seat)" for seat in self._room_players.seats])
            ) + "\n" +
            ("-" * 80) + "\n"
        )
        self.broadcast({
            "message_type": "room-update",
            "event": event,
            "room_id": self._room_id,
            "players": {player.id: player.dto() for player in self._room_players.players},
            "player_ids": self._room_players.seats,
            "player_id": player_id
        })

    def broadcast(self, message):
        """
        广播消息到所有玩家。
        :param message: 要广播的消息
        """
        for player in self._room_players.players:
            player.try_send_message(message)


class GameRoom(GameSubscriber):
    """
    游戏房间类，负责管理房间内的玩家、处理玩家加入和离开事件，
    以及与游戏工厂交互以管理游戏的生命周期。
    继承自 GameSubscriber，支持订阅游戏事件。
    """

    def __init__(self, id: str, private: bool, game_factory: GameFactory, room_size: int, logger):
        """
        初始化游戏房间。
        :param id: 房间ID
        :param private: 是否为私人房间
        :param game_factory: 游戏工厂，用于创建游戏实例
        :param room_size: 房间的最大容量
        :param logger:
        """
        self.id = id
        self.private = private
        self.active = False
        self._game_factory = game_factory
        self._room_players = GameRoomPlayers(room_size)  # 管理玩家
        self._room_event_handler = GameRoomEventHandler(self._room_players, self.id, logger)  # 管理房间
        self._event_messages = []
        self._logger = logger
        self._lock = threading.Lock()

    def join(self, player: PlayerServer):
        self._lock.acquire()
        try:
            try:
                self._room_players.add_player(player)  # 在GameRoomPlayer中添加玩家
                self._room_event_handler.room_event("player-added", player.id)  # 将player-added事件广播给房间内所有玩家
            except DuplicateRoomPlayerException:
                old_player = self._room_players.get_player(player.id)
                old_player.update_channel(player)
                player = old_player
                self._room_event_handler.room_event("player-rejoined", player.id)

            for event_message in self._event_messages:
                # 将事件信息广播给加入的玩家
                if "target" not in event_message or event_message["target"] == player.id:
                    # target为针对某玩家的单独事件
                    player.send_message(event_message)
        finally:
            self._lock.release()

    def leave(self, player_id: str):
        self._lock.acquire()
        try:
            self._leave(player_id)
        finally:
            self._lock.release()

    def _leave(self, player_id: str):
        """
        处理玩家离开的内部方法。
        :param player_id: 离开的玩家ID
        """
        player = self._room_players.get_player(player_id)  # 获取某id的PlayerServer
        player.disconnect()
        self._room_players.remove_player(player.id)  # 使用管理玩家类GameRoomPlayers中移除
        self._room_event_handler.room_event("player-removed", player.id)  # 广播player-removed事件

    def game_event(self, event: str, event_data: dict):
        """
        处理游戏事件。
        :param event: 游戏事件类型
        :param event_data: 事件相关数据
        """
        self._lock.acquire()
        try:
            # Broadcast the event to the room
            event_message = {"message_type": "game-update"}
            event_message.update(event_data)

            if "target" in event_data:
                player = self._room_players.get_player(event_data["target"])  # 获取指定PlayerServer
                player.send_message(event_message)  # 发送消息
            else:
                # Broadcasting message
                self._room_event_handler.broadcast(event_message)  # 广播消息

            if event == "game-over":
                # 游戏结束清空事件
                self._event_messages = []
            else:
                # 添加事件
                self._event_messages.append(event_message)

            if event == "dead-player":
                self._leave(event_data["player"]["id"])
        finally:
            self._lock.release()

    def remove_inactive_players(self):
        """
        移除所有不活跃的玩家。
        """

        def ping_player(player):
            if not player.ping():
                self.leave(player.id)

        gevent.joinall([
            gevent.spawn(ping_player, player)
            for player in self._room_players.players
        ])

    def all_players_ready(self):
        """
        检查所有玩家是否都准备就绪。
        """
        return all(player.ready for player in self._room_players.players)

    def activate(self):
        """
        激活房间并开始游戏循环。
        """
        self.active = True
        try:
            self._logger.info("Activating room {}...".format(self.id))
            dealer_key = -1
            while True:
                try:
                    self.remove_inactive_players()
                    # 检查准备状态
                    if not self.all_players_ready():
                        continue
                    # 检查是否大于两个玩家
                    players = self._room_players.players
                    if len(players) < 2:
                        raise GameError("At least two players needed to start a new game")

                    dealer_key = (dealer_key + 1) % len(players)  # 更新庄家位置
                    game = self._game_factory.create_game(players)  # game是HoldemPokerGame()
                    game.event_dispatcher.subscribe(self)  # 添加订阅者
                    game.play_hand(players[dealer_key].id)  # 开始游戏
                    game.save_player_data()  # 保存玩家数据
                    game.update_ranking_list()  # 更新排行榜
                    game.event_dispatcher.unsubscribe(self)  # 取消订阅

                except GameError:
                    break
        finally:
            # 只有一个玩家时房间状态为非活动
            self._logger.info("Deactivating room {}...".format(self.id))
            self.active = False


class GameRoomFactory:
    """
    游戏房间工厂类，用于创建房间实例。
    提供了标准化的接口，根据房间大小和游戏工厂生成新房间。
    """

    def __init__(self, room_size: int, game_factory: GameFactory):
        self._room_size: int = room_size
        self._game_factory: GameFactory = game_factory

    def create_room(self, id: str, private: bool, logger) -> GameRoom:
        return GameRoom(id=id, private=private, game_factory=self._game_factory, room_size=self._room_size,
                        logger=logger)
