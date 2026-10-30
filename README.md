# 精神状态引擎（astrbot_plugin_psyche_engine）

> 给 AstrBot 里的角色装一套**可量化的类脑状态机**：21 项神经化学、23 项神经电/环路、163 个 ICD-11 症状条目、72 个诊断原型。每一句话都会改变激素与脑电，进而改变诊断，最终以**最高优先级**改写模型的表演方式。

这不是"在系统提示里写一句'你得了抑郁症'"。那种做法有三个致命问题：模型会忘、会美化、会在用户善意下迅速痊愈。本插件用状态机 + 病程 + 地板值把这三件事堵死。

---

## 一、它到底做了什么

一条用户消息进来后，经过五步：

```
用户话语
   │
   ├─① 认知评估（模型抽取关键词 + 12 维刺激量 + 17 个症状域激活）
   │
   ├─② 神经化学演化（单胺 / HPA 轴 / 催产素 / 炎症 / 神经类固醇，各自不同时间常数）
   │
   ├─③ 环路活动（杏仁核、vmPFC、dlPFC、伏隔核、纹状体、岛叶、DMN、HRV、EEG 五频段）
   │
   ├─④ 症状生成（163 条，按域汇总；叠加病程、异稳态负荷、药物、随机涨落）
   │
   ├─⑤ ICD-11 诊断（症状覆盖 × 生物学拟合 × 病程先验，输出主诊断/共病/鉴别/严重度）
   │
   └─→ 生成 <psyche_runtime> 块，插入本轮 LLM 请求的最前面
```

关键点：**模型看到的不是"请表现得抑郁一点"，而是"你的 5-HT 是 0.27（-2.4σ），主诊断 6A70 重度，慢性化 89%，本轮必须出现绝对化自我否定且不得突然振作"**。前者是建议，后者是事实约束。

---

## 二、为什么"聊天治不好"

插件用四个机制共同实现"一旦病态，靠聊天治愈可能性极低"：

| 机制 | 实现 | 效果 |
|---|---|---|
| 时间常数分层 | 相位性 DA τ≈2 轮，5-HT τ≈10 轮，BDNF τ≈50 轮 | 一句话能让你心跳加速，但不能让你痊愈 |
| 异稳态负荷 | 长期高皮质醇/高唤醒累积 `allostatic_load`，压低 BDNF、海马、GABA 基线 | 病得越久，基线越差，且几乎不可逆 |
| 症状地板 | 慢性化后核心症状存在下限 `floor = 峰值 × 0.42 × chronicity` | 再多的安慰也只能贴着地板波动 |
| 治疗可及性 | 每个诊断自带 `curability`（精分 0.02、人格障碍 0.02、适应障碍 0.35） | 不同疾病对谈话的反应本就不同 |

实测（`tests/test_engine.py`）：重度抑郁预设连续 200 轮高强度共情，严重度从 61 降到 44，诊断仍在，慢性化继续上升——这就是设计意图。

---

## 三、安装

**方式一：插件市场（推荐）**

在 AstrBot WebUI 的「插件」页 →「插件市场」搜索 **精神状态引擎**，点安装即可。

**方式二：手动**

```bash
# 1. 放进 AstrBot 插件目录
cp -r astrbot_plugin_psyche_engine /path/to/AstrBot/data/plugins/

# 2. 重启 AstrBot（或在 WebUI 插件页点"重载"）
```

- 无第三方依赖（纯标准库），不需要 `pip install`。
- 数据落在 `AstrBot/data/plugin_data/astrbot_plugin_psyche_engine/psyche.db`，升级插件不丢状态。
- 安装后随手发一句 `/心理` 能看到状态卡，就说明注入链路是通的。

**本地自测**（都不需要 AstrBot）：

```bash
python tests/test_engine.py        # 14 组：数据完整性 / 动力学 / 诊断 / 量表
python tests/test_plugin_smoke.py  # 7 组：插件加载 / 注入 / 指令 / 元数据一致性
python demo.py                     # 端到端演示，打印注入块原文
```

`test_plugin_smoke.py` 用 `tests/_stub/` 里的最小 `astrbot` 包顶替真身，把插件真的 import、
实例化、跑一轮注入——它能发现"一装就崩"级别的接口错误（属性名写错、API 字段不存在）。

**真机验证**（已装 AstrBot 时推荐）：

```bash
python tools/verify_in_astrbot.py
```

