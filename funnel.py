"""漏斗计算 + 衍生指标 + 阈值诊断。

把一条(或一组)直播场次的原始指标，转成转化漏斗各级 + 衍生指标(ERR/GPM拆解/客单价/UV价值)，
并按阈值给出每级的健康度诊断(ok/warn/bad)。
"""
from config import DEFAULT_THRESHOLDS


def derive_metrics(room: dict) -> dict:
    """从单场原始字段计算衍生指标。"""
    impressions = room.get("impressions", 0) or 0
    views = room.get("views", 0) or 0
    items_sold = room.get("items_sold", 0) or 0
    gmv = room.get("gmv", 0) or 0
    gmv_usd = room.get("gmv_usd", 0) or 0
    ads_cost = room.get("ads_cost", 0) or 0

    # 进入率 ERR = 场观 / 曝光
    enter_room_rate = (views / impressions) if impressions else 0.0
    # 客单价 AOV = GMV / 件数（近似，缺买家数用件数兜底）
    aov = (gmv / items_sold) if items_sold else 0.0
    aov_usd = (gmv_usd / items_sold) if items_sold else 0.0
    # UV 价值 = GMV / 场观
    uv_value = (gmv / views) if views else 0.0
    uv_value_usd = (gmv_usd / views) if views else 0.0
    # 粗略 ROAS（本币）：GMV / 投流花费（同币种近似）
    roas = (gmv / ads_cost) if ads_cost else 0.0

    return {
        "enter_room_rate": enter_room_rate,
        "aov": aov,
        "aov_usd": aov_usd,
        "uv_value": uv_value,
        "uv_value_usd": uv_value_usd,
        "roas": roas,
    }


def diagnose(value: float, key: str) -> dict:
    """按阈值判断单指标健康度。返回 {level, label, value, threshold}。"""
    t = DEFAULT_THRESHOLDS.get(key)
    if not t:
        return {"level": "na", "label": "", "value": value}
    warn, bad, direction = t["warn"], t["bad"], t["dir"]
    if direction == "low":  # 越低越差
        if value < bad:
            level = "bad"
        elif value < warn:
            level = "warn"
        else:
            level = "ok"
    else:  # 越高越差
        if value > bad:
            level = "bad"
        elif value > warn:
            level = "warn"
        else:
            level = "ok"
    return {"level": level, "name": t["name"], "value": value, "warn": warn, "bad": bad, "fmt": t["fmt"]}


def build_funnel(room: dict) -> dict:
    """构建单场转化漏斗 + 诊断。

    曝光 → 进入率 → 场观 → 停留 → 商品点击CTR → 下单率 → GMV/GPM
    """
    d = derive_metrics(room)
    stages = [
        {"stage": "曝光", "metric": "impressions", "value": room.get("impressions", 0), "diag": None},
        {"stage": "进入率", "metric": "enter_room_rate", "value": d["enter_room_rate"],
         "diag": diagnose(d["enter_room_rate"], "enter_room_rate")},
        {"stage": "场观", "metric": "views", "value": room.get("views", 0), "diag": None},
        {"stage": "平均停留", "metric": "dwell_time", "value": room.get("dwell_time", 0),
         "diag": diagnose(room.get("dwell_time", 0), "dwell_time")},
        {"stage": "商品点击率", "metric": "ctr", "value": room.get("ctr", 0),
         "diag": diagnose(room.get("ctr", 0), "ctr")},
        {"stage": "下单率", "metric": "order_rate", "value": room.get("order_rate", 0),
         "diag": diagnose(room.get("order_rate", 0), "order_rate")},
        {"stage": "成交件数", "metric": "items_sold", "value": room.get("items_sold", 0), "diag": None},
        {"stage": "GMV(USD)", "metric": "gmv_usd", "value": room.get("gmv_usd", 0), "diag": None},
    ]
    # 额外诊断（转粉/评论/ROI）
    extra_diag = {
        "follow_rate": diagnose(room.get("follow_rate", 0), "follow_rate"),
        "comment_rate": diagnose(room.get("comment_rate", 0), "comment_rate"),
        "roi": diagnose(room.get("roi", 0), "roi"),
    }
    return {"stages": stages, "derived": d, "extra_diag": extra_diag}


def gpm_decomposition(room: dict) -> dict:
    """GPM = CTR × 转化率 × 客单价（千次观看维度）。定位最弱因子。
    GPM(每千次观看成交) ≈ ctr × order_rate × aov × 1000 / 1（数量级近似，用于相对比较）。
    """
    d = derive_metrics(room)
    ctr = room.get("ctr", 0) or 0
    order_rate = room.get("order_rate", 0) or 0
    aov_usd = d["aov_usd"]
    # 三因子相对贡献（标准化到各自经验基线）
    factors = {
        "商品点击率CTR": {"value": ctr, "baseline": DEFAULT_THRESHOLDS["ctr"]["warn"]},
        "下单率": {"value": order_rate, "baseline": DEFAULT_THRESHOLDS["order_rate"]["warn"]},
        "客单价AOV(USD)": {"value": aov_usd, "baseline": 35.0},  # TikTok Shop 经验AOV
    }
    for f in factors.values():
        f["ratio"] = (f["value"] / f["baseline"]) if f["baseline"] else 0.0
    weakest = min(factors.items(), key=lambda kv: kv[1]["ratio"])
    return {"factors": factors, "weakest": weakest[0]}
