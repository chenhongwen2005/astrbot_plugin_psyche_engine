# 身心状态引擎

AstrBot 插件，包名 `astrbot_plugin_psyche_engine`，版本 1.9.0。纯标准库，无第三方依赖。

为虚构角色维护一套可复算的精神与身体状态。每轮对话重算一次，结果以高优先级写进模型上下文，约束语气、动作与认知偏差。

详细设计见 [README.full.md](README.full.md)。

## 规模

| 层 | 内容 |
|---|---|
| 精神 | 21 生化 / 23 电生理 / 14 特质 / 163 症状 / 72 诊断原型 / 37 预设 / 12 量表 263 条 / 18 药 + ECT / 20 副作用 |
| 情感 | 13 分量 / 3 反应风格 / 心境基线 / 按小时衰减 |
| 记忆 | 4 层（瞬时·短期·较长期·长期）/ 默认 240 条 / 2-gram + FTS5 检索 |
| 身体 | 29 器官 / 15 系统 / 387 疾病 / 204 药 156 类 / 138 检验 19 组 / 23 生活维度 / 7 环境项 |
| 时间 | 真实北京时间，固定 +8，真日历，整点推进 |
| 文件 | `psyche/` 20 个 / `physio/` 22 个 |

## 安装

插件市场：WebUI「插件」→「插件市场」，搜索 **身心状态引擎**。

手动：

```bash
cp -r astrbot_plugin_psyche_engine /path/to/AstrBot/data/plugins/
# 重启 AstrBot，或在 WebUI 插件页点「重载」
```

安装后发 `/心理` 能看到状态卡，即注入链路正常。

## 指令

主指令 `/心理`，别名 `/身心` `/生命` `/psyche` `/精神`。

| 指令 | 作用 |
|---|---|
| `/心理` | 状态卡：诊断、生化条、环路、TOP8 症状、身体摘要 |
| `/心理 诊断` | ICD-11 诊断、鉴别与表演要求 |
| `/心理 生化` | 21 项生化与 23 项电生理明细 |
| `/心理 情感` | 情绪底色：主调、前列分量、效价 / 唤醒 / 支配、心境基线、行为落点 |
| `/心理 记忆` | 最近 15 条：轮次、强度、巩固度、当时的情绪 |
| `/心理 记忆 <关键词>` | 关键词检索（检索会加强命中条目） |
| `/心理 记忆 <层名>` | 按层查看：瞬时 / 短期 / 较长期 / 长期 |
| `/心理 记忆 层 <层名>` | 同上，显式写法 |
| `/心理 记忆 清空 [层名]` | 清空记忆，可只清一层；状态与身体不受影响 |
| `/心理 设定情绪 <分量> <值>` | 手工设定情绪分量，`mood` 取 −1~1，其余 0~1 |
| `/心理 时间线` | 诊断、事件、用药历史 |
| `/心理 预设 <名称>` | 切换初始病理，37 个预设 |
| `/心理 事件 <类型>` | 注入生活事件，10 种，见下 |
| `/心理 用药 <药名> [剂量]` | 精神侧给药，延迟起效 |
| `/心理 副作用` | 在服药物与副作用：已现 / 未现、强度、起效轮数 |
| `/心理 停药 <药名>` | 精神侧停药，可能反跳 |
| `/心理 快进 <轮数>` | 空转演化 N 轮，不进对话 |
| `/心理 量表 [名称…]` | 角色填量表并校准，默认 SCL-90 |
| `/心理 重置` | 回到预设初始状态 |
| `/心理 导出` | 导出状态 JSON |
| `/心理 生理` | 一句话身体状况，与注入块同段 |
| `/心理 体检` | 完整体检 19 组 138 项，分 6 条发送 |
| `/心理 体检 <组名>` | 单组，见下表 |
| `/心理 体检 异常` | 仅异常项 |
| `/心理 生活` / `/心理 日子` | 作息饮食活动环境 / 身体日志 |
| `/心理 服药 <药名> [剂量]` | 身体侧给药，204 种，与精神侧分开 |
| `/心理 找药 <关键词>` | 按药名或类别检索 |
| `/心理 停服 <药名>` | 停止身体侧用药 |
| `/心理 推进 <小时>` | 仅推进身体时间，24 = 一天，上限一年 |
| `/心理 时差 <小时>` | 生物钟整体挪动 ±12 小时（跨时区 / 换班次），之后每天回 1 小时 |
| `/心理 设置 <维度> <值>` | 直接设定生活、环境或体征维度；设定后被钉住，`auto` 交回自动推算 |

