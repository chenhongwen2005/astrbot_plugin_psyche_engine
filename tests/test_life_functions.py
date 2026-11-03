"""「一个完整的人」的回归自测：内感受、睡眠结构、疾病目录完整性。

跑法：
    python tests/test_life_functions.py

测什么
    这三个模块有一个共同的失败模式：**数值全都合法，但人不像人**。
    膀胱永远不会涨、口渴永远不出现、睡眠永远「七小时质量良好」——
    每一项单看都说得过去，合起来是一个不吃饭不上厕所也不会难受的角色。

    所以这里的断言全部指向「会不会发生」而不是「数值等于几」：
    一夜之后睡眠债有没有收敛、早上起来是不是真的渴、憋久了会不会
    自己去厕所、喝了两杯深睡是不是真的变浅。参数改了就改吧，
    只要这些关系还在，人就还是活的。
"""

from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physio import intero as IO  # noqa: E402
from physio import injury as INJ  # noqa: E402
from physio import aging as AG  # noqa: E402
from physio import traits as TR  # noqa: E402
from physio import rhythm as RY  # noqa: E402
from physio import mind as MD  # noqa: E402
from physio import sleep as SL  # noqa: E402
from physio import body as B  # noqa: E402
from physio import const as C  # noqa: E402
from physio import report as R  # noqa: E402
from physio.diseases import DISEASES  # noqa: E402
from physio.drugs import DRUGS  # noqa: E402
from physio.engine import Physiology  # noqa: E402

PASS = 0


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"[ok] {msg}")


def fail(msg: str) -> None:
    raise AssertionError(msg)


# ----------------------------------------------------------------------
# 1. 疾病目录完整性
# ----------------------------------------------------------------------
def test_catalog_integrity() -> None:
    bad = []
    for code, spec in DISEASES.items():
        for k in spec["labs"]:
            if k not in C.LABS and k not in C.VITALS:
                bad.append(f"{code}.labs.{k}")
        for k in spec["org"]:
            if k not in C.ORGANS:
                bad.append(f"{code}.org.{k}")
        for k in spec["treat"]:
            if k not in DRUGS:
                bad.append(f"{code}.treat.{k}")
        if spec["sys"] not in C.SYSTEM_ZH:
            bad.append(f"{code}.sys.{spec['sys']}")
    if bad:
        fail("疾病目录引用了不存在的表项：" + "、".join(bad[:8]))
    ok(f"疾病目录自洽（{len(DISEASES)} 项，化验/器官/药物/系统全部对得上）")


def test_catalog_no_dup_name() -> None:
    c = Counter(v["zh"] for v in DISEASES.values())
    dup = [k for k, n in c.items() if n > 1]
    if dup:
        fail("疾病重名会导致按名查询命中错误的病：" + "、".join(dup))
    ok(f"疾病中文名唯一（{len(c)} 个名字）")


def test_catalog_scale() -> None:
    """急性按天、慢性按月。两套尺度写反了，一年的病会比一辈子还多。

    acute=True 但不给 dur 是合法的：心梗、主动脉夹层、白血病这些本来就是
    「突然发生、不会自己好」的，靠治疗而不是靠时间。
    """
    bad = []
    for code, spec in DISEASES.items():
        if spec["acute"]:
            if spec["base"] > 0.06:
                bad.append(f"{code} 急性日概率 {spec['base']} 过高")
        else:
            if spec["base"] > 0.01:
                bad.append(f"{code} 慢性月概率 {spec['base']} 过高")
        if spec["dur"] is not None and spec["dur"] > 4000.0:
            bad.append(f"{code} 自限期 {spec['dur']} 小时过长（超过半年）")
    if bad:
        fail("概率尺度可疑：" + "；".join(bad[:6]))
    ok("急性/慢性的概率尺度分类一致")


def test_environment_risk() -> None:
    """中暑只该在热的时候发生，失温只该在冷的时候发生。"""
    e = Physiology({"physio_disease_onset": False})
    hot = B.new_body()
    hot["env"]["temp_c"] = 40.0
    hot["env"]["humidity"] = 85.0
    cold = B.new_body()
    cold["env"]["temp_c"] = -5.0
    g_hot = e._risk_factor(hot, "heat")
    g_cold = e._risk_factor(cold, "cold")
    w_hot = e._risk_factor(hot, "cold")
    w_cold = e._risk_factor(cold, "heat")
    if not (g_hot > 0.4 and w_hot == 0.0):
        fail(f"高温下 heat={g_hot:.2f} cold={w_hot:.2f}，环境风险因子没接上")
    if not (g_cold > 0.4 and w_cold == 0.0):
        fail(f"低温下 cold={g_cold:.2f} heat={w_cold:.2f}，环境风险因子没接上")
    ok(f"环境风险因子方向正确（40℃热 {g_hot:.2f}；-5℃冷 {g_cold:.2f}）")


