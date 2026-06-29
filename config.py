"""配置加载 + 指标定义 + 诊断阈值。

加载优先级：config.json（UI 保存）> .env > 代码默认。复用 darwin 的模式。
"""
from pathlib import Path
import os
import json

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass

BASE_DIR = Path(__file__).parent

# config.json 覆盖 .env（首页保存的配置优先）
_config_json = BASE_DIR / "config.json"
if _config_json.exists():
    try:
        for k, v in json.loads(_config_json.read_text(encoding="utf-8")).items():
            if v and isinstance(v, str):
                os.environ[k] = v
    except Exception:
        pass

# ===== 数据目录 =====
DATA_DIR = BASE_DIR / "data"
ROOMS_DIR = DATA_DIR / "rooms"          # 每主播的场次数据
ANALYSES_DIR = DATA_DIR / "analyses"    # 复盘结果缓存
VIDEOS_DIR = DATA_DIR / "videos"        # 录像/抽帧/转写缓存
for _d in (ROOMS_DIR, ANALYSES_DIR, VIDEOS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ===== 凭证 =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_PROXY_URL = os.getenv("OPENAI_PROXY_URL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_PROXY_URL = os.getenv("ANTHROPIC_PROXY_URL", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_PROXY_KEY = os.getenv("GOOGLE_PROXY_KEY", "")
GOOGLE_PROXY_URL = os.getenv("GOOGLE_PROXY_URL", "")
ZMENG_AUTH_TOKEN = os.getenv("ZMENG_AUTH_TOKEN", "")
ZMENG_COOKIE = os.getenv("ZMENG_COOKIE", "")

# 本地代理（下载录像 / Gemini 官方直连用）
LOCAL_PROXY = os.getenv("LOCAL_PROXY", "http://127.0.0.1:7890")

# ASR 转写模型（faster-whisper）
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
# 录像抽帧间隔（秒）
FRAME_INTERVAL_S = int(os.getenv("FRAME_INTERVAL_S", "30"))

CONFIG_PATH = _config_json
EXAMPLE_CONFIG_PATH = BASE_DIR / "config.example.json"

# ===== 指标全集（众盟原始字段 → 内部 key + 中文名 + 所属维度 + 解析方式） =====
# parse: "num"=数量(支持K/M), "pct"=百分比, "money"=带币种金额, "dur"=时长(1m30s=90s), "raw"=原样
# dim: traffic 流量 / conversion 转化 / order 下单 / meta 元数据
METRIC_DEFS = [
    # 流量获取
    {"key": "impressions", "src": "impressions", "name": "曝光次数", "dim": "traffic", "parse": "num"},
    {"key": "expv", "src": "expv", "name": "曝光观看", "dim": "traffic", "parse": "num"},
    {"key": "views", "src": "views", "name": "场观人次", "dim": "traffic", "parse": "num"},
    {"key": "online", "src": "online", "name": "在线人数", "dim": "traffic", "parse": "num"},
    {"key": "impressions_per_hour", "src": "impressionsPerHour", "name": "每小时曝光", "dim": "traffic", "parse": "num"},
    {"key": "tap_through_rate", "src": "tapThroughRate", "name": "曝光点击进入率", "dim": "traffic", "parse": "pct"},
    {"key": "tap_through_preview", "src": "tapThroughRateViaPreview", "name": "预览点击率", "dim": "traffic", "parse": "pct"},
    {"key": "ads_cost", "src": "adsCost", "name": "投流花费", "dim": "traffic", "parse": "num"},
    {"key": "ads_cost_usd", "src": "adsCostInUSD", "name": "投流花费(USD)", "dim": "traffic", "parse": "money"},
    # 转化效率
    {"key": "ctr", "src": "ctr", "name": "商品点击率", "dim": "conversion", "parse": "pct"},
    {"key": "dwell_time", "src": "avgViewDuration", "name": "平均停留时长", "dim": "conversion", "parse": "dur"},
    {"key": "stay", "src": "stay", "name": "停留时长", "dim": "conversion", "parse": "dur"},
    {"key": "like_rate", "src": "likeRate", "name": "点赞率", "dim": "conversion", "parse": "pct"},
    {"key": "comment_rate", "src": "commentRate", "name": "评论率", "dim": "conversion", "parse": "pct"},
    {"key": "share_rate", "src": "shareRate", "name": "分享率", "dim": "conversion", "parse": "pct"},
    {"key": "follow_rate", "src": "followRate", "name": "转粉率", "dim": "conversion", "parse": "pct"},
    # 下单效率
    {"key": "order_rate", "src": "orderRate", "name": "下单率", "dim": "order", "parse": "pct"},
    {"key": "items_sold", "src": "itemsSold", "name": "成交件数", "dim": "order", "parse": "num"},
    {"key": "gmv", "src": "gmv", "name": "成交额(本币)", "dim": "order", "parse": "money"},
    {"key": "gmv_usd", "src": "gmvInUSD", "name": "成交额(USD)", "dim": "order", "parse": "money"},
    {"key": "gmv_per_hour", "src": "gmvPerHour", "name": "每小时成交", "dim": "order", "parse": "num"},
    {"key": "gmv_per_hour_usd", "src": "gmvPerHourInUSD", "name": "每小时成交(USD)", "dim": "order", "parse": "money"},
    {"key": "gpm", "src": "showGPM", "name": "千次观看成交GPM", "dim": "order", "parse": "num"},
    {"key": "gpm_usd", "src": "showGPMInUSD", "name": "GPM(USD)", "dim": "order", "parse": "money"},
    {"key": "roi", "src": "gmvMaxROI", "name": "投流ROI", "dim": "order", "parse": "num"},
]

# 元数据字段（原样保留，前缀 _ ）
META_FIELDS = {
    "roomId": "_room_id", "hostName": "_host", "openTime": "_open_time",
    "duration": "_duration", "deviceId": "_device_id", "deviceName": "_device",
    "country": "_country", "language": "_language", "roomUrl": "_room_url",
    "geminiTaskId": "_gemini_task_id", "ossUrl": "_oss_url",
    "gmvMaxString": "_gmv_max_on", "liveStatusName": "_live_status",
}

# ===== 诊断阈值（行业经验值，可按类目调；direction: low=低于warn告警, high=高于warn告警） =====
# warn=黄线, bad=红线
DEFAULT_THRESHOLDS = {
    "enter_room_rate": {"name": "进入率(ERR)", "warn": 0.02, "bad": 0.01, "dir": "low", "fmt": "pct"},
    "ctr": {"name": "商品点击率", "warn": 0.03, "bad": 0.015, "dir": "low", "fmt": "pct"},
    "dwell_time": {"name": "平均停留(秒)", "warn": 20, "bad": 10, "dir": "low", "fmt": "sec"},
    "order_rate": {"name": "下单率", "warn": 0.04, "bad": 0.02, "dir": "low", "fmt": "pct"},
    "follow_rate": {"name": "转粉率", "warn": 0.02, "bad": 0.01, "dir": "low", "fmt": "pct"},
    "comment_rate": {"name": "评论率", "warn": 0.02, "bad": 0.01, "dir": "low", "fmt": "pct"},
    "roi": {"name": "投流ROI", "warn": 3.0, "bad": 1.5, "dir": "low", "fmt": "num"},
}

# 直播间质量四维（Gemini 看录像评分）
QUALITY_DIMENSIONS = {
    "visual": "画面",      # 灯光/构图/产品展示/贴片
    "audio": "声音",       # 麦克风/能量/语速/冷场
    "interaction": "互动",  # 迎新/秒回/CTA节奏/福袋时机
    "script": "脚本",      # 循环结构/hook/FABE/逼单
}


def get_default_models() -> dict:
    """返回默认模型 {reasoner: {provider,model}, vision: {provider,model}}。
    reasoner=复盘推理(Opus 4.8)，vision=看录像(Gemini)。"""
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    def _parse(val, fp, fm):
        if val and "/" in val:
            p, m = val.split("/", 1)
            return {"provider": p, "model": m}
        return {"provider": fp, "model": fm}

    return {
        "reasoner": _parse(cfg.get("DEFAULT_REASONER"), "anthropic", "claude-opus-4-8"),
        "vision": _parse(cfg.get("DEFAULT_VISION"), "google（代理）", "gemini-3.1-pro-preview"),
    }


def api_key_for(provider_name: str) -> str:
    if provider_name == "openai":
        return OPENAI_API_KEY
    if provider_name == "anthropic":
        return ANTHROPIC_API_KEY
    if provider_name.startswith("google"):
        return GOOGLE_API_KEY
    return ""


def save_config(updates: dict):
    """更新 config.json（UI 配置面板用）。"""
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg.update(updates)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    for k, v in updates.items():
        if v and isinstance(v, str):
            os.environ[k] = v