模型侧另有工具 `psyche_self_report` 供角色内省。自知力受损时自述会失真，这本身是症状。

**生活事件**（`/心理 事件`）：失业 失恋 被霸凌 升职 丧亲 创伤 表扬 陪伴 失眠 戒断。

**体检分组**（`/心理 体检`）：生命体征 血常规 炎症 肝功能 肾功能 电解质 糖代谢 血脂 甲状腺 内分泌 心肌 凝血 血气 尿液 免疫 营养 胰腺 肿瘤标志物 遗传代谢。共 19 组 138 项。

**可设定维度**（`/心理 设置`，共 40 项）：

| 组 | 键 |
|---|---|
| 生活 23 | `sleep_h` `sleep_debt` `sleep_qual` `kcal` `protein` `iron` `b12` `folate` `vitd` `water` `fiber` `salt` `sugar` `satfat` `activity` `fitness` `sedentary` `alcohol` `smoking` `caffeine` `hygiene` `sun` `stress` |
| 环境 7 | `temp_c` `humidity` `pm25` `pathogen` `allergen` `noise` `altitude` |
| 体征 10 | `HR` `SBP` `DBP` `RR` `SpO2` `TEMP` `WEIGHT` `BMI` `WAIST` `PAIN` |

`auto` 只对生活维度有效，交回作息、三餐、运动逻辑推算。

## 量表

| 名称 | 条数 | 名称 | 条数 |
|---|---|---|---|
| SCL-90 | 90 | PCL-5 | 20 |
| PANSS | 30 | DES-II | 28 |
| EDE-Q | 28 | MDQ | 13 |
| YMRS | 11 | AUDIT | 10 |
| Y-BOCS | 10 | PHQ-9 | 9 |
| GAD-7 | 7 | ISI | 7 |

共 12 份 263 条。

## 预设（37）

```
healthy                      prodromal                 schizophrenia_paranoid
schizophrenia_disorganized   delusional                catatonia
mdd_severe                   mdd_melancholic           dysthymia
mixed_anxiety_depression     bipolar_i_manic           bipolar_i_depressed
bipolar_ii                   cyclothymia               gad
panic                        social_anxiety            ocd
ptsd                         cptsd                     prolonged_grief
adjustment                   borderline                npd
aspd                         avoidant                  dependent
ocpd                         schizotypal               paranoid_pd
anorexia                     bulimia                   gambling
asd                          adhd                      insomnia
dissociative_identity
```

## 配置（32）