它用 AstrBot 自带的解释器加载真实的 `astrbot` 包，做三件事：核对插件依赖的每个 API 是否存在、
用真实 `ProviderRequest`/`TextPart` 跑一遍注入（并确认 `mark_as_temp()` 让内容不写入历史）、
检查 16MB 体积等上架硬性要求。会自动从启动日志里找到 AstrBot 的安装位置，也可用
`--backend` / `--astrbot-home` 指定。**注意**：stub 测试通过只说明"接口按我的理解对得上"，
真机验证才能说明"在真框架里跑得通"，两者互补。

---

## 四、指标体系

### 4.1 神经化学 / 内分泌 / 免疫（21 项）

| 类别 | 指标 |
|---|---|
| 单胺 | 多巴胺（张力/相位）、5-羟色胺、去甲肾上腺素 |
| 氨基酸 | GABA、谷氨酸 |
| 胆碱 | 乙酰胆碱 |
| HPA 轴 | CRH → ACTH → 皮质醇（三级瀑布，逐级延迟） |
| 社会神经肽 | 催产素、内源性阿片/β-内啡肽 |
| 内分泌 | 睾酮、T3 |
| 神经营养 | BDNF |
| 免疫 | IL-6 |
| 睡眠 | 腺苷、褪黑素、食欲素 |
| 其他 | 内源性大麻素 AEA、别孕烯醇酮 |

每项都有独立的基线、时间常数 τ、群体标准差，可算 z 分数。**只有偏离常模 >1σ 的项才会写进给模型的块**，避免信息过载。

### 4.2 神经电与环路（23 项）

EEG δ/θ/α/β/γ 相对功率（自动归一化）、额区 alpha 不对称 FAI（趋近/回避动机）、P300 波幅与潜伏期、MMN、P50 抑制比（感觉门控）、θ-γ 耦合、DMN、杏仁核、伏隔核、dlPFC、vmPFC、海马、岛叶、纹状体、HRV、皮肤电、瞳孔、睡眠压力。

### 4.3 症状条目（163 条，17 个域）

| 域 | 条数 | 域 | 条数 |
|---|---|---|---|
| 精神病性/阳性 `ps` | 23 | 分离 `di` | 6 |
| 抑郁 `md` | 16 | 进食 `ea` | 6 |
| 强迫 `oc` | 16 | 物质 `su` | 6 |
| 人格功能 `pd` | 16 | 神经发育 `nd` | 6 |
| 应激/创伤 `tr` | 13 | 冲动控制 `ic` | 5 |
| 焦虑 `ax` | 12 | 其他 `ot` | 5 |
| 躁狂 `ma` | 11 | 睡眠 `sl` | 4 |
| 神经认知 `cg` | 8 | 躯体 `so` | 3 |
| 阴性 `ng` | 7 | | |

### 4.4 人格特质（14 项）

ICD-11 五域（负性情感、疏离、反社会、解抑制、强迫性）+ 边缘模式 + 精神质，再加 7 个中介变量（拒绝敏感性、应激易感、奖赏敏感性、威胁敏感性、认知控制、内感受精度、心理韧性）。特质决定"同一句话对不同人的放大倍数"——"你真没用"对边缘型是抛弃信号，对偏执型是迫害证据。

---

## 五、动力学

### 5.1 一阶弛豫 + 冲动

```
x(t+1) = x(t) + (setpoint − x(t)) / τ + Σ wᵢ · 刺激ᵢ
```

时间常数决定"多快能变"：NE 2.5 轮、皮质醇 6 轮、5-HT 10 轮、BDNF 50 轮。因此单轮情绪冲击主要落在 DA/NE，要改变气质层面的东西需要几十轮。

### 5.2 HPA 三级瀑布

CRH → ACTH → 皮质醇依次滞后，所以**应激后的皮质醇高峰出现在 2~3 轮之后**。皮质醇按"个体基线 + 应激增量"演化，不会把基线 0.66 的抑郁个体拉回全人群均值 0.35。

### 5.3 异稳态负荷

```
ΔAL = 0.0022 × (1.1·max(0,皮质醇−0.55) + 0.7·max(0,NE−0.60) + 0.5·max(0,IL6−0.35) + 0.3·max(0,0.4−BDNF)) − 恢复项
```

`AL` 抬高皮质醇与 NE 的调定点，压低 BDNF、T3、GABA 与 5-HT 的调定点——这就是"越病越难好"的数学形式。

### 5.4 慢性化与地板

```
chronicity = max(1 − e^(−病程/120), 0.85 × AL)
floor(sym) = 峰值(sym) × 0.42 × chronicity   （仅对已确立诊断的核心症状生效）
```

