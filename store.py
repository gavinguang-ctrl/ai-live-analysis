"""数据存储 — 按主播(hostName)组织场次数据 + 分析结果缓存，纯 JSON 文件。"""
import json
import re
from pathlib import Path
from datetime import datetime

from config import ROOMS_DIR, ANALYSES_DIR


def _safe(name: str) -> str:
    """主播名 → 安全文件名。"""
    s = re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip())
    return s[:80] or "unknown"


def save_host_rooms(host_name: str, rooms: list[dict]) -> Path:
    """保存某主播的所有场次（覆盖式，按 roomId 去重合并已有）。"""
    path = ROOMS_DIR / f"{_safe(host_name)}.json"
    existing = {}
    if path.exists():
        try:
            for r in json.loads(path.read_text(encoding="utf-8")).get("rooms", []):
                existing[r.get("_room_id")] = r
        except Exception:
            pass
    for r in rooms:
        existing[r.get("_room_id")] = r
    merged = sorted(existing.values(), key=lambda r: r.get("_open_time", ""), reverse=True)
    payload = {"host": host_name, "updated_at": datetime.now().isoformat(timespec="seconds"),
               "count": len(merged), "rooms": merged}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_host_rooms(host_name: str) -> list[dict]:
    path = ROOMS_DIR / f"{_safe(host_name)}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("rooms", [])
    except Exception:
        return []


def load_hosts_rooms(host_names: list[str]) -> list[dict]:
    """合并加载多个主播的全部场次（用于多主播合并分析，如同一产品多主播）。
    每条场次补上 _host 字段（若缺），便于后续按主播拆分对比。
    """
    merged = []
    for h in host_names:
        for r in load_host_rooms(h):
            if not r.get("_host"):
                r = {**r, "_host": h}
            merged.append(r)
    return sorted(merged, key=lambda r: r.get("_open_time", ""), reverse=True)


def group_label(host_names: list[str]) -> str:
    """多主播组的展示名：单个直接用主播名，多个用 ' + ' 连接。"""
    names = [h for h in host_names if h]
    return names[0] if len(names) == 1 else " + ".join(names)


def analysis_key(host_names: list[str]) -> str:
    """多主播组的缓存 key（顺序无关，去重排序后拼接），如 a__b_auto。"""
    uniq = sorted(set(h for h in host_names if h))
    return "__".join(uniq) if uniq else "unknown"


def list_hosts() -> list[dict]:
    """列出所有已抓取的主播 [{host, count, updated_at}]。"""
    out = []
    for p in ROOMS_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"host": d.get("host", p.stem), "count": d.get("count", 0),
                        "updated_at": d.get("updated_at", "")})
        except Exception:
            continue
    return sorted(out, key=lambda x: x.get("updated_at", ""), reverse=True)


def save_analysis(key: str, data: dict) -> Path:
    """缓存一份分析结果（key 自定义，如 host_week_2026-W24 或 roomId_video）。"""
    path = ANALYSES_DIR / f"{_safe(key)}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_analysis(key: str) -> dict | None:
    path = ANALYSES_DIR / f"{_safe(key)}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