| 键 | 默认 | 说明 |
|---|---|---|
| `enabled` | true | 总开关 |
| `default_preset` | healthy | 新会话初始预设 |
| `scope` | session | `session` 每会话 / `user` 跨会话 / `global` 全局 |
| `inject_mode` | dynamic | `dynamic` 插到用户内容最前 / `system_prepend` / `system_append` |
| `authority_clause` | true | 常驻权威声明 |
| `max_block_chars` | 1800 | 注入块字符上限，低于 1000 会丢段 |
| `enable_circadian` | true | 昼夜节律（皮质醇、褪黑素、腺苷） |
| `stochastic` | true | 症状随机涨落 |
| `therapy_enabled` | true | 谈话治疗效应 |
| `chronic_turns` | 120 | 慢性化时间尺度 |
| `crisis_override` | true | 检出真实自伤风险时跳出角色 |
| `compliance_guard` | true | 回复偏离检测 |
| `commands_enabled` | true | 指令开关 |
| `debug` | false | 打印注入块 |
| `appraisal_timeout` | 12 | 话语评估超时，秒 |
| `scale_always_scl90` | true | 专项量表附带 SCL-90 |
| `scale_timeout` | 40 | 量表自评超时，秒 |
| `physio_enabled` | true | 启用身体模拟 |
| `clock_mode` | real | `real` 按真实北京时间 / `virtual` 每轮固定推进 |
| `physio_hours_per_turn` | 6 | 每轮虚拟小时，仅 `virtual` 生效 |
| `physio_sex` | m | 生理性别，影响参考区间与周期、妊娠、产后 |
| `physio_age` | 30 | 年龄，决定器官功能储备与老年病窗口 |
| `physio_preset` | healthy | 底子：healthy athlete sedentary obese smoker drinker insomniac burnout elderly frail chronically_ill |
| `physio_disease_onset` | true | 允许自发发病 |
| `physio_onset_scale` | 0.3 | 发病概率缩放，1.0 等于人群年发病率 |
| `physio_mortality` | false | 允许因病死亡 |
| `physio_couple` | true | 身体 ↔ 精神双向耦合 |
| `emotion_enabled` | true | 启用情感层 |
| `emotion_style` | balanced | `balanced` 常人 / `labile` 起伏大退得慢 / `stable` 钝感回落快 |
| `emotion_persistence` | 1.5 | 情绪驻留倍数，乘在分量半衰期上 |
| `memory_enabled` | true | 启用类脑记忆 |
| `memory_max` | 240 | 短期层上限，较长期为其两倍 |

## 文件结构

```
astrbot_plugin_psyche_engine/
├── main.py                 # 入口：注入、指令、工具、回复合规检测
├── metadata.yaml           # 市场元数据
├── _conf_schema.json       # 32 项配置
├── requirements.txt        # 空，纯标准库
├── LICENSE                 # MIT + 非医疗器械声明
├── demo.py                 # 无需 AstrBot 的链路演示
├── README.md               # 本文件
├── README.full.md          # 详细设计文档
├── tests/
│   ├── test_engine.py          # 21 组 数据完整性 / 动力学 / 诊断 / 量表
│   ├── test_physio.py          # 19 组 自洽 / 自限 / 蓄积 / 体型 / 合规
│   ├── test_mind.py            # 14 组 情绪回落 / 有界 / 检索 / 遗忘 / 存档
│   ├── test_clock.py           # 9 组 北京时间与整点判定
│   ├── test_memdb.py           # 10 组 建表 / 分层 / 检索 / 迁移
│   ├── test_life_functions.py  # 50 组 内感受 / 睡眠 / 外伤 / 衰老 / 体质 / 生殖
│   ├── test_longterm.py        # 17 组 一年长跑 / 慢性情绪 / 时差 / 体质漂移
│   ├── test_plugin_smoke.py    # 8 组 加载 / 注入 / 指令 / 元数据
│   └── _stub/astrbot/          # 最小 AstrBot stub
├── tools/
│   ├── verify_in_astrbot.py  # 真机验证：API、注入、落盘、上架要求
│   ├── stress_induce.py      # 173 条诱导话术逐条压测
│   ├── longitudinal.py       # 长程累积：多久致病、能否治愈
│   ├── day_demo.py           # 过一天：24 小时注入块逐小时摊开
│   ├── soak.py               # 长程浸泡：9 个场景、数年虚拟时间
│   └── repl.py               # 手动逐条测试台
├── psyche/
│   ├── const.py          # 21 生化 + 23 电生理 + 14 特质 + 163 症状
│   ├── criteria.py       # 72 个诊断原型 + CORE + 互斥
│   ├── presets.py        # 37 个病理预设 + 健康基线
│   ├── model.py          # 状态容器与派生特征
│   ├── compat.py         # physio 双模式导入适配
│   ├── appraisal.py      # 模型抽取 + 无模型兜底
│   ├── lexicons.py       # 危机判定词表
│   ├── keyword_map.py    # 关键词 → 症状增量
│   ├── dynamics.py       # 生化 / 环路 / 症状 / 负荷 / 地板 / 调定点
│   ├── emotion.py        # 13 分量情感、派生维度、心境基线
│   ├── memory.py         # 记忆封装：编码 / 检索 / 注入
│   ├── memdb.py          # SQLite 四层表、倒排索引、FTS5、晋升与遗忘
│   ├── clock.py          # 北京时间单一时间源
│   ├── diagnose.py       # 诊断与病程
│   ├── scales.py         # 12 份量表 263 条 + 计分 / 因子
│   ├── pharm.py          # 18 药 + ECT + 20 项副作用与归因
│   ├── narrative.py      # 注入块、量表锚点、状态卡、身体段、情绪段、记忆段
│   ├── engine.py         # 编排、事件、校准、合规、身体侧指令
│   └── store.py          # SQLite 持久化
└── physio/
    ├── const.py          # 29 器官 + 15 系统 + 138 检验 + 23 生活 + 7 环境
    ├── body.py           # 身体容器、年龄衰退、11 种底子预设
    ├── diseases.py       # 387 种疾病
    ├── drugs.py          # 204 种药
    ├── labs.py           # 器官→指标→疾病→药物→自洽修正
    ├── engine.py         # 逐小时推进、按天结算病程与发病
    ├── lifecycle.py      # 生殖总调度
    ├── cycle.py          # 月事：PMS、经期与排卵、失血债、无排卵
    ├── gestation.py      # 妊娠：按周症状、增重、并发症、分娩
    ├── postpartum.py     # 产后：恶露、伤口、泌乳、乳腺炎、抑郁、脱发
    ├── gonadal.py        # 性腺轴：活动水平、体毛、夜尿、功能减退
    ├── energy.py         # 精力预算
    ├── intero.py         # 内感受：饿、渴、尿意、便意、痒、心悸、眩晕、耳鸣、酸痛
    ├── sleep.py          # 整夜结构：就寝、潜伏、深睡、REM、夜醒
    ├── injury.py         # 外伤 25 种（16 轻症 + 9 中重度）：情境风险 + 单调愈合
    ├── aging.py          # 衰老：年龄推进、体能上限、老年病日程
    ├── substance.py      # 酒精 / 咖啡因 / 宿醉
    ├── traits.py         # 体质：seed 基线 + 按周漂移
    ├── rhythm.py         # 昼夜：体温 / 血压 / 心率（含时差与倒班偏移）
    ├── mind.py           # 情绪 → 身体：生理签名、饱和、衰减、慢性通路
    └── report.py         # 体检报告、分组、生活、日志、注入段
```