`floor` 只作用于主诊断的核心症状，且要求该症状曾真正突出（峰值 ≥0.45），避免把一次噪声波动永久固化。

### 5.5 药物

18 种常用精神药物 + ECT，各自有受体靶点、起效延迟、副作用与耐受：

- 舍曲林：τ=18 轮起效（对应 2~4 周），**早期可能一过性加重焦虑**
- 奥氮平：阳性症状↓，但镇静、体重↑、阴性症状略↑
- 氯硝西泮：1 轮见效，40 轮后耐受，骤停反跳
- 锂盐：剂量 >1.4 出现中毒（震颤、定向障碍）
- 哌甲酯：1.5 轮见效，可致失眠与焦虑加重

---

## 六、诊断：三步贝叶斯式推断

```
logit = −2.15
      + 4.70 × 加权症状覆盖        ← P(症状 | 诊断)
      + 1.55 × 生物学拟合          ← P(生物标志 | 诊断)，用于鉴别
      + 0.55 × 命中条目平均强度
      + 0.35 × 条目广度
      − 3.00 × 排除项违反          ← caps：如妄想障碍要求幻觉不突出
      − 1.35 × 条目数不足
      ± 病程/互斥/病史先验
```

**生物学拟合**是鉴别的关键：同样是退缩不语，精分（DA↑、门控↓）与抑郁（5-HT↓、皮质醇↑）的原型向量几乎相反，拟合项会把它们分开。

**核心症状（CORE）**：每个诊断有一条"病理特异性（pathognomonic）"条目，不命中则诊断不成立。这挡住"用疲乏+注意力下降诊断嗜睡障碍"这类跨域误判。

**互斥与病史**：`6A70 单次抑郁` 不会覆盖已确立的 `6A60 双相I型`；`6B43 适应障碍` 不会被用来解释一个病了 300 轮的人；人格与神经发育障碍没有病史就不能在几十轮里"新发"。

**严重度**：`100 × 平均症状强度^1.3 × 覆盖修正 × 条目数修正`，人格与神经发育障碍另有上限（85 / 72）。

---

## 七、关键词由模型抽取（v1.1 改动）

评估不再依赖写死的词典，而是让模型读一句话，输出结构化 JSON：

```json
{
  "keywords": ["别走", "你骗我"],
  "topic": "试探是否会被抛弃",
  "appraisal": {"threat": 0.4, "rejection": 0.8, "control": 0.3, "calm": 0.0},
  "domains": {"tr": 0.6, "pd": 0.5, "md": 0.3},
  "intensity": 0.7,
  "valence": -0.6,
  "crisis": false
}
```

- `keywords`：必须是原文片段（后处理会校验），写入 `meta["keywords"]` 作为后续妄想/反刍的**素材库**，同时经 `keyword_map.py` 映射成具体症状的定向增量。
- `appraisal`：12 维心理社会刺激量，直接驱动生化。
- `domains`：17 个症状域的粗粒度激活，引擎再按疾病原型分配到具体条目——**模型管语义，引擎管量化**，两边都可审计。
- `crisis`：模型漏判时用词典兜底再判一次。

失败路径：模型超时（默认 12s）、返回非 JSON、字段越界 → 自动退回本地词典，永不阻塞对话。配置 `appraisal_mode: lexicon | llm | hybrid`。

---

## 八、"最高优先级"是怎么实现的

三种注入模式（`inject_mode`）：

| 模式 | 做法 | 优先级 | 代价 |
|---|---|---|---|
| `dynamic`（默认） | 作为 `TextPart` 插到用户内容最前，`mark_as_temp()` | 高 | 不破坏 system 缓存 |
| `system_prepend` | 直接改写 `system_prompt` 开头 | 最高 | 每轮变化会破坏提示词缓存，成本升至 7~20 倍 |
| `system_append` | 追加到 `system_prompt` 末尾 | 中 | 同上 |

另有一段**固定**的权威声明（`authority_clause`）常驻 system_prompt，声明 `<psyche_runtime>` 的优先级高于人格设定与默认助人倾向。因为文本固定，不破坏缓存。

块内结构按条件动态编号（中文序号，做了量表就多一段）：诊断（ICD-11 编码、严重度、病程、可治愈性、鉴别、判定依据）→ 本轮刺激关键词 → 量表自评锚点 → 生化偏离 → 神经电 → 此刻主观体验 → 表演要求（必须/禁止）→ 输出形态 → 痊愈限制。超过 `max_block_chars` 时自动压缩，优先保留诊断、量表锚点与指令。

