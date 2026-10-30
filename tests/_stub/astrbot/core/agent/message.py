"""`astrbot.core.agent.message` 的最小 stub：TextPart。"""

from __future__ import annotations

from typing import Any


class TextPart:
    """用户消息中的一段文本。

    真实实现是 pydantic 模型，临时标记字段名是私有属性 ``_no_save``
    （由 ContentPart.mark_as_temp 置位，model_dump_for_context 时带出）。
    stub 必须沿用同一个名字，否则本地测试绿了而真实语义对不上。
    """

    def __init__(self, text: str = "", type: str = "text", **_k: Any) -> None:
        self.text = text
        self.type = type
        self._no_save = False

    def mark_as_temp(self) -> "TextPart":
        """标记为仅面向 provider，不写入历史（真实实现的 docstring 原文）。"""
        self._no_save = True
        return self

    def model_dump_for_context(self) -> dict:
        data = {"type": self.type, "text": self.text}
        if self._no_save:
            data["_no_save"] = True
        return data

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"TextPart(len={len(self.text)}, no_save={self._no_save})"