## 测试

```bash
python tests/test_engine.py          # 21 组
python tests/test_physio.py          # 19 组
python tests/test_mind.py            # 14 组
python tests/test_life_functions.py  # 50 组
python tests/test_clock.py           # 9 组
python tests/test_memdb.py           # 10 组
python tests/test_longterm.py        # 17 组
python tests/test_plugin_smoke.py    # 8 组
python demo.py                       # 端到端，打印注入块原文
python tools/day_demo.py             # 24 小时逐小时
```

全部为断言脚本，`Skipped 0 Failed 0` 即通过。

真机验证需 AstrBot 自带解释器（系统 python 缺 `deprecated`）：

```bash
"<AstrBot>/backend/python/python.exe" tools/verify_in_astrbot.py
```

## 疾病分布

| 系统 | 病种 | 系统 | 病种 |
|---|---|---|---|
| 消化 | 56 | 神经 | 31 |
| 血液 | 30 | 风湿免疫 | 29 |
| 心血管 | 29 | 内分泌 | 29 |
| 呼吸 | 28 | 运动 | 28 |
| 皮肤 | 27 | 外伤 | 24 |
| 泌尿 | 19 | 耳鼻咽喉 | 21 |
| 生殖 | 13 | 眼 | 12 |
| 代谢 | 11 | — | — |

合计 387：急性 129 / 慢性 258。按管线另分三类：普通 362、外伤 25、年龄型 5。管线与系统不互斥，外伤管线中有 2 条登记在运动与耳鼻咽喉系统下。