# ----------------------------------------------------------------------
# 2. 内感受
# ----------------------------------------------------------------------
def test_hunger_follows_meals() -> None:
    """刚吃完不饿，饭点前饿。"""
    body = B.new_body()
    full = dict(body)
    full["clock"] = 8.0            # 刚吃完早饭
    before = dict(body)
    before["clock"] = 18.6         # 晚饭前
    labs = {"GLU": 5.0}
    h_full = IO.compute(full, labs, {}, {})["hunger"]
    h_before = IO.compute(before, labs, {}, {})["hunger"]
    if not (h_before > h_full + 0.3):
        fail(f"饭前 {h_before:.2f} 不比饭后 {h_full:.2f} 饿，三餐模型没进内感受")
    ok(f"饥饿跟随三餐（饭后 {h_full:.2f} → 饭前 {h_before:.2f}）")


def test_thirst_appears_overnight() -> None:
    """一夜不喝水，早上应该是渴的。"""
    e = Physiology({"physio_disease_onset": False})
    b = B.new_body()
    b["clock"] = 20.0                      # 晚饭后
    b["life"]["water"] = 0.95
    for _ in range(10):                    # 走到次日早上六点（还没开始做早饭）
        b["clock"] = float(b["clock"]) + 1.0
        e._hydration(b, 1.0, B.rng_for(b, salt=3))
    thirst = IO.compute(b, {}, {}, {})["thirst"]
    if thirst < 0.45:
        fail(f"11 小时没喝水，口渴只有 {thirst:.2f}——水分收支没在动")
    ok(f"不喝水会渴（11 小时后 {thirst:.2f}，水合 {b['life']['water']:.2f}）")


def test_water_does_not_drift() -> None:
    """喝水是负反馈，不是单向漂移：跑三天不能一路掉到底或粘在满格。"""
    e = Physiology({"physio_disease_onset": False})
    b = B.new_body()
    lows, highs = [], []
    for _ in range(72):
        b["clock"] = float(b["clock"]) + 1.0
        e._hydration(b, 1.0, B.rng_for(b, salt=3))
        w = float(b["life"]["water"])
        lows.append(w)
        highs.append(w)
    lo, hi = min(lows), max(highs)
    if lo < 0.35:
        fail(f"三天后水合掉到 {lo:.2f}，收支不平衡")
    if hi - lo < 0.08:
        fail(f"水合三天只有 {hi - lo:.2f} 的波动，等于没建模")
    ok(f"水合三天在 {lo:.2f}~{hi:.2f} 之间往复（振幅 {hi - lo:.2f}）")


def test_bladder_voids_itself() -> None:
    """憋到顶必须自己去，否则角色会永远憋着。"""
    body = B.new_body()
    IO.ensure(body)
    events = []
    for i in range(1, 40):
        body["clock"] = float(i)
        events.extend(IO.step(body, 1.0))
    n = events.count("void")
    if n < 3:
        fail(f"40 小时只排尿 {n} 次，膀胱要么不涨要么不排")
    if float((body.get("intero") or {}).get("bladder", 0)) >= 1.2:
        fail("膀胱超过上限还没排空")
    ok(f"膀胱会涨也会排（40 小时 {n} 次，当前 {body['intero']['bladder']:.2f}）")


def test_bowel_is_about_once_a_day() -> None:
    body = B.new_body()
    IO.ensure(body)
    events = []
    for i in range(1, 97):
        body["clock"] = float(i)
        events.extend(IO.step(body, 1.0))
    n = events.count("stool")
    if not (2 <= n <= 6):
        fail(f"四天排便 {n} 次，不符合一天一到两次")
    ok(f"排便是日常频率（4 天 {n} 次）")


def test_intero_quiet_when_healthy() -> None:
    """健康人刚起床吃完早饭，不该有任何越线信号。"""
    body = B.new_body()
    IO.ensure(body)
    body["clock"] = 8.4
    body["intero"]["bladder"] = 0.35
    body["intero"]["bowel"] = 0.30
    io = IO.compute(body, {"GLU": 5.2}, {}, {})
    if io["signals"]:
        fail("刚吃完早饭就有身体信号：" + "、".join(s for s, _ in io["signals"]))
    ok("健康态内感受安静（无越线信号）")


# ----------------------------------------------------------------------
# 3. 睡眠结构
# ----------------------------------------------------------------------
def _run_nights(days: int, tune=None):
    e = Physiology({"physio_disease_onset": False})
    b = B.new_body()
    # 从下午三点起跑、到下午三点收工：结算点必须落在清醒时段。
    # 停在半夜的话 sleep_h 是「这觉已经睡了多久」，拿它当昨夜总时长
    # 去断言就是在测一件错事。
    b["clock"] = 15.0
    if tune:
        tune(b)
    for _ in range(int(days * 24)):
        e.step(b, 1.0)
    return b


