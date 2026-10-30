"""Collide brief: a collision title and a written brief.

An LLM (any OpenAI-compatible endpoint) may draft the brief, but every entity it
cites is checked against the Qloo evidence and unknown names are stripped.
Without an LLM, a deterministic template writes it from the data.
"""
import os
import re

import requests

MARK = re.compile(r"\[\[(.+?)\]\]")

MEDIUMS = {
    "music": "track",
    "fashion": "capsule collection",
    "film": "short film",
    "brand": "campaign",
    "food": "tasting menu",
}

SYSTEM = (
    "You write short, vivid creative briefs from evidence supplied by the user message. "
    "Rules: use ONLY entities listed in the evidence; wrap every entity name in double square brackets like [[Name]]; "
    "never invent numbers, sales or audience sizes; affinity is taste fit, not demand. "
    "Maximum 170 words. Use bold section labels with **double asterisks**."
)


def sections(medium):
    noun = MEDIUMS[medium]
    return (
        f"The creator is making a {noun}. Sections: **Your taste** (one line), **Your opposite** (2-3 opposite entities), "
        f"**The collision** (a concept for the {noun}, built from 2-3 bridge entities and the tags that link both sides), "
        f"**Make this week** (one concrete first step for the {noun})."
    )


GENERIC = {"other", "b2c", "b2b", "seasonal", "mainstream", "$", "$$", "$$$", "$$$$", "casual", "usa", "american", "2",
           "ngo", "nonprofit", "nonprofit brand", "lifestyle / casual", "fashion & apparel", "organizations established in 2017"}


def clean_tags(tags, n):
    """Tag names for display: drop catch-all tags and duplicates (Qloo has several ids with the same name)."""
    seen, out = set(), []
    for t in tags:
        name = t["name"].strip()
        k = name.lower()
        if k in GENERIC or k in seen or len(name) < 3:
            continue
        seen.add(k)
        out.append(name)
    return out[:n]


def title(r):
    a = (clean_tags(r["audience_tags"], 1) or ["Your taste"])[0]
    o = (clean_tags(r["opposite_tags"], 1) or ["its opposite"])[0]
    return f"{a} × {o}"


def rules(medium, r):
    """Four creative rules of thumb, filled in with this run's tags and entities."""
    noun = MEDIUMS[medium]
    a = ", ".join(clean_tags(r["audience_tags"], 3)) or "your taste"
    o = ", ".join(clean_tags(r["opposite_tags"], 3)) or "its opposite"
    br = sorted([x for v in r["bridges"].values() for x in v], key=lambda x: -x["strength"])[:2]
    bridge_names = " and ".join(x["name"] for x in br) or "the bridge cards"
    return [
        {"label": "Keep", "text": f"The look and feel of {a}. That is what keeps the {noun} recognisably yours."},
        {"label": "Borrow", "text": f"One idea from {o}, not all of it. A single borrowed element reads as a choice; several read as noise."},
        {"label": "Bridge with", "text": f"{bridge_names}. They link both sides, so use them as the connective tissue."},
        {"label": "Avoid", "text": f"Putting every clash card into one {noun}. Move the dial to decide how hard to push, then cut to one or two."},
    ]


def _evidence(r):
    seeds = ", ".join(s["name"] for s in r["seeds"])
    aud = ", ".join(t["name"] for t in r["audience_tags"][:6])
    opp = ", ".join(t["name"] for t in r["opposite_tags"][:6])
    return f"SEEDS: {seeds}\nAUDIENCE TAGS: {aud}\nOPPOSITE TAGS: {opp}\n" + "\n".join(r["ledger"])


def _llm(medium, r):
    key = os.environ.get("LLM_API_KEY", "")
    if not key:
        return None
    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    try:
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
                "temperature": 0.8,
                "max_tokens": 900,
                "reasoning": {"exclude": True},  # OpenRouter: do not return chain-of-thought
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": sections(medium) + "\n\nEVIDENCE:\n" + _evidence(r)},
                ],
            },
            timeout=40,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"] or ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        return text if _looks_clean(text) else None
    except Exception:  # noqa: BLE001 - fall back to the template
        return None


LEAKS = ("we need", "we have seed", "must use", "must be from", "need to pick", "could pick", "probably choose", "let's", "the user wants")


def _looks_clean(text):
    """Free reasoning models sometimes return their scratchpad. Accept only a finished brief."""
    low = text.lower()
    if any(x in low for x in LEAKS):
        return False
    labels = ("your taste", "your opposite", "the collision", "make this week")
    return text.lstrip().startswith("**") and all(l in low for l in labels) and len(text.split()) <= 260


def template(medium, r):
    noun = MEDIUMS[medium]
    seed = r["seeds"][0]["name"]
    opp = sorted([x for v in r["opposites"].values() for x in v], key=lambda x: -x["distance"])[:3]
    br = sorted([x for v in r["bridges"].values() for x in v], key=lambda x: -x["strength"])[:2]
    a_tags = ", ".join(t["name"] for t in r["audience_tags"][:3])
    o_tags = ", ".join(t["name"] for t in r["opposite_tags"][:3])
    opp_txt = ", ".join(f"[[{x['name']}]]" for x in opp) or "no clear opposite"
    br_txt = " and ".join(f"[[{x['name']}]]" for x in br) or "no clear bridge"
    if br:
        link = f"linking {', '.join(br[0]['audience_side']) or 'your taste'} with {', '.join(br[0]['opposite_side']) or 'its opposite'}"
    else:
        link = "with a thin overlap"
    return (
        f"**Your taste.** [[{seed}]], leaning {a_tags}.\n"
        f"**Your opposite.** {opp_txt}, leaning {o_tags}.\n"
        f"**The collision.** Build the {noun} around {br_txt}, the common ground that makes the clash work ({link}).\n"
        f"**Make this week.** Sketch one {noun} that keeps the look of {a_tags} and takes the mood of {o_tags}."
    )


def verify(text, allowed):
    allowed_cf = {a.casefold() for a in allowed}
    stats = {"verified": 0, "removed": 0}

    def fix(m):
        name = m.group(1).strip()
        if name.casefold() in allowed_cf:
            stats["verified"] += 1
            return f"[[{name}]]"
        stats["removed"] += 1
        return name

    return MARK.sub(fix, text), stats["verified"], stats["removed"]


def build(medium, r):
    text = _llm(medium, r)
    used_llm = text is not None
    if not text:
        text = template(medium, r)
    text, verified, removed = verify(text, r["allowed_names"])
    return {"text": text, "verified": verified, "removed": removed, "llm": used_llm}
