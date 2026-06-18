"""Benchmark — 给每场打综合分，选历史最佳场作基准，对比后续场次为何没提升。"""
from funnel import derive_metrics

# 综合分权重（覆盖三维度：下单效率为主，转化+流量为辅）
_SCORE_WEIGHTS = {
    "gmv_usd": 0.30,        # 结果
    "gpm": 0.20,            # 千次观看成交(效率核心)
    "order_rate": 0.15,     # 下单效率
    "ctr": 0.12,            # 转化
    "dwell_time": 0.13,     # 停留(留人)
    "roi": 0.10,            # 投流效率
}


def _norm(rooms: list[dict], key: str) -> dict:
    """把某指标按全体场次归一化到 0-1（min-max）。返回 roomId→分。"""
    vals = [(r.get("_room_id"), r.get(key, 0) or 0) for r in rooms]
    nums = [v for _, v in vals]
    lo, hi = min(nums), max(nums)
    rng = (hi - lo) or 1.0
    return {rid: (v - lo) / rng for rid, v in vals}


def score_sessions(rooms: list[dict]) -> list[dict]:
    """给每场算综合分(0-100)，返回带 _score 的列表（按分降序）。"""
    if not rooms:
        return []
    norms = {k: _norm(rooms, k) for k in _SCORE_WEIGHTS}
    scored = []
    for r in rooms:
        rid = r.get("_room_id")
        s = sum(norms[k][rid] * w for k, w in _SCORE_WEIGHTS.items())
        rr = dict(r)
        rr["_score"] = round(s * 100, 1)
        scored.append(rr)
    return sorted(scored, key=lambda x: x["_score"], reverse=True)


def pick_benchmark(rooms: list[dict], min_gmv: float = 0) -> dict | None:
    """选历史最佳场作 benchmark：综合分最高、且有真实成交的场。"""
    scored = score_sessions(rooms)
    real = [r for r in scored if (r.get("gmv_usd", 0) or 0) > min_gmv]
    return (real or scored)[0] if scored else None


_CMP_KEYS = [
    ("gmv_usd", "GMV(USD)", "money"),
    ("gpm", "GPM", "num"),
    ("order_rate", "下单率", "pct"),
    ("ctr", "商品点击率", "pct"),
    ("dwell_time", "平均停留", "sec"),
    ("follow_rate", "转粉率", "pct"),
    ("roi", "投流ROI", "num"),
    ("views", "场观", "num"),
    ("impressions", "曝光", "num"),
]


def compare_to_benchmark(room: dict, bench: dict) -> list[dict]:
    """单场 vs benchmark 的逐指标差异。返回 [{name, cur, bench, delta_pct, worse}]。"""
    out = []
    for key, name, fmt in _CMP_KEYS:
        cur = room.get(key, 0) or 0
        bv = bench.get(key, 0) or 0
        delta = ((cur - bv) / bv * 100) if bv else 0.0
        out.append({"key": key, "name": name, "fmt": fmt, "cur": cur, "bench": bv,
                    "delta_pct": delta, "worse": cur < bv})
    return out


def regression_summary(rooms: list[dict], bench: dict) -> dict:
    """benchmark 之后的场次整体 vs benchmark：为何没提升。
    取 benchmark 开播时间之后的场次，算均值对比。"""
    bt = bench.get("_open_time", "")
    after = [r for r in rooms if r.get("_open_time", "") > bt]
    if not after:
        return {"after_count": 0}
    n = len(after)
    avg = {}
    for key, name, fmt in _CMP_KEYS:
        avg[key] = sum(r.get(key, 0) or 0 for r in after) / n
    # 哪些指标比 benchmark 差
    gaps = []
    for key, name, fmt in _CMP_KEYS:
        bv = bench.get(key, 0) or 0
        if bv and avg[key] < bv:
            gaps.append({"name": name, "fmt": fmt, "after_avg": avg[key], "bench": bv,
                         "gap_pct": (avg[key] - bv) / bv * 100})
    gaps.sort(key=lambda x: x["gap_pct"])  # 最差排前
    return {"after_count": n, "after_avg": avg, "bench_time": bt, "gaps": gaps}