def test_night_settles() -> None:
    """连睡五天，债务要收敛而不是单调堆到天花板。"""
    b = _run_nights(5)
    debt = float(b["life"]["sleep_debt"])
    h = float(b["life"]["sleep_h"])
    if debt > 20.0:
        fail(f"五天之后睡眠债 {debt:.1f} 小时，说明一夜根本没还上")
    if not (5.0 <= h <= 9.5):
        fail(f"睡眠时长 {h:.1f} 小时超出人类范围")
    ok(f"睡眠收敛（五天：{h:.1f} 小时/夜，债务 {debt:.1f}）")


def test_night_record_exists() -> None:
    b = _run_nights(3)
    st = b.get("sleep") or {}
    last = st.get("last")
    if not isinstance(last, dict):
        fail("睡了三天还没有任何一夜的记录")
    for k in ("hours", "lat_min", "n3", "rem", "awakenings", "eff"):
        if k not in last:
            fail(f"昨夜记录缺字段 {k}")
    if not (0.4 <= float(last["eff"]) <= 1.0):
        fail(f"睡眠效率 {last['eff']} 不在合理区间")
    line = SL.summary(b)
    if "睡了" not in line:
        fail("昨夜摘要读不出来：" + line)
    ok(f"一夜有完整结构（{line}）")


def test_debt_deepens_sleep() -> None:
    """欠得越多，前半夜压得越狠：深睡应该上升。"""
    import random
    base = B.new_body()
    tired = B.new_body()
    tired["life"]["sleep_debt"] = 9.0
    p1 = SL.plan_night(base, random.Random(7), 23.0)
    p2 = SL.plan_night(tired, random.Random(7), 23.0)
    if not (p2["n3"] > p1["n3"] + 0.03):
        fail(f"欠债后深睡没上升（{p1['n3']:.3f} → {p2['n3']:.3f}）")
    ok(f"睡眠压力加深慢波睡眠（{p1['n3']:.2f} → {p2['n3']:.2f}）")


def test_alcohol_lightens_sleep() -> None:
    """两杯之后深睡变浅、夜醒变多。这是有据可查的，也是很多人的实际体验。"""
    import random
    sober = B.new_body()
    drunk = B.new_body()
    drunk["life"]["alcohol"] = 2.0
    p1 = SL.plan_night(sober, random.Random(11), 23.0)
    p2 = SL.plan_night(drunk, random.Random(11), 23.0)
    if not (p2["n3"] < p1["n3"]):
        fail(f"饮酒后深睡反而更高（{p1['n3']:.3f} → {p2['n3']:.3f}）")
    ok(f"酒精削浅睡眠（深睡 {p1['n3']:.2f} → {p2['n3']:.2f}）")


def test_stress_delays_onset() -> None:
    """焦虑的人躺得久。入睡潜伏是失眠的主诉，不能恒等于十分钟。"""
    import random
    calm = B.new_body()
    calm["life"]["stress"] = 0.2
    tense = B.new_body()
    tense["life"]["stress"] = 0.95
    p1 = SL.plan_night(calm, random.Random(5), 23.0)
    p2 = SL.plan_night(tense, random.Random(5), 23.0)
    if not (p2["lat_min"] > p1["lat_min"] * 2):
        fail(f"高压力没延长入睡（{p1['lat_min']} → {p2['lat_min']} 分钟）")
    ok(f"压力延长入睡潜伏（{p1['lat_min']:.0f} → {p2['lat_min']:.0f} 分钟）")


def test_one_night_per_night() -> None:
    """跨零点不能把一夜劈成两半，也不能一夜睡两次。"""
    e = Physiology({"physio_disease_onset": False})
    b = B.new_body()
    # 从下午起跑：从零点起跑会先补一觉（1 点睡到 8 点），那是真实的
    # 熬夜补觉，不是重复睡，但会让「三天几夜」这个数对不上。
    b["clock"] = 15.0
    onsets = 0
    for _ in range(24 * 3):
        r = e.step(b, 1.0)
        onsets += [x for x in r["events"] if x == "sleep_onset"].__len__()
    if not (2 <= onsets <= 3):
        fail(f"三天里入睡事件 {onsets} 次，一夜被劈开或重复睡")
    ok(f"一夜只排一次（三天 {onsets} 次入睡）")


def test_sleep_in_reports() -> None:
    b = _run_nights(3)
    life = R.render_life(b)
    if "昨夜：" not in life:
        fail("生活状态里没有昨夜睡眠一行")
    ok("体检报告带昨夜睡眠结构")


