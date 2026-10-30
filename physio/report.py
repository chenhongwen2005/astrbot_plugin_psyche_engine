"""体检报告与注入块的生理段渲染。

两条硬规则，写在这里而不是散落在调用处：

1. **只描述此刻的事实，不给预后。** 报告里不会出现生存期、死亡率、治愈率
   这类数字——那既不是模拟该输出的东西，也容易被当成医学结论。
2. **每份完整报告都带声明。** 这是虚构角色的身体数据，不构成任何医学建议，
   也不能用来推断真人的健康状况。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from . import body as B
from .const import LABS, PANELS, VITALS, ref_range
from .diseases import DISEASES

DISCLAIMER = ("以上是虚构角色的模拟数据，不是真实检查结果，"
              "不构成医学建议，也不能用于判断任何真人的健康状况。")

DIR_ZH = {"high": "↑", "low": "↓"}


def _fmt(v: float) -> str:
    if v == 0:
        return "0"
    if abs(v) >= 100:
        return f"{v:.0f}"
    if abs(v) >= 10:
        return f"{v:.1f}"
    if abs(v) >= 1:
        return f"{v:.2f}"
    return f"{v:.3f}"


def _vital_line(body: Dict[str, Any]) -> List[str]:
    vit = body.get("vitals") or {}
    order = ["TEMP", "HR", "SBP", "DBP", "RR", "SpO2", "WEIGHT", "BMI", "PAIN"]
    parts = []
    for k in order:
        if k not in vit:
            continue
        v = float(vit[k])
        ab, d = _abn(body, k, v)
        mark = DIR_ZH.get(d, "") if ab else ""
        if k in ("SBP", "DBP"):
            continue
        if k == "PAIN":
            if v < 1:
                continue
            parts.append(f"疼痛 {v:.0f}/10")
            continue
        unit = {k: v2[1] for k, v2 in VITALS.items()}.get(k, "")
        parts.append(f"{VITALS[k][0]} {_fmt(v)}{unit}{mark}")
    sbp, dbp = vit.get("SBP"), vit.get("DBP")
    if sbp and dbp:
        ab_s, d_s = _abn(body, "SBP", float(sbp))
        ab_d, d_d = _abn(body, "DBP", float(dbp))
        mk = DIR_ZH.get(d_s if ab_s else d_d, "") if (ab_s or ab_d) else ""
        parts.insert(2, f"血压 {float(sbp):.0f}/{float(dbp):.0f}mmHg{mk}")
    return parts


def _abn(body: Dict[str, Any], key: str, v: float) -> Tuple[bool, str]:
    from .labs import is_abnormal
    return is_abnormal(body, key, v)


def render_vitals(body: Dict[str, Any]) -> str:
    parts = _vital_line(body)
    return "　".join(parts) if parts else "未记录"


def render_panel(body: Dict[str, Any], panel: str) -> str:
    labs = body.get("labs") or {}
    vit = body.get("vitals") or {}
    keys = [k for k, m in LABS.items() if m[5] == panel]
    if panel == "生命体征":
        return render_vitals(body)
    if not keys:
        return ""
    lines = []
    for k in keys:
        if k not in labs:
            continue
        v = float(labs[k])
        lo, hi = ref_range(k, body.get("sex", "m"))
        ab, d = _abn(body, k, v)
        zh, unit = LABS[k][0], LABS[k][1]
        flag = DIR_ZH.get(d, "") if ab else ""
        rng = f"{_fmt(lo)}–{_fmt(hi)}"
        lines.append(f"{zh:<16s}{_fmt(v):>9s} {unit:<9s}{flag:<2s} 参考 {rng}")
    return "\n".join(lines)


def render_full(body: Dict[str, Any], only_abnormal: bool = False) -> str:
    body = B.ensure_body(body)
    out = [f"── 体检报告｜{B.summary_line(body)} ──",
           f"身高 {float(body.get('height', 0)):.0f}cm　体重 "
           f"{float((body.get('vitals') or {}).get('WEIGHT', 0)):.1f}kg　"
           f"BMI {float((body.get('vitals') or {}).get('BMI', 0)):.1f}"]
    out.append("")
    out.append("【生命体征】")
    out.append(render_vitals(body))
    panels = [p for p in PANELS if p[0] != "vitals"]
    for key, name in panels:
        text = render_panel(body, key)
        if not text:
            continue
        if only_abnormal:
            keep = []
            for ln in text.splitlines():
                if "↑" in ln or "↓" in ln:
                    keep.append(ln)
            if not keep:
                continue
            text = "\n".join(keep)
        out.append("")
        out.append(f"【{name}】")
        out.append(text)
    conds = render_conditions(body)
    if conds:
        out.append("")
        out.append("【当前问题】")
        out.append(conds)
    out.append("")
    out.append(DISCLAIMER)
    return "\n".join(out)


def render_conditions(body: Dict[str, Any]) -> str:
    conds = B.alive_conditions(body)
    if not conds:
        return ""
    lines = []
    for c in sorted(conds, key=lambda x: -float(x.get("sev", 0))):
        spec = DISEASES.get(c["code"]) or {}
        sev = float(c.get("sev", 0))
        lvl = ("轻" if sev < 0.25 else "中" if sev < 0.55 else "重")
        if sev >= 0.8 and float(spec.get("mortal", 0.0) or 0.0) > 0.004:
            lvl = "危重"
        days = (float(body.get("clock", 0)) - float(c.get("onset", 0))) / 24.0
        tr = "｜已用药" if c.get("treated") else ""
        lines.append(f"{c.get('zh', c['code'])}　{lvl}（{sev:.0%}）"
                     f"　第 {days + 1:.0f} 天{tr}")
    return "\n".join(lines)


def render_symptoms(body: Dict[str, Any]) -> str:
    d = body.get("derived") or {}
    sx = d.get("symptoms") or []
    if not sx:
        return "说不上有什么特别不舒服。"
    return "、".join(f"{s}" for s, v in sx[:8] if v > 0.15) or "说不上有什么特别不舒服。"


def render_summary(body: Dict[str, Any]) -> str:
    body = B.ensure_body(body)
    d = body.get("derived") or {}
    lines = [f"【生理】{B.summary_line(body)}"]
    lines.append("体征：" + render_vitals(body))
    sx = render_symptoms(body)
    lines.append("感受：" + sx)
    ab = d.get("abnormal") or []
    if ab:
        names = []
        for it in ab[:10]:
            zh = LABS[it["key"]][0] if it["key"] in LABS else VITALS.get(it["key"], (it["key"],))[0]
            names.append(f"{zh}{DIR_ZH.get(it['dir'], '')}")
        lines.append("异常项：" + "、".join(names))
    of = d.get("organ_failure") or []
    if of:
        lines.append("器官功能下降：" + "、".join(f"{n}（{v:.0%}）" for n, v in of[:5]))
    return "\n".join(lines)


def render_life(body: Dict[str, Any]) -> str:
    body = B.ensure_body(body)
    life = body.get("life") or {}
    env = body.get("env") or {}
    sleep_h = float(life.get("sleep_h", 7.5))
    debt = float(life.get("sleep_debt", 0.0))
    kcal = float(life.get("kcal", 1.0))
    lines = [
        f"作息：平均睡 {sleep_h:.1f} 小时，睡眠债 {debt:.1f} 小时，"
        f"质量 {float(life.get('sleep_qual', 0.8)):.0%}",
        f"饮食：热量 {kcal:.2f} 倍需要量，盐 {float(life.get('salt', 1)):.2f}，"
        f"糖 {float(life.get('sugar', 1)):.2f}，纤维 {float(life.get('fiber', 0.7)):.0%}",
        f"活动：体能 {float(life.get('fitness', 0.5)):.0%}，久坐 "
        f"{float(life.get('sedentary', 6)):.1f} 小时/日",
        f"习惯：吸烟 {float(life.get('smoking', 0)):.0f} 支/日，"
        f"饮酒 {float(life.get('alcohol', 0)):.1f} 标准杯/日，"
        f"水合 {float(life.get('water', 0.85)):.0%}",
        f"环境：{float(env.get('temp_c', 22)):.0f}℃，湿度 "
        f"{float(env.get('humidity', 55)):.0f}%，PM2.5 "
        f"{float(env.get('pm25', 25)):.0f}µg/m³，病原暴露 "
        f"{float(env.get('pathogen', 0.15)):.0%}",
    ]
    return "\n".join(lines)


def render_log(body: Dict[str, Any], limit: int = 12) -> str:
    rows = (body.get("log") or [])[-limit:]
    if not rows:
        return "暂无记录。"
    lines = []
    for r in rows:
        lines.append(f"第{r.get('d', 1)}天 {int(float(r.get('h', 0)) % 24):02d}:"
                     f"{int((float(r.get('h', 0)) % 1) * 60):02d}　{r.get('text')}")
    return "\n".join(lines)


def render_block_section(body: Dict[str, Any], max_chars: int = 420) -> str:
    """注入块用：只给"此刻身上什么感觉"，不给诊断名词堆砌。"""
    body = B.ensure_body(body)
    d = body.get("derived") or {}
    vit = body.get("vitals") or {}
    parts: List[str] = []

    sx = [s for s, v in (d.get("symptoms") or []) if v > 0.2]
    if sx:
        parts.append("身上：" + "、".join(sx[:6]))

    bits = []
    t = float(vit.get("TEMP", 36.6))
    if t >= 37.3:
        bits.append(f"发烧 {t:.1f}℃" if t < 38.5 else f"高热 {t:.1f}℃")
    hr = float(vit.get("HR", 72))
    if hr >= 100:
        bits.append("心跳快")
    elif hr <= 55:
        bits.append("心跳偏慢")
    spo2 = float(vit.get("SpO2", 98))
    if spo2 < 94:
        bits.append("喘不上气")
    pain = float(vit.get("PAIN", 0))
    if pain >= 4:
        bits.append("疼得厉害" if pain >= 7 else "一直在疼")
    if bits:
        parts.append("体征：" + "、".join(bits))

    if float(d.get("dysfunction", 0)) > 0.45:
        parts.append("整个人提不起劲，做什么都费劲")
    if not parts:
        parts.append("身上没什么特别的，状态还行")

    text = "；".join(parts)
    return text[:max_chars]