外伤模板 25 种。轻症 16：淤青 纸割伤 割伤 脚趾撞伤 烫嘴 水泡 噎住 擦伤 扎刺 烫伤 肌肉拉伤 腕扭伤 异物入眼 鼻出血 晒伤 蜇伤。中重度 9：深割伤 二度烧伤 腕骨折 踝骨折 肩脱位 脑震荡 跌倒摔伤 眼部化学伤 牙外伤（初值 0.56~0.78，实测一年约 0.1 次）。

年龄型 5 种，出现年龄按男 / 女：老视 42~50 / 40~48、老年性耳聋 58~72 / 55~70、骨质疏松 64~80 / 55~70、白内障 62~78 / 60~76、肌少症 66~80 / 64~78。

## 已知限制

1. 诊断是症状级的。双相 I 型在抑郁相与单次抑郁无法区分，靠预设病史先验。
2. 生化为现象学代理，不是药代动力学，绝对值不可当检验报告读。
3. 必须有可用模型。话语评估只有模型一条路径，每轮多一次小模型调用，默认超时 12 s。
4. 状态用 SQLite 串行写入，万人级并发需换连接池。
5. 表演效果取决于底座模型的指令遵循能力。
6. 危机判定是词表加规则，会漏隐晦表达，不能替代人工干预。
7. 换模型后应重跑 `tools/stress_induce.py --llm` 复核。
8. 正性刺激共用同一饱和项，模型分不出「被夸」与「被陪伴」。
9. 症状绝对幅度偏低，重度抑郁单项峰值 0.4~0.6，靠并存凑严重度。
10. 缺少「自我概念」状态量，100 轮后直接否定与人格化批评症状近乎重合。
11. 阴性症状分辨率有限，抑郁与精分紊乱型相差 0.014。
12. 药源性症状归因只覆盖直接写入 `sym` 的部分。
13. `max_block_chars` 低于 1000 会丢段。
14. 副作用强度不区分代谢快慢与基因多态性。
15. 无影像与病理，只有化验与体征。
16. 疾病库按人群发病率标定，个体化只到 30 个风险因子。
17. 化验绝对值不可当真，方向与内部自洽可信。
18. 危重不等于死亡，默认不判死。
19. 情感与记忆不参与诊断。慢性情绪经 IL-6、皮质醇、CRP 与静息心率进入体征和化验，但**不改症状严重度、不进诊断原型**：`test_mind.py` 用固定 seed 卡住这条，开关情绪前后症状和逐位相同。代价是「被骂三个月」的病程只来自症状侧，情绪侧的心境是平行叙事，两者可能不同步。
20. 记忆是文本级的。只存用户原话，不存角色自己的话，也不做结构化抽取；同义扩展只有 12 组手工词表，2-gram 的边界仍在（「公司把我裁了」切出「我裁」，勾不到「裁员」）。
21. 心境基线的下限由异稳态负荷决定，负荷 0.45 以上封顶 −0.20。所以「长期偏暗」在慢性化个体身上是设计行为，不是数值发散。
22. 饿与渴的阈值是按「说出来值不值得占篇幅」定的，不是按生理量定的。这条曲线被 `test_life_functions.py` 的「一天里有节奏」钉死，改阈值会被拦下。
23. 是否妊娠是显式状态，不由随机数触发；终止妊娠、避孕方式、辅助生殖不在模型内。
24. 妊娠并发症只到「窗口 + 指标」层。子痫前期落血压与尿蛋白、妊娠期糖尿病落血糖，但没有胎盘灌注、胎儿监护，也不改变分娩时机。
25. 性腺轴只有活动水平一个量，无行为模拟，不进注入块。围绝经潮热现在是连续脉冲（6 小时窄峰，叠激素深度与昼夜权重），但性腺轴本身仍是单标量。

### v1.9.0 解除的限制

