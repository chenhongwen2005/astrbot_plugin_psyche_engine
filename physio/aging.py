"""衰老：让时间真的在一个人身上留下痕迹。

为什么单独一个模块
    疾病目录里已经有老视、老年性耳聋、白内障、骨质疏松、肌少症，但它们
    走的是「按月抽签」那条路：base 平摊在每一岁上，结果二十五岁也能抽到
    骨质疏松，而真正该出现它们的六十岁反而未必抽得中。

    衰老不是抽签，是日程。每个人都会老花，只是早晚差几年；绝大多数人
    六十岁以后听力会掉、骨量会走。所以这里不用概率，用一张带个体差异的
    时间表：出生时就把「这个人大概哪一年老花」定下来，到点就发生。

    年龄本身也真的会走。原来跑五年模拟，角色从七十八岁跑到七十八岁，
    体检报告上写着「78 岁」，五年后还是「78 岁」——那不是人，那是一张
    照片。

体能天花板
    成年之后体能的**上限**随年龄下降，这和「最近有没有锻炼」是两件事。
    一个七十岁的人可以练得很勤，但他练不到二十五岁的水平。所以这里
    给 fitness 加一个随年龄下降的封顶，锻炼只能在封顶之下往上补。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from . import body as B
from .diseases import DISEASES

# (代码, 男性最早, 男性最晚, 女性最早, 女性最晚)
# 女性绝经后骨量掉得快，骨质疏松比男性早十年左右，这是流行病学上
# 最稳定的一条性别差异，不写进来反而奇怪。
SCHEDULE: Tuple[Tuple[str, float, float, float, float], ...] = (
    ("EYE-PRESBYOPIA", 42.0, 50.0, 40.0, 48.0),   # 老视：四十岁后看近处要拿远
    ("EN-PRESBYCUSIS", 58.0, 72.0, 55.0, 70.0),   # 老年性耳聋
    ("EN-OSTEOPOR", 64.0, 80.0, 55.0, 70.0),      # 骨质疏松
    ("EY-CATARACT", 62.0, 78.0, 60.0, 76.0),      # 白内障
    ("MS-SARCOPENIA", 66.0, 80.0, 64.0, 78.0),    # 肌少症
)


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def fitness_cap(age: float) -> float:
    """体能的年龄上限。三十岁封顶 1.0，之后每十年掉一截。"""
    a = max(0.0, float(age) - 30.0)
    if a <= 0:
        return 1.0
    # 30→1.00，50→0.86，70→0.66，85→0.50
    return _clip(1.0 - a * 0.0043 - a * a * 0.00006, 0.42, 1.0)


def new_plan(body: Dict[str, Any]) -> Dict[str, float]:
    """出生（或首次进入模拟）时把这一生的衰老日程排好。"""
    rng = B.rng_for(body, salt=53)
    female = (body.get("sex") or "m") == "f"
    plan: Dict[str, float] = {}
    for code, m0, m1, f0, f1 in SCHEDULE:
        lo, hi = (f0, f1) if female else (m0, m1)
        plan[code] = round(rng.uniform(lo, hi), 1)
    return plan


def ensure(body: Dict[str, Any]) -> Dict[str, Any]:
    st = body.get("aging")
    if not isinstance(st, dict):
        st = {"plan": new_plan(body), "done": []}
        body["aging"] = st
    st.setdefault("plan", new_plan(body))
    st.setdefault("done", [])
    return st


def _has(body: Dict[str, Any], code: str) -> bool:
    return any(c.get("code") == code for c in (body.get("conditions") or []))


def step(body: Dict[str, Any], hours: float, events: List[str]) -> None:
    """推进年龄，到点就落一条衰老相关的改变。"""
    if hours <= 0:
        return
    years = float(hours) / (24.0 * 365.25)
    before = float(body.get("age", 30.0) or 30.0)
    body["age"] = round(before + years, 5)

    # 体能的年龄天花板。只往下压，不往上抬——锻炼归 _exercise 管，
    # 这里只负责「再怎么练也练不回去」的那部分。
    act = float((body.get("life") or {}).get("fitness", 0.5) or 0.5)
    cap = fitness_cap(body["age"])
    if act > cap and not B.locked(body, "fitness"):
        # 先平滑趋近，再硬封顶。只做平滑是不够的：锻炼每次加 0.004，
        # 而每轮的老化扣减正比于「超出量×极小的时间比例」，两者相抵之后
        # 体能会永远停在 1.0，六十岁的人和二十五岁一样能跑——封顶就得
        # 真的是封顶。
        rate = 1.0 - math.exp(-years / 3.0)
        body["life"]["fitness"] = min(round(act - (act - cap) * rate, 4), cap)

    st = ensure(body)
    plan = st.get("plan") or {}
    done = st.get("done") or []
    for code, when in plan.items():
        if code in done or body["age"] < float(when):
            continue
        spec = DISEASES.get(code)
        if not spec or _has(body, code):
            st["done"] = done + [code]
            continue
        item = B.add_condition(body, code, spec["zh"], sev=0.05,
                               note=spec.get("note", ""))
        item["treat_effect"] = 0.0
        B.push_log(body, f"身体开始有{spec['zh']}的样子", "aging")
        events.append(f"aging:{spec['zh']}")
        st["done"] = done + [code]
        done = st["done"]


# ----------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------
def stage(age: float) -> str:
    if age < 3:
        return "婴幼儿"
    if age < 13:
        return "儿童"
    if age < 18:
        return "少年"
    if age < 30:
        return "青年"
    if age < 41:
        return "壮年"
    if age < 56:
        return "中年"
    if age < 66:
        return "中老年"
    if age < 80:
        return "老年"
    return "高龄"


def line(body: Dict[str, Any]) -> str:
    """报告里的年龄一行。

    不写「刚过 42 岁」这种播报——没人每句话都提自己几岁。只在报告里
    给出年龄段，因为年龄段才是可用的信息：「中年」和「高龄」对应完全
    不同的说话方式，而 47 和 48 之间没有区别。
    """
    age = float(body.get("age", 30.0) or 30.0)
    return f"{int(age)} 岁（{stage(age)}）"
