"""长程与「慢变量」的回归自测：一年推演、慢性情绪、时差、体质漂移。

跑法：
    python tests/test_longterm.py

测什么
    这一批改动的共同点是**时间尺度**：按天结算、按天累积的慢性情绪、按天
    恢复的时差、按周漂移的体质。它们单独看都对，错的地方在于「短跑测不出
    来」——六小时一轮跑一百轮，一切正常；一次推一年，问题全在括号里。

    所以这里的断言都是长跑：一年之后病历里是不是堆着一排「刚起病」、连着
    丧二十天炎症有没有抬起来、飞八小时之后几点睡、练三年静息心率降不降。
"""

from __future__ import annotations

import os
import random
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physio import body as B  # noqa: E402
from physio import injury as INJ  # noqa: E402
from physio import intero as IO  # noqa: E402
from physio import mind as MD  # noqa: E402
from physio import rhythm as RY  # noqa: E402
from physio import sleep as SL  # noqa: E402
from physio import traits as TR  # noqa: E402
from physio.engine import Physiology  # noqa: E402
from psyche import narrative as NA  # noqa: E402

PASS = 0


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"[ok] {msg}")


def fail(msg: str) -> None:
    raise AssertionError(msg)


# ----------------------------------------------------------------------
# 1. 一次推一年：病历不能被堆在段末
# ----------------------------------------------------------------------
def test_year_run_keeps_record_sane() -> None:
    """一年一次性推完，不能攒出一排「刚起病」。

    原来的写法是整段跑完生活层，最后统一算一次病程与抽签：所有在年里发生
    的病都带着 sev=0.06 的初值落在段末，谁也不推进——第二年一开年，人身上
    挂着十几条「早期迹象」。按天结算之后，起病时间散布在全年，段末只有
    最近两天真的新发的那一两条。
    """
    e = Physiology({"physio_disease_onset": True})
    worst = 0
    detail = []
    t0 = time.time()
    for seed in (1, 7, 42, 99, 2026):
        b = B.new_body(seed=seed)
        e.step(b, 24 * 365)
        cond = b.get("conditions") or []
        clock = float(b.get("clock", 0.0))
        fresh = [c for c in cond
                 if float(c.get("sev", 0.0)) <= 0.11
                 and clock - float(c.get("onset", 0.0)) <= 48.0]
        worst = max(worst, len(fresh))
        detail.append(f"seed{seed}:{len(cond)}活/{len(fresh)}新")
        if len(cond) > 6:
            fail(f"seed={seed} 一年后挂着 {len(cond)} 条活动性疾病")
    spent = time.time() - t0
    if worst > 4:
        fail(f"段末仍有 {worst} 条「刚起病」：{' '.join(detail)}")
    if spent > 20.0:
        fail(f"五个 seed 各推一年用了 {spent:.1f} 秒，退回逐小时把大步长堵死了")
    ok(f"一年长跑病历不堆积（{' '.join(detail)}，{spent:.1f} 秒）")


def test_year_run_history_accumulates() -> None:
    """一年里该有几十条好转记录。整段只结算一次的话，病史是空的。"""
    e = Physiology({"physio_disease_onset": True})
    b = B.new_body(seed=42)
    e.step(b, 24 * 365)
    hist = b.get("history") or []
    if len(hist) < 20:
        fail(f"一年只留下 {len(hist)} 条病史，病程没有被逐日结算")
    ok(f"一年留下 {len(hist)} 条病史（起病与好转都按天记录）")


# ----------------------------------------------------------------------
# 2. 慢性情绪：连着丧要攒得起来，好起来要退得回去
# ----------------------------------------------------------------------
def _mood_run(days: int, emo: dict, seed: int = 5):
    b = B.new_body(seed=seed)
    b["clock"] = 0.0
    for _ in range(days * 4):
        MD.set_state(b, emo)
        b["clock"] += 6.0
        MD.step_chronic(b, 6.0)
    return b