| 原序号 | 原来的问题 | 现在的做法 |
|---|---|---|
| 19 | 逐小时循环，大步长阻塞（上限 14 天） | 上限一年；按天结算病程、发病、体质漂移与慢性情绪。五个 seed 各推一年 3.7 s |
| 21 | 无模型时情绪只剩词表，反讽读不出 | 词表兜底逐词计分：否定词 ×0.30、反讽正向 ×0.45 / 负向 ×1.15 |
| 22 | 词表兜底分不清谁在承受 | 人称主体系数，纯转述别人 ×0.35 |
| 23 | 记忆不做语义理解 | 12 组同义扩展，字面召回不足时以 0.60 权重补入 |
| 26 | 关闭身体后昼夜按每轮 6 小时攒 | `clock_mode=real` 时直读北京时间 |
| 27 | 表达义务是硬阈值 | 连续病理负荷（严重度 / 镇静 / 副作用 / 主诊断 / 热点取最大），0.20 以下豁免、0.42 以上强制，中间段「有由头就说」 |
| 28 | 体质 7 维一生不变 | 基线 + 按周漂移：体能 0.9 三年静息心率 −6，慢性疼痛痛敏 +0.30（急性疼痛不计入） |
| 29 | 情绪 → 身体只管急性（半衰期 1.8 h） | 加慢性通路：心情按 τ=8 h 计平均，按 96 / 168 h 上抬回落，抬 IL-6、皮质醇、CRP/hsCRP、静息心率 |
| 30 | 昼夜曲线不支持倒班与时差 | `/心理 时差 <小时>`（±12）：偏移叠到体温、心率、血压与就寝点，每天回 1 小时 |
| 31 | 外伤只有 16 个轻症模板 | 加 9 种中重度（深割伤、二度烧伤、腕 / 踝骨折、肩脱位、脑震荡、跌倒、眼部化学伤、牙外伤），初值 0.56 起 |
| 32 | 内感受只有 4 个通道 | 8 个：加心悸、起身发晕、耳鸣、肌肉酸 |
| 36 | 围绝经潮热是随机开关 | 连续脉冲曲线，叠加激素深度与昼夜权重 |

## 声明

- 角色扮演与创作辅助工具，不是医疗器械。诊断是引擎内部的叙事参数，不构成医学意见。
- 体检报告附免责声明，不给预后、生存期、存活率。
- 不含自伤方式、剂量建议或获取途径。`/心理 服药` 只输出「按常规剂量」，不打印毫克数。
- `crisis_override` 优先级最高，检出真实自伤风险时退出角色并给出求助资源（中国大陆心理援助热线 **12356**）。
- 仅用于虚构角色与明确知情的场景。

## 附录 A　ICD-11 诊断原型（72）

编码遵循 ICD-11 MMS 第 06 / 07 章；`6A2Z-UHR` 为自建亚临床状态。`curability` 是谈话治疗的单轮获益系数。

