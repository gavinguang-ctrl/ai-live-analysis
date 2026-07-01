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
                    FRAME_INTERVAL_S, get_default_models, av_offset_severity)
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


def probe_av_sync(video_path: Path) -> dict:
    """客观音画同步测量：ffprobe 读容器里音轨 vs 视频轨的起始偏移与时长漂移。
    这是“音画布不同步(muxing 层)”的确定性证据，与后面视觉模型判的口型无关。

    返回 {offset_ms, duration_drift_ms, video_start, audio_start, level, severity, score}。
    offset_ms>0 表示音频相对视频滞后(晚开始)，<0 表示音频超前。severity/score 见 config.av_offset_severity。
    无法测量(无 ffprobe / 无音轨 / 解析失败)时 severity=None。
    """
    out = {"offset_ms": None, "duration_drift_ms": None,
           "video_start": None, "audio_start": None, **av_offset_severity(None)}
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,start_time,duration", "-of", "json", str(video_path)],
            capture_output=True, timeout=60, text=True,
        )
        data = json.loads(proc.stdout or "{}")
    except Exception:
        return out

    v = a = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and v is None:
            v = s
        elif s.get("codec_type") == "audio" and a is None:
            a = s
    if not v or not a:
        return out  # 缺音轨或视频轨，无法比对

    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    vs, as_ = _f(v.get("start_time")), _f(a.get("start_time"))
    vd, ad = _f(v.get("duration")), _f(a.get("duration"))
    if vs is None or as_ is None:
        return out
    offset_ms = (as_ - vs) * 1000.0                       # +：音频晚于画面开始（滞后）
    drift_ms = ((ad - vd) * 1000.0) if (vd is not None and ad is not None) else None
    out.update({"offset_ms": round(offset_ms, 1),
                "duration_drift_ms": round(drift_ms, 1) if drift_ms is not None else None,
                "video_start": round(vs, 4), "audio_start": round(as_, 4)})
    out.update(av_offset_severity(offset_ms))             # level/severity/score 用带符号偏移的绝对值
    out["offset_ms"] = round(offset_ms, 1)                # 保留符号，覆盖 helper 里取的绝对值
    return out


def extract_burst_frames(video_path: Path, room_id: str, fps: int = 5,
                         burst_s: int = 2, num_bursts: int = 3,
                         max_frames: int = 30) -> list[Path]:
    """为口型/发音吻合度抽“连续帧突发段”：在录像的前/中/后各取一小段，按高帧率(默认5fps)连抽。
    普通抽帧每30秒一张看不出嘴型动没动；连续帧才能让视觉模型判断口型开合是否跟随发音。
    返回图片路径列表(已按突发段+序号排序)。ffprobe 拿总时长决定采样点。
    """
    burst_dir = VIDEOS_DIR / f"{room_id}_lipsync"
    burst_dir.mkdir(exist_ok=True)
    existing = sorted(burst_dir.glob("burst_*.jpg"))
    if existing:
        return existing[:max_frames]

    # 取总时长，选前 15%、50%、85% 三个位置各抽 burst_s 秒
    dur = 0.0
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(video_path)],
            capture_output=True, timeout=60, text=True)
        dur = float((p.stdout or "0").strip() or 0)
    except Exception:
        dur = 0.0
    if dur <= 0:
        dur = 300.0  # 兜底：录像常见为5分钟切片

    fracs = [0.15, 0.5, 0.85][:max(1, num_bursts)]
    idx = 1
    for bi, frac in enumerate(fracs):
        start = max(0.0, min(dur - burst_s, dur * frac))
        try:
            subprocess.run(
                ["ffmpeg", "-ss", f"{start:.2f}", "-i", str(video_path),
                 "-t", str(burst_s), "-vf", f"fps={fps},scale=384:-1", "-q:v", "4",
                 str(burst_dir / f"burst_{bi+1}_%03d.jpg"), "-y"],
                capture_output=True, timeout=120)
        except Exception:
            continue
    existing = sorted(burst_dir.glob("burst_*.jpg"))
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


