"""`astrbot.core.utils.astrbot_path` 的最小 stub。"""

from __future__ import annotations

import os
import tempfile


def get_astrbot_data_path() -> str:
    """真实实现返回 AstrBot 的 data 目录；stub 用临时目录，避免污染。"""
    p = os.path.join(tempfile.gettempdir(), "astrbot_stub_data")
    os.makedirs(p, exist_ok=True)
    return p
