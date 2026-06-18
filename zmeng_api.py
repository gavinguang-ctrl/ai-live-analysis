"""众盟 API 客户端 — 全量字段提取（含录像 ossUrl）+ 货币/时长解析。

复用 darwin 的认证方式：Authorization: ZMENG_AUTH_TOKEN(JWT) + 可选 Cookie。
与 darwin 不同：本项目提取 API 返回的**全部**性能字段（流量/转化/下单）+ 录像 URL。
"""
import re
import os
import requests

from config import METRIC_DEFS, META_FIELDS

API_URL = "https://tt.zmeng123.com/alived/live/list"
TASK_CONTENT_URL = "https://tt.zmeng123.com/alived/live/gemini/task/content"
SHOTSNAP_URL = "https://tt.zmeng123.com/alived/rci/tool/live_shotsnap"


def _get_token() -> str:
    return os.environ.get("ZMENG_AUTH_TOKEN", "")


def _get_cookie() -> str:
    return os.environ.get("ZMENG_COOKIE", "")


def _headers_cookies() -> tuple[dict, dict]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Authorization": _get_token(),
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://tt.zmeng123.com",
        "Referer": "https://tt.zmeng123.com/",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X)",
    }
    cookies = {}
    if _get_cookie():
        for pair in _get_cookie().split("; "):
            if "=" in pair:
                k, v = pair.split("=", 1)
                cookies[k.strip()] = v.strip()
    return headers, cookies


def parse_duration(val) -> float:
    """时长 → 秒。支持 '1h2m30s' / '1m30s' / '45s' / '00:27:29' / 纯数字。"""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s == "-":
        return 0.0
    # HH:MM:SS 或 MM:SS
    if ":" in s:
        parts = s.split(":")
        try:
            parts = [int(p) for p in parts]
        except ValueError:
            return 0.0
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return float(parts[0])
    # 1h2m30s
    total = 0.0
    h = re.search(r"(\d+)\s*h", s, re.I)
    m = re.search(r"(\d+)\s*m", s, re.I)
    sec = re.search(r"(\d+)\s*s", s, re.I)
    if h or m or sec:
        if h:
            total += int(h.group(1)) * 3600
        if m:
            total += int(m.group(1)) * 60
        if sec:
            total += int(sec.group(1))
        return total
    s2 = re.sub(r"[^\d.]", "", s)
    return float(s2) if s2 else 0.0


def parse_pct(val) -> float:
    """百分比 → 小数。'4.06%' → 0.0406；'0%' → 0。"""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "")
    if not s or s == "-":
        return 0.0
    has_pct = s.endswith("%")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s:
        return 0.0
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return v / 100.0 if has_pct else v


def parse_num(val) -> float:
    """数量 → float。支持 K/M 后缀、千分位逗号。'2.45K' → 2450, '17.36K' → 17360。"""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "")
    if not s or s == "-":
        return 0.0
    mult = 1.0
    if s and s[-1] in "KkMmBb":
        suffix = s[-1].upper()
        mult = {"K": 1e3, "M": 1e6, "B": 1e9}[suffix]
        s = s[:-1]
    s = re.sub(r"[^\d.\-]", "", s)
    if not s:
        return 0.0
    try:
        return float(s) * mult
    except ValueError:
        return 0.0


# 已知货币符号 → 代码（仅用于展示；金额数值统一用 parse_num 提取）
_CURRENCY_SYMBOLS = {
    "₫": "VND", "RM": "MYR", "$": "USD", "Rp": "IDR", "฿": "THB",
    "₱": "PHP", "£": "GBP", "¥": "CNY", "€": "EUR",
}


def parse_money(val) -> float:
    """金额 → 数值（剥离币种符号 + K/M）。'15.2K₫' → 15200, 'RM0' → 0, '$0.66' → 0.66。"""
    return parse_num(val)


def detect_currency(val) -> str:
    """从金额字符串识别币种符号，返回币种代码（默认空）。"""
    if val is None:
        return ""
    s = str(val)
    for sym, code in _CURRENCY_SYMBOLS.items():
        if sym in s:
            return code
    return ""


_PARSERS = {"num": parse_num, "pct": parse_pct, "dur": parse_duration, "money": parse_money}


def normalize_item(item: dict) -> dict:
    """把一条原始 API 记录转成内部全量字段 dict。"""
    out = {}
    for d in METRIC_DEFS:
        raw = item.get(d["src"])
        parser = _PARSERS.get(d["parse"])
        out[d["key"]] = parser(raw) if parser else raw
    # 元数据原样
    for src, dst in META_FIELDS.items():
        out[dst] = item.get(src, "")
    # 币种（从本币 gmv 推断）
    out["_currency"] = detect_currency(item.get("gmv"))
    # 保留原始未解析的几个常用展示串
    out["_gmv_raw"] = item.get("gmv", "")
    out["_ads_cost_raw"] = item.get("adsCost", "")
    return out


