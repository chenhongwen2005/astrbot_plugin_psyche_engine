"""疾病目录。

每个条目是一个「能被风险因素推出来、能把器官和化验单改坏」的东西，
不是一段文字描述。字段含义：

    base   基线日发病概率（中性风险条件下）
    risk   风险因子的权重：出现该因子时乘数 ×(1+w)
    org    患病时对各器官功能的损伤上限（乘以疾病严重度）
    labs   满载时对化验值的绝对偏移（add）或倍率（mul）
    sx     主观症状（进注入块，模型据此"身上不舒服"）
    acute  急症：起病以小时计，可自限
    dur    未治疗时的自限期（虚拟小时），None 表示不自动好
    fever/pain/inflam  驱动体温、疼痛评分、CRP/ESR
    mortal 未治疗时每日死亡概率（仅用于极重情形）
    treat  有效药物（名字必须存在于 drugs.py）
    sex/age 易感人群

刻意做的一件事：常见病 base 高但不留后遗症，罕见病 base 极低但器官损伤重。
这样长程模拟里"得一场感冒"和"查出骨髓瘤"的体验完全不同，而不是同一条概率线上抽名字。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

DISEASES: Dict[str, Dict[str, Any]] = {}


def D(
    code: str,
    zh: str,
    sys_: str,
    *,
    base: float,
    risk: Optional[Dict[str, float]] = None,
    org: Optional[Dict[str, float]] = None,
    labs: Optional[Dict[str, Tuple[float, str]]] = None,
    sx: Optional[List[str]] = None,
    acute: bool = False,
    dur: Optional[float] = None,
    fever: float = 0.0,
    pain: float = 0.0,
    inflam: float = 0.0,
    mortal: float = 0.0,
    treat: Optional[List[str]] = None,
    sex: Optional[str] = None,
    age: Optional[Tuple[float, float]] = None,
    rare: bool = False,
    note: str = "",
) -> None:
    DISEASES[code] = {
        "code": code, "zh": zh, "sys": sys_, "base": base,
        "risk": risk or {}, "org": org or {}, "labs": labs or {},
        "sx": sx or [], "acute": acute, "dur": dur,
        "fever": fever, "pain": pain, "inflam": inflam,
        "mortal": mortal, "treat": treat or [], "sex": sex, "age": age,
        "rare": rare, "note": note,
    }


# ======================================================================
# 感染
# ======================================================================
D("CA-URI", "普通感冒", "resp", base=0.020,
  risk={"pathogen": 0.9, "sleep_debt": 0.5, "stress": 0.4, "hygiene": 0.6, "vitd": 0.4},
  org={"airway": 0.10, "immune": 0.03},
  labs={"WBC": (1.2, "add"), "LYMPH_p": (8.0, "add"), "CRP": (6.0, "add")},
  sx=["咽部发干发痒", "清水样鼻涕", "打喷嚏", "轻微畏寒"], acute=True, dur=150.0,
  fever=0.25, treat=["对乙酰氨基酚", "氯苯那敏", "伪麻黄碱"])
D("CA-FLU", "流行性感冒", "resp", base=0.004,
  risk={"pathogen": 1.2, "sleep_debt": 0.6, "stress": 0.5, "age": 0.4},
  org={"airway": 0.18, "lungs": 0.08},
  labs={"WBC": (-0.8, "add"), "LYMPH_p": (6.0, "add"), "CRP": (18.0, "add"),
        "AST": (12.0, "add"), "CK": (60.0, "add")},
  sx=["突然发烧", "全身肌肉酸痛", "头痛", "干咳", "眼眶后胀痛"], acute=True, dur=190.0,
  fever=0.85, pain=0.45, inflam=0.35, treat=["奥司他韦", "对乙酰氨基酚"])
D("CA-COVID", "新型冠状病毒感染", "resp", base=0.003,
  risk={"pathogen": 1.0, "age": 0.8, "bmi": 0.5},
  org={"lungs": 0.22, "airway": 0.12, "coag": 0.15, "heart": 0.06},
  labs={"LYMPH_p": (-8.0, "add"), "CRP": (22.0, "add"), "DD": (0.6, "add"),
        "LDH": (60.0, "add"), "SpO2": (-3.0, "add")},
  sx=["咽痛", "干咳", "嗅觉变淡", "活动后气短", "乏力"], acute=True, dur=280.0,
  fever=0.6, inflam=0.45, treat=["对乙酰氨基酚", "地塞米松"])
D("CA-PNEU", "社区获得性肺炎", "resp", base=0.0006,
  risk={"pathogen": 0.8, "smoking": 1.2, "age": 0.9, "alcohol": 0.6, "hygiene": 0.4},
  org={"lungs": 0.35, "heart": 0.08},
  labs={"WBC": (6.0, "add"), "NEUT_p": (14.0, "add"), "CRP": (90.0, "add"),
        "pO2": (-14.0, "add"), "SpO2": (-5.0, "add"), "BUN": (2.5, "add")},
  sx=["高热寒战", "咳黄痰", "胸膜性胸痛", "呼吸费力"], acute=True, dur=340.0,
  fever=0.9, pain=0.4, inflam=0.75, mortal=0.004,
  treat=["阿莫西林", "左氧氟沙星", "头孢曲松", "对乙酰氨基酚"])
D("CA-BRONCH", "急性支气管炎", "resp", base=0.002,
  risk={"smoking": 1.5, "pathogen": 0.6, "pm25": 0.6},
  org={"airway": 0.22},
  labs={"CRP": (12.0, "add"), "WBC": (1.0, "add")},
  sx=["咳嗽有痰", "胸骨后灼热", "夜间咳醒"], acute=True, dur=220.0, fever=0.2,
  treat=["对乙酰氨基酚", "沙丁胺醇"])
D("CA-TB", "肺结核", "resp", base=0.00008,
  risk={"pathogen": 0.9, "bmi": 0.6, "stress": 0.5, "hygiene": 0.5},
  org={"lungs": 0.40, "fat": 0.3},
  labs={"ESR": (30.0, "add"), "CRP": (25.0, "add"), "LYMPH_p": (5.0, "add"),
        "HGB": (-12.0, "add"), "ALB": (-4.0, "add")},
  sx=["午后低热", "夜间盗汗", "咳两周以上", "体重下降", "痰中血丝"],
  dur=2000.0, fever=0.45, inflam=0.45, treat=["异烟肼", "利福平", "吡嗪酰胺", "乙胺丁醇"])
D("CA-HBV", "慢性乙型肝炎", "gi", base=0.00004,
  risk={"pathogen": 0.5}, org={"liver": 0.30}, labs={},
  sx=["右上腹隐痛", "乏力", "食欲差"], dur=None, inflam=0.15,
  treat=["恩替卡韦", "替诺福韦"], note="急性期后转慢性，ALT 随炎症活动波动")
D("CA-HCV", "丙型肝炎", "gi", base=0.00003, org={"liver": 0.25},
  labs={"ALT": (35.0, "add")}, sx=["长期乏力", "右上腹不适"], dur=None, inflam=0.12,
  treat=["索磷布韦"], rare=True)
D("CA-HIV", "HIV 感染", "rheum", base=0.00001,
  risk={"pathogen": 0.6}, org={"immune": 0.55},
  labs={"CD4": (-380.0, "add"), "CD4_CD8": (-0.6, "add"), "LYMPH_p": (-10.0, "add"),
        "IgG": (4.0, "add")},
  sx=["反复低热", "颈部淋巴结肿大", "夜间盗汗", "口腔白斑"], dur=None,
  fever=0.25, inflam=0.2, treat=["替诺福韦", "拉米夫定", "多替拉韦"])
D("CA-UTI", "急性膀胱炎", "renal", base=0.004,
  risk={"water": 0.6, "hygiene": 0.5, "sex": 0.3},
  org={"bladder": 0.18, "kidney": 0.03},
  labs={"U_WBC": (18.0, "add"), "U_BLD": (0.3, "add"), "CRP": (8.0, "add")},
  sx=["尿频", "尿急", "排尿末灼痛", "下腹坠胀"], acute=True, dur=120.0,
  fever=0.2, pain=0.3, treat=["左氧氟沙星", "呋喃妥因", "磷霉素"])
D("CA-PYELO", "急性肾盂肾炎", "renal", base=0.0007,
  risk={"water": 0.6, "sex": 0.5, "hygiene": 0.4},
  org={"kidney": 0.16, "bladder": 0.15},
  labs={"WBC": (5.0, "add"), "NEUT_p": (10.0, "add"), "CRP": (70.0, "add"),
        "U_WBC": (40.0, "add"), "CREA": (18.0, "add")},
  sx=["高热", "腰痛叩击痛", "尿频尿痛", "恶心"], acute=True, dur=260.0,
  fever=0.9, pain=0.55, inflam=0.7, treat=["头孢曲松", "左氧氟沙星"])
D("CA-GASTRO", "急性胃肠炎", "gi", base=0.006,
  risk={"hygiene": 0.8, "pathogen": 0.5}, org={"gut": 0.15, "kidney_tubule": 0.05},
  labs={"K": (-0.4, "add"), "Na": (-3.0, "add"), "BUN": (1.8, "add")},
  sx=["水样腹泻", "脐周绞痛", "恶心呕吐"], acute=True, dur=90.0, fever=0.35,
  pain=0.35, treat=["蒙脱石散", "口服补液盐", "洛哌丁胺"])
D("CA-APPEND", "急性阑尾炎", "gi", base=0.00035, org={"gut": 0.10},
  labs={"WBC": (6.0, "add"), "NEUT_p": (12.0, "add"), "CRP": (45.0, "add")},
  sx=["转移性右下腹痛", "麦氏点压痛", "恶心", "低热"], acute=True, dur=200.0,
  fever=0.55, pain=0.8, inflam=0.6, mortal=0.001,
  treat=["头孢曲松", "甲硝唑"])
D("CA-CHOLE", "急性胆囊炎", "gi", base=0.0004,
  risk={"bmi": 0.8, "sex": 0.4, "age": 0.5}, org={"liver": 0.12},
  labs={"WBC": (5.0, "add"), "CRP": (60.0, "add"), "ALP": (60.0, "add"),
        "GGT": (70.0, "add"), "TBIL": (12.0, "add")},
  sx=["右上腹持续痛", "向右肩放射", "油腻后加重", "墨菲征阳性"], acute=True, dur=240.0,
  fever=0.6, pain=0.75, inflam=0.6, treat=["头孢曲松", "甲硝唑"])
D("CA-PANC", "急性胰腺炎", "gi", base=0.00016,
  risk={"alcohol": 1.8, "TG": 1.2, "bmi": 0.6}, org={"pancreas_exo": 0.30, "gut": 0.12},
  labs={"AMY": (600.0, "add"), "LIP": (900.0, "add"), "CRP": (110.0, "add"),
        "WBC": (4.0, "add"), "Ca": (-0.20, "add"), "LAC": (1.2, "add")},
  sx=["上腹持续剧痛向背放射", "弯腰可稍缓", "呕吐后不缓解"], acute=True, dur=300.0,
  fever=0.5, pain=0.95, inflam=0.8, mortal=0.006,
  treat=["生长抑素", "哌替啶", "乳酸林格"])
D("CA-MENING", "细菌性脑膜炎", "neuro", base=0.00003,
  risk={"pathogen": 0.6, "hygiene": 0.4}, org={"brain": 0.35, "nerve": 0.10},
  labs={"WBC": (8.0, "add"), "NEUT_p": (16.0, "add"), "CRP": (120.0, "add")},
  sx=["剧烈头痛", "颈项强直", "畏光", "喷射性呕吐", "意识模糊"], acute=True, dur=260.0,
  fever=0.95, pain=0.8, inflam=0.9, mortal=0.05, treat=["头孢曲松", "万古霉素"])
D("CA-SEPSIS", "脓毒症", "gi", base=0.00006,
  risk={"pathogen": 0.9, "age": 0.9, "immune": 0.8},
  org={"heart": 0.25, "kidney": 0.30, "lungs": 0.20, "coag": 0.30, "brain": 0.20},
  labs={"WBC": (9.0, "add"), "CRP": (160.0, "add"), "LAC": (3.2, "add"),
        "CREA": (60.0, "add"), "PLT": (-90.0, "add"), "INR": (0.5, "add"),
        "SBP": (-30.0, "add"), "HR": (35.0, "add")},
  sx=["高热或体温不升", "意识恍惚", "四肢湿冷", "尿量减少"], acute=True, dur=200.0,
  fever=0.9, inflam=1.0, mortal=0.10, treat=["去甲肾上腺素", "美罗培南", "液体复苏"])
D("CA-ENDO", "感染性心内膜炎", "cardio", base=0.00004,
  risk={"pathogen": 0.6}, org={"heart": 0.30, "kidney": 0.12, "coag": 0.10},
  labs={"WBC": (4.0, "add"), "CRP": (70.0, "add"), "ESR": (35.0, "add"),
        "HGB": (-15.0, "add"), "U_BLD": (0.25, "add")},
  sx=["持续低热", "新出现的心脏杂音", "指甲下线状出血", "乏力"], dur=600.0,
  fever=0.6, inflam=0.6, mortal=0.01, treat=["万古霉素", "庆大霉素"], rare=True)
D("CA-CELLUL", "丹毒与蜂窝织炎", "derm", base=0.0007, org={"skin": 0.25},
  labs={"WBC": (3.5, "add"), "CRP": (45.0, "add")},
  sx=["局部红肿热痛", "边界清楚", "发热"], acute=True, dur=200.0, fever=0.5,
  pain=0.5, inflam=0.5, treat=["头孢氨苄", "青霉素"])
D("CA-SINUS", "急性鼻窦炎", "ent", base=0.003, risk={"allergen": 0.6, "pathogen": 0.5},
  org={"airway": 0.06}, labs={"CRP": (8.0, "add")},
  sx=["面部压迫感", "黄绿色脓涕", "嗅觉下降"], acute=True, dur=240.0, fever=0.25, pain=0.35,
  treat=["阿莫西林", "布地奈德鼻喷"])
D("CA-OTITIS", "急性中耳炎", "ent", base=0.002, risk={"pathogen": 0.6},
  org={"ear": 0.12}, sx=["耳深部胀痛", "听力发闷", "牵拉耳廓痛"], acute=True,
  dur=180.0, fever=0.35, pain=0.5, treat=["阿莫西林"])
D("CA-PHARYN", "链球菌性咽炎", "ent", base=0.002, risk={"pathogen": 0.7},
  org={}, labs={"WBC": (2.5, "add"), "ASO": (150.0, "add")},
  sx=["咽痛剧烈", "扁桃体脓点", "高热"], acute=True, dur=150.0, fever=0.75, pain=0.5,
  treat=["青霉素", "对乙酰氨基酚"])
D("CA-MONO", "传染性单核细胞增多症", "heme", base=0.0004,
  risk={"pathogen": 0.6}, org={"spleen": 0.18, "liver": 0.12},
  labs={"LYMPH_p": (22.0, "add"), "ALT": (70.0, "add"), "AST": (50.0, "add"),
        "PLT": (-40.0, "add")},
  sx=["持续高热", "咽痛明显", "颈部淋巴结肿大", "极度乏力", "左 upper 腹不适"],
  acute=True, dur=800.0, fever=0.7, inflam=0.35, treat=["对乙酰氨基酚"])
D("CA-HZV", "带状疱疹", "derm", base=0.0005,
  risk={"age": 0.9, "stress": 0.8, "immune": 0.7}, org={"nerve": 0.15, "skin": 0.15},
  labs={}, sx=["单侧沿神经分布的灼痛", "成簇水疱", "触痛明显"], acute=True,
  dur=500.0, pain=0.8, treat=["伐昔洛韦", "加巴喷丁"])
D("CA-VZV", "水痘", "derm", base=0.0003, risk={"pathogen": 0.7},
  org={"skin": 0.20}, sx=["全身瘙痒性皮疹", "低热"], acute=True, dur=300.0,
  fever=0.4, treat=["炉甘石洗剂", "阿昔洛韦"])
D("CA-MEASLES", "麻疹", "derm", base=0.00008, risk={"pathogen": 0.8},
  org={"skin": 0.25, "lungs": 0.10, "eye": 0.08},
  labs={"LYMPH_p": (-6.0, "add")},
  sx=["高热", "口腔黏膜斑", "自上而下皮疹", "畏光"], acute=True, dur=350.0,
  fever=0.9, inflam=0.3, treat=["维生素A"])
D("CA-MUMPS", "流行性腮腺炎", "ent", base=0.0001, risk={"pathogen": 0.7},
  org={"pancreas_exo": 0.10, "gonad": 0.08},
  labs={"AMY": (180.0, "add")},
  sx=["耳前腮腺肿痛", "张口困难", "发热"], acute=True, dur=300.0, fever=0.6, pain=0.5,
  treat=["对乙酰氨基酚"])
D("CA-LYME", "莱姆病", "rheum", base=0.00002, risk={"pathogen": 0.5},
  org={"joint": 0.20, "heart": 0.08, "nerve": 0.10},
  labs={"ESR": (25.0, "add"), "CRP": (20.0, "add")},
  sx=["游走性红斑", "关节游走性肿痛", "乏力"], dur=1200.0, fever=0.3, pain=0.4,
  treat=["多西环素"], rare=True)
D("CA-MALARIA", "疟疾", "heme", base=0.00002, risk={"pathogen": 0.6},
  org={"marrow": 0.25, "liver": 0.12, "kidney": 0.10},
  labs={"HGB": (-25.0, "add"), "TBIL": (20.0, "add"), "PLT": (-60.0, "add"),
        "LDH": (120.0, "add")},
  sx=["周期性寒战高热大汗", "脾区胀", "头痛"], acute=True, dur=400.0,
  fever=0.95, inflam=0.5, mortal=0.005, treat=["青蒿琥酯"], rare=True)
D("CA-DENGUE", "登革热", "heme", base=0.00003, risk={"pathogen": 0.6},
  org={"coag": 0.25, "marrow": 0.15},
  labs={"PLT": (-80.0, "add"), "WBC": (-2.5, "add"), "HCT": (4.0, "add"),
        "AST": (80.0, "add")},
  sx=["突发高热", "剧烈骨痛", "皮疹", "牙龈易出血"], acute=True, dur=300.0,
  fever=0.9, pain=0.6, mortal=0.002, treat=["对乙酰氨基酚"], rare=True)
D("CA-TYPHOID", "伤寒", "gi", base=0.00002, risk={"hygiene": 0.7},
  org={"gut": 0.20, "liver": 0.12}, labs={"WBC": (-1.0, "add"), "CRP": (40.0, "add")},
  sx=["持续高热", "玫瑰疹", "相对缓脉", "腹胀"], acute=True, dur=500.0,
  fever=0.85, pain=0.4, treat=["头孢曲松"], rare=True)
D("CA-BRUCELL", "布鲁菌病", "rheum", base=0.00001, risk={"pathogen": 0.5},
  org={"joint": 0.18, "liver": 0.10},
  labs={"ESR": (28.0, "add")}, sx=["波状热", "大汗", "关节痛", "腰骶痛"],
  dur=1800.0, fever=0.6, pain=0.45, treat=["多西环素", "利福平"], rare=True)
D("CA-LEPTO", "钩端螺旋体病", "rheum", base=0.000008, risk={"pathogen": 0.5},
  org={"liver": 0.25, "kidney": 0.22, "muscle": 0.15},
  labs={"ALT": (90.0, "add"), "CREA": (40.0, "add"), "CK": (400.0, "add"),
        "TBIL": (25.0, "add")},
  sx=["腓肠肌压痛", "结膜充血", "发热", "少尿"], acute=True, dur=400.0,
  fever=0.8, pain=0.6, treat=["青霉素"], rare=True)
D("CA-INFECT-ENDO", "感染性腹泻（细菌性）", "gi", base=0.0016, risk={"hygiene": 0.7},
  org={"gut": 0.18}, labs={"WBC": (2.0, "add"), "K": (-0.3, "add")},
  sx=["黏液脓血便", "里急后重", "发热"], acute=True, dur=130.0, fever=0.5, pain=0.4,
  treat=["左氧氟沙星", "口服补液盐"])
D("CA-GIARDIA", "贾第虫病", "gi", base=0.00005, risk={"hygiene": 0.6},
  org={"gut": 0.15}, sx=["油腻恶臭腹泻", "腹胀", "体重下降"], dur=800.0,
  treat=["甲硝唑"], rare=True)
D("CA-CANDIDA", "念珠菌感染", "derm", base=0.0004, risk={"immune": 0.7, "sugar": 0.6},
  org={"skin": 0.10}, sx=["口腔白膜", "外阴瘙痒", "灼痛"], dur=300.0,
  treat=["氟康唑"])
D("CA-ASPERGILLUS", "侵袭性曲霉病", "resp", base=0.000006,
  risk={"immune": 1.2}, org={"lungs": 0.40},
  labs={"CRP": (60.0, "add")}, sx=["持续发热不退", "咳嗽", "痰中带血"], dur=600.0,
  fever=0.7, mortal=0.02, treat=["伏立康唑"], rare=True)
D("CA-SCABIES", "疥疮", "derm", base=0.0002, risk={"hygiene": 0.8},
  org={"skin": 0.12}, sx=["夜间剧烈瘙痒", "指缝丘疹"], dur=700.0, pain=0.3,
  treat=["氯菊酯"])
D("CA-OSTEO", "急性骨髓炎", "msk", base=0.00003, risk={"pathogen": 0.6},
  org={"bone": 0.25, "marrow": 0.10},
  labs={"WBC": (4.0, "add"), "CRP": (70.0, "add"), "ESR": (40.0, "add")},
  sx=["局部深部骨痛", "压痛", "发热"], dur=600.0, fever=0.6, pain=0.7,
  treat=["万古霉素"], rare=True)
D("CA-PROSTAT", "急性前列腺炎", "repro", base=0.0003, risk={"water": 0.5},
  org={"bladder": 0.15}, labs={"WBC": (3.0, "add"), "CRP": (40.0, "add")},
  sx=["会阴胀痛", "排尿灼痛", "发热"], acute=True, dur=280.0, fever=0.6, pain=0.6,
  treat=["左氧氟沙星"], sex="m")

# ======================================================================
# 心血管
# ======================================================================
D("CV-HTN", "原发性高血压", "cardio", base=0.0012,
  risk={"age": 1.2, "bmi": 0.9, "salt": 1.0, "stress": 0.6, "alcohol": 0.5,
        "sedentary": 0.5},
  org={"vessels": 0.20, "heart": 0.10, "kidney": 0.08},
  labs={"SBP": (28.0, "add"), "DBP": (14.0, "add")},
  sx=["后颈发紧", "晨起枕部头痛", "耳鸣"], dur=None, treat=["氨氯地平", "缬沙坦", "氢氯噻嗪"])
D("CV-AS", "动脉粥样硬化", "cardio", base=0.0009,
  risk={"LDL": 1.4, "smoking": 1.4, "bmi": 0.8, "age": 1.0, "sugar": 0.7},
  org={"vessels": 0.28, "heart": 0.08, "brain": 0.06},
  labs={"LDL": (1.2, "add"), "TC": (1.0, "add"), "ApoB": (0.2, "add")},
  sx=["活动后胸闷", "下肢发凉"], dur=None, inflam=0.10, treat=["阿托伐他汀", "瑞舒伐他汀"])
D("CV-CAD", "冠心病（稳定型心绞痛）", "cardio", base=0.00035,
  risk={"LDL": 1.2, "smoking": 1.3, "age": 1.0, "bmi": 0.7, "stress": 0.5},
  org={"heart": 0.24, "vessels": 0.15},
  labs={"hsTnI": (8.0, "add"), "LDL": (0.9, "add")},
  sx=["劳力性胸骨后压榨感", "休息数分钟缓解", "向左臂放射"], dur=None, pain=0.25,
  treat=["阿司匹林", "阿托伐他汀", "美托洛尔", "硝酸甘油"])
D("CV-MI", "急性心肌梗死", "cardio", base=0.00006,
  risk={"LDL": 1.5, "smoking": 1.8, "age": 1.2, "bmi": 0.8},
  org={"heart": 0.45, "lungs": 0.15, "kidney": 0.10},
  labs={"hsTnI": (900.0, "add"), "CKMB": (90.0, "add"), "MYO": (200.0, "add"),
        "NTproBNP": (600.0, "add"), "LAC": (1.8, "add"), "SBP": (-18.0, "add")},
  sx=["持续胸骨后压榨痛超过 20 分钟", "冷汗", "濒死感", "恶心"], acute=True,
  dur=None, pain=0.95, inflam=0.4, mortal=0.06,
  treat=["阿司匹林", "氯吡格雷", "硝酸甘油", "美托洛尔"])
D("CV-HF", "慢性心力衰竭", "cardio", base=0.00012,
  risk={"age": 1.0, "bmi": 0.8, "smoking": 0.8, "SBP": 0.8},
  org={"heart": 0.45, "lungs": 0.20, "kidney": 0.18, "liver": 0.10},
  labs={"NTproBNP": (900.0, "add"), "Na": (-3.0, "add"), "CREA": (15.0, "add"),
        "U_PRO": (0.2, "add")},
  sx=["平卧气短", "夜间憋醒", "双下肢水肿", "活动耐量下降"], dur=None,
  pain=0.15, treat=["呋塞米", "沙库巴曲缬沙坦", "美托洛尔", "螺内酯"])
D("CV-AF", "心房颤动", "cardio", base=0.0004,
  risk={"age": 1.2, "alcohol": 0.9, "SBP": 0.7, "stress": 0.5},
  org={"heart": 0.20, "brain": 0.10},
  labs={"HR": (30.0, "add"), "NTproBNP": (200.0, "add")},
  sx=["心悸", "脉搏绝对不齐", "乏力", "活动后气短"], dur=None, treat=["美托洛尔", "利伐沙班"])
D("CV-SVT", "阵发性室上性心动过速", "cardio", base=0.0002, org={"heart": 0.10},
  labs={"HR": (70.0, "add")},
  sx=["突发心悸", "心率 150 以上", "头晕"], acute=True, dur=3.0, treat=["维拉帕米"])
D("CV-AS-VALVE", "主动脉瓣狭窄", "cardio", base=0.00006,
  risk={"age": 1.2}, org={"heart": 0.35},
  labs={"NTproBNP": (150.0, "add")},
  sx=["劳力性晕厥", "心绞痛", "气短"], dur=None, rare=True)
D("CV-MR", "二尖瓣反流", "cardio", base=0.00008, org={"heart": 0.25},
  labs={"NTproBNP": (100.0, "add")}, sx=["活动后气短", "心悸"], dur=None)
D("CV-DCM", "扩张型心肌病", "cardio", base=0.00004,
  risk={"alcohol": 0.8}, org={"heart": 0.50},
  labs={"NTproBNP": (700.0, "add")},
  sx=["进行性气短", "下肢水肿", "端坐呼吸"], dur=None, rare=True,
  treat=["呋塞米", "美托洛尔", "沙库巴曲缬沙坦"])
D("CV-HCM", "肥厚型心肌病", "cardio", base=0.00003, org={"heart": 0.35},
  labs={"NTproBNP": (200.0, "add")},
  sx=["活动后晕厥", "胸痛", "心悸"], dur=None, rare=True, treat=["美托洛尔"])
D("CV-MYOCARD", "急性心肌炎", "cardio", base=0.00008,
  risk={"pathogen": 0.7}, org={"heart": 0.35},
  labs={"hsTnI": (220.0, "add"), "CRP": (50.0, "add"), "NTproBNP": (300.0, "add")},
  sx=["发热后胸闷", "心悸", "活动耐量骤降"], acute=True, dur=500.0, fever=0.4,
  pain=0.35, treat=["美托洛尔", "呋塞米"])
D("CV-PERICARD", "急性心包炎", "cardio", base=0.00007,
  risk={"pathogen": 0.6}, org={"heart": 0.18},
  labs={"CRP": (60.0, "add"), "ESR": (30.0, "add")},
  sx=["胸痛随呼吸加重", "前倾坐位减轻", "心包摩擦音"], acute=True, dur=400.0,
  fever=0.4, pain=0.7, treat=["布洛芬", "秋水仙碱"])
D("CV-ANEURYSM", "腹主动脉瘤", "cardio", base=0.00003,
  risk={"smoking": 1.6, "age": 1.4, "SBP": 0.8}, org={"vessels": 0.30},
  sx=["腹部搏动性包块", "腰背隐痛"], dur=None, rare=True)
D("CV-DISSECT", "主动脉夹层", "cardio", base=0.000008,
  risk={"SBP": 1.5, "smoking": 1.0}, org={"vessels": 0.55, "heart": 0.25,
                                          "kidney": 0.20, "brain": 0.15},
  labs={"DD": (4.0, "add"), "SBP": (30.0, "add")},
  sx=["突发撕裂样胸背痛", "血压双臂不等", "濒死感"], acute=True, dur=None,
  pain=1.0, mortal=0.10, treat=["艾司洛尔", "硝普钠"], rare=True)
D("CV-PAD", "下肢动脉硬化闭塞", "cardio", base=0.0002,
  risk={"smoking": 1.5, "LDL": 1.0, "sugar": 0.8}, org={"vessels": 0.22, "muscle": 0.10},
  sx=["间歇性跛行", "足背动脉搏动减弱", "足凉"], dur=None, pain=0.4,
  treat=["阿司匹林", "西洛他唑"])
D("CV-DVT", "深静脉血栓", "cardio", base=0.0002,
  risk={"sedentary": 1.4, "bmi": 0.7, "smoking": 0.6}, org={"vessels": 0.18},
  labs={"DD": (2.2, "add")},
  sx=["单侧小腿肿胀", "腓肠肌压痛", "皮温升高"], acute=True, dur=600.0, pain=0.5,
  treat=["利伐沙班"])
D("CV-PE", "肺栓塞", "resp", base=0.00006,
  risk={"sedentary": 1.5, "bmi": 0.7, "coag": 0.8}, org={"lungs": 0.35, "heart": 0.20},
  labs={"DD": (5.5, "add"), "pO2": (-18.0, "add"), "SpO2": (-6.0, "add"),
        "NTproBNP": (400.0, "add"), "HR": (28.0, "add")},
  sx=["突发气短", "胸痛", "咳血", "晕厥"], acute=True, dur=None, pain=0.6,
  mortal=0.03, treat=["利伐沙班", "肝素"])
D("CV-ORTHOSTATIC", "体位性低血压", "cardio", base=0.0006,
  risk={"age": 0.9, "water": 0.6}, org={"vessels": 0.12},
  labs={"SBP": (-16.0, "add")},
  sx=["起身时眼前发黑", "头晕", "站立不稳"], dur=None)
D("CV-VT", "室性心动过速", "cardio", base=0.00002, org={"heart": 0.40},
  labs={"HR": (80.0, "add")}, sx=["心悸", "黑矇", "胸闷"], acute=True, dur=1.0,
  mortal=0.05, treat=["胺碘酮"])
D("CV-AVBLOCK", "房室传导阻滞", "cardio", base=0.00004,
  risk={"age": 0.9}, org={"heart": 0.25}, labs={"HR": (-28.0, "add")},
  sx=["乏力", "头晕", "活动后气短"], dur=None, rare=True)
D("CV-PHTN", "肺动脉高压", "resp", base=0.00002, org={"lungs": 0.30, "heart": 0.25},
  labs={"NTproBNP": (300.0, "add"), "pO2": (-8.0, "add")},
  sx=["活动后气短进行性加重", "晕厥", "下肢水肿"], dur=None, rare=True)
D("CV-CORPULM", "肺源性心脏病", "resp", base=0.00005,
  risk={"smoking": 1.4}, org={"heart": 0.30, "lungs": 0.25},
  labs={"NTproBNP": (250.0, "add"), "HGB": (12.0, "add")},
  sx=["活动后气短", "下肢水肿", "颈静脉充盈"], dur=None)
D("CV-RHEUM", "风湿性心脏病", "cardio", base=0.00002, risk={"pathogen": 0.5},
  org={"heart": 0.30}, labs={"ASO": (200.0, "add")},
  sx=["活动后气短", "关节痛史", "心脏杂音"], dur=None, rare=True, treat=["青霉素"])
D("CV-LONGQT", "长 QT 综合征", "cardio", base=0.000008, org={"heart": 0.20},
  sx=["运动时晕厥", "心悸"], dur=None, rare=True, mortal=0.002)
D("CV-ASD", "房间隔缺损", "cardio", base=0.000006, org={"heart": 0.20, "lungs": 0.10},
  sx=["活动后气短", "反复呼吸道感染"], dur=None, rare=True, age=(0.0, 40.0))
D("CV-TAKOTSUBO", "应激性心肌病", "cardio", base=0.00001,
  risk={"stress": 1.5}, org={"heart": 0.30},
  labs={"hsTnI": (150.0, "add"), "NTproBNP": (400.0, "add")},
  sx=["重大情绪事件后胸痛", "气短"], acute=True, dur=400.0, pain=0.6, rare=True)

# ======================================================================
# 呼吸
# ======================================================================
D("RS-ASTHMA", "支气管哮喘", "resp", base=0.0008,
  risk={"allergen": 1.4, "pm25": 0.9, "smoking": 0.7},
  org={"airway": 0.35, "lungs": 0.10},
  labs={"EO_p": (3.0, "add"), "IgE": (120.0, "add"), "pO2": (-6.0, "add")},
  sx=["发作性喘息", "呼气相延长", "夜间憋醒", "胸闷"], dur=None, treat=["沙丁胺醇", "布地奈德"])
D("RS-COPD", "慢性阻塞性肺疾病", "resp", base=0.0005,
  risk={"smoking": 2.0, "pm25": 0.8, "age": 0.8},
  org={"lungs": 0.35, "airway": 0.20, "heart": 0.10},
  labs={"pO2": (-12.0, "add"), "pCO2": (8.0, "add"), "HGB": (10.0, "add"),
        "SpO2": (-4.0, "add")},
  sx=["活动后气短", "慢性咳痰", "桶状胸"], dur=None, treat=["噻托溴铵", "沙美特罗"])
D("RS-EMPHYSEMA", "肺气肿", "resp", base=0.0002, risk={"smoking": 1.8},
  org={"lungs": 0.30}, labs={"pO2": (-8.0, "add")},
  sx=["气短", "呼气费力", "体重下降"], dur=None)
D("RS-BRONCHIECT", "支气管扩张", "resp", base=0.0001,
  risk={"pathogen": 0.7, "smoking": 0.6}, org={"lungs": 0.25, "airway": 0.20},
  labs={"CRP": (15.0, "add"), "HGB": (-8.0, "add")},
  sx=["大量黏痰", "反复痰中带血", "杵状指"], dur=None, treat=["阿莫西林克拉维酸"])
D("RS-ILD", "间质性肺病", "resp", base=0.00005,
  risk={"smoking": 0.8, "pm25": 0.7}, org={"lungs": 0.40},
  labs={"pO2": (-14.0, "add"), "LDH": (50.0, "add"), "SpO2": (-4.0, "add")},
  sx=["进行性气短", "干咳", "杵状指"], dur=None, rare=True)
D("RS-IPF", "特发性肺纤维化", "resp", base=0.000015,
  risk={"smoking": 1.0, "age": 1.2}, org={"lungs": 0.50},
  labs={"pO2": (-18.0, "add"), "LDH": (60.0, "add")},
  sx=["干咳", "进行性气短", "Velcro 啰音"], dur=None, rare=True, mortal=0.001)
D("RS-SARCOID", "肺结节病", "rheum", base=0.00002,
  org={"lungs": 0.20, "eye": 0.10, "skin": 0.08},
  labs={"ACE": (30.0, "add"), "Ca": (0.15, "add"), "ESR": (20.0, "add")},
  sx=["干咳", "乏力", "结节性红斑"], dur=None, rare=True, treat=["泼尼松"])
D("RS-PTX", "自发性气胸", "resp", base=0.00006,
  risk={"smoking": 1.2, "bmi": 0.6}, org={"lungs": 0.28},
  labs={"pO2": (-12.0, "add"), "SpO2": (-5.0, "add")},
  sx=["突发单侧胸痛", "吸气时加重", "气短"], acute=True, dur=300.0, pain=0.75,
  treat=["胸腔闭式引流"])
D("RS-PLEURAL", "胸腔积液", "resp", base=0.0001,
  risk={"pathogen": 0.5}, org={"lungs": 0.25},
  labs={"pO2": (-8.0, "add"), "CRP": (25.0, "add")},
  sx=["气短", "患侧呼吸音降低", "胸闷"], dur=None)
D("RS-OSA", "阻塞性睡眠呼吸暂停", "resp", base=0.0009,
  risk={"bmi": 1.5, "alcohol": 0.6, "age": 0.7}, org={"lungs": 0.10, "brain": 0.10},
  labs={"pCO2": (4.0, "add")},
  sx=["响亮打鼾", "晨起头痛", "白天嗜睡", "夜尿增多"], dur=None, treat=["CPAP"])
D("RS-CF", "囊性纤维化", "resp", base=0.000004,
  org={"lungs": 0.50, "pancreas_exo": 0.40, "gut": 0.20},
  labs={"Cl": (-6.0, "add"), "ALP": (40.0, "add")},
  sx=["反复肺部感染", "脂肪泻", "杵状指"], dur=None, rare=True, age=(0.0, 45.0))
D("RS-A1AT", "α1-抗胰蛋白酶缺乏症", "resp", base=0.000003,
  org={"lungs": 0.40, "liver": 0.20},
  sx=["早发肺气肿", "肝功能异常"], dur=None, rare=True)
D("RS-ARDS", "急性呼吸窘迫综合征", "resp", base=0.00002,
  risk={"pathogen": 1.0, "bmi": 0.6},
  org={"lungs": 0.55, "heart": 0.15, "brain": 0.15},
  labs={"pO2": (-45.0, "add"), "SpO2": (-12.0, "add"), "LAC": (2.0, "add")},
  sx=["进行性呼吸困难", "口唇发绀", "烦躁"], acute=True, dur=250.0, mortal=0.07,
  treat=["地塞米松", "机械通气"])
D("RS-ASPIRATION", "吸入性肺炎", "resp", base=0.00008,
  risk={"age": 0.9, "alcohol": 0.6}, org={"lungs": 0.28},
  labs={"CRP": (70.0, "add"), "WBC": (5.0, "add")},
  sx=["进食后呛咳咳痰", "发热", "右下肺啰音"], acute=True, dur=350.0, fever=0.7)
D("RS-SILICOSIS", "矽肺", "resp", base=0.00001, risk={"pm25": 1.8},
  org={"lungs": 0.35}, labs={"pO2": (-10.0, "add")},
  sx=["干咳", "渐进性气短"], dur=None, rare=True)
D("RS-HYPERSENS", "过敏性肺炎", "resp", base=0.00002,
  risk={"allergen": 1.5}, org={"lungs": 0.30},
  sx=["接触后发热咳嗽", "气短", "乏力"], dur=None, rare=True, treat=["泼尼松"])
D("RS-LARYNG", "急性喉炎", "ent", base=0.0008, risk={"pathogen": 0.6},
  org={"airway": 0.15}, sx=["声音嘶哑", "犬吠样咳", "吸气性喉鸣"], acute=True,
  dur=120.0, fever=0.3, treat=["布地奈德雾化"])

# ======================================================================
# 消化
# ======================================================================
D("GI-GERD", "胃食管反流病", "gi", base=0.0025,
  risk={"bmi": 1.0, "alcohol": 0.6, "salt": 0.4, "stress": 0.5},
  org={"gut": 0.10}, sx=["餐后烧心", "反酸", "夜间呛咳", "胸骨后灼痛"],
  dur=None, pain=0.3, treat=["奥美拉唑", "莫沙必利"])
D("GI-GASTRITIS", "慢性胃炎", "gi", base=0.002, risk={"salt": 0.6, "smoking": 0.5},
  org={"gut": 0.12}, sx=["上腹隐痛", "餐后饱胀", "嗳气"], dur=None, pain=0.3,
  treat=["奥美拉唑"])
D("GI-PUD", "消化性溃疡", "gi", base=0.0009,
  risk={"salt": 0.4, "smoking": 0.8, "alcohol": 0.6, "stress": 0.8},
  org={"gut": 0.18}, labs={"HGB": (-10.0, "add")},
  sx=["空腹痛", "夜间痛醒", "进食后缓解", "黑便史"], dur=None, pain=0.55,
  treat=["奥美拉唑", "阿莫西林", "克拉霉素"])
D("GI-UGIB", "上消化道出血", "gi", base=0.0002,
  risk={"alcohol": 1.2, "HGB": 1.0}, org={"gut": 0.20, "heart": 0.10},
  labs={"HGB": (-30.0, "add"), "BUN": (4.0, "add"), "HR": (18.0, "add"),
        "SBP": (-15.0, "add")},
  sx=["上腹剧痛", "柏油样便", "头晕心慌"], acute=True, dur=200.0,
  pain=0.5, mortal=0.01, treat=["奥美拉唑", "生长抑素", "输血"])
D("GI-CELIAC", "乳糜泻", "gi", base=0.00008, org={"gut": 0.30},
  labs={"HGB": (-14.0, "add"), "FE": (-4.0, "add"), "FOL": (-6.0, "add"),
        "ALB": (-5.0, "add")},
  sx=["进食麦类后腹泻", "腹胀", "体重下降", "乏力"], dur=None, rare=True)
D("GI-IBD-UC", "溃疡性结肠炎", "gi", base=0.00012,
  risk={"stress": 0.8}, org={"gut": 0.30},
  labs={"CRP": (30.0, "add"), "ESR": (28.0, "add"), "HGB": (-18.0, "add"),
        "PLT": (60.0, "add"), "ALB": (-5.0, "add")},
  sx=["黏液脓血便", "里急后重", "左下腹痛", "便次增多"], dur=None, pain=0.55,
  inflam=0.4, treat=["美沙拉秦", "泼尼松"])
D("GI-IBD-CD", "克罗恩病", "gi", base=0.00008,
  org={"gut": 0.35}, labs={"CRP": (35.0, "add"), "HGB": (-20.0, "add"),
                            "ALB": (-6.0, "add"), "FERR": (-15.0, "add")},
  sx=["右下腹痛", "腹泻", "肛周瘘管", "体重下降"], dur=None, pain=0.6,
  inflam=0.45, rare=True, treat=["美沙拉秦", "英夫利西单抗"])
D("GI-IBS", "肠易激综合征", "gi", base=0.003,
  risk={"stress": 1.6, "fiber": 0.5}, org={"gut": 0.06},
  sx=["腹痛排便后缓解", "便次与性状改变", "腹胀"], dur=None, pain=0.35)
D("GI-CONSTIP", "慢性便秘", "gi", base=0.004,
  risk={"fiber": 1.2, "water": 0.8, "sedentary": 0.9}, org={"gut": 0.05},
  sx=["排便费力", "每周少于三次", "粪便干硬"], dur=None, pain=0.2)
D("GI-HEMORRHOID", "痔", "gi", base=0.002, risk={"fiber": 1.0, "sedentary": 0.8},
  org={"gut": 0.05}, labs={"HGB": (-5.0, "add")},
  sx=["便后滴血", "肛门异物感", "排便痛"], dur=None, pain=0.4)
D("GI-GALLSTONE", "胆囊结石", "gi", base=0.0009,
  risk={"bmi": 1.0, "sex": 0.7, "age": 0.6, "satfat": 0.6},
  org={"liver": 0.05}, labs={"ALP": (15.0, "add"), "GGT": (20.0, "add")},
  sx=["右上腹隐痛", "油腻餐后加重", "右肩放射"], dur=None, pain=0.35)
D("GI-CHOLANG", "急性胆管炎", "gi", base=0.00008,
  risk={"age": 0.7}, org={"liver": 0.30, "kidney": 0.12},
  labs={"TBIL": (70.0, "add"), "DBIL": (55.0, "add"), "ALP": (180.0, "add"),
        "GGT": (220.0, "add"), "WBC": (6.0, "add"), "CRP": (90.0, "add")},
  sx=["高热", "黄疸", "右上腹痛", "意识模糊"], acute=True, dur=200.0, fever=0.9,
  pain=0.8, inflam=0.8, mortal=0.02, treat=["头孢曲松", "甲硝唑"])
D("GI-CIRRHOSIS", "肝硬化", "gi", base=0.00015,
  risk={"alcohol": 2.0, "bmi": 0.9}, org={"liver": 0.55, "coag": 0.25,
                                          "spleen": 0.25, "kidney": 0.12},
  labs={"ALB": (-12.0, "add"), "TBIL": (22.0, "add"), "PT": (3.5, "add"),
        "PLT": (-80.0, "add"), "CHE": (-3500.0, "add"), "AMM": (18.0, "add")},
  sx=["腹胀", "乏力", "下肢水肿", "蜘蛛痣", "牙龈易出血"], dur=None, inflam=0.2,
  treat=["螺内酯", "呋塞米", "乳果糖"])
D("GI-NAFLD", "非酒精性脂肪肝", "gi", base=0.0025,
  risk={"bmi": 1.6, "sugar": 1.2, "TG": 1.0, "sedentary": 0.9},
  org={"liver": 0.18}, labs={"ALT": (28.0, "add"), "GGT": (25.0, "add"),
                              "TG": (0.6, "add")},
  sx=["右上腹闷胀", "乏力"], dur=None, treat=["二甲双胍"])
D("GI-NASH", "脂肪性肝炎", "gi", base=0.0006,
  risk={"bmi": 1.8, "sugar": 1.5}, org={"liver": 0.32},
  labs={"ALT": (70.0, "add"), "AST": (45.0, "add"), "FERR": (80.0, "add")},
  sx=["右上腹不适", "疲劳"], dur=None, inflam=0.2)
D("GI-PANCC", "慢性胰腺炎", "gi", base=0.00006,
  risk={"alcohol": 2.2, "smoking": 1.0}, org={"pancreas_exo": 0.45,
                                              "pancreas_endo": 0.25},
  labs={"AMY": (60.0, "add"), "ALB": (-4.0, "add"), "FPG": (1.2, "add")},
  sx=["上腹慢性痛向背放射", "脂肪泻", "体重下降"], dur=None, pain=0.6)
D("GI-OBSTRUCT", "肠梗阻", "gi", base=0.00006,
  risk={"age": 0.8}, org={"gut": 0.35, "kidney": 0.10},
  labs={"K": (-0.8, "add"), "BUN": (5.0, "add"), "WBC": (4.0, "add"),
        "LAC": (1.2, "add")},
  sx=["阵发性绞痛", "呕吐", "停止排气排便", "腹胀"], acute=True, dur=None,
  pain=0.9, mortal=0.02, treat=["胃肠减压", "乳酸林格"])
D("GI-DIVERTIC", "结肠憩室", "gi", base=0.0008,
  risk={"age": 0.9, "fiber": 0.8}, org={"gut": 0.08},
  sx=["左下腹隐痛", "排便习惯改变"], dur=None, pain=0.25)
D("GI-DIVERTICULITIS", "憩室炎", "gi", base=0.0002,
  risk={"age": 0.9, "fiber": 0.7}, org={"gut": 0.22},
  labs={"WBC": (4.0, "add"), "CRP": (60.0, "add")},
  sx=["左下腹持续痛", "发热", "腹泻或便秘"], acute=True, dur=300.0, fever=0.6,
  pain=0.7, treat=["头孢曲松", "甲硝唑"])
D("GI-HERNIA", "腹股沟疝", "gi", base=0.0003, risk={"bmi": 0.6},
  org={"gut": 0.05}, sx=["站立时腹股沟包块", "坠胀感"], dur=None, pain=0.3)
D("GI-APPEND-CHRONIC", "慢性阑尾炎", "gi", base=0.0002,
  org={"gut": 0.04}, sx=["右下腹间断隐痛"], dur=None, pain=0.2)
D("GI-FISSURE", "肛裂", "gi", base=0.0008, risk={"fiber": 0.9},
  org={"gut": 0.03}, sx=["排便时刀割样痛", "便纸带血"], dur=None, pain=0.5)
D("GI-ESOPHAGITIS", "反流性食管炎", "gi", base=0.0006,
  risk={"bmi": 0.7, "alcohol": 0.5}, org={"gut": 0.10},
  sx=["吞咽时胸骨后痛", "烧心"], dur=None, pain=0.35, treat=["奥美拉唑"])
D("GI-VARICES", "食管胃底静脉曲张", "gi", base=0.00005,
  risk={"alcohol": 1.5}, org={"gut": 0.15, "liver": 0.3},
  labs={"PLT": (-60.0, "add"), "ALB": (-10.0, "add")},
  sx=["多数无症状，可突发黑便"], dur=None, rare=True, mortal=0.003)
D("GI-LACTOSE", "乳糖不耐受", "gi", base=0.0012, org={"gut": 0.06},
  sx=["饮奶后腹胀腹泻", "肠鸣"], dur=None, pain=0.2)
D("GI-SIBO", "小肠细菌过度生长", "gi", base=0.0002,
  risk={"fiber": 0.4}, org={"gut": 0.12},
  sx=["腹胀", "腹泻", "体重下降"], dur=None, pain=0.3, rare=True)
D("GI-WHIPPLE", "Whipple 病", "gi", base=0.000002,
  org={"gut": 0.35, "joint": 0.20, "brain": 0.10},
  labs={"ALB": (-8.0, "add"), "HGB": (-15.0, "add")},
  sx=["脂肪泻", "体重下降", "关节痛", "认知变慢"], dur=None, rare=True)
D("GI-HEPATITIS-A", "甲型肝炎", "gi", base=0.00004, risk={"hygiene": 0.7},
  org={"liver": 0.25}, labs={"ALT": (700.0, "add"), "AST": (500.0, "add"),
                              "TBIL": (30.0, "add")},
  sx=["发热", "恶心", "尿色变深", "黄疸"], acute=True, dur=900.0, fever=0.5,
  inflam=0.3, treat=["休息与补液"])
D("GI-AUTOIMMUNE-HEP", "自身免疫性肝炎", "gi", base=0.00002,
  org={"liver": 0.35}, labs={"ALT": (120.0, "add"), "IgG": (6.0, "add"),
                              "ANA": (2.0, "add")},
  sx=["乏力", "关节痛", "右上腹不适"], dur=None, rare=True, treat=["泼尼松"])
D("GI-PBC", "原发性胆汁性胆管炎", "gi", base=0.000015,
  org={"liver": 0.30}, labs={"ALP": (250.0, "add"), "GGT": (180.0, "add"),
                              "TBIL": (15.0, "add")},
  sx=["瘙痒", "乏力", "黄疸"], dur=None, rare=True, treat=["熊去氧胆酸"])
D("GI-PSC", "原发性硬化性胆管炎", "gi", base=0.00001,
  org={"liver": 0.35}, labs={"ALP": (300.0, "add"), "GGT": (200.0, "add")},
  sx=["乏力", "瘙痒", "黄疸"], dur=None, rare=True)

# ======================================================================
# 肾脏与泌尿
# ======================================================================
D("RN-AKI", "急性肾损伤", "renal", base=0.0002,
  risk={"water": 1.0, "SBP": 0.9, "age": 0.7},
  org={"kidney": 0.40, "kidney_tubule": 0.25},
  labs={"CREA": (150.0, "add"), "BUN": (12.0, "add"), "K": (0.8, "add"),
        "U_PRO": (0.3, "add"), "HCO3": (-5.0, "add")},
  sx=["尿量骤减", "下肢水肿", "恶心", "乏力"], acute=True, dur=400.0, mortal=0.02,
  treat=["液体复苏", "呋塞米"])
D("RN-CKD", "慢性肾脏病", "renal", base=0.0003,
  risk={"sugar": 1.4, "SBP": 1.2, "age": 1.0, "UA": 0.6},
  org={"kidney": 0.55, "kidney_tubule": 0.35, "heart": 0.12, "bone": 0.20},
  labs={"CREA": (120.0, "add"), "BUN": (10.0, "add"), "eGFR": (-45.0, "add"),
        "P": (0.4, "add"), "Ca": (-0.18, "add"), "PTH": (60.0, "add"),
        "HGB": (-18.0, "add"), "HCO3": (-4.0, "add")},
  sx=["夜尿增多", "乏力", "下肢水肿", "皮肤痒", "食欲差"], dur=None,
  treat=["缬沙坦", "碳酸钙", "促红素"])
D("RN-NEPHROTIC", "肾病综合征", "renal", base=0.00008,
  org={"kidney": 0.45, "coag": 0.15, "immune": 0.10},
  labs={"U_PRO": (1.8, "add"), "ALB": (-16.0, "add"), "TC": (2.5, "add"),
        "CREA": (20.0, "add"), "FIB": (1.0, "add")},
  sx=["眼睑与下肢水肿", "泡沫尿", "体重短期增加"], dur=None, pain=0.2,
  treat=["泼尼松", "呋塞米", "阿托伐他汀"])
D("RN-IGAN", "IgA 肾病", "renal", base=0.0001,
  org={"kidney": 0.35}, labs={"U_BLD": (0.8, "add"), "U_PRO": (0.6, "add"),
                               "CREA": (25.0, "add")},
  sx=["感冒后肉眼血尿", "腰痛", "泡沫尿"], dur=None, rare=True)
D("RN-GN", "急进性肾小球肾炎", "renal", base=0.00002,
  org={"kidney": 0.60}, labs={"CREA": (300.0, "add"), "ANCA": (2.0, "add"),
                               "U_BLD": (1.5, "add"), "HGB": (-20.0, "add")},
  sx=["数周内肾功能恶化", "血尿", "水肿", "气短"], dur=None, mortal=0.01,
  rare=True, treat=["甲泼尼龙", "环磷酰胺"])
D("RN-PKD", "多囊肾", "renal", base=0.00002,
  org={"kidney": 0.45, "liver": 0.10},
  labs={"CREA": (80.0, "add"), "U_BLD": (0.3, "add")},
  sx=["腰腹部胀痛", "高血压", "血尿"], dur=None, rare=True)
D("RN-STONE", "肾结石", "renal", base=0.0008,
  risk={"water": 1.2, "salt": 0.7, "UA": 0.8}, org={"kidney": 0.10},
  labs={"U_BLD": (0.9, "add"), "UA": (60.0, "add")},
  sx=["突发腰腹绞痛", "向会阴放射", "肉眼血尿", "恶心"], acute=True, dur=200.0,
  pain=0.95, treat=["坦索罗辛", "双氯芬酸"])
D("RN-HYDRONEPH", "肾积水", "renal", base=0.0001,
  risk={"age": 0.6}, org={"kidney": 0.25},
  labs={"CREA": (30.0, "add")}, sx=["腰部胀痛", "尿流变细"], dur=None, pain=0.45)
D("RN-RCC", "肾细胞癌", "renal", base=0.00002,
  risk={"smoking": 1.5, "bmi": 0.8, "age": 1.0}, org={"kidney": 0.40},
  labs={"HGB": (-15.0, "add"), "Ca": (0.20, "add"), "ESR": (30.0, "add"),
        "U_BLD": (0.6, "add")},
  sx=["无痛性血尿", "腰腹包块", "不明原因发热", "体重下降"], dur=None,
  rare=True, mortal=0.002)
D("RN-BLADDER-CA", "膀胱癌", "renal", base=0.00003,
  risk={"smoking": 1.8, "age": 1.0}, org={"bladder": 0.35},
  labs={"U_BLD": (1.6, "add")},
  sx=["间歇性无痛血尿", "尿频"], dur=None, rare=True, mortal=0.001)
D("RN-PROSTATE-CA", "前列腺癌", "repro", base=0.00004,
  risk={"age": 1.6}, org={"bladder": 0.20, "bone": 0.25},
  labs={"ALP": (60.0, "add")},
  sx=["排尿不畅", "骨痛", "夜尿"], dur=None, sex="m", rare=True, mortal=0.0006)
D("RN-BPH", "良性前列腺增生", "repro", base=0.0016,
  risk={"age": 1.6}, org={"bladder": 0.20},
  sx=["夜尿增多", "尿线细", "排尿不尽"], dur=None, sex="m", treat=["坦索罗辛", "非那雄胺"])
D("RN-INTERSTITIAL", "间质性肾炎", "renal", base=0.00003,
  risk={"NSAID": 1.5}, org={"kidney": 0.30, "kidney_tubule": 0.35},
  labs={"CREA": (60.0, "add"), "EO_p": (4.0, "add")},
  sx=["皮疹", "发热", "尿量变化"], dur=None, rare=True)
D("RN-ALPORT", "Alport 综合征", "renal", base=0.000004,
  org={"kidney": 0.45, "ear": 0.30, "eye": 0.20},
  labs={"U_BLD": (1.0, "add"), "CREA": (40.0, "add")},
  sx=["血尿", "感音性耳聋", "视力下降"], dur=None, rare=True)
D("RN-FANCONI", "Fanconi 综合征", "renal", base=0.000006,
  org={"kidney_tubule": 0.55}, labs={"P": (-0.5, "add"), "K": (-0.9, "add"),
                                      "HCO3": (-6.0, "add"), "U_GLU": (0.6, "add")},
  sx=["多尿", "肌无力", "骨痛"], dur=None, rare=True)
D("RN-RAS", "肾动脉狭窄", "renal", base=0.00002,
  risk={"SBP": 0.9, "smoking": 0.6}, org={"kidney": 0.25, "vessels": 0.2},
  labs={"CREA": (25.0, "add")}, sx=["难治性高血压", "夜尿"], dur=None, rare=True)

# ======================================================================
# 内分泌与代谢
# ======================================================================
D("EN-T1DM", "1 型糖尿病", "endo", base=0.00004,
  org={"pancreas_endo": 0.75, "kidney": 0.15, "nerve": 0.15, "eye": 0.15},
  labs={"FPG": (9.0, "add"), "HbA1c": (5.0, "add"), "CPEP": (-0.30, "add"),
        "U_KET": (0.5, "add")},
  sx=["多饮多尿", "体重下降", "乏力", "视物模糊"], dur=None, treat=["胰岛素"])
D("EN-T2DM", "2 型糖尿病", "endo", base=0.0018,
  risk={"bmi": 1.6, "sugar": 1.4, "sedentary": 1.0, "age": 1.0, "TG": 0.7},
  org={"pancreas_endo": 0.35, "fat_sens": 0.45, "kidney": 0.12,
       "nerve": 0.10, "eye": 0.10, "vessels": 0.15},
  labs={"FPG": (4.0, "add"), "HbA1c": (2.2, "add"), "INS": (8.0, "add"),
        "HOMA_IR": (3.0, "add"), "U_GLU": (0.4, "add")},
  sx=["多饮多尿", "伤口愈合慢", "手足麻木", "反复皮肤感染"], dur=None,
  treat=["二甲双胍", "达格列净", "胰岛素", "格列美脲"])
D("EN-PREDM", "糖尿病前期", "endo", base=0.004,
  risk={"bmi": 1.2, "sugar": 1.0}, org={"fat_sens": 0.25},
  labs={"FPG": (1.2, "add"), "HbA1c": (0.8, "add")},
  sx=["餐前心慌", "体重增加"], dur=None, treat=["二甲双胍"])
D("EN-METSYN", "代谢综合征", "metab", base=0.003,
  risk={"bmi": 1.5, "sedentary": 1.0, "salt": 0.8},
  org={"fat_sens": 0.30, "vessels": 0.15},
  labs={"TG": (0.8, "add"), "HDL": (-0.3, "add"), "SBP": (12.0, "add"),
        "FPG": (0.9, "add")},
  sx=["腹型肥胖", "乏力"], dur=None)
D("EN-DYSLIPID", "血脂异常", "metab", base=0.003,
  risk={"satfat": 1.3, "bmi": 0.9, "sedentary": 0.8},
  org={"vessels": 0.15}, labs={"LDL": (1.3, "add"), "TC": (1.2, "add")},
  sx=["多无明显症状"], dur=None, treat=["阿托伐他汀"])
D("EN-OBESITY", "肥胖症", "metab", base=0.004,
  risk={"kcal": 1.5, "sedentary": 1.2}, org={"fat": 0.5, "joint": 0.15},
  labs={"TG": (0.5, "add"), "HDL": (-0.2, "add")},
  sx=["活动后气短", "关节负担", "白天嗜睡"], dur=None, treat=["司美格鲁肽"])
D("EN-HASHIMOTO", "桥本甲状腺炎", "endo", base=0.0007,
  risk={"sex": 0.8, "stress": 0.6}, org={"thyroid": 0.45},
  labs={"TSH": (8.0, "add"), "FT4": (-4.0, "add"), "TPOAb": (400.0, "add")},
  sx=["怕冷", "乏力", "便秘", "体重增加", "皮肤干"], dur=None, treat=["左甲状腺素"])
D("EN-HYPOTHY", "甲状腺功能减退", "endo", base=0.0005,
  risk={"sex": 0.6}, org={"thyroid": 0.40, "heart": 0.10},
  labs={"TSH": (12.0, "add"), "FT4": (-5.0, "add"), "TC": (1.2, "add"),
        "CK": (80.0, "add")},
  sx=["怕冷", "嗜睡", "体重增加", "记忆变慢", "月经过多"], dur=None,
  treat=["左甲状腺素"])
D("EN-GRAVES", "Graves 病", "endo", base=0.0004,
  risk={"sex": 0.9, "stress": 0.8, "smoking": 0.5}, org={"thyroid": 0.40,
                                                        "heart": 0.20, "eye": 0.15},
  labs={"TSH": (-0.25, "add"), "FT4": (18.0, "add"), "FT3": (8.0, "add"),
        "HR": (22.0, "add")},
  sx=["心悸", "怕热多汗", "体重下降", "手抖", "眼球突出", "易怒"], dur=None,
  treat=["甲巯咪唑", "普萘洛尔"])
D("EN-THYROID-NODULE", "甲状腺结节", "endo", base=0.0015,
  risk={"sex": 0.7, "age": 0.6}, org={"thyroid": 0.08},
  sx=["颈部异物感", "吞咽不适"], dur=None)
D("EN-THYROID-CA", "甲状腺癌", "endo", base=0.00005,
  risk={"age": 0.8}, org={"thyroid": 0.30},
  labs={"Tg": (120.0, "add")},
  sx=["颈部无痛性肿块", "声音嘶哑"], dur=None, rare=True, mortal=0.0003)
D("EN-CUSHING", "库欣综合征", "endo", base=0.00003,
  org={"adrenal": 0.35, "bone": 0.25, "fat": 0.3, "fat_sens": 0.3},
  labs={"COR_8am": (350.0, "add"), "ACTH": (-18.0, "add"), "FPG": (1.8, "add"),
        "K": (-0.5, "add")},
  sx=["满月脸", "向心性肥胖", "紫纹", "肌无力", "情绪波动"], dur=None, rare=True)
D("EN-ADDISON", "原发性肾上腺皮质功能减退", "endo", base=0.00002,
  org={"adrenal": 0.65}, labs={"COR_8am": (-120.0, "add"), "ACTH": (90.0, "add"),
                                "Na": (-6.0, "add"), "K": (0.9, "add")},
  sx=["极度乏力", "体位性头晕", "皮肤变黑", "食欲差", "喜咸食"], dur=None,
  rare=True, treat=["氢化可的松"])
D("EN-CONN", "原发性醛固酮增多症", "endo", base=0.00006,
  org={"adrenal": 0.20, "kidney": 0.12},
  labs={"ALD": (280.0, "add"), "RENIN": (-0.4, "add"), "ARR": (60.0, "add"),
        "K": (-1.0, "add"), "SBP": (22.0, "add")},
  sx=["难治性高血压", "肌无力", "夜尿多"], dur=None, rare=True, treat=["螺内酯"])
D("EN-PHEO", "嗜铬细胞瘤", "endo", base=0.000015,
  org={"adrenal": 0.25, "heart": 0.20, "vessels": 0.2},
  labs={"HR": (30.0, "add"), "SBP": (40.0, "add"), "FPG": (1.2, "add")},
  sx=["阵发性头痛心悸出汗三联征", "血压骤升"], dur=None, rare=True)
D("EN-ACROMEGALY", "肢端肥大症", "endo", base=0.00001,
  org={"pituitary": 0.30, "heart": 0.20, "joint": 0.15},
  labs={"IGF1": (300.0, "add"), "GH": (8.0, "add"), "FPG": (1.5, "add")},
  sx=["手足变大", "下颌前突", "打鼾加重", "视野缺损"], dur=None, rare=True)
D("EN-PROLACTINOMA", "催乳素瘤", "endo", base=0.00004,
  org={"pituitary": 0.25, "gonad": 0.30},
  labs={"PRL": (180.0, "add"), "TST": (-6.0, "add")},
  sx=["月经紊乱或闭经", "乳房胀痛", "精力与兴趣下降", "头痛"], dur=None, rare=True,
  treat=["卡麦角林"])
D("EN-HYPOPIT", "腺垂体功能减退", "endo", base=0.00002,
  org={"pituitary": 0.60, "thyroid": 0.25, "adrenal": 0.25, "gonad": 0.3},
  labs={"FT4": (-5.0, "add"), "COR_8am": (-100.0, "add"), "IGF1": (-60.0, "add")},
  sx=["乏力", "怕冷", "精力与兴趣下降", "低血糖"], dur=None, rare=True)
D("EN-DI", "尿崩症", "endo", base=0.00002,
  org={"pituitary": 0.30, "kidney_tubule": 0.20},
  labs={"Na": (6.0, "add"), "OSM": (12.0, "add"), "U_SG": (-0.010, "add")},
  sx=["极度口渴", "大量低比重尿", "夜尿"], dur=None, rare=True, treat=["去氨加压素"])
D("EN-SIADH", "抗利尿激素分泌不当综合征", "endo", base=0.00002,
  org={}, labs={"Na": (-9.0, "add"), "OSM": (-14.0, "add"), "ADH_osm": (250.0, "add")},
  sx=["乏力", "恶心", "意识模糊", "抽搐"], dur=None, rare=True)
D("EN-PCOS", "多囊卵巢综合征", "repro", base=0.0012,
  risk={"bmi": 1.2}, org={"gonad": 0.30, "fat_sens": 0.3},
  labs={"TST": (1.2, "add"), "LH": (6.0, "add"), "INS": (6.0, "add")},
  sx=["月经稀发", "多毛痤疮", "体重增加", "不孕"], dur=None, sex="f")
D("EN-HYPOGONAD", "性腺功能减退", "endo", base=0.0004,
  risk={"age": 0.8, "bmi": 0.6}, org={"gonad": 0.45},
  labs={"TST": (-9.0, "add")},
  sx=["精力与兴趣下降", "乏力", "肌肉减少", "情绪低落"], dur=None, sex="m",
  treat=["睾酮"])
D("EN-OSTEOPOR", "骨质疏松", "msk", base=0.0012,
  risk={"age": 1.4, "sex": 1.0, "vitd": 0.8, "sedentary": 0.8, "smoking": 0.5},
  org={"bone": 0.45}, labs={"Ca": (-0.10, "add"), "PTH": (12.0, "add")},
  sx=["腰背痛", "身高变矮", "轻微外力骨折"], dur=None, pain=0.35,
  treat=["阿仑膦酸", "碳酸钙", "维生素D"])
D("EN-OSTEOMALACIA", "骨软化症", "msk", base=0.0001,
  risk={"vitd": 1.5, "sun": 1.0}, org={"bone": 0.40},
  labs={"Ca": (-0.20, "add"), "P": (-0.30, "add"), "ALP": (120.0, "add"),
        "PTH": (40.0, "add")},
  sx=["骨痛", "肌无力", "走路摇摆"], dur=None, pain=0.5, treat=["维生素D", "碳酸钙"])
D("EN-VITD-DEF", "维生素 D 缺乏", "endo", base=0.004,
  risk={"sun": 1.2, "vitd": 1.0}, org={"bone": 0.15, "immune": 0.10},
  labs={"VD_25": (-30.0, "add")},
  sx=["乏力", "骨痛", "易感冒", "情绪低落"], dur=None, treat=["维生素D"])
D("EN-HYPERPTH", "甲状旁腺功能亢进", "endo", base=0.00006,
  org={"bone": 0.30, "kidney": 0.20},
  labs={"PTH": (120.0, "add"), "Ca": (0.50, "add"), "P": (-0.30, "add")},
  sx=["骨痛", "肾结石", "乏力", "便秘"], dur=None, rare=True)
D("EN-HYPOPTH", "甲状旁腺功能减退", "endo", base=0.00002,
  org={"bone": 0.15}, labs={"PTH": (-12.0, "add"), "Ca": (-0.45, "add"),
                             "P": (0.35, "add")},
  sx=["手足搐搦", "口周麻木", "肌肉痉挛"], dur=None, rare=True)
D("EN-GOUT", "痛风", "rheum", base=0.0008,
  risk={"UA": 1.4, "alcohol": 1.2, "bmi": 0.8, "satfat": 0.6},
  org={"joint": 0.18, "kidney": 0.15},
  labs={"UA": (180.0, "add"), "CRP": (20.0, "add")},
  sx=["第一跖趾关节夜间剧痛", "红肿热", "触碰即痛"], acute=True, dur=200.0,
  pain=0.9, inflam=0.4, treat=["秋水仙碱", "别嘌醇", "双氯芬酸"])
D("EN-HYPERURIC", "高尿酸血症", "metab", base=0.002,
  risk={"alcohol": 1.0, "bmi": 0.8}, org={"kidney": 0.08},
  labs={"UA": (120.0, "add")}, sx=["多无症状"], dur=None, treat=["别嘌醇"])
D("EN-MEN1", "多发性内分泌腺瘤病 1 型", "endo", base=0.000002,
  org={"pituitary": 0.25, "pancreas_endo": 0.25, "thyroid": 0.2},
  labs={"PRL": (80.0, "add"), "Ca": (0.35, "add")},
  sx=["反复溃疡", "肾结石", "低血糖"], dur=None, rare=True)
D("EN-MEN2", "多发性内分泌腺瘤病 2 型", "endo", base=0.000001,
  org={"thyroid": 0.35, "adrenal": 0.25},
  labs={"COR_8am": (200.0, "add")},
  sx=["甲状腺髓样癌", "阵发高血压"], dur=None, rare=True)
D("EN-KLINE", "Klinefelter 综合征", "endo", base=0.00004,
  org={"gonad": 0.50}, labs={"TST": (-12.0, "add"), "LH": (10.0, "add")},
  sx=["身材偏高", "青春期发育延迟", "不育", "身材高"], dur=None, sex="m", rare=True)
D("EN-TURNER", "Turner 综合征", "endo", base=0.00002,
  org={"gonad": 0.60, "heart": 0.25},
  labs={"E2": (-40.0, "add")},
  sx=["身材矮小", "原发闭经", "颈蹼"], dur=None, sex="f", rare=True)

# ======================================================================
# 血液
# ======================================================================
D("HM-IDA", "缺铁性贫血", "heme", base=0.0025,
  risk={"iron": 1.4, "sex": 0.6}, org={"marrow": 0.15},
  labs={"HGB": (-30.0, "add"), "MCV": (-12.0, "add"), "MCH": (-8.0, "add"),
        "FERR": (-20.0, "add"), "TSAT": (-14.0, "add"), "RDW": (2.5, "add")},
  sx=["乏力", "头晕", "活动后心慌", "异食癖", "指甲变脆"], dur=None,
  treat=["琥珀酸亚铁", "维生素C"])
D("HM-B12", "维生素 B12 缺乏性贫血", "heme", base=0.0004,
  risk={"b12": 1.5}, org={"marrow": 0.20, "nerve": 0.25},
  labs={"HGB": (-25.0, "add"), "MCV": (16.0, "add"), "B12": (-90.0, "add"),
        "LDH": (80.0, "add")},
  sx=["乏力", "手脚麻木", "舌面光滑", "走路不稳"], dur=None,
  treat=["甲钴胺"])
D("HM-FOLATE", "叶酸缺乏性贫血", "heme", base=0.0003,
  risk={"folate": 1.5}, org={"marrow": 0.15},
  labs={"HGB": (-22.0, "add"), "MCV": (12.0, "add"), "FOL": (-6.0, "add")},
  sx=["乏力", "头晕", "舌痛"], dur=None, treat=["叶酸"])
D("HM-THAL", "地中海贫血", "heme", base=0.00006,
  org={"marrow": 0.30, "spleen": 0.20, "bone": 0.10},
  labs={"HGB": (-32.0, "add"), "MCV": (-14.0, "add"), "MCH": (-6.0, "add"),
        "RDW": (1.0, "add"), "TBIL": (10.0, "add")},
  sx=["苍白", "黄疸", "脾大", "骨痛"], dur=None, rare=True)
D("HM-SICKLE", "镰状细胞病", "heme", base=0.00002,
  org={"marrow": 0.35, "spleen": 0.35, "kidney": 0.15, "bone": 0.15},
  labs={"HGB": (-30.0, "add"), "TBIL": (25.0, "add"), "LDH": (180.0, "add")},
  sx=["骨与腹部剧痛危象", "黄疸", "反复感染"], dur=None, pain=0.6, rare=True)
D("HM-G6PD", "G6PD 缺乏症", "heme", base=0.00004,
  risk={"pathogen": 0.4}, org={"marrow": 0.15},
  labs={"HGB": (-35.0, "add"), "TBIL": (30.0, "add"), "LDH": (200.0, "add")},
  sx=["进食蚕豆或药物后酱油色尿", "黄疸", "乏力"], acute=True, dur=300.0,
  rare=True)
D("HM-AA", "再生障碍性贫血", "heme", base=0.000015,
  risk={"pathogen": 0.5}, org={"marrow": 0.80},
  labs={"HGB": (-45.0, "add"), "WBC": (-3.0, "add"), "PLT": (-110.0, "add"),
        "RET_p": (-1.2, "add")},
  sx=["进行性苍白", "皮下出血点", "反复感染发热"], dur=None, rare=True,
  mortal=0.004, treat=["环孢素", "抗胸腺细胞球蛋白"])
D("HM-MDS", "骨髓增生异常综合征", "heme", base=0.00002,
  risk={"age": 1.5}, org={"marrow": 0.55},
  labs={"HGB": (-30.0, "add"), "MCV": (10.0, "add"), "WBC": (-1.5, "add"),
        "PLT": (-60.0, "add")},
  sx=["贫血", "反复感染", "瘀斑"], dur=None, rare=True, mortal=0.002)
D("HM-AML", "急性髓系白血病", "heme", base=0.000012,
  risk={"age": 1.2}, org={"marrow": 0.80, "immune": 0.45, "coag": 0.30},
  labs={"WBC": (25.0, "add"), "HGB": (-40.0, "add"), "PLT": (-110.0, "add"),
        "NEUT_p": (-25.0, "add"), "LDH": (300.0, "add"), "FIB": (-1.2, "add")},
  sx=["发热", "进行性苍白", "牙龈出血", "骨痛", "乏力"], acute=True, dur=None,
  fever=0.6, mortal=0.02, rare=True, treat=["化疗"])
D("HM-ALL", "急性淋巴细胞白血病", "heme", base=0.000008,
  org={"marrow": 0.80, "immune": 0.5, "brain": 0.1},
  labs={"WBC": (30.0, "add"), "HGB": (-38.0, "add"), "PLT": (-100.0, "add"),
        "LDH": (350.0, "add")},
  sx=["骨与关节痛", "发热", "出血倾向", "淋巴结肿大"], acute=True, dur=None,
  mortal=0.015, rare=True, age=(0.0, 40.0))
D("HM-CML", "慢性髓性白血病", "heme", base=0.000008,
  org={"marrow": 0.45, "spleen": 0.45},
  labs={"WBC": (60.0, "add"), "HGB": (-15.0, "add"), "PLT": (150.0, "add"),
        "LDH": (150.0, "add")},
  sx=["巨脾", "乏力", "盗汗", "体重下降"], dur=None, rare=True, treat=["伊马替尼"])
D("HM-CLL", "慢性淋巴细胞白血病", "heme", base=0.000012,
  risk={"age": 1.4}, org={"marrow": 0.35, "immune": 0.35},
  labs={"LYMPH_p": (40.0, "add"), "WBC": (35.0, "add"), "HGB": (-12.0, "add"),
        "IgG": (-3.0, "add")},
  sx=["淋巴结肿大", "乏力", "反复感染"], dur=None, rare=True)
D("HM-HL", "霍奇金淋巴瘤", "heme", base=0.00001,
  org={"marrow": 0.25, "immune": 0.25},
  labs={"ESR": (40.0, "add"), "LDH": (80.0, "add")},
  sx=["无痛性颈部淋巴结肿大", "饮酒后淋巴结痛", "夜间盗汗", "体重下降"],
  dur=None, fever=0.35, rare=True, treat=["化疗"])
D("HM-NHL", "非霍奇金淋巴瘤", "heme", base=0.00002,
  org={"marrow": 0.35, "immune": 0.25, "gut": 0.1},
  labs={"LDH": (180.0, "add"), "ESR": (30.0, "add"), "UA": (80.0, "add")},
  sx=["多处淋巴结肿大", "腹胀", "盗汗", "体重下降"], dur=None, rare=True,
  mortal=0.001)
D("HM-MM", "多发性骨髓瘤", "heme", base=0.000012,
  risk={"age": 1.5}, org={"marrow": 0.55, "bone": 0.45, "kidney": 0.30},
  labs={"HGB": (-28.0, "add"), "Ca": (0.40, "add"), "CREA": (70.0, "add"),
        "TP": (18.0, "add"), "ESR": (50.0, "add"), "ALB": (-6.0, "add")},
  sx=["骨痛以腰背为主", "贫血", "反复感染", "夜尿增多"], dur=None, pain=0.6,
  rare=True, mortal=0.0015)
D("HM-ITP", "免疫性血小板减少症", "heme", base=0.00005,
  org={"coag": 0.30, "spleen": 0.15},
  labs={"PLT": (-90.0, "add")},
  sx=["皮肤瘀点瘀斑", "牙龈出血", "月经过多"], dur=None, rare=True,
  treat=["泼尼松"])
D("HM-TTP", "血栓性血小板减少性紫癜", "heme", base=0.000004,
  org={"coag": 0.50, "brain": 0.30, "kidney": 0.25, "marrow": 0.2},
  labs={"PLT": (-120.0, "add"), "LDH": (500.0, "add"), "HGB": (-25.0, "add"),
        "CREA": (40.0, "add")},
  sx=["意识模糊", "皮下出血", "发热", "少尿"], acute=True, dur=None,
  mortal=0.05, rare=True)
D("HM-HEMO-A", "血友病 A", "heme", base=0.000006,
  org={"coag": 0.55}, labs={"APTT": (20.0, "add"), "FIB": (0.0, "add")},
  sx=["关节自发出血", "深部血肿", "拔牙后出血不止"], dur=None, rare=True, sex="m")
D("HM-HEMO-B", "血友病 B", "heme", base=0.000003,
  org={"coag": 0.50}, labs={"APTT": (18.0, "add")},
  sx=["关节出血", "血肿"], dur=None, rare=True, sex="m")
D("HM-VWD", "血管性血友病", "heme", base=0.00002,
  org={"coag": 0.30}, labs={"vWF": (-55.0, "add"), "APTT": (8.0, "add")},
  sx=["鼻衄", "月经过多", "术后出血"], dur=None, rare=True)
D("HM-DIC", "弥散性血管内凝血", "heme", base=0.00002,
  risk={"pathogen": 1.0}, org={"coag": 0.60, "kidney": 0.25, "lungs": 0.2},
  labs={"PLT": (-100.0, "add"), "PT": (8.0, "add"), "FIB": (-1.8, "add"),
        "DD": (6.0, "add")},
  sx=["多部位出血", "休克", "少尿"], acute=True, dur=None, mortal=0.08, rare=True)
D("HM-PV", "真性红细胞增多症", "heme", base=0.00001,
  org={"marrow": 0.30, "coag": 0.20},
  labs={"HGB": (45.0, "add"), "HCT": (12.0, "add"), "PLT": (150.0, "add")},
  sx=["面部潮红", "头痛", "皮肤瘙痒", "血栓"], dur=None, rare=True)
D("HM-ET", "原发性血小板增多症", "heme", base=0.000012,
  org={"coag": 0.20}, labs={"PLT": (500.0, "add")},
  sx=["头痛", "肢端麻木", "血栓或出血"], dur=None, rare=True)
D("HM-NEUTROPENIA", "中性粒细胞减少症", "heme", base=0.0001,
  org={"immune": 0.35}, labs={"WBC": (-2.5, "add"), "NEUT_p": (-20.0, "add")},
  sx=["反复口腔溃疡", "低热", "乏力"], dur=None)

# ======================================================================
# 神经
# ======================================================================
D("NR-STROKE", "缺血性脑卒中", "neuro", base=0.00012,
  risk={"SBP": 1.2, "smoking": 1.2, "LDL": 1.0, "age": 1.1, "sugar": 0.8},
  org={"brain": 0.45, "nerve": 0.20},
  labs={"LAC": (0.8, "add")},
  sx=["突发单侧肢体无力", "言语不清", "口角歪斜", "视野缺损"], acute=True,
  dur=None, mortal=0.02, treat=["阿司匹林", "阿托伐他汀"])
D("NR-TIA", "短暂性脑缺血发作", "neuro", base=0.0003,
  risk={"SBP": 1.0, "smoking": 1.0}, org={"brain": 0.10},
  sx=["一过性肢体麻木", "短暂失语", "数分钟自行缓解"], acute=True, dur=24.0)
D("NR-ICH", "脑出血", "neuro", base=0.00006,
  risk={"SBP": 1.5, "alcohol": 1.0, "coag": 1.2}, org={"brain": 0.55},
  labs={"HR": (12.0, "add")},
  sx=["突发剧烈头痛", "呕吐", "意识障碍", "偏瘫"], acute=True, dur=None,
  pain=0.8, mortal=0.08, treat=["甘露醇", "尼莫地平"])
D("NR-SAH", "蛛网膜下腔出血", "neuro", base=0.00002,
  risk={"smoking": 1.0, "SBP": 0.9}, org={"brain": 0.45},
  sx=["霹雳样头痛", "颈项强直", "畏光"], acute=True, dur=None, pain=1.0,
  mortal=0.05, rare=True)
D("NR-MIGRAINE", "偏头痛", "neuro", base=0.004,
  risk={"stress": 1.2, "sleep_debt": 1.0, "sex": 0.6}, org={},
  sx=["单侧搏动性头痛", "畏光畏声", "恶心", "活动后加重"], acute=True, dur=24.0,
  pain=0.75, treat=["布洛芬", "舒马曲坦"])
D("NR-TTH", "紧张型头痛", "neuro", base=0.006,
  risk={"stress": 1.3, "sleep_debt": 1.0}, org={},
  sx=["双侧紧箍样头痛", "午后加重"], dur=12.0, pain=0.45, treat=["布洛芬"])
D("NR-EPILEPSY", "癫痫", "neuro", base=0.0002,
  org={"brain": 0.25}, sx=["突发意识丧失", "四肢抽搐", "发作后嗜睡"],
  dur=None, treat=["丙戊酸钠", "左乙拉西坦"])
D("NR-MS", "多发性硬化", "neuro", base=0.00004,
  risk={"sex": 0.8, "vitd": 0.7}, org={"brain": 0.30, "nerve": 0.35, "eye": 0.20},
  sx=["视力下降", "肢体麻木无力", "共济失调", "疲劳"], dur=None, rare=True,
  treat=["甲泼尼龙"])
D("NR-PARKINSON", "帕金森病", "neuro", base=0.00006,
  risk={"age": 1.6}, org={"brain": 0.35, "nerve": 0.2},
  sx=["静止性震颤", "动作变慢", "肌强直", "起步困难", "写字变小"], dur=None,
  treat=["左旋多巴"])
D("NR-ALZHEIMER", "阿尔茨海默病", "neuro", base=0.00008,
  risk={"age": 1.8, "sedentary": 0.6}, org={"brain": 0.45},
  sx=["近期记忆下降", "迷路", "语言找词困难", "性格改变"], dur=None,
  treat=["多奈哌齐"])
D("NR-ALS", "肌萎缩侧索硬化", "neuro", base=0.000006,
  org={"nerve": 0.60, "muscle": 0.45},
  sx=["进行性肌无力", "肌肉跳动", "说话含糊", "吞咽困难"], dur=None,
  rare=True, mortal=0.004)
D("NR-MG", "重症肌无力", "neuro", base=0.00002,
  org={"muscle": 0.35}, sx=["晨轻暮重的眼睑下垂", "复视", "咀嚼无力"],
  dur=None, rare=True, treat=["溴吡斯的明", "泼尼松"])
D("NR-GBS", "吉兰-巴雷综合征", "neuro", base=0.00001,
  risk={"pathogen": 0.7}, org={"nerve": 0.55, "muscle": 0.4},
  sx=["感染后对称性上升性无力", "腱反射消失", "吞咽困难"], acute=True, dur=None,
  rare=True, mortal=0.01)
D("NR-BELL", "贝尔面瘫", "neuro", base=0.0002, org={"nerve": 0.20},
  sx=["一侧面部肌肉瘫痪", "闭眼不全", "口角漏气"], acute=True, dur=500.0,
  treat=["泼尼松", "伐昔洛韦"])
D("NR-ENCEPH", "病毒性脑炎", "neuro", base=0.00002,
  risk={"pathogen": 0.8}, org={"brain": 0.40},
  labs={"WBC": (1.5, "add"), "CRP": (20.0, "add")},
  sx=["发热", "意识模糊", "抽搐", "行为异常"], acute=True, dur=350.0, fever=0.8,
  mortal=0.01, rare=True, treat=["阿昔洛韦"])
D("NR-CONCUSSION", "脑震荡", "neuro", base=0.0004, org={"brain": 0.12},
  sx=["头部外伤后头痛", "短暂失忆", "恶心", "注意力不集中"], acute=True, dur=200.0,
  pain=0.5)
D("NR-RADICULO", "腰椎间盘突出", "msk", base=0.0012,
  risk={"sedentary": 1.2, "bmi": 0.7, "age": 0.6}, org={"nerve": 0.18},
  sx=["腰痛向臀部下肢放射", "咳嗽时加重", "足趾麻木"], dur=None, pain=0.65,
  treat=["塞来昔布", "甲钴胺"])
D("NR-CARPAL", "腕管综合征", "msk", base=0.0008,
  risk={"sedentary": 1.0, "sugar": 0.5}, org={"nerve": 0.10},
  sx=["夜间手指麻木", "甩手缓解", "拇指无力"], dur=None, pain=0.35)
D("NR-NEUROPATHY", "周围神经病变", "neuro", base=0.0004,
  risk={"sugar": 1.4, "alcohol": 1.2}, org={"nerve": 0.30},
  sx=["双足袜套样麻木", "烧灼感", "夜间加重"], dur=None, pain=0.45,
  treat=["甲钴胺", "普瑞巴林"])
D("NR-BPPV", "良性阵发性位置性眩晕", "ent", base=0.0015,
  org={"ear": 0.10}, sx=["翻身时天旋地转", "持续数十秒", "恶心"], acute=True,
  dur=200.0, pain=0.1)
D("NR-MENIERE", "梅尼埃病", "ent", base=0.0002,
  org={"ear": 0.30}, sx=["发作性眩晕", "耳鸣", "耳闷", "波动性听力下降"],
  dur=None, rare=True)
D("NR-BRAIN-TUMOR", "脑肿瘤", "neuro", base=0.000015,
  org={"brain": 0.50, "eye": 0.15},
  sx=["晨起头痛加重", "喷射性呕吐", "癫痫发作", "视野缺损"], dur=None,
  pain=0.5, rare=True, mortal=0.002)
D("NR-DELIRIUM", "谵妄", "neuro", base=0.0003,
  risk={"age": 1.2, "pathogen": 0.6}, org={"brain": 0.20},
  sx=["注意力涣散", "昼夜颠倒", "视幻觉", "语无伦次"], acute=True, dur=150.0)
D("NR-HUNTINGTON", "亨廷顿病", "neuro", base=0.000004,
  org={"brain": 0.45, "muscle": 0.25},
  sx=["舞蹈样动作", "认知下降", "情绪不稳"], dur=None, rare=True)
D("NR-FRIEDREICH", "弗里德赖希共济失调", "neuro", base=0.000002,
  org={"nerve": 0.45, "heart": 0.30},
  sx=["进行性共济失调", "脊柱侧弯", "心肌病"], dur=None, rare=True)
D("NR-DMD", "杜氏肌营养不良", "msk", base=0.000003,
  org={"muscle": 0.65, "heart": 0.25, "lungs": 0.2},
  labs={"CK": (3000.0, "add")},
  sx=["男孩学步晚", "腓肠肌假性肥大", "上楼困难"], dur=None, rare=True,
  age=(0.0, 25.0), sex="m")
D("NR-SMA", "脊髓性肌萎缩", "neuro", base=0.000003,
  org={"nerve": 0.55, "muscle": 0.55},
  sx=["进行性近端肌无力", "腱反射消失"], dur=None, rare=True, age=(0.0, 30.0))

# ======================================================================
# 风湿免疫
# ======================================================================
D("RH-RA", "类风湿关节炎", "rheum", base=0.0005,
  risk={"sex": 1.2, "smoking": 1.0}, org={"joint": 0.40, "bone": 0.2, "lungs": 0.1},
  labs={"RF": (140.0, "add"), "CCP": (180.0, "add"), "ESR": (35.0, "add"),
        "CRP": (30.0, "add")},
  sx=["对称性小关节肿痛", "晨僵超过一小时", "握力下降"], dur=None, pain=0.6,
  inflam=0.4, treat=["甲氨蝶呤", "塞来昔布"])
D("RH-SLE", "系统性红斑狼疮", "rheum", base=0.00015,
  risk={"sex": 1.6}, org={"kidney": 0.35, "joint": 0.25, "skin": 0.2,
                           "marrow": 0.2, "brain": 0.1},
  labs={"ANA": (3.5, "add"), "C3": (-0.5, "add"), "C4": (-0.2, "add"),
        "ESR": (35.0, "add"), "U_PRO": (0.7, "add"), "PLT": (-50.0, "add")},
  sx=["面部蝶形红斑", "关节痛", "脱发", "口腔溃疡", "光过敏", "乏力"], dur=None,
  fever=0.3, pain=0.45, inflam=0.4, treat=["羟氯喹", "泼尼松"])
D("RH-SJOREN", "干燥综合征", "rheum", base=0.0002,
  risk={"sex": 1.4}, org={"eye": 0.25, "gut": 0.10, "kidney": 0.1},
  labs={"ANA": (2.0, "add"), "IgG": (4.0, "add"), "ESR": (25.0, "add")},
  sx=["眼干无泪", "口干需饮水", "腮腺肿大", "龋齿增多"], dur=None,
  treat=["人工泪液", "羟氯喹"])
D("RH-SCLERODERMA", "系统性硬化症", "rheum", base=0.00005,
  org={"skin": 0.35, "lungs": 0.30, "gut": 0.20, "kidney": 0.2},
  labs={"ANA": (2.5, "add")},
  sx=["手指遇冷变白变紫", "皮肤变硬", "吞咽困难", "气短"], dur=None, rare=True)
D("RH-AS", "强直性脊柱炎", "rheum", base=0.0003,
  risk={"sex": 1.0}, org={"joint": 0.30, "bone": 0.25},
  labs={"ESR": (28.0, "add"), "CRP": (25.0, "add")},
  sx=["夜间腰背僵痛", "晨起明显", "活动后减轻", "胸廓扩张受限"], dur=None,
  pain=0.55, inflam=0.35, treat=["塞来昔布", "柳氮磺吡啶"])
D("RH-PSA", "银屑病关节炎", "rheum", base=0.0001,
  org={"joint": 0.30, "skin": 0.25},
  labs={"ESR": (22.0, "add"), "CRP": (20.0, "add")},
  sx=["指趾肿如香肠", "甲板点状凹陷", "关节痛"], dur=None, pain=0.5)
D("RH-GPA", "肉芽肿性多血管炎", "rheum", base=0.000015,
  org={"kidney": 0.45, "lungs": 0.35, "nerve": 0.2},
  labs={"ANCA": (3.0, "add"), "CREA": (80.0, "add"), "CRP": (40.0, "add")},
  sx=["鼻塞血性分泌物", "咳嗽伴痰中带血", "肾功能下降"], dur=None, rare=True,
  mortal=0.004, treat=["环磷酰胺", "泼尼松"])
D("RH-MPA", "显微镜下多血管炎", "rheum", base=0.00001,
  org={"kidney": 0.50, "lungs": 0.35},
  labs={"ANCA": (3.2, "add"), "CREA": (100.0, "add")},
  sx=["痰中带血", "快速进展的肾功能不全", "紫癜"], dur=None, rare=True, mortal=0.005)
D("RH-PAN", "结节性多动脉炎", "rheum", base=0.000008,
  org={"nerve": 0.30, "kidney": 0.30, "skin": 0.2},
  sx=["多发性单神经炎", "皮下结节", "高血压"], dur=None, rare=True)
D("RH-TAKAYASU", "大动脉炎", "rheum", base=0.000008,
  risk={"sex": 0.8}, org={"vessels": 0.35},
  labs={"ESR": (40.0, "add")},
  sx=["无脉症", "双上肢血压差", "活动后上肢乏力"], dur=None, rare=True)
D("RH-GCA", "巨细胞动脉炎", "rheum", base=0.000012,
  risk={"age": 1.6}, org={"eye": 0.35, "brain": 0.15},
  labs={"ESR": (55.0, "add"), "CRP": (40.0, "add")},
  sx=["新发颞部头痛", "咀嚼停顿", "视力模糊"], dur=None, rare=True,
  treat=["泼尼松"])
D("RH-PMR", "风湿性多肌痛", "rheum", base=0.00002,
  risk={"age": 1.6}, org={"muscle": 0.25},
  labs={"ESR": (50.0, "add")},
  sx=["肩髋带肌肉晨僵疼痛", "起床困难"], dur=None, pain=0.55, rare=True,
  treat=["泼尼松"])
D("RH-DM", "皮肌炎", "rheum", base=0.000015,
  org={"muscle": 0.40, "skin": 0.2, "lungs": 0.2},
  labs={"CK": (900.0, "add"), "LDH": (150.0, "add"), "ANA": (1.5, "add")},
  sx=["对称性近端肌无力", "眶周紫红色皮疹", "吞咽困难"], dur=None,
  pain=0.4, rare=True, treat=["泼尼松"])
D("RH-BEHcet", "白塞病", "rheum", base=0.00003,
  org={"skin": 0.20, "eye": 0.25, "joint": 0.15},
  labs={"ESR": (25.0, "add"), "CRP": (20.0, "add")},
  sx=["反复口腔溃疡", "皮肤脓疱样皮损", "葡萄膜炎", "针刺反应阳性"], dur=None,
  pain=0.4, rare=True)
D("RH-IGAV", "IgA 血管炎", "rheum", base=0.00006,
  org={"skin": 0.20, "kidney": 0.20, "gut": 0.15, "joint": 0.15},
  labs={"U_BLD": (0.4, "add")},
  sx=["双下肢可触性紫癜", "腹痛", "关节痛", "血尿"], acute=True, dur=600.0,
  pain=0.45, rare=True)
D("RH-APS", "抗磷脂综合征", "rheum", base=0.00002,
  org={"coag": 0.35}, labs={"APTT": (10.0, "add"), "PLT": (-40.0, "add")},
  sx=["反复血栓", "习惯性流产", "网状青斑"], dur=None, rare=True)
D("RH-CVID", "普通变异型免疫缺陷", "rheum", base=0.00001,
  org={"immune": 0.55},
  labs={"IgG": (-6.0, "add"), "IgA": (-0.6, "add"), "IgM": (-0.3, "add")},
  sx=["反复鼻窦肺部感染", "慢性腹泻"], dur=None, rare=True)
D("RH-ALLERGY", "过敏性鼻炎", "rheum", base=0.006,
  risk={"allergen": 1.8}, org={"airway": 0.10},
  labs={"IgE": (200.0, "add"), "EO_p": (3.5, "add")},
  sx=["晨起连续打喷嚏", "清水涕", "鼻痒眼痒"], dur=None, treat=["氯雷他定",
                                                                "布地奈德鼻喷"])
D("RH-URTICARIA", "荨麻疹", "derm", base=0.002,
  risk={"allergen": 1.2, "stress": 0.6}, org={"skin": 0.18},
  sx=["风团", "剧烈瘙痒", "此起彼伏"], acute=True, dur=72.0, pain=0.25,
  treat=["西替利嗪"])
D("RH-ANAPHYLAXIS", "过敏性休克", "rheum", base=0.00002,
  risk={"allergen": 2.0, "IgE": 1.5},
  org={"vessels": 0.45, "airway": 0.45, "heart": 0.2},
  labs={"SBP": (-45.0, "add"), "HR": (40.0, "add"), "SpO2": (-8.0, "add")},
  sx=["接触后数分钟喉紧", "全身风团", "血压骤降", "意识丧失"], acute=True,
  dur=None, mortal=0.08, rare=True, treat=["肾上腺素", "地塞米松"])
D("RH-MASTO", "肥大细胞增多症", "rheum", base=0.000006,
  org={"skin": 0.20, "gut": 0.15},
  sx=["皮肤划痕症", "阵发潮红", "腹泻", "骨痛"], dur=None, rare=True)
D("RH-HAE", "遗传性血管性水肿", "rheum", base=0.000004,
  org={"airway": 0.40, "skin": 0.2},
  sx=["反复无痛性水肿", "喉头水肿", "腹痛"], dur=None, rare=True, mortal=0.002)

# ======================================================================
# 皮肤
# ======================================================================
D("DR-ECZEMA", "特应性皮炎", "derm", base=0.003,
  risk={"allergen": 1.3, "humidity": 1.0}, org={"skin": 0.20},
  labs={"IgE": (150.0, "add"), "EO_p": (2.5, "add")},
  sx=["肘窝腘窝对称性瘙痒", "皮肤干燥", "抓痕"], dur=None, pain=0.3,
  treat=["糠酸莫米松", "西替利嗪"])
D("DR-PSORIASIS", "银屑病", "derm", base=0.0008,
  risk={"stress": 1.2, "alcohol": 0.7, "smoking": 0.6}, org={"skin": 0.30,
                                                             "joint": 0.15},
  labs={"CRP": (12.0, "add")},
  sx=["肘膝伸侧覆银白色鳞屑的红斑", "刮除见点状出血", "指甲凹陷"], dur=None,
  pain=0.3, inflam=0.15)
D("DR-ACNE", "痤疮", "derm", base=0.004, risk={"sugar": 0.8, "satfat": 0.5},
  org={"skin": 0.10}, sx=["面部丘疹脓疱", "粉刺", "结节"], dur=None, pain=0.25)
D("DR-ROSACEA", "玫瑰痤疮", "derm", base=0.0012, org={"skin": 0.10},
  sx=["面颊阵发潮红", "灼热", "丘疹"], dur=None, pain=0.2)
D("DR-CONTACT", "接触性皮炎", "derm", base=0.0018, risk={"allergen": 1.4},
  org={"skin": 0.15}, sx=["接触部位边界清楚的红斑水疱", "瘙痒灼痛"],
  acute=True, dur=150.0, pain=0.35)
D("DR-TINEA", "体癣", "derm", base=0.0015, risk={"humidity": 1.2, "hygiene": 0.6},
  org={"skin": 0.10}, sx=["环形红斑边缘脱屑", "瘙痒"], dur=600.0,
  treat=["特比萘芬"])
D("DR-MELANOMA", "黑色素瘤", "derm", base=0.00002,
  risk={"sun": 1.5, "skin": 0.8}, org={"skin": 0.30, "liver": 0.2},
  labs={"LDH": (90.0, "add")},
  sx=["色素痣近期变大变色", "边缘不规则", "破溃出血"], dur=None, rare=True,
  mortal=0.003)
D("DR-BCC", "基底细胞癌", "derm", base=0.00006,
  risk={"sun": 1.6, "age": 1.2}, org={"skin": 0.20},
  sx=["面部珍珠样结节", "中央溃疡", "缓慢增大"], dur=None, rare=True)
D("DR-SCC", "鳞状细胞癌（皮肤）", "derm", base=0.00003,
  risk={"sun": 1.8, "smoking": 0.8}, org={"skin": 0.30},
  sx=["角化性斑块", "结痂不愈", "触之易出血"], dur=None, rare=True,
  mortal=0.001)
D("DR-PRESSURE", "压疮", "derm", base=0.0002,
  risk={"sedentary": 1.6, "age": 1.0}, org={"skin": 0.30},
  sx=["骶尾部皮肤发红破溃", "疼痛"], dur=None, pain=0.6)
D("DR-DECUBITUS-INF", "压疮感染", "derm", base=0.00005,
  risk={"sedentary": 1.5}, org={"skin": 0.35, "coag": 0.05},
  labs={"CRP": (55.0, "add"), "WBC": (3.0, "add")},
  sx=["创面脓性分泌物", "异味", "发热"], dur=None, fever=0.5, pain=0.6)

# ======================================================================
# 运动系统
# ======================================================================
D("MS-OA", "骨关节炎", "msk", base=0.0025,
  risk={"age": 1.5, "bmi": 1.2, "activity": 0.5}, org={"joint": 0.35},
  sx=["膝或髋负重时痛", "晨僵少于半小时", "关节摩擦感"], dur=None, pain=0.55,
  treat=["塞来昔布", "氨基葡萄糖"])
D("MS-FRACTURE", "骨折", "msk", base=0.0003,
  risk={"bone": 1.6, "activity": 0.8, "age": 0.8}, org={"bone": 0.30,
                                                        "muscle": 0.15},
  labs={"ALP": (30.0, "add")},
  sx=["外伤后局部剧痛", "畸形", "不能负重"], acute=True, dur=1200.0, pain=0.9)
D("MS-OSTEO-FRAG", "脆性骨折", "msk", base=0.00015,
  risk={"bone": 2.0, "age": 1.4}, org={"bone": 0.35, "muscle": 0.2},
  sx=["轻微跌倒即骨折", "腰背痛加重", "身高变矮"], acute=True, dur=1500.0,
  pain=0.8)
D("MS-TENDINITIS", "肌腱炎", "msk", base=0.0015,
  risk={"activity": 1.2}, org={"muscle": 0.08},
  sx=["局部活动时痛", "压痛", "抗阻痛"], dur=None, pain=0.45)
D("MS-ROTATOR", "肩袖损伤", "msk", base=0.0008,
  risk={"activity": 1.2, "age": 0.6}, org={"muscle": 0.12},
  sx=["举手过顶时痛", "夜间压患侧痛醒", "外展无力"], dur=None, pain=0.55)
D("MS-PLANTAR", "足底筋膜炎", "msk", base=0.0012,
  risk={"sedentary": 0.8, "bmi": 0.7}, org={},
  sx=["晨起第一步足跟剧痛", "走开后减轻"], dur=None, pain=0.55)
D("MS-FIBROMYALGIA", "纤维肌痛", "msk", base=0.0008,
  risk={"stress": 1.4, "sex": 0.8, "sleep_debt": 1.0}, org={"muscle": 0.15},
  sx=["全身弥漫性疼痛", "多处压痛点", "睡醒不解乏", "脑雾"], dur=None,
  pain=0.6, treat=["度洛西汀", "普瑞巴林"])
D("MS-RHABDO", "横纹肌溶解", "msk", base=0.00008,
  risk={"activity": 1.5, "water": 0.8}, org={"muscle": 0.35, "kidney": 0.30},
  labs={"CK": (8000.0, "add"), "MYO": (400.0, "add"), "CREA": (35.0, "add"),
        "K": (0.6, "add")},
  sx=["剧烈运动后肌肉剧痛", "酱油色尿", "无力"], acute=True, dur=250.0,
  pain=0.8, mortal=0.005)
D("MS-SARCOPENIA", "肌少症", "msk", base=0.0008,
  risk={"age": 1.6, "activity": 1.2, "protein": 1.0},
  org={"muscle": 0.40}, sx=["握力下降", "走路变慢", "易跌倒"], dur=None,
  pain=0.2)
D("MS-DISC", "椎间盘退变", "msk", base=0.0018,
  risk={"sedentary": 1.2, "age": 1.0}, org={"joint": 0.15},
  sx=["久坐后腰痛", "弯腰受限"], dur=None, pain=0.45)
D("MS-MARFAN", "马方综合征", "msk", base=0.000005,
  org={"vessels": 0.35, "eye": 0.25, "bone": 0.2, "heart": 0.2},
  sx=["身材瘦高", "细长指", "晶状体脱位", "主动脉扩张"], dur=None, rare=True)
D("MS-EDS", "Ehlers-Danlos 综合征", "msk", base=0.000006,
  org={"joint": 0.35, "skin": 0.25, "vessels": 0.2},
  sx=["关节过度活动", "皮肤过度伸展", "反复脱位"], dur=None, rare=True)
D("MS-NF1", "神经纤维瘤病 1 型", "neuro", base=0.000008,
  org={"skin": 0.25, "nerve": 0.25, "eye": 0.15},
  sx=["咖啡牛奶斑", "多发神经纤维瘤", "腋窝雀斑"], dur=None, rare=True)
D("MS-NF2", "神经纤维瘤病 2 型", "neuro", base=0.000003,
  org={"ear": 0.35, "nerve": 0.3}, sx=["双侧听神经瘤", "听力下降", "耳鸣"],
  dur=None, rare=True)
D("MS-TSC", "结节性硬化症", "neuro", base=0.000004,
  org={"brain": 0.35, "kidney": 0.25, "skin": 0.2},
  sx=["面部血管纤维瘤", "癫痫", "智力受损"], dur=None, rare=True)

# ======================================================================
# 眼与耳鼻喉
# ======================================================================
D("EY-CATARACT", "白内障", "eye", base=0.0008,
  risk={"age": 1.6, "sugar": 0.8, "sun": 0.6}, org={"eye": 0.35},
  sx=["视物模糊如隔雾", "眩光", "夜间视力差"], dur=None)
D("EY-GLAUCOMA", "青光眼", "eye", base=0.0003,
  risk={"age": 1.2, "SBP": 0.6}, org={"eye": 0.45},
  sx=["视野逐渐缩小", "眼胀", "看灯有虹视"], dur=None, pain=0.3)
D("EY-RETINOPATHY", "糖尿病视网膜病变", "eye", base=0.0002,
  risk={"sugar": 1.6}, org={"eye": 0.40},
  sx=["视力下降", "眼前黑影飘动", "夜间看不清"], dur=None)
D("EY-AMD", "年龄相关性黄斑变性", "eye", base=0.0002,
  risk={"age": 1.8, "smoking": 1.0}, org={"eye": 0.40},
  sx=["中央视野暗点", "看直线变形", "阅读困难"], dur=None, rare=True)
D("EY-CONJUNCT", "结膜炎", "eye", base=0.002, risk={"allergen": 1.2,
                                                    "hygiene": 0.6},
  org={"eye": 0.10}, sx=["眼红", "分泌物增多", "异物感"], acute=True, dur=100.0,
  pain=0.3, treat=["人工泪液", "左氧氟沙星滴眼液"])
D("EY-DRY", "干眼症", "eye", base=0.003,
  risk={"sedentary": 1.2, "humidity": 0.8}, org={"eye": 0.15},
  sx=["眼干涩", "沙砾感", "视疲劳"], dur=None, pain=0.25, treat=["人工泪液"])
D("EY-RETINAL-DET", "视网膜脱离", "eye", base=0.00002,
  org={"eye": 0.55}, sx=["突发闪光感", "大量飞蚊", "视野幕帘样遮挡"],
  acute=True, dur=None, rare=True)
D("EN-CATARRH", "分泌性中耳炎", "ent", base=0.001, org={"ear": 0.15},
  sx=["耳闷", "听力下降", "自听过响"], dur=None)
D("EN-PRESBYCUSIS", "老年性耳聋", "ent", base=0.0008,
  risk={"age": 1.8, "noise": 1.0}, org={"ear": 0.35},
  sx=["高频听不清", "嘈杂环境听懂困难", "耳鸣"], dur=None)
D("EN-NIHL", "噪声性听力损失", "ent", base=0.0004,
  risk={"noise": 2.0}, org={"ear": 0.35},
  sx=["耳鸣", "听力下降"], dur=None, rare=True)
D("EN-TINNITUS", "耳鸣", "ent", base=0.0015,
  risk={"noise": 1.2, "stress": 0.8}, org={"ear": 0.10},
  sx=["持续蝉鸣声", "夜间明显", "影响入睡"], dur=None, pain=0.2)
D("EN-VERTIGO", "前庭性眩晕", "ent", base=0.0008, org={"ear": 0.15},
  sx=["旋转性眩晕", "恶心", "走路不稳"], acute=True, dur=120.0, pain=0.2)

# ======================================================================
# 生殖
# ======================================================================
D("RP-ENDOMETRIOSIS", "子宫内膜异位症", "repro", base=0.0005,
  org={"gonad": 0.25}, sx=["进行性痛经", "盆腔坠痛", "不孕"], dur=None, pain=0.6,
  sex="f")
D("RP-FIBROID", "子宫肌瘤", "repro", base=0.0015, org={"gonad": 0.15},
  labs={"HGB": (-10.0, "add")},
  sx=["经量增多", "经期延长", "下腹坠胀"], dur=None, pain=0.3, sex="f")
D("RP-MENOPAUSE", "围绝经期综合征", "repro", base=0.002,
  risk={"age": 1.8}, org={"gonad": 0.35, "bone": 0.15},
  labs={"E2": (-200.0, "add"), "FSH": (40.0, "add")},
  sx=["潮热盗汗", "失眠", "情绪波动", "黏膜干燥"], dur=None, sex="f")
D("RP-INFERTILITY", "不孕症", "repro", base=0.0004, org={"gonad": 0.25},
  sx=["规律性生活一年未孕"], dur=None, sex="f", rare=False)

# ======================================================================
# 罕见遗传与代谢病
# ======================================================================
D("GD-WILSON", "肝豆状核变性", "gi", base=0.000004,
  org={"liver": 0.45, "brain": 0.30, "eye": 0.2},
  labs={"ALT": (60.0, "add"), "TBIL": (15.0, "add")},
  sx=["手抖", "构音不清", "角膜色素环", "肝功能异常"], dur=None, rare=True,
  age=(5.0, 45.0))
D("GD-HEMOCHROM", "血色病", "gi", base=0.000006,
  org={"liver": 0.40, "pancreas_endo": 0.30, "heart": 0.25, "joint": 0.2},
  labs={"FERR": (900.0, "add"), "TSAT": (35.0, "add"), "ALT": (40.0, "add")},
  sx=["皮肤青铜色", "关节痛", "乏力", "精力与兴趣下降"], dur=None, rare=True)
D("GD-GAUCHER", "戈谢病", "heme", base=0.000002,
  org={"spleen": 0.55, "marrow": 0.35, "bone": 0.3, "liver": 0.2},
  labs={"HGB": (-25.0, "add"), "PLT": (-70.0, "add")},
  sx=["巨脾", "骨痛", "易瘀伤"], dur=None, rare=True)
D("GD-FABRY", "法布里病", "endo", base=0.000002,
  org={"kidney": 0.40, "heart": 0.35, "nerve": 0.25, "skin": 0.15},
  labs={"U_PRO": (0.5, "add"), "CREA": (40.0, "add")},
  sx=["肢端烧灼样痛", "少汗", "血管角质瘤", "蛋白尿"], dur=None, rare=True)
D("GD-POMPE", "糖原累积病 II 型（Pompe）", "msk", base=0.000001,
  org={"muscle": 0.60, "heart": 0.30, "lungs": 0.2},
  labs={"CK": (600.0, "add")},
  sx=["进行性近端肌无力", "呼吸费力", "心脏扩大"], dur=None, rare=True)
D("GD-PKU", "苯丙酮尿症", "endo", base=0.000003,
  org={"brain": 0.45}, labs={"PHE": (900.0, "add")},
  sx=["智力发育迟缓", "鼠尿味", "皮肤白皙"], dur=None, rare=True, age=(0.0, 20.0))
D("GD-HOMOCYST", "同型半胱氨酸尿症", "cardio", base=0.000002,
  org={"vessels": 0.40, "eye": 0.25, "brain": 0.2},
  labs={"HCY": (60.0, "add")},
  sx=["晶状体脱位", "血栓", "智力下降"], dur=None, rare=True)
D("GD-PORPHYRIA", "卟啉病", "gi", base=0.000002,
  org={"nerve": 0.30, "liver": 0.15, "skin": 0.2},
  sx=["发作性剧烈腹痛", "深色尿", "光敏性皮损", "肢体麻木"], dur=None,
  pain=0.8, rare=True)
D("GD-AMYLOID", "淀粉样变性", "rheum", base=0.000008,
  org={"kidney": 0.45, "heart": 0.40, "nerve": 0.25, "gut": 0.2},
  labs={"U_PRO": (1.2, "add"), "NTproBNP": (500.0, "add")},
  sx=["乏力", "水肿", "舌体肥大", "体位性低血压"], dur=None, rare=True)
D("GD-PNH", "阵发性睡眠性血红蛋白尿", "heme", base=0.000003,
  org={"marrow": 0.35, "coag": 0.25, "kidney": 0.15},
  labs={"HGB": (-30.0, "add"), "LDH": (400.0, "add"), "TBIL": (20.0, "add")},
  sx=["晨起酱油色尿", "乏力", "血栓"], dur=None, rare=True)
D("GD-CARDIAC-AMYLOID", "转甲状腺素蛋白心肌淀粉样变", "cardio", base=0.000004,
  org={"heart": 0.45, "nerve": 0.25},
  labs={"NTproBNP": (700.0, "add")},
  sx=["气短", "下肢水肿", "腕管综合征史"], dur=None, rare=True)
D("GD-HAE-2", "遗传性血管性水肿（补体）", "rheum", base=0.000002,
  org={"airway": 0.35}, labs={"C4": (-0.25, "add")},
  sx=["反复喉头水肿", "腹痛"], dur=None, rare=True)
D("GD-ALPHA1", "α1-抗胰蛋白酶缺乏（肝型）", "gi", base=0.000003,
  org={"liver": 0.40, "lungs": 0.25},
  sx=["新生儿黄疸史", "肝功能异常", "早发肺气肿"], dur=None, rare=True)

# ======================================================================
# 肿瘤（非血液、非已列专科）
# ======================================================================
D("ON-LUNG", "肺癌", "resp", base=0.00009,
  risk={"smoking": 2.2, "pm25": 0.8, "age": 1.2}, org={"lungs": 0.55,
                                                       "brain": 0.15, "bone": 0.15},
  labs={"LDH": (80.0, "add"), "ESR": (30.0, "add"), "Ca": (0.20, "add")},
  sx=["持续刺激性干咳", "痰中带血", "胸痛", "声音嘶哑", "体重下降"], dur=None,
  pain=0.4, rare=True, mortal=0.006)
D("ON-GASTRIC", "胃癌", "gi", base=0.00006,
  risk={"salt": 1.4, "smoking": 1.0, "age": 1.2}, org={"gut": 0.45, "marrow": 0.15},
  labs={"HGB": (-25.0, "add"), "ALB": (-6.0, "add")},
  sx=["上腹持续隐痛", "早饱", "体重下降", "黑便"], dur=None, pain=0.5,
  rare=True, mortal=0.005)
D("ON-ESOPHAGEAL", "食管癌", "gi", base=0.00003,
  risk={"alcohol": 1.5, "smoking": 1.2, "salt": 1.0}, org={"gut": 0.45},
  labs={"ALB": (-5.0, "add")},
  sx=["进行性吞咽困难", "胸骨后痛", "体重下降"], dur=None, pain=0.55, rare=True,
  mortal=0.005)
D("ON-COLORECTAL", "结直肠癌", "gi", base=0.00008,
  risk={"satfat": 1.3, "fiber": 1.0, "age": 1.3, "alcohol": 0.8},
  org={"gut": 0.40, "marrow": 0.20, "liver": 0.1},
  labs={"HGB": (-22.0, "add"), "FERR": (-15.0, "add")},
  sx=["排便习惯改变", "便血", "里急后重", "体重下降"], dur=None, pain=0.4,
  rare=True, mortal=0.004)
D("ON-HEPATOCELL", "肝细胞癌", "gi", base=0.00003,
  risk={"alcohol": 1.8, "pathogen": 1.2}, org={"liver": 0.55},
  labs={"AFP": (600.0, "add"), "ALT": (60.0, "add"), "TBIL": (25.0, "add")},
  sx=["右上腹持续痛", "腹胀", "黄疸", "消瘦"], dur=None, pain=0.55, rare=True,
  mortal=0.006)
D("ON-PANCREATIC", "胰腺癌", "gi", base=0.00003,
  risk={"smoking": 1.3, "bmi": 0.8, "age": 1.2}, org={"pancreas_exo": 0.50,
                                                      "liver": 0.15},
  labs={"CA199": (800.0, "add"), "TBIL": (40.0, "add"), "ALP": (120.0, "add")},
  sx=["上腹持续痛向背放射", "无痛性黄疸", "体重骤降", "新发糖尿病"], dur=None,
  pain=0.7, rare=True, mortal=0.010)
D("ON-BREAST", "乳腺癌", "repro", base=0.0001,
  risk={"sex": 2.0, "age": 1.2, "alcohol": 0.8}, org={"skin": 0.2, "bone": 0.2,
                                                      "lungs": 0.15},
  labs={"ALP": (40.0, "add")},
  sx=["无痛性乳房肿块", "皮肤橘皮样", "乳头溢液"], dur=None, rare=True,
  sex="f", mortal=0.0015)
D("ON-OVARIAN", "卵巢癌", "repro", base=0.00004,
  risk={"sex": 1.0, "age": 1.2}, org={"gonad": 0.4, "gut": 0.2},
  labs={"CA125": (600.0, "add")},
  sx=["腹胀", "腹围增大", "盆腔压迫感", "消瘦"], dur=None, pain=0.4, rare=True,
  sex="f", mortal=0.005)
D("ON-CERVICAL", "宫颈癌", "repro", base=0.00005,
  risk={"pathogen": 1.6}, org={"gonad": 0.35},
  sx=["接触后少量出血", "异常出血", "盆腔痛"], dur=None, rare=True, sex="f",
  mortal=0.003)
D("ON-ENDOMETRIAL", "子宫内膜癌", "repro", base=0.00004,
  risk={"bmi": 1.4, "age": 1.2}, org={"gonad": 0.3},
  sx=["绝经后出血", "经量增多"], dur=None, rare=True, sex="f", mortal=0.002)
D("ON-ESOPH-GASTRIC", "食管胃交界腺癌", "gi", base=0.00002,
  org={"gut": 0.45}, sx=["吞咽不适", "反酸加重", "体重下降"], dur=None,
  rare=True, mortal=0.004)
D("ON-BRAIN", "胶质瘤", "neuro", base=0.00002,
  org={"brain": 0.60}, sx=["进行性头痛", "癫痫", "肢体无力", "视野缺损"],
  dur=None, pain=0.45, rare=True, mortal=0.005)
D("ON-THYROID-MED", "甲状腺髓样癌", "endo", base=0.000008,
  org={"thyroid": 0.35}, labs={"CALC": (1200.0, "add")},
  sx=["颈部硬块", "腹泻", "面部潮红"], dur=None, rare=True, mortal=0.001)
D("ON-CARCINOID", "类癌综合征", "endo", base=0.000005,
  org={"liver": 0.25, "heart": 0.2}, labs={"CGA": (400.0, "add")},
  sx=["阵发性面部潮红", "水样腹泻", "哮喘样发作", "右心瓣膜病变"], dur=None,
  rare=True)
D("ON-MESOTHELIOMA", "间皮瘤", "resp", base=0.000004,
  risk={"pm25": 2.0}, org={"lungs": 0.50, "gut": 0.15},
  sx=["胸膜性胸痛", "气短", "胸腔积液"], dur=None, pain=0.6, rare=True,
  mortal=0.006)
D("ON-NASOPHARYNGEAL", "鼻咽癌", "ent", base=0.00003,
  risk={"pathogen": 1.2}, org={"ear": 0.2, "nerve": 0.15},
  sx=["回吸性血涕", "单侧鼻塞", "颈部肿块", "耳闷"], dur=None, rare=True,
  mortal=0.002)
D("ON-LEUKEMIA-UNSPEC", "白血病（未定型）", "heme", base=0.00001,
  org={"marrow": 0.6}, labs={"WBC": (20.0, "add"), "HGB": (-30.0, "add")},
  sx=["发热", "贫血", "出血"], dur=None, rare=True, mortal=0.01)


# 需要额外化验项目支持的特殊指标（基表未列，供参考实现补齐）
EXTRA_LABS: Dict[str, Tuple[str, str, float, float]] = {
    "AMY":   ("淀粉酶", "U/L", 30.0, 110.0),
    "LIP":   ("脂肪酶", "U/L", 23.0, 300.0),
    "AFP":   ("甲胎蛋白", "ng/mL", 0.0, 7.0),
    "CA125": ("糖类抗原 125", "U/mL", 0.0, 35.0),
    "CA199": ("糖类抗原 19-9", "U/mL", 0.0, 37.0),
    "CALC":  ("降钙素", "pg/mL", 0.0, 10.0),
    "CGA":   ("嗜铬粒蛋白 A", "ng/mL", 0.0, 100.0),
    "PHE":   ("苯丙氨酸", "µmol/L", 35.0, 120.0),
    "HCY":   ("同型半胱氨酸", "µmol/L", 5.0, 15.0),
    "LH":    ("促黄体生成素", "IU/L", 1.0, 12.0),
    "FSH":   ("促卵泡激素", "IU/L", 1.0, 12.0),
    "ACE":   ("血管紧张素转换酶", "U/L", 12.0, 68.0),
    "NSAID": ("（占位：非甾体抗炎药暴露）", "", 0.0, 1.0),
}


def resolve(name: str) -> Optional[str]:
    """按中文名或 ICD 码查疾病。"""
    if not name:
        return None
    if name in DISEASES:
        return name
    for k, v in DISEASES.items():
        if v["zh"] == name:
            return k
    return None


def by_system(sys_: str) -> List[str]:
    return [k for k, v in DISEASES.items() if v["sys"] == sys_]


def all_zh() -> List[str]:
    return [v["zh"] for v in DISEASES.values()]


def stats() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in DISEASES.values():
        out[v["sys"]] = out.get(v["sys"], 0) + 1
    return out
