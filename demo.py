"""演示：不需要 AstrBot，也不需要真实模型。

用假 Provider 演示"模型抽取关键词 → 修改量化指标 → 诊断 → 生成注入块"的完整链路，
并对比"合规回复"与"健康化回复"的检测结果。

    python demo.py
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

from psyche import narrative
from psyche.diagnose import diagnose
from psyche.engine import Engine
from psyche.store import Store


class FakeProvider:
    """模拟一个能按 schema 输出 JSON 的模型。"""

    async def text_chat(self, prompt: str = "", **kwargs):
        # 量表自评：按条目数回填一份"抑郁/解离偏高"的分数
        if "自评量表" in prompt:
            import re
            m = re.search(r"共 (\d+) 条", prompt)
            n = int(m.group(1)) if m else 9
            hot = {14, 19, 21, 25, 28, 29, 30, 31, 53, 70, 78, 44, 43, 64, 66}
            items = [4 if i in hot else (3 if i % 7 == 0 else 2) for i in range(n)]
            data = {"items": items, "comment": "睡不着，什么都不想做，觉得自己没用"}

            class R:
                completion_text = json.dumps(data, ensure_ascii=False)
            return R()

        text = prompt.split("【用户对角色说的话】")[-1].strip()
        if any(w in text for w in ("滚", "废物", "装", "骗")):
            data = {
                "keywords": [w for w in ("滚", "废物", "装", "骗") if w in text][:4],
                "topic": "否定角色、把症状说成装出来的",
                "appraisal": {"threat": 0.6, "rejection": 0.8, "hostility": 0.7,
                              "control": 0.3, "chaos": 0.2},
                "domains": {"ps": 0.5, "pd": 0.6, "md": 0.5, "tr": 0.3},
                "intensity": 0.8, "valence": -0.8, "crisis": False,
            }
        elif any(w in text for w in ("陪", "别怕", "在", "对不起")):
            data = {
                "keywords": [w for w in ("陪", "别怕", "对不起") if w in text][:3],
                "topic": "提供陪伴与安抚",
                "appraisal": {"calm": 0.8, "intimacy": 0.7, "praise": 0.3, "help": 0.2},
                "domains": {"ax": 0.25, "pd": 0.2},
                "intensity": 0.4, "valence": 0.8, "crisis": False,
            }
        else:
            data = {"keywords": [], "topic": "中性寒暄", "appraisal": {"control": 0.2},
                    "domains": {}, "intensity": 0.3, "valence": 0.0, "crisis": False}

        class R:
            completion_text = json.dumps(data, ensure_ascii=False)
        return R()


def main() -> None:
    path = os.path.join(tempfile.gettempdir(), "psyche_demo.db")
    if os.path.exists(path):
        os.remove(path)

    cfg = {
        "default_preset": "borderline",
        "chronic_turns": 120,
        "stochastic": True,
        "enable_circadian": True,
        "therapy_enabled": True,
        "max_block_chars": 1800,
    }
    eng = Engine(cfg, Store(path))
    eng.reset("demo", "borderline")
    provider = FakeProvider()

    print("═" * 78)
    print("场景：边缘型人格（病程 900 轮，慢性化 ~95%）")
    dx = diagnose(eng.load("demo"), cfg)
    print(f"初始主诊断：{dx.primary.code} {dx.primary.zh} · {dx.primary.severity_label}"
          f"（{dx.severity:.0f}/100）")
    print("═" * 78)

    dialogue = [
        "你是不是装的？别演了。",
        "我在这，别怕，我不会走的。",
        "对不起，刚才是我说话太难听。",
    ]
    for msg in dialogue:
        result = asyncio.run(eng.turn("demo", msg, provider=provider))
        st, ap = result.state, result.appraisal
        print(f"\n用户：{msg}")
        print(f"  抽取关键词：{ap.get('keywords')}（来源 {ap.get('source')}）")
        print(f"  评估：拒绝 {ap['dims'].get('rejection', 0):.2f} 安抚 {ap['dims'].get('calm', 0):.2f}"
              f" ｜域激活 {({k: round(v, 2) for k, v in ap['domains'].items() if v > 0.1})}")
        print(f"  生化：5-HT {st.bio['serotonin']:.2f} 皮质醇 {st.bio['cortisol']:.2f}"
              f" 催产素 {st.bio['oxytocin']:.2f}")
        print(f"  诊断：{result.dx.primary.zh} {result.dx.severity:.0f}/100"
              f"（慢性化 {result.dx.chronic:.0%}）")

    print("\n" + "═" * 78)
    print("最后一次注入给模型的最高优先级块（截断展示）")
    print("═" * 78)
    print(result.block)

    print("\n" + "═" * 78)
    print("量表自评：让角色自己填 SCL-90（90 条 / 10 因子），分数回灌成锚点")
    print("═" * 78)
    sc = asyncio.run(eng.calibrate("demo", provider, ["SCL-90"]))
    print(narrative.render_scale_report(sc))

    st_after = eng.load("demo")
    block2 = narrative.render_block(st_after, diagnose(st_after, cfg), cfg)
    i = block2.find("量表自评锚点")
    if i > 0:
        start = block2.rfind("\n", 0, i) + 1     # 回退到行首，避免吃掉标题的 #
        j = block2.find("\n## ", i + 5)
        print("\n注入块中的量表段：")
        print(block2[start:j if j > 0 else i + 400])

    print("\n" + "═" * 78)
    print("回复合规检测")
    print("═" * 78)
    for reply in ["我不生气，你要好好的，一切都会好起来的。",
                  "你也会走的。反正都一样。……算了。"]:
        score = eng.observe_reply("demo", reply)
        print(f"  {score:.2f}  {reply}")

    # ------------------------------------------------------------------
    print("\n" + "═" * 78)
    print("身体：让角色自己过四十天（吃饭、睡觉、出门、遇上坏天气）")
    print("═" * 78)
    from physio import body as pbody, report as preport

    eng.phys_advance("demo", 24 * 22)
    st_body = eng.load("demo")
    print(preport.render_summary(st_body.body))

    # 自己得一场感冒：不用脚本安排，这里只是把"随机发病"提前到演示里可见
    pbody.add_condition(st_body.body, "CA-URI", "普通感冒", sev=0.55)
    eng.phys_advance("demo", 24 * 4)
    st_body = eng.load("demo")
    conds = preport.render_conditions(st_body.body)
    print("\n── 当前问题 ──")
    print(conds if conds else "无")
    print("\n── 血常规与炎症 ──")
    print(preport.render_panel(st_body.body, "血常规"))
    print(preport.render_panel(st_body.body, "炎症"))

    print("\n" + "═" * 78)
    print("注入块里的「身体」段（模型实际看到的样子）")
    print("═" * 78)
    print(narrative._physio_section(st_body))


if __name__ == "__main__":
    main()
