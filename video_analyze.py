"""录像视觉分析 — 下载 ossUrl 录像，抽帧，用 Gemini(代理,OpenAI兼容) 看画面/声音/互动/脚本四维。

为什么抽帧+代理：官方 Files API 的 Google 直连 key 当前不可用；vectorengine 代理是
OpenAI 兼容层，支持多图 base64 视觉输入。所以策略是 ffmpeg 抽关键帧 → base64 多图喂
Gemini。音频维度(声音)用可选 ASR 转写补充（faster-whisper）。
"""
import json
import re
import base64
import subprocess
import urllib.request
from pathlib import Path

from config import (VIDEOS_DIR, GOOGLE_PROXY_KEY, GOOGLE_PROXY_URL, LOCAL_PROXY,
                    FRAME_INTERVAL_S, get_default_models)
from prompts import QUALITY_RUBRIC

# 代理上验证可用的视觉模型（按优先级回退）
_VISION_MODELS = ["gemini-3-flash-preview", "gemini-2.5-flash"]


def download_recording(oss_url: str, room_id: str) -> Path | None:
    if not oss_url:
        return None
    dest = VIDEOS_DIR / f"{room_id}.mp4"
    if dest.exists() and dest.stat().st_size > 10000:
        return dest
    try:
        proxy = urllib.request.ProxyHandler({"http": LOCAL_PROXY, "https": LOCAL_PROXY})
        opener = urllib.request.build_opener(proxy)
        opener.addheaders = [("User-Agent", "Mozilla/5.0")]
        with opener.open(oss_url, timeout=180) as resp, open(dest, "wb") as f:
            f.write(resp.read())
        return dest if dest.stat().st_size > 10000 else None
    except Exception:
        return None


def extract_frames(video_path: Path, room_id: str, interval_s: int = None, max_frames: int = 24) -> list[Path]:
    interval_s = interval_s or FRAME_INTERVAL_S
    frame_dir = VIDEOS_DIR / f"{room_id}_frames"
    frame_dir.mkdir(exist_ok=True)
    existing = sorted(frame_dir.glob("frame_*.jpg"))
    if not existing:
        try:
            subprocess.run(
                ["ffmpeg", "-i", str(video_path), "-vf", f"fps=1/{interval_s},scale=512:-1",
                 "-q:v", "5", str(frame_dir / "frame_%04d.jpg"), "-y"],
                capture_output=True, timeout=300,
            )
        except Exception:
            return []
        existing = sorted(frame_dir.glob("frame_*.jpg"))
    return existing[:max_frames]


def transcribe_audio(video_path: Path, room_id: str) -> str:
    """可选：faster-whisper 转写音频（用于「声音」维度）。失败返回空串。"""
    try:
        from faster_whisper import WhisperModel
        from config import WHISPER_MODEL
        model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(video_path), beam_size=1)
        return " ".join(s.text for s in segments)[:4000]
    except Exception:
        return ""


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def analyze_recording(oss_url: str, room_id: str, model: str = "",
                      with_transcript: bool = False, on_progress=None) -> dict | None:
    """下载录像 → 抽帧(+可选转写) → Gemini 代理四维分析 → 结构化评分 dict。"""
    def log(m):
        if on_progress:
            on_progress(m)

    import httpx
    from openai import OpenAI

    log("下载录像...")
    vp = download_recording(oss_url, room_id)
    if not vp:
        return {"error": "录像下载失败或无录像"}

    log("抽帧...")
    frames = extract_frames(vp, room_id)
    if not frames:
        return {"error": "抽帧失败（检查 ffmpeg 是否安装）"}

    transcript = ""
    if with_transcript:
        log("音频转写(可能较慢)...")
        transcript = transcribe_audio(vp, room_id)

    # 构造多图 + 文本消息
    content = [{"type": "text", "text":
                f"以下是一段 TikTok 带货直播录像按时间顺序抽取的 {len(frames)} 张关键帧"
                f"（每帧间隔约 {FRAME_INTERVAL_S} 秒）。"
                + (f"\n\n【音频转写】\n{transcript}\n" if transcript else "")
                + "\n\n" + QUALITY_RUBRIC}]
    for fp in frames:
        b64 = base64.b64encode(fp.read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    client = OpenAI(api_key=GOOGLE_PROXY_KEY, base_url=f"{GOOGLE_PROXY_URL}/v1",
                    http_client=httpx.Client(timeout=300, proxy=None))

    models_to_try = [model] if model else _VISION_MODELS
    last_err = ""
    for mdl in models_to_try:
        log(f"Gemini({mdl}) 分析 {len(frames)} 帧...")
        for attempt in range(2):
            try:
                resp = client.chat.completions.create(
                    model=mdl, messages=[{"role": "user", "content": content}],
                    max_tokens=4096)
                result = _parse_json(resp.choices[0].message.content)
                if result:
                    result["_model"] = mdl
                    result["_frames"] = len(frames)
                    result["_has_transcript"] = bool(transcript)
                    return result
                last_err = "返回无法解析为JSON"
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:100]}"
                import time
                time.sleep(2)
    return {"error": f"分析失败: {last_err}"}
