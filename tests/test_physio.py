"""生理侧的回归自测：只验证"能不能自洽"，不验证"医学上对不对"。

跑法：
    python tests/test_physio.py
或：
    pytest tests/test_physio.py -q

这里刻意不测具体数值（比如血红蛋白该是多少），因为那属于参数标定，
每次调参都会变。测的是那些**一旦破了就说明模型逻辑坏了**的约束：
一张化验单内部自洽、急性病会自限、器官坏了药会蓄积、旧存档还能读、
注入块压缩后身体段不被切掉、对外文本里没有不该出现的词。
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physio import Physiology, body as B, const as C, report as R  # noqa: E402
from physio.diseases import DISEASES  # noqa: E402
from physio.drugs import DRUGS  # noqa: E402

PASS = 0


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"[ok] {msg}")


def fail(msg: str) -> None:
    raise AssertionError(msg)


# ----------------------------------------------------------------------
def test_tables() -> None:
    if len(C.LABS) < 120:
        fail(f"检验项太少：{len(C.LABS)}")
    if len(DISEASES) < 280:
        fail(f"疾病库太少：{len(DISEASES)}")
    if len(DRUGS) < 180:
        fail(f"药物库太少：{len(DRUGS)}")
    if len(C.ORGANS) < 25:
        fail(f"器官太少：{len(C.ORGANS)}")

    sys_set = {v[1] for v in C.ORGANS.values()}
    want = {"心血管", "呼吸", "消化", "泌尿", "神经", "内分泌", "免疫",
            "血液", "运动"}
    missing = want - sys_set
    if missing:
        fail(f"缺系统：{missing}")
    ok(f"基础表：{len(C.LABS)} 项检验／{len(DISEASES)} 种疾病／"
       f"{len(DRUGS)} 种药／{len(C.ORGANS)} 个器官／{len(sys_set)} 个系统")

    # 每种疾病引用的指标必须真实存在，否则偏移会静默丢失
    bad = []
    for code, spec in DISEASES.items():
        for lab in (spec.get("labs") or {}):
            if lab not in C.LABS and lab not in C.VITALS:
                bad.append((code, lab))
        for org in (spec.get("org") or {}):
            if org not in C.ORGANS:
                bad.append((code, org))
    if bad:
        fail(f"疾病引用了不存在的指标/器官：{bad[:6]}")
    ok("疾病 → 指标/器官 引用全部有效")


# ----------------------------------------------------------------------
def test_labs_self_consistent() -> None:
    """一张化验单内部不能自相矛盾。"""
    phys = Physiology({"physio_disease_onset": False})
    for preset in ("healthy", "obese", "elderly", "frail", "chronically_ill"):
        b = B.new_body(sex="m", age=55, preset=preset)
        for _ in range(6):
            phys.step(b, 24.0)
        labs, vit = b["labs"], b["vitals"]

        # 声明了却没算出来的指标会静默从报告里消失，必须当场发现
        missing = [k for k in C.LABS if k not in labs]
        if missing:
            fail(f"{preset}: 有 {len(missing)} 项检验未产出：{missing[:6]}")

        ag = labs["Na"] - labs["Cl"] - labs["HCO3"]
        if not (2.0 <= ag <= 30.0):
            fail(f"{preset}: 阴离子间隙 {ag:.1f} 不合理（Na {labs['Na']:.0f} "
                 f"Cl {labs['Cl']:.0f} HCO3 {labs['HCO3']:.0f}）")

        pct = (labs["NEUT_p"] + labs["LYMPH_p"] + labs["MONO_p"]
               + labs["EO_p"] + labs["BASO_p"])
        if pct > 102.0:
            fail(f"{preset}: 白细胞分类合计 {pct:.0f}%")

        if not (30.0 <= labs["SaO2"] <= 100.5):
            fail(f"{preset}: SaO2 {labs['SaO2']:.1f}%")
        if labs["pO2"] < 25.0 or labs["pO2"] > 130.0:
            fail(f"{preset}: pO2 {labs['pO2']:.1f}")
        if not (7.10 <= labs["pH"] <= 7.65):
            fail(f"{preset}: pH {labs['pH']:.2f}")
        if not (5.0 <= labs["eGFR"] <= 145.0):
            fail(f"{preset}: eGFR {labs['eGFR']:.0f}")
        # 碱剩余可以合法为负（碱缺失），其余指标没有负值这回事
        if not (-15.0 <= labs.get("BE", 0.0) <= 15.0):
            fail(f"{preset}: BE {labs.get('BE', 0):.1f} 超出可能范围")
        for k, v in labs.items():
            if v != v:  # NaN
                fail(f"{preset}: {k} 是 NaN")
            if v < -1e-6 and k != "BE":
                fail(f"{preset}: {k} 为负 {v}")
        for k, v in vit.items():
            if v != v:
                fail(f"{preset}: 体征 {k} 是 NaN")
        if not (28.0 <= vit["TEMP"] <= 42.5):
            fail(f"{preset}: 体温 {vit['TEMP']:.1f}")
        if not (35.0 <= vit["HR"] <= 190.0):
            fail(f"{preset}: 心率 {vit['HR']:.0f}")
        if not (60.0 <= vit["SBP"] <= 220.0):
            fail(f"{preset}: 收缩压 {vit['SBP']:.0f}")
    ok("化验单内部自洽（阴离子间隙/分类百分比/血气/eGFR/体征范围）")


def test_reference_direction() -> None:
    """真有病时，该升的指标要升，该降的要降。"""
    phys = Physiology({"physio_disease_onset": False})
    b = B.new_body(sex="m", age=34, preset="healthy")
    phys.step(b, 6.0)
    base = dict(b["labs"])

    B.add_condition(b, "CA-PNEU", "社区获得性肺炎", sev=0.8)
    phys.step(b, 48.0)
    after = b["labs"]

    if after["CRP"] <= base["CRP"] * 2:
        fail(f"肺炎 CRP 未升高：{base['CRP']:.1f} → {after['CRP']:.1f}")
    if after["WBC"] <= base["WBC"]:
        fail("肺炎白细胞未升高")
    if after["NEUT_p"] <= base["NEUT_p"]:
        fail("肺炎中性粒细胞比例未升高")
    if after["pO2"] >= base["pO2"]:
        fail("肺炎氧分压未下降")
    if b["vitals"]["TEMP"] < 37.3:
        fail(f"肺炎没有发热：{b['vitals']['TEMP']:.1f}℃")
    if b["vitals"]["HR"] <= b["vitals"].get("HR", 72) - 1:
        fail("肺炎心率未加快")
    ok(f"肺炎方向正确：CRP {base['CRP']:.1f}→{after['CRP']:.0f}，"
       f"体温 {b['vitals']['TEMP']:.1f}℃，pO2 {base['pO2']:.0f}→{after['pO2']:.0f}")


def test_acute_self_limits() -> None:
    """急性病必须自己好，不能一边长一边掉停在平衡点。"""
    phys = Physiology({"physio_disease_onset": False})
    b = B.new_body(sex="m", age=30, preset="healthy")
    B.add_condition(b, "CA-FLU", "流行性感冒", sev=0.75)
    peak = 0.0
    resolved_at = None
    for day in range(1, 61):
        phys.step(b, 24.0)
        sev = next((float(c["sev"]) for c in b["conditions"] if c["code"] == "CA-FLU"), 0.0)
        peak = max(peak, sev)
        if resolved_at is None and not any(c["code"] == "CA-FLU" for c in b["conditions"]):
            resolved_at = day
    if peak < 0.6:
        fail(f"流感峰值只有 {peak:.2f}")
    if resolved_at is None:
        fail("流感 60 天仍未痊愈")
    dur = DISEASES["CA-FLU"]["dur"] / 24.0
    if resolved_at > dur * 1.9:
        fail(f"流感 {resolved_at} 天才好，dur={dur:.1f} 天")
    ok(f"急性病自限：流感峰值 {peak:.2f}，第 {resolved_at} 天痊愈（dur {dur:.1f} 天）")


def test_chronic_stays() -> None:
    """慢性病不该按急性病的方式自己消失。"""
    phys = Physiology({"physio_disease_onset": False})
    b = B.new_body(sex="m", age=58, preset="healthy")
    B.add_condition(b, "EN-T2DM", "2 型糖尿病", sev=0.4)
    for _ in range(10):
        phys.step(b, 24.0 * 3)
    alive = [c for c in b["conditions"] if c["code"] == "EN-T2DM"]
    if not alive:
        fail("2 型糖尿病 30 天后自己消失了")
    ok(f"慢性病持续存在（2 型糖尿病 sev {float(alive[0]['sev']):.2f}）")


def test_drug_accumulation() -> None:
    """清除器官坏了，同样剂量下药物作用必须更强。"""
    drug = "地高辛"  # 经肾清除、治疗窗窄，最能体现蓄积
    if drug not in DRUGS:
        fail("药库里没有地高辛")
    phys = Physiology({"physio_disease_onset": False})

    def run(kidney: float) -> float:
        b = B.new_body(sex="m", age=60, preset="healthy")
        b["organs"]["kidney"] = kidney
        phys.add_med(b, drug, 1.0)
        for _ in range(4):
            phys.step(b, 12.0)
        return float(b["labs"].get("CREA", 0.0)), float(
            (b.get("derived") or {}).get("drug_load", 0.0))

    _c1, load_ok = run(1.0)
    _c2, load_bad = run(0.30)
    if load_bad <= load_ok * 1.05:
        fail(f"肾功能下降后药物未蓄积：{load_ok:.3f} → {load_bad:.3f}")
    ok(f"肾功能下降时药物蓄积：负荷 {load_ok:.3f} → {load_bad:.3f}")


def test_onset_rate() -> None:
    """发病频率要能当"生活质感"，不能让人长期卧病。"""
    phys = Physiology({"physio_disease_onset": True, "physio_onset_scale": 0.30})
    counts_30, counts_365 = [], []
    for i in range(6):
        b = B.new_body(sex="m" if i % 2 == 0 else "f", age=30 + i * 4,
                       preset="healthy", seed=1000 + i)
        phys.step(b, 24.0 * 30)
        counts_30.append(len([c for c in b["conditions"] if float(c["sev"]) > 0.03]))
        phys.step(b, 24.0 * 335)
        counts_365.append(len([c for c in b["conditions"] if float(c["sev"]) > 0.03]))
    if max(counts_30) > 3:
        fail(f"30 天内活动性疾病过多：{counts_30}")
    if max(counts_365) > 10:
        fail(f"一年内活动性疾病过多：{counts_365}")
    ok(f"发病频率合理：30 天 {counts_30}，一年 {counts_365}")


def test_deterministic() -> None:
    """同一 seed 重放必须得到同一结果，否则没法复现问题。"""
    def run() -> tuple:
        phys = Physiology({"physio_disease_onset": True})
        b = B.new_body(sex="f", age=41, preset="sedentary", seed=777)
        phys.step(b, 24.0 * 45)
        return (round(float(b["labs"]["HGB"]), 3),
                round(float(b["vitals"]["WEIGHT"]), 3),
                tuple(sorted(c["code"] for c in b["conditions"])))

    if run() != run():
        fail("同 seed 两次结果不同")
    ok("确定性重放（同 seed 结果一致）")


def test_old_save() -> None:
    """旧存档（没有 body 或字段残缺）必须能读，且不崩。"""
    phys = Physiology({})
    for raw in ({}, {"v": 1}, {"clock": 48.0, "organs": {"liver": 0.7}},
                {"conditions": [{"code": "NOPE", "sev": 0.5}]}):
        b = B.ensure_body(dict(raw))
        out = phys.step(b, 12.0)
        if not isinstance(out, dict) or "events" not in out:
            fail(f"存档 {raw} 推进失败")
    ok("旧存档/残缺存档兼容（缺失字段自动补齐，未知疾病自动清理）")


def test_couple_scale() -> None:
    """身体→精神的耦合量必须落在精神侧的量纲里，不能把 t3 写成化验值。"""

    class FakeState:
        def __init__(self) -> None:
            self.bio = {"il6": 0.20, "cortisol": 0.35, "norepinephrine": 0.45,
                        "serotonin": 0.55, "bdnf": 0.50, "t3": 0.50}
            self.neuro = {"sleep_pressure": 0.30}

    phys = Physiology({"physio_disease_onset": False})
    b = B.new_body(sex="m", age=30, preset="healthy")
    phys.step(b, 24.0)
    st = FakeState()
    phys.couple(b, st)
    for k, v in st.bio.items():
        if not (0.0 <= v <= 1.0):
            fail(f"couple 把 {k} 写成了 {v}")
    if abs(st.bio["t3"] - 0.50) > 0.12:
        fail(f"健康人 t3 被写偏：{st.bio['t3']:.3f}")
    ok(f"耦合量量纲正确（健康态 t3 {st.bio['t3']:.2f}，il6 {st.bio['il6']:.2f}）")


def test_reports() -> None:
    phys = Physiology({"physio_disease_onset": False})
    b = B.new_body(sex="m", age=34, preset="healthy")
    phys.step(b, 24.0)
    full = R.render_full(b)
    if "参考" not in full:
        fail("体检报告缺少参考区间")
    if R.DISCLAIMER not in full:
        fail("体检报告缺少免责声明")
    for panel_key, panel_name in C.PANELS:
        text = R.render_panel(b, panel_key)
        if panel_key != "vitals" and not text:
            fail(f"检查项「{panel_name}」为空")
    for name, fn in (("生活", R.render_life), ("日志", R.render_log),
                     ("摘要", R.render_summary), ("体征", R.render_vitals)):
        if not fn(b):
            fail(f"{name} 渲染为空")
    sec = R.render_block_section(b)
    if not sec:
        fail("注入段落为空")
    ok(f"报告渲染完整（体检 {len(full)} 字，{len(C.PANELS)} 个检查项）")


def test_block_keeps_physio() -> None:
    """压缩路径必须保住身体段：丢了它，模型就只剩一句诊断可演。"""
    from psyche import narrative
    from psyche.diagnose import diagnose

    class Store:
        def load(self, k):
            return None

        def save(self, *a, **k):
            pass

        def log(self, *a, **k):
            pass

        def events(self, k, limit=15):
            return []

    from psyche.engine import Engine

    cfg = {"default_preset": "healthy", "physio_enabled": True,
           "physio_disease_onset": False, "max_block_chars": 900}
    eng = Engine(cfg, Store())
    st = eng.load("t")
    B.add_condition(st.body, "CA-UTI", "急性膀胱炎", sev=0.7)
    eng.phys.step(st.body, 12.0)
    dx = diagnose(st, cfg)
    block = narrative.render_block(st, dx, cfg)
    if "身体" not in block:
        fail("压缩后身体段丢失")
    if "急性膀胱炎" not in block:
        fail("压缩后没带上正在生的病")
    ok(f"压缩块保住身体段（{len(block)} 字，含当前疾病）")


def test_no_banned_terms() -> None:
    """合规：对外文本里不得出现易引起误解或联想的表述。"""
    banned = ["性交", "阴道", "睾丸", "阴茎", "生殖器", "勃起", "性欲",
              "溢乳", "逆行射精", "梅毒", "呕血", "咯血", "自杀方法"]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hits = []
    for sub in ("physio", "psyche"):
        for fn in os.listdir(os.path.join(root, sub)):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, sub, fn)
            text = open(path, encoding="utf-8").read()
            for w in banned:
                if w in text:
                    hits.append(f"{sub}/{fn}: {w}")
    if hits:
        fail("发现敏感表述：" + "；".join(hits[:8]))
    ok(f"合规扫描通过（{len(banned)} 个词，physio/ 与 psyche/ 全清）")


def test_disclaimer_everywhere() -> None:
    """任何一份完整体检都必须带免责声明。"""
    phys = Physiology({"physio_disease_onset": False})
    b = B.new_body(sex="f", age=70, preset="chronically_ill")
    phys.step(b, 24.0 * 5)
    if R.DISCLAIMER not in R.render_full(b, only_abnormal=True):
        fail("异常项报告缺免责声明")
    if "预后" in R.render_full(b) or "存活" in R.render_full(b):
        fail("报告里出现预后/存活字样")
    ok("免责声明齐备，且不出现预后/存活类表述")


def test_presets_differ() -> None:
    """不同身体底子必须走出不同体型，且都不能漂到荒谬值。

    这一条是为了守住一个具体的坑：设定点回归曾经无条件拉向体脂 1.0，
    于是运动员、久坐者、肥胖者一年后体重几乎一样，预设等于没起作用。
    """
    phys = Physiology({"physio_disease_onset": True})
    weight = {}
    for preset in ("athlete", "healthy", "sedentary", "obese"):
        b = B.new_body(sex="m", age=34, preset=preset, seed=42)
        phys.step(b, 24.0 * 365)
        kg = float(b["vitals"]["WEIGHT"])
        weight[preset] = kg
        if not (45.0 <= kg <= 130.0):
            fail(f"{preset} 一年后体重 {kg:.1f}kg 不合理")
        bmi = float(b["vitals"]["BMI"])
        if not (16.0 <= bmi <= 42.0):
            fail(f"{preset} 一年后 BMI {bmi:.1f} 不合理")
    if not (weight["athlete"] < weight["healthy"] < weight["sedentary"] < weight["obese"]):
        fail("预设体型没拉开：" + "，".join(f"{k} {v:.1f}" for k, v in weight.items()))
    ok("预设体型分化：" + " / ".join(f"{k} {v:.1f}kg" for k, v in weight.items()))


def test_age_declines() -> None:
    """年纪越大，肾功能与血红蛋白越低——但老年不该被算成肾衰。"""
    phys = Physiology({"physio_disease_onset": False})
    rows = []
    for age in (25, 45, 80):
        b = B.new_body(sex="m", age=age, preset="healthy")
        phys.step(b, 48.0)
        rows.append((age, float(b["labs"]["eGFR"]), float(b["labs"]["HGB"])))
    if not (rows[0][1] > rows[1][1] > rows[2][1]):
        fail("eGFR 没有随年龄下降：" + str(rows))
    if rows[2][1] < 45.0:
        fail(f"80 岁健康人 eGFR 只有 {rows[2][1]:.0f}，被算成肾衰了")
    if not (rows[0][2] > rows[2][2]):
        fail("血红蛋白没有随年龄下降")
    ok("年龄衰退方向正确（eGFR " + " → ".join(f"{r[1]:.0f}" for r in rows) + "）")


def test_fresh_body_reports() -> None:
    """刚建好的身体一次都没 step 过，体检也必须出数。

    这里卡的是真实故障：新会话里第一句就发 /心理 体检，报告出现
    「体重 0.0kg」「生命体征：未记录」——因为 labs/vitals 只在推进之后才填。
    """
    from psyche import narrative
    from psyche.engine import Engine

    class Store:
        def load(self, k):
            return None

        def save(self, *a, **k):
            pass

        def log(self, *a, **k):
            pass

        def events(self, k, limit=15):
            return []

    cfg = {"default_preset": "healthy", "physio_sex": "f", "physio_age": 18,
           "physio_preset": "healthy"}
    eng = Engine(cfg, Store())
    st = eng.load("fresh")          # 不经过任何一轮对话

    if len(st.body.get("labs") or {}) < len(C.LABS):
        fail(f"初生身体只算了 {len(st.body.get('labs') or {})}/{len(C.LABS)} 项检验")
    if not st.body.get("vitals"):
        fail("初生身体没有生命体征")

    report = eng.phys_report("fresh")
    for bad in ("体重 0.0kg", "BMI 0.0", "未记录"):
        if bad in report:
            fail(f"首次体检出现「{bad}」")
    if "参考" not in report:
        fail("首次体检没有参考区间")

    # 用户版不加模型的表演指令
    text = narrative.render_body_section(st)
    if "神经电与环路" in text:
        fail("/心理 生理 把给模型的指令也发给了用户")
    if "第 1 天" not in text:
        fail("/心理 生理 缺少时间与人物行")

    ok(f"首次体检即出数（{len(st.body['labs'])} 项检验，{len(report)} 字）")


def main() -> None:
    test_tables()
    test_labs_self_consistent()
    test_reference_direction()
    test_acute_self_limits()
    test_chronic_stays()
    test_drug_accumulation()
    test_onset_rate()
    test_deterministic()
    test_presets_differ()
    test_age_declines()
    test_old_save()
    test_couple_scale()
    test_reports()
    test_fresh_body_reports()
    test_block_keeps_physio()
    test_no_banned_terms()
    test_disclaimer_everywhere()
    print(f"\n全部通过（{PASS} 项）。")


if __name__ == "__main__":
    main()
