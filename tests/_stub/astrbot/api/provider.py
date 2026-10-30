"""`astrbot.api.provider` 的最小 stub：ProviderRequest 容器。"""

from __future__ import annotations

from typing import Any, List


class ProviderRequest:
    """插件会读写的字段：prompt / system_prompt / contexts / extra_user_content_parts。"""

    def __init__(self, prompt: str = "", system_prompt: str = "") -> None:
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.contexts: List[Any] = []
        self.extra_user_content_parts: List[Any] = []