# ----------------------------------------------------------------------
# 4. 外伤
# ----------------------------------------------------------------------
def test_injury_heals() -> None:
    """伤口要一天比一天好，而不是一直挂着。"""
    e = Physiology({"physio_disease_onset": False})
    b = B.new_body()
    b["clock"] = 10.0
    INJ.inflict(b, "INJ-CUT", [])
    cond = next((c for c in b["conditions"] if c["code"] == "INJ-CUT"), None)
    if cond is None:
        fail("切了一刀，身上却没有这条伤")
    # 盯住这一条，而不是「当前最重的那条」：这几天里很可能又添了新伤，
    # 拿列表首项做轨迹会把两条伤混成一条，看着就像「伤口又变重了」。
    trail = []
    gone_at = None
    for i in range(24 * 8):
        e.step(b, 1.0)
        if cond in b["conditions"]:
            trail.append(float(cond.get("sev", 0.0)))
        elif gone_at is None:
            gone_at = i
            break
    if trail[0] < 0.1:
        fail("伤口刚弄上就不疼了，初值没落到病程上")
    if any(b2 > a + 1e-6 for a, b2 in zip(trail, trail[1:])):
        fail("伤口中途又变重了：外伤不该有「回升」这一段")
    if gone_at is None:
        fail(f"八天还没好，剩下 {trail[-1]:.3f}")
    ok(f"伤口单调愈合并消失（{trail[0]:.2f} → 0，第 {gone_at / 24:.1f} 天好全）")


def test_injury_shows_in_block() -> None:
    e = Physiology({"physio_disease_onset": False})
    b = B.new_body()
    b["clock"] = 10.0
    INJ.inflict(b, "INJ-CUT", [])
    e.refresh(b)
    text = R.render_block_section(b)
    if "外伤" not in text:
        fail("注入块里没有外伤一行：" + text)
    if "手指上划开一道口子" not in text:
        fail("注入块没体现伤口的具体位置与感觉：" + text)
    if text.count("手指上划开一道口子") > 1:
        fail("外伤行与症状行重复了同一句：" + text)
    # 好全了就不该再提这一条。这几天里可能又添了新伤，所以只针对
    # 「切割伤」断言，而不是「块里完全没有外伤」。
    for _ in range(24 * 12):
        e.step(b, 1.0)
        if not any(c["code"] == "INJ-CUT" for c in b["conditions"]):
            break
    e.refresh(b)
    if "切割伤" in R.render_block_section(b):
        fail("伤已经好了，注入块还在提")
    ok("外伤进块且不重复，好了就消失")


def test_injury_hazard_follows_context() -> None:
    """喝多了、困狠了，切到手的概率必须显著更高。"""
    def rate(etoh_gL: float, debt: float) -> float:
        b = B.new_body()
        b["clock"] = 18.0
        # 用血酒精而不是「每天几杯」：白天不喝酒的人不该因为习惯而更容易
        # 切到手，只有此刻真的喝了才算。
        b["subs"] = {"etoh": etoh_gL, "caff": 0.0, "peak": 0.0, "hang": 0.0, "since": -1.0}
        b["life"]["sleep_debt"] = debt
        c = INJ._ctx(b)
        return INJ._mult(b, "INJ-CUT", c)

    sober = rate(0.0, 0.0)
    drunk = rate(1.2, 0.0)
    tired = rate(0.0, 12.0)
    if not (drunk > sober * 1.8):
        fail(f"喝到 1.2 g/L 切到手风险只涨了 {drunk / sober:.2f} 倍")
    if not (tired > sober * 1.4):
        fail(f"严重缺觉只把风险抬高 {tired / sober:.2f} 倍")
    ok(f"困与醉都抬高受伤风险（醉 ×{drunk / sober:.1f}，困 ×{tired / sober:.1f}）")


def test_injury_rate_is_human() -> None:
    """一年三四十次小磕碰是生活，一年三百次是纸糊的。"""
    total = 0
    for seed in (11, 12, 13):
        e = Physiology({"physio_disease_onset": False})
        b = B.new_body(seed=seed)
        b["clock"] = 15.0
        for _ in range(24 * 365):
            r = e.step(b, 1.0)
            total += sum(1 for ev in r["events"] if ev.startswith("injury:"))
    per_year = total / 3
    if not (12 <= per_year <= 80):
        fail(f"一年受伤 {per_year:.0f} 次，不像人")
    ok(f"外伤频率像人（一年约 {per_year:.0f} 次）")


def test_injury_no_duplicate() -> None:
    """同一处不叠两条：切了两次手是两个口子，但同名条目只能有一条。"""
    b = B.new_body()
    b["clock"] = 10.0
    INJ.inflict(b, "INJ-CUT", [])
    INJ.inflict(b, "INJ-CUT", [])
    n = len([c for c in b["conditions"] if c["code"] == "INJ-CUT"])
    if n != 1:
        fail(f"同一处伤被记了 {n} 次")
    ok("同一处伤不会重复记账")


