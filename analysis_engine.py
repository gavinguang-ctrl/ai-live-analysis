"""复盘分析引擎 — 组装漏斗/聚合/四维数据 → Opus 4.8 推理 → 复盘文本 + TODO。"""
from funnel import build_funnel, gpm_decomposition, diagnose
from aggregate import aggregate, summary_kpis, trend
from prompts import (REVIEW_SYSTEM, REVIEW_USER_TMPL, QUALITY_RUBRIC, fmt_val,
                     SCRIPT_SYSTEM, SCRIPT_USER_TMPL)
import json as _json
import re as _re


def analyze_script(script_text: str) -> dict:
    """用 Opus 4.8 分析单份口播稿的脚本问题。"""
    from llm import get_reasoner
    llm = get_reasoner()
    out = llm.generate(SCRIPT_USER_TMPL.format(script=script_text[:8000]), system=SCRIPT_SYSTEM)
    txt = _re.sub(r"^```(?:json)?|```$", "", (out or "").strip(), flags=_re.MULTILINE).strip()
    m = _re.search(r"\{.*\}", txt, _re.DOTALL)
    if m:
        try:
            return _json.loads(m.group(0))
        except Exception:
            pass
    return {"raw": out}


_LEVEL_TAG = {"ok": "✓正常", "warn": "⚠偏低", "bad": "✗严重偏低", "na": ""}


def _kpi_block(rooms: list[dict]) -> str:
    k = summary_kpis(rooms)
    return (
        f"- 场次数: {k['session_count']}\n"
        f"- 总GMV(USD): ${k['total_gmv_usd']:,.2f}\n"
        f"- 总成交件数: {k['total_items_sold']:,.0f}\n"
        f"- 总场观: {k['total_views']:,.0f}\n"
        f"- 整体GPM(USD/千观看): ${k['gpm_usd_overall']:.2f}\n"
        f"- 平均商品点击率CTR: {k['avg_ctr']*100:.2f}%\n"
        f"- 平均停留: {k['avg_dwell']:.0f}秒\n"
        f"- 平均下单率: {k['avg_order_rate']*100:.2f}%\n"
        f"- 平均ROI: {k['avg_roi']:.2f}"
    )


def _funnel_block(rooms: list[dict]) -> str:
    """对全体场次取代表性(平均)漏斗 — 用聚合后的单行构建。"""
    if not rooms:
        return "(无数据)"
    agg = aggregate(rooms, "month")  # 借月聚合得到加总+均值的代表行；若跨多月取整体
    # 用整体平均行
    from config import METRIC_DEFS
    rep = {}
    n = len(rooms)
    sum_keys = {"impressions", "views", "items_sold", "gmv", "gmv_usd"}
    for d in METRIC_DEFS:
        kk = d["key"]
        vals = [r.get(kk, 0) or 0 for r in rooms]
        rep[kk] = sum(vals) if kk in sum_keys else (sum(vals)/n if vals else 0)
    f = build_funnel(rep)
    lines = []
    for s in f["stages"]:
        diag = s["diag"]
        if diag and diag.get("level") != "na":
            v = fmt_val(s["value"], diag.get("fmt", "num"))
            lines.append(f"- {s['stage']}: {v}  [{_LEVEL_TAG.get(diag['level'],'')}]")
        else:
            lines.append(f"- {s['stage']}: {s['value']:,.0f}")
    ed = f["extra_diag"]
    for key in ("follow_rate", "comment_rate", "roi"):
        d = ed[key]
        if d.get("level") != "na":
            lines.append(f"- {d['name']}: {fmt_val(d['value'], d['fmt'])}  [{_LEVEL_TAG.get(d['level'],'')}]")
    return "\n".join(lines)


def _gpm_block(rooms: list[dict]) -> str:
    if not rooms:
        return "(无数据)"
    from config import METRIC_DEFS
    n = len(rooms)
    rep = {}
    for d in METRIC_DEFS:
        kk = d["key"]
        rep[kk] = sum(r.get(kk, 0) or 0 for r in rooms) / n
    rep["gmv_usd"] = sum(r.get("gmv_usd", 0) or 0 for r in rooms) / n
    rep["items_sold"] = sum(r.get("items_sold", 0) or 0 for r in rooms) / n
    g = gpm_decomposition(rep)
    lines = [f"最弱因子: **{g['weakest']}**"]
    for name, f in g["factors"].items():
        lines.append(f"- {name}: 当前 {f['value']:.4f} / 基线 {f['baseline']} → 相对 {f['ratio']*100:.0f}%")
    return "\n".join(lines)


def _detail_block(series: list[dict], granularity: str) -> str:
    if not series:
        return "(无数据)"
    lines = []
    for s in series[-12:]:  # 最近12个周期
        cur = s.get("_currency", "")
        lines.append(
            f"- {s['period']} (×{s['session_count']}场): "
            f"曝光{s.get('impressions',0):,.0f} 场观{s.get('views',0):,.0f} "
            f"停留{s.get('dwell_time',0):.0f}s CTR{s.get('ctr',0)*100:.1f}% "
            f"下单率{s.get('order_rate',0)*100:.1f}% GMV${s.get('gmv_usd',0):,.0f} "
            f"GPM{s.get('gpm',0):.1f} ROI{s.get('roi',0):.1f}"
        )
    return "\n".join(lines)


_GRAN_DESC = {"session": "按场次", "day": "按天", "week": "按周", "month": "按月"}


def run_review(host: str, rooms: list[dict], granularity: str = "week",
               quality: dict | None = None, scripts: list[str] | None = None) -> dict:
    """执行复盘：组装数据 → Opus 4.8 → 返回 {markdown, blocks}。

    quality: 可选，录像四维分析结果(来自 video_analyze)。
    scripts: 可选，口播稿文本列表(来自 fetch_task_content)。
    """
    from llm import get_reasoner

    series = aggregate(rooms, granularity)
    period_desc = f"{_GRAN_DESC.get(granularity, granularity)}（共{len(rooms)}场，{series[0]['period'] if series else ''} ~ {series[-1]['period'] if series else ''}）"

    quality_block = ""
    if quality:
        qs = quality
        quality_block = (
            "## 录像四维评分（Gemini 视觉分析）\n"
            f"- 画面: {qs.get('visual',{}).get('score','?')}/10\n"
            f"- 声音: {qs.get('audio',{}).get('score','?')}/10\n"
            f"- 互动: {qs.get('interaction',{}).get('score','?')}/10\n"
            f"- 脚本: {qs.get('script',{}).get('score','?')}/10\n"
            f"- 掉点时刻: {', '.join(qs.get('dropoff_moments', []))}\n"
            f"- 高光时刻: {', '.join(qs.get('highlight_moments', []))}\n"
            f"- 总评: {qs.get('overall_comment','')}\n"
        )

    script_block = ""
    if scripts:
        joined = "\n---\n".join(s[:1500] for s in scripts[:3])
        script_block = f"## 口播稿样本（脚本质量参考）\n{joined}\n"

    user = REVIEW_USER_TMPL.format(
        host=host, period_desc=period_desc,
        kpi_block=_kpi_block(rooms),
        funnel_block=_funnel_block(rooms),
        gpm_block=_gpm_block(rooms),
        detail_block=_detail_block(series, granularity),
        quality_block=quality_block,
        script_block=script_block,
    )

    llm = get_reasoner()
    markdown = llm.generate(user, system=REVIEW_SYSTEM)

    return {
        "host": host, "granularity": granularity, "period_desc": period_desc,
        "session_count": len(rooms), "markdown": markdown,
        "kpis": summary_kpis(rooms),
        "series": series,
    }
