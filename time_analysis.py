"""时间维度分析 — 跨场最佳开播时段(何时开播) + 单场时间线衰减(何时关播)。"""
import re
from datetime import datetime
from collections import defaultdict


def _hour_of(open_time: str) -> int | None:
    m = re.search(r"\s(\d{1,2}):", open_time or "")
    return int(m.group(1)) if m else None


def _weekday_of(open_time: str) -> int | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(open_time, fmt).weekday()  # 0=Mon
        except (ValueError, TypeError):
            continue
    return None


_WD = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def best_time_slots(rooms: list[dict]) -> dict:
    """按开播小时 / 星期 聚合表现，找最佳开播时段（何时开播）。"""
    by_hour = defaultdict(list)
    by_wd = defaultdict(list)
    for r in rooms:
        h = _hour_of(r.get("_open_time", ""))
        wd = _weekday_of(r.get("_open_time", ""))
        gmv = r.get("gmv_usd", 0) or 0
        gpm = r.get("gpm", 0) or 0
        if h is not None:
            by_hour[h].append((gmv, gpm, r))
        if wd is not None:
            by_wd[wd].append((gmv, gpm, r))

    def _agg(d, labeler):
        rows = []
        for k, items in sorted(d.items()):
            n = len(items)
            rows.append({
                "slot": labeler(k), "key": k, "sessions": n,
                "avg_gmv": sum(x[0] for x in items) / n,
                "avg_gpm": sum(x[1] for x in items) / n,
                "total_gmv": sum(x[0] for x in items),
            })
        return rows

    hour_rows = _agg(by_hour, lambda h: f"{h:02d}:00")
    wd_rows = _agg(by_wd, lambda w: _WD[w])
    best_hour = max(hour_rows, key=lambda x: x["avg_gmv"]) if hour_rows else None
    best_wd = max(wd_rows, key=lambda x: x["avg_gmv"]) if wd_rows else None
    return {"by_hour": hour_rows, "by_weekday": wd_rows,
            "best_hour": best_hour, "best_weekday": best_wd}


def session_timeline_decay(timeline: list[dict]) -> dict:
    """从数据洞察时间线(Gemini 解析的 timeline)推断单场的开播/关播时机。

    timeline 每项含 time/online/gmv/note。用文本里的趋势词判断衰减点。
    返回 {peak_window, decay_point, suggest_close, suggest_open, reasons}。
    """
    if not timeline:
        return {}
    # 简单启发：找最后一个 online still有量 → 之后建议关播
    decay_idx = None
    for i, t in enumerate(timeline):
        txt = f"{t.get('online','')}{t.get('note','')}"
        if re.search(r"归零|掉至0|暴跌|流失|0人|停止推流|断崖", txt):
            decay_idx = i
            break
    reasons = []
    suggest_close = ""
    if decay_idx is not None:
        seg = timeline[decay_idx]
        suggest_close = seg.get("time", "")
        reasons.append(f"{suggest_close} 起在线/流量明显衰减({seg.get('note','')[:40]})，此后继续开播是空耗")
    return {
        "decay_window": timeline[decay_idx].get("time") if decay_idx is not None else "",
        "suggest_close": suggest_close,
        "reasons": reasons,
        "total_windows": len(timeline),
    }


def fmt_slot_block(slots: dict) -> str:
    """把最佳时段整理成喂给 LLM 的文本。"""
    if not slots:
        return ""
    lines = ["## 开播时段表现（跨场）"]
    bh, bw = slots.get("best_hour"), slots.get("best_weekday")
    if bh:
        lines.append(f"- 最佳开播小时: {bh['slot']}（{bh['sessions']}场，均GMV${bh['avg_gmv']:.0f}）")
    if bw:
        lines.append(f"- 最佳开播星期: {bw['slot']}（{bw['sessions']}场，均GMV${bw['avg_gmv']:.0f}）")
    # top3 小时
    hr = sorted(slots.get("by_hour", []), key=lambda x: x["avg_gmv"], reverse=True)[:5]
    if hr:
        lines.append("- 各时段均GMV TOP: " + "，".join(f"{h['slot']}=${h['avg_gmv']:.0f}({h['sessions']}场)" for h in hr))
    return "\n".join(lines)
