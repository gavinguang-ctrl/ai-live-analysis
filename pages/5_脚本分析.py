"""脚本分析页 — 取「查看脚本」的口播稿(geminiTaskId)，用 Opus 4.8 看脚本问题。"""
import streamlit as st

import store
from zmeng_api import fetch_task_content
import analysis_engine

st.set_page_config(page_title="脚本分析", page_icon="📝", layout="wide")
st.title("📝 脚本分析（本场脚本的问题）")
st.caption("来源：众盟「查看脚本」的口播稿。分析循环结构 / 开场hook / 留人 / FABE / 价格锚点 / 逼单 / CTA。")

hosts = store.list_hosts()
if not hosts:
    st.info("还没有数据，请先到「数据抓取」页。")
    st.stop()

host = st.selectbox("选择主播", [h["host"] for h in hosts])
rooms = store.load_host_rooms(host)
script_rooms = [r for r in rooms if r.get("_gemini_task_id")]
if not script_rooms:
    st.warning("该主播没有带脚本(geminiTaskId)的场次。")
    st.stop()


def _label(r):
    return f"{r.get('_open_time')} · GMV${r.get('gmv_usd',0):.0f} · 停留{r.get('dwell_time',0):.0f}s"


room = st.selectbox("选择场次（有脚本）", script_rooms, format_func=_label)

src = st.radio("分析对象", ["整份脚本拼接", "选择单条脚本"], horizontal=True)

if st.button("📝 拉取并分析脚本", type="primary"):
    with st.spinner("拉取脚本..."):
        tc = fetch_task_content(room["_gemini_task_id"])
    if not tc or not tc.get("scripts"):
        st.error("未取到脚本内容")
        st.stop()
    st.caption(f"任务：{tc.get('task_name','')} · 共 {tc['script_count']} 条脚本")

    if src == "整份脚本拼接":
        text = "\n\n".join(s["content"] for s in tc["scripts"])
    else:
        idx = st.session_state.get("_script_idx", 0)
        text = tc["scripts"][min(idx, len(tc["scripts"]) - 1)]["content"]

    with st.expander("脚本原文"):
        st.text(text[:5000])

    with st.spinner("Opus 4.8 分析脚本中..."):
        res = analysis_engine.analyze_script(text)
        store.save_analysis(f"{room['_room_id']}_script", res)

    if res.get("raw"):
        st.markdown(res["raw"])
    else:
        st.metric("脚本评分", f"{res.get('score','?')}/10")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("❌ 存在的问题")
            for p in res.get("problems", []):
                st.write("•", p)
            st.subheader("⚠️ 缺失的关键环节")
            for m in res.get("missing", []):
                st.write("•", m)
        with c2:
            st.subheader("✅ 做得好的点")
            for g in res.get("good_points", []):
                st.write("•", g)
            st.subheader("✍️ 改写建议")
            for r in res.get("rewrite_suggestions", []):
                st.write("•", r)

cached = store.load_analysis(f"{room['_room_id']}_script")
if cached:
    with st.expander("查看上次脚本分析(JSON)"):
        st.json(cached)