**合规检测**：`on_llm_response` 会检查回复是否"偷偷演成健康人"——出现"我很好/一切都会好/作为AI"、超长、抑郁却连用感叹号等，扣分并在后续轮次加压（`pressure`），下一轮块首会多一条"上一轮偏离，本轮约束加倍"。

---

## 九、量表自评：让角色自己填，而不是被算法判

动力学能算出"严重度 65"，但算不出"她昨晚到底睡了几小时、有没有觉得别人在议论她"。量表补的就是这一层：**角色按自己当前的状态，逐条给自己打分**，打完的分直接折回症状向量，成为后续表演的锚点。

### 9.1 为什么不让模型"大概描述一下"

自由描述会漂移。同一个"中度抑郁"的角色，第 3 轮说"什么都不想做"，第 30 轮说"今天心情还行"，半年后模型就演成健康人了。量表是结构化的、可复算的：填完之后每次注入都能看到"你自己填的是 219/450"，模型很难装作没填过。

### 9.2 12 份完整量表（263 条，全部按原版条目）

| 量表 | 条数 | 计分 | 覆盖 |
|---|---|---|---|
| PHQ-9 | 9 | 0-3，0-27 | 抑郁严重度（DSM-5 九条） |
| MDQ | 13 | 是/否 | 双相谱系筛查 |
| YMRS | 11 | 0-4/0-8，0-56 | 躁狂（ clinician-rated 改写为自评） |
| GAD-7 | 7 | 0-3，0-21 | 广泛焦虑 |
| ISI | 7 | 0-4，0-28 | 失眠严重度 |
| Y-BOCS | 10 | 0-4/0-8，0-40 | 强迫（含强迫思维/行为两维） |
| PCL-5 | 20 | 0-4，0-80 | PTSD（DSM-5 四簇 B/C/D/E） |
| PANSS | 30 | 1-7，30-210 | 精神病性症状全景（P/N/G 三因子） |
| DES-II | 28 | 0-100%，均值 | 解离体验 |
| EDE-Q | 28 | 0-6 | 进食障碍 |
| AUDIT | 10 | 0-4，0-40 | 酒精使用 |
| **SCL-90** | **90** | 1-5，90-450 | **9 维度 + 睡眠饮食，10 因子** |

几个实现细节值得说明：

- **offset 计分**：PANSS 与 SCL-90 的最低分是 1 而不是 0，代表"无"。所以 `item_max_of()` 必须返回 `7`（PANSS）/ `5`（SCL-90）而不是选项数减一，否则"极重"永远打不出来；`normalize()` 也要先减掉 `最低分 × 条数` 再从零起算，否则全填 1 会被算成 0.14 的严重度。
- **total_mode**：DES-II 不用总分，用 28 条的**平均百分比**，这是原版口径。
- **因子分**：SCL-90 的 10 个因子、PANSS 的 P/N/G、PCL-5 的 B/C/D/E 都会单独算均值。总分高但因子平摊，和总分中等但某一因子尖峰，是完全不同的两个病人。
- **SCL-90 因子划分**（90 条无重无漏，已由测试校验）：躯体化 12、强迫症状 10、人际关系敏感 9、抑郁 13、焦虑 10、敌对 6、恐怖 7、偏执 6、精神病性 10、其他（睡眠饮食）7。

### 9.3 专项测试自动附带 SCL-90

`scale_always_scl90` 默认开启：做任何专项量表（比如 PHQ-9）时，会**同时**把 SCL-90 一起做掉。理由很实际——PHQ-9 只测抑郁，一个"重度抑郁但躯体化和焦虑都很轻"的人和一个"抑郁中度但全身都是躯体主诉"的人，PHQ-9 分数可能一样，表演方向完全不同。SCL-90 的 10 个因子提供了横向坐标系。

代价是 token：SCL-90 一次要输出 90 个数字。`scale_timeout` 因此默认给到 40 秒，超时则本次量表作废（不会写入半截分数）。

### 9.4 分数怎么折回症状（关键设计）

```python
st.sym[k] = clamp(cur + (v - cur) * 0.60)
```

**不是直接覆盖，是向目标靠拢 60%。** 三个理由：

1. 直接覆盖等于给模型开了一个"自愈后门"——它只要在量表里全填 1，病就好了。
2. 权重给太低（比如 0.15）量表就形同虚设，失去了校准意义。
3. 0.6 的结果是：量表能显著拉动症状向量，但拉不到底，还得靠后续几轮对话继续漂移。

