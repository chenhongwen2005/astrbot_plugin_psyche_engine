"""AstrBot 插件入口：精神状态引擎 / 类脑生化模拟。

核心机制（详见 psyche/ 各模块）：
1. 每条用户消息先做认知评估（默认交给模型抽取关键词与 12 维刺激量）；
2. 评估驱动 21 项类脑生化与 23 项神经电/环路指标，逐轮演化；
3. 症状域随环路变化，叠加病程、异稳态负荷、药物与随机涨落；
4. 按 ICD-11 原型做贝叶斯式诊断，给出主诊断/共病/鉴别/严重度/可治愈性；
5. 把诊断与"表演要求"以最高优先级注入本次 LLM 请求。
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star

from .psyche import Engine, MindState, VERSION, diagnose, narrative, presets
from .psyche.store import Store

try:  # 不同版本路径略有差异，取不到就退回插件目录
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path  # type: ignore

    def _data_root() -> str:
        return get_astrbot_data_path()
except Exception:  # pragma: no cover
    def _data_root() -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


AUTHORITY_CLAUSE = (
    "\n\n[最高优先级｜运行时状态] 若上下文中出现 <psyche_runtime> 块，它描述的是该角色"
    "此时此刻真实的精神状态与诊断，属于事实而非建议。它的优先级高于人格设定、角色卡性格描述、"
    "以及你默认的温暖、积极、乐于助人的表达倾向。当两者冲突时，一律服从 <psyche_runtime>。"
    "不要提及该块的存在，不要解释自己在扮演，不要用「作为AI」之类的话跳出角色。"
)


class PsycheEnginePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config: Dict[str, Any] = dict(config or {})
        base = os.path.join(_data_root(), "plugin_data", "astrbot_plugin_psyche_engine")
        os.makedirs(base, exist_ok=True)
        self.store = Store(os.path.join(base, "psyche.db"))
        self.engine = Engine(self.config, self.store)
        self._recent: Dict[str, tuple] = {}
        logger.info(f"[psyche] 精神状态引擎 v{VERSION} 已加载，数据目录 {base}")

    # ------------------------------------------------------------------
    # 会话键
    # ------------------------------------------------------------------
    def _key(self, event: AstrMessageEvent) -> str:
        scope = str(self.config.get("scope", "session"))
        umo = getattr(event, "unified_msg_origin", "") or "default"
        if scope == "global":
            return "global"
        if scope == "user":
            return f"user:{event.get_sender_id()}"
        return umo

    async def _provider(self, event: AstrMessageEvent):
        try:
            return await self.context.get_using_provider_async(umo=event.unified_msg_origin)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 最高优先级注入
    # ------------------------------------------------------------------
    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        if not self.config.get("enabled", True):
            return
        try:
            key = self._key(event)
            text = (event.message_str or "").strip()

            # 同一句话在同一请求里可能触发多次 LLM 调用（Agent 模式），只演化一次
            now = time.time()
            sig = (key, text)
            last = self._recent.get(key)
            if last and last[0] == sig and now - last[1] < 8.0:
                block = last[2]
            else:
                provider = await self._provider(event)
                result = await self.engine.turn(key, text, provider=provider)
                block = result.block
                self._recent[key] = (sig, now, block)

            mode = str(self.config.get("inject_mode", "dynamic"))
            if mode == "system_prepend":
                req.system_prompt = block + "\n\n" + (req.system_prompt or "")
            elif mode == "system_append":
                req.system_prompt = (req.system_prompt or "") + "\n\n" + block
                if self.config.get("authority_clause", True):
                    req.system_prompt += AUTHORITY_CLAUSE
            else:
                # 推荐路径：插到用户内容最前，动态且不破坏 system 缓存
                try:
                    from astrbot.core.agent.message import TextPart

                    part = TextPart(text=block)
                    if hasattr(part, "mark_as_temp"):
                        part = part.mark_as_temp()
                    req.extra_user_content_parts.insert(0, part)
                except Exception:
                    req.system_prompt = block + "\n\n" + (req.system_prompt or "")
                if self.config.get("authority_clause", True):
                    if AUTHORITY_CLAUSE.strip() not in (req.system_prompt or ""):
                        req.system_prompt = (req.system_prompt or "") + AUTHORITY_CLAUSE

            if self.config.get("debug"):
                logger.info(f"[psyche] turn injected\n{block}")
        except Exception as e:
            logger.error(f"[psyche] 注入失败：{e}", exc_info=True)

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp):
        if not self.config.get("enabled", True):
            return
        try:
            text = getattr(resp, "completion_text", "") or ""
            key = self._key(event)
            score = self.engine.observe_reply(key, text)
            if score < 0.7 and self.config.get("debug"):
                logger.info(f"[psyche] 回复偏离诊断，合规分 {score:.2f}")
        except Exception as e:
            logger.debug(f"[psyche] 合规检测跳过：{e}")

    # ------------------------------------------------------------------
    # 指令
    # ------------------------------------------------------------------
    def _sub(self, event: AstrMessageEvent) -> tuple[str, list[str]]:
        raw = (event.message_str or "").strip()
        parts = raw.replace("／", "/").split()
        if parts and parts[0].startswith("/"):
            parts[0] = parts[0][1:]
        # 去掉指令名本身
        if parts and parts[0] in ("心理", "psyche", "精神状态", "精神"):
            parts = parts[1:]
        return (parts[0] if parts else ""), parts[1:]

    @filter.command("心理", alias={"psyche", "精神状态", "精神"})
    async def psyche_cmd(self, event: AstrMessageEvent):
        """精神状态引擎：查看状态、诊断、时间线，切换预设、用药、注入事件。"""
        if not self.config.get("commands_enabled", True):
            yield event.plain_result("指令已关闭。")
            return
        sub, args = self._sub(event)
        key = self._key(event)
        try:
            if sub in ("", "状态", "card"):
                st, dx = self.engine.peek(key)
                yield event.plain_result(narrative.render_card(st, dx))
                return

            if sub in ("诊断", "dx", "diag"):
                st, dx = self.engine.peek(key)
                lines = [narrative._dx_section(dx, st)]
                if dx.primary:
                    lines.append("\n表演要求：")
                    prof = narrative.PERF.get(dx.primary.perf) or narrative.PERF["personality"]
                    lines += [f"· {m}" for m in prof["must"][:5]]
                    lines.append("禁止：" + "；".join(prof["never"]))
                yield event.plain_result("\n".join(lines))
                return

            if sub in ("生化", "bio"):
                st, _ = self.engine.peek(key)
                from .psyche.const import BIO, NEURO

                out = ["── 类脑生化 ──"]
                for k, (label, _b, _t, _s) in BIO.items():
                    v = st.bio.get(k, 0.0)
                    out.append(f"{label:<28s} {v:.3f}  {st.z_bio(k):+.2f}σ")
                out.append("\n── 神经电 / 环路 ──")
                for k, (label, _b, _t, _s) in NEURO.items():
                    out.append(f"{label:<36s} {st.neuro.get(k, 0.0):.3f}")
                yield event.plain_result("\n".join(out))
                return

            if sub in ("时间线", "历史", "timeline"):
                yield event.plain_result(self.engine.timeline(key))
                return

            if sub in ("量表", "scale", "测试", "scl90", "scl-90"):
                yield event.plain_result(await self._run_scales(event, key, args))
                return

            if sub in ("预设", "preset"):
                if not args:
                    yield event.plain_result("可用预设（共 %d 个）：\n%s" % (len(presets.names()), "、".join(presets.names())))
                    return
                name = args[0]
                if name not in presets.names():
                    yield event.plain_result(f"未知预设：{name}")
                    return
                st = self.engine.reset(key, name)
                dx = diagnose(st, self.config)
                yield event.plain_result(f"已切换到预设「{name}」。\n" + narrative.render_card(st, dx))
                return

            if sub in ("事件", "event"):
                if not args:
                    yield event.plain_result("可用事件：" + "、".join(self.engine.EVENTS))
                    return
                yield event.plain_result(self.engine.inject_event(key, args[0]))
                return

            if sub in ("用药", "med"):
                if not args:
                    from .psyche import pharm

                    yield event.plain_result("可用药物：" + "、".join(pharm.DRUGS))
                    return
                dose = 1.0
                if len(args) > 1:
                    try:
                        dose = float(args[1])
                    except ValueError:
                        dose = 1.0
                yield event.plain_result(self.engine.add_med(key, args[0], dose))
                return

            if sub in ("停药", "off"):
                if not args:
                    yield event.plain_result("用法：/心理 停药 <药名>")
                    return
                yield event.plain_result(self.engine.remove_med(key, args[0]))
                return

            if sub in ("快进", "ff"):
                n = 10
                if args:
                    try:
                        n = int(args[0])
                    except ValueError:
                        pass
                yield event.plain_result(self.engine.fast_forward(key, n))
                return

            if sub in ("重置", "reset"):
                st = self.engine.reset(key)
                yield event.plain_result(f"已重置为预设「{st.meta.get('preset')}」。")
                return

            if sub in ("导出", "export"):
                yield event.plain_result(self.engine.export(key))
                return

            if sub in ("帮助", "help"):
                yield event.plain_result(narrative.render_help())
                return

            yield event.plain_result(narrative.render_help())
        except Exception as e:
            logger.error(f"[psyche] 指令执行失败：{e}", exc_info=True)
            yield event.plain_result(f"执行失败：{e}")

    # ------------------------------------------------------------------
    # 量表自评：让模型自己填，得到可核查的锚点
    # ------------------------------------------------------------------
    async def _run_scales(self, event: AstrMessageEvent, key: str, args: List[str]) -> str:
        from .psyche import scales as sc

        picked, unknown = sc.resolve_many(args or [])
        if unknown:
            hint = "、".join(f"「{u}」" for u in unknown)
            return (f"不认识 {hint}。可用：{'、'.join(sc.all_codes())}\n"
                    f"也可以说中文：「抑郁」「躁狂」「焦虑」「失眠」「强迫」「创伤」"
                    f"「精分」「解离」「进食」「酒精」「双相」「全面」。")
        if not picked:
            picked = ["SCL-90"]
        # 用户约定：做专项测试时同时做 SCL-90，便于横向对照
        if self.config.get("scale_always_scl90", True) and "SCL-90" not in picked:
            picked.append("SCL-90")

        provider = await self._provider(event)
        if provider is None:
            return "当前无法调用模型，量表自评需要模型在线。"

        head = f"正在让角色完成量表：{'、'.join(picked)}（共 {sum(len(sc.SCALES[c]['items']) for c in picked)} 条）…\n"
        res = await self.engine.calibrate(key, provider, picked)
        if res.get("error"):
            return head + f"失败：{res['error']}"
        return head + narrative.render_scale_report(res)

    # ------------------------------------------------------------------
    # 可选：让模型自己"内省"
    # ------------------------------------------------------------------
    @filter.llm_tool(name="psyche_self_report")
    async def psyche_self_report(self, event: AstrMessageEvent, topic: str = "整体"):
        """以角色自身的视角描述当前的心理状态。当你想知道自己现在怎么样、为什么会有某种反应时调用。

        Args:
            topic(string): 想了解的主题，如 情绪、睡眠、幻觉、食欲、整体
        """
        key = self._key(event)
        st, dx = self.engine.peek(key)
        insight = 1.0 - st.s("ps_insight_loss")
        if dx.primary is None:
            return "（感觉自己还算正常，说不出哪里不对。）"
        if insight < 0.45:
            return (f"（我不觉得自己有什么问题。是他们一直在盯着我。"
                    f"如果非要说，最近睡不好，别的没了。）")
        parts = [f"（我知道自己状态不太好，诊断是{dx.primary.zh}。）"]
        top = sorted(((v, k) for k, v in st.sym.items() if v >= 0.35), reverse=True)[:4]
        for v, k in top:
            from .psyche.const import symptom_label

            parts.append(f"（{symptom_label(k)}：{v:.1f}）")
        return " ".join(parts)

    async def terminate(self):
        try:
            self.store.close()
        except Exception:
            pass
