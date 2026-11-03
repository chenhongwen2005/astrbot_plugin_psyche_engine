"""过一天：把 24 小时压成一屏，用来看「这个人今天像不像活人」。

跑法：
    python tools/day_demo.py [seed]

为什么不看单元测试就够
    单测断言的是关系（渴了要渴、憋久了要上厕所），但看不出**节奏**：
    早上起来是不是真的口干、午饭后有没有起伏、傍晚精力是不是掉了、
    夜里睡着之后那些行有没有安静下来。这个脚本按小时摊开注入块，
    一眼就能看出哪里还像机器。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physio import body as B  # noqa: E402
from physio import report as R  # noqa: E402
from physio.engine import Physiology  # noqa: E402

# 内部事件码 → 人话。没列出来的原样打出来，方便发现漏掉的新事件。
EVENT_ZH = {
    "sleep_onset": "入睡",
    "wake": "醒",
    "night_wake": "夜醒",
    "exercise": "活动",
    "meal": "进食",
    "drink": "喝水",
    "toilet": "上厕所",
    "onset": "起病",
    "injury": "外伤",
    "aging": "又长一岁",
    "hangover": "宿醉",
}


def _hm(h: float) -> str:
    h = h % 24.0
    return f"{int(h):02d}:{int(round((h - int(h)) * 60)) % 60:02d}"


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 20261103
    body = B.new_body(sex="m", age=31.0, seed=seed)
    ph = Physiology({"hours_per_turn": 1.0, "enable_onset": True})

    print(f"seed={seed}  起点 {_hm(float(body.get('clock', 0.0)))}")
    print("=" * 78)
    for _ in range(24):
        res = ph.step(body, hours=1.0)
        now = float(body.get("clock", 0.0))
        block = R.render_block_section(body, max_chars=400)
        print(f"\n[{_hm(now)}] {block}")
        evs = [EVENT_ZH.get(e, e) for e in (res.get("events") or [])]
        if evs:
            print(f"        （{ '、'.join(evs) }）")
        if res.get("dead"):
            print("        （角色已死亡）")
            break


if __name__ == "__main__":
    main()