| 编码 | 中文 | 组 | curability |
|---|---|---|---|
| `6A20` | 精神分裂症 | psychotic | 0.02 |
| `6A21` | 分裂情感性障碍 | psychotic | 0.03 |
| `6A22` | 分裂型障碍 | psychotic | 0.02 |
| `6A23` | 急性短暂性精神病性障碍 | psychotic | 0.12 |
| `6A24` | 妄想障碍 | psychotic | 0.03 |
| `6A25` | 症状性精神病性障碍 | psychotic | 0.10 |
| `6A40` | 紧张症 | psychotic | 0.20 |
| `6A2Z-UHR` | 精神病高风险状态（前驱期） | psychotic | 0.15 |
| `6A60` | 双相I型障碍 | bipolar | 0.02 |
| `6A61` | 双相II型障碍 | bipolar | 0.03 |
| `6A62` | 环性心境障碍 | bipolar | 0.05 |
| `6A70` | 单次抑郁发作 | mood | 0.18 |
| `6A71` | 复发性抑郁障碍 | mood | 0.10 |
| `6A72` | 恶劣心境障碍 | mood | 0.08 |
| `6A73` | 混合性抑郁焦虑障碍 | mood | 0.20 |
| `6A80` | 经前期烦躁障碍 | mood | 0.15 |
| `6B00` | 广泛性焦虑障碍 | anxiety | 0.16 |
| `6B01` | 惊恐障碍 | anxiety | 0.22 |
| `6B02` | 广场恐惧 | anxiety | 0.18 |
| `6B03` | 特定恐惧症 | anxiety | 0.30 |
| `6B04` | 社交焦虑障碍 | anxiety | 0.20 |
| `6B05` | 分离焦虑障碍 | anxiety | 0.22 |
| `6B06` | 选择性缄默 | anxiety | 0.20 |
| `6B20` | 强迫症 | ocd | 0.04 |
| `6B21` | 躯体变形障碍 | ocd | 0.06 |
| `6B22` | 嗅觉参照障碍 | ocd | 0.06 |
| `6B23` | 疑病症（疾病焦虑障碍） | ocd | 0.10 |
| `6B24` | 囤积障碍 | ocd | 0.05 |
| `6B25.0` | 拔毛障碍 | ocd | 0.08 |
| `6B25.1` | 皮肤搔抓障碍 | ocd | 0.08 |
| `6B40` | 创伤后应激障碍 | stress | 0.06 |
| `6B41` | 复杂性创伤后应激障碍 | stress | 0.04 |
| `6B42` | 延长哀伤障碍 | stress | 0.12 |
| `6B43` | 适应障碍 | stress | 0.35 |
| `6B44` | 反应性依恋障碍 | stress | 0.05 |
| `6B45` | 脱抑制性社会参与障碍 | stress | 0.05 |
| `6B60` | 分离性神经症状障碍 | dissociative | 0.12 |
| `6B61` | 分离性遗忘 | dissociative | 0.14 |
| `6B62` | 出神障碍 | dissociative | 0.10 |
| `6B64` | 分离性身份障碍 | dissociative | 0.03 |
| `6B66` | 人格解体-现实解体障碍 | dissociative | 0.08 |
| `6B80` | 神经性厌食 | eating | 0.03 |
| `6B81` | 神经性贪食 | eating | 0.06 |
| `6B82` | 暴食障碍 | eating | 0.10 |
| `6B83` | 回避-限制性摄食障碍 | eating | 0.12 |
| `6C20` | 躯体痛苦障碍 | bodily | 0.10 |
| `6C21` | 身体完整性烦恼 | bodily | 0.05 |
| `6C40` | 酒精使用障碍 | substance | 0.03 |
| `6C43` | 阿片类使用障碍 | substance | 0.02 |
| `6C46` | 兴奋剂使用障碍 | substance | 0.03 |
| `6C4A` | 尼古丁使用障碍 | substance | 0.04 |
| `6C50` | 赌博障碍 | impulse | 0.05 |
| `6C51` | 游戏障碍 | impulse | 0.08 |
| `6C72` | 强迫性行为障碍 | impulse | 0.06 |
| `6C73` | 间歇性暴怒障碍 | impulse | 0.08 |
| `6D10.0` | 人格障碍（轻度） | personality | 0.03 |
| `6D10.1` | 人格障碍（中度） | personality | 0.02 |
| `6D10.2` | 人格障碍（重度） | personality | 0.01 |
| `6D11.0` | 显著负性情感特质 | personality | 0.04 |
| `6D11.1` | 显著疏离特质 | personality | 0.03 |
| `6D11.2` | 显著反社会特质 | personality | 0.01 |
| `6D11.3` | 显著解抑制特质 | personality | 0.03 |
| `6D11.4` | 显著强迫性特质 | personality | 0.03 |
| `6D11.5` | 边缘型模式 | personality | 0.02 |
| `6A02` | 孤独症谱系障碍 | neurodev | 0.01 |
| `6A05` | 注意缺陷多动障碍 | neurodev | 0.02 |
| `6D70` | 谵妄 | neurocognitive | 0.25 |
| `6D80` | 痴呆 | neurocognitive | 0.01 |
| `7A00` | 失眠障碍 | sleep | 0.22 |
| `7A01` | 嗜睡障碍 | sleep | 0.15 |
| `7A20` | 昼夜节律睡眠-觉醒障碍 | sleep | 0.20 |
| `6D50` | 做作性障碍 | other | 0.03 |

## 许可

MIT。
