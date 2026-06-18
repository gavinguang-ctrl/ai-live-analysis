"""数据洞察截屏分析 — 读取一场直播的「每15分钟大屏 + 流量来源」截屏，
用 Gemini 读图串成时间线，分析这场随时间的变化。

截屏来源：众盟「数据洞察」页（接口待接入；当前支持 URL 列表 / 本地图片路径）。
"""
import json
import re
import base64
import urllib.request
from pathlib import Path

from config import GOOGLE_PROXY_KEY, GOOGLE_PROXY_URL, LOCAL_PROXY, VIDEOS_DIR
from prompts import INSIGHT_SYSTEM, INSIGHT_USER

_VISION_MODELS = ["gemini-3-flash-preview", "gemini-2.5-flash"]


def _img_to_b64(src: str) -> str | None:
    """src 可以是本地路径或 http(s) URL。返回 base64。
    众盟截屏在阿里云 cn-beijing OSS，直连即可（先直连，失败再走代理）。"""
    try:
        if src.startswith("http"):
            data = None
            for proxy in (None, {"http": LOCAL_PROXY, "https": LOCAL_PROXY}):
                try:
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler(proxy or {}))
                    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
                    data = opener.open(src, timeout=60).read()
                    if data and len(data) >= 200:
                        break
                except Exception:
                    data = None
            if not data:
                return None
        else:
            data = Path(src).read_bytes()
        if len(data) < 200:
            return None
        return base64.b64encode(data).decode()
    except Exception:
        return None


def _mime(src: str) -> str:
    return "image/png" if src.lower().endswith(".png") else "image/jpeg"


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def analyze_insight_screenshots(screenshots: list, model: str = "",
                                on_progress=None) -> dict:
    """screenshots: 按时间先后排列的截屏列表。每项可为:
       - str: 本地路径或 URL
       - dict: {snapshot_url|path, type(overview/traffic-source), create_time}

    返回时间线分析 dict（见 prompts.INSIGHT_USER 的 JSON schema）。
    """
    def log(m):
        if on_progress:
            on_progress(m)

    if not screenshots:
        return {"error": "没有截屏可分析"}

    import httpx
    from openai import OpenAI

    # 归一化为 [{src, type, time}]
    norm = []
    for s in screenshots:
        if isinstance(s, dict):
            norm.append({"src": s.get("snapshot_url") or s.get("path") or s.get("src", ""),
                         "type": s.get("type", ""), "time": s.get("create_time", "")})
        else:
            norm.append({"src": s, "type": "", "time": ""})

    log(f"加载 {len(norm)} 张截屏...")
    content = [{"type": "text", "text": INSIGHT_SYSTEM + "\n\n" + INSIGHT_USER}]
    loaded = 0
    _TYPE_CN = {"overview": "直播大屏", "traffic-source": "流量来源"}
    for i, item in enumerate(norm):
        b64 = _img_to_b64(item["src"])
        if not b64:
            continue
        tlabel = item["time"] or f"第{(i+1)*15}分钟(估)"
        tylabel = _TYPE_CN.get(item["type"], item["type"] or "截屏")
        content.append({"type": "text", "text": f"[{tlabel} · {tylabel}]"})
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:{_mime(item['src'])};base64,{b64}"}})
        loaded += 1
    if loaded == 0:
        return {"error": "所有截屏加载失败"}

    client = OpenAI(api_key=GOOGLE_PROXY_KEY, base_url=f"{GOOGLE_PROXY_URL}/v1",
                    http_client=httpx.Client(timeout=300, proxy=None))
    models_to_try = [model] if model else _VISION_MODELS
    last_err = ""
    for mdl in models_to_try:
        log(f"Gemini({mdl}) 读 {loaded} 张截屏分析时间线...")
        for attempt in range(2):
            try:
                resp = client.chat.completions.create(
                    model=mdl, messages=[{"role": "user", "content": content}],
                    max_tokens=4096)
                result = _parse_json(resp.choices[0].message.content)
                if result:
                    result["_model"] = mdl
                    result["_shots"] = loaded
                    return result
                last_err = "返回无法解析为JSON"
            except Exception as e:
                import time
                last_err = f"{type(e).__name__}: {str(e)[:100]}"
                time.sleep(2)
    return {"error": f"分析失败: {last_err}"}
