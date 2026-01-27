import time
from typing import Any, Optional

from redis import Redis

from .player import Player
from .channel import MessageFormatError, Channel
from .channel_redis import ChannelRedis, MessageQueue


class PlayerClient:
    def __init__(self, player: Player, connection_message: Any, server_channel: Channel):
        self._player: Player = player
        self._connection_message: Any = connection_message
        self._server_channel: Channel = server_channel

    @property
    def connection_message(self):
        return self._connection_message

    @property
    def player(self) -> Player:
        return self._player

    def send_message(self, message: Any):
        #
        self._server_channel.send_message(message)

    def recv_message(self, timeout_epoch: Optional[float] = None) -> Any:
        # 从O队列的右端弹出消息   O队列   [msg5, msg4, msg3, msg2] ---> msg1
        return self._server_channel.recv_message(timeout_epoch)

    def close(self):
        self._server_channel.close()


class PlayerClientConnector:
    """
    向大厅发送连接消息并返回玩家客户端
    """
    CONNECTION_TIMEOUT = 30

    def __init__(self, redis: Redis, connection_channel: str, logger):
        """

        :param redis: redis数据库
        :param connection_channel: 游戏类型, texas holdem或normal
        :param logger:
        """
        self._redis = redis
        self._connection_queue = MessageQueue(redis, connection_channel)  # redis消息队列
        self._logger = logger

    def connect(self, player: Player, session_id: str, room_id: str) -> PlayerClient:
        # Requesting new connection
        # 在texas-holdem-poker:lobby中添加新连接玩家信息
        # 玩家链接信息发送到lobby中
        self._connection_queue.push(
            {
                "message_type": "connect",
                "timeout_epoch": time.time() + PlayerClientConnector.CONNECTION_TIMEOUT,
                "player": {
                    "id": player.id,
                    "name": player.name,
                    "money": player.money,
                    "avatar": player.avatar,
                },
                "session_id": session_id,
                "room_id": room_id
            }
        )

        # 在redis中新建该用户的消息发送和读取队列
        server_channel = ChannelRedis(
            self._redis,
            "poker5:player-{}:session-{}:O".format(player.id, session_id),
            "poker5:player-{}:session-{}:I".format(player.id, session_id)
        )

        # 这里读取的是GameServerRedis建立时发送到O队列的连接信息
        # {
        #     "message_type": "connect",
        #     "server_id": self._id,
        #     "player": player.dto()
        # }
        connection_message = server_channel.recv_message(time.time() + PlayerClientConnector.CONNECTION_TIMEOUT)
        MessageFormatError.validate_message_type(connection_message, "connect")
        self._logger.info("{}: connected to server {}".format(player, connection_message["server_id"]))
        return PlayerClient(player, connection_message, server_channel)
