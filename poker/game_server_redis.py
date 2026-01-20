import time
from typing import Generator

from redis import Redis

from .game_room import GameRoomFactory
from .channel_redis import MessageQueue, ChannelRedis, ChannelError, MessageFormatError, MessageTimeout
from .game_server import GameServer, ConnectedPlayer
from .player_server import PlayerServer


class GameServerRedis(GameServer):
    """

    """
    def __init__(self, redis: Redis, connection_channel: str, room_factory: GameRoomFactory, logger=None):
        """
        connection_channel: "texas-holdem-poker:lobby"
        """
        GameServer.__init__(self, room_factory, logger)
        self._redis: Redis = redis
        self._connection_queue = MessageQueue(redis, connection_channel)  # 游戏大厅队列

    def _connect_player(self, message) -> ConnectedPlayer:
        """
        从message中提取关键信息来新建PlayerServer
        """
        # 检测是否超时
        try:
            timeout_epoch = int(message["timeout_epoch"])
        except KeyError:
            raise MessageFormatError(attribute="timeout_epoch", desc="Missing attribute")
        except ValueError:
            raise MessageFormatError(attribute="timeout_epoch", desc="Invalid session id")

        if timeout_epoch < time.time():
            raise MessageTimeout("Connection timeout")

        # 检测 session_id
        try:
            session_id = str(message["session_id"])
        except KeyError:
            raise MessageFormatError(attribute="session", desc="Missing attribute")
        except ValueError:
            raise MessageFormatError(attribute="session", desc="Invalid session id")

        # 提取玩家属性
        # player id
        try:
            player_id = str(message["player"]["id"])
        except KeyError:
            raise MessageFormatError(attribute="player.id", desc="Missing attribute")
        except ValueError:
            raise MessageFormatError(attribute="player.id", desc="Invalid player id")
        # player name
        try:
            player_name = str(message["player"]["name"])
        except KeyError:
            raise MessageFormatError(attribute="player.name", desc="Missing attribute")
        except ValueError:
            raise MessageFormatError(attribute="player.name", desc="Invalid player name")
        # player money
        try:
            player_money = float(message["player"]["money"])
        except KeyError:
            raise MessageFormatError(attribute="player.money", desc="Missing attribute")
        except ValueError:
            raise MessageFormatError(attribute="player.money",
                                     desc="'{}' is not a number".format(message["player"]["money"]))
        # player loan (loan是借款次数，应该是整数)
        try:
            player_loan = int(message["player"]["loan"])
        except KeyError:
            raise MessageFormatError(attribute="player.loan", desc="Missing attribute")
        except ValueError:
            raise MessageFormatError(attribute="player.loan",
                                     desc="'{}' is not a valid integer".format(message["player"]["loan"]))
        # player avatar
        try:
            player_avatar = message["player"].get("avatar")
            # 如果头像数据过大，截断或置空 (50KB limit)
            if player_avatar and len(player_avatar) > 50000:
                player_avatar = None
        except KeyError:
            player_avatar = None

        # room id
        try:
            game_room_id = str(message["room_id"])
        except KeyError:
            game_room_id = None
        except ValueError:
            raise MessageFormatError(attribute="room_id", desc="Invalid room id")

        player = PlayerServer(
            channel=ChannelRedis(
                self._redis,
                "poker5:player-{}:session-{}:I".format(player_id, session_id),
                "poker5:player-{}:session-{}:O".format(player_id, session_id)
            ),
            logger=self._logger,
            id=player_id,
            name=player_name,
            money=player_money,
            loan=player_loan,
            avatar=player_avatar,
            ready=False
        )

        # Acknowledging the connection
        # O队列左端推入消息（在PlayerClientConnector连接时读取连接确认信息）
        player.send_message({
            "message_type": "connect",
            "server_id": self._id,
            "player": player.dto()
        })

        return ConnectedPlayer(player=player, room_id=game_room_id)

    def new_players(self) -> Generator[ConnectedPlayer, None, None]:
        while True:
            try:
                # 将大厅队列中的玩家依次建立连接返回ConnectedPlayer(记录了PlayerServer,room_id信息)
                yield self._connect_player(self._connection_queue.pop())
            except (ChannelError, MessageTimeout, MessageFormatError) as e:
                self._logger.error("Unable to connect the player: {}".format(e.args[0]))