# ----------------------------------------------------------------------
# 5. 衰老
# ----------------------------------------------------------------------
FLAG_DISEASES = ("EYE-PRESBYOPIA", "EN-PRESBYCUSIS", "EN-OSTEOPOR",
                 "EY-CATARACT", "MS-SARCOPENIA")


def test_age_advances_with_clock() -> None:
    """时钟走了多久，人就老多久。五年模拟跑完还写着七十八岁，那是照片。"""
    e = Physiology({"physio_disease_onset": False})
    b = B.new_body()
    b["clock"] = 15.0
    a0 = float(b["age"])
    c0 = float(b["clock"])
    # 单次 step 有 14 天上限，分两次走满 28 天
    for _ in range(2):
        e.step(b, 24.0 * 14)
    grew = float(b["age"]) - a0
    want = (float(b["clock"]) - c0) / (24.0 * 365.25)
    if abs(grew - want) > 0.0005:
        fail(f"时钟走了 {want * 365.25:.1f} 天，年龄只涨了 {grew * 365.25:.1f} 天")
    ok(f"年龄跟着时钟走（28 天 +{grew * 365.25:.1f} 天）")


def test_aging_schedule_is_human() -> None:
    """四十岁上下老花、六十往后白内障骨松耳背、七十肌少——顺序不能乱。"""
    b = B.new_body()
    b["age"] = 30.0
    b["clock"] = 15.0
    ev: list = []
    AG.step(b, 24.0 * 365.0 * 45.0, ev)
    got = {c["code"] for c in b["conditions"]}
    missing = [c for c in FLAG_DISEASES if c not in got]
    if missing:
        fail(f"七十五岁还缺这些衰老改变：{missing}")
    if float(b["age"]) < 74.9:
        fail(f"直接推进四十五年，年龄只到 {b['age']}")
    marks = [e.split(":")[-1] for e in ev if e.startswith("aging:")]
    if len(marks) != len(FLAG_DISEASES):
        fail(f"衰老事件 {len(marks)} 条，应有 {len(FLAG_DISEASES)} 条：{marks}")
    ok("衰老按日程发生（" + "、".join(marks) + "）")


def test_no_aging_before_its_time() -> None:
    """二十五岁的人不该有白内障。这不是概率问题，是排期问题。"""
    b = B.new_body()
    b["age"] = 25.0
    b["clock"] = 15.0
    AG.step(b, 24.0 * 365.0 * 14.0, [])          # 走到三十九岁
    got = {c["code"] for c in b["conditions"]}
    early = [c for c in FLAG_DISEASES if c in got]
    if early:
        fail(f"三十九岁就出现了：{early}")
    AG.step(b, 24.0 * 365.0 * 12.0, [])          # 走到五十一岁
    got = {c["code"] for c in b["conditions"]}
    if "EYE-PRESBYOPIA" not in got:
        fail(f"五十一岁还没老花，日程表没生效（{sorted(got)}）")
    if "EY-CATARACT" in got:
        fail("五十一岁就有白内障，日程表跑早了")
    ok("衰老不提前发生（39 岁全无、51 岁只多老花）")


def test_fitness_capped_by_age() -> None:
    """再怎么练也练不回二十五岁——封顶就是封顶。"""
    b = B.new_body()
    b["age"] = 25.0
    b["clock"] = 15.0
    b["life"]["fitness"] = 1.0
    AG.step(b, 24.0 * 365.0 * 40.0, [])
    cap = AG.fitness_cap(float(b["age"]))
    fit = float(b["life"]["fitness"])
    if fit > cap + 1e-6:
        fail(f"{b['age']:.0f} 岁体能 {fit:.2f} 超过了年龄上限 {cap:.2f}")
    if cap > 0.90:
        fail(f"六十五岁的体能上限还有 {cap:.2f}，老化没压下来")
    ok(f"体能受年龄封顶（{b['age']:.0f} 岁 {fit:.2f} ≤ {cap:.2f}）")



# ----------------------------------------------------------------------
# 8. 个体差异与昼夜节律
# ----------------------------------------------------------------------
def test_traits_are_stable() -> None:
    """同一个 seed 必须永远给同一副身体，换 seed 才换人。"""
    a1 = TR.new_traits(7)
    a2 = TR.new_traits(7)
    b1 = TR.new_traits(8)
    if a1 != a2:
        fail("同 seed 两次生成不一样，这个人每重启一次就换一副身体")
    if a1 == b1:
        fail("不同 seed 生成完全相同，等于没做个体差异")
    ok("体质由 seed 稳定决定，不同人不重样")


