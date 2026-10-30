"""上架前冒烟测试：在没有 AstrBot 运行时的机器上，验证插件能被加载并跑通注入链路。

为什么需要这个文件：
    其余测试都只测 ``psyche/`` 里的纯逻辑，从不 import ``main.py``。
    而插件"一装就崩"的原因几乎全在 main.py 与 AstrBot 的接口层——
    属性名写错、API 字段不存在、装饰器签名不符。这些只能靠真的 import 一遍才能发现。

做法：
    用 ``tests/_stub/`` 里的最小 astrbot 包顶替真身，然后把插件当作包导入，
    实例化、跑一轮 on_llm_request、跑几个指令、跑一次 llm_tool。

注意：
    stub 只声明插件用到的符号，不模拟行为；它能证明「接口对得上」，
    不能证明「在真 AstrBot 里效果对」。
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                 # 插件目录
PARENT = os.path.dirname(ROOT)               # 插件目录的父目录
PLUGIN_PKG = os.path.basename(ROOT)

sys.path.insert(0, os.path.join(HERE, "_stub"))
sys.path.insert(0, PARENT)


def _load():
    """把插件当包导入，返回 (module, plugin_class, stub 模块们)。"""
    mod = importlib.import_module(PLUGIN_PKG + ".main")
    ev_mod = importlib.import_module("astrbot.api.event")
    pr_mod = importlib.import_module("astrbot.api.provider")
    st_mod = importlib.import_module("astrbot.api.star")
    return mod, ev_mod, pr_mod, st_mod


def test_imports_and_instantiates() -> None:
    mod, ev_mod, _pr, st_mod = _load()
    assert hasattr(mod, "PsycheEnginePlugin"), "缺少插件类 PsycheEnginePlugin"
    assert hasattr(mod, "VERSION"), "缺少 VERSION"

    plugin = mod.PsycheEnginePlugin(st_mod.Context(), {})
    assert plugin.store is not None and plugin.engine is not None
    assert hasattr(plugin, "on_llm_request")
    assert hasattr(plugin, "on_llm_response")
    assert hasattr(plugin, "psyche_cmd")
    assert hasattr(plugin, "psyche_self_report")
    print(f"[ok] 插件可导入并实例化（v{mod.VERSION}）")


def test_inject_dynamic() -> None:
    mod, ev_mod, pr_mod, st_mod = _load()
    plugin = mod.PsycheEnginePlugin(st_mod.Context(), {})

    ev = ev_mod.AstrMessageEvent("他们都在背后议论我，我睡不着", umo="test:FriendMessage:1")
    req = pr_mod.ProviderRequest(prompt=ev.message_str, system_prompt="你是一个助手。")
    asyncio.run(plugin.on_llm_request(ev, req))

    assert req.extra_user_content_parts, "dynamic 模式没有插入 extra_user_content_parts"
    part = req.extra_user_content_parts[0]
    assert getattr(part, "text", ""), "插入的 part 没有 text"
    assert "<psyche_runtime" in part.text, "注入块缺少 <psyche_runtime> 根标签"
    assert getattr(part, "_no_save", False), \
        "注入块没有标记 _no_save（会写进对话历史，污染上下文与提示词缓存）"
    assert "最高优先级" in (req.system_prompt or ""), "缺少常驻权威声明"
    print(f"[ok] dynamic 注入（块 {len(part.text)} 字，已 mark_as_temp）")


def test_inject_system_modes() -> None:
    mod, ev_mod, pr_mod, st_mod = _load()
    for mode in ("system_prepend", "system_append"):
        plugin = mod.PsycheEnginePlugin(st_mod.Context(), {"inject_mode": mode})
        ev = ev_mod.AstrMessageEvent("最近很累", umo=f"test:FriendMessage:{mode}")
        req = pr_mod.ProviderRequest(prompt=ev.message_str, system_prompt="原始系统提示")
        asyncio.run(plugin.on_llm_request(ev, req))
        assert "psyche_runtime" in req.system_prompt, f"{mode} 没有写进 system_prompt"
        assert "原始系统提示" in req.system_prompt, f"{mode} 把原有 system_prompt 覆盖掉了"
        assert not req.extra_user_content_parts, f"{mode} 不该再插 extra_user_content_parts"
    print("[ok] system_prepend / system_append 两种模式均保留原有 system_prompt")


def test_enabled_switch_and_dedup() -> None:
    mod, ev_mod, pr_mod, st_mod = _load()

    # 总开关关闭时不应注入任何东西
    plugin = mod.PsycheEnginePlugin(st_mod.Context(), {"enabled": False})
    ev = ev_mod.AstrMessageEvent("你好", umo="test:FriendMessage:off")
    req = pr_mod.ProviderRequest(prompt="你好")
    asyncio.run(plugin.on_llm_request(ev, req))
    assert not req.extra_user_content_parts and not req.system_prompt

    # 同一句话连续两次请求（Agent 模式会这样）只应演化一次
    plugin2 = mod.PsycheEnginePlugin(st_mod.Context(), {})
    ev2 = ev_mod.AstrMessageEvent("你好", umo="test:FriendMessage:dup")
    turns = []
    for _ in range(2):
        req2 = pr_mod.ProviderRequest(prompt="你好")
        asyncio.run(plugin2.on_llm_request(ev2, req2))
        st = plugin2.engine.load(plugin2._key(ev2))
        turns.append(int(st.meta.get("turn", 0)))
    assert turns[0] == turns[1], f"同一句话在同一请求内被重复演化：{turns}"
    print(f"[ok] 总开关生效；同句去重生效（turn 稳定在 {turns[0]}）")


def test_response_and_commands() -> None:
    mod, ev_mod, _pr, st_mod = _load()
    plugin = mod.PsycheEnginePlugin(st_mod.Context(), {})

    class _Resp:
        completion_text = "我不生气，你要好好的，一切都会好起来的。"

    ev = ev_mod.AstrMessageEvent("我很难受", umo="test:FriendMessage:cmd")
    asyncio.run(plugin.on_llm_request(ev, importlib.import_module("astrbot.api.provider").ProviderRequest(prompt="我很难受")))
    asyncio.run(plugin.on_llm_response(ev, _Resp()))

    async def _collect(msg: str) -> list[str]:
        e = ev_mod.AstrMessageEvent(msg, umo="test:FriendMessage:cmd")
        out = []
        async for r in plugin.psyche_cmd(e):
            out.append(r[1] if isinstance(r, tuple) else str(r))
        return out

    for cmd in ("/心理", "/心理 诊断", "/心理 生化", "/心理 预设", "/心理 时间线"):
        lines = asyncio.run(_collect(cmd))
        assert lines and isinstance(lines[0], str) and lines[0].strip(), f"{cmd} 没有输出"
        assert "Traceback" not in lines[0], f"{cmd} 抛异常了"

    # 未知子指令与未知预设不应崩
    for cmd in ("/心理 不存在的子指令", "/心理 预设 不存在的预设"):
        lines = asyncio.run(_collect(cmd))
        assert lines and lines[0].strip(), f"{cmd} 空输出"

    # llm_tool：内省工具
    text = asyncio.run(plugin.psyche_self_report(ev, topic="整体"))
    assert isinstance(text, str) and text.strip()
    print(f"[ok] 指令与内省工具可用（{len(text)} 字）")


def test_physio_commands() -> None:
    """身体侧指令：每条都要有输出、不抛异常，且体检要分条发。"""
    mod, ev_mod, _pr, st_mod = _load()
    plugin = mod.PsycheEnginePlugin(st_mod.Context(), {"physio_hours_per_turn": 24})

    async def _collect(msg: str) -> list[str]:
        e = ev_mod.AstrMessageEvent(msg, umo="test:FriendMessage:phys")
        out = []
        async for r in plugin.psyche_cmd(e):
            out.append(r[1] if isinstance(r, tuple) else str(r))
        return out

    # 全新会话的第一句就是体检：此时身体一次都没推进过，化验单不能是空的
    async def _fresh(msg: str) -> list[str]:
        e = ev_mod.AstrMessageEvent(msg, umo="test:FriendMessage:physfresh")
        out = []
        async for r in plugin.psyche_cmd(e):
            out.append(r[1] if isinstance(r, tuple) else str(r))
        return out

    first = "".join(asyncio.run(_fresh("/心理 体检")))
    for bad in ("体重 0.0kg", "BMI 0.0", "未记录"):
        assert bad not in first, f"首句体检出现「{bad}」"

    # 先让身体过几天，才有东西可看
    asyncio.run(_collect("/心理 推进 72"))

    simple = ["/心理 生理", "/心理 生活", "/心理 日子", "/心理 体检 血常规",
              "/心理 体检 异常", "/心理 找药 他汀", "/心理 设置 sleep_h 5.5",
              "/心理 设置 不存在的维度 1", "/心理 服药 不存在的药"]
    for cmd in simple:
        lines = asyncio.run(_collect(cmd))
        assert lines and lines[0].strip(), f"{cmd} 没有输出"
        assert "Traceback" not in lines[0], f"{cmd} 抛异常"
        assert "执行失败" not in lines[0], f"{cmd} 报错：{lines[0][:80]}"

    # 服药 → 停药 闭环
    asyncio.run(_collect("/心理 服药 奥美拉唑"))
    out = asyncio.run(_collect("/心理 停服 奥美拉唑"))
    assert "已停用" in out[0], f"停服未生效：{out[0][:80]}"

    # 完整体检必然超长，必须切成多条，且每条都带序号
    parts = asyncio.run(_collect("/心理 体检"))
    assert len(parts) >= 2, f"完整体检没有分条（{len(parts)} 条）"
    assert all(len(p) <= 2000 for p in parts), "分条后单条仍然过长"
    assert parts[0].startswith("（1/"), "分条缺少序号"
    assert any("参考" in p for p in parts), "分条后丢了参考区间"
    print(f"[ok] 身体侧指令可用（体检切成 {len(parts)} 条，单条 ≤ "
          f"{max(len(p) for p in parts)} 字）")


def test_requirements_declared() -> None:
    """市场安装靠 requirements.txt 装依赖，文件必须存在（哪怕为空）。"""
    path = os.path.join(ROOT, "requirements.txt")
    assert os.path.exists(path), "缺少 requirements.txt"
    body = open(path, encoding="utf-8").read()
    assert "requests" not in body, "开发原则禁止使用 requests"
    print("[ok] requirements.txt 存在且未引入 requests")


# 官方文档列出的合法平台适配器（metadata.yaml 的 support_platforms）
_LEGAL_PLATFORMS = {
    "aiocqhttp", "qq_official", "qq_official_webhook", "telegram", "wecom",
    "wecom_ai_bot", "lark", "dingtalk", "discord", "slack", "kook",
    "vocechat", "weixin_official_account", "weixin_oc", "satori",
    "misskey", "line", "matrix", "mattermost",
}


def test_metadata_consistency() -> None:
    """metadata.yaml 与代码保持一致——这是市场展示和版本判定的唯一来源。"""
    import re

    text = open(os.path.join(ROOT, "metadata.yaml"), encoding="utf-8").read()

    def field(key: str) -> str:
        m = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE)
        assert m, f"metadata.yaml 缺少 {key}"
        return m.group(1).strip().strip('"').strip("'")

    def block_list(key: str) -> list[str]:
        m = re.search(rf"^{key}:\s*$\n((?:\s+-\s*.+\n)+)", text, re.MULTILINE)
        if not m:
            return []
        return [ln.strip().lstrip("-").strip() for ln in m.group(1).splitlines() if ln.strip()]

    mod = sys.modules.get(PLUGIN_PKG + ".main") or importlib.import_module(PLUGIN_PKG + ".psyche")
    version = importlib.import_module(PLUGIN_PKG + ".psyche.const").VERSION

    assert field("version") == version, (
        f"metadata.yaml 版本 {field('version')} 与 psyche/const.py 的 VERSION {version} 不一致")
    assert field("name") == PLUGIN_PKG, f"metadata name {field('name')} 与目录名 {PLUGIN_PKG} 不一致"
    assert field("name").startswith("astrbot_plugin_"), "name 必须以 astrbot_plugin_ 开头"
    assert field("name").islower(), "name 必须全小写"
    assert " " not in field("name"), "name 不能含空格"
    assert field("repo").startswith("https://github.com/"), "repo 必须是 GitHub 仓库地址"

    bad = [p for p in block_list("support_platforms") if p not in _LEGAL_PLATFORMS]
    assert not bad, f"support_platforms 含非法适配器名：{bad}"
    assert "不是医疗器械" in text, "desc 缺少非医疗器械声明（上架审核关注点）"
    print(f"[ok] metadata 一致性（v{version}，{len(block_list('support_platforms'))} 个平台均合法）")


if __name__ == "__main__":
    test_imports_and_instantiates()
    test_inject_dynamic()
    test_inject_system_modes()
    test_enabled_switch_and_dedup()
    test_response_and_commands()
    test_physio_commands()
    test_requirements_declared()
    test_metadata_consistency()
    print("\n冒烟测试全部通过。")
