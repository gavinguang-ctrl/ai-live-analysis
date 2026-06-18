"""录像分析页 — Gemini 看录像，聚焦画面/声音质量（前提：AI数字人+TTS，给调优方向）。"""
import streamlit as st

import store
import video_analyze

st.set_page_config(page_title="录像分析", page_icon="🎬", layout="wide")
st.title("🎬 录像分析（画面 & 声音质量）")
st.caption("前提：本账号全是 AI 数字人+TTS。从录像评判画面/声音质量，给出数字人形象与 TTS 拟真度的调优方向、降低限流风险。脚本见「脚本分析」，数据走势见「数据洞察」。")

hosts = store.list_hosts()
if not hosts:
    st.info("还没有数据，请先到「数据抓取」页。")
    st.stop()

host = st.selectbox("选择主播", [h["host"] for h in hosts])
rooms = store.load_host_rooms(host)
rec_rooms = [r for r in rooms if r.get("_oss_url")]
if not rec_rooms:
    st.warning("该主播没有带录像的场次。")
    st.stop()


def _label(r):
    return f"{r.get('_open_time')} · {r.get('_duration')} · GMV${r.get('gmv_usd',0):.0f}"


room = st.selectbox("选择场次（有录像）", rec_rooms, format_func=_label)
with_tx = st.checkbox("同时转写音频（评估 TTS 拟真度更准，但较慢）", value=True)
if st.checkbox("预览录像"):
    st.video(room["_oss_url"])

if st.button("🎬 分析录像", type="primary"):
    prog = st.empty()
    res = video_analyze.analyze_recording(room["_oss_url"], room["_room_id"],
                                          with_transcript=with_tx,
                                          on_progress=lambda m: prog.info(m))
    prog.empty()
    if res.get("error"):
        st.error(res["error"])
        if res.get("raw"):
            st.code(res["raw"])
    else:
        store.save_analysis(f"{room['_room_id']}_video", res)
        c1, c2 = st.columns(2)
        c1.metric("画面质量", f"{res.get('visual',{}).get('score','?')}/10")
        c2.metric("声音质量", f"{res.get('audio',{}).get('score','?')}/10")

        c3, c4 = st.columns(2)
        exposure = res.get("ai_exposure", "")
        tts = res.get("tts_naturalness", "")
        (c3.warning if exposure.startswith(("高", "中")) else c3.success)(f"**AI暴露/限流风险**：{exposure}")
        c4.info(f"**TTS 拟真度**：{tts}")

        with st.expander(f"画面观察 — {res.get('visual',{}).get('score','?')}/10", expanded=True):
            for o in res.get("visual", {}).get("observations", []):
                st.write("•", o)
        with st.expander(f"声音观察 — {res.get('audio',{}).get('score','?')}/10", expanded=True):
            for o in res.get("audio", {}).get("observations", []):
                st.write("•", o)
        if res.get("avatar_tuning"):
            st.subheader("🛠 数字人/TTS 可调优点")
            for t in res.get("avatar_tuning", []):
                st.write("•", t)
        st.info(res.get("overall_comment", ""))
        st.caption(f"模型 {res.get('_model')} · {res.get('_frames')} 帧 · 转写 {'有' if res.get('_has_transcript') else '无'}")

cached = store.load_analysis(f"{room['_room_id']}_video")
if cached and not cached.get("error"):
    with st.expander("查看上次分析结果(JSON)"):
        st.json(cached)
