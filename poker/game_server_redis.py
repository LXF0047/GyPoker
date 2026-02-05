import time
from typing import Generator

from redis import Redis

import gevent

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
        self._room_control_queue = MessageQueue(redis, "texas-holdem-poker:room-control")

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

    def on_start(self):
        gevent.spawn(self._room_control_loop)

    def _room_control_loop(self):
        while True:
            try:
                message = self._room_control_queue.pop()
            except (ChannelError, MessageTimeout, MessageFormatError) as e:
                self._logger.error("Room control queue error: {}".format(e.args[0]))
                continue

            if not isinstance(message, dict):
                continue

            if message.get("message_type") != "room-control":
                continue

            room_id = message.get("room_id")
            action = message.get("action")
            requester_id = message.get("requester_id")
            self._logger.info("Room control message: action=%s room=%s requester=%s seat=%s bot=%s diff=%s",
                              action, room_id, requester_id, message.get("seat_index"), message.get("bot_id"), message.get("difficulty"))
            if not room_id or not action or not requester_id:
                continue

            room = self.get_room_by_id(room_id)
            if not room:
                self._logger.warning("Room control: room not found %s", room_id)
                continue

            if action == "add-bot":
                seat_index = message.get("seat_index")
                if seat_index is None:
                    continue
                difficulty = message.get("difficulty") or "easy"
                ok, result = room.add_bot(requester_id, int(seat_index), difficulty)
                self._logger.info("Room control add-bot result: ok=%s result=%s", ok, result)
                if not ok:
                    try:
                        player = room._room_players.get_player(requester_id)
                        player.try_send_message({"message_type": "error", "error": result})
                    except Exception:
                        pass
            elif action == "remove-bot":
                seat_index = message.get("seat_index")
                bot_id = message.get("bot_id")
                ok, result = room.remove_bot(requester_id, bot_id=bot_id, seat_index=seat_index)
                self._logger.info("Room control remove-bot result: ok=%s result=%s", ok, result)
                if not ok:
                    try:
                        player = room._room_players.get_player(requester_id)
                        player.try_send_message({"message_type": "error", "error": result})
                    except Exception:
                        pass
