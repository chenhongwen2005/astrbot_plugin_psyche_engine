"""真实北京时间时钟的回归自测。

跑法：
    python tests/test_clock.py

测的是「时钟不许凭空跳、不许倒退、不许永久滞后」这几条硬约束，不是
具体几点。时间源统一走 clock.now_ts()，所以这里可以 patch 它来模拟
八小时后、三天后、系统时间被往回调，不需要真的等。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physio import Physiology, body as B  # noqa: E402
from psyche import clock as C  # noqa: E402

PASS = 0
_FAKE = {"ts": None}
_real_now_ts = C.now_ts


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"[ok] {msg}")


def set_ts(ts: float) -> None:
    _FAKE["ts"] = float(ts)
    C.now_ts = lambda: _FAKE["ts"]


def restore() -> None:
    C.now_ts = _real_now_ts


# ----------------------------------------------------------------------
def test_mode_parse() -> None:
    for v in ("real", "REAL", " real ", "true", "北京时间"):
        assert C.is_real(v), v
    for v in ("virtual", "v", "", None, "false"):
        assert not C.is_real(v), v
    ok("clock_mode 解析：real/虚拟/空值都认得")


def test_first_sync_keeps_total_clock() -> None:
    """首次切真实时钟只平移日内相位，绝不回退总量。

    回退会让所有疾病的 onset 与记忆时间戳变成「未来」。
    """
    t0 = 1_791_000_000.0        # 任意固定时刻
    set_ts(t0)
    body = B.new_body(sex="m", age=30)
    body["clock"] = 100.6       # 旧存档：虚拟时间已经走了 100 小时
    before = float(body["clock"])
    h = C.sync_clock(body, "real")
    assert h == 0.0, "首次切换不该推进"
    assert body["clock"] >= before, "首次切换不许回退 clock"
    want = C.bj_hour_at(t0)
    got = body["clock"] % 24.0
    assert abs(got - want) < 1e-6, f"相位没对齐：clock%24={got:.4f} 真实={want:.4f}"
    assert body.get("clock_epoch") is not None
    ok(f"首次切换只平移相位：clock {before:.1f} → {body['clock']:.1f}，对齐 {want:.2f} 点")


def test_elapsed_advances_and_stays_aligned() -> None:
    """过 8 小时后：推进 8 小时，且钟点仍是北京真实钟点。"""
    t0 = 1_791_000_000.0
    set_ts(t0)
    body = B.new_body(sex="m", age=30)
    C.sync_clock(body, "real")
    c0 = float(body["clock"])

    set_ts(t0 + 8 * 3600)
    h = C.sync_clock(body, "real")
    assert abs(h - 8.0) < 1e-6, f"应推进 8 小时，实际 {h}"
    body["clock"] = c0 + h
    assert abs((body["clock"] % 24.0) - C.bj_hour_at(t0 + 8 * 3600)) < 1e-6
    ok("真实流逝 8 小时：推进 8.0 小时，钟点跟随北京时间")


def test_short_gap_is_tiny() -> None:
    """一分钟内连发三条，不该推进 6 小时。"""
    t0 = 1_791_000_000.0
    set_ts(t0)
    body = B.new_body(sex="m", age=30)
    C.sync_clock(body, "real")
    set_ts(t0 + 40)
    h = C.sync_clock(body, "real")
    assert 0 < h < 0.02, f"40 秒应推进约 0.011 小时，实际 {h}"
    ok(f"40 秒推进 {h * 60:.1f} 分钟，短对话不再被当成 6 小时")


def test_long_offline_clamped_and_realigned() -> None:
    """离线三天以上：只补 72 小时，并重设 epoch，之后不再一直补账。"""
    t0 = 1_791_000_000.0
    set_ts(t0)
    body = B.new_body(sex="m", age=30)
    C.sync_clock(body, "real")
    c0 = float(body["clock"])

    set_ts(t0 + 10 * 24 * 3600)
    h1 = C.sync_clock(body, "real")
    assert h1 == C.MAX_GAP_H, f"应钳到 {C.MAX_GAP_H}，实际 {h1}"
    body["clock"] = c0 + h1

    # 关键：下一轮不能再补那笔账
    set_ts(t0 + 10 * 24 * 3600 + 60)
    h2 = C.sync_clock(body, "real")
    assert h2 < 0.05, f"epoch 没重设，第二轮还在补 {h2} 小时"
    ok(f"离线十天只补 {h1:.0f} 小时，第二轮只补 {h2 * 60:.1f} 分钟（不滞后）")


def test_clock_backwards_is_ignored() -> None:
    """系统时间被往回调（虚拟机快照、时区误设）时既不推进也不倒退。"""
    t0 = 1_791_000_000.0
    set_ts(t0)
    body = B.new_body(sex="m", age=30)
    C.sync_clock(body, "real")
    c0 = float(body["clock"])
    set_ts(t0 - 3600)
    h = C.sync_clock(body, "real")
    assert h == 0.0, f"倒退时应返回 0，实际 {h}"
    assert float(body["clock"]) == c0, "clock 不许自己变"
    ok("系统时间倒退：不推进、不倒退")


def test_virtual_untouched() -> None:
    body = B.new_body(sex="m", age=30)
    body["clock"] = 7.25
    h = C.sync_clock(body, "virtual")
    assert h == 0.0
    assert body["clock"] == 7.25
    assert "clock_epoch" not in body
    ok("虚拟模式完全不动身体时钟")


def test_hourly_judgement_independent_of_chunking() -> None:
    """睡眠/运动判定必须每小时恰好一次，与调用方怎么切时间无关。

    旧写法 `while remaining: chunk=min(1.0, remaining)` 在真实时钟下
    每轮只过几分钟也会跑一遍判定，夜里连发一百条就等于抽一百次
    「今晚睡不睡」的签。
    """
    def count_sleep_calls(hours: float, pieces: int) -> int:
        phys = Physiology({"physio_hours_per_turn": 6})
        body = B.new_body(sex="m", age=30)
        body["clock"] = 22.0
        calls = []
        orig = phys._sleep

        def spy(*a, **k):
            calls.append(a[1])
            return orig(*a, **k)

        phys._sleep = spy
        for _ in range(pieces):
            phys.step(body, hours / pieces)
        return len(calls)

    whole = count_sleep_calls(6.0, 1)
    split = count_sleep_calls(6.0, 60)
    tiny = count_sleep_calls(6.0, 360)
    assert whole == split == tiny, f"判定次数不一致：{whole} / {split} / {tiny}"
    assert 5 <= whole <= 7, f"6 小时应判定约 6 次（跨整点），实际 {whole}"
    ok(f"整点判定：6 小时切成 1/60/360 份，睡眠判定都是 {whole} 次")


def test_day_of_year_follows_real_date() -> None:
    t = 1_791_000_000.0
    assert 1 <= C.day_of_year_at(t) <= 366
    d = C.bj_from_ts(t)
    assert d.utcoffset().total_seconds() == 8 * 3600
    ok(f"北京时间偏移固定 +8：{d.strftime('%Y-%m-%d %H:%M')}，年内第 {C.day_of_year_at(t)} 天")


def main() -> int:
    print("── 时钟自测 ──")
    test_mode_parse()
    test_first_sync_keeps_total_clock()
    test_elapsed_advances_and_stays_aligned()
    test_short_gap_is_tiny()
    test_long_offline_clamped_and_realigned()
    test_clock_backwards_is_ignored()
    test_virtual_untouched()
    test_hourly_judgement_independent_of_chunking()
    test_day_of_year_follows_real_date()
    restore()
    print(f"\n全部通过（{PASS} 项）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