def _merge_av_sync(probe: dict, model_sync) -> dict:
    """融合客观(ffprobe容器偏移)与感知(模型判的数字人口型吻合)两路信号，产出统一音画同步专项。

    - container: 客观测量(offset_ms/level/severity/score)
    - lip_sync : 模型对数字人嘴型-发音吻合度的判断(score 0-100, level, observations, tuning)
    - overall_score / severity / level: 综合分。取两路里“更差”的一路主导（木桶原理）：
      综合分 = min(容器分, 口型分)；severity 取更高者；这样任一路严重都会拉低总分。
    返回结构给页面/编排统一读取。
    """
    ms = model_sync if isinstance(model_sync, dict) else {}

    def _num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    lip_score = _num(ms.get("score"))
    if lip_score is not None and lip_score <= 10:      # 容错：模型可能按 0-10 打
        lip_score *= 10.0

    container = {k: probe.get(k) for k in
                 ("offset_ms", "duration_drift_ms", "level", "severity", "score",
                  "video_start", "audio_start")}
    c_score, c_sev = probe.get("score"), probe.get("severity")

    scores = [s for s in (c_score, lip_score) if s is not None]
    overall_score = round(min(scores)) if scores else None

    # 感知侧 severity：由 lip_score 反推档位（band 边界对齐容器代表分 95/80/55/30/10，两把尺一致）
    def _score_to_sev(s):
        if s is None:
            return None
        if s >= 85:
            return 0
        if s >= 65:
            return 1
        if s >= 45:
            return 2
        if s >= 25:
            return 3
        return 4
    lip_sev = _score_to_sev(lip_score)
    sevs = [s for s in (c_sev, lip_sev) if s is not None]
    overall_sev = max(sevs) if sevs else None
    level_map = {0: "同步", 1: "轻微不同步", 2: "明显不同步", 3: "严重不同步", 4: "极严重不同步"}

    return {
        "overall_score": overall_score,          # 0-100，越高越同步
        "severity": overall_sev,                 # 0(同步)~4(极严重)
        "level": level_map.get(overall_sev, "未知"),
        "container": container,                  # 客观音画布偏移
        "lip_sync": {
            "score": round(lip_score) if lip_score is not None else None,
            "level": ms.get("level"),
            "observations": ms.get("observations", []),
            "tuning": ms.get("tuning", []),
            "comment": ms.get("comment", ""),
        },
        "summary": ms.get("comment") or "",
    }


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

    log("测量音画同步(ffprobe)...")
    probe = probe_av_sync(vp)          # 客观：容器层音画偏移

    log("抽口型连续帧...")
    burst = extract_burst_frames(vp, room_id)   # 感知：数字人口型/发音吻合度

    transcript = ""
    if with_transcript:
        log("音频转写(可能较慢)...")
        transcript = transcribe_audio(vp, room_id)

    # 客观测量结果先给模型当已知事实（避免它凭画面瞎猜偏移方向/毫秒数）
    probe_note = ""
    if probe.get("severity") is not None:
        _dir = "音频滞后于画面" if probe["offset_ms"] > 0 else ("音频超前于画面" if probe["offset_ms"] < 0 else "起始对齐")
        probe_note = (f"\n\n【客观音画同步(ffprobe容器测量,已知事实)】音轨相对视频轨起始偏移 "
                      f"{probe['offset_ms']:+.0f}ms（{_dir}），时长漂移 "
                      f"{probe.get('duration_drift_ms')}ms，判级：{probe['level']}(severity {probe['severity']})。"
                      f"这是音画布(muxing)层的偏移；请你另外判断数字人口型与发音的吻合(lip-sync)，两者不同。")

    # 构造多图 + 文本消息
    content = [{"type": "text", "text":
                f"以下是一段 TikTok 带货直播录像按时间顺序抽取的 {len(frames)} 张关键帧"
                f"（每帧间隔约 {FRAME_INTERVAL_S} 秒）。"
                + (f"\n\n【音频转写】\n{transcript}\n" if transcript else "")
                + probe_note
                + "\n\n" + QUALITY_RUBRIC}]
    for fp in frames:
        b64 = base64.b64encode(fp.read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    # 追加口型连续帧（高帧率突发段），供判断嘴型是否跟随发音自然开合
    if burst:
        content.append({"type": "text", "text":
                        f"\n\n以下另有 {len(burst)} 张【口型连续帧】——从录像前/中/后各截取一小段、"
                        f"按约5帧/秒连续抽取（burst_段号_序号）。请重点看数字人嘴部：口型是否随发音自然开合、"
                        f"有无“嘴动但该停/该动却僵住/循环重复同一口型/闭口出声”等 AI 数字人常见的口型-发音错位，"
                        f"据此给 lip_sync 评分与观察。"})
        for fp in burst:
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
                    result["_burst_frames"] = len(burst)
                    result["_has_transcript"] = bool(transcript)
                    result["av_sync"] = _merge_av_sync(probe, result.get("av_sync"))
                    return result
                last_err = "返回无法解析为JSON"
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:100]}"
                import time
                time.sleep(2)
    return {"error": f"分析失败: {last_err}"}
