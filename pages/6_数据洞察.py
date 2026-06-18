"""数据洞察页 — 自动拉取这场的「直播大屏 + 流量来源」截屏(每约15分钟)，Gemini 读图分析随时间变化。"""
import streamlit as st

import store
import insight_analyze
from zmeng_api import fetch_live_screenshots

st.set_page_config(page_title="数据洞察", page_icon="📊", layout="wide")
st.title("📊 数据洞察（随时间变化）")
st.caption("自动拉取这场每约15分钟的直播大屏(overview)+流量来源(traffic-source)截屏，Gemini 串成时间线：在线/GMV/转化走势、流量来源结构变化、高峰与掉量时段。")

hosts = store.list_hosts()
if not hosts:
    st.info("还没有数据，请先到「数据抓取」页。")
    st.stop()

host = st.selectbox("选择主播", [h["host"] for h in hosts])
rooms = store.load_host_rooms(host)


def _label(r):
    return f"{r.get('_open_time')} · {r.get('_duration')} · GMV${r.get('gmv_usd',0):.0f}"


room = st.selectbox("选择场次", rooms, format_func=_label)

mode = st.radio("截屏来源", ["自动拉取(按场次)", "手动上传", "粘贴 URL"], horizontal=True)

screenshots = []
if mode == "自动拉取(按场次)":
    rid = room.get("_room_id"); did = room.get("_device_id")
    if not did:
        st.warning("该场次缺 deviceId（请到「数据抓取」重新抓一次以补全）。可改用手动上传。")
    if st.button("📥 拉取本场截屏", disabled=not (rid and did)):
        shots = fetch_live_screenshots(rid, did)
        if not shots:
            st.warning("未拉到截屏（该场可能没有数据洞察截屏）。")
        else:
            st.session_state["_insight_shots"] = shots
            st.success(f"拉到 {len(shots)} 张截屏")
    shots = st.session_state.get("_insight_shots", [])
    if shots and shots[0].get("snapshot_url"):
        # 仅当属于当前房间
        n_ov = sum(1 for s in shots if s.get("type") == "overview")
        n_ts = sum(1 for s in shots if s.get("type") == "traffic-source")
        st.caption(f"大屏 {n_ov} 张 · 流量来源 {n_ts} 张")
        cols = st.columns(min(6, len(shots)))
        for i, s in enumerate(shots[:6]):
            cols[i].image(s["snapshot_url"], caption=f"{s.get('create_time','')[-8:]} {s.get('type','')}", use_container_width=True)
        screenshots = shots

elif mode == "手动上传":
    files = st.file_uploader("按时间先后上传", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if files:
        from config import VIDEOS_DIR
        tmp = VIDEOS_DIR / "_insight_upload"; tmp.mkdir(exist_ok=True)
        for i, f in enumerate(files):
            p = tmp / f"shot_{i:02d}_{f.name}"; p.write_bytes(f.read())
            screenshots.append(str(p))
        st.image(files[:6], width=140)
else:
    urls = st.text_area("截屏 URL（每行一个，按时间先后）", height=140)
    screenshots = [u.strip() for u in urls.splitlines() if u.strip()]

if st.button("📊 分析时间线", type="primary", disabled=not screenshots):
    prog = st.empty()
    res = insight_analyze.analyze_insight_screenshots(screenshots, on_progress=lambda m: prog.info(m))
    prog.empty()
    if res.get("error"):
        st.error(res["error"])
    else:
        store.save_analysis(f"{room['_room_id']}_insight", res)
        st.success(res.get("overall_comment", ""))
        c1, c2 = st.columns(2)
        c1.info("**高峰时段**：" + str(res.get("peak_period", "")))
        c2.warning("**掉量时段**：" + "；".join(res.get("drop_periods", [])))
        st.markdown("**流量来源随时间变化**：" + str(res.get("traffic_shift", "")))
        tl = res.get("timeline", [])
        if tl:
            st.subheader("时间线")
            st.dataframe(
                [{"时段": t.get("time"), "在线/趋势": t.get("online"), "成交/趋势": t.get("gmv"),
                  "主要来源": t.get("traffic_source"), "特征": t.get("note")} for t in tl],
                use_container_width=True, hide_index=True)
        st.subheader("关键发现")
        for k in res.get("key_findings", []):
            st.write("•", k)

cached = store.load_analysis(f"{room['_room_id']}_insight")
if cached and not cached.get("error"):
    with st.expander("查看上次时间线分析(JSON)"):
        st.json(cached)
