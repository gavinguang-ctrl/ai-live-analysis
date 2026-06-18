"""趋势对比页 — 周/月趋势线 + 主播间 KPI 横向对比。"""
import streamlit as st
import plotly.graph_objects as go

import store
from aggregate import aggregate, summary_kpis

st.set_page_config(page_title="趋势对比", page_icon="📈", layout="wide")
st.title("📈 趋势对比")

hosts = store.list_hosts()
if not hosts:
    st.info("还没有数据，请先到「数据抓取」页。")
    st.stop()

tab1, tab2 = st.tabs(["单主播趋势", "主播间对比"])

with tab1:
    host = st.selectbox("主播", [h["host"] for h in hosts], key="trend_host")
    gran_label = st.radio("粒度", ["按天", "按周", "按月"], horizontal=True)
    gran = {"按天": "day", "按周": "week", "按月": "month"}[gran_label]
    rooms = store.load_host_rooms(host)
    series = aggregate(rooms, gran)
    if not series:
        st.warning("无足够数据")
    else:
        metrics = st.multiselect("对比指标", ["gmv_usd", "ctr", "dwell_time", "order_rate", "gpm", "roi", "views", "follow_rate"],
                                 default=["gmv_usd", "ctr", "order_rate"],
                                 format_func=lambda x: {"gmv_usd": "GMV(USD)", "ctr": "CTR", "dwell_time": "停留",
                                                        "order_rate": "下单率", "gpm": "GPM", "roi": "ROI",
                                                        "views": "场观", "follow_rate": "转粉率"}.get(x, x))
        fig = go.Figure()
        for m in metrics:
            fig.add_trace(go.Scatter(x=[s["period"] for s in series],
                                     y=[s.get(m, 0) for s in series], mode="lines+markers", name=m))
        fig.update_layout(height=400, margin=dict(t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            [{"周期": s["period"], "场次": s["session_count"], "GMV$": round(s.get("gmv_usd", 0)),
              "CTR%": round(s.get("ctr", 0) * 100, 2), "停留s": round(s.get("dwell_time", 0)),
              "下单率%": round(s.get("order_rate", 0) * 100, 2), "GPM": round(s.get("gpm", 0), 1),
              "ROI": round(s.get("roi", 0), 1)} for s in series],
            use_container_width=True, hide_index=True,
        )

with tab2:
    sel = st.multiselect("选择主播对比", [h["host"] for h in hosts],
                         default=[h["host"] for h in hosts[:min(5, len(hosts))]])
    if sel:
        rows = []
        for h in sel:
            k = summary_kpis(store.load_host_rooms(h))
            rows.append({"主播": h, "场次": k["session_count"], "总GMV$": round(k["total_gmv_usd"]),
                         "整体GPM$": round(k["gpm_usd_overall"], 2), "平均CTR%": round(k["avg_ctr"] * 100, 2),
                         "平均停留s": round(k["avg_dwell"]), "平均下单率%": round(k["avg_order_rate"] * 100, 2),
                         "平均ROI": round(k["avg_roi"], 2)})
        st.dataframe(rows, use_container_width=True, hide_index=True)
        # 柱状对比
        metric = st.selectbox("对比维度", ["总GMV$", "整体GPM$", "平均CTR%", "平均停留s", "平均下单率%", "平均ROI"])
        bfig = go.Figure(go.Bar(x=[r["主播"] for r in rows], y=[r[metric] for r in rows]))
        bfig.update_layout(height=350, margin=dict(t=20, b=10), title=metric)
        st.plotly_chart(bfig, use_container_width=True)
