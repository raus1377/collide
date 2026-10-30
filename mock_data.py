"""SAMPLE DATA ONLY. Synthetic, fictional entities used to test the pipeline and
build the UI without spending Qloo credits. This is NOT Qloo output."""
import hashlib

CLUSTERS = {
    "urban": ["Streetwear", "Hip-hop", "Sneakers", "Nightlife", "Pop"],
    "quiet": ["Folk", "Indie", "Bookish", "Tea rooms", "Cottagecore"],
    "classic": ["Opera", "Tailoring", "Fine dining", "Luxury", "Classical"],
    "outdoor": ["Hiking", "Camping", "Trail", "Country", "Adventure"],
}


def _tag(name):
    return {"id": "urn:tag:sample:" + name.lower().replace(" ", "-"), "name": name}


def _ent(eid, name, etype, tag_names, pop):
    return {
        "entity_id": eid,
        "name": name,
        "types": [etype],
        "popularity": pop,
        "tags": [_tag(t) for t in tag_names],
        "properties": {"description": "Sample entity (not Qloo data)."},
    }


U, Q, C, O = CLUSTERS["urban"], CLUSTERS["quiet"], CLUSTERS["classic"], CLUSTERS["outdoor"]
A, M, B, P = "urn:entity:artist", "urn:entity:movie", "urn:entity:brand", "urn:entity:place"

UNIVERSE = [
    _ent("s-a1", "Neon Static (sample)", A, [U[1], U[3], U[4]], 0.9),
    _ent("s-a2", "Pavement Choir (sample)", A, [U[1], U[0], U[4]], 0.8),
    _ent("s-a3", "Willow & Ash (sample)", A, [Q[0], Q[1], Q[4]], 0.6),
    _ent("s-a4", "Marlow Quartet (sample)", A, [C[0], C[4], C[2]], 0.5),
    _ent("s-a5", "Dust Road Band (sample)", A, [O[3], O[0], Q[0]], 0.7),
    _ent("s-a6", "Gilded Hours (sample)", A, [Q[1], C[3], U[4]], 0.4),
    _ent("s-m1", "Midnight Lanes (sample)", M, [U[3], U[1], U[0]], 0.8),
    _ent("s-m2", "The Quiet Orchard (sample)", M, [Q[2], Q[4], Q[3]], 0.5),
    _ent("s-m3", "Grand Salon (sample)", M, [C[2], C[3], C[1]], 0.5),
    _ent("s-m4", "Summit Line (sample)", M, [O[4], O[0], O[2]], 0.7),
    _ent("s-m5", "Paper Lanterns (sample)", M, [Q[2], U[4], Q[1]], 0.45),
    _ent("s-b1", "Kickline (sample)", B, [U[0], U[2], U[3]], 0.9),
    _ent("s-b2", "Hearthbound (sample)", B, [Q[3], Q[4], Q[2]], 0.5),
    _ent("s-b3", "Maison Verre (sample)", B, [C[3], C[1], C[2]], 0.6),
    _ent("s-b4", "Ridgeway Gear (sample)", B, [O[0], O[1], O[2]], 0.7),
    _ent("s-b5", "Common Thread (sample)", B, [Q[4], U[0], Q[2]], 0.55),
    _ent("s-p1", "Basement 9 (sample)", P, [U[3], U[1], U[4]], 0.8),
    _ent("s-p2", "Fern Room Cafe (sample)", P, [Q[3], Q[2], Q[1]], 0.5),
    _ent("s-p3", "Chandler Hall (sample)", P, [C[0], C[2], C[3]], 0.5),
    _ent("s-p4", "Basecamp Yard (sample)", P, [O[1], O[0], O[4]], 0.6),
    _ent("s-p5", "Loft & Leaf (sample)", P, [Q[3], U[4], Q[2]], 0.45),
    # hybrids: sit between two tastes
    _ent("s-b6", "Concrete Garden (sample)", B, [U[0], O[0], O[2]], 0.5),
    _ent("s-a7", "Back Alley Banjo (sample)", A, [U[1], Q[0], O[3]], 0.45),
    _ent("s-m6", "Tailored Streets (sample)", M, [U[3], C[1], C[3]], 0.4),
    _ent("s-p6", "Terrace 88 (sample)", P, [U[3], C[2], O[1]], 0.4),
]
BY_ID = {e["entity_id"]: e for e in UNIVERSE}


def _seed_for(query):
    q = query.casefold()
    for e in UNIVERSE:
        if q in e["name"].casefold():
            return e
    pool = [e for e in UNIVERSE if e["types"][0] in (A, B)]
    return pool[int(hashlib.md5(q.encode()).hexdigest(), 16) % len(pool)]


def route(path, params):
    if path == "/search":
        e = _seed_for(params.get("query", ""))
        named = dict(e)
        named["name"] = params.get("query", e["name"]).strip().title() + " (sample)"
        BY_ID[named["entity_id"]] = named
        return {"results": [named]}
    if path == "/v2/insights":
        etype = params.get("filter.type")
        pool = [e for e in UNIVERSE if e["types"][0] == etype]
        excl = set(filter(None, (params.get("filter.exclude.tags") or "").split(",")))
        if excl:
            pool = [e for e in pool if not any(t["id"] in excl for t in e["tags"])]
        sig_ids = [s for s in (params.get("signal.interests.entities") or "").split(",") if s]
        sig_tags = {t["id"] for s in sig_ids if s in BY_ID for t in BY_ID[s]["tags"]}
        out = []
        for e in pool:
            if e["entity_id"] in sig_ids:
                continue
            if sig_tags:
                hit = sum(1 for t in e["tags"] if t["id"] in sig_tags)
                if hit == 0 and not excl:
                    continue  # like the real API: only affine entities come back
                aff = round(hit / 3, 3)
            else:
                aff = None
            c = dict(e)
            c["query"] = {"affinity": aff} if aff is not None else {}
            out.append((aff or 0, e["popularity"], c))
        out.sort(key=lambda x: (-x[0], -x[1]))
        take = int(params.get("take", 20))
        return {"results": {"entities": [c for _, _, c in out[:take]]}}
    return {"results": []}
