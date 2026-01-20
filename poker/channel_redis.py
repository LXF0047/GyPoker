import json
import signal
import time
from typing import Optional, Any

import gevent
from redis import exceptions, Redis

from .channel import Channel, MessageFormatError, MessageTimeout, ChannelError, ChannelClosed


class MessageQueue:
    """
    基于 Redis 列表实现的消息队列。
    """
    def __init__(self, redis: Redis, queue_name: str, expire: int = 300):
        self._redis: Redis = redis
        self._queue_name: str = queue_name
        self._expire: int = expire  # 过期时间
        self._active: bool = True

    @property
    def name(self):
        return self._queue_name

    def close(self):
        self._active = False

    def push(self, message: Any):
        msg_serialized = json.dumps(message)
        msg_encoded = msg_serialized.encode("utf-8")
        try:
            self._redis.lpush(self._queue_name, msg_encoded)  # 推入队列左端
            self._redis.expire(self._queue_name, self._expire)  # 设置队列过期时间
        except exceptions.RedisError as e:
            raise ChannelError(e.args[0])

    def pop(self, timeout_epoch: Optional[float] = None) -> Any:
        while timeout_epoch is None or time.time() < timeout_epoch:
            if not self._active:
                raise ChannelClosed("Queue closed")
            try:
                response = self._redis.rpop(self._queue_name)  # 从队列右端弹出消息
                if response is not None:
                    try:
                        # Deserialize and return the message
                        return json.loads(response)
                    except ValueError:
                        # Invalid json
                        raise MessageFormatError(desc="Unable to decode the JSON message")
                else:
                    # Context switching
                    gevent.sleep(0.01)
            except exceptions.RedisError as ex:
                raise ChannelError(ex.args[0])
        raise MessageTimeout("Timed out")


class ChannelRedis(Channel):
    """
    connect时channel_in的输入为O队列，channel_out的输入为I队列
    PlayerServer中传入的channel_in为I队列，channel_out为O队列

    PlayerClientConnector和PlayerClient中（新连接时）：
    recv_message是从O队列的右端弹出消息   O队列   [msg5, msg4, msg3, msg2] ---> msg1
    send_message是从I队列的左端推入消息   I队列   msg5 ---> [msg4, msg3, msg2, msg1]
    PlayerServer中
    send_message是从O队列的左端推入消息   O队列   msg5 ---> [msg4, msg3, msg2, msg1]
    recv_message是从I队列的右端弹出消息   I队列   [msg5, msg4, msg3, msg2] ---> msg1
    """
    def __init__(self, redis: Redis, channel_in: str, channel_out: str):
        self._queue_in = MessageQueue(redis, channel_in)
        self._queue_out = MessageQueue(redis, channel_out)

    def send_message(self, message: Any):
        # 左入
        self._queue_out.push(message)

    def recv_message(self, timeout_epoch: Optional[float] = None) -> Any:
        # 右出
        return self._queue_in.pop(timeout_epoch)

    def close(self):
        self._queue_in.close()
        self._queue_out.close()
