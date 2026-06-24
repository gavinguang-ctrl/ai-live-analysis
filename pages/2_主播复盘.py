"""主播复盘页 — 展示自动综合复盘结果(benchmark对比/时间维度/开播关播时机/TODO)。
支持多选主播合并分析（同一产品多主播场景）。"""
import streamlit as st
import plotly.graph_objects as go

import store
from aggregate import aggregate, summary_kpis, per_host_summary
import orchestrator
import time_analysis as ta

st.set_page_config(page_title="主播复盘", page_icon="🔬", layout="wide")
st.title("🔬 主播综合复盘")

hosts = store.list_hosts()
if not hosts:
    st.info("还没有数据，请先到「数据抓取」页（抓取后会自动复盘）。")
    st.stop()

all_host_names = [h["host"] for h in hosts]
col1, col2, col3 = st.columns([2, 1, 1])
selected = col1.multiselect(
    "选择主播（可多选合并分析，如同一产品多个主播）",
    all_host_names, default=all_host_names[:1],
    help="选 2 个及以上主播会把他们的场次合并分析，并做主播间横向对比")
gran_label = col2.selectbox("时间粒度", ["按周", "按天", "按月", "按场次"])
gran = {"按周": "week", "按天": "day", "按月": "month", "按场次": "session"}[gran_label]
deep = col3.checkbox("深度(录像/截屏)", value=True)

if not selected:
    st.warning("请至少选择一个主播。")
    st.stop()

multi = len(selected) > 1
host_label = store.group_label(selected)
rooms = store.load_hosts_rooms(selected) if multi else store.load_host_rooms(selected[0])
st.caption(f"{host_label} · 共 {len(rooms)} 场" + (f" · {len(selected)} 个主播合并" if multi else ""))

# ===== KPI 卡片（合并整体）=====
k = summary_kpis(rooms)
cols = st.columns(4)
cols[0].metric("总GMV(USD)", f"${k['total_gmv_usd']:,.0f}")
cols[1].metric("整体GPM(USD)", f"${k['gpm_usd_overall']:.2f}")
cols[2].metric("平均停留", f"{k['avg_dwell']:.0f}秒")
cols[3].metric("平均下单率", f"{k['avg_order_rate']*100:.2f}%")

# ===== 多主播横向对比表 =====
if multi:
    st.subheader("👥 主播横向对比（同一产品）")
    per = per_host_summary(rooms)
    st.dataframe(
        [{"主播": p["host"], "场次": p["session_count"],
          "总GMV$": round(p["total_gmv_usd"]),
          "整体GPM$": round(p["gpm_usd_overall"], 2),
          "平均CTR": f"{p['avg_ctr']*100:.2f}%",
          "平均停留s": round(p["avg_dwell"]),
          "平均下单率": f"{p['avg_order_rate']*100:.2f}%",
          "平均ROI": round(p["avg_roi"], 2)} for p in per],
        use_container_width=True, hide_index=True,
    )
    # 各主播 GMV 对比柱状
    bfig = go.Figure(go.Bar(x=[p["host"] for p in per], y=[p["total_gmv_usd"] for p in per]))
    bfig.update_layout(height=240, margin=dict(t=10, b=10), title="各主播 总GMV(USD)")
    st.plotly_chart(bfig, use_container_width=True)

# ===== 趋势线 =====
series = aggregate(rooms, gran if gran != "session" else "day")
if len(series) > 1:
    metric = st.selectbox("趋势指标", ["gmv_usd", "ctr", "dwell_time", "order_rate", "gpm", "roi"],
                          format_func=lambda x: {"gmv_usd": "GMV(USD)", "ctr": "CTR", "dwell_time": "停留",
                                                 "order_rate": "下单率", "gpm": "GPM", "roi": "ROI"}.get(x, x))
    fig = go.Figure(go.Scatter(x=[s["period"] for s in series], y=[s.get(metric, 0) for s in series],
                               mode="lines+markers"))
    fig.update_layout(height=240, margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

# ===== 最佳开播时段 =====
slots = ta.best_time_slots(rooms)
if slots.get("by_hour"):
    st.subheader("⏰ 最佳开播时段")
    bh, bw = slots.get("best_hour"), slots.get("best_weekday")
    c1, c2 = st.columns(2)
    if bh:
        c1.metric("最佳开播小时", bh["slot"], f"均GMV ${bh['avg_gmv']:.0f}（{bh['sessions']}场）")
    if bw:
        c2.metric("最佳开播星期", bw["slot"], f"均GMV ${bw['avg_gmv']:.0f}（{bw['sessions']}场）")
    hfig = go.Figure(go.Bar(x=[h["slot"] for h in slots["by_hour"]],
                            y=[h["avg_gmv"] for h in slots["by_hour"]]))
    hfig.update_layout(height=220, margin=dict(t=10, b=10), title="各开播小时 均GMV")
    st.plotly_chart(hfig, use_container_width=True)

st.divider()

# ===== 整体复盘报告（单一统一报告：漏斗+三维度+benchmark+时间维度+TODO）=====
cached = store.load_analysis(f"{store.analysis_key(selected)}_auto")
hcol1, hcol2 = st.columns([3, 1])
hcol1.subheader("🧠 整体复盘报告")
cap = "漏斗逐级诊断 + 流量/转化/下单三维度 + benchmark 对比 + 开播/关播时机 + TODO（融合录像/脚本/数据洞察）"
if multi:
    cap = "多主播合并 · 主播横向对比 + " + cap
hcol1.caption(cap)
if hcol2.button("🔄 重新生成", type="primary", key="regen"):
    aprog = st.empty()
    with st.spinner("综合分析中（benchmark/录像/脚本/数据洞察 → Opus 4.8）…"):
        cached = orchestrator.auto_analyze(selected if multi else selected[0],
                                           gran, deep, deep, deep,
                                           on_progress=lambda m: aprog.info(m))
    aprog.empty()

if cached and not cached.get("error"):
    bench = cached.get("benchmark")
    decay = cached.get("decay") or {}
    if bench:
        btag = f"【{bench.get('_host')}】" if multi and bench.get("_host") else ""
        st.info(f"🏆 历史最佳场：{btag}{bench.get('_open_time')} · GMV ${bench.get('gmv_usd',0):,.0f} · "
                f"GPM {bench.get('gpm',0):.1f} · 综合分 {bench.get('_score')}")
    if decay.get("suggest_close"):
        st.warning(f"⏱ 最近一场建议关播时点：{decay['suggest_close']} —— " + "；".join(decay.get("reasons", [])))
    st.markdown(cached.get("markdown", ""))
    with st.expander("原始分析数据(JSON)"):
        st.json({kk: cached.get(kk) for kk in ("benchmark", "regression", "decay", "video", "insight", "script")})
else:
    st.info("还没有复盘报告。点「重新生成」，或到「数据抓取」页抓取（会自动复盘）。")


