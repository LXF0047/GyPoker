import logging
import threading
from typing import List, Generator, Dict
from uuid import uuid4

import gevent

from .player_server import PlayerServer
from .game_room import FullGameRoomException, GameRoom, GameRoomFactory


class ConnectedPlayer:
    """已连接玩家类"""
    def __init__(self, player: PlayerServer, room_id: str = None):
        self.player: PlayerServer = player
        self.room_id: str = room_id


class GameServer:
    """

    """
    def __init__(self, room_factory: GameRoomFactory, logger=None):
        self._id: str = str(uuid4())
        self._rooms: List[GameRoom] = []
        self._players: Dict[str, PlayerServer] = {}
        self._lobby_lock = threading.Lock()
        self._room_factory: GameRoomFactory = room_factory
        self._logger = logger if logger else logging

    def __str__(self):
        return "server {}".format(self._id)

    def new_players(self) -> Generator[ConnectedPlayer, None, None]:
        raise NotImplementedError

    def __get_room(self, room_id: str) -> GameRoom:
        """
        根据房间id获取GameRoom实例
        """
        try:
            return next(room for room in self._rooms if room.id == room_id)
        except StopIteration:
            room = self._room_factory.create_room(id=room_id, private=True, logger=self._logger)
            self._rooms.append(room)
            return room

    def get_room_by_id(self, room_id: str) -> GameRoom:
        try:
            return next(room for room in self._rooms if room.id == room_id)
        except StopIteration:
            return None

    def _join_private_room(self, player: PlayerServer, room_id: str) -> GameRoom:
        """加入私有房间"""
        self._lobby_lock.acquire()
        try:
            room = self.__get_room(room_id)
            room.join(player)  # PlayerServer添加到GameRoomPlayers(room_size)中
            return room
        finally:
            self._lobby_lock.release()

    def _join_any_public_room(self, player: PlayerServer) -> GameRoom:
        """加入任意一个非满的公共房间，没有则新建房间"""
        self._lobby_lock.acquire()
        try:
            # Adding player to the first non-full public room
            for room in self._rooms:
                if not room.private:
                    try:
                        room.join(player)
                        return room
                    except FullGameRoomException:
                        pass

            # All rooms are full: creating new room
            room = self._room_factory.create_room(id=str(uuid4()), private=False, logger=self._logger)
            room.join(player)
            self._rooms.append(room)
            return room
        finally:
            self._lobby_lock.release()

    def _join_room(self, player: ConnectedPlayer) -> GameRoom:
        """
        根据ConnectedPlayer中记录的PlayerServer 和 room_id信息判断加入的房间类型
        """
        if player.room_id is None:
            self._logger.info("Player {}: joining public room".format(player.player))
            return self._join_any_public_room(player.player)
        else:
            self._logger.info("Player {}: joining private room {}".format(player.player.name, player.room_id))
            return self._join_private_room(player.player, player.room_id)

    def start(self):
        """
        启动游戏服务器，激活房间并将大厅队列中的玩家加入到房间中
        """
        self._logger.info("{}: running".format(self))
        self.on_start()
        try:
            # 遍历大厅中玩家， new_players是一个迭代器持续读取大厅中新加入的玩家
            for player in self.new_players():
                # Player successfully connected: joining the lobby
                self._logger.info("{}: {} connected".format(self, player.player.name))
                try:
                    # player: ConnectedPlayer(包含PlayerServer和room_id)，加入private还是public房间，将player加入到指定房间并返回GameRoom
                    room = self._join_room(player)  # 此时玩家在GameRoom的_room_players中
                    self._logger.info("Room: {}".format(room.id))
                    if not room.active:
                        # 第一个加入房间的玩家同时激活房间状态，启动一个协程来维持房间状态
                        room.active = True
                        gevent.spawn(room.activate)
                except:
                    # Close bad connections and ignore the connection
                    self._logger.exception("{}: bad connection".format(self))
                    pass
        finally:
            self._logger.info("{}: terminating".format(self))
            self.on_shutdown()

    def on_start(self):
        pass

    def on_shutdown(self):
        pass
