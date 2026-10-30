"""Live API check. Run this FIRST with your real key: python smoke.py Nike Chicago

Spends about 8 Qloo calls (cached afterwards). It prints what came back at each
step so you can see whether tags, popularity, affinity and the exclude-tags
filter behave the way Foil assumes. Paste the output here if anything looks off.
"""
import sys

import pipeline
import qloo


def main():
    seed = sys.argv[1] if len(sys.argv) > 1 else "Nike"
    city = sys.argv[2] if len(sys.argv) > 2 else ""
    if not qloo.KEY and not qloo.is_mock():
        sys.exit("Set QLOO_API_KEY in .env first.")
    ent = qloo.search(seed)
    print("SEARCH ->", ent and {k: ent[k] for k in ("id", "name", "types")})
    if not ent:
        sys.exit("Search returned nothing. Check the key and base URL.")
    raw = qloo.insights({"filter.type": "urn:entity:artist", "signal.interests.entities": ent["id"], "take": 5})
    print("INSIGHTS top-level keys:", list(raw.keys()) if isinstance(raw, dict) else type(raw))
    ents = qloo.entities(raw)
    print("entities parsed:", len(ents))
    for e in ents[:3]:
        print(" -", e["name"], "| tags:", [t["name"] for t in e["tags"]][:4], "| affinity:", e["affinity"], "| pop:", e["popularity"])
    if ents and not any(e["tags"] for e in ents):
        print("WARNING: no tags in results. Foil needs tags to measure distance.")
    print("\nFULL RUN ...")
    r = pipeline.run([seed], city)
    print("scores:", r["scores"])
    print("audience tags:", [t["name"] for t in r["audience_tags"]])
    print("opposite tags:", [t["name"] for t in r["opposite_tags"]])
    for k, v in r["opposites"].items():
        print(f"opposites[{k}]:", [(x["name"], x["distance"]) for x in v[:3]])
    for k, v in r["bridges"].items():
        print(f"bridges[{k}]:", [(x["name"], x["strength"]) for x in v[:2]])
    print("warnings:", r["warnings"])
    print("calls used:", qloo.stats())


if __name__ == "__main__":
    main()
