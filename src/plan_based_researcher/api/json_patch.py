"""RFC 6902 JSON Patch for AG-UI ACTIVITY_DELTA."""

from __future__ import annotations

__all__ = ["json_patch"]


def json_patch(old: object, new: object) -> list[dict]:
    ops: list[dict] = []
    _diff(old, new, "", ops)
    return ops


def _diff(old: object, new: object, path: str, ops: list[dict]) -> None:
    if old == new:
        return
    if not isinstance(old, type(new)) or not isinstance(new, (dict, list)):
        ops.append({"op": "replace", "path": path or "/", "value": new})
        return
    if isinstance(new, dict):
        old_d = old if isinstance(old, dict) else {}
        for key, value in new.items():
            child = f"{path}/{key}"
            if key not in old_d:
                ops.append({"op": "add", "path": child, "value": value})
            else:
                _diff(old_d[key], value, child, ops)
        for key in old_d:
            if key not in new:
                ops.append({"op": "remove", "path": f"{path}/{key}"})
        return
    old_l = old if isinstance(old, list) else []
    if len(old_l) != len(new):
        ops.append({"op": "replace", "path": path or "/", "value": new})
        return
    for index, (left, right) in enumerate(zip(old_l, new, strict=True)):
        _diff(left, right, f"{path}/{index}", ops)
