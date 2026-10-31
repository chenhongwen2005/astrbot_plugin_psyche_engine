"""检验值与生命体征的推导。

核心原则：**化验单不是随机数表，而是器官功能的投影。**

所以每个指标要么由器官/营养状态算出（`_organ_driven`），要么由疾病与药物
的偏移叠加（diseases.py / drugs.py 里声明的 signature），最后再做一次
生理一致性收敛（eGFR 由肌酐反算、SaO2 由氧分压按氧解离曲线算、pH 用
Henderson-Hasselbalch、LDL 用 Friedewald）。

这样做的直接好处：把一个健康人放进高原、让他失血、给他上激素，化验单会
自己往该去的方向走，而不需要为每种组合预先写死。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .const import LABS, VITALS, ref_range
from . import body as B
from .diseases import DISEASES
from .drugs import DRUGS

# 各检验项的生理上下限（防止叠加出不可能的值）
HARD_LIMITS: Dict[str, Tuple[float, float]] = {
    "HGB": (25.0, 230.0), "WBC": (0.05, 120.0), "PLT": (2.0, 1600.0),
    "CREA": (20.0, 1600.0), "BUN": (0.5, 90.0), "K": (1.2, 9.5),
    "Na": (105.0, 175.0), "Cl": (70.0, 140.0), "Ca": (0.9, 4.5),
    "P": (0.2, 4.0), "Mg": (0.2, 3.0), "HCO3": (4.0, 45.0),
    "FPG": (0.8, 40.0), "HbA1c": (3.0, 18.0), "ALT": (1.0, 12000.0),
    "AST": (1.0, 12000.0), "TBIL": (1.0, 700.0), "ALB": (8.0, 62.0),
    "pH": (6.6, 7.8), "pCO2": (8.0, 120.0), "pO2": (18.0, 640.0),
    "SaO2": (30.0, 100.0), "LAC": (0.2, 30.0), "TEMP": (32.0, 43.0),
    "HR": (20.0, 240.0), "SBP": (40.0, 280.0), "DBP": (20.0, 170.0),
    "RR": (4.0, 60.0), "SpO2": (35.0, 100.0),
    "TSH": (0.001, 200.0), "FT4": (0.5, 100.0), "FT3": (0.5, 40.0),
    "COR_8am": (10.0, 3000.0), "TST": (0.1, 80.0), "PRL": (0.5, 2000.0),
    "INS": (0.2, 400.0), "DD": (0.0, 40.0), "INR": (0.7, 12.0),
}


# 按定义可以为负的化验项（碱剩余、阴离子间隙）。其余一律不小于 0。
NEG_OK = frozenset({"BE", "AG"})


def _mid(key: str, sex: str = "m") -> float:
    lo, hi = ref_range(key, sex)
    return (lo + hi) / 2.0


def _clip(key: str, v: float) -> float:
    lo, hi = HARD_LIMITS.get(key, (-1e9, 1e9))
    return max(lo, min(hi, v))


def _organ_driven(body: Dict[str, Any], labs: Dict[str, float]) -> None:
    """由器官功能与营养状态算出的那部分。"""
    sex = body.get("sex", "m")
    age = float(body.get("age", 30.0))
    kidney = B.organ(body, "kidney")
    tubule = B.organ(body, "kidney_tubule")
    liver = B.organ(body, "liver")
    marrow = B.organ(body, "marrow")
    thyroid = B.organ(body, "thyroid")
    adrenal = B.organ(body, "adrenal")
    gonad = B.organ(body, "gonad")
    muscle = B.organ(body, "muscle")
    lungs = B.organ(body, "lungs")
    sens = B.organ(body, "fat_sens")
    pendo = B.organ(body, "pancreas_endo")
    fat = B.organ(body, "fat")

    # ---- 红细胞系：骨髓 + 铁/B12/叶酸 + 肾 EPO + 失血/溶血（后两者由疾病偏移负责）
    fe = min(1.0, B.life(body, "iron") * 1.05)
    b12 = min(1.0, B.life(body, "b12") * 1.05)
    fol = min(1.0, B.life(body, "folate") * 1.05)
    nut = min(fe, min(b12, fol))
    epo = 0.55 + 0.45 * kidney
    hgb_base = 145.0 if sex == "m" else 130.0
    labs["HGB"] = hgb_base * (0.55 + 0.45 * marrow) * (0.70 + 0.30 * nut) * epo
    labs["MCV"] = 88.0 * (0.78 + 0.22 * fe) * (0.90 + 0.10 * min(b12, fol))
    labs["MCH"] = 30.0 * (0.80 + 0.20 * fe)
    labs["MCHC"] = 335.0
    labs["RBC"] = labs["HGB"] / max(12.0, labs["MCH"])
    labs["HCT"] = labs["HGB"] / 3.35
    labs["RDW"] = 12.8 + 6.0 * (1.0 - fe) + 3.0 * (1.0 - b12)
    labs["RET_p"] = 1.0 * (0.4 + 0.6 * marrow)
    labs["PLT"] = 230.0 * (0.55 + 0.45 * marrow)
    # 平均血小板体积：骨髓产量不足时新生成的血小板偏大（年轻血小板体积大）
    labs["MPV"] = 10.2 + 2.2 * max(0.0, 1.0 - marrow)

    # ---- 白细胞：骨髓 + 免疫 + 炎症（炎症部分后面叠加）
    labs["WBC"] = 6.2 * (0.55 + 0.45 * B.organ(body, "immune")) * (0.7 + 0.3 * marrow)
    labs["NEUT_p"] = 58.0
    labs["LYMPH_p"] = 31.0
    labs["MONO_p"] = 5.5
    labs["EO_p"] = 2.2
    labs["BASO_p"] = 0.4

    # ---- 肝：合成 + 解毒
    labs["ALT"] = 20.0 + 70.0 * max(0.0, 1.0 - liver) ** 1.4
    labs["ALT"] += 12.0 * max(0.0, B.life(body, "alcohol") - 1.0)
    labs["AST"] = 19.0 + 55.0 * max(0.0, 1.0 - liver) ** 1.4
    labs["AST"] += 8.0 * max(0.0, B.life(body, "alcohol") - 1.0)
    labs["GGT"] = 24.0 + 40.0 * max(0.0, 1.0 - liver) + 22.0 * max(0.0, B.life(body, "alcohol") - 0.5)
    labs["ALP"] = 75.0 + 45.0 * max(0.0, 1.0 - liver)
    labs["TBIL"] = 11.0 + 26.0 * max(0.0, 1.0 - liver) ** 1.5
    labs["ALB"] = 45.0 * (0.45 + 0.55 * liver) * (0.85 + 0.15 * B.life(body, "protein"))
    labs["TP"] = labs["ALB"] + 28.0
    labs["GLB"] = labs["TP"] - labs["ALB"]
    labs["CHE"] = 8000.0 * (0.4 + 0.6 * liver)
    labs["TBA"] = 4.0 + 20.0 * max(0.0, 1.0 - liver)
    # 血氨：肝功能下降时清除不足；上消化道出血与高蛋白摄入也会推高
    labs["AMM"] = 13.0 + 45.0 * max(0.0, 1.0 - liver) ** 2

    # ---- 肾：滤过 + 小管
    crea_base = 78.0 if sex == "m" else 63.0
    # 肌酐产量随肌肉量走：老年人肌肉少，同样的 GFR 下肌酐也更低。
    # 少写这一项，70 岁以上的人会被系统性地判成肾功能不全。
    crea_base *= 0.55 + 0.45 * min(1.20, muscle)
    labs["CREA"] = crea_base / max(0.14, kidney ** 1.15)
    labs["BUN"] = 4.6 / max(0.12, kidney) + 1.6 * max(0.0, B.life(body, "protein") - 0.85)
    labs["UA"] = (330.0 if sex == "m" else 260.0) / max(0.3, kidney) * (0.9 + 0.2 * fat)
    labs["CysC"] = 0.80 / max(0.15, kidney ** 1.2)
    labs["K"] = 4.2 + 0.55 * (1.0 - tubule)
    labs["Na"] = 141.0 - 2.5 * (1.0 - tubule) + 1.5 * (B.life(body, "salt") - 1.0)
    labs["HCO3"] = 25.0 - 4.5 * (1.0 - tubule)
    # 氯按「钠 − 碳酸氢根 − 阴离子间隙」反推，保证一张单子内部自洽
    labs["Cl"] = labs["Na"] - labs["HCO3"] - 12.0
    labs["Ca"] = 2.32
    labs["P"] = 1.10 + 0.25 * (1.0 - kidney)
    labs["Mg"] = 0.88
    labs["U_SG"] = 1.018 * (0.85 + 0.15 * tubule) * (0.9 + 0.1 * B.life(body, "water"))
    labs["U_PRO"] = 0.03 + 0.35 * max(0.0, 1.0 - kidney) ** 2
    labs["U_GLU"] = 0.0
    labs["U_BLD"] = 0.0
    labs["U_WBC"] = 0.6
    labs["U_KET"] = 0.0

    # ---- 糖代谢：敏感性 × β 细胞 × 肾上腺
    fp = 4.9 * (1.0 / max(0.30, sens)) ** 0.45
    fp *= (1.0 / max(0.20, pendo)) ** 0.55
    fp += 0.35 * max(0.0, B.life(body, "sugar") - 1.0)
    fp += 0.30 * max(0.0, B.life(body, "stress") - 0.5)
    labs["FPG"] = fp
    labs["HbA1c"] = 4.6 + (fp - 4.9) * 0.55
    labs["INS"] = 8.0 * (1.0 / max(0.25, sens)) ** 1.1
    labs["CPEP"] = 1.0 * max(0.15, pendo)
    labs["GA"] = 13.5 + (fp - 4.9) * 0.8

    # ---- 血脂：肝合成 + 脂肪量 + 饮食
    labs["TC"] = 4.3 + 0.9 * max(0.0, fat - 0.85) + 0.35 * (B.life(body, "satfat") - 1.0)
    labs["TG"] = 1.1 + 1.1 * max(0.0, fat - 0.85) + 0.30 * (B.life(body, "sugar") - 1.0)
    labs["LDL"] = 2.4 + 0.6 * max(0.0, fat - 0.85) + 0.25 * (B.life(body, "satfat") - 1.0)
    labs["HDL"] = 1.35 - 0.25 * max(0.0, fat - 0.85) + 0.08 * (B.life(body, "activity") - 1.0)
    labs["ApoB"] = 0.85 + 0.15 * max(0.0, fat - 0.85)
    labs["Lp(a)"] = 15.0

    # ---- 甲状腺：TSH 与 FT4 反向
    tfunc = max(0.05, thyroid)
    labs["FT4"] = 17.0 * (0.55 + 0.45 * tfunc)
    labs["FT3"] = 4.9 * (0.55 + 0.45 * tfunc)
    labs["TT4"] = 120.0 * (0.55 + 0.45 * tfunc)
    labs["TSH"] = 2.0 / max(0.12, tfunc) ** 1.6
    labs["TPOAb"] = 15.0
    labs["TgAb"] = 20.0
    labs["Tg"] = 20.0

    # ---- 其他内分泌
    labs["COR_8am"] = 380.0 * (0.35 + 0.65 * adrenal) * (0.85 + 0.3 * B.life(body, "stress"))
    labs["ACTH"] = 30.0 / max(0.30, adrenal)
    labs["ALD"] = 120.0 / max(0.3, kidney)
    labs["RENIN"] = 1.2 * max(0.3, kidney)
    # 醛固酮/肾素比值（ARR）：肾灌注不足时肾素先升、醛固酮随后跟上，
    # 所以比值随肾功能下降而轻度上升；这里只需要方向对、量级合理。
    labs["ARR"] = 8.0 + 26.0 * max(0.0, 1.0 - kidney)
    labs["TST"] = (18.0 if sex == "m" else 1.2) * (0.35 + 0.65 * gonad) / (1.0 + 0.4 * max(0.0, fat - 1.0))
    labs["E2"] = (120.0 if sex == "m" else 260.0) * (0.35 + 0.65 * gonad)
    labs["PRL"] = 10.0
    labs["IGF1"] = 170.0 * (0.5 + 0.5 * thyroid)
    labs["PTH"] = 30.0 + 40.0 * max(0.0, 1.0 - kidney)
    labs["VD_25"] = 42.0 + 45.0 * min(1.0, B.life(body, "vitd")) * (0.6 + 0.4 * min(1.0, B.life(body, "sun") / 25.0))
    labs["GH"] = 1.0
    labs["LH"] = 5.0
    labs["FSH"] = 6.0
    labs["ADH_osm"] = 780.0 * (0.6 + 0.4 * tubule)

    # ---- 营养
    labs["FERR"] = (110.0 if sex == "m" else 65.0) * (0.25 + 0.75 * fe) * (1.0 + 0.5 * (1.0 - fe))
    labs["FE"] = 18.0 * (0.4 + 0.6 * fe)
    labs["TSAT"] = 30.0 * (0.35 + 0.65 * fe)
    labs["B12"] = 380.0 * (0.35 + 0.65 * b12)
    labs["FOL"] = 22.0 * (0.35 + 0.65 * fol)
    labs["PREALB"] = 300.0 * (0.4 + 0.6 * B.life(body, "protein"))

    # ---- 心肌与肌肉
    labs["CK"] = 110.0 * (0.5 + 0.5 * max(0.3, 1.0 - 0.5 * (1.0 - muscle)))
    labs["CKMB"] = 8.0
    labs["LDH"] = 180.0
    labs["hsTnI"] = 3.0
    labs["NTproBNP"] = 40.0 + 260.0 * max(0.0, 1.0 - B.organ(body, "heart"))
    labs["MYO"] = 30.0

    # ---- 凝血
    labs["PT"] = 12.5 / max(0.25, B.organ(body, "coag"))
    labs["APTT"] = 33.0 / max(0.3, B.organ(body, "coag"))
    labs["FIB"] = 3.0 * (0.5 + 0.5 * B.organ(body, "coag"))
    labs["DD"] = 0.22
    labs["AT3"] = 100.0
    labs["vWF"] = 100.0

    # ---- 血气：肺 + 海拔
    alt = B.env(body, "altitude")
    labs["pO2"] = 98.0 * (0.55 + 0.45 * lungs) - 0.028 * max(0.0, alt - 100.0)
    labs["pCO2"] = 40.0 + 6.0 * max(0.0, 1.0 - lungs)
    labs["SaO2"] = 0.0     # 后面由 pO2 反算
    labs["LAC"] = 1.0 + 0.8 * max(0.0, 1.0 - B.organ(body, "heart")) \
        + 0.5 * max(0.0, 1.0 - lungs)
    labs["BE"] = 0.0

    # ---- 免疫
    labs["IgG"] = 11.0 * (0.45 + 0.55 * B.organ(body, "immune"))
    labs["IgA"] = 2.1 * (0.5 + 0.5 * B.organ(body, "immune"))
    labs["IgM"] = 1.2 * (0.5 + 0.5 * B.organ(body, "immune"))
    labs["IgE"] = 40.0
    labs["C3"] = 1.25
    labs["C4"] = 0.25
    labs["CD4"] = 900.0 * (0.5 + 0.5 * B.organ(body, "immune"))
    labs["CD8"] = 520.0
    labs["CD4_CD8"] = labs["CD4"] / max(50.0, labs["CD8"])
    labs["RF"] = 9.0
    labs["ASO"] = 60.0
    labs["ANA"] = 0.15
    labs["ANCA"] = 0.10
    labs["CCP"] = 5.0
    labs["IgG4"] = 0.4
    labs["ACE"] = 32.0

    # ---- 胰腺与肿瘤标志物
    labs["AMY"] = 62.0
    labs["LIP"] = 120.0
    labs["AFP"] = 3.0
    labs["CA125"] = 12.0
    labs["CA199"] = 15.0
    labs["CEA"] = 1.8
    labs["CALC"] = 3.0
    labs["CGA"] = 45.0
    labs["PSA"] = 1.2 if sex == "m" else 0.0
    labs["PHE"] = 62.0
    labs["HCY"] = 9.5

    # ---- 炎症基线
    labs["CRP"] = 1.2
    labs["hsCRP"] = 0.8
    labs["ESR"] = 8.0 + 0.35 * max(0.0, age - 40.0)


def _apply_conditions(body: Dict[str, Any], labs: Dict[str, float],
                      vitals: Dict[str, float], derived: Dict[str, Any]) -> None:
    inflam = 0.0
    fever = 0.0
    pain = 0.0
    for c in B.alive_conditions(body):
        spec = DISEASES.get(c["code"])
        if not spec:
            continue
        sev = float(c.get("sev", 0.0))
        treated = 1.0 - 0.55 * float(c.get("treat_effect", 0.0))
        k = sev * treated
        for lab, (delta, mode) in (spec["labs"] or {}).items():
            # 疾病表里也写了 SpO2 / SBP / HR 这类体征：它们不在 LABS 里，
            # 一律走 vitals，否则会以检验项的身份写进化验单，报告里看不到，
            # 低氧和低血压就白算了。
            tgt = vitals if (lab in vitals and lab not in LABS) else labs
            if mode == "mul":
                cur = tgt.get(lab, 0.0) or 1.0
                tgt[lab] = cur * (1.0 + delta) ** (k * 3.0)
            else:
                tgt[lab] = tgt.get(lab, 0.0) + delta * k
        inflam += float(spec.get("inflam", 0.0)) * k
        fever += float(spec.get("fever", 0.0)) * k
        pain += float(spec.get("pain", 0.0)) * k
    derived["inflammation"] = min(1.0, inflam)
    derived["fever_drive"] = min(1.0, fever)
    derived["pain_drive"] = min(1.0, pain)

    # 炎症对炎症指标与白细胞的回写
    labs["CRP"] = labs.get("CRP", 1.0) + 70.0 * derived["inflammation"]
    labs["hsCRP"] = labs.get("hsCRP", 0.8) + 45.0 * derived["inflammation"]
    labs["ESR"] = labs.get("ESR", 8.0) + 45.0 * derived["inflammation"]
    labs["FIB"] = labs.get("FIB", 3.0) + 1.5 * derived["inflammation"]
    labs["DD"] = labs.get("DD", 0.2) + 0.6 * derived["inflammation"]
    labs["WBC"] = labs.get("WBC", 6.0) * (1.0 + 0.45 * derived["inflammation"])
    labs["NEUT_p"] = labs.get("NEUT_p", 58.0) + 18.0 * derived["inflammation"]
    labs["LYMPH_p"] = max(2.0, labs.get("LYMPH_p", 31.0) - 12.0 * derived["inflammation"])
    # 分类百分比是一个整体，各项之和不能超过 100
    _pct = ("NEUT_p", "LYMPH_p", "MONO_p", "EO_p", "BASO_p")
    _tot = sum(float(labs.get(k, 0.0)) for k in _pct)
    if _tot > 99.0:
        for k in _pct:
            labs[k] = float(labs.get(k, 0.0)) * 99.0 / _tot


def _apply_drugs(body: Dict[str, Any], labs: Dict[str, float],
                 vitals: Dict[str, float], derived: Dict[str, Any]) -> None:
    clock = float(body.get("clock", 0.0))
    notes: List[str] = []
    for m in body.get("meds") or []:
        spec = DRUGS.get(m.get("name", ""))
        if not spec:
            continue
        on_h = clock - float(m.get("start_h", clock))
        if on_h <= 0:
            continue
        # 一阶起效：24 小时达 63%，与"当天起效"的临床印象一致
        r = 1.0 - math.exp(-on_h / 24.0)
        dose = float(m.get("dose", 1.0))
        # 清除器官受损时蓄积
        clr = spec.get("clear", "liver")
        acc = 1.0
        if clr in ("liver", "both"):
            acc = max(acc, 1.0 + 0.8 * (1.0 - B.organ(body, "liver")))
        if clr in ("kidney", "both"):
            acc = max(acc, 1.0 + 0.9 * (1.0 - B.organ(body, "kidney")))
        amp = r * dose * acc
        for lab, (delta, mode) in (spec["labs"] or {}).items():
            tgt = vitals if (lab in vitals and lab not in LABS) else labs
            if mode == "mul":
                tgt[lab] = (tgt.get(lab, 0.0) or 1.0) * (1.0 + delta) ** (amp * 2.0)
            else:
                tgt[lab] = tgt.get(lab, 0.0) + delta * amp
        derived.setdefault("drug_load", 0.0)
        derived["drug_load"] += amp * 0.1
        if acc > 1.25 and amp > 0.3:
            notes.append(f"{m.get('name')} 因清除器官功能下降而蓄积")
    derived["drug_notes"] = notes


def _consistency(body: Dict[str, Any], labs: Dict[str, float],
                 vitals: Dict[str, float],
                 derived: Dict[str, Any] | None = None) -> None:
    """把派生指标算回去，保证一张化验单内部自洽。"""
    # eGFR：CKD-EPI 2021（去掉种族项）
    sex = body.get("sex", "m")
    age = float(body.get("age", 30.0))
    scr = max(0.2, labs["CREA"] / 88.4)          # mg/dL
    k = 0.9 if sex == "m" else 0.7
    a = -0.302 if sex == "m" else -0.241
    egfr = 142.0 * (min(scr / k, 1.0) ** a) * (max(scr / k, 1.0) ** -1.200) \
        * (0.9938 ** age) * (1.012 if sex == "f" else 1.0)
    labs["eGFR"] = max(3.0, min(140.0, egfr))

    # 阴离子间隙与渗透压
    labs["AG"] = labs["Na"] - labs["Cl"] - labs["HCO3"]
    labs["OSM"] = 2.0 * labs["Na"] + labs["FPG"] + labs["BUN"]

    # HOMA-IR
    labs["HOMA_IR"] = max(0.1, labs["FPG"] * labs["INS"] / 22.5)

    # LDL：Friedewald（TG < 4.5 时可靠）
    if labs["TG"] < 4.5:
        labs["LDL"] = max(0.3, labs["TC"] - labs["HDL"] - labs["TG"] / 2.2)
    else:
        labs["LDL"] = max(0.3, labs["TC"] - labs["HDL"] - 0.8)

    # 氧饱和度：由氧分压按氧解离曲线反算（Hill 方程，n=2.7，P50=26.6）
    po2 = max(10.0, labs["pO2"])
    labs["SaO2"] = 100.0 / (1.0 + (26.6 / po2) ** 2.7)
    labs["SaO2"] = min(100.0, labs["SaO2"])
    vitals["SpO2"] = min(100.0, labs["SaO2"] - 1.0)

    # pH：Henderson-Hasselbalch
    hco3 = max(2.0, labs["HCO3"])
    pco2 = max(5.0, labs["pCO2"])
    labs["pH"] = 6.1 + math.log10(hco3 / (0.0301 * pco2))
    labs["BE"] = (hco3 - 24.8) + 16.2 * (labs["pH"] - 7.40)

    # INR 与 PT 同源
    labs["INR"] = 1.0 * (labs["PT"] / 12.5) ** 1.15

    # 胆红素拆分与白/球比
    labs["DBIL"] = labs["TBIL"] * 0.32
    labs["IBIL"] = labs["TBIL"] - labs["DBIL"]
    labs["GLB"] = max(12.0, labs["TP"] - labs["ALB"])

    # 体温：由炎症/感染驱动（疾病层算好的 fever_drive），这里回写到体征。
    # 不能线性映射——线性会把普通感冒和流感挤在同一条线上。真实情况是
    # 低驱动基本不烧（<37.2），过了阈值才陡升，重症能到 40℃ 以上。
    fd = float(derived.get("fever_drive", 0.0)) if derived else 0.0
    ramp = max(0.0, fd - 0.12) / 0.88
    base_t = 36.5 + 3.5 * (ramp ** 1.25)
    base_t = min(40.6, base_t)
    vitals["TEMP"] = base_t
    # 体温每升 1℃ 心率约增 10 次
    vitals["HR"] = float(vitals.get("HR", 72)) + 10.0 * max(0.0, base_t - 36.8)
    # 疼痛与发热都会推高血压
    vitals["SBP"] = float(vitals.get("SBP", 115)) + 6.0 * max(0.0, float(derived.get("pain_drive", 0.0)) - 0.4)

    # 血气与体温的耦合：高热时氧分压略降
    fever = max(0.0, vitals.get("TEMP", 36.6) - 37.0)
    labs["pO2"] = max(20.0, labs["pO2"] - 3.0 * fever)
    labs["LAC"] = labs["LAC"] + 0.25 * fever
    labs["SaO2"] = 100.0 / (1.0 + (26.6 / max(10.0, labs["pO2"])) ** 2.7)
    vitals["SpO2"] = min(100.0, labs["SaO2"] - 1.0)

    # 血细胞比容与血红蛋白同步
    labs["HCT"] = labs["HGB"] / 3.35
    labs["RBC"] = labs["HGB"] / max(12.0, labs["MCH"])


def _vitals(body: Dict[str, Any], labs: Dict[str, float],
            derived: Dict[str, Any]) -> Dict[str, float]:
    sex = body.get("sex", "m")
    age = float(body.get("age", 30.0))
    fitness = B.life(body, "fitness")
    hr = 72.0 - 12.0 * (fitness - 0.5)
    hr += 0.16 * max(0.0, 37.0 - 0.0) * 0.0  # 占位，保持初值可读
    hr += 0.9 * max(0.0, (B.bmi(body) - 25.0))
    hr += 0.35 * max(0.0, age - 50.0) * 0.6

    sbp = 108.0 + 0.38 * max(0.0, age - 20.0)
    sbp += 0.9 * max(0.0, B.bmi(body) - 24.0)
    sbp += 3.0 * max(0.0, B.life(body, "salt") - 1.0)
    sbp -= 6.0 * (fitness - 0.5)
    dbp = 68.0 + 0.16 * max(0.0, age - 20.0) + 0.5 * max(0.0, B.bmi(body) - 24.0)

    h_m = float(body.get("height", 172.0)) / 100.0
    fat = max(0.3, min(1.8, B.organ(body, "fat")))
    weight = 22.5 * h_m * h_m * (0.55 + 0.45 * fat)
    weight *= 1.0 + 0.06 * max(0.0, B.life(body, "salt") - 1.0)
    bmi_v = weight / (float(body.get("height", 172.0)) / 100.0) ** 2

    v = {
        "HR": hr, "SBP": sbp, "DBP": dbp, "RR": 15.0,
        # 体温与疼痛的疾病分量在 compute() 里统一叠加：那时 fever_drive /
        # pain_drive 才算出来，在这里读只能读到 0，等于永远不发烧、永远不疼。
        "TEMP": 36.55,
        "SpO2": 97.5, "WEIGHT": weight, "BMI": bmi_v,
        "WAIST": (bmi_v - 20.0) * 2.1 + 66.0,
        "PAIN": 0.0,
    }
    return v


def compute(body: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, Any]]:
    """算出一整套指标。返回 (labs, vitals, derived)。"""
    labs: Dict[str, float] = {}
    _organ_driven(body, labs)
    vitals = _vitals(body, labs, {})
    derived: Dict[str, Any] = {}
    _apply_conditions(body, labs, vitals, derived)
    # 发热、疼痛、失血/低氧对心率呼吸的连带影响，只能在疾病偏移之后叠加：
    # 放在 _vitals() 里读到的 fever_drive 还是 0，读到的 HGB 还是病前的值。
    sex = body.get("sex", "m")
    vitals["TEMP"] += 0.85 * float(derived.get("fever_drive", 0.0))
    vitals["PAIN"] = min(10.0, float(vitals.get("PAIN", 0.0))
                         + 8.0 * float(derived.get("pain_drive", 0.0)))
    vitals["HR"] += 12.0 * max(0.0, 1.0 - labs["HGB"] / (140.0 if sex == "m" else 125.0))
    vitals["RR"] += 4.0 * max(0.0, 1.0 - labs["pO2"] / 95.0)
    _apply_drugs(body, labs, vitals, derived)
    _consistency(body, labs, vitals, derived)

    # 硬限幅
    for k in list(labs):
        if k in HARD_LIMITS:
            labs[k] = _clip(k, labs[k])
    # 化验值不会为负。药物的绝对减量能把 PSA、GGT、CRP 直接减到 0 以下，
    # 报出「-54 U/L」比不给数据更糟。碱剩余与阴离子间隙按定义可以为负，放过。
    for k in list(labs):
        if k not in NEG_OK and labs[k] < 0.0:
            labs[k] = 0.0
    for k in list(vitals):
        if k in HARD_LIMITS:
            vitals[k] = _clip(k, vitals[k])

    derived["abnormal"] = abnormal_items(body, labs, vitals)
    derived["organ_failure"] = organ_failure(body)
    derived["symptoms"] = symptoms(body)
    derived["dysfunction"] = dysfunction_score(body)
    return labs, vitals, derived


# ----------------------------------------------------------------------
# 异常判定与读单
# ----------------------------------------------------------------------
def is_abnormal(body: Dict[str, Any], key: str, value: float) -> Tuple[bool, str]:
    if key in VITALS:
        _zh, _u, lo, hi = VITALS[key]
        zero_ok = key in ("PAIN",)
    else:
        if key not in LABS:
            return False, ""
        lo, hi = ref_range(key, body.get("sex", "m"))
        zero_ok = lo <= 0.0
    # 允许 10% 的边缘容差，避免所有指标都在"擦边异常"
    tol_lo = lo - (0.0 if zero_ok else (hi - lo) * 0.02)
    tol_hi = hi + (hi - lo) * 0.02
    if value < tol_lo:
        return True, "low"
    if value > tol_hi:
        return True, "high"
    return False, ""


def abnormal_items(body: Dict[str, Any], labs: Dict[str, float],
                   vitals: Dict[str, float]) -> List[Dict[str, Any]]:
    out = []
    for k, v in labs.items():
        ab, d = is_abnormal(body, k, v)
        if ab:
            out.append({"key": k, "dir": d, "value": v, "panel": LABS[k][5]
                        if k in LABS else "其他"})
    for k, v in vitals.items():
        if k in ("WEIGHT", "BMI", "WAIST"):
            continue
        ab, d = is_abnormal(body, k, v)
        if ab:
            out.append({"key": k, "dir": d, "value": v, "panel": "生命体征"})
    return out


def organ_failure(body: Dict[str, Any]) -> List[Tuple[str, float]]:
    from .const import ORGANS
    out = []
    for o, fn in B.organ(body, "x") if False else body.get("organs", {}).items():
        if o in ("fat", "fat_sens"):
            continue
        if fn < 0.55:
            out.append((ORGANS[o][0], fn))
    out.sort(key=lambda t: t[1])
    return out


def symptoms(body: Dict[str, Any]) -> List[Tuple[str, float]]:
    """当前主观症状（去重，按强度降序）。"""
    agg: Dict[str, float] = {}
    for c in B.alive_conditions(body):
        spec = DISEASES.get(c["code"])
        if not spec:
            continue
        sev = float(c.get("sev", 0.0))
        for s in spec["sx"]:
            agg[s] = max(agg.get(s, 0.0), min(1.0, sev * 1.2))
    # 生活方式导致的非特异不适
    if B.life(body, "sleep_debt") > 8:
        agg["白天困倦、注意力涣散"] = min(1.0, B.life(body, "sleep_debt") / 30.0)
    if B.life(body, "water") < 0.6:
        agg["口渴、尿色深"] = min(1.0, (0.6 - B.life(body, "water")) * 3.0)
    if B.life(body, "kcal") < 0.6:
        agg["饥饿感、乏力"] = min(1.0, (0.6 - B.life(body, "kcal")) * 3.0)
    out = sorted(agg.items(), key=lambda kv: -kv[1])
    return out[:12]


def dysfunction_score(body: Dict[str, Any]) -> float:
    """0..1 的总体失能度：器官 + 症状 + 炎症共同决定。"""
    organ_pen = 0.0
    n = 0
    for o, fn in (body.get("organs") or {}).items():
        if o in ("fat", "fat_sens"):
            continue
        organ_pen += max(0.0, 1.0 - fn)
        n += 1
    organ_pen = organ_pen / max(1, n)
    sx = B.alive_conditions(body)
    sx_load = min(1.0, sum(float(c.get("sev", 0)) for c in sx) / 2.5)
    return min(1.0, 0.55 * organ_pen * 2.2 + 0.30 * sx_load
               + 0.15 * min(1.0, B.life(body, "sleep_debt") / 20.0))
