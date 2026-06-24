"""按 场次 / 天 / 周 / 月 聚合主播的直播数据。"""
from datetime import datetime
from collections import defaultdict

from config import METRIC_DEFS

# 求和类指标(累加) vs 求均类指标(加权/简单平均)
_SUM_KEYS = {"impressions", "expv", "views", "items_sold", "gmv", "gmv_usd",
             "ads_cost", "ads_cost_usd"}
# 其余比率/时长类做平均
_AVG_KEYS = {d["key"] for d in METRIC_DEFS} - _SUM_KEYS


def _parse_dt(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _period_key(dt: datetime, granularity: str) -> str:
    if granularity == "day":
        return dt.strftime("%Y-%m-%d")
    if granularity == "week":
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if granularity == "month":
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y-%m-%d %H:%M")  # session


def aggregate(rooms: list[dict], granularity: str = "session") -> list[dict]:
    """聚合。granularity ∈ session|day|week|month。
    返回按时间正序的分组列表，每组含聚合指标 + 场次数 + 时间区间。
    """
    if granularity == "session":
        out = []
        for r in sorted(rooms, key=lambda x: x.get("_open_time", "")):
            row = {"period": r.get("_open_time", ""), "session_count": 1,
                   "_room_id": r.get("_room_id"), "_oss_url": r.get("_oss_url", ""),
                   "_gemini_task_id": r.get("_gemini_task_id", ""), "_currency": r.get("_currency", "")}
            for d in METRIC_DEFS:
                row[d["key"]] = r.get(d["key"], 0)
            out.append(row)
        return out

    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rooms:
        dt = _parse_dt(r.get("_open_time", ""))
        if not dt:
            continue
        groups[_period_key(dt, granularity)].append(r)

    out = []
    for pk in sorted(groups.keys()):
        items = groups[pk]
        row = {"period": pk, "session_count": len(items),
               "_currency": items[0].get("_currency", "")}
        for d in METRIC_DEFS:
            k = d["key"]
            vals = [it.get(k, 0) or 0 for it in items]
            if k in _SUM_KEYS:
                row[k] = sum(vals)
            else:
                row[k] = (sum(vals) / len(vals)) if vals else 0.0
        out.append(row)
    return out


def trend(series: list[dict], metric: str) -> dict:
    """计算某指标的环比趋势（最近 vs 上一期）。"""
    vals = [(s["period"], s.get(metric, 0) or 0) for s in series]
    if len(vals) < 2:
        return {"latest": vals[-1][1] if vals else 0, "prev": 0, "change_pct": 0, "direction": "flat"}
    latest, prev = vals[-1][1], vals[-2][1]
    change = ((latest - prev) / prev * 100) if prev else 0.0
    direction = "up" if change > 1 else ("down" if change < -1 else "flat")
    return {"latest": latest, "prev": prev, "change_pct": change, "direction": direction}


def summary_kpis(rooms: list[dict]) -> dict:
    """主播整体 8KPI 汇总（用于卡片）。"""
    n = len(rooms) or 1
    total_views = sum(r.get("views", 0) or 0 for r in rooms)
    total_gmv_usd = sum(r.get("gmv_usd", 0) or 0 for r in rooms)
    total_items = sum(r.get("items_sold", 0) or 0 for r in rooms)
    return {
        "session_count": len(rooms),
        "total_gmv_usd": total_gmv_usd,
        "total_items_sold": total_items,
        "avg_ctr": sum(r.get("ctr", 0) or 0 for r in rooms) / n,
        "avg_dwell": sum(r.get("dwell_time", 0) or 0 for r in rooms) / n,
        "avg_order_rate": sum(r.get("order_rate", 0) or 0 for r in rooms) / n,
        "avg_gpm": sum(r.get("gpm", 0) or 0 for r in rooms) / n,
        "avg_roi": sum(r.get("roi", 0) or 0 for r in rooms) / n,
        "total_views": total_views,
        "gpm_usd_overall": (total_gmv_usd / total_views * 1000) if total_views else 0.0,
    }


def per_host_summary(rooms: list[dict]) -> list[dict]:
    """按主播(_host)拆分，各主播一行 KPI，用于多主播横向对比。按总GMV降序。"""
    by_host: dict[str, list[dict]] = defaultdict(list)
    for r in rooms:
        by_host[r.get("_host") or "unknown"].append(r)
    out = []
    for host, rs in by_host.items():
        k = summary_kpis(rs)
        out.append({"host": host, **k})
    return sorted(out, key=lambda x: x.get("total_gmv_usd", 0), reverse=True)
