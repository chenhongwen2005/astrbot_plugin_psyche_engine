"""`astrbot.core.agent.message` 的最小 stub：TextPart。"""

from __future__ import annotations

from typing import Any


class TextPart:
    """用户消息中的一段文本。真实实现还带 type / _no_save 等字段。"""

    def __init__(self, text: str = "", type: str = "text", **_k: Any) -> None:
        self.text = text
        self.type = type
        self._is_temp = False

    def mark_as_temp(self) -> "TextPart":
        """标记为临时内容，不写入历史、不参与缓存。"""
        self._is_temp = True
        return self

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"TextPart(len={len(self.text)}, temp={self._is_temp})"
