"""`astrbot.api.event` 的最小 stub：消息事件与装饰器注册器。"""

from __future__ import annotations

from typing import Any, Callable, Optional


class AstrMessageEvent:
    """只实现插件实际读取的四个成员。"""

    def __init__(self, message_str: str = "", umo: str = "test:FriendMessage:1",
                 sender_id: str = "1") -> None:
        self.message_str = message_str
        self.unified_msg_origin = umo
        self._sender_id = sender_id
        self.sent: list[Any] = []

    def get_sender_id(self) -> str:
        return self._sender_id

    def plain_result(self, text: str) -> Any:
        self.sent.append(text)
        return ("plain", text)


class _Filter:
    """装饰器注册器。真实实现会把函数登记到元数据里，stub 只原样返回。"""

    def _passthrough(self, *_a: Any, **_k: Any) -> Callable:
        def deco(fn: Callable) -> Callable:
            return fn

        return deco

    def on_llm_request(self, *_a: Any, **_k: Any) -> Callable:
        return self._passthrough()

    def on_llm_response(self, *_a: Any, **_k: Any) -> Callable:
        return self._passthrough()

    def command(self, *_a: Any, **_k: Any) -> Callable:
        return self._passthrough()

    def llm_tool(self, *_a: Any, **_k: Any) -> Callable:
        return self._passthrough()

    def event_message_type(self, *_a: Any, **_k: Any) -> Callable:
        return self._passthrough()


filter = _Filter()

__all__ = ["AstrMessageEvent", "filter", "Optional"]
