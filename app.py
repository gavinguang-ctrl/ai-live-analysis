"""AI Analysis — TikTok 直播带货复盘工具。首页：API 配置 + 概览。"""
import streamlit as st
import json

import config
from zmeng_api import check_token
import store

st.set_page_config(page_title="AI 直播复盘分析", page_icon="📊", layout="wide")

st.title("📊 TikTok 直播带货 AI 复盘分析")
st.caption("众盟 API 数据 + Gemini 看录像 + Opus 4.8 复盘推理 · 以主播为粒度，输出可执行优化 TODO")

# ===== 概览 =====
hosts = store.list_hosts()
col1, col2, col3 = st.columns(3)
col1.metric("已抓取主播数", len(hosts))
col2.metric("累计场次", sum(h["count"] for h in hosts))
ok, msg = check_token() if config.ZMENG_AUTH_TOKEN else (False, "未配置")
col3.metric("众盟 Token", "✅ 有效" if ok else "❌ 失效")

if hosts:
    st.subheader("已抓取的主播")
    st.dataframe(
        [{"主播": h["host"], "场次": h["count"], "更新时间": h["updated_at"]} for h in hosts],
        use_container_width=True, hide_index=True,
    )
else:
    st.info("还没有数据。请到左侧「数据抓取」页输入主播 id 抓取直播数据。")

st.divider()

# ===== API 配置面板 =====
with st.expander("⚙️ API 配置（保存到 config.json）", expanded=not ok):
    cfg = {}
    if config.CONFIG_PATH.exists():
        try:
            cfg = json.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

    st.markdown("**众盟 API**（Token 会过期，失效时在此更新）")
    zt = st.text_area("ZMENG_AUTH_TOKEN", value=cfg.get("ZMENG_AUTH_TOKEN", ""), height=68)
    zc = st.text_input("ZMENG_COOKIE（可选）", value=cfg.get("ZMENG_COOKIE", ""))

    st.markdown("**Anthropic（复盘推理 Opus 4.8）**")
    ak = st.text_input("ANTHROPIC_API_KEY", value=cfg.get("ANTHROPIC_API_KEY", ""), type="password")
    au = st.text_input("ANTHROPIC_PROXY_URL", value=cfg.get("ANTHROPIC_PROXY_URL", ""))

    st.markdown("**Google（看录像 Gemini）**")
    gk = st.text_input("GOOGLE_API_KEY", value=cfg.get("GOOGLE_API_KEY", ""), type="password")
    gpk = st.text_input("GOOGLE_PROXY_KEY", value=cfg.get("GOOGLE_PROXY_KEY", ""), type="password")
    gpu = st.text_input("GOOGLE_PROXY_URL", value=cfg.get("GOOGLE_PROXY_URL", ""))

    st.markdown("**本地代理**（下载海外录像 / Gemini 直连用，填本机 Clash/V2Ray 端口）")
    lp = st.text_input("LOCAL_PROXY", value=cfg.get("LOCAL_PROXY", "http://127.0.0.1:7890"))

    c1, c2 = st.columns(2)
    reasoner = c1.text_input("复盘模型", value=cfg.get("DEFAULT_REASONER", "anthropic/claude-opus-4-8"))
    vision = c2.text_input("视频模型", value=cfg.get("DEFAULT_VISION", "google（代理）/gemini-3.1-pro-preview"))

    if st.button("💾 保存配置", type="primary"):
        config.save_config({
            "ZMENG_AUTH_TOKEN": zt.strip(), "ZMENG_COOKIE": zc.strip(),
            "ANTHROPIC_API_KEY": ak.strip(), "ANTHROPIC_PROXY_URL": au.strip(),
            "GOOGLE_API_KEY": gk.strip(), "GOOGLE_PROXY_KEY": gpk.strip(),
            "GOOGLE_PROXY_URL": gpu.strip(), "LOCAL_PROXY": lp.strip(),
            "DEFAULT_REASONER": reasoner.strip(), "DEFAULT_VISION": vision.strip(),
        })
        st.success("已保存。刷新页面生效。")
        st.rerun()
