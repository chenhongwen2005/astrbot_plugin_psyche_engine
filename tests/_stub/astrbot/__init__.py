"""AstrBot 的最小 stub，仅用于在无 AstrBot 运行时的环境里做导入与注入冒烟测试。

它不是 AstrBot 的替代品，只声明插件真正用到的那几个符号与签名，
使得 `main.py` 可以被 import、被实例化、被跑一遍 on_llm_request，
从而在本地发现「属性名写错 / API 用了不存在的字段」这类一装就崩的问题。
"""

__version__ = "0.0.0-stub"
