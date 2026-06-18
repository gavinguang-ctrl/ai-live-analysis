"""自动复盘编排 — 抓取后一键跑：benchmark → 三类来源深度分析(benchmark+最近场) →
时间维度 → Opus 4.8 综合复盘 + TODO。无需手点各页。
"""
import json
import re

import store
from aggregate import aggregate, summary_kpis
import benchmark as bm
import time_analysis as ta
from analysis_engine import (_kpi_block, _funnel_block, _gpm_block, _detail_block,
                             analyze_script)
from prompts import SYNTH_SYSTEM, SYNTH_USER_TMPL, fmt_val


def _benchmark_block(bench: dict) -> str:
    if not bench:
        return "(无可用基准场)"
    return (f"- 时间: {bench.get('_open_time')} · 时长 {bench.get('_duration')} · 综合分 {bench.get('_score')}\n"
            f"- GMV(USD): ${bench.get('gmv_usd',0):,.0f} · GPM: {bench.get('gpm',0):.1f} · "
            f"下单率: {bench.get('order_rate',0)*100:.2f}% · CTR: {bench.get('ctr',0)*100:.2f}% · "
            f"停留: {bench.get('dwell_time',0):.0f}s · ROI: {bench.get('roi',0):.1f}")


def _regression_block(reg: dict, bench: dict) -> str:
    if not reg or reg.get("after_count", 0) == 0:
        return "(benchmark 之后暂无场次)"
    lines = [f"benchmark 之后共 {reg['after_count']} 场，对比 benchmark 仍偏低的指标(从最差排起):"]
    for g in reg.get("gaps", [])[:8]:
        lines.append(f"- {g['name']}: 后续均值 {fmt_val(g['after_avg'], g['fmt'])} "
                     f"vs 基准 {fmt_val(g['bench'], g['fmt'])}（差 {g['gap_pct']:.0f}%）")
    return "\n".join(lines)


def _timeline_block(insight: dict, decay: dict) -> str:
    if not insight or insight.get("error"):
        return ""
    lines = ["## 单场数据洞察时间线（最近一场，随时间变化）"]
    for t in insight.get("timeline", [])[:8]:
        lines.append(f"- {t.get('time')}: 在线{t.get('online')} / 成交{t.get('gmv')} / "
                     f"来源 {t.get('traffic_source')} — {t.get('note','')[:50]}")
    if insight.get("peak_period"):
        lines.append(f"高峰: {insight['peak_period']}")
    if insight.get("drop_periods"):
        lines.append("掉量: " + "；".join(insight["drop_periods"]))
    if insight.get("traffic_shift"):
        lines.append(f"流量来源变化: {insight['traffic_shift']}")
    if decay and decay.get("suggest_close"):
        lines.append(f"⏱ 衰减推断: {decay['suggest_close']} 起建议关播（{'；'.join(decay.get('reasons',[]))}）")
    return "\n".join(lines)


def _video_block(video: dict) -> str:
    if not video or video.get("error"):
        return ""
    return ("## 最近一场录像（画面/声音质量 · 数字人+TTS前提）\n"
            f"- 画面: {video.get('visual',{}).get('score','?')}/10 — "
            + "；".join(video.get('visual', {}).get('observations', [])[:2]) + "\n"
            f"- 声音: {video.get('audio',{}).get('score','?')}/10 — "
            + "；".join(video.get('audio', {}).get('observations', [])[:2]) + "\n"
            f"- AI暴露/限流风险: {video.get('ai_exposure','?')}\n"
            f"- TTS拟真度: {video.get('tts_naturalness','?')}\n"
            f"- 数字人可调优点: " + "；".join(video.get('avatar_tuning', [])[:3]) + "\n"
            f"- 总评: {video.get('overall_comment','')}")


def _script_block(script: dict) -> str:
    if not script:
        return ""
    if script.get("raw"):
        return "## 脚本分析\n" + script["raw"][:800]
    return ("## 脚本分析（最佳场脚本）\n"
            f"- 评分: {script.get('score','?')}/10\n"
            f"- 问题: " + "；".join(script.get("problems", [])[:4]) + "\n"
            f"- 缺失环节: " + "；".join(script.get("missing", [])[:4]) + "\n"
            f"- 改写建议: " + "；".join(script.get("rewrite_suggestions", [])[:3]))