def test_traits_reach_vitals() -> None:
    """体质偏移必须真的落到体征上，不能只是存着好看。"""
    got = []
    for seed in (11, 12, 13, 14, 15, 16):
        b = B.new_body(seed=seed)
        b["clock"] = 15.0
        e = Physiology({"physio_disease_onset": False, "physio_hours_per_turn": 0.0})
        e.refresh(b)
        got.append((float(b["vitals"]["HR"]), TR.get(b, "hr_off")))
    span = max(g[0] for g in got) - min(g[0] for g in got)
    if span < 6.0:
        fail(f"六个健康人的静息心率只差 {span:.1f} 次，像同一个模板")
    hi = max(got, key=lambda x: x[1])
    lo = min(got, key=lambda x: x[1])
    if hi[0] <= lo[0]:
        fail("心率偏移为正的人读数反而更低，偏移没接上体征")
    ok(f"静息心率因人而异（{min(g[0] for g in got):.0f}~{max(g[0] for g in got):.0f} 次）")


def test_pain_sensitivity_scales_pain() -> None:
    """同样的伤，怕疼的人 VAS 更高。"""
    def vas(sens: float) -> float:
        b = B.new_body()
        b["clock"] = 14.0
        b["traits"] = dict(TR.new_traits(1))
        b["traits"]["pain_sens"] = sens
        INJ.inflict(b, "INJ-CUT", [])
        e = Physiology({"physio_disease_onset": False,
                        "physio_hours_per_turn": 0.0})
        e.refresh(b)
        return float(b["vitals"]["PAIN"])

    low, high = vas(0.75), vas(1.30)
    if high <= low + 0.3:
        fail(f"疼痛敏感度 0.75 → 1.30，VAS 只从 {low:.1f} 走到 {high:.1f}")
    ok(f"疼痛敏感度落到 VAS（{low:.1f} → {high:.1f}）")


def test_body_temp_follows_clock() -> None:
    """凌晨四五点最低、傍晚最高，差半度以上。整天 36.5 就是块铁。"""
    def temp_at(hour: float) -> float:
        b = B.new_body(seed=21)
        b["clock"] = hour
        return RY.temp_off(b)

    lo = min(temp_at(h) for h in range(0, 24))
    hi = max(temp_at(h) for h in range(0, 24))
    if hi - lo < 0.4:
        fail(f"体温昼夜振幅只有 {hi - lo:.2f}℃，太扁")
    if not (temp_at(4.5) < temp_at(12.0) < temp_at(17.0)):
        fail("体温最低点不在凌晨，或下午不比中午高，相位错了")
    ok(f"体温有昼夜曲线（振幅 {hi - lo:.2f}℃，4:30 最低、傍晚最高）")


def test_bp_dips_at_night() -> None:
    """睡着之后血压要降，醒来那两小时要是晨峰。"""
    b = B.new_body(seed=22)
    b["clock"] = 3.0
    b["sleep"] = {"sleeping": True}
    s_sleep, _ = RY.bp_off(b)
    b["sleep"] = {"sleeping": False}
    s_awake, _ = RY.bp_off(b)
    b["clock"] = 7.5
    s_morning, _ = RY.bp_off(b)
    if s_sleep > -10.0:
        fail(f"睡着时收缩压只降了 {s_sleep:.1f}，夜间下降没了")
    if s_morning <= s_awake + 3.0:
        fail(f"清晨收缩压没冲起来（晨峰 {s_morning:.1f} vs 平段 {s_awake:.1f}）")
    ok(f"血压夜间下降 {s_sleep:.0f}、清晨晨峰 +{s_morning - s_awake:.0f}")


def test_sleep_need_is_personal() -> None:
    """短睡者每晚少睡一小时就够了，长睡者要睡够才不欠。

    这里看的是**排出来的整夜时长**，不是跑完一夜之后的债务余额：
    债务是「需求 − 实睡」，而实睡本身带着 ±0.9 小时的抽样噪声，
    单跑一夜两家正好撞上同一个数是完全可能的。比时长没有这个问题。
    """
    def planned(need: float) -> float:
        b = B.new_body()
        b["clock"] = 22.0
        b["traits"] = dict(TR.new_traits(3))
        b["traits"]["sleep_need"] = need
        return float(SL.plan_night(b, B.rng_for(b, salt=5), 22.0)["hours"])

    short, long_ = planned(6.8), planned(8.8)
    if long_ - short < 1.2:
        fail(f"需求差两小时，排出来的夜只差 {long_ - short:.1f} 小时")
    if abs(short - 6.8) > 1.2 or abs(long_ - 8.8) > 1.2:
        fail(f"整夜时长离需求太远（{short:.1f} / {long_:.1f}）")
    ok(f"整夜时长跟着个人需求走（{short:.1f}h vs {long_:.1f}h）")


