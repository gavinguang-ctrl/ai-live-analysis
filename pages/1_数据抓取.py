"""数据抓取页 — 输入主播 id + 日期范围，抓取该主播全部直播间数据。"""
import streamlit as st
from datetime import date, timedelta

import config
from zmeng_api import fetch_host_rooms, fetch_rooms_by_ids
import store

st.set_page_config(page_title="数据抓取", page_icon="📥", layout="wide")
st.title("📥 数据抓取")
st.caption("按主播 id（hostName）抓取全部直播场次，含全量指标 + 录像 URL")

mode = st.radio("抓取方式", ["按主播 id", "按直播间 id 列表"], horizontal=True)

proxies = None  # 众盟 API 国内可直连

if mode == "按主播 id":
    col1, col2, col3 = st.columns([2, 1, 1])
    host = col1.text_input("主播 id（hostName）", placeholder="如 sayangbody.vn")
    start = col2.date_input("开始日期", value=date.today() - timedelta(days=30))
    end = col3.date_input("结束日期", value=date.today())

    cc1, cc2, cc3 = st.columns([1, 1, 2])
    auto = cc1.checkbox("抓取后自动复盘", value=True)
    deep = cc2.checkbox("含录像/截屏深度分析", value=True,
                        help="对历史最佳场脚本 + 最近场录像/数据洞察做多模态分析")
    gran = cc3.selectbox("复盘粒度", ["week", "day", "month", "session"],
                         format_func=lambda x: {"week": "按周", "day": "按天", "month": "按月", "session": "按场次"}[x])

    if st.button("🚀 开始抓取", type="primary", disabled=not host):
        prog = st.empty()
        rooms = fetch_host_rooms(host.strip(), start_date=str(start), end_date=str(end),
                                 proxies=proxies, on_progress=lambda m: prog.info(m))
        if rooms:
            store.save_host_rooms(host.strip(), rooms)
            prog.success(f"✅ 抓取并保存 {len(rooms)} 场")
            n_rec = sum(1 for r in rooms if r.get("_oss_url"))
            n_script = sum(1 for r in rooms if r.get("_gemini_task_id"))
            st.write(f"其中 {n_rec} 场有录像、{n_script} 场有脚本")
            st.dataframe(
                [{"开播": r.get("_open_time"), "时长": r.get("_duration"),
                  "场观": r.get("views"), "GMV$": round(r.get("gmv_usd", 0), 1),
                  "CTR": f"{r.get('ctr',0)*100:.1f}%", "停留s": round(r.get("dwell_time", 0)),
                  "录像": "✓" if r.get("_oss_url") else ""} for r in rooms],
                use_container_width=True, hide_index=True,
            )
            # ===== 抓取后自动综合复盘 =====
            if auto:
                st.divider()
                st.subheader("🧠 自动综合复盘（Opus 4.8 + Gemini）")
                aprog = st.empty()
                import orchestrator
                with st.spinner("自动分析中：benchmark → 录像/脚本/数据洞察 → 综合复盘…（约 1-3 分钟）"):
                    res = orchestrator.auto_analyze(
                        host.strip(), granularity=gran,
                        deep_video=deep, deep_insight=deep, deep_script=deep,
                        on_progress=lambda m: aprog.info(m))
                aprog.empty()
                if res.get("error"):
                    st.error(res["error"])
                else:
                    st.markdown(res["markdown"])
                    st.success("已生成，可到「主播复盘」页随时查看。")
        else:
            prog.error("未抓到数据。检查主播 id、日期范围、或 Token 是否有效。")

else:
    ids = st.text_area("直播间 id 列表（每行一个）", height=120)
    if st.button("🚀 抓取", type="primary", disabled=not ids.strip()):
        id_list = [x.strip() for x in ids.splitlines() if x.strip()]
        rooms = fetch_rooms_by_ids(id_list, proxies=proxies)
        if rooms:
            # 按主播分组保存
            by_host = {}
            for r in rooms:
                by_host.setdefault(r.get("_host", "unknown"), []).append(r)
            for h, rs in by_host.items():
                store.save_host_rooms(h, rs)
            st.success(f"✅ 抓取 {len(rooms)} 场，归入 {len(by_host)} 个主播")
        else:
            st.error("未抓到数据")
