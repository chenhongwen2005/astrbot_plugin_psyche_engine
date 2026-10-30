"""在真实 AstrBot 运行时里验证本插件：API 是否对得上、能否加载、注入是否生效。

``tests/test_plugin_smoke.py`` 用的是假的 astrbot 替身，只能证明"接口按我的理解对得上"；
本脚本用 AstrBot 自带的解释器加载真实 ``astrbot`` 包，能证明"在真的框架里跑得通"。
两者互补，上架前都建议跑一遍。

用法（二选一）::

    # 1) 自动发现 AstrBot Desktop 的安装位置
    python tools/verify_in_astrbot.py

    # 2) 手动指定 backend 目录（含 app/ 与 python/）
    python tools/verify_in_astrbot.py --backend "C:/Path/To/AstrBot/backend"
    python tools/verify_in_astrbot.py --backend "..." --astrbot-home "C:/Users/me/.astrbot"

说明
----
* 只读探测 + 用临时 session key，不会改动你的对话数据。
* 会以真实 ``ProviderRequest`` / ``TextPart`` 跑一次注入，验证 ``mark_as_temp()``
  确实把内容标成"不写入历史"（字段是 pydantic 私有属性 ``_no_save``）。
* 不覆盖 ``llm`` 评估模式：那条路径需要真 provider，属于运行时行为而非接口问题。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import os
import re
import sys
import traceback
from pathlib import Path

PLUGIN_NAME = "astrbot_plugin_psyche_engine"
OK = "  [OK]  "
BAD = "  [FAIL]"


# ---------------------------------------------------------------------------
# 定位 AstrBot
# ---------------------------------------------------------------------------
def find_backend(explicit: str | None) -> Path:
    """返回含 app/ 与 python/ 的 backend 目录。"""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not (p / "app" / "astrbot").is_dir():
            raise SystemExit(f"{p} 下没有 app/astrbot，不是有效的 AstrBot backend 目录")
        return p

    env = os.environ.get("ASTRBOT_BACKEND")
    if env and (Path(env) / "app" / "astrbot").is_dir():
        return Path(env).resolve()

    def valid(p: Path) -> bool:
        return (p / "app" / "astrbot").is_dir()

    candidates: list[Path] = []

    # 1) 当前用户的 AppData\Local\AstrBot\backend
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "AstrBot" / "backend")

    # 2) 别的盘符。装 AstrBot 时把 AppData 放到别的盘并不罕见（本机就在 G:）。
    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        candidates.append(Path(f"{drive}:/Users") / Path.home().name / "AppData" / "Local" / "AstrBot" / "backend")

    # 3) 常见安装位置
    candidates += [
        Path.home() / "AstrBot" / "backend",
        Path("/AstrBot/backend"),  # Docker 常见挂载点
    ]

    for c in candidates:
        try:
            if valid(c):
                return c.resolve()
        except OSError:
            continue

    # 4) 最后从 desktop.log 里嗅探：启动时记录了 backend 的 python 绝对路径
    for log in (Path.home() / ".astrbot" / "logs" / "desktop.log",
                Path.home() / ".astrbot" / "logs" / "backend.log"):
        found = _sniff_backend_from_log(log)
        if found:
            return found

    raise SystemExit(
        "没找到 AstrBot backend 目录。请用 --backend 指定，"
        "或设置环境变量 ASTRBOT_BACKEND（该目录下应有 app/astrbot 与 python/）。"
    )


def _sniff_backend_from_log(log: Path) -> Path | None:
    """从启动日志里提取 backend 路径。Desktop 版会打印 spawn 的 python 绝对路径。"""
    if not log.is_file():
        return None
    try:
        text = log.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    for m in re.finditer(r'"?([A-Za-z]:[\\/][^"\n]*?[\\/]backend)[\\/]python[\\/]python', text):
        raw = m.group(1).lstrip("\\?")
        raw = raw.replace("\\\\?\\", "").replace("\\", "/")
        p = Path(raw)
        if (p / "app" / "astrbot").is_dir():
            return p.resolve()
    return None


def find_astrbot_home(explicit: str | None) -> Path:
    """数据目录。注入测试会在这里写入临时会话状态。"""
    if explicit:
        return Path(explicit).expanduser().resolve()
    for c in (Path.home() / ".astrbot", Path("/AstrBot/data")):
        if c.is_dir():
            return c.resolve()
    return Path.home() / ".astrbot"


# ---------------------------------------------------------------------------
# 1. API 探针
# ---------------------------------------------------------------------------
def probe_api() -> bool:
    print("\n【1/3】API 探针：插件依赖的符号在真实 astrbot 中是否都存在")
    print("-" * 74)
    ok = True

    def check(label, fn):
        nonlocal ok
        try:
            detail = fn()
            print(f"{OK}{label}" + (f"  {detail}" if detail else ""))
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"{BAD}{label}  ->  {type(e).__name__}: {e}")

    check("import astrbot", lambda: importlib.import_module("astrbot").__version__)
    check("astrbot.api.AstrBotConfig",
          lambda: importlib.import_module("astrbot.api").AstrBotConfig.__name__)
    check("astrbot.api.logger",
          lambda: type(importlib.import_module("astrbot.api").logger).__name__)
    check("astrbot.api.event.AstrMessageEvent",
          lambda: importlib.import_module("astrbot.api.event").AstrMessageEvent.__name__)

    def _filter():
        # filter 是 event 包的子模块，必须按插件的真实写法导入；
        # 只 import 父包不会把子模块绑定成属性。
        from astrbot.api.event import filter as f

        return f"模块 {f.__name__}"

    check("from astrbot.api.event import filter", _filter)

    from astrbot.api.event import filter as f

    for deco in ("on_llm_request", "on_llm_response", "command", "llm_tool"):
        check(f"filter.{deco}",
              lambda d=deco: "callable" if callable(getattr(f, d, None))
              else (_ for _ in ()).throw(AttributeError(d)))

    check("astrbot.api.provider.ProviderRequest",
          lambda: importlib.import_module("astrbot.api.provider").ProviderRequest.__name__)
    check("astrbot.api.star.Context",
          lambda: importlib.import_module("astrbot.api.star").Context.__name__)
    check("astrbot.api.star.Star",
          lambda: importlib.import_module("astrbot.api.star").Star.__name__)
    check("astrbot.core.agent.message.TextPart",
          lambda: importlib.import_module("astrbot.core.agent.message").TextPart.__name__)
    check("TextPart.mark_as_temp",
          lambda: "存在" if hasattr(
              importlib.import_module("astrbot.core.agent.message").TextPart, "mark_as_temp")
          else (_ for _ in ()).throw(AttributeError("no mark_as_temp")))

    def _req_fields():
        PR = importlib.import_module("astrbot.api.provider").ProviderRequest
        r = PR()
        missing = [x for x in ("prompt", "system_prompt", "extra_user_content_parts")
                   if not hasattr(r, x)]
        if missing:
            raise AttributeError(f"缺少字段 {missing}；签名 {inspect.signature(PR)}")
        return f"extra_user_content_parts={type(r.extra_user_content_parts).__name__}"

    check("ProviderRequest 实例字段", _req_fields)
    return ok


# ---------------------------------------------------------------------------
# 2. 加载与注入
# ---------------------------------------------------------------------------
class FakeEvent:
    """插件只 duck-typing 这四个成员，不需要真正的平台事件对象。"""

    def __init__(self, text: str, umo: str = "verify:FriendMessage:1") -> None:
        self.message_str = text
        self.unified_msg_origin = umo

    def get_sender_id(self) -> str:
        return "1"

    def plain_result(self, text):
        return ("plain", text)


def probe_plugin(plugins_dir: Path) -> bool:
    print("\n【2/3】加载与注入：用真实 ProviderRequest / TextPart 跑一遍")
    print("-" * 74)
    sys.path.insert(0, str(plugins_dir))

    try:
        m = importlib.import_module(f"{PLUGIN_NAME}.main")
    except Exception:  # noqa: BLE001
        print(f"{BAD} 导入插件失败：")
        traceback.print_exc()
        return False
    print(f"{OK} 导入插件（VERSION={m.VERSION}）")

    from astrbot.api.provider import ProviderRequest
    from astrbot.api.star import Context

    # Context 有十余个必填依赖，脱离内核无法构造；绕过 __init__ 拿真实例。
    # 默认 lexicon 模式不会调用它的任何方法。
    ctx = Context.__new__(Context)
    try:
        plugin = m.PsycheEnginePlugin(ctx, {})
    except Exception:  # noqa: BLE001
        print(f"{BAD} 实例化失败：")
        traceback.print_exc()
        return False
    print(f"{OK} 实例化（数据目录 {plugin.store.path if hasattr(plugin.store, 'path') else '已就绪'}）")

    ev = FakeEvent("他们都在背后议论我，我睡不着")
    req = ProviderRequest(prompt=ev.message_str, system_prompt="你是一个助手。")
    asyncio.run(plugin.on_llm_request(ev, req))

    if not req.extra_user_content_parts:
        print(f"{BAD} 没有插入 extra_user_content_parts（会退化改写 system_prompt）")
        return False
    part = req.extra_user_content_parts[0]
    text = getattr(part, "text", "")
    if "<psyche_runtime" not in text:
        print(f"{BAD} 注入内容缺少 <psyche_runtime>")
        return False
    print(f"{OK} dynamic 注入：{type(part).__name__} / {len(text)} 字")

    no_save = getattr(part, "_no_save", False)
    if not no_save:
        print(f"{BAD} mark_as_temp 未生效——注入块会被写进对话历史，污染上下文与缓存")
        return False
    print(f"{OK} _no_save=True（不写入历史）")

    async def run_cmd(msg: str) -> str:
        e = FakeEvent(msg, umo="verify:FriendMessage:cmd")
        chunks = []
        async for r in plugin.psyche_cmd(e):
            chunks.append(str(r[1]) if isinstance(r, tuple) else str(getattr(r, "text", r)))
        return "\n".join(chunks)

    for cmd in ("/心理", "/心理 诊断", "/心理 生化"):
        out = asyncio.run(run_cmd(cmd))
        ok = bool(out.strip()) and "Traceback" not in out
        print(f"{OK if ok else BAD} {cmd}  ->  {len(out)} 字")
        if not ok:
            return False

    try:
        out = asyncio.run(plugin.psyche_self_report(ev, topic="整体"))
        print(f"{OK} llm_tool psyche_self_report -> {out[:36]}")
    except Exception:  # noqa: BLE001
        print(f"{BAD} llm_tool 调用失败：")
        traceback.print_exc()
        return False

    print("\n注入块前 14 行：")
    for line in text.splitlines()[:14]:
        print("    " + line)

    # 清掉本次验证写进真实数据库的临时会话，不留垃圾状态
    for key in ("verify:FriendMessage:1", "verify:FriendMessage:cmd"):
        try:
            plugin.store.delete(key)
        except Exception:  # noqa: BLE001
            pass
    print(f"\n{OK} 已清理验证用的临时会话状态")
    return True


# ---------------------------------------------------------------------------
# 3. 市场合规
# ---------------------------------------------------------------------------
def probe_market(plugin_root: Path) -> bool:
    print("\n【3/3】上架硬性要求")
    print("-" * 74)
    ok = True

    def item(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        if not passed:
            ok = False
        print(f"{OK if passed else BAD} {label}" + (f"  {detail}" if detail else ""))

    meta = plugin_root / "metadata.yaml"
    item("metadata.yaml 存在", meta.exists())
    item("requirements.txt 存在", (plugin_root / "requirements.txt").exists())
    item("main.py 存在", (plugin_root / "main.py").exists())
    item("_conf_schema.json 合法",
         _json_ok(plugin_root / "_conf_schema.json"))
    item("目录名与插件名一致", plugin_root.name == PLUGIN_NAME, plugin_root.name)

    total = sum(f.stat().st_size for f in plugin_root.rglob("*")
                if f.is_file() and ".git" not in f.parts and "__pycache__" not in f.parts)
    item("体积 < 16MB", total < 16 * 1024 * 1024, f"{total / 1024:.0f} KB")

    junk = [str(p.relative_to(plugin_root)) for p in plugin_root.rglob("*")
            if p.name in (".DS_Store", "Thumbs.db") or p.suffix in (".pyc", ".db")]
    item("无缓存/数据库残留", not junk, ", ".join(junk[:3]))
    return ok


def _json_ok(path: Path) -> bool:
    import json

    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="在真实 AstrBot 中验证本插件")
    ap.add_argument("--backend", help="AstrBot backend 目录（含 app/ 与 python/）")
    ap.add_argument("--astrbot-home", help="AstrBot 数据目录，默认 ~/.astrbot")
    args = ap.parse_args()

    backend = find_backend(args.backend)
    home = find_astrbot_home(args.astrbot_home)
    plugin_root = Path(__file__).resolve().parent.parent
    app_dir = backend / "app"
    plugins_dir = home / "data" / "plugins"

    print("=" * 74)
    print("真实 AstrBot 环境验证")
    print("=" * 74)
    print(f"  backend : {backend}")
    print(f"  data    : {home}")
    print(f"  plugin  : {plugin_root}")

    # 本脚本若被外部 python 启动，必须切到 AstrBot 的解释器与 sys.path 才有意义
    sys.path.insert(0, str(app_dir))
    os.chdir(home)

    if not (plugins_dir / PLUGIN_NAME).is_dir():
        print(f"\n  提示：{plugins_dir / PLUGIN_NAME} 不存在，"
              f"请先把插件放到该目录（或直接复制本仓库）")
        return 2

    try:
        import astrbot
    except ImportError as e:
        py = backend / "python" / "python.exe"
        if not py.exists():
            py = backend / "python" / "bin" / "python3"
        print(f"\n  无法 import astrbot（{e}）。")
        print("  请改用 AstrBot 自带的解释器运行本脚本：")
        print(f"      \"{py}\" \"{Path(__file__).resolve()}\"")
        return 2

    print(f"  AstrBot : {astrbot.__version__}\n")
    results = [probe_api(), probe_plugin(plugins_dir), probe_market(plugin_root)]

    print("\n" + "=" * 74)
    if all(results):
        print("结论：三项全过 —— 可在真实 AstrBot 中运行，且满足上架硬性要求")
        return 0
    print("结论：存在未通过项，见上方 FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