def test_chronic_mood_settles_once() -> None:
    """同一段时间只记一次账。

    两个调用点（情绪更新、生理推进）都会结算「上一段心情」，靠 chr_at 去重。
    没有这个账本的话，同一段被记两遍，慢性值会平白高出一截，而且时钟停着
    反复调用会把值一路推到顶。
    """
    b = B.new_body(seed=5)
    b["clock"] = 0.0
    MD.set_state(b, {"sadness": 0.9})
    b["clock"] = 6.0
    MD.step_chronic(b, 6.0)
    c1 = MD.chronic(b)
    for _ in range(5):                      # 时钟没动，再喊五次不该有变化
        MD.step_chronic(b, 6.0)
    c2 = MD.chronic(b)
    if abs(c2 - c1) > 1e-6:
        fail(f"时钟停着反复推进，慢性值从 {c1:.3f} 爬到 {c2:.3f}，重复结算")
    if c1 <= 0.0:
        fail("六个小时的难过一点都没进慢性变量")
    ok(f"慢性情绪只结算一次（停表连推五次仍是 {c1:.3f}）")


def test_chronic_mood_accumulates() -> None:
    """连着二十天低落，慢性负荷要过 0.45，并且真的抬到化验单上。"""
    b = _mood_run(20, {"sadness": 0.8})
    c = MD.chronic(b)
    if c < 0.45:
        fail(f"二十天持续低落只攒到 {c:.3f}，够不到生理后果")

    e = Physiology({"physio_disease_onset": False})
    e.refresh(b)
    sad_cor = float(b["labs"].get("COR_8am", 0.0))
    sad_crp = float(b["labs"].get("hsCRP", 0.0))
    sad_hr = float(b["vitals"].get("HR", 0.0))

    calm = B.new_body(seed=5)
    calm["clock"] = float(b["clock"])
    e.refresh(calm)
    if sad_cor - float(calm["labs"].get("COR_8am", 0.0)) < 8.0:
        fail(f"慢性低落只把晨皮质醇抬了 {sad_cor - float(calm['labs'].get('COR_8am', 0.0)):.1f}")
    if sad_crp - float(calm["labs"].get("hsCRP", 0.0)) < 0.2:
        fail("慢性低落没有抬 hsCRP")
    if sad_hr - float(calm["vitals"].get("HR", 0.0)) < 0.5:
        fail("慢性低落没有抬静息心率")
    ok(f"二十天低落 chronic={c:.2f}（COR {sad_cor:.0f} vs {calm['labs'].get('COR_8am', 0):.0f}、"
       f"hsCRP {sad_crp:.2f}、HR {sad_hr:.1f}）")


def test_chronic_mood_fades() -> None:
    """心情好转之后要退回去，而且退得比上来慢。"""
    b = _mood_run(20, {"sadness": 0.8})
    peak = MD.chronic(b)
    for _ in range(20 * 4):
        MD.set_state(b, {"joy": 0.9})
        b["clock"] += 6.0
        MD.step_chronic(b, 6.0)
    c = MD.chronic(b)
    if c > 0.15:
        fail(f"好转二十天后慢性值还有 {c:.3f}")
    ok(f"慢性情绪会退（{peak:.2f} → {c:.3f}）")


def test_stale_mood_does_not_persist_forever() -> None:
    """说完一句就一个月不更新，那句话不能一直算数。

    心情按 τ=8 小时计平均：跨度拉到一个月，这一段的平均强度趋近于零。
    全额持有会让一句气话变成一个月的高炎症。
    """
    b = B.new_body(seed=5)
    b["clock"] = 0.0
    MD.set_state(b, {"sadness": 1.0})
    b["clock"] = 24 * 30.0
    MD.step_chronic(b, 24 * 30.0)
    c = MD.chronic(b)
    if c > 0.10:
        fail(f"一个月不更新情绪，慢性值仍然 {c:.3f}")
    ok(f"过时情绪会自己失重（一个月后 {c:.3f}）")


