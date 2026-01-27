import logging
import time
from typing import Any, Optional

from .channel import MessageFormatError, ChannelError, MessageTimeout, Channel, ChannelClosed
from .player import Player


class PlayerServer(Player):
    def __init__(self, channel: Channel, logger, *args, **kwargs):
        Player.__init__(self, *args, **kwargs)
        self._channel: Channel = channel
        self._connected: bool = True
        self.wants_to_start_final_10_hands: bool = False
        self._logger = logger if logger else logging

    def disconnect(self):
        """Disconnect the client"""
        if self._connected:
            self.try_send_message({"message_type": "disconnect"})
            self._channel.close()
            self._connected = False

    @property
    def channel(self) -> Channel:
        return self._channel

    @property
    def connected(self) -> bool:
        return self._connected

    def update_channel(self, new_player):
        old_channel = self._channel
        try:
            old_channel.send_message({"message_type": "disconnect"})
        except ChannelError:
            pass

        self._channel = new_player.channel
        self._connected = new_player.connected
        
        old_channel.close()
        # 注意：重连时不应该从数据库同步数据，因为：
        # 1. 游戏进行中，内存中的筹码值是最新的（包含了下注等变化）
        # 2. 数据库只在游戏结束后才更新
        # 3. 如果从数据库同步，会用旧值覆盖内存中的正确值，导致筹码不一致

    def ping(self) -> bool:
        try:
            self.send_message({"message_type": "ping"})
            # 增加 ping 超时时间到 5 秒，给网络不稳定的玩家更多响应时间
            message = self.recv_message(timeout_epoch=time.time() + 5)
            MessageFormatError.validate_message_type(message, expected="pong")
            if "ready" in message:
                self._ready = bool(message["ready"])
            if "start_final_10_hands" in message:
                self.wants_to_start_final_10_hands = bool(message["start_final_10_hands"])
            return True
        except (ChannelError, MessageTimeout, MessageFormatError) as e:
            # 降低日志级别，ping超时是正常的重连场景
            self._logger.info("Player {} disconnected during ping: {}".format(self, e))
            self.disconnect()
            return False

    def update_ready_state(self):
        pass

    def try_send_message(self, message: Any) -> bool:
        try:
            self.send_message(message)
            return True
        except ChannelError:
            return False

    def send_message(self, message: Any):
        # 从O队列的左端推入消息   O队列   msg5 ---> [msg4, msg3, msg2, msg1]
        return self._channel.send_message(message)

    def recv_message(self, timeout_epoch: Optional[float] = None) -> Any:
        # I队列   [msg5, msg4, msg3, msg2] ---> msg1
        while True:
            current_channel = self._channel
            try:
                message = current_channel.recv_message(timeout_epoch)
                if "message_type" in message and message["message_type"] == "disconnect":
                    raise ChannelError("Client disconnected")
                return message
            except ChannelClosed:
                if self._channel is not current_channel:
                    # Channel updated, retry with new channel
                    continue
                raise ChannelError("Client disconnected")