def test_bedtime_follows_chronotype() -> None:
    """早鸟该早睡，夜猫子该过午夜才躺下。"""
    def bed_for(chrono: float) -> float:
        b = B.new_body()
        b["traits"] = dict(TR.new_traits(4))
        b["traits"]["chronotype"] = chrono
        SL.ensure(b)
        return float(b["sleep"]["bed_h"])

    early, late = bed_for(-1.4), bed_for(1.4)
    if early >= 22.0:
        fail(f"极早起型 {early:.1f} 点才睡，不像早鸟")
    # 就寝点按 24 小时归一：1.2 点就是过了午夜的那种晚睡
    if not (late > 24.0 or late < 7.0):
        fail(f"极晚睡型 {late:.1f} 点就睡，不像夜猫子")
    ok(f"就寝点跟着昼夜相位走（早鸟 {early:.1f} 点，夜猫子 {late:.1f} 点）")


def test_night_owl_still_sleeps() -> None:
    """就寝点过了午夜，不能让一整夜都不触发——那会永远睡不着。"""
    b = B.new_body()
    b["clock"] = 18.0
    b["traits"] = dict(TR.new_traits(4))
    b["traits"]["chronotype"] = 1.4      # 就寝点约 1:15
    b["traits"]["sleep_need"] = 6.8
    e = Physiology({"physio_disease_onset": False})
    onsets = 0
    for _ in range(24 * 3):
        r = e.step(b, 1.0)
        onsets += sum(1 for ev in r["events"] if ev == "sleep_onset")
    if not (2 <= onsets <= 3):
        fail(f"三天里夜猫子只睡了 {onsets} 次，跨零点的就寝判定算错了")
    ok(f"过了午夜才睡的人也排得上夜（三天 {onsets} 次）")



# ----------------------------------------------------------------------
# 9. 情绪落到身体
# ----------------------------------------------------------------------
def _calm_body(seed: int = 5):
    b = B.new_body(seed=seed)
    b["clock"] = 15.0
    b["sleep"] = {"sleeping": False}
    return b


def test_mind_moves_vitals() -> None:
    """吵起来的时候心率血压都要动，不是只在情绪模块里记一笔。"""
    b = _calm_body()
    e = Physiology({"physio_disease_onset": False})
    e.refresh(b)
    hr0 = float(b["vitals"]["HR"])
    sbp0 = float(b["vitals"]["SBP"])

    MD.set_state(b, {"anger": 0.9})
    e.refresh(b)
    hr1 = float(b["vitals"]["HR"])
    sbp1 = float(b["vitals"]["SBP"])

    if hr1 - hr0 < 8.0:
        fail(f"愤怒 0.9 只把心率抬了 {hr1 - hr0:.1f} 次")
    if sbp1 - sbp0 < 8.0:
        fail(f"愤怒 0.9 只把收缩压抬了 {sbp1 - sbp0:.1f}")
    ok(f"情绪落到体征（愤怒：心率 +{hr1 - hr0:.0f}，收缩压 +{sbp1 - sbp0:.0f}）")


def test_mind_saturates() -> None:
    """又怕又气不能把心率叠到 130。总量有上限，这是设计不是巧合。"""
    b = _calm_body()
    e = Physiology({"physio_disease_onset": False})
    e.refresh(b)
    hr0 = float(b["vitals"]["HR"])
    MD.set_state(b, {"anger": 1.0, "fear": 1.0, "jealousy": 1.0, "shame": 1.0})
    e.refresh(b)
    rise = float(b["vitals"]["HR"]) - hr0
    if rise > 26.0:
        fail(f"四种情绪叠在一起把心率抬了 {rise:.0f} 次，饱和没生效")
    if rise < 12.0:
        fail(f"强烈的复合情绪只抬了 {rise:.0f} 次，饱和得太狠")
    ok(f"情绪效应有上限（叠加后 +{rise:.0f} 次）")


def test_mind_fades_with_hours() -> None:
    """情绪的身体反应要按小时退下去，而不是一直挂着。"""
    b = _calm_body()
    e = Physiology({"physio_disease_onset": False})
    e.refresh(b)
    hr0 = float(b["vitals"]["HR"])
    MD.set_state(b, {"anger": 1.0})
    e.refresh(b)
    hot = float(b["vitals"]["HR"]) - hr0

    b["clock"] += MD.HALF_LIFE_H
    e.refresh(b)
    half = float(b["vitals"]["HR"]) - hr0
    b["clock"] += 6.0
    e.refresh(b)
    later = float(b["vitals"]["HR"]) - hr0

    if not (half < hot * 0.7):
        fail(f"过了一个半衰期，心率增量还剩 {half / hot:.0%}")
    if later > 1.5:
        fail(f"七小时后心率还高 {later:.1f} 次，情绪没退")
    ok(f"情绪按小时衰减（+{hot:.0f} → +{half:.0f} → +{later:.1f}）")


