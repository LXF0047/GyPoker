from typing import Any, Optional

from ..channel import Channel, MessageTimeout


class BotChannel(Channel):
    def recv_message(self, timeout_epoch: Optional[float] = None) -> Any:
        raise MessageTimeout("Bot channel does not receive messages")

    def send_message(self, message: Any):
        return None
