"""physio：全生理指标模拟。

与 psyche 并列的第二套模型：
  psyche 管神经递质、环路与精神症状；
  physio 管器官功能、检验指标、疾病与药物。

两者通过 Physiology.couple() 单向耦合，physio 改 psyche 的四个共享量，
反向不写，避免任何一边调参时把另一边带崩。

用法：
    from physio import Physiology, new_body, report
    phys = Physiology(cfg)
    phys.step(body)              # 推进一轮（默认 6 小时）
    report.render_summary(body)  # 人看的摘要
"""

from __future__ import annotations

from .body import (PRESETS, add_condition, alive_conditions, condition_codes,
                   ensure_body, new_body, remove_condition, summary_line)
from .const import ENV, LABS, LIFE, ORGANS, PANELS, VITALS, ref_range
from .diseases import DISEASES
from .drugs import DRUGS
from .engine import Physiology
from . import report

__all__ = [
    "Physiology", "new_body", "ensure_body", "alive_conditions",
    "condition_codes", "add_condition", "remove_condition", "summary_line",
    "PRESETS", "LABS", "VITALS", "ORGANS", "LIFE", "ENV", "PANELS",
    "DISEASES", "DRUGS", "report", "ref_range",
]