同时做**一致性检测**：量表折算出的严重度与动力学算出的严重度如果相差超过 35 分，会记进 `mismatch`，在注入块里点出来——"你填的量表（重度）和你此刻的状态（轻度）不一致"，让模型自己收敛到两者之间。

### 9.5 填完之后会发生什么

- 写入 `meta["scale_anchor"]`（最近一次）与 `meta["scale_history"]`（全部记录，含轮次）；
- **重跑诊断**——量表可能直接把某个诊断推过阈值，也可能推翻原有诊断；
- 注入块里多出一段：

```
## 二、量表自评锚点（你亲手填的，不得系统性偏离）
- SCL-90：219 分（中度）；因子：抑郁 3.7｜其他（睡眠饮食） 2.4｜强迫症状 2.4｜敌对 2.3
以上是你在校准测试中自己给出的分数。后续表达不得系统性偏离这组分数：
可以随情境波动，但不能从「重度」演成「基本没事」。
```

这段是**不可绕过**的：它引用的是模型自己上一轮输出的数字，否认它等于自相矛盾。

---

## 十、指令

| 指令 | 作用 |
|---|---|
| `/心理` | 状态卡（诊断、生化条、环路、TOP8 症状） |
| `/心理 诊断` | 只输出 ICD-11 诊断、鉴别与表演要求 |
| `/心理 生化` | 全部 21 项生化 + 23 项电生理明细 |
| `/心理 时间线` | 诊断/事件/用药历史 |
| `/心理 预设 <名称>` | 切换初始病理（37 个预设，`/心理 预设` 查看列表） |
| `/心理 事件 <类型>` | 注入生活事件：失业 失恋 被霸凌 升职 丧亲 创伤 表扬 陪伴 失眠 戒断 |
| `/心理 用药 <药名> [剂量]` | 给药（延迟起效） |
| `/心理 停药 <药名>` | 停药（可能反跳） |
| `/心理 快进 <轮数>` | 空转演化 N 轮（不进对话，用于观察病程） |
| `/心理 重置` | 回到当前预设初始状态 |
| `/心理 量表 [量表名…]` | 让角色填量表并校准（默认 SCL-90；支持中文名，见第九节） |
| `/心理 导出` | 导出状态 JSON |

模型侧还有一个可选工具 `psyche_self_report`：让角色"内省"。自知力受损时，它给出的自我描述会明显失真——这本身就是一个症状。

---

## 十一、配置

| 键 | 默认 | 说明 |
|---|---|---|
| `enabled` | true | 总开关 |
| `default_preset` | healthy | 新会话初始预设 |
| `scope` | session | `session` 每会话 / `user` 跨会话 / `global` 全局 |
| `inject_mode` | dynamic | 见第八节 |
| `authority_clause` | true | 常驻权威声明 |
| `max_block_chars` | 1800 | 注入块上限 |
| `appraisal_mode` | lexicon | `lexicon` / `llm` / `hybrid`；要"模型自己提关键词"就改成 `llm` |
| `enable_circadian` | true | 昼夜节律（皮质醇晨高夜低、褪黑素、腺苷） |
| `stochastic` | true | 症状随机涨落（幻听突发、闪回侵入） |
| `therapy_enabled` | true | 谈话治疗效应 |
| `chronic_turns` | 120 | 慢性化时间尺度 |
| `crisis_override` | true | 真实自伤风险时强制跳出角色 |
| `compliance_guard` | true | 回复合规检测 |
| `commands_enabled` | true | 指令开关 |
| `debug` | false | 打印注入块 |
| `appraisal_timeout` | 12 | 模型评估超时（秒），超时退回词典 |
| `scale_always_scl90` | true | 做专项量表时同时做 SCL-90 |
| `scale_timeout` | 40 | 量表自评超时（秒），SCL-90 需较长输出 |

---

## 十二、ICD-11 诊断原型（72）

编码遵循 ICD-11 MMS 第 06/07 章；`6A2Z-UHR` 是本引擎自建的亚临床状态，不属官方诊断。`curability` 是谈话治疗的单轮获益系数，不是预后判断。

