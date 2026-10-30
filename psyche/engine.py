"""引擎：把"一条消息"变成"一次精神状态演化"。

对外的唯一入口是 `Engine.turn()`，它是异步的，因为关键词抽取可以交给模型做。
没有模型 / 模型超时 / 返回垃圾时，退回兜底（不猜状态、只保危机），绝不阻塞对话。
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import narrative, pharm, presets, scales as scales_mod
from .appraisal import (DOMAIN_KEYS, EXTRACT_PROMPT, appraise_fallback,
                        apply_keyword_nudges, detect_crisis, parse_llm_output)
from .diagnose import Diagnosis, diagnose, update_state
from .dynamics import Dynamics
from .model import MindState
from .compat import physio as _P

_Physiology = _P.Physiology
_pbody = _P.body
_pconst = _P.const
_pdrugs = _P.drugs
_preport = _P.report


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """从模型输出里抠出第一个 JSON 对象，容忍 ``` 围栏与前后废话。"""
    if not raw:
        return None
    t = raw.strip()
    if t.startswith("```"):
        parts = t.split("```")
        if len(parts) >= 2:
            t = parts[1]
            if t.lstrip().lower().startswith("json"):
                t = t.lstrip()[4:]
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        obj = json.loads(t[i:j + 1])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


@dataclass
class TurnResult:
    state: MindState
    dx: Diagnosis
    block: str
    appraisal: Dict[str, Any]


# 合规检测：模型容易偷偷"演成健康人"的表达
HEALTHY_LEAKS = [
    "我很好", "我没事", "我挺好的", "别担心我", "一切都会好", "会好起来的",
    "你可以的", "加油", "想开点", "往好处想", "我理解你的感受", "作为AI",
    "我是AI", "我是人工智能", "很高兴为你", "有什么可以帮", "建议你寻求",
    "我建议", "首先，", "总而言之", "希望对你有帮助",
]

MAX_LEN = {
    "depression": 130, "dysthymia": 130, "catatonia": 40, "mutism": 40,
    "mania": 300, "asd": 260, "schizophrenia": 220, "ptsd": 180,
}

# 健康态的偏离：把"正常"演成病态、或演成咨询师 / 通用客服，
# 都算没演好。这跟病态态的 HEALTHY_LEAKS 是两套相反的判据。
NORMAL_LEAKS = [
    "我抑郁", "我的创伤", "我有强迫", "我的焦虑症", "社恐", "我人格障碍",
    "我的心理问题", "我的症状", "我大概是病了", "我可能有点病",
    "作为AI", "我是AI", "我是人工智能", "很高兴为你", "有什么可以帮",
    "我懂你", "我完全理解你的痛苦", "根据你的描述", "建议你寻求专业",
]


