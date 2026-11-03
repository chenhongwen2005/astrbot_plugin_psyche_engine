"""产后：孩子出来了，身体的事才刚开始。

为什么单独一层
    妊娠在分娩那一刻结束，但身体没有。接下来六周里发生的事——恶露、
    宫缩痛、伤口疼、乳房胀满、乳部皲裂、半夜被哭声叫醒两三次、情绪
    忽然崩一次——密度不比孕期低，而且更影响一个人怎么说话。

    原来这里只有一个 `lactating` 布尔和一个 6 周的倒计时。结果就是：
    角色刚生完孩子，第二天就能健步如飞，情绪只在「产后低落」一项上
    闪一下，六周后一切归零。

按天给，因为产后是以天变的
    产后的每个阶段都比孕期短：恶露三天一变颜色，乳房胀满第五天到顶，
    伤口两周愈合，产后抑郁的窗口在第 14 天前后分岔。用周做单位会把
    头一周里最难受的那几天抹平。

产后抑郁不是「产后情绪低落」
    分娩后三五天里哭一场、觉得撑不住，是 baby blues，两周内自己会退。
    两周之后还在往下掉，才是产后抑郁——这两件事的处置完全不同，所以
    这里分成两个量，不合并写成一个「情绪不佳」。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _r(body: Dict[str, Any]) -> Dict[str, Any]:
    r = body.get("repro")
    return r if isinstance(r, dict) else {}


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def active(body: Dict[str, Any]) -> bool:
    """在产后一年内、且没有再次妊娠，就算还在产后这条线上。

    不能只看 phase：月经一恢复，phase 就被周期逻辑改成「月经期」，
    产后脱发、盆底、哺乳这些还会持续好几个月的东西会一起消失。
    """
    r = _r(body)
    d = _f(r.get("postpartum_days"), -1.0)
    return 0.0 <= d < 365.0 and not r.get("pregnant")


# ----------------------------------------------------------------------
# 推进
# ----------------------------------------------------------------------
def step(body: Dict[str, Any], r: Dict[str, Any], dh_days: float, rng,
         events: List[str]) -> None:
    # 哺乳期（42 天后）仍在产后的延长线上：脱发、乳腺炎、体重恢复都还在走，
    # 只是急性期过了。这里只认 postpartum_state，不认「已经满六周」。
    if str(r.get("phase") or "") not in ("postpartum", "lactating"):
        return
    d = _f(r.get("postpartum_days"), 0.0) + max(0.0, dh_days)
    r["postpartum_days"] = round(d, 2)
    r["postpartum_week"] = round(max(0.0, 6.0 - d / 7.0), 2)
    lact = bool(r.get("lactating"))

    # --- 恶露：血性 → 浆液性 → 白色，四周左右干净 ---
    if d <= 4.0:
        r["lochia"] = 0.90
        r["lochia_kind"] = "血性"
    elif d <= 10.0:
        r["lochia"] = 0.45
        r["lochia_kind"] = "浆液性"
    elif d <= 28.0:
        r["lochia"] = 0.18
        r["lochia_kind"] = "白色"
    else:
        r["lochia"] = 0.0
        r["lochia_kind"] = ""

    # --- 宫缩痛（产后痛）：头三天最明显，喂奶时加重 ---
    r["afterpains"] = max(0.0, 0.85 * (1.0 - d / 3.0)) if d <= 3.0 else 0.0

    # --- 伤口：会阴侧切/撕裂两周内基本愈合；剖宫产更久 ---
    if r.get("cesarean"):
        r["wound"] = max(0.0, 1.0 - d / 21.0)
        r["wound_kind"] = "剖宫产刀口"
    else:
        r["wound"] = max(0.0, 1.0 - d / 14.0)
        r["wound_kind"] = "会阴伤口" if _f(r.get("episiotomy")) > 0 else ""

    # --- 泌乳：第 2~5 天乳房胀满到顶，之后靠按需哺乳维持 ---
    if lact:
        if 2.0 <= d <= 5.0:
            r["engorgement"] = 0.85
        elif d < 2.0:
            r["engorgement"] = 0.30
        else:
            r["engorgement"] = max(0.0, 0.35 - (d - 5.0) * 0.02)
        # 乳部皮肤皲裂：那两周里每次哺乳都疼
        r["nipple_crack"] = min(0.8, max(0.0, (d - 2.0) / 6.0)) if d <= 15.0 else 0.0
        # 乳腺炎：乳汁淤积 + 皲裂破口，2~6 周是高发窗口
        if 12.0 <= d <= 42.0 and not r.get("mastitis"):
            if rng.random() < 0.012 * max(0.2, dh_days):
                r["mastitis"] = 0.7
                events.append("mastitis")
        # 乳腺炎会退：排空、冷敷、必要时用药，一到两周。不退的话
        # 这个角色会带着一块红肿的乳房过完整个哺乳期。
        if _f(r.get("mastitis")) > 0.0:
            m = _f(r.get("mastitis")) - 0.085 * max(0.0, dh_days)
            r["mastitis"] = round(m, 3) if m > 0.05 else 0.0
        # 夜奶把睡眠撕成碎片。这不是「困」，是连续的、无法补的剥夺
        life = body.get("life")
        if isinstance(life, dict):
            life["sleep_debt"] = min(40.0, _f(life.get("sleep_debt")) + 0.10 * max(0.0, dh_days))

    # --- 情绪：两周内是 baby blues，两周后还低就是产后抑郁 ---
    if d <= 14.0:
        r["baby_blues"] = max(0.0, 1.0 - d / 14.0)
    else:
        r["baby_blues"] = 0.0
    # 风险因素是真的：睡眠剥夺、哺乳困难、缺乏支持、既往抑郁史
    if d >= 14.0 and not r.get("ppd"):
        life = body.get("life") or {}
        debt = _f(life.get("sleep_debt"))
        p = 0.0016 * max(0.2, dh_days)
        p *= 1.0 + 0.03 * max(0.0, debt - 6.0)
        if _f(r.get("nipple_crack")) > 0.3:
            p *= 1.4
        if rng.random() < p:
            r["ppd"] = 0.55
            events.append("postpartum_depression")
    if r.get("ppd"):
        r["ppd"] = min(1.0, _f(r.get("ppd")) + 0.0015 * max(0.0, dh_days))

    # --- 脱发：产后 3~6 个月，雌激素撤退让生长期毛囊一起进休止期 ---
    r["hair_loss"] = 0.7 if 84.0 <= d <= 180.0 else 0.0

    # --- 盆底：漏尿、下坠感，六周内最明显 ---
    r["pelvic"] = max(0.0, 1.0 - d / 42.0)

    # --- 体重：哺乳期掉得快一点，之后每周半斤左右 ---
    r["weight_gain"] = max(0.0, _f(r.get("weight_gain")) - (0.5 if lact else 0.35) / 7.0 * max(0.0, dh_days))

    # --- 月经恢复：不哺乳 6~8 周，哺乳常常拖到半年后 ---
    if not r.get("cycle_resumed"):
        resume = 56.0 if lact else 42.0
        if d >= resume and rng.random() < 0.02 * max(0.2, dh_days):
            r["cycle_resumed"] = True
            r["cycle_day"] = 1.0
            events.append("cycle_resumed")

    # --- 六周后退出产后期 ---
    if d > 42.0 and not lact:
        r["phase"] = "reproductive"
    elif d > 42.0 and lact:
        # 哺乳期仍算产后，但急性期已过：只保留泌乳与情绪
        r["phase"] = "lactating"


# ----------------------------------------------------------------------
# 指标
# ----------------------------------------------------------------------
def modulate(body: Dict[str, Any], labs: Dict[str, float],
             vitals: Dict[str, float], derived: Dict[str, Any]) -> None:
    r = _r(body)
    if not active(body):
        return
    d = _f(r.get("postpartum_days"))

    if body.pop("_postpartum_blood_loss", 0):
        if "HGB" in labs:
            labs["HGB"] = max(75.0, float(labs["HGB"]) - 12.0)

    # 乳腺炎：低热、心率快。这个不能拖，真实世界里拖成脓肿要切开
    if _f(r.get("mastitis")) > 0.0:
        vitals["TEMP"] = float(vitals.get("TEMP", 36.6)) + 0.9
        vitals["HR"] = float(vitals.get("HR", 72)) + 8.0
        derived["mastitis"] = round(_f(r.get("mastitis")), 2)

    # 产后痛与伤口：疼是真的疼
    pain = 3.0 * _f(r.get("afterpains")) + 2.2 * _f(r.get("wound"))
    if pain > 0.05:
        vitals["PAIN"] = min(10.0, float(vitals.get("PAIN", 0.0)) + pain)

    # 哺乳消耗：每天多烧 400~500 kcal，水也去得多
    if r.get("lactating"):
        life = body.get("life")
        if isinstance(life, dict):
            life["water"] = max(0.15, _f(life.get("water"), 0.85) - 0.004)
        derived["lactating"] = 1

    if d < 42.0:
        derived["postpartum_days"] = int(d)
    if _f(r.get("ppd")) > 0.0:
        derived["postpartum_depression"] = round(_f(r.get("ppd")), 2)


# ----------------------------------------------------------------------
# 症状
# ----------------------------------------------------------------------
def symptoms(body: Dict[str, Any]) -> List[Tuple[str, float]]:
    r = _r(body)
    out: List[Tuple[str, float]] = []
    if not active(body):
        return out
    d = _f(r.get("postpartum_days"))

    if _f(r.get("lochia")) > 0.2:
        out.append(("恶露还没干净", min(0.8, _f(r.get("lochia")))))
    if _f(r.get("afterpains")) > 0.25:
        out.append(("下腹阵发性疼痛", min(0.9, _f(r.get("afterpains")))))
    if _f(r.get("wound")) > 0.25:
        out.append((f"{r.get('wound_kind') or '伤口'}疼痛，坐位时加重", min(0.9, _f(r.get("wound")))))
    if _f(r.get("engorgement")) > 0.35:
        out.append(("乳房胀满疼痛", min(0.9, _f(r.get("engorgement")))))
    if _f(r.get("nipple_crack")) > 0.25:
        out.append(("乳部皮肤皲裂，哺乳时疼痛", min(0.9, _f(r.get("nipple_crack")))))
    if _f(r.get("mastitis")) > 0.0:
        out.append(("乳房局部红肿发热", min(0.95, 0.6 + _f(r.get("mastitis")) * 0.4)))
        out.append(("身上发冷、有点烧", 0.7))
    if _f(r.get("pelvic")) > 0.35:
        out.append(("咳嗽时漏尿、下腹坠胀", min(0.7, _f(r.get("pelvic")))))
    if _f(r.get("hair_loss")) > 0.0 and d > 60.0:
        out.append(("洗头时脱发明显", 0.6))

    # 情绪：baby blues 与产后抑郁分开写，因为它们是两件事
    blues = _f(r.get("baby_blues"))
    ppd = _f(r.get("ppd"))
    if ppd > 0.25:
        out.append(("兴趣减退，对周围反应淡漠", min(0.95, 0.5 + ppd * 0.5)))
        out.append(("自责、信心不足", min(0.85, 0.4 + ppd * 0.4)))
    elif blues > 0.30:
        out.append(("情绪波动、易落泪", min(0.8, blues)))

    if not out and d < 3.0:
        out.append(("产后初期，体力明显不足", 0.7))
    return out


def summary(body: Dict[str, Any]) -> str:
    r = _r(body)
    if not active(body):
        return ""
    d = int(_f(r.get("postpartum_days")))
    lact = bool(r.get("lactating"))
    if d > 42 and not lact:
        return ""
    bits = [f"产后第 {d} 天" if d <= 42 else "哺乳期"]
    if lact and d <= 42:
        bits.append("哺乳中")
    if _f(r.get("ppd")) > 0.25:
        bits.append("情绪持续低落")
    if _f(r.get("mastitis")) > 0.0:
        bits.append("乳腺炎")
    if _f(r.get("lochia")) > 0.2:
        bits.append(f"恶露{r.get('lochia_kind') or ''}")
    return "·".join(bits)


def line(body: Dict[str, Any]) -> str:
    """只在头两天补一句整体状态。

    具体的不适（伤口、胀满、乳腺炎、宫缩痛）已经写进症状表了，这里再
    说一遍就是同一件事在一段话里出现两次——注入块的篇幅是要抢的。
    """
    r = _r(body)
    if not active(body):
        return ""
    d = _f(r.get("postpartum_days"))
    if d <= 2.0:
        return "刚生完，起身会发晕"
    return ""