def fetch_host_rooms(host_name: str, start_date: str = "", end_date: str = "",
                     page_size: int = 50, proxies: dict | None = None,
                     on_progress=None) -> list[dict]:
    """抓取指定主播在日期范围内的所有直播间（全量字段，含录像 ossUrl）。

    on_progress(msg) 可选回调，用于 UI 进度。
    """
    headers, cookies = _headers_cookies()
    if not end_date:
        from datetime import datetime as _dt
        end_date = _dt.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = "2025-01-01"

    all_rooms: list[dict] = []
    page = 1
    while True:
        payload = {
            "pageNum": page, "pageSize": page_size, "liveStatus": 0,
            "hostName": host_name, "startDate": start_date, "endDate": end_date,
        }
        try:
            resp = requests.post(API_URL, json=payload, headers=headers, cookies=cookies,
                                 timeout=20, proxies=proxies)
            data = resp.json()
        except Exception as e:
            if on_progress:
                on_progress(f"第{page}页请求失败: {e}")
            break
        if data.get("errorCode") != 0:
            if on_progress:
                on_progress(f"API 返回错误: {data.get('errorMsg') or data.get('msg')}")
            break
        items = data.get("data", {}).get("list", [])
        if not items:
            break
        for it in items:
            all_rooms.append(normalize_item(it))
        total = data.get("data", {}).get("total", 0)
        if on_progress:
            on_progress(f"已抓取 {len(all_rooms)}/{total} 场")
        if page * page_size >= total:
            break
        page += 1
    return all_rooms


def fetch_rooms_by_ids(room_ids: list[str], proxies: dict | None = None) -> list[dict]:
    """通过直播间 ID 列表抓取（全量字段）。"""
    headers, cookies = _headers_cookies()
    out: list[dict] = []
    for rid in room_ids:
        rid = (rid or "").strip()
        if not rid:
            continue
        payload = {"pageNum": 1, "pageSize": 1, "roomId": rid}
        try:
            resp = requests.post(API_URL, json=payload, headers=headers, cookies=cookies,
                                 timeout=20, proxies=proxies)
            data = resp.json()
        except Exception:
            continue
        items = data.get("data", {}).get("list", [])
        if data.get("errorCode") == 0 and items:
            out.append(normalize_item(items[0]))
    return out


def fetch_task_content(gemini_task_id: str, proxies: dict | None = None) -> dict | None:
    """抓取一个 geminiTask 的脚本(口播稿) + 提示词。"""
    if not gemini_task_id:
        return None
    headers, cookies = _headers_cookies()
    try:
        resp = requests.post(TASK_CONTENT_URL, json={"geminiTaskId": gemini_task_id},
                             headers=headers, cookies=cookies, timeout=30, proxies=proxies)
        data = resp.json()
    except Exception:
        return None
    if data.get("errorCode") != 0 or not data.get("data"):
        return None
    d = data["data"]
    scripts = sorted(d.get("scripts", []), key=lambda s: s.get("sequenceNo", 0))
    return {
        "id": d.get("id"),
        "task_name": d.get("taskName", ""),
        "prompt": d.get("prompt", ""),
        "scripts": [{"seq": s.get("sequenceNo", 0), "content": s.get("content", "")}
                    for s in scripts if s.get("content")],
        "script_count": len(scripts),
    }


def fetch_live_screenshots(room_id: str, device_id: str, proxies: dict | None = None) -> list[dict]:
    """抓取一场直播的「数据洞察」截屏列表（每约15分钟的大屏 + 流量来源）。

    端点：POST /alived/rci/tool/live_shotsnap  {deviceId, roomId}
    返回按时间排序的 [{type, snapshot_url, create_time}]，
    type: overview=直播大屏 / traffic-source=流量来源。
    """
    if not room_id or not device_id:
        return []
    headers, cookies = _headers_cookies()
    try:
        resp = requests.post(SHOTSNAP_URL, json={"deviceId": device_id, "roomId": room_id},
                             headers=headers, cookies=cookies, timeout=20, proxies=proxies)
        data = resp.json()
    except Exception:
        return []
    if data.get("errorCode") != 0 or not data.get("data"):
        return []
    out = []
    for x in data["data"]:
        cb = x.get("callbackData") or {}
        url = cb.get("snapshot", "") if isinstance(cb, dict) else ""
        if not url:
            continue
        out.append({
            "type": x.get("type", ""),          # overview / traffic-source
            "snapshot_url": url,
            "create_time": x.get("createTime", ""),
            "id": x.get("id"),
        })
    out.sort(key=lambda s: s.get("create_time", ""))
    return out


def check_token() -> tuple[bool, str]:
    """快速校验 token 是否有效（抓1条）。返回 (ok, message)。"""
    headers, cookies = _headers_cookies()
    if not _get_token():
        return False, "未配置 ZMENG_AUTH_TOKEN"
    try:
        resp = requests.post(API_URL, json={"pageNum": 1, "pageSize": 1, "liveStatus": 0,
                                            "startDate": "2025-01-01", "endDate": "2030-12-31"},
                             headers=headers, cookies=cookies, timeout=15)
        data = resp.json()
    except Exception as e:
        return False, f"请求失败: {e}"
    if data.get("errorCode") == 0:
        return True, "Token 有效"
    return False, f"Token 无效: {data.get('errorMsg') or data.get('msg') or data}"

