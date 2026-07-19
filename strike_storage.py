import json
import os
from datetime import datetime, timezone

FILE = os.path.join(os.path.dirname(__file__), "data", "strikes.json")


def _ensure_file():
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    if not os.path.exists(FILE):
        with open(FILE, "w") as f:
            json.dump({}, f, indent=4)


_ensure_file()


def _load() -> dict:
    with open(FILE, "r") as f:
        return json.load(f)


def _save(data: dict):
    with open(FILE, "w") as f:
        json.dump(data, f, indent=4)


def get_strikes(user_id: int) -> int:
    return _load().get(str(user_id), {}).get("total", 0)


def get_record(user_id: int) -> dict:
    return _load().get(str(user_id), {"total": 0, "history": []})


def add_strikes(user_id: int, count: int, strike_type: str, reason: str, added_by: str) -> int:
    data = _load()
    key = str(user_id)
    if key not in data:
        data[key] = {"total": 0, "history": []}
    data[key]["total"] = max(0, data[key]["total"] + count)
    data[key]["history"].append({
        "action": "add", "type": strike_type, "count": count,
        "reason": reason, "added_by": added_by,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save(data)
    return data[key]["total"]


def remove_strikes(user_id: int, count: int, reason: str, removed_by: str) -> int:
    data = _load()
    key = str(user_id)
    if key not in data:
        data[key] = {"total": 0, "history": []}
    data[key]["total"] = max(0, data[key]["total"] - count)
    data[key]["history"].append({
        "action": "remove", "count": count, "reason": reason,
        "removed_by": removed_by,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save(data)
    return data[key]["total"]


def clear_strikes(user_id: int, cleared_by: str):
    data = _load()
    key = str(user_id)
    if key in data:
        data[key]["total"] = 0
        data[key]["history"].append({
            "action": "clear", "cleared_by": cleared_by,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    _save(data)
