"""药物库（全身用药）。

与 psyche/pharm.py 的关系：
  psyche/pharm.py 管精神科药物对**神经递质与精神症状**的效应（那是它的主场）；
  physio/drugs.py 管所有药物对**身体**的效应——靶器官、化验值、代谢清除。
  精神科药物在这里也有一份，因为奥氮平会升血糖血脂、锂盐会伤肾、氯丙嗪会降白细胞，
  这些在精神科模块里不建模，但对"完整体检"是必须的。

字段：
    cls      药理类别
    route    给药途径
    org      用药期间对器官功能的影响（负值＝损害，正值＝改善）
    labs     对化验值的影响，(偏移, "add"/"mul")
    side     副作用（主观症状），进注入块
    ind      适应症（physio.diseases 的疾病代码）
    clear    主要清除途径：liver / kidney / both —— 器官功能下降时药物蓄积、毒性放大
    inter    重要相互作用（仅记录，用于提示，不做动力学）
    note     一句话说明

刻意保留的两类"代价"：
  1) 真正会致病的药：NSAID 伤胃伤肾、糖皮质激素升糖降免疫、化疗骨髓抑制；
  2) 需要监测的药：氯氮平查血常规、锂盐查浓度、胺碘酮查甲功。
不建模这两类，"吃药"就变成纯收益，模拟立刻失真。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

DRUGS: Dict[str, Dict[str, Any]] = {}


def K(
    name: str,
    cls: str,
    *,
    route: str = "口服",
    org: Optional[Dict[str, float]] = None,
    labs: Optional[Dict[str, Tuple[float, str]]] = None,
    side: Optional[List[str]] = None,
    ind: Optional[List[str]] = None,
    clear: str = "liver",
    inter: Optional[List[str]] = None,
    note: str = "",
) -> None:
    DRUGS[name] = {
        "name": name, "cls": cls, "route": route,
        "org": org or {}, "labs": labs or {}, "side": side or [],
        "ind": ind or [], "clear": clear, "inter": inter or [], "note": note,
    }


# ======================================================================
# 抗感染
# ======================================================================
K("阿莫西林", "青霉素类抗生素", ind=["CA-PNEU", "CA-SINUS", "CA-OTITIS"],
  side=["恶心", "腹泻", "皮疹"], clear="kidney",
  note="广谱青霉素，皮疹与胃肠道反应常见")
K("阿莫西林克拉维酸", "青霉素+酶抑制剂", ind=["RS-BRONCHIECT", "CA-SINUS"],
  side=["腹泻", "恶心"], clear="both", note="覆盖产 β-内酰胺酶菌")
K("青霉素", "青霉素类抗生素", ind=["CA-PHARYN", "CA-CELLUL"],
  side=["过敏反应", "注射部位痛"], clear="kidney", note="用前需皮试")
K("头孢氨苄", "一代头孢", ind=["CA-CELLUL"], side=["腹泻", "皮疹"], clear="kidney")
K("头孢曲松", "三代头孢", ind=["CA-PNEU", "CA-PYELO", "CA-MENING", "CA-CHOLE"],
  side=["腹泻", "静脉炎"], clear="both", note="可透过血脑屏障")
K("头孢他啶", "三代头孢（抗铜绿）", ind=["CA-PNEU", "CA-SEPSIS"],
  side=["腹泻"], clear="kidney")
K("美罗培南", "碳青霉烯类", ind=["CA-SEPSIS", "CA-PNEU"],
  side=["腹泻", "抽搐风险"], clear="kidney", note="重症感染首选之一")
K("万古霉素", "糖肽类抗生素", ind=["CA-MENING", "CA-ENDO", "CA-OSTEO"],
  org={"kidney": -0.10}, labs={"CREA": (18.0, "add")},
  side=["肾毒性", "红人综合征", "耳鸣"], clear="kidney", note="需监测谷浓度")
K("左氧氟沙星", "氟喹诺酮类", ind=["CA-PNEU", "CA-UTI", "CA-PYELO"],
  side=["肌腱痛", "失眠", "恶心", "光敏"], clear="kidney",
  note="可能加重肌腱损伤与 QT 延长")
K("莫西沙星", "氟喹诺酮类", ind=["CA-PNEU"], side=["QT 延长", "恶心"], clear="liver")
K("阿奇霉素", "大环内酯类", ind=["CA-PNEU", "CA-PHARYN"],
  labs={"ALT": (18.0, "add")}, side=["腹痛", "恶心"], clear="liver",
  note="可致 QT 延长")
K("克拉霉素", "大环内酯类", ind=["GI-PUD"],
  labs={"ALT": (25.0, "add")}, side=["口苦", "腹泻"], clear="liver")
K("多西环素", "四环素类", ind=["CA-LYME", "CA-BRUCELL", "DR-ACNE"],
  side=["光敏", "食管刺激", "恶心"], clear="liver")
K("米诺环素", "四环素类", ind=["DR-ACNE"], side=["头晕", "皮肤色素沉着"], clear="liver")
K("甲硝唑", "硝基咪唑类", ind=["CA-APPEND", "CA-CHOLE", "CA-GIARDIA", "GI-DIVERTICULITIS"],
  side=["金属味", "恶心", "头痛"], clear="liver", note="服期间禁酒")
K("替硝唑", "硝基咪唑类", ind=["CA-GIARDIA"], side=["金属味"], clear="liver")
K("呋喃妥因", "硝基呋喃类", ind=["CA-UTI"], side=["恶心", "尿色加深"],
  clear="kidney", note="仅用于下尿路感染")
K("磷霉素", "磷霉素类", ind=["CA-UTI"], side=["腹泻"], clear="both")
K("复方磺胺甲噁唑", "磺胺类", ind=["CA-UTI", "CA-PNEU"],
  labs={"K": (0.3, "add")}, side=["皮疹", "光敏", "高钾"], clear="kidney")
K("异烟肼", "抗结核药", ind=["CA-TB"], labs={"ALT": (60.0, "add"), "AST": (45.0, "add")},
  side=["周围神经炎", "肝损伤", "恶心"], clear="liver", inter=["利福平"],
  note="需同服维生素 B6")
K("利福平", "抗结核药", ind=["CA-TB", "CA-BRUCELL"],
  labs={"ALT": (45.0, "add"), "TBIL": (10.0, "add")},
  side=["尿橘红色", "肝损伤", "胃肠不适"], clear="liver", inter=["华法林", "口服避孕药"])
K("吡嗪酰胺", "抗结核药", ind=["CA-TB"], labs={"UA": (200.0, "add"),
                                                "ALT": (40.0, "add")},
  side=["关节痛", "肝损伤"], clear="liver", note="升尿酸，可诱发痛风")
K("乙胺丁醇", "抗结核药", ind=["CA-TB"], side=["视神经炎", "视力下降"], clear="kidney")
K("恩替卡韦", "核苷类抗 HBV", ind=["CA-HBV"], side=["头痛", "乏力"], clear="kidney")
K("替诺福韦", "核苷酸类抗病毒", ind=["CA-HBV", "CA-HIV"],
  org={"kidney": -0.08}, labs={"CREA": (8.0, "add"), "P": (-0.15, "add")},
  side=["肾小管损伤", "骨密度下降"], clear="kidney")
K("拉米夫定", "核苷类抗病毒", ind=["CA-HIV", "CA-HBV"], side=["头痛"], clear="kidney")
K("多替拉韦", "整合酶抑制剂", ind=["CA-HIV"], side=["失眠", "头痛"], clear="liver")
K("索磷布韦", "丙肝 NS5B 抑制剂", ind=["CA-HCV"], side=["头痛", "乏力"], clear="liver")
K("阿昔洛韦", "抗疱疹病毒", ind=["CA-VZV", "NR-ENCEPH"], clear="kidney",
  side=["肾损伤", "恶心"], note="需充分水化")
K("伐昔洛韦", "抗疱疹病毒", ind=["CA-HZV"], side=["头痛", "恶心"], clear="kidney")
K("奥司他韦", "神经氨酸酶抑制剂", ind=["CA-FLU"], side=["恶心", "呕吐"], clear="kidney")
K("氟康唑", "三唑类抗真菌", ind=["CA-CANDIDA"], labs={"ALT": (25.0, "add")},
  side=["肝损伤", "QT 延长"], clear="kidney")
K("伏立康唑", "三唑类抗真菌", ind=["CA-ASPERGILLUS"],
  org={"eye": -0.10}, labs={"ALT": (50.0, "add")},
  side=["视觉异常", "光敏", "肝损伤"], clear="liver")
K("青蒿琥酯", "抗疟药", ind=["CA-MALARIA"], side=["恶心", "网织红下降"], clear="liver")
K("氯喹", "抗疟药", ind=["CA-MALARIA"], org={"eye": -0.15},
  side=["视网膜病变", "瘙痒"], clear="both")
K("氯菊酯", "外用杀疥虫", ind=["CA-SCABIES"], route="外用",
  side=["局部灼热"], clear="skin")

# ======================================================================
# 心血管
# ======================================================================
K("氨氯地平", "二氢吡啶钙拮抗剂", ind=["CV-HTN"],
  labs={"SBP": (-18.0, "add"), "DBP": (-10.0, "add")},
  side=["踝部水肿", "面部潮红", "头痛"], clear="liver")
K("硝苯地平", "二氢吡啶钙拮抗剂", ind=["CV-HTN"],
  labs={"SBP": (-16.0, "add")}, side=["水肿", "心悸"], clear="liver")
K("缬沙坦", "ARB", ind=["CV-HTN", "RN-CKD", "CV-HF"],
  labs={"SBP": (-16.0, "add"), "K": (0.25, "add"), "CREA": (6.0, "add")},
  side=["头晕", "高钾"], clear="liver")
K("氯沙坦", "ARB", ind=["CV-HTN"], labs={"SBP": (-15.0, "add"), "UA": (-25.0, "add")},
  side=["头晕"], clear="both")
K("依那普利", "ACEI", ind=["CV-HTN", "CV-HF"],
  labs={"SBP": (-16.0, "add"), "K": (0.3, "add")},
  side=["干咳", "高钾", "血管性水肿"], clear="kidney")
K("氢氯噻嗪", "噻嗪类利尿剂", ind=["CV-HTN"],
  labs={"K": (-0.45, "add"), "Na": (-2.0, "add"), "UA": (45.0, "add"),
        "FPG": (0.5, "add"), "SBP": (-12.0, "add")},
  side=["低钾", "乏力", "多尿"], clear="kidney")
K("呋塞米", "袢利尿剂", ind=["CV-HF", "RN-NEPHROTIC", "RN-AKI"],
  labs={"K": (-0.6, "add"), "Na": (-3.0, "add"), "CREA": (10.0, "add"),
        "U_SG": (-0.006, "add")},
  side=["多尿", "口干", "低钾", "体位性头晕"], clear="kidney")
K("螺内酯", "醛固酮受体拮抗剂", ind=["CV-HF", "GI-CIRRHOSIS", "EN-CONN"],
  labs={"K": (0.45, "add")}, side=["男性乳房发育", "高钾"], clear="liver")
K("美托洛尔", "β1 受体阻滞剂", ind=["CV-CAD", "CV-HF", "CV-AF", "CV-MI"],
  labs={"HR": (-18.0, "add"), "SBP": (-8.0, "add")},
  side=["乏力", "心动过缓", "四肢发冷", "恶梦"], clear="liver",
  note="骤停可反跳性心动过速")
K("比索洛尔", "β1 受体阻滞剂", ind=["CV-HF", "CV-HTN"],
  labs={"HR": (-16.0, "add")}, side=["乏力", "心动过缓"], clear="both")
K("阿替洛尔", "β1 受体阻滞剂", ind=["CV-HTN", "EN-GRAVES"],
  labs={"HR": (-15.0, "add")}, side=["乏力"], clear="kidney")
K("普萘洛尔", "非选择性 β 阻滞剂", ind=["EN-GRAVES", "NR-MIGRAINE"],
  labs={"HR": (-14.0, "add")}, side=["乏力", "肢冷", "支气管痉挛"], clear="liver")
K("阿司匹林", "抗血小板", ind=["CV-CAD", "CV-MI", "NR-STROKE"],
  org={"gut": -0.05}, labs={"PLT": (-15.0, "add")},
  side=["胃部不适", "牙龈出血", "耳鸣"], clear="liver",
  note="小剂量抗血小板，大剂量镇痛；出血风险随剂量上升")
K("氯吡格雷", "P2Y12 抑制剂", ind=["CV-MI", "NR-STROKE"],
  side=["瘀斑", "腹泻"], clear="liver")
K("替格瑞洛", "P2Y12 抑制剂", ind=["CV-MI"], side=["呼吸困难", "瘀斑"], clear="liver")
K("华法林", "维生素 K 拮抗剂", ind=["CV-AF", "CV-DVT", "CV-PE"],
  labs={"INR": (1.2, "add"), "PT": (8.0, "add")},
  side=["出血", "瘀斑", "皮肤坏死"], clear="liver",
  inter=["阿司匹林", "利福平", "头孢曲松"], note="治疗窗窄，需监测 INR")
K("利伐沙班", "Xa 因子抑制剂", ind=["CV-DVT", "CV-PE", "CV-AF"],
  labs={"APTT": (4.0, "add")}, side=["出血", "瘀斑"], clear="both")
K("达比加群", "直接凝血酶抑制剂", ind=["CV-AF"], side=["出血"], clear="kidney")
K("肝素", "抗凝（注射）", ind=["CV-PE", "CV-DVT"], route="皮下",
  labs={"APTT": (20.0, "add"), "PLT": (-40.0, "add")},
  side=["出血", "血小板减少"], clear="both")
K("阿托伐他汀", "HMG-CoA 还原酶抑制剂", ind=["EN-DYSLIPID", "CV-AS", "CV-CAD"],
  org={"liver": -0.03}, labs={"LDL": (-1.4, "add"), "TC": (-1.5, "add"),
                               "ALT": (15.0, "add")},
  side=["肌肉酸痛", "肝酶升高"], clear="liver", note="肌痛需查 CK")
K("瑞舒伐他汀", "HMG-CoA 还原酶抑制剂", ind=["EN-DYSLIPID", "CV-AS"],
  labs={"LDL": (-1.7, "add"), "ALT": (12.0, "add")},
  side=["肌肉酸痛"], clear="both")
K("依折麦布", "胆固醇吸收抑制剂", ind=["EN-DYSLIPID"],
  labs={"LDL": (-0.8, "add")}, side=["腹泻"], clear="gut")
K("非诺贝特", "贝特类", ind=["EN-DYSLIPID"], labs={"TG": (-0.9, "add")},
  side=["肌痛", "胆囊结石"], clear="kidney")
K("硝酸甘油", "硝酸酯类", ind=["CV-CAD", "CV-MI"], route="舌下",
  labs={"SBP": (-10.0, "add")}, side=["头痛", "面部潮红"], clear="liver",
  note="耐药性需留出无药间期")
K("硝酸异山梨酯", "硝酸酯类", ind=["CV-CAD"], side=["头痛", "潮红"], clear="liver")
K("胺碘酮", "III 类抗心律失常", ind=["CV-VT", "CV-AF"],
  org={"thyroid": -0.15, "lungs": -0.10, "liver": -0.08},
  labs={"ALT": (30.0, "add"), "TSH": (3.0, "add")},
  side=["肺纤维化", "甲功异常", "角膜沉着", "光敏"], clear="liver",
  note="长期用需监测甲功、肝功、胸片")
K("维拉帕米", "非二氢吡啶钙拮抗剂", ind=["CV-SVT"],
  labs={"HR": (-12.0, "add")}, side=["便秘", "心动过缓"], clear="liver")
K("地高辛", "强心苷", ind=["CV-HF", "CV-AF"],
  labs={"HR": (-10.0, "add"), "K": (-0.1, "add")},
  side=["恶心", "黄视", "心律失常"], clear="kidney",
  note="治疗窗窄，低钾时易中毒")
K("沙库巴曲缬沙坦", "ARNI", ind=["CV-HF"],
  labs={"NTproBNP": (-300.0, "add"), "SBP": (-14.0, "add"), "K": (0.2, "add")},
  side=["低血压", "高钾", "头晕"], clear="both")
K("艾司洛尔", "超短效 β 阻滞剂", ind=["CV-DISSECT"], route="静脉",
  labs={"HR": (-25.0, "add"), "SBP": (-25.0, "add")}, side=["低血压"], clear="blood")
K("硝普钠", "血管扩张剂", ind=["CV-DISSECT"], route="静脉",
  labs={"SBP": (-40.0, "add")}, side=["低血压", "氰化物中毒"], clear="liver")
K("去甲肾上腺素", "血管活性药", ind=["CA-SEPSIS"], route="静脉",
  labs={"SBP": (40.0, "add"), "HR": (10.0, "add")}, side=["肢端缺血"], clear="both")
K("西洛他唑", "磷酸二酯酶 III 抑制剂", ind=["CV-PAD"],
  side=["头痛", "心悸"], clear="liver")
K("依诺肝素", "低分子肝素", ind=["CV-DVT", "CV-PE"], route="皮下",
  labs={"PLT": (-20.0, "add")}, side=["注射部位瘀斑"], clear="kidney")

# ======================================================================
# 内分泌与代谢
# ======================================================================
K("二甲双胍", "双胍类", ind=["EN-T2DM", "EN-PREDM", "GI-NAFLD", "EN-PCOS"],
  org={"gut": -0.04}, labs={"FPG": (-1.8, "add"), "HbA1c": (-1.1, "add"),
                            "B12": (-40.0, "add")},
  side=["腹泻", "恶心", "金属味", "维生素 B12 下降"], clear="kidney",
  note="肾功能不全时乳酸酸中毒风险上升")
K("格列美脲", "磺脲类", ind=["EN-T2DM"],
  labs={"FPG": (-2.2, "add"), "HbA1c": (-1.3, "add")},
  side=["低血糖", "体重增加"], clear="both")
K("西格列汀", "DPP-4 抑制剂", ind=["EN-T2DM"],
  labs={"FPG": (-1.2, "add"), "HbA1c": (-0.8, "add")}, side=["头痛"], clear="kidney")
K("达格列净", "SGLT2 抑制剂", ind=["EN-T2DM", "CV-HF", "RN-CKD"],
  labs={"FPG": (-1.6, "add"), "HbA1c": (-1.0, "add"), "U_GLU": (0.5, "add"),
        "K": (0.15, "add")},
  side=["多尿", "生殖道感染", "脱水"], clear="kidney")
K("恩格列净", "SGLT2 抑制剂", ind=["EN-T2DM", "CV-HF"],
  labs={"FPG": (-1.5, "add"), "HbA1c": (-0.9, "add")},
  side=["多尿", "尿路感染"], clear="kidney")
K("利拉鲁肽", "GLP-1 受体激动剂", ind=["EN-T2DM", "EN-OBESITY"],
  org={"gut": -0.03}, labs={"FPG": (-1.6, "add"), "HbA1c": (-1.2, "add")},
  side=["恶心", "食欲下降", "体重下降", "便秘"], clear="kidney")
K("司美格鲁肽", "GLP-1 受体激动剂", ind=["EN-OBESITY", "EN-T2DM"],
  labs={"HbA1c": (-1.4, "add")},
  side=["恶心", "呕吐", "食欲显著下降", "便秘"], clear="kidney")
K("胰岛素", "胰岛素", ind=["EN-T1DM", "EN-T2DM"], route="皮下",
  labs={"FPG": (-4.5, "add"), "HbA1c": (-2.2, "add"), "K": (-0.3, "add")},
  side=["低血糖", "注射部位硬结", "体重增加"], clear="liver")
K("左甲状腺素", "甲状腺激素", ind=["EN-HYPOTHY", "EN-HASHIMOTO"],
  labs={"TSH": (-9.0, "add"), "FT4": (4.0, "add")},
  side=["心悸", "失眠", "体重下降", "骨密度下降"], clear="liver",
  note="剂量过高会出现甲亢样表现")
K("甲巯咪唑", "抗甲状腺药", ind=["EN-GRAVES"],
  org={"marrow": -0.15}, labs={"FT4": (-10.0, "add"), "TSH": (1.5, "add"),
                               "WBC": (-1.8, "add")},
  side=["粒细胞缺乏", "皮疹", "关节痛", "肝损伤"], clear="both",
  note="发热咽痛需立即查血常规")
K("丙硫氧嘧啶", "抗甲状腺药", ind=["EN-GRAVES"],
  org={"liver": -0.15}, labs={"ALT": (40.0, "add"), "FT4": (-9.0, "add")},
  side=["肝损伤", "粒细胞缺乏"], clear="kidney")
K("氢化可的松", "糖皮质激素（生理替代）", ind=["EN-ADDISON"],
  labs={"COR_8am": (180.0, "add"), "FPG": (0.6, "add")},
  side=["血糖升高", "失眠", "体重增加"], clear="liver")
K("泼尼松", "糖皮质激素", ind=["RH-RA", "RH-SLE", "RN-NEPHROTIC", "RS-SARCOID",
                               "GI-IBD-CD", "NR-BELL", "HM-ITP", "RH-GCA"],
  org={"immune": -0.20, "bone": -0.10, "skin": -0.05},
  labs={"WBC": (2.5, "add"), "LYMPH_p": (-8.0, "add"), "FPG": (1.6, "add"),
        "Ca": (-0.08, "add"), "K": (-0.3, "add")},
  side=["满月脸", "血糖升高", "失眠", "情绪高涨", "骨密度下降", "易感染"],
  clear="liver", note="长期用需缓慢减量，骤停可致肾上腺危象")
K("甲泼尼龙", "糖皮质激素", ind=["RN-GN", "NR-MS", "RH-DM"],
  org={"immune": -0.25}, labs={"FPG": (2.0, "add"), "WBC": (3.0, "add")},
  side=["血糖升高", "失眠", "感染风险"], clear="liver")
K("地塞米松", "糖皮质激素", ind=["CA-COVID", "RS-ARDS", "RH-ANAPHYLAXIS"],
  org={"immune": -0.22}, labs={"FPG": (2.2, "add"), "LYMPH_p": (-10.0, "add")},
  side=["血糖升高", "失眠", "欣快"], clear="liver")
K("卡麦角林", "多巴胺激动剂", ind=["EN-PROLACTINOMA"],
  labs={"PRL": (-120.0, "add")}, side=["恶心", "头晕", "冲动控制障碍"], clear="liver")
K("去氨加压素", "ADH 类似物", ind=["EN-DI"],
  labs={"Na": (-3.0, "add"), "U_SG": (0.010, "add")},
  side=["低钠", "头痛"], clear="kidney")
K("睾酮", "雄激素", ind=["EN-HYPOGONAD"],
  labs={"TST": (12.0, "add"), "HGB": (8.0, "add")},
  side=["痤疮", "红细胞增多", "情绪波动"], clear="liver")
K("阿仑膦酸", "双膦酸盐", ind=["EN-OSTEOPOR"],
  org={"bone": 0.10}, labs={"Ca": (-0.06, "add")},
  side=["上腹不适", "颌骨坏死（罕见）"], clear="kidney",
  note="需空腹直立服用")
K("碳酸钙", "钙剂", ind=["EN-OSTEOPOR", "RN-CKD", "EN-OSTEOMALACIA"],
  labs={"Ca": (0.20, "add")}, side=["便秘", "腹胀"], clear="gut")
K("维生素D", "维生素 D 制剂", ind=["EN-VITD-DEF", "EN-OSTEOMALACIA", "EN-OSTEOPOR"],
  labs={"VD_25": (45.0, "add"), "Ca": (0.10, "add"), "P": (0.08, "add")},
  side=["高钙（剂量过高时）"], clear="liver")
K("别嘌醇", "黄嘌呤氧化酶抑制剂", ind=["EN-GOUT", "EN-HYPERURIC"],
  labs={"UA": (-220.0, "add")}, side=["皮疹", "胃肠不适", "痛风发作诱发"],
  clear="kidney", note="起始期需联用抗炎药防诱发")
K("非布司他", "黄嘌呤氧化酶抑制剂", ind=["EN-GOUT"],
  labs={"UA": (-260.0, "add")}, side=["肝酶升高"], clear="liver")
K("秋水仙碱", "抗痛风", ind=["EN-GOUT", "CV-PERICARD"],
  labs={"WBC": (-1.5, "add")}, side=["腹泻", "恶心", "肌痛"], clear="both",
  note="治疗窗窄，腹泻常是早期不良反应信号")
K("司美格鲁肽（减重）", "GLP-1 受体激动剂", ind=["EN-OBESITY"],
  side=["恶心", "食欲下降"], clear="kidney")

# ======================================================================
# 镇痛与抗炎
# ======================================================================
K("对乙酰氨基酚", "解热镇痛药", ind=["CA-URI", "CA-FLU", "NR-TTH", "CA-PHARYN"],
  org={"liver": -0.06}, labs={"ALT": (20.0, "add")},
  side=["肝损伤", "恶心"], clear="liver", note="剂量越高肝损伤风险越大，需按医嘱")
K("布洛芬", "非甾体抗炎药", ind=["NR-MIGRAINE", "NR-TTH", "CV-PERICARD", "MS-OA",
                                "RP-ENDOMETRIOSIS"],
  org={"gut": -0.10, "kidney": -0.08}, labs={"CREA": (10.0, "add"),
                                              "SBP": (5.0, "add")},
  side=["胃痛", "胃出血风险", "水肿", "肾功能下降"], clear="liver")
K("双氯芬酸", "非甾体抗炎药", ind=["RN-STONE", "EN-GOUT"],
  org={"gut": -0.10}, labs={"ALT": (18.0, "add")},
  side=["胃痛", "肝酶升高"], clear="liver")
K("塞来昔布", "COX-2 抑制剂", ind=["MS-OA", "RH-RA", "RH-AS", "NR-RADICULO"],
  org={"kidney": -0.05}, labs={"SBP": (4.0, "add")},
  side=["水肿", "心血管风险"], clear="liver")
K("美洛昔康", "非甾体抗炎药", ind=["MS-OA", "RH-RA"],
  org={"gut": -0.08}, side=["胃痛"], clear="liver")
K("曲马多", "弱阿片类", ind=["MS-FRACTURE", "NR-RADICULO"],
  side=["恶心", "头晕", "便秘", "嗜睡"], clear="liver")
K("哌替啶", "阿片类", ind=["CA-PANC"], route="注射",
  side=["呼吸抑制", "恶心", "嗜睡"], clear="liver")
K("吗啡", "阿片类", ind=["ON-PANCREATIC", "MS-FRACTURE"], route="注射",
  org={"gut": -0.08}, side=["便秘", "呼吸抑制", "嗜睡", "瘙痒"], clear="liver")
K("加巴喷丁", "钙通道 α2δ 配体", ind=["CA-HZV", "NR-NEUROPATHY"],
  side=["嗜睡", "头晕", "水肿"], clear="kidney")
K("普瑞巴林", "钙通道 α2δ 配体", ind=["NR-NEUROPATHY", "MS-FIBROMYALGIA"],
  side=["嗜睡", "头晕", "体重增加"], clear="kidney")
K("舒马曲坦", "5-HT1B/1D 激动剂", ind=["NR-MIGRAINE"],
  side=["胸部紧压感", "头晕"], clear="liver", note="心血管病者禁用")

# ======================================================================
# 消化
# ======================================================================
K("奥美拉唑", "质子泵抑制剂", ind=["GI-GERD", "GI-PUD", "GI-GASTRITIS", "GI-UGIB"],
  labs={"Mg": (-0.08, "add"), "B12": (-25.0, "add")},
  side=["腹胀", "便秘", "长期用骨密度下降"], clear="liver")
K("泮托拉唑", "质子泵抑制剂", ind=["GI-PUD", "GI-UGIB"], side=["腹胀"], clear="liver")
K("雷贝拉唑", "质子泵抑制剂", ind=["GI-GERD"], side=["头痛"], clear="liver")
K("法莫替丁", "H2 受体拮抗剂", ind=["GI-GERD"], side=["头痛", "便秘"], clear="kidney")
K("蒙脱石散", "止泻吸附剂", ind=["CA-GASTRO"], side=["便秘"], clear="gut")
K("洛哌丁胺", "阿片类止泻", ind=["CA-GASTRO", "GI-IBS"], side=["便秘", "腹胀"],
  clear="liver")
K("口服补液盐", "补液", ind=["CA-GASTRO", "CA-INFECT-ENDO"],
  labs={"Na": (2.0, "add"), "K": (0.2, "add")}, side=["腹胀"], clear="kidney")
K("乳酸林格", "等渗晶体液", ind=["CA-PANC", "GI-OBSTRUCT", "RN-AKI"], route="静脉",
  labs={"SBP": (8.0, "add"), "Na": (1.5, "add")}, side=["水肿"], clear="kidney")
K("液体复苏", "等渗晶体液（快速）", ind=["CA-SEPSIS", "RN-AKI"], route="静脉",
  labs={"SBP": (15.0, "add"), "CREA": (-15.0, "add")}, side=["水肿"], clear="kidney")
K("莫沙必利", "促动力药", ind=["GI-GERD"], side=["腹泻", "腹痛"], clear="liver")
K("多潘立酮", "促动力药", ind=["GI-GERD"], side=["口干", "乳房胀痛"], clear="liver")
K("乳果糖", "渗透性泻药", ind=["GI-CIRRHOSIS", "GI-CONSTIP"],
  labs={"AMM": (-15.0, "add")}, side=["腹胀", "腹泻"], clear="gut")
K("聚乙二醇", "渗透性泻药", ind=["GI-CONSTIP"], side=["腹胀"], clear="gut")
K("美沙拉秦", "5-ASA", ind=["GI-IBD-UC", "GI-IBD-CD"],
  org={"kidney": -0.04}, labs={"CRP": (-15.0, "add")},
  side=["恶心", "头痛"], clear="gut")
K("柳氮磺吡啶", "5-ASA 前体", ind=["RH-AS", "GI-IBD-UC"],
  labs={"WBC": (-1.2, "add")}, side=["皮疹", "胃肠不适", "精液异常"], clear="liver")
K("英夫利西单抗", "TNF-α 抑制剂", ind=["GI-IBD-CD"],
  org={"immune": -0.20}, side=["输液反应", "感染风险", "结核再激活"],
  clear="immune", route="静脉")
K("熊去氧胆酸", "胆汁酸", ind=["GI-PBC"],
  labs={"ALP": (-120.0, "add"), "GGT": (-80.0, "add")}, side=["腹泻"], clear="liver")
K("生长抑素", "抑酸抑酶", ind=["CA-PANC", "GI-UGIB"], route="静脉",
  side=["血糖波动"], clear="liver")
K("奥曲肽", "生长抑素类似物", ind=["GI-VARICES", "ON-CARCINOID"],
  side=["腹泻", "胆结石"], clear="liver")
K("甲氧氯普胺", "止吐促动力", ind=["CA-PANC", "NR-MIGRAINE"],
  side=["锥体外系反应", "嗜睡"], clear="kidney")

# ======================================================================
# 呼吸
# ======================================================================
K("沙丁胺醇", "短效 β2 激动剂", ind=["RS-ASTHMA", "CA-BRONCH", "RS-COPD"],
  route="吸入", labs={"HR": (8.0, "add"), "K": (-0.2, "add")},
  side=["手抖", "心悸", "低钾"], clear="liver")
K("沙美特罗", "长效 β2 激动剂", ind=["RS-COPD", "RS-ASTHMA"], route="吸入",
  side=["手抖", "心悸"], clear="liver")
K("布地奈德", "吸入糖皮质激素", ind=["RS-ASTHMA", "RS-COPD"], route="吸入",
  side=["口咽念珠菌", "声音嘶哑"], clear="liver", note="用后需漱口")
K("布地奈德鼻喷", "鼻用糖皮质激素", ind=["RH-ALLERGY", "CA-SINUS"], route="鼻喷",
  side=["鼻干", "鼻出血"], clear="liver")
K("布地奈德雾化", "雾化糖皮质激素", ind=["RS-LARYNG"], route="雾化",
  side=["口苦"], clear="liver")
K("噻托溴铵", "长效抗胆碱能", ind=["RS-COPD"], route="吸入",
  side=["口干", "排尿困难"], clear="kidney")
K("孟鲁司特", "白三烯受体拮抗剂", ind=["RS-ASTHMA", "RH-ALLERGY"],
  side=["头痛", "梦境异常", "情绪变化"], clear="liver")
K("氨溴索", "祛痰药", ind=["CA-BRONCH", "CA-PNEU"], side=["胃部不适"], clear="liver")
K("乙酰半胱氨酸", "祛痰抗氧化", ind=["RS-COPD", "CA-BRONCH"],
  side=["恶心", "支气管痉挛"], clear="liver")
K("机械通气", "呼吸支持", ind=["RS-ARDS", "CA-SEPSIS"], route="设备",
  labs={"SpO2": (6.0, "add"), "pO2": (20.0, "add"), "pCO2": (-6.0, "add")},
  side=["气压伤"], clear="none")
K("CPAP", "无创正压通气", ind=["RS-OSA"], route="设备",
  labs={"SpO2": (2.0, "add")}, side=["鼻干", "面罩压迫"], clear="none")
K("胸腔闭式引流", "引流", ind=["RS-PTX"], route="操作",
  labs={"SpO2": (4.0, "add"), "pO2": (12.0, "add")}, side=["胸痛"], clear="none")

# ======================================================================
# 血液
# ======================================================================
K("琥珀酸亚铁", "铁剂", ind=["HM-IDA"],
  org={"gut": -0.04}, labs={"HGB": (18.0, "add"), "FERR": (60.0, "add"),
                            "TSAT": (12.0, "add")},
  side=["黑便", "便秘", "胃部不适"], clear="gut")
K("维生素C", "维生素", ind=["HM-IDA"],
  labs={"TSAT": (4.0, "add")}, side=["胃部不适"], clear="kidney")
K("甲钴胺", "维生素 B12", ind=["HM-B12", "NR-NEUROPATHY"],
  labs={"B12": (250.0, "add"), "HGB": (12.0, "add")}, side=["皮疹"], clear="liver")
K("叶酸", "叶酸", ind=["HM-FOLATE"], labs={"FOL": (15.0, "add")},
  side=["口苦"], clear="liver")
K("促红素", "红细胞生成刺激剂", ind=["RN-CKD", "HM-IDA"], route="皮下",
  labs={"HGB": (20.0, "add")}, side=["血压升高", "血栓"], clear="liver")
K("环孢素", "钙调神经磷酸酶抑制剂", ind=["HM-AA", "RN-NEPHROTIC"],
  org={"kidney": -0.15}, labs={"CREA": (25.0, "add"), "K": (0.35, "add"),
                               "UA": (40.0, "add")},
  side=["肾毒性", "高血压", "手抖", "牙龈增生"], clear="liver",
  note="需监测血药浓度")
K("抗胸腺细胞球蛋白", "免疫抑制", ind=["HM-AA"], route="静脉",
  org={"immune": -0.35}, side=["发热寒战", "血清病"], clear="immune")
K("输血", "成分输血", ind=["GI-UGIB", "HM-AA", "CA-SEPSIS"], route="静脉",
  labs={"HGB": (25.0, "add"), "SBP": (8.0, "add")}, side=["发热", "过敏"], clear="none")
K("羟基脲", "抗代谢", ind=["HM-PV", "HM-ET"],
  org={"marrow": -0.20}, labs={"WBC": (-3.0, "add"), "PLT": (-150.0, "add")},
  side=["骨髓抑制", "口腔溃疡"], clear="kidney")
K("伊马替尼", "BCR-ABL 抑制剂", ind=["HM-CML"],
  labs={"WBC": (-25.0, "add")}, side=["水肿", "肌肉痉挛", "恶心"], clear="liver")
K("化疗", "细胞毒方案", ind=["HM-AML", "HM-ALL", "HM-HL", "HM-NHL"],
  org={"marrow": -0.45, "immune": -0.35, "gut": -0.20},
  labs={"WBC": (-3.5, "add"), "HGB": (-20.0, "add"), "PLT": (-80.0, "add")},
  side=["呕吐", "脱发", "口腔溃疡", "骨髓抑制", "乏力"], clear="both",
  note="治疗本身即一次打击，需权衡")
K("环磷酰胺", "烷化剂", ind=["RN-GN", "RH-GPA"],
  org={"marrow": -0.25, "bladder": -0.10}, labs={"WBC": (-2.0, "add")},
  side=["出血性膀胱炎", "脱发", "恶心"], clear="both")
K("甲氨蝶呤", "抗叶酸", ind=["RH-RA"],
  org={"liver": -0.10, "marrow": -0.10}, labs={"ALT": (30.0, "add")},
  side=["口腔溃疡", "肝损伤", "恶心"], clear="kidney", note="需补叶酸")
K("羟氯喹", "抗疟/免疫调节", ind=["RH-SLE", "RH-SJOREN"],
  org={"eye": -0.08}, side=["视网膜病变（长期）", "皮疹"], clear="both")
K("硫唑嘌呤", "嘌呤拮抗剂", ind=["RH-SLE", "GI-IBD-UC"],
  org={"marrow": -0.20}, labs={"WBC": (-1.8, "add")},
  side=["骨髓抑制", "肝损伤"], clear="liver")

# ======================================================================
# 精神科（身体效应部分；精神症状效应见 psyche/pharm.py）
# ======================================================================
K("奥氮平", "第二代抗精神病药", ind=["PSY"],
  org={"liver": -0.05}, labs={"FPG": (1.4, "add"), "TG": (0.9, "add"),
                               "ALT": (20.0, "add"), "PRL": (10.0, "add")},
  side=["嗜睡", "体重增加", "食欲增加", "口干", "便秘"], clear="liver",
  note="代谢综合征风险最高的抗精神病药之一")
K("氯氮平", "第二代抗精神病药", ind=["PSY"],
  org={"marrow": -0.30}, labs={"WBC": (-2.5, "add"), "NEUT_p": (-15.0, "add")},
  side=["流涎", "嗜睡", "体重增加", "粒细胞缺乏"], clear="liver",
  note="必须定期查血常规")
K("利培酮", "第二代抗精神病药", ind=["PSY"],
  labs={"PRL": (60.0, "add")},
  side=["催乳素升高", "体重增加", "静坐不能", "乳房胀痛"], clear="liver")
K("氟哌啶醇", "第一代抗精神病药", ind=["PSY"],
  labs={"PRL": (30.0, "add")},
  side=["手抖", "动作僵硬", "静坐不能", "迟发性运动障碍"], clear="liver")
K("喹硫平", "第二代抗精神病药", ind=["PSY"],
  labs={"FPG": (0.9, "add"), "TG": (0.6, "add")},
  side=["嗜睡", "口干", "体重增加", "体位性低血压"], clear="liver")
K("舍曲林", "SSRI", ind=["PSY"], labs={"Na": (-2.0, "add")},
  side=["恶心", "腹泻", "性功能障碍", "出汗"], clear="liver")
K("氟西汀", "SSRI", ind=["PSY"], side=["恶心", "失眠", "性功能障碍"], clear="liver")
K("文拉法辛", "SNRI", ind=["PSY"], labs={"SBP": (6.0, "add")},
  side=["出汗", "血压升高", "恶心", "停药反应"], clear="liver")
K("米氮平", "NaSSA", ind=["PSY"], labs={"TG": (0.5, "add")},
  side=["嗜睡", "食欲增加", "体重增加", "口干"], clear="liver")
K("锂盐", "心境稳定剂", ind=["PSY"],
  org={"kidney_tubule": -0.20, "thyroid": -0.12},
  labs={"TSH": (3.5, "add"), "Ca": (0.10, "add"), "CREA": (12.0, "add")},
  side=["手抖", "多尿", "口渴", "甲减", "体重增加"], clear="kidney",
  note="治疗窗极窄，脱水或 NSAID 联用易中毒")
K("丙戊酸钠", "心境稳定剂", ind=["NR-EPILEPSY", "PSY"],
  org={"liver": -0.12}, labs={"ALT": (35.0, "add"), "PLT": (-40.0, "add"),
                               "AMM": (8.0, "add")},
  side=["体重增加", "手抖", "脱发", "肝损伤"], clear="liver")
K("拉莫三嗪", "心境稳定剂", ind=["PSY"], side=["皮疹", "头痛", "失眠"], clear="liver",
  note="加量过快可致史蒂文斯-约翰逊综合征")
K("氯硝西泮", "苯二氮䓬类", ind=["PSY"], side=["嗜睡", "记忆减退", "共济失调"],
  clear="liver", note="长期用产生耐受与依赖")
K("丁螺环酮", "5-HT1A 部分激动剂", ind=["PSY"], side=["头晕", "恶心"], clear="liver")
K("哌甲酯", "中枢兴奋剂", ind=["PSY"], labs={"HR": (10.0, "add"),
                                              "SBP": (8.0, "add")},
  side=["失眠", "食欲下降", "心悸"], clear="liver")
K("托莫西汀", "选择性 NE 再摄取抑制剂", ind=["PSY"],
  side=["恶心", "口干", "嗜睡", "血压升高"], clear="liver")
K("纳曲酮", "阿片受体拮抗剂", ind=["PSY"], org={"liver": -0.10},
  labs={"ALT": (30.0, "add")}, side=["恶心", "头痛"], clear="liver")
K("褪黑素", "褪黑素受体激动剂", ind=["PSY"], side=["嗜睡", "头痛"], clear="liver")
K("多奈哌齐", "胆碱酯酶抑制剂", ind=["NR-ALZHEIMER"],
  labs={"HR": (-6.0, "add")}, side=["恶心", "腹泻", "心动过缓", "梦境增多"],
  clear="liver")
K("左旋多巴", "多巴胺前体", ind=["NR-PARKINSON"],
  side=["恶心", "体位性低血压", "异动症", "冲动控制障碍"], clear="liver")
K("左乙拉西坦", "抗癫痫药", ind=["NR-EPILEPSY"],
  side=["易怒", "嗜睡", "头晕"], clear="kidney")
K("溴吡斯的明", "胆碱酯酶抑制剂", ind=["NR-MG"],
  side=["腹痛", "腹泻", "流涎", "肌束颤动"], clear="kidney")
K("环苯扎林", "肌松剂", ind=["NR-RADICULO"], side=["嗜睡", "口干"], clear="liver")

# ======================================================================
# 其他与支持治疗
# ======================================================================
K("肾上腺素", "肾上腺素受体激动剂", ind=["RH-ANAPHYLAXIS"], route="肌注",
  labs={"SBP": (40.0, "add"), "HR": (30.0, "add")},
  side=["心悸", "手抖", "血压升高"], clear="liver")
K("氯雷他定", "二代抗组胺", ind=["RH-ALLERGY", "RH-URTICARIA"],
  side=["口干", "乏力"], clear="liver")
K("西替利嗪", "二代抗组胺", ind=["RH-URTICARIA", "DR-ECZEMA"],
  side=["嗜睡", "口干"], clear="kidney")
K("氯苯那敏", "一代抗组胺", ind=["CA-URI"],
  side=["嗜睡", "口干", "排尿困难"], clear="liver")
K("伪麻黄碱", "减充血剂", ind=["CA-URI"],
  labs={"SBP": (8.0, "add"), "HR": (8.0, "add")},
  side=["心悸", "失眠", "血压升高"], clear="kidney")
K("糠酸莫米松", "外用糖皮质激素", ind=["DR-ECZEMA"], route="外用",
  side=["皮肤变薄", "局部灼热"], clear="skin")
K("特比萘芬", "抗真菌", ind=["DR-TINEA"], org={"liver": -0.05},
  labs={"ALT": (20.0, "add")}, side=["胃部不适", "皮疹"], clear="liver")
K("炉甘石洗剂", "外用止痒", ind=["CA-VZV"], route="外用", side=["皮肤干燥"],
  clear="skin")
K("人工泪液", "润滑", ind=["EY-DRY", "RH-SJOREN"], route="滴眼",
  side=["短暂视物模糊"], clear="none")
K("左氧氟沙星滴眼液", "抗菌滴眼", ind=["EY-CONJUNCT"], route="滴眼",
  side=["眼部刺痛"], clear="none")
K("坦索罗辛", "α1 受体阻滞剂", ind=["RN-BPH", "RN-STONE"],
  labs={"SBP": (-8.0, "add")}, side=["体位性头晕", "排尿无力"], clear="liver")
K("非那雄胺", "5α-还原酶抑制剂", ind=["RN-BPH"],
  labs={"PSA": (-2.0, "add")}, side=["精力下降", "乳房胀痛"], clear="liver")
K("索利那新", "抗胆碱能", ind=["RN-BPH"],
  side=["口干", "便秘", "视物模糊"], clear="liver")
K("甲钴胺（神经）", "神经营养", ind=["NR-NEUROPATHY"], side=["皮疹"], clear="liver")
K("氨基葡萄糖", "软骨保护", ind=["MS-OA"], side=["胃部不适"], clear="gut")
K("秋水仙碱（预防）", "抗痛风", ind=["EN-GOUT"], side=["腹泻"], clear="both")
K("尼古丁替代", "戒烟辅助", ind=["PSY"], side=["口腔刺激", "心悸"], clear="liver")
K("伐尼克兰", "戒烟辅助", ind=["PSY"], side=["恶心", "梦境异常", "情绪变化"],
  clear="kidney")
K("雌孕激素制剂", "雌孕激素复方", ind=["RP-ENDOMETRIOSIS", "EN-PCOS"],
  labs={"TG": (0.3, "add"), "SBP": (4.0, "add")},
  side=["恶心", "体重增加", "血栓风险"], clear="liver")
K("依托考昔", "COX-2 抑制剂", ind=["EN-GOUT", "MS-OA"],
  org={"kidney": -0.06}, side=["水肿", "血压升高"], clear="liver")
K("泛昔洛韦", "抗疱疹病毒", ind=["CA-HZV"], side=["头痛"], clear="kidney")
K("庆大霉素", "氨基糖苷类", ind=["CA-ENDO"],
  org={"kidney": -0.15, "ear": -0.15},
  labs={"CREA": (25.0, "add")}, side=["耳毒性", "肾毒性"], clear="kidney")
K("尼莫地平", "钙拮抗剂（脑血管）", ind=["NR-ICH", "NR-SAH"],
  labs={"SBP": (-8.0, "add")}, side=["低血压", "头痛"], clear="liver")
K("甘露醇", "渗透性脱水剂", ind=["NR-ICH", "NR-BRAIN-TUMOR"], route="静脉",
  labs={"OSM": (18.0, "add"), "Na": (-3.0, "add")},
  side=["多尿", "口渴", "电解质紊乱"], clear="kidney")
K("度洛西汀", "SNRI", ind=["MS-FIBROMYALGIA", "PSY"],
  org={"liver": -0.05}, labs={"ALT": (20.0, "add")},
  side=["恶心", "出汗", "血压升高"], clear="liver")
K("维生素A", "维生素", ind=["CA-MEASLES"], side=["头痛（剂量过高时）"], clear="liver")
K("休息与补液", "支持治疗", ind=["GI-HEPATITIS-A", "CA-URI"], route="支持",
  labs={"U_SG": (-0.004, "add")}, side=["无"], clear="none")
K("胃肠减压", "支持治疗", ind=["GI-OBSTRUCT"], route="操作",
  side=["咽部不适", "口干"], clear="none")


def resolve(name: str) -> Optional[str]:
    name = (name or "").strip()
    if name in DRUGS:
        return name
    for k in DRUGS:
        if k.startswith(name) and len(name) >= 2:
            return k
    return None


def by_indication(code: str) -> List[str]:
    return [k for k, v in DRUGS.items() if code in v["ind"]]


def by_class(cls_kw: str) -> List[str]:
    return [k for k, v in DRUGS.items() if cls_kw in v["cls"]]


def stats() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in DRUGS.values():
        out[v["cls"]] = out.get(v["cls"], 0) + 1
    return out
