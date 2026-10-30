"""Taste pipeline: audience -> measurable opposite -> bridge.

1. AUDIENCE  : what Qloo says people who love the seed(s) also love, per domain.
2. OPPOSITE  : entities whose tags barely overlap with the audience's tags.
               Distance is computed here from Qloo's own tags, so it stays honest
               even if Qloo ignores an unsupported filter parameter.
3. BRIDGE    : entities Qloo ranks highly for the combined taste of the seed and
               its opposite, scored by how much they share with both sides.

Affinity is taste fit. It is not demand or purchase intent.
"""
from concurrent.futures import ThreadPoolExecutor

import qloo

DOMAINS = [
    ("artist", "urn:entity:artist"),
    ("movie", "urn:entity:movie"),
    ("brand", "urn:entity:brand"),
    ("place", "urn:entity:place"),
]
TOP_TAGS = 8


PROBES = {
    "artist": ["classical", "country", "metal", "jazz"],
    "movie": ["documentary", "western", "horror", "musical"],
    "brand": ["outdoor", "luxury", "budget", "sports"],
    "place": ["museum", "dive bar", "park"],
}


def probe_tag(name, urn, audience_ids):
    """Find a Qloo tag for this entity type that is NOT part of the audience's taste."""
    for word in PROBES.get(name, [])[:3]:
        try:
            data = qloo._get("/v2/tags", {"filter.query": word, "take": 6})
        except qloo.BudgetExceeded:
            raise
        except Exception:  # noqa: BLE001
            continue
        res = data.get("results", data) if isinstance(data, dict) else data
        tags = (res.get("tags") if isinstance(res, dict) else res) or []
        for t in tags:
            if not isinstance(t, dict) or not t.get("id") or t["id"] in audience_ids:
                continue
            if any(isinstance(x, dict) and x.get("type") == urn for x in t.get("parents") or []):
                return t["id"]
    return None


class PipelineError(RuntimeError):
    pass


def tag_weights(ents):
    w = {}
    for i, e in enumerate(ents):
        aff = e.get("affinity")
        base = aff if isinstance(aff, (int, float)) and aff > 0 else 1.0 / (1 + i)
        for t in e["tags"]:
            w[t["id"]] = w.get(t["id"], 0.0) + base
    total = sum(w.values())
    return {k: v / total for k, v in w.items()} if total else {}


def cap_of(weights, n=TOP_TAGS):
    return sum(sorted(weights.values(), reverse=True)[:n])


def overlap(e, weights, cap):
    if not weights or not cap:
        return 0.0
    return min(1.0, sum(weights.get(t["id"], 0.0) for t in e["tags"]) / cap)


def top_ids(weights, n=TOP_TAGS):
    return [k for k, _ in sorted(weights.items(), key=lambda kv: -kv[1])[:n]]


def slim(e, **extra):
    d = {
        "id": e["id"],
        "name": e["name"],
        "tags": [t["name"] for t in e["tags"][:4]],
        "address": e.get("address") or "",
        "description": (e.get("description") or "")[:160],
        "popularity": e.get("popularity"),
    }
    d.update(extra)
    return d


