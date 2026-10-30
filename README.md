# Collide

**A website for making something your taste would never make.** Built for the Qloo Agentic Hackathon.

Tell Collide up to three things you love (artists, brands, shows) and what you're making (a track, capsule collection, short film, campaign or tasting menu). It uses Qloo's taste graph to build a **collision board**:

- **Keep** cards: what lives in your own taste world.
- **Clash** cards: entities measurably far from it.
- **Bridge** cards: the few things Qloo ranks highly for your taste and the clash together, with the tags that link both sides.

A **taste dial** slides from "your world" to "full opposite" and re-draws the board instantly. **Shuffle** deals a new hand. Both run in the browser from one API run, so experimenting costs no extra credits. Copy the brief or download the whole board as Markdown.

## How Qloo is used (and why it can't be removed)

| Step | Qloo call | Purpose |
|---|---|---|
| Resolve | `GET /search` | Turn what you love into Qloo entities |
| Audience | `GET /v2/insights` with `signal.interests.entities` | What your taste neighbours love across artists, film/TV, brands, places |
| Clash | `GET /v2/insights` with `filter.exclude.tags` | Candidates outside your top tags |
| Bridge | `GET /v2/insights` with you + clash as signals | Items between both tastes |

**Distance and bridge strength are computed from Qloo's own tags** (`pipeline.py`), so they stay honest even if a filter is ignored. An LLM alone cannot name real entities that sit far from, or between, two tastes.

## Honesty features

- The brief may only cite entities present in the Qloo evidence. Unknown names are stripped and counted.
- Affinity is taste fit, not a prediction of success. The page says so.
- Without an LLM key, a deterministic template writes the brief.
- `FOIL_MOCK=1` uses **fictional sample data** and shows a banner. It is not Qloo output.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env           # add QLOO_API_KEY
python smoke.py "Billie Eilish"  # checks the live API (about 8 calls)
python app.py                  # http://localhost:5000
pytest                         # offline, no key needed
```

## Credit protection

Responses are cached on disk (`.qloo_cache.json`, gitignored: real Qloo responses must not be committed). `QLOO_MAX_CALLS` caps live calls. A run uses about 8 to 12 calls; repeats are free. `/healthz` shows usage.

## Deploy (Render free tier)

Push to a public GitHub repo, create a Web Service from it, and set `QLOO_API_KEY` (optionally `LLM_API_KEY`) in the dashboard. Free-tier disk is ephemeral, so after each deploy run your demo searches once to warm the cache.

MIT licensed.

## Judging criteria: where to find the evidence

| Criterion | Evidence in this repo |
|---|---|
| Technological implementation | `qloo.py` (cache, call budget, retries, key kept server-side), `pipeline.py` (four-step Qloo pipeline, tag-based distance, bridge scoring, fallback, measured-vs-popularity baseline), `brief.py` (LLM output verified against Qloo evidence), `tests/` (offline) |
| Design | A Prizd-inspired editorial interface (serif display type, mono labels, stat strip, role filter chips, grid/list toggle) from taste to board: a taste dial and shuffle that re-draw the board instantly, collision rules, brief, evidence ledger, Markdown export and print. Works on mobile and in dark mode |
| Potential impact | Gives independent creators a concrete starting board and four rules for a specific project (track, collection, short film, campaign, menu). Inspiration, not a guarantee |
| Quality of the idea | Uses Qloo to find the measurable opposite of a taste and the bridge between the two, then lets the creator choose how hard to collide them |
