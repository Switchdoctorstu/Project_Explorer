from __future__ import annotations


def safe_call(obj, method_name, default=""):
    if obj is None:
        return default
    try:
        value = getattr(obj, method_name)()
        return default if value is None else value
    except Exception:
        return default


def as_text(value) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def as_bool_text(value) -> str:
    if value is None or value == "":
        return ""
    text = str(value).strip().lower()
    if text == "true":
        return "Yes"
    if text == "false":
        return "No"
    return str(value)


def collection_items(collection) -> list:
    if collection is None:
        return []
    try:
        return list(collection)
    except Exception:
        return []