def auto_analyze(host: str, granularity: str = "week",
                 deep_video: bool = True, deep_insight: bool = True,
                 deep_script: bool = True, on_progress=None) -> dict:
    """抓取后自动综合复盘。

    流程：
      1. 载入该主播全部场次
      2. 选历史最佳场(benchmark) + 回归差距
      3. 时间维度(最佳开播时段)
      4. 深度分析：最佳场脚本 + 最近场录像 + 最近场数据洞察时间线
      5. Opus 4.8 综合所有维度 → 复盘 + TODO（含开播/关播时机）
    返回 {markdown, benchmark, regression, time_slots, video, insight, decay, kpis}。
    """
    from llm import get_reasoner
    from zmeng_api import fetch_task_content, fetch_live_screenshots
    import video_analyze
    import insight_analyze

    def log(m):
        if on_progress:
            on_progress(m)

    rooms = store.load_host_rooms(host)
    if not rooms:
        return {"error": "无场次数据"}

    log("计算 benchmark...")
    bench = bm.pick_benchmark(rooms)
    reg = bm.regression_summary(rooms, bench) if bench else {}

    log("分析最佳开播时段...")
    slots = ta.best_time_slots(rooms)

    # 最近一场（按开播时间）
    recent = max(rooms, key=lambda r: r.get("_open_time", ""))

    # 深度：最佳场脚本
    script_res = None
    if deep_script and bench and bench.get("_gemini_task_id"):
        log("分析最佳场脚本(Opus)...")
        try:
            tc = fetch_task_content(bench["_gemini_task_id"], proxies={"http": None, "https": None})
            if tc and tc.get("scripts"):
                text = "\n\n".join(s["content"] for s in tc["scripts"][:3])
                script_res = analyze_script(text)
                store.save_analysis(f"{bench['_room_id']}_script", script_res)
        except Exception as e:
            log(f"脚本分析跳过: {e}")

    # 深度：最近场数据洞察时间线
    insight_res, decay = None, {}
    if deep_insight and recent.get("_room_id") and recent.get("_device_id"):
        log("拉取并分析最近场数据洞察时间线(Gemini)...")
        try:
            shots = fetch_live_screenshots(recent["_room_id"], recent["_device_id"],
                                           proxies={"http": None, "https": None})
            if shots:
                insight_res = insight_analyze.analyze_insight_screenshots(shots, on_progress=log)
                if insight_res and not insight_res.get("error"):
                    store.save_analysis(f"{recent['_room_id']}_insight", insight_res)
                    decay = ta.session_timeline_decay(insight_res.get("timeline", []))
        except Exception as e:
            log(f"数据洞察跳过: {e}")

    # 深度：最近场录像（画面/声音）
    video_res = None
    if deep_video and recent.get("_oss_url"):
        log("分析最近场录像画面/声音(Gemini)...")
        try:
            video_res = video_analyze.analyze_recording(recent["_oss_url"], recent["_room_id"],
                                                        with_transcript=False, on_progress=log)
            if video_res and not video_res.get("error"):
                store.save_analysis(f"{recent['_room_id']}_video", video_res)
        except Exception as e:
            log(f"录像分析跳过: {e}")

    # 组装并跑 Opus 综合复盘
    log("Opus 4.8 综合复盘中...")
    series = aggregate(rooms, granularity)
    period_desc = (f"共{len(rooms)}场，{series[0]['period'] if series else ''} ~ "
                   f"{series[-1]['period'] if series else ''}")
    user = SYNTH_USER_TMPL.format(
        host=host, period_desc=period_desc,
        kpi_block=_kpi_block(rooms),
        funnel_block=_funnel_block(rooms),
        gpm_block=_gpm_block(rooms),
        benchmark_block=_benchmark_block(bench),
        regression_block=_regression_block(reg, bench),
        time_block=ta.fmt_slot_block(slots),
        timeline_block=_timeline_block(insight_res, decay),
        video_block=_video_block(video_res),
        script_block=_script_block(script_res),
        detail_block=_detail_block(series, granularity),
    )
    markdown = get_reasoner().generate(user, system=SYNTH_SYSTEM)

    result = {
        "host": host, "granularity": granularity, "period_desc": period_desc,
        "markdown": markdown, "kpis": summary_kpis(rooms),
        "benchmark": {k: bench.get(k) for k in ("_room_id", "_open_time", "_score",
                      "gmv_usd", "gpm", "order_rate", "ctr", "dwell_time", "roi")} if bench else None,
        "regression": reg, "time_slots": slots,
        "video": video_res, "insight": insight_res, "decay": decay, "script": script_res,
        "recent_room": recent.get("_room_id"),
    }
    store.save_analysis(f"{host}_auto", result)
    log("完成")
    return result

