"""Qloo client: server-side key, disk cache, hard call budget, optional mock mode.

The API key never leaves the server. Every cache miss is a real (credit-costing)
call, so identical requests are served from a local cache and a budget stops
the app before credits run out. The cache file is private (gitignored): real
Qloo responses must not be committed to a public repo.
"""
import json
import os
import threading
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_env(path=os.path.join(BASE_DIR, ".env")):
    """Tiny .env loader so no extra dependency is needed."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

KEY = os.environ.get("QLOO_API_KEY", "")
BASE = os.environ.get("QLOO_API_URL", "https://hackathon.api.qloo.com").rstrip("/")
MAX_CALLS = int(os.environ.get("QLOO_MAX_CALLS", "120"))
CACHE_PATH = os.environ.get("FOIL_CACHE", os.path.join(BASE_DIR, ".qloo_cache.json"))
TIMEOUT = 25

_lock = threading.Lock()
_cache = {}
_calls = 0


class QlooError(RuntimeError):
    pass


class BudgetExceeded(QlooError):
    pass


def is_mock():
    return os.environ.get("FOIL_MOCK") == "1"


if not is_mock() and os.path.exists(CACHE_PATH):
    try:
        with open(CACHE_PATH, encoding="utf-8") as _f:
            _cache = json.load(_f)
    except (OSError, ValueError):
        _cache = {}


def stats():
    return {"live_calls": _calls, "budget": MAX_CALLS, "cached": len(_cache), "mock": is_mock()}


def _save():
    try:
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_cache, f)
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass


def _get(path, params):
    global _calls
    clean = {k: v for k, v in params.items() if v not in (None, "")}
    if is_mock():
        import mock_data
        return mock_data.route(path, clean)
    key = path + "?" + json.dumps(clean, sort_keys=True)
    with _lock:
        if key in _cache:
            return _cache[key]
    if not KEY:
        raise QlooError("QLOO_API_KEY is not set on the server.")
    with _lock:
        if _calls >= MAX_CALLS:
            raise BudgetExceeded(f"Call budget of {MAX_CALLS} reached. Raise QLOO_MAX_CALLS to continue.")
        _calls += 1
    for attempt in range(3):
        r = requests.get(
            f"{BASE}{path}",
            params=clean,
            headers={"X-Api-Key": KEY, "Accept": "application/json"},
            timeout=TIMEOUT,
        )
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(0.8 * (attempt + 1))  # brief backoff, then retry once or twice
            continue
        break
    if r.status_code in (401, 403):
        raise QlooError("Qloo rejected the API key (hackathon keys also expire after the event).")
    r.raise_for_status()
    data = r.json()
    with _lock:
        _cache[key] = data
        _save()
    return data


def entities(data):
    """Normalise a Qloo response into a flat list of entity dicts."""
    res = data.get("results", data) if isinstance(data, dict) else data
    if isinstance(res, dict):
        res = res.get("entities") or res.get("results") or []
    out = []
    for e in res or []:
        if not isinstance(e, dict):
            continue
        props = e.get("properties") or {}
        tags = []
        for t in e.get("tags") or []:
            if isinstance(t, dict):
                tid = t.get("id") or t.get("tag_id") or t.get("name")
                name = t.get("name") or tid
                if tid and name:
                    tags.append({"id": tid, "name": name})
        q = e.get("query")
        loc = e.get("location") if isinstance(e.get("location"), dict) else {}
        out.append({
            "id": e.get("entity_id") or e.get("id"),
            "name": e.get("name"),
            "types": e.get("types") or [],
            "tags": tags,
            "popularity": e.get("popularity"),
            "affinity": q.get("affinity") if isinstance(q, dict) else None,
            "address": props.get("address") or loc.get("address") or "",
            "description": props.get("short_description") or props.get("description") or "",
        })
    return [e for e in out if e["id"] and e["name"]]


def search(name):
    """Resolve free text to the best Qloo entity (or None)."""
    found = entities(_get("/search", {"query": name, "take": 3, "limit": 3}))
    return found[0] if found else None


def insights(params):
    return _get("/v2/insights", params)