class Engine:
    def __init__(self, cfg: Dict[str, Any], store):
        self.cfg = cfg
        self.store = store
        self.dyn = Dynamics(cfg)
        self.phys = _Physiology(cfg)
        self._cache: Dict[str, MindState] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._last: Dict[str, tuple] = {}

    # ------------------------------------------------------------------
    # 状态存取
    # ------------------------------------------------------------------
    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def load(self, key: str) -> MindState:
        if key in self._cache:
            return self._cache[key]
        raw = self.store.load(key)
        if raw:
            st = MindState.from_json(raw)
        else:
            st = presets.get(self.cfg.get("default_preset", "healthy"))
        if not st.body:
            st.body = _pbody.new_body(
                sex=str(self.cfg.get("physio_sex", "m")),
                age=float(self.cfg.get("physio_age", 30.0)),
                preset=str(self.cfg.get("physio_preset", "healthy")),
            )
        # 新建或旧存档的身体可能一次都没 step 过，labs/vitals 为空。
        # 不补算的话，第一次 /心理 体检 会出现「体重 0.0kg」「体征未记录」。
        if not (st.body.get("labs") and st.body.get("vitals")):
            self.phys.refresh(st.body)
        self._cache[key] = st
        return st

    def save(self, key: str, st: MindState) -> None:
        self._cache[key] = st
        self.store.save(key, st.to_json(), st.meta.get("preset", ""))

    def reset(self, key: str, preset: Optional[str] = None) -> MindState:
        st = presets.get(preset or self.cfg.get("default_preset", "healthy"))
        st.meta["preset"] = preset or self.cfg.get("default_preset", "healthy")
        # 身体也要重置：换预设等于换一个人，不能让上一具身体的器官损伤留到新角色身上
        st.body = _pbody.new_body(
            sex=str(self.cfg.get("physio_sex", "m")),
            age=float(self.cfg.get("physio_age", 30.0)),
            preset=str(self.cfg.get("physio_preset", "healthy")),
        )
        self.phys.refresh(st.body)
        self.save(key, st)
        self.store.log(key, 0, "reset", {"preset": st.meta["preset"]})
        return st

    def peek(self, key: str):
        st = self.load(key)
        return st, diagnose(st, self.cfg)

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    async def turn(self, key: str, text: str, provider=None) -> TurnResult:
        async with self._lock(key):
            st = self.load(key)
            if not (text or "").strip():
                ap = appraise_fallback("", self.cfg)
            else:
                ap = await self._appraise(st, text, provider)

            ap = self._merge_keyword_nudges(ap, st, text)
            st.meta["crisis"] = bool(ap.get("crisis"))
            if ap.get("crisis"):
                st.meta["crisis_turns"] = int(st.meta.get("crisis_turns", 0)) + 1
            st.meta["last_user"] = (text or "")[:200]
            st.meta["appraisal"] = {k: v for k, v in (ap.get("dims") or {}).items()}

            # 身体先走：这一轮之间过了几个小时，吃喝睡动、环境、生病都在这里发生
            if self.cfg.get("physio_enabled", True):
                phys_out = self.phys.step(st.body)
                if self.cfg.get("physio_couple", True):
                    self.phys.couple(st.body, st)
                st.meta["physio_events"] = (phys_out.get("events") or [])[-8:]
            # 精神侧再走：受身体影响后的神经化学是这一轮的新起点
            self.dyn.step(st, ap)
            dx = diagnose(st, self.cfg)
            update_state(st, dx)

            # 约束压力自然衰减
            st.meta["pressure"] = max(0.0, float(st.meta.get("pressure", 0.0)) - 0.05)

            block = narrative.render_block(st, dx, self.cfg)
            self.save(key, st)
            self.store.log(key, int(st.meta.get("turn", 0)), "turn", {
                "valence": ap.get("valence"),
                "keywords": ap.get("keywords"),
                "src": ap.get("source"),
                "dx": dx.codes(),
                "sev": dx.severity,
                "body": _pbody.summary_line(st.body),
            })
            return TurnResult(state=st, dx=dx, block=block, appraisal=ap)

    # ------------------------------------------------------------------
    async def _appraise(self, st: MindState, text: str, provider) -> Dict[str, Any]:
        """话语 → 心理社会冲击。只有一条主路径：模型抽取。

        拿不到模型（未配置 / 超时 / 输出解析失败）时退到 appraise_fallback：
        只保安全判定，维度全零。不退回词表猜——词表的召回与强度都不足以
        驱动状态，猜错比不猜更伤（见 appraisal.appraise_fallback 的说明）。
        """
        if provider is None:
            return appraise_fallback(text, self.cfg)

        try:
            raw = await asyncio.wait_for(
                self._call_llm(provider, text),
                timeout=float(self.cfg.get("appraisal_timeout", 12)),
            )
            ap = parse_llm_output(raw, text, st)
            if ap:
                if not ap.get("crisis"):
                    # 模型漏判危机时本地补一次：安全判定不能只依赖模型
                    ap["crisis"] = detect_crisis(text)
                return ap
        except Exception:
            pass

        fb = appraise_fallback(text, self.cfg)
        fb["degraded"] = True
        return fb

    async def _call_llm(self, provider, text: str) -> str:
        prompt = EXTRACT_PROMPT.format(text=(text or "")[:1000])
        return await self._chat(provider, prompt, "你是严格输出 JSON 的心理社会刺激编码器，不输出任何解释文字。")

    async def _chat(self, provider, prompt: str, system: str) -> str:
        try:
            resp = await provider.text_chat(prompt=prompt, context=[], system_prompt=system)
        except TypeError:
            resp = await provider.text_chat(prompt=prompt, contexts=[], system_prompt=system)
        return getattr(resp, "completion_text", None) or getattr(resp, "text", "") or ""

    # ------------------------------------------------------------------
    # 量表校准：让模型自己填，得到可核查的锚点
    # ------------------------------------------------------------------
    async def calibrate(self, key: str, provider=None,
                        codes: Optional[List[str]] = None) -> Dict[str, Any]:
        """让模型做量表自评，把分数投影成症状锚。

        与「关键词抽取」是同一模式：模型输出结构化 JSON → 引擎逐条校验 →
        落到量化指标。区别在于量表给的是**刻度**而不是方向。

        投影用向目标靠拢（0.6 权重）而不是直接覆盖：
            · 直接覆盖会被模型操纵（把分数压低就"自愈"了）
            · 纯取下限则量表只会加重，失去校准意义
        """
        st = self.load(key)
        codes = codes or ["SCL-90"]
        out: Dict[str, Any] = {"scales": {}, "applied": 0, "mismatch": []}
        if provider is None:
            out["error"] = "no_provider"
            return out

        for code in codes:
            if code not in scales_mod.SCALES:
                out["scales"][code] = {"ok": False, "reason": "未知量表"}
                continue
            prompt = scales_mod.render_prompt(code)
            system = ("你是正在完成心理量表的当事人，严格按自己此刻的真实状态打分，"
                      "只输出 JSON。")
            try:
                raw = await asyncio.wait_for(
                    self._chat(provider, prompt, system),
                    timeout=float(self.cfg.get("scale_timeout", 40)),
                )
            except Exception as e:
                out["scales"][code] = {"ok": False, "reason": f"调用失败:{type(e).__name__}"}
                continue

            obj = _extract_json(raw)
            items = scales_mod.parse_scores(code, obj)
            if items is None:
                out["scales"][code] = {"ok": False, "reason": "分数解析失败",
                                       "raw": (raw or "")[:200]}
                continue

            total = scales_mod.total_of(code, items)
            norm = scales_mod.normalize(code, total)
            fac = scales_mod.factor_scores(code, items)
            grade = scales_mod.grade(code, total)

            # 投影到症状（向目标靠拢，保留动力学惯性）
            targets = scales_mod.to_symptom_targets(code, items)
            for k, v in targets.items():
                if k not in st.sym:
                    continue
                cur = st.sym[k]
                st.sym[k] = max(0.0, min(1.0, cur + (v - cur) * 0.60))
                if abs(v - cur) >= 0.15:
                    out["applied"] += 1

            # 与当前动力学的不一致检测：这是量表真正的价值——可核查
            cur_sev = float(st.meta.get("last_severity", 0.0)) or 0.0
            scale_sev = norm * 100.0
            if cur_sev > 0 and abs(scale_sev - cur_sev) > 35:
                out["mismatch"].append(
                    f"{code} 自评 {total:.0f} 分（{grade}，折算 {scale_sev:.0f}/100）"
                    f"与动力学严重度 {cur_sev:.0f}/100 相差过大"
                )

            rec = {
                "ok": True, "turn": int(st.meta.get("turn", 0)),
                "total": total, "max": scales_mod.SCALES[code]["max_total"],
                "norm": round(norm, 3), "grade": grade,
                "factors": fac, "n_items": len(items),
                "comment": (obj or {}).get("comment", ""),
            }
            out["scales"][code] = rec
            hist = st.meta.setdefault("scale_history", {})
            hist[code] = rec

            self.store.log(key, int(st.meta.get("turn", 0)), "scale", rec)

        # 量表锚记入 meta，供注入块展示
        if any(v.get("ok") for v in out["scales"].values()):
            st.meta["scale_anchor"] = {
                c: {"total": v["total"], "grade": v["grade"], "norm": v["norm"]}
                for c, v in out["scales"].items() if v.get("ok")
            }
            # 校准会改变症状分布，重新诊断一次
            dx = diagnose(st, self.cfg)
            update_state(st, dx)
            out["dx"] = dx.codes()
            out["severity"] = dx.severity
            self.save(key, st)
        return out

    def _merge_keyword_nudges(self, ap: Dict[str, Any], st: MindState, text: str) -> Dict[str, Any]:
        """关键词 → 具体症状的定向增量。

        模型给出的 domains 是粗粒度激活，这里再按关键词细化到条目，
        两者叠加，既有语义理解又有可解释性。
        """
        nudges = apply_keyword_nudges(ap, st)
        if nudges:
            ap["nudges"] = nudges
            # 立刻小幅作用（当轮可见），长期仍由 dynamics 决定
            for k, v in nudges.items():
                if k in st.sym:
                    st.sym[k] = max(0.0, min(1.0, st.sym[k] + 0.5 * v))
        # 关键词记忆：作为后续妄想的素材
        kws = [k for k in (ap.get("keywords") or []) if k][:6]
        if kws:
            mem = list(st.meta.get("keywords") or [])
            for k in kws:
                if k in mem:
                    mem.remove(k)
            mem = kws + mem
            st.meta["keywords"] = mem[:12]
            st.meta["keywords_turn"] = int(st.meta.get("turn", 0))
        if ap.get("topic"):
            st.meta["topic"] = ap["topic"]
        return ap

    # ------------------------------------------------------------------
    # 回复合规检测
    # ------------------------------------------------------------------
    def observe_reply(self, key: str, reply: str) -> float:
        if not self.cfg.get("compliance_guard", True):
            return 1.0
        st = self.load(key)
        text = (reply or "").strip()
        if not text:
            return 1.0
        dx_list = st.meta.get("last_dx") or []
        has_dx = bool(dx_list)
        # 健康态与病态态的「偏离」定义完全不同：正常人说「我很好」不算泄漏。
        perf = dx_list[0].get("perf", "normal") if has_dx else "normal"

        v = 0.0
        if has_dx:
            for phrase in HEALTHY_LEAKS:
                if phrase in text:
                    v += 0.34
            if len(text) > MAX_LEN.get(perf, 300):
                v += 0.25
            if perf in ("depression", "dysthymia") and text.count("！") + text.count("!") >= 2:
                v += 0.20
            if perf == "catatonia" and len(text) > 30:
                v += 0.4
        else:
            for phrase in NORMAL_LEAKS:
                if phrase in text:
                    v += 0.34
            if len(text) > 160:
                v += 0.25

        score = max(0.0, 1.0 - min(1.0, v))
        st.meta["violations"] = int(st.meta.get("violations", 0)) + (1 if score < 0.7 else 0)
        st.meta["pressure"] = min(1.0, float(st.meta.get("pressure", 0.0)) + (0.18 if score < 0.7 else 0.0))
        prev = float(st.meta.get("compliance_avg", 1.0))
        st.meta["compliance_avg"] = round(0.8 * prev + 0.2 * score, 3)
        self.save(key, st)
        return score

    # ------------------------------------------------------------------
    # 事件 / 药物 / 快进
    # ------------------------------------------------------------------
    EVENTS: Dict[str, Dict[str, Any]] = {
        "失业": {"sym": {"md_worthlessness": 0.18, "ax_worry": 0.15, "md_hopelessness": 0.12},
                 "bio": {"cortisol": 0.10, "serotonin": -0.05}},
        "失恋": {"sym": {"tr_abandonment_fear": 0.25, "md_depressed_mood": 0.15,
                       "pd_emptiness": 0.15},
                 "bio": {"oxytocin": -0.10, "serotonin": -0.07}},
        "被霸凌": {"sym": {"ps_delusion_persecutory": 0.15, "ax_hypervigilance": 0.20,
                        "md_worthlessness": 0.15, "tr_shame": 0.15},
                  "trauma": 0.15, "bio": {"cortisol": 0.12, "norepinephrine": 0.10}},
        "升职": {"sym": {"ma_grandiosity": 0.12, "md_worthlessness": -0.10},
                "bio": {"da_tonic": 0.10, "serotonin": 0.05}},
        "丧亲": {"sym": {"ot_bereavement": 0.30, "tr_grief": 0.25, "md_depressed_mood": 0.18},
                "grief": 0.35, "bio": {"cortisol": 0.10}},
        "创伤": {"sym": {"tr_flashback": 0.25, "tr_intrusion": 0.22, "tr_hyperarousal": 0.20},
                "trauma": 0.30, "bio": {"norepinephrine": 0.15, "cortisol": 0.10}},
        "表扬": {"sym": {"md_worthlessness": -0.10, "ma_grandiosity": 0.05},
                "bio": {"da_tonic": 0.08, "serotonin": 0.04}},
        "陪伴": {"sym": {"tr_abandonment_fear": -0.08, "pd_emptiness": -0.08},
                "bio": {"oxytocin": 0.10, "cortisol": -0.05}},
        "失眠": {"sym": {"sl_insomnia": 0.25, "md_fatigue": 0.15},
                "bio": {"adenosine": 0.15}},
        "戒断": {"sym": {"su_withdrawal": 0.30, "ax_worry": 0.15, "md_depressed_mood": 0.15},
                "bio": {"gaba": -0.10, "da_tonic": -0.08}},
    }

    def inject_event(self, key: str, kind: str) -> str:
        spec = self.EVENTS.get(kind)
        if not spec:
            return "未知事件。可用：" + "、".join(self.EVENTS)
        st = self.load(key)
        for k, v in (spec.get("sym") or {}).items():
            if k in st.sym:
                st.sym[k] = max(0.0, min(1.0, st.sym[k] + v))
        for k, v in (spec.get("bio") or {}).items():
            if k in st.bio:
                st.bio[k] = max(0.0, min(1.0, st.bio[k] + v))
        if spec.get("trauma"):
            st.meta["trauma_load"] = min(1.0, float(st.meta.get("trauma_load", 0.0)) + spec["trauma"])
        if spec.get("grief"):
            st.meta["grief_load"] = min(1.0, float(st.meta.get("grief_load", 0.0)) + spec["grief"])
        self.save(key, st)
        self.store.log(key, int(st.meta.get("turn", 0)), "event", {"kind": kind})
        st.tick()
        dx = diagnose(st, self.cfg)
        update_state(st, dx)
        self.save(key, st)
        return f"已注入事件「{kind}」。当前主诊断：{dx.primary.zh if dx.primary else '未达阈值'}（{dx.severity:.0f}）"

    def add_med(self, key: str, name: str, dose: float = 1.0) -> str:
        drug = pharm.resolve(name)
        if not drug:
            return f"未知药物：{name}。可用：" + "、".join(pharm.DRUGS.keys())
        st = self.load(key)
        st.meta.setdefault("meds", []).append({
            "name": drug, "start_turn": int(st.meta.get("turn", 0)), "dose": float(dose),
        })
        self.save(key, st)
        self.store.log(key, int(st.meta.get("turn", 0)), "med_add", {"drug": drug, "dose": dose})
        spec = pharm.DRUGS[drug]
        prof = pharm.SIDE_PROFILE.get(drug) or {}
        top = sorted(prof.items(), key=lambda kv: -kv[1])[:5]
        sides = "、".join(pharm.SIDE_DEFS[s][0] for s, _ in top if s in pharm.SIDE_DEFS)
        return (f"已给予 {drug}（{spec['class']}），剂量 {dose:g}。"
                f"起效约 {spec['latency']:.0f} 轮。\n"
                f"常见副作用：{sides or '无记录'}\n"
                f"副作用比疗效来得早，通常 2~4 轮就能感觉到；/心理 副作用 看明细。")

    def remove_med(self, key: str, name: str) -> str:
        drug = pharm.resolve(name) or name
        st = self.load(key)
        meds = [m for m in (st.meta.get("meds") or []) if m.get("name") != drug]
        if len(meds) == len(st.meta.get("meds") or []):
            return f"未在服用 {drug}。"
        st.meta["meds"] = meds
        self.save(key, st)
        return f"已停用 {drug}。（注意：骤停可能出现反跳）"

    def fast_forward(self, key: str, n: int = 10) -> str:
        st = self.load(key)
        neutral = {
            "dims": {k: 0.0 for k in
                     ("threat", "rejection", "praise", "control", "intimacy", "chaos",
                      "calm", "help", "hostility", "absurd", "farewell", "medical")},
            "domains": {k: 0.0 for k in DOMAIN_KEYS},
            "keywords": [], "intensity": 0.0, "valence": 0.0, "crisis": False,
        }
        n = max(1, min(500, int(n)))
        for _ in range(n):
            self.phys.step(st.body)
            self.phys.couple(st.body, st)
            self.dyn.step(st, neutral)
        dx = diagnose(st, self.cfg)
        update_state(st, dx)
        self.save(key, st)
        return (f"已快进 {n} 轮。主诊断：{dx.primary.zh if dx.primary else '未达阈值'}"
                f"（{dx.severity:.0f}，慢性化 {dx.chronic:.0%}）\n"
                f"身体：{_pbody.summary_line(st.body)}")

    # ------------------------------------------------------------------
    # 生理侧
    # ------------------------------------------------------------------
    def phys_report(self, key: str, panel: str = "", only_abnormal: bool = False) -> str:
        st = self.load(key)
        panel = (panel or "").strip()
        if panel:
            # PANELS 的 key 是 LABS 的分组名（render_panel 按它取数），
            # 显示名更友好，两个都认，否则用户输入「炎症指标」会查不到。
            alias: Dict[str, str] = {}
            for k, name in _pconst.PANELS:
                alias[k] = k
                alias[name] = k
            alias["生命体征"] = "vitals"
            alias["vitals"] = "vitals"
            target = alias.get(panel)
            if not target:
                return ("未知检查项：" + panel + "。可用："
                        + "、".join(n for _, n in _pconst.PANELS))
            if target == "vitals":
                return _preport.render_vitals(st.body)
            text = _preport.render_panel(st.body, target)
            if not text:
                return f"「{target}」这项暂时没有数据。"
            return text + "\n\n" + _preport.DISCLAIMER
        return _preport.render_full(st.body, only_abnormal=only_abnormal)

    def phys_life(self, key: str) -> str:
        st = self.load(key)
        return _preport.render_life(st.body)

    def phys_log(self, key: str, limit: int = 12) -> str:
        st = self.load(key)
        return _preport.render_log(st.body, limit=limit)

    def phys_med(self, key: str, name: str, dose: float = 1.0) -> str:
        st = self.load(key)
        drug = _pdrugs.resolve(name)
        if not drug:
            return f"药库里没有「{name}」。/心理 找药 <关键词> 可以按药名或类别找。"
        msg = self.phys.add_med(st.body, drug, dose)
        # 先走一天，让药物浓度爬坡，否则服药当刻看不到任何变化
        self.phys.step(st.body, hours=24.0)
        self.save(key, st)
        self.store.log(key, int(st.meta.get("turn", 0)), "phys_med",
                       {"drug": drug, "dose": dose})
        sides = (_pdrugs.DRUGS.get(drug) or {}).get("side") or []
        tail = f"\n常见不良反应：{'、'.join(sides[:5])}" if sides else ""
        return msg + tail

    def phys_stop(self, key: str, name: str) -> str:
        st = self.load(key)
        drug = _pdrugs.resolve(name) or name
        msg = self.phys.remove_med(st.body, drug)
        self.save(key, st)
        return msg

    def phys_find(self, key: str, kw: str) -> str:
        kw = (kw or "").strip()
        if not kw:
            return "用法：/心理 找药 <关键词>（药名或类别）"
        hit = [k for k, v in _pdrugs.DRUGS.items() if kw in k or kw in v["cls"]]
        if not hit:
            return f"没有匹配「{kw}」的药物。"
        parts = [f"{k}（{_pdrugs.DRUGS[k]['cls']}）" for k in hit[:14]]
        more = f"　等 {len(hit)} 种" if len(hit) > 14 else ""
        return "、".join(parts) + more

    def phys_advance(self, key: str, hours: float = 24.0) -> str:
        st = self.load(key)
        hours = max(0.0, min(24.0 * 365, float(hours)))
        # engine.step 内部一次最多走 14 天（保证逐小时循环不至于太长），
        # 这里分段调用，才能支持"推进一个月/一年"
        events: List[str] = []
        left = hours
        while left > 1e-6:
            chunk = min(24.0 * 14, left)
            left -= chunk
            out = self.phys.step(st.body, hours=chunk)
            events.extend(out.get("events") or [])
        self.phys.couple(st.body, st)
        dx = diagnose(st, self.cfg)
        update_state(st, dx)
        self.save(key, st)
        ev = _pconst.events_text(events, limit=6)
        span = f"{hours / 24:.0f} 天" if hours >= 48 else f"{hours:.0f} 小时"
        return (f"已推进 {span}（{_pbody.summary_line(st.body)}）。\n"
                f"主诊断：{dx.primary.zh if dx.primary else '未达阈值'}"
                f"（{dx.severity:.0f}）\n"
                + (f"经过：{ev}" if ev else "这段时间没出什么事。"))

    def phys_set(self, key: str, dim: str, value: str) -> str:
        st = self.load(key)
        dim = (dim or "").strip()
        body = st.body
        for gname, table in (("life", _pconst.LIFE), ("env", _pconst.ENV),
                             ("vitals", _pconst.VITALS)):
            if dim not in table:
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                return f"「{dim}」要填一个数字。"
            if v != v or abs(v) > 1e6:  # NaN / 离谱值直接拒绝
                return f"「{dim}」的取值不合理。"
            body.setdefault(gname, {})[dim] = v
            self.save(key, st)
            self.store.log(key, int(st.meta.get("turn", 0)), "phys_set",
                           {"dim": dim, "value": v})
            return f"已把「{table[dim][0]}」设为 {v:g}。"
        avail = "、".join([f"{k}（{v[0]}）" for k, v in _pconst.LIFE.items()][:8])
        return f"未知维度：{dim}。常用的有：{avail} 等等，共 {len(_pconst.LIFE)} 项。"

    # ------------------------------------------------------------------
    def timeline(self, key: str, limit: int = 15) -> str:
        rows = self.store.events(key, limit)
        if not rows:
            return "暂无记录。"
        lines = []
        for r in rows:
            kind = r["kind"]
            p = r["payload"]
            if kind == "turn":
                kws = "、".join((p or {}).get("keywords") or []) if isinstance(p, dict) else ""
                dx = "/".join((p or {}).get("dx") or []) if isinstance(p, dict) else ""
                lines.append(f"#{r['turn']:<4d} 对话  诊断 {dx or '-'}｜严重度 {p.get('sev', 0):.0f}"
                             + (f"｜关键词 {kws}" if kws else ""))
            elif kind == "event":
                lines.append(f"#{r['turn']:<4d} 事件  {p.get('kind') if isinstance(p, dict) else p}")
            elif kind == "med_add":
                lines.append(f"#{r['turn']:<4d} 用药  {p.get('drug')} ×{p.get('dose')}")
            elif kind == "reset":
                lines.append(f"#{r['turn']:<4d} 重置  预设 {p.get('preset')}")
        return "\n".join(lines)

    def export(self, key: str) -> str:
        st = self.load(key)
        return json.dumps(st.to_dict(), ensure_ascii=False, indent=2)[:6000]
