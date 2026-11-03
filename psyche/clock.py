"""时间来源：虚拟时钟与真实北京时间。

为什么要有这一层
    虚拟时钟每轮固定推进 hours_per_turn（默认 6 小时），四轮就是一天。好处是
    几十轮就能观察到「熬夜一周」的后果；代价是角色活在一条自转的时间轴上——
    凌晨两点找它，它不知道「现在很晚」，也不会说「你该睡了」；中午第一句话，
    它可能刚睡醒。真实时钟模式解决这个：时钟按真实流逝推进，hour_of_day 就是
    北京的钟点。代价是短促对话几乎不推进生理时间——这本身是对的，人不会因为
    聊了五十句话而累。

北京时间怎么算
    中国不实行夏令时，UTC+8 是固定偏移，所以直接写 timedelta(hours=8)。
    不用 zoneinfo：它在 Windows 上依赖 tzdata 包，AstrBot 环境不一定有，
    一个 ImportError 会把整个插件拖垮，而这里根本不需要时区数据库。

一个容易踩的坑
    离线三天后再启动，real 模式会把 72 小时一次性喂给生理循环。所以推进量
    有上限；而且**钳制之后必须重设 epoch**，否则真实时间永远领先时钟，
    每一轮都在补那笔永远补不完的账，角色会持续处在「时间被压缩」的状态。
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

BJ = timezone(timedelta(hours=8), "Asia/Shanghai")

# 单次推进上限：三天。再长的离线不该逐小时回放，重设 epoch 直接跳过。
MAX_GAP_H = 72.0


def now_ts() -> float:
    return time.time()


def now_bj() -> datetime:
    return bj_from_ts(now_ts())


def bj_from_ts(ts: float) -> datetime:
    return datetime.fromtimestamp(float(ts), BJ)


def bj_hour_at(ts: float) -> float:
    """给定时间戳，北京是几点（0~24 浮点）。

    刻意做成「时间戳进、钟点出」的纯函数：sync_clock 里若先取一次
    time.time() 再单独读一次 datetime.now()，两次调用之间会漏掉毫秒，
    相位对齐就永远差一点点，几百轮之后累积成分钟级的漂移。
    """
    d = bj_from_ts(ts)
    return d.hour + d.minute / 60.0 + d.second / 3600.0


def bj_hour_float() -> float:
    """此刻是北京的几点（0~24 的浮点）。"""
    return bj_hour_at(now_ts())


def bj_date_str() -> str:
    return now_bj().strftime("%Y-%m-%d")


def day_of_year_at(ts: float) -> int:
    return int(bj_from_ts(ts).strftime("%j"))


def day_of_year() -> int:
    return day_of_year_at(now_ts())


def is_real(mode: Any) -> bool:
    return str(mode or "").strip().lower() in ("real", "true", "1", "北京时间", "wall")


# ----------------------------------------------------------------------
# 时钟同步
# ----------------------------------------------------------------------
def sync_clock(body: Dict[str, Any], mode: Any,
               hours_per_turn: float = 6.0) -> float:
    """把 body.clock 对齐到真实时间，返回本轮应推进的小时数。

    virtual 模式不做任何事，调用方沿用 hours_per_turn。
    real 模式返回「距上次同步真实过去了多少小时」，并把 clock 的日内相位
    锁在北京钟点上。
    """
    if not is_real(mode):
        return 0.0

    now = now_ts()
    clock = float(body.get("clock", 0.0) or 0.0)
    epoch = body.get("clock_epoch")

    if epoch is None:
        # 首次切到真实时钟：只平移日内相位，不回退总量。
        # 回退会让所有疾病的 onset、记忆的时间戳变成「未来」。
        target_h = bj_hour_float()
        delta = (target_h - (clock % 24.0)) % 24.0
        if delta > 0:
            body["clock"] = clock + delta
        body["clock_epoch"] = now - float(body["clock"]) * 3600.0
        body["clock_mode"] = "real"
        return 0.0

    try:
        epoch = float(epoch)
    except (TypeError, ValueError):
        body["clock_epoch"] = now - clock * 3600.0
        return 0.0

    elapsed = (now - epoch) / 3600.0 - clock
    if elapsed <= 0:
        # 系统时间被往回调过。不倒退，也不推进。
        return 0.0

    if elapsed > MAX_GAP_H:
        # 离线太久：只补三天，然后把 epoch 推到「现在」，从此重新对齐。
        body["clock"] = clock + MAX_GAP_H
        body["clock_epoch"] = now - float(body["clock"]) * 3600.0
        return MAX_GAP_H

    return elapsed


def clock_now(body: Dict[str, Any]) -> float:
    """该身体当前应有的时钟值（不做推进，只读）。"""
    epoch = body.get("clock_epoch")
    if epoch is None:
        return float(body.get("clock", 0.0) or 0.0)
    try:
        return max(float(body.get("clock", 0.0) or 0.0),
                   (now_ts() - float(epoch)) / 3600.0)
    except (TypeError, ValueError):
        return float(body.get("clock", 0.0) or 0.0)


def phase_of(clock: float) -> float:
    """clock 对应的日内钟点，0~24。"""
    return float(clock) % 24.0


def day_index(clock: float) -> int:
    return int(math.floor(float(clock) / 24.0))


def describe(body: Dict[str, Any], mode: Any) -> str:
    """一句话说明当前时间来源，给 /心理 状态 与调试用。"""
    if is_real(mode):
        return f"真实北京时间 {now_bj().strftime('%m-%d %H:%M')}"
    h = phase_of(float(body.get("clock", 0.0) or 0.0))
    d = day_index(float(body.get("clock", 0.0) or 0.0)) + 1
    return f"虚拟时间 第 {d} 天 {int(h):02d}:{int((h % 1) * 60):02d}"