def run(seed_names, city=""):
    names = [n.strip() for n in seed_names if n and n.strip()][:3]
    if not names:
        raise PipelineError("Add at least one brand, artist or show.")
    warnings = []

    with ThreadPoolExecutor(max_workers=3) as pool:
        found = list(pool.map(qloo.search, names))
    seeds = [s for s in found if s]
    unresolved = [n for n, s in zip(names, found) if not s]
    if not seeds:
        raise PipelineError("Qloo didn't recognise those names. Try a well-known brand, artist or show.")
    seed_ids = [s["id"] for s in seeds]
    domains = [d for d in DOMAINS if d[0] != "place" or city]

    def safe_ins(domain, extra):
        name, urn = domain
        p = {"filter.type": urn, "take": 20}
        p.update(extra)
        if name == "place":
            p["filter.location.query"] = city
        try:
            return qloo.entities(qloo.insights(p))
        except qloo.BudgetExceeded:
            raise
        except Exception as ex:  # noqa: BLE001 - one weak domain must not kill the run
            warnings.append(f"{name}: {ex}")
            return []

    # 1. audience
    with ThreadPoolExecutor(max_workers=4) as pool:
        aud_lists = list(pool.map(lambda d: safe_ins(d, {"signal.interests.entities": ",".join(seed_ids)}), domains))
    seed_lc0 = {s["name"].lower() for s in seeds}
    audience = {d[0]: [e for e in lst if e["id"] not in seed_ids and e["name"].lower() not in seed_lc0] for d, lst in zip(domains, aud_lists)}
    all_aud = [e for lst in audience.values() for e in lst]
    if not all_aud:
        raise PipelineError("Qloo returned no audience data for those names.")
    a_w = tag_weights(all_aud)
    a_cap = cap_of(a_w)
    a_ids = top_ids(a_w)

    # 2. opposite
    # Verified against the live API: Qloo needs a real signal next to filter.exclude.tags
    # (exclude alone returns 400). Two sources per domain, both scored locally afterwards:
    #   a) seed signal + exclude the audience's own top tags  (related but off-profile)
    #   b) a contrast tag as signal (found via /v2/tags) + the same exclusion (genuinely far)
    def exclude_try(domain):
        name, urn = domain
        own = tag_weights(audience.get(name, []))
        ids = top_ids(own, 3) or a_ids[:3]
        loc = {"filter.location.query": city} if name == "place" else {}
        out, last = [], None
        for k in (len(ids), 1):
            if k < 1:
                break
            try:
                out = qloo.entities(qloo.insights({"filter.type": urn, "take": 20, "signal.interests.entities": ",".join(seed_ids),
                                                   "filter.exclude.tags": ",".join(ids[:k]), **loc}))
                last = None
                break
            except qloo.BudgetExceeded:
                raise
            except Exception as ex:  # noqa: BLE001
                last = ex
        if last is not None:
            warnings.append(f"{name}: exclude filter not accepted by Qloo ({str(last)[:60]})")
        pt = probe_tag(name, urn, set(a_w))
        if pt:
            try:
                more = qloo.entities(qloo.insights({"filter.type": urn, "take": 20, "signal.interests.tags": pt,
                                                    "filter.exclude.tags": ",".join(ids[:3]), **loc}))
                have = {e["id"] for e in out}
                out = out + [e for e in more if e["id"] not in have]
            except qloo.BudgetExceeded:
                raise
            except Exception:  # noqa: BLE001 - the probe is a bonus source
                pass
        return out

    with ThreadPoolExecutor(max_workers=4) as pool:
        opp_lists = list(pool.map(exclude_try, domains))
    seen = set(seed_ids) | {e["id"] for e in all_aud}
    seed_lc = {s["name"].lower() for s in seeds}
    opp_raw = {}
    naive_d, chosen_d = [], []
    for (name, _), lst in zip(domains, opp_lists):
        cands = []
        for e in lst:
            if e["id"] in seen or e["name"].lower() in seed_lc or len(e["tags"]) < 2:
                continue
            # obscure items look "far" only because Qloo has few tags for them: require known entities
            if isinstance(e.get("popularity"), (int, float)) and e["popularity"] < 0.45:
                continue
            dist = 1.0 - overlap(e, a_w, a_cap)
            pop = e["popularity"] if isinstance(e.get("popularity"), (int, float)) else 0.0
            cands.append((0.6 * dist + 0.4 * pop, dist, e))
        naive = sorted(cands, key=lambda x: -(x[2].get("popularity") or 0.0))[:5]
        naive_d.extend(d for _, d, _ in naive)
        cands.sort(key=lambda x: -x[0])
        chosen_d.extend(d for _, d, _ in cands[:5])
        opp_raw[name] = [(e, dist) for _, dist, e in cands[:5]]
    baseline = {
        "naive": round(100 * sum(naive_d) / len(naive_d)) if naive_d else None,
        "measured": round(100 * sum(chosen_d) / len(chosen_d)) if chosen_d else None,
    }
    opp_flat = sorted([(dist, e) for v in opp_raw.values() for e, dist in v], key=lambda x: -x[0])
    if not opp_flat:
        # Fallback: nothing came back outside the audience's tags, so use the farthest related items.
        for (name, _), lst in zip(domains, aud_lists):
            far = [(1.0 - overlap(e, a_w, a_cap), e) for e in lst if e["id"] not in seed_ids and e["tags"]]
            far.sort(key=lambda x: -x[0])
            opp_raw[name] = [(e, d) for d, e in far[:5] if d > 0.3]
        opp_flat = sorted([(dist, e) for v in opp_raw.values() for e, dist in v], key=lambda x: -x[0])
        if opp_flat:
            warnings.append("Qloo returned nothing outside the audience's tags, so these are the farthest related items instead.")
    if not opp_flat:
        raise PipelineError("Couldn't find entities with a clearly different taste. Try another seed.")
    o_w = tag_weights([e for _, e in opp_flat[:10]])
    o_cap = cap_of(o_w)

    # 3. bridge
    anchors = [e["id"] for _, e in opp_flat[:2]]
    sig = ",".join(seed_ids + anchors)
    with ThreadPoolExecutor(max_workers=4) as pool:
        br_lists = list(pool.map(lambda d: safe_ins(d, {"signal.interests.entities": sig}), domains))
    seen |= {e["id"] for _, e in opp_flat}
    bridges = {}
    for (name, _), lst in zip(domains, br_lists):
        scored = []
        for e in lst:
            if e["id"] in seen or not e["tags"]:
                continue
            a, o = overlap(e, a_w, a_cap), overlap(e, o_w, o_cap)
            strength = 2 * a * o / (a + o) if (a + o) else 0.0
            a_side = [t["name"] for t in e["tags"] if t["id"] in a_w][:2]
            o_side = [t["name"] for t in e["tags"] if t["id"] in o_w][:2]
            scored.append((strength, e, a_side, o_side))
        scored.sort(key=lambda x: -x[0])
        bridges[name] = [
            slim(e, strength=round(s, 3), audience_side=a_s, opposite_side=o_s)
            for s, e, a_s, o_s in scored[:3]
        ]

    # scores + display data
    tag_names = {}
    for e in all_aud + [e for _, e in opp_flat]:
        for t in e["tags"]:
            tag_names[t["id"]] = t["name"]
    top_opp = [d for d, _ in opp_flat[:3]]
    flat_br = sorted([b["strength"] for v in bridges.values() for b in v], reverse=True)[:3]
    scores = {
        "opposite_distance": round(100 * sum(top_opp) / len(top_opp)),
        "bridge_strength": round(100 * sum(flat_br) / len(flat_br)) if flat_br else 0,
    }
    result = {
        "seeds": [{"name": s["name"], "id": s["id"]} for s in seeds],
        "unresolved": unresolved,
        "city": city,
        "audience": {k: [slim(e) for e in v[:5]] for k, v in audience.items() if v},
        "audience_tags": [{"name": tag_names.get(i, i), "weight": round(a_w[i], 3)} for i in a_ids],
        "opposites": {k: [slim(e, distance=round(d, 3)) for e, d in v] for k, v in opp_raw.items() if v},
        "opposite_tags": [{"name": tag_names.get(i, i), "weight": round(o_w[i], 3)} for i in [i for i in top_ids(o_w, 14) if i not in a_ids][:TOP_TAGS]],
        "bridges": {k: v for k, v in bridges.items() if v},
        "scores": scores,
        "warnings": warnings,
        "baseline": baseline,
    }
    names_allowed = {s["name"] for s in seeds}
    for section in ("audience", "opposites", "bridges"):
        for lst in result[section].values():
            names_allowed |= {x["name"] for x in lst}
    result["allowed_names"] = sorted(names_allowed)
    result["ledger"] = ledger(result)
    return result


def ledger(r):
    """Plain-text evidence lines every claim in the brief can be traced to."""
    lines = []
    for k, v in r["opposites"].items():
        for x in v:
            lines.append(f"OPPOSITE [{k}] {x['name']} - taste distance {round(x['distance'] * 100)}% - tags: {', '.join(x['tags'])}")
    for k, v in r["bridges"].items():
        for x in v:
            lines.append(
                f"BRIDGE [{k}] {x['name']} - strength {round(x['strength'] * 100)}% - links "
                f"{', '.join(x['audience_side']) or 'n/a'} (audience side) with {', '.join(x['opposite_side']) or 'n/a'} (opposite side)"
            )
    for k, v in r["audience"].items():
        for x in v:
            lines.append(f"AUDIENCE [{k}] {x['name']} - tags: {', '.join(x['tags'])}")
    return lines