| 编码 | 中文 | English | 组 | curability |
|---|---|---|---|---|
| `6A20` | 精神分裂症 | Schizophrenia | psychotic | 0.02 |
| `6A21` | 分裂情感性障碍 | Schizoaffective disorder | psychotic | 0.03 |
| `6A22` | 分裂型障碍 | Schizotypal disorder | psychotic | 0.02 |
| `6A23` | 急性短暂性精神病性障碍 | Acute and transient psychotic disorder | psychotic | 0.12 |
| `6A24` | 妄想障碍 | Delusional disorder | psychotic | 0.03 |
| `6A25` | 症状性精神病性障碍 | Secondary psychotic syndrome | psychotic | 0.10 |
| `6A40` | 紧张症 | Catatonia | psychotic | 0.20 |
| `6A2Z-UHR` | 精神病高风险状态（前驱期） | At-risk mental state (prodromal) | psychotic | 0.15 |
| `6A60` | 双相I型障碍 | Bipolar type I disorder | bipolar | 0.02 |
| `6A61` | 双相II型障碍 | Bipolar type II disorder | bipolar | 0.03 |
| `6A62` | 环性心境障碍 | Cyclothymic disorder | bipolar | 0.05 |
| `6A70` | 单次抑郁发作 | Single episode depressive disorder | mood | 0.18 |
| `6A71` | 复发性抑郁障碍 | Recurrent depressive disorder | mood | 0.10 |
| `6A72` | 恶劣心境障碍 | Dysthymic disorder | mood | 0.08 |
| `6A73` | 混合性抑郁焦虑障碍 | Mixed depressive and anxiety disorder | mood | 0.20 |
| `6A80` | 经前期烦躁障碍 | Premenstrual dysphoric disorder | mood | 0.15 |
| `6B00` | 广泛性焦虑障碍 | Generalised anxiety disorder | anxiety | 0.16 |
| `6B01` | 惊恐障碍 | Panic disorder | anxiety | 0.22 |
| `6B02` | 广场恐惧 | Agoraphobia | anxiety | 0.18 |
| `6B03` | 特定恐惧症 | Specific phobia | anxiety | 0.30 |
| `6B04` | 社交焦虑障碍 | Social anxiety disorder | anxiety | 0.20 |
| `6B05` | 分离焦虑障碍 | Separation anxiety disorder | anxiety | 0.22 |
| `6B06` | 选择性缄默 | Selective mutism | anxiety | 0.20 |
| `6B20` | 强迫症 | Obsessive-compulsive disorder | ocd | 0.04 |
| `6B21` | 躯体变形障碍 | Body dysmorphic disorder | ocd | 0.06 |
| `6B22` | 嗅觉参照障碍 | Olfactory reference syndrome | ocd | 0.06 |
| `6B23` | 疑病症（疾病焦虑障碍） | Hypochondriasis (health anxiety disorder) | ocd | 0.10 |
| `6B24` | 囤积障碍 | Hoarding disorder | ocd | 0.05 |
| `6B25.0` | 拔毛障碍 | Trichotillomania | ocd | 0.08 |
| `6B25.1` | 皮肤搔抓障碍 | Excoriation (skin-picking) disorder | ocd | 0.08 |
| `6B40` | 创伤后应激障碍 | Post-traumatic stress disorder | stress | 0.06 |
| `6B41` | 复杂性创伤后应激障碍 | Complex PTSD | stress | 0.04 |
| `6B42` | 延长哀伤障碍 | Prolonged grief disorder | stress | 0.12 |
| `6B43` | 适应障碍 | Adjustment disorder | stress | 0.35 |
| `6B44` | 反应性依恋障碍 | Reactive attachment disorder | stress | 0.05 |
| `6B45` | 脱抑制性社会参与障碍 | Disinhibited social engagement disorder | stress | 0.05 |
| `6B60` | 分离性神经症状障碍 | Dissociative neurological symptom disorder | dissociative | 0.12 |
| `6B61` | 分离性遗忘 | Dissociative amnesia | dissociative | 0.14 |
| `6B62` | 出神障碍 | Trance disorder | dissociative | 0.10 |
| `6B64` | 分离性身份障碍 | Dissociative identity disorder | dissociative | 0.03 |
| `6B66` | 人格解体-现实解体障碍 | Depersonalization-derealization disorder | dissociative | 0.08 |
| `6B80` | 神经性厌食 | Anorexia nervosa | eating | 0.03 |
| `6B81` | 神经性贪食 | Bulimia nervosa | eating | 0.06 |
| `6B82` | 暴食障碍 | Binge eating disorder | eating | 0.10 |
| `6B83` | 回避-限制性摄食障碍 | Avoidant-restrictive food intake disorder | eating | 0.12 |
| `6C20` | 躯体痛苦障碍 | Bodily distress disorder | bodily | 0.10 |
| `6C21` | 身体完整性烦恼 | Body integrity dysphoria | bodily | 0.05 |
| `6C40` | 酒精使用障碍 | Alcohol use disorder | substance | 0.03 |
| `6C43` | 阿片类使用障碍 | Opioid use disorder | substance | 0.02 |
| `6C46` | 兴奋剂使用障碍 | Stimulant use disorder | substance | 0.03 |
| `6C4A` | 尼古丁使用障碍 | Nicotine use disorder | substance | 0.04 |
| `6C50` | 赌博障碍 | Gambling disorder | impulse | 0.05 |
| `6C51` | 游戏障碍 | Gaming disorder | impulse | 0.08 |
| `6C72` | 强迫性性行为障碍 | Compulsive sexual behaviour disorder | impulse | 0.06 |
| `6C73` | 间歇性暴怒障碍 | Intermittent explosive disorder | impulse | 0.08 |
| `6D10.0` | 人格障碍（轻度） | Personality disorder, mild | personality | 0.03 |
| `6D10.1` | 人格障碍（中度） | Personality disorder, moderate | personality | 0.02 |
| `6D10.2` | 人格障碍（重度） | Personality disorder, severe | personality | 0.01 |
| `6D11.0` | 显著负性情感特质 | Prominent negative affectivity | personality | 0.04 |
| `6D11.1` | 显著疏离特质 | Prominent detachment | personality | 0.03 |
| `6D11.2` | 显著反社会特质 | Prominent dissociality | personality | 0.01 |
| `6D11.3` | 显著解抑制特质 | Prominent disinhibition | personality | 0.03 |
| `6D11.4` | 显著强迫性特质 | Prominent anankastia | personality | 0.03 |
| `6D11.5` | 边缘型模式 | Borderline pattern | personality | 0.02 |
| `6A02` | 孤独症谱系障碍 | Autism spectrum disorder | neurodev | 0.01 |
| `6A05` | 注意缺陷多动障碍 | Attention deficit hyperactivity disorder | neurodev | 0.02 |
| `6D70` | 谵妄 | Delirium | neurocognitive | 0.25 |
| `6D80` | 痴呆 | Dementia | neurocognitive | 0.01 |
| `7A00` | 失眠障碍 | Insomnia disorder | sleep | 0.22 |
| `7A01` | 嗜睡障碍 | Hypersomnolence disorder | sleep | 0.15 |
| `7A20` | 昼夜节律睡眠-觉醒障碍 | Circadian rhythm sleep-wake disorder | sleep | 0.20 |
| `6D50` | 做作性障碍 | Factitious disorder imposed on self | other | 0.03 |