# ----------------------------------------------------------------------
# 3. 时差 / 倒班
# ----------------------------------------------------------------------
def test_jet_lag_moves_bedtime_and_recovers() -> None:
    """飞八小时：入睡点跟着生物钟走，九天之内被拉回来。"""
    e = Physiology({"physio_disease_onset": False})
    b = B.new_body(seed=11)
    b["clock"] = 8.0
    bed0 = float(SL.ensure(b)["bed_h"])
    phase0 = RY.phase_hour(15.0, TR.chronotype(b), RY.shift(b))
    e.set_shift(b, 8.0)
    bed1 = float(SL.ensure(b)["bed_h"])
    phase1 = RY.phase_hour(15.0, TR.chronotype(b), RY.shift(b))
    moved = (bed1 - bed0) % 24.0
    if not 7.5 <= moved <= 8.5:
        fail(f"时差 8 小时只让入睡点挪了 {moved:.2f} 小时（{bed0} → {bed1}）")
    if abs((phase0 - phase1) % 24.0 - 8.0) > 0.1:
        fail("昼夜相位没有跟着偏移，体温与血压曲线还按旧生物钟走")
    e.step(b, 24 * 9)
    if float(b.get("circadian_shift", 0.0)) != 0.0:
        fail(f"九天之后还没倒回来（shift={b.get('circadian_shift')}）")
    ok(f"时差挪入睡点（{bed0:.2f} → {bed1:.2f}，相位 {phase0:.1f} → {phase1:.1f}），九天回零")


def test_shift_is_clamped() -> None:
    """转 30 小时和转 12 小时是一回事：偏移量有上下限。"""
    b = B.new_body(seed=3)
    Physiology({"physio_disease_onset": False}).set_shift(b, 30.0)
    if abs(float(b["circadian_shift"]) - 12.0) > 1e-6:
        fail(f"偏移量没被夹到 12，实际 {b['circadian_shift']}")
    ok("时差偏移夹在 ±12 小时")


# ----------------------------------------------------------------------
# 4. 内感受：四个新通道
# ----------------------------------------------------------------------
def _body_at_noon(seed: int = 3):
    e = Physiology({"physio_disease_onset": False})
    b = B.new_body(seed=seed)
    b["clock"] = 14.0
    b["sleep"] = {"sleeping": False}
    b["life"]["water"] = 0.92
    b["life"]["kcal"] = 1.0
    e.refresh(b)
    return b


def _intero(b) -> dict:
    return IO.compute(b, b["labs"], b["vitals"], b.get("derived") or {})


def test_new_intero_channels_are_quiet() -> None:
    """健康安静的时候这四条一个都不该冒出来。"""
    out = _intero(_body_at_noon())
    for k in ("palpitation", "dizzy", "tinnitus", "soreness"):
        if k not in out:
            fail(f"内感受缺 {k} 通道")
        if float(out[k]) > 0.2:
            fail(f"安静健康态 {k} 已经 {out[k]}")
    if out["signals"]:
        fail(f"安静健康态仍然报了 {out['signals']}")
    ok("四个新通道在健康安静态全静默")


def test_new_intero_channels_speak() -> None:
    """真的异常了要说出来，而且各说各的。"""
    b = _body_at_noon()
    b["vitals"]["HR"] = 104.0
    b["substance"] = {"caffeine": 0.6}
    if not any("心慌" in s[0] for s in _intero(b)["signals"]):
        fail("心率 104 加咖啡因，没报心慌")

    b = _body_at_noon()
    b["vitals"]["SBP"] = 88.0
    b["labs"]["HGB"] = 96.0
    b["life"]["water"] = 0.55
    if not any("发晕" in s[0] for s in _intero(b)["signals"]):
        fail("血压 88、血红蛋白 96、缺水，没报起身发晕")

    b = _body_at_noon()
    b["age"] = 76.0
    b["env"]["noise"] = 78.0
    if not any("嗡嗡" in s[0] for s in _intero(b)["signals"]):
        fail("76 岁待在 78 分贝环境里，没报耳鸣")

    b = _body_at_noon()
    b["life"]["activity"] = 1.8
    b["life"]["fitness"] = 0.30
    if not any("发酸" in s[0] for s in _intero(b)["signals"]):
        fail("长期不练又突然大运动量，没报肌肉酸")
    ok("四个新通道各自能被触发（心慌 / 发晕 / 耳鸣 / 发酸）")


