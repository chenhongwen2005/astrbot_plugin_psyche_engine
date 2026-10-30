"""`astrbot.api` 的最小 stub。"""

from __future__ import annotations

from typing import Any, Dict


class AstrBotConfig(Dict[str, Any]):
    """插件配置。真实实现是带 save_config 的 dict 子类。"""

    def save_config(self) -> None:  # noqa: D102 - stub
        pass


class _StubLogger:
    def __getattr__(self, _name: str):
        def _noop(*_a, **_k) -> None:
            return None

        return _noop


logger = _StubLogger()