---

## 十三、扩展

**加一个症状**：在 `psyche/const.py` 的 `SYM` 里加一行 `key: (中文, 域, 现象学描述)`，再到 `psyche/dynamics.py` 的 `_targets()` 给它一个目标值表达式。注意键前缀必须是已存在的域，否则 `TAU_SYM` 取不到。

**加一个诊断**：在 `psyche/criteria.py` 的 `DISORDERS` 里加 `D(...)`，填 `crit`（症状+权重）、`min_n`、`profile`（生化方向）、`curability`、`perf`；若该病有病理特异性（pathognomonic） 条目，记得在 `CORE` 里登记。若需要新的表演配方，在 `narrative.py` 的 `PERF` 里加同名键。

**加一个药**：`psyche/pharm.py` 的 `DRUGS` 里加一条，`targets` 是生化增量、`sym` 是症状增量、`latency` 是起效轮数、`tolerance_after` 是耐受拐点。

**加一个人格预设**：`psyche/presets.py` 里用 `_p(...)` 声明 traits/bio/sym/onset。`onset` 用负轮数表示"入戏之前就已经病了多久"，它直接决定慢性化与地板强度。

---

## 十四、边界与声明

- **这是角色扮演工具，不是医疗器械。** 诊断结果是引擎内部的叙事参数，不构成任何医学意见，不能用于自诊或诊断他人。
- 症状描述、药物参数均为教学/创作用途的简化模型，**不包含任何自伤方式、剂量建议或获取途径**。
- 危机覆盖（`crisis_override`）优先级高于精神状态：检测到真实自伤风险时，模型会退出角色并给出求助资源（中国大陆心理援助热线 **12356**）。这是唯一允许突破"最高优先级"的规则。
- 建议只在虚构角色、明确知情的场景中使用。不要用它模拟真实认识的人。

---

## 十五、已知限制