# ----------------------------------------------------------------------
# 5. 中重度外伤
# ----------------------------------------------------------------------
def test_severe_injury_starts_high() -> None:
    """割伤、骨折、脑震荡这些不能从 0.06 的「早期迹象」开始。"""
    b = B.new_body(seed=21)
    ctx = INJ._ctx(b)
    rng = random.Random(7)
    low = []
    for code in sorted(INJ._SEVERE):
        sev = INJ._sev0(b, code, ctx, rng)
        if sev < 0.5:
            low.append(f"{code}={sev}")
        if sev > 0.9:
            fail(f"{code} 初值 {sev} 超过上限")
    if low:
        fail(f"重度外伤初值过低：{', '.join(low)}")
    ok(f"{len(INJ._SEVERE)} 种中重度外伤初值都在 0.5 以上")


def test_severe_injury_stays_rare() -> None:
    """一年撞上七八次骨折的人不正常。

    小磕碰一年三四十次是生活（既有断言的范围是 12~80），中重度那九种
    必须稀得多：割伤缝合、骨折、脑震荡这类事，一个人几年碰上一次。
    实测八个 seed 各一年，合计 9 次 / 8 年，约 0.1 次一年。
    """
    e = Physiology({"physio_disease_onset": True})
    total = 0
    severe = 0
    for seed in (1, 7, 42, 99, 2026, 11, 12, 13):
        b = B.new_body(seed=seed)
        e.step(b, 24 * 365)
        for h in b.get("history") or []:
            if str(h.get("code", "")).startswith("INJ-"):
                total += 1
                if h["code"] in INJ._SEVERE:
                    severe += 1
        for c in b.get("conditions") or []:
            if str(c.get("code", "")).startswith("INJ-"):
                total += 1
                if c["code"] in INJ._SEVERE:
                    severe += 1
    per_year = total / 8.0
    severe_year = severe / 8.0
    if not 12.0 <= per_year <= 80.0:
        fail(f"一年 {per_year:.1f} 次外伤，不像人")
    if severe_year > 2.0:
        fail(f"一年 {severe_year:.1f} 次中重度外伤，太重了")
    ok(f"外伤频率像人（一年 {per_year:.1f} 次，其中中重度 {severe_year:.1f} 次）")


# ----------------------------------------------------------------------
# 6. 体质漂移
# ----------------------------------------------------------------------
def test_traits_drift_with_training() -> None:
    """练三年，静息心率该降一点；但基线不能被改写。"""
    b = B.new_body(seed=13)
    b["life"]["fitness"] = 0.9
    base = float((b.get("traits") or {}).get("hr_off", 0.0))
    TR.step(b, 24 * 365 * 3)
    drift = TR.drift_of(b, "hr_off")
    if drift > -4.0:
        fail(f"练了三年体能 0.9，静息心率偏移只动了 {drift:.2f}")
    if abs(float((b.get("traits") or {}).get("hr_off", 0.0)) - base) > 1e-9:
        fail("漂移写进了基线，seed 定的人格被改掉了")
    ok(f"练三年静息心率偏移 {drift:+.2f}（基线仍是 {base:+.2f}）")


def test_traits_drift_from_pain() -> None:
    """长期疼痛会把痛觉敏感度往上调。"""
    b = B.new_body(seed=13)
    B.add_condition(b, "NR-RADICULO", "腰椎间盘突出", sev=0.42)
    TR.step(b, 24 * 365 * 3)
    drift = TR.drift_of(b, "pain_sens")
    if drift < 0.10:
        fail(f"三年腰椎间盘突出，痛敏只动了 {drift:.3f}")

    # 一处慢性疼痛的目标是 +0.15，两处到顶 +0.30：不能一处就把人写到顶
    b2 = B.new_body(seed=13)
    B.add_condition(b2, "NR-RADICULO", "腰椎间盘突出", sev=0.42)
    B.add_condition(b2, "GI-IBD-CD", "克罗恩病", sev=0.40)
    TR.step(b2, 24 * 365 * 3)
    drift2 = TR.drift_of(b2, "pain_sens")
    if drift2 < 0.25 or drift2 > 0.31:
        fail(f"两处慢性疼痛的痛敏漂移是 {drift2:.3f}，不在 0.25~0.31")
    ok(f"慢性疼痛抬高痛敏（一处 {drift:+.2f}，两处 {drift2:+.2f}，上限 0.30）")