def test_mind_shifts_pain_threshold() -> None:
    """同一处伤，心情差的时候更疼，高兴的时候没那么疼。"""
    def vas(emo) -> float:
        b = _calm_body()
        INJ.inflict(b, "INJ-CUT", [])
        MD.set_state(b, emo)
        e = Physiology({"physio_disease_onset": False,
                        "physio_hours_per_turn": 0.0})
        e.refresh(b)
        return float(b["vitals"]["PAIN"])

    sad = vas({"sadness": 0.9})
    glad = vas({"joy": 0.9})
    if sad <= glad:
        fail(f"低落时 VAS {sad:.1f} 不高于愉快时 {glad:.1f}，痛觉阈值没跟着情绪走")
    ok(f"情绪改变痛觉（低落 {sad:.1f} vs 愉快 {glad:.1f}）")


def test_mind_block_stays_single_line() -> None:
    """情绪的身体反应并进「身上：」那一行，不能多出一条同名行。"""
    b = _calm_body()
    MD.set_state(b, {"anger": 0.9, "fear": 0.6})
    e = Physiology({"physio_disease_onset": False})
    e.refresh(b)
    text = R.render_block_section(b)
    n = sum(1 for ln in text.splitlines() if ln.startswith("身上"))
    if n != 1:
        fail(f"注入块里有 {n} 条「身上」行")
    if "心跳" not in text:
        fail(f"强烈情绪没在身体段里出现：{text[:80]}")
    ok("情绪并进同一条「身上」，不另起一行")


def test_a_day_says_something() -> None:
    """一整天跑下来，饿、渴、尿意、便意都该真的出现过。

    这条是从 tools/day_demo.py 里长出来的。之前所有断言都在验「某一刻
    的数值关系」——饭前比饭后饿、11 小时不喝水会渴——每一项都过，但
    饥饿的曲线标定得太钝（要 7.6 小时才越线，三餐间隔只有 5~6.5 小时），
    于是这个人**一整天一次都没喊过饿**。单点全对，一天全空。

    所以这里不看某一刻，看 24 小时里信号的种类和次数。
    """
    e = Physiology({"physio_disease_onset": False})
    b = B.new_body(seed=20261103)
    seen: Counter = Counter()
    for _ in range(24):
        e.step(b, hours=1.0)
        io = ((b.get("derived") or {}).get("intero") or {})
        for s, _v in (io.get("signals") or []):
            if "饿" in s:
                seen["hunger"] += 1
            elif "干" in s or "渴" in s:
                seen["thirst"] += 1
            elif "厕所" in s:
                seen["bladder"] += 1
            elif "大号" in s:
                seen["bowel"] += 1
    for key, least in (("hunger", 2), ("thirst", 1), ("bladder", 2), ("bowel", 1)):
        if seen[key] < least:
            fail(f"一整天只说过 {seen[key]} 次 {key}（至少要 {least} 次）：{dict(seen)}")
    ok(f"一天里有节奏（饿 {seen['hunger']} 次、渴 {seen['thirst']} 次、"
       f"尿意 {seen['bladder']} 次、便意 {seen['bowel']} 次）")


# ----------------------------------------------------------------------
def main() -> None:
    test_catalog_integrity()
    test_catalog_no_dup_name()
    test_catalog_scale()
    test_environment_risk()
    test_hunger_follows_meals()
    test_thirst_appears_overnight()
    test_water_does_not_drift()
    test_bladder_voids_itself()
    test_bowel_is_about_once_a_day()
    test_intero_quiet_when_healthy()
    test_night_settles()
    test_night_record_exists()
    test_debt_deepens_sleep()
    test_alcohol_lightens_sleep()
    test_stress_delays_onset()
    test_one_night_per_night()
    test_sleep_in_reports()
    test_injury_heals()
    test_injury_shows_in_block()
    test_injury_hazard_follows_context()
    test_injury_rate_is_human()
    test_injury_no_duplicate()
    test_age_advances_with_clock()
    test_aging_schedule_is_human()
    test_no_aging_before_its_time()
    test_fitness_capped_by_age()
    test_traits_are_stable()
    test_traits_reach_vitals()
    test_pain_sensitivity_scales_pain()
    test_body_temp_follows_clock()
    test_bp_dips_at_night()
    test_sleep_need_is_personal()
    test_bedtime_follows_chronotype()
    test_night_owl_still_sleeps()
    test_mind_moves_vitals()
    test_mind_saturates()
    test_mind_fades_with_hours()
    test_mind_shifts_pain_threshold()
    test_mind_block_stays_single_line()
    test_a_day_says_something()
    print(f"\n全部通过（{PASS} 项）。")


if __name__ == "__main__":
    main()
