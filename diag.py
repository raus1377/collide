"""Prints what Qloo actually says for each way of asking for an 'opposite'. Run: python diag.py"""
import os, sys, requests
sys.path.insert(0, os.getcwd())
try:
    import qloo
    KEY = qloo.KEY
except Exception:
    KEY = os.environ.get("QLOO_API_KEY", "")
BASE = "https://hackathon.api.qloo.com"
H = {"X-Api-Key": KEY}

def call(label, path, params):
    r = requests.get(BASE + path, headers=H, params=params, timeout=30)
    body = r.text.replace("\n", " ")
    n = ""
    try:
        j = r.json()
        res = (j.get("results") or {}).get("entities") if isinstance(j.get("results"), dict) else j.get("results")
        n = f" entities={len(res) if isinstance(res, list) else '?'}"
    except Exception:
        pass
    print(f"\n[{label}] HTTP {r.status_code}{n}\n  {body[:350]}")
    return r

s = requests.get(BASE + "/search", headers=H, params={"query": "Billie Eilish", "take": 3}, timeout=30).json()
seed = (s.get("results") or [{}])[0].get("entity_id")
print("seed:", seed)
base = {"filter.type": "urn:entity:artist", "take": 5}
r = requests.get(BASE + "/v2/insights", headers=H, params={**base, "signal.interests.entities": seed}, timeout=30).json()
ents = (r.get("results") or {}).get("entities") or []
tags = [t.get("id") or t.get("tag_id") for t in (ents[0].get("tags") or [])] if ents else []
print("sample tags:", tags[:4])
t1 = tags[0] if tags else "urn:tag:genre:qloo:indie_pop"

call("A exclude.tags alone", "/v2/insights", {**base, "filter.exclude.tags": t1})
call("B exclude.tags + seed signal", "/v2/insights", {**base, "filter.exclude.tags": t1, "signal.interests.entities": seed})
call("C filter.tags (include) alone", "/v2/insights", {**base, "filter.tags": t1})
call("D signal.interests.tags alone", "/v2/insights", {**base, "signal.interests.tags": t1})
call("E exclude.tags + signal tags", "/v2/insights", {**base, "filter.exclude.tags": t1, "signal.interests.tags": "urn:tag:genre:qloo:rock"})
call("F tags search 'country'", "/v2/tags", {"filter.query": "country", "take": 5})
call("G tags search 'classical'", "/v2/tags", {"filter.query": "classical", "take": 5})
