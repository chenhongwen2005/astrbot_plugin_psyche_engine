"""`astrbot.api.star` 的最小 stub。"""

from __future__ import annotations

from typing import Any, Optional


class Context:
    """AstrBot 上下文。插件只调用 get_using_provider_async。"""

    def __init__(self) -> None:
        self.provider: Optional[Any] = None

    async def get_using_provider_async(self, umo: str = "", **_k: Any) -> Optional[Any]:
        return self.provider

    def get_config(self, **_k: Any) -> dict:
        return {}


class Star:
    """插件基类。"""

    def __init__(self, context: Optional[Context] = None) -> None:
        self.context = context if context is not None else Context()

    async def terminate(self) -> None:
        return None