def test_acute_pain_does_not_drift() -> None:
    """一次心梗很疼，但不是三年的痛觉敏化。

    目录里 dur=None 同时罩着心梗、主动脉夹层这类急症，只看「dur 为空且疼」
    会把它们算成慢性疼痛。急性的一律排除。
    """
    b = B.new_body(seed=13)
    B.add_condition(b, "CV-MI", "急性心肌梗死", sev=0.50)
    TR.step(b, 24 * 365 * 3)
    drift = TR.drift_of(b, "pain_sens")
    if drift > 1e-6:
        fail(f"一次急性心梗把痛敏推了 {drift:.3f}")
    ok("急性疼痛不会变成长期痛敏")


# ----------------------------------------------------------------------
# 7. 表达义务：连续三档
# ----------------------------------------------------------------------
def _load(sev: float, primary=None, meta=None) -> float:
    st = SimpleNamespace(meta=meta or {})
    dx = SimpleNamespace(severity=sev, primary=primary)
    return NA._pathology_load(st, dx)


def test_express_obligation_is_continuous() -> None:
    """严重度扫过去，负荷要连续变化，不能在某个数上整段跳。"""
    prev = _load(0.0)
    jump = 0.0
    for i in range(1, 121):
        cur = _load(i * 0.5)
        jump = max(jump, cur - prev)
        prev = cur
    if jump > 0.02:
        fail(f"负荷在 0.5 的严重度步长上跳了 {jump:.3f}，还是硬阈值")
    ok(f"表达义务负荷连续（最大步进 {jump:.4f}）")


def test_express_obligation_three_bands() -> None:
    """三档：健康豁免 / 偏轻不强制 / 够重必须说。"""
    st_meta = {"side_effects": [], "sedation": 0.0, "hot": {}}
    st = SimpleNamespace(meta=st_meta)
    light = SimpleNamespace(severity=3.0, primary=None)
    middle = SimpleNamespace(severity=15.0, primary=None)
    heavy = SimpleNamespace(severity=45.0, primary=None)

    if not NA._express_exempt(st, light):
        fail("健康态没有被豁免")
    if NA._express_exempt(st, middle):
        fail("严重度 15 仍被判为豁免")
    if NA._pathology_load(st, middle) >= NA._MANDATE_AT:
        fail("严重度 15 直接进了强制档，中间带没生效")
    if NA._pathology_load(st, heavy) < NA._MANDATE_AT:
        fail("严重度 45 还没进强制档")

    txt = NA._express_section(st, middle)
    if "不强制" not in txt:
        fail("中间带没有给出「不强制但有由头就说」的写法")
    ok("表达义务分三档（豁免 / 有由头才说 / 强制）")


# ----------------------------------------------------------------------
def main() -> None:
    test_year_run_keeps_record_sane()
    test_year_run_history_accumulates()
    test_chronic_mood_settles_once()
    test_chronic_mood_accumulates()
    test_chronic_mood_fades()
    test_stale_mood_does_not_persist_forever()
    test_jet_lag_moves_bedtime_and_recovers()
    test_shift_is_clamped()
    test_new_intero_channels_are_quiet()
    test_new_intero_channels_speak()
    test_severe_injury_starts_high()
    test_severe_injury_stays_rare()
    test_traits_drift_with_training()
    test_traits_drift_from_pain()
    test_acute_pain_does_not_drift()
    test_express_obligation_is_continuous()
    test_express_obligation_three_bands()
    print(f"\n全部通过（{PASS} 项）。")


if __name__ == "__main__":
    main()