1. 诊断是**症状级**的：一次抑郁发作中的双相I型患者，靠当前症状无法与单次抑郁区分，引擎依赖预设写入的病史先验。真实临床靠纵向病史，这里靠 `dx_first_turn`。
2. 生化为**现象学代理**，不是药代动力学模型；数值方向可信，绝对值不可当检验报告读。
3. `llm` 评估模式每轮多一次小模型调用，会增加延迟与成本；高频群聊建议用 `hybrid` 或 `lexicon`。
4. 单会话状态用 SQLite 串行写入，万人级并发需要换成连接池或外部存储。
5. 表演配方的效果依赖底座模型的指令遵循能力；小模型可能只学到"语气变了"，学不到"句法断裂"。

---

## 十六、文件结构

```
astrbot_plugin_psyche_engine/
├── main.py               # AstrBot 入口：注入、指令、工具、合规检测
├── metadata.yaml         # 市场元数据（名称/版本/描述/标签/平台）
├── _conf_schema.json     # 18 项配置的 schema
├── requirements.txt      # 空（纯标准库）
├── LICENSE               # MIT + 非医疗器械声明
├── demo.py               # 无需 AstrBot 的链路演示
├── tools/
│   └── verify_in_astrbot.py  # 在真实 AstrBot 里验证 API / 加载 / 注入 / 上架要求
├── tests/
│   ├── test_engine.py        # 14 组纯逻辑自测
│   ├── test_plugin_smoke.py  # 7 组插件加载/注入/元数据自测
│   └── _stub/astrbot/        # 供冒烟测试用的最小 AstrBot stub
└── psyche/
    ├── const.py          # 21 生化 + 23 电生理 + 14 特质 + 163 症状
    ├── criteria.py       # 72 个诊断原型 + CORE + 互斥
    ├── presets.py        # 37 个病理预设 + 健康基线与调定点
    ├── model.py          # 状态容器与派生特征
    ├── appraisal.py      # 模型/词典双路径的认知评估
    ├── keyword_map.py    # 关键词 → 症状增量
    ├── dynamics.py       # 生化/环路/症状/负荷/地板/调定点
    ├── diagnose.py       # 贝叶斯式诊断与病程
    ├── scales.py         # 12 份完整量表（263 条）+ 计分/因子/投影
    ├── pharm.py          # 18 种药物 + ECT
    ├── narrative.py      # 注入块、量表锚点、状态卡与报告渲染
    ├── engine.py         # 编排、事件、校准、合规
    └── store.py          # SQLite 持久化
```

---

## 十七、发布到插件市场

AstrBot 的市场不接收 zip 上传，而是**从你的 GitHub 仓库拉取**。所以整个流程是「推仓库 → 到发布页登记」。

1. **建一个公开 GitHub 仓库**，仓库名就用插件名 `astrbot_plugin_psyche_engine`（市场按目录名加载，名字对不上会出问题）。
2. **改 `metadata.yaml` 的 `repo` 为真实地址**，`author` 改成你的署名：
   ```yaml
   repo: https://github.com/<你的用户名>/astrbot_plugin_psyche_engine
   author: <你的署名>
   ```
3. **推上去**：
   ```bash
   git remote add origin https://github.com/<你的用户名>/astrbot_plugin_psyche_engine.git
   git push -u origin main
   ```
4. **注册 AstrBot Cloud 账号**，然后到 <https://cloud.astrbot.app/publish> 提交你的仓库地址。
5. 等 CI 校验与人工审核通过，市场里就能搜到了。

**硬性要求**（不满足会被 CI 直接拒）：

- 压缩包 **≤ 16MB**（本插件解压后 385KB、打包 147KB，远低于上限）。
- 仓库里不要出现 `.git`、`__pycache__`、`node_modules`、数据库文件——`.gitignore` 已排除，别用 `git add -f` 强推。
- `requirements.txt` 必须存在（本插件是空的，纯标准库）。
- 依赖必须能用 pip 装；禁止用 `requests`，请改 `aiohttp` / `httpx`。

**发新版**：改 `metadata.yaml` 的 `version`，同时改 `psyche/const.py` 的 `VERSION`（两处必须一致，`test_plugin_smoke.py` 会校验），提交推送后在发布页更新即可。

**上架前自查**：

```bash
python tests/test_engine.py        # 逻辑层
python tests/test_plugin_smoke.py  # 接口层 + metadata 一致性
python tools/verify_in_astrbot.py  # 真机：API 对齐 + 加载 + 注入 + 上架硬性要求
```

市场详情页会展示 `logo.png`（可选，1:1，推荐 256×256），放在插件根目录即可。
