"""数据存储 — 按主播(hostName)组织场次数据 + 分析结果缓存，纯 JSON 文件。"""
import json
import re
from pathlib import Path
from datetime import datetime

from config import ROOMS_DIR, ANALYSES_DIR, DATA_DIR


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


# ===== 主播组合（同一产品的多主播分组，可命名/保存/复用/增删改）=====
GROUPS_PATH = DATA_DIR / "groups.json"


def load_groups() -> dict[str, list[str]]:
    """读取所有组合 {组合名: [主播id, ...]}。"""
    if not GROUPS_PATH.exists():
        return {}
    try:
        data = json.loads(GROUPS_PATH.read_text(encoding="utf-8"))
        # 兼容：值必须是 list
        return {k: list(v) for k, v in data.items() if isinstance(v, list)}
    except Exception:
        return {}


def _write_groups(groups: dict[str, list[str]]) -> None:
    GROUPS_PATH.write_text(json.dumps(groups, ensure_ascii=False, indent=2), encoding="utf-8")


def save_group(name: str, host_names: list[str]) -> bool:
    """新建或更新一个组合（同名覆盖）。去重保序。name 为空或无成员则不保存。"""
    name = (name or "").strip()
    members = []
    for h in host_names:
        h = (h or "").strip()
        if h and h not in members:
            members.append(h)
    if not name or not members:
        return False
    groups = load_groups()
    groups[name] = members
    _write_groups(groups)
    return True
# APPEND_GROUPS_MARKER


def rename_group(old_name: str, new_name: str) -> bool:
    """重命名组合。新名为空或与他人重名(非自身)则失败。"""
    old_name, new_name = (old_name or "").strip(), (new_name or "").strip()
    groups = load_groups()
    if old_name not in groups or not new_name:
        return False
    if new_name != old_name and new_name in groups:
        return False  # 不覆盖已存在的其他组合
    members = groups.pop(old_name)
    groups[new_name] = members
    _write_groups(groups)
    return True


def delete_group(name: str) -> bool:
    groups = load_groups()
    if name in groups:
        groups.pop(name)
        _write_groups(groups)
        return True
    return False


def get_group(name: str) -> list[str]:
    """取某组合的主播列表（不存在返回空）。"""
    return load_groups().get(name, [])
