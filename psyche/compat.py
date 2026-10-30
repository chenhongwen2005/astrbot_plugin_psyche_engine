"""physio 包的导入适配层。

为什么要这一层：插件在 AstrBot 里是被当成一个**包**加载的
（`...astrbot_plugin_psyche_engine.main`），此时 `physio` 与 `psyche` 是兄弟子包，
只能写 `from ..physio import ...`；而测试脚本是把插件目录塞进 sys.path 后
直接 `from psyche import ...`，此时 `physio` 是顶层模块，只能写 `from physio import ...`。

两种写法都不通用，写死在任何一个里都会在另一种场景下炸掉整个插件。
所以在这里试一次、退一次，其余模块统一从本模块取。

只做一次导入还有一个副作用是好的：`physio.DISEASES` 这类注册表在 import 时构建，
两条路径各导一次会得到两份互不相干的字典，虽然内容相同，但排查问题时很费神。
"""

from __future__ import annotations

try:  # 作为包的一部分（AstrBot 运行时）
    from .. import physio as physio  # type: ignore
    from ..physio import body as physio_body  # type: ignore
    from ..physio import report as physio_report  # type: ignore
except ImportError:  # 作为顶层包（测试脚本 / 独立运行）
    import physio as physio  # type: ignore
    from physio import body as physio_body  # type: ignore
    from physio import report as physio_report  # type: ignore

__all__ = ["physio", "physio_body", "physio_report"]
