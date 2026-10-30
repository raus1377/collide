# Collide: Devpost description (fill the [brackets] after your live run)

## What it does
Collide helps a creator make something their taste would never make. Enter up to three things you love and what you are making (a track, capsule collection, short film, campaign or tasting menu). Collide uses Qloo's taste graph to build a collision board of "keep", "bridge" and "clash" cards, with a taste dial that slides from "your world" to "full opposite" and re-draws the board instantly. It adds four collision rules, a short brief, and exports to Markdown or print.

## Why it is Qloo-powered (and would not work without it)
- `/search` resolves what you love to Qloo entities.
- `/v2/insights` with `signal.interests.entities` returns your taste neighbours across artists, film/TV, brands and places.
- `/v2/insights` with `filter.exclude.tags` finds candidates outside your top tags. Collide measures each one's taste distance from Qloo's own tags, so the clash cards are measured.
- A second `/v2/insights` call with you plus the clash as signals finds the bridge items, scored by how much they link both sides.
An LLM alone cannot name real entities that sit far from, or between, two tastes.

## Example run
Loves: [your seeds]. Collision title: [title]. Clash cards: [2 names]. Bridge: [name]. Making a [medium]: [one sentence on the idea you took from it].

## How we built it
Python and Flask, a server-side Qloo client with caching, a call budget and retries, a tag-based scoring pipeline, and a single-page front end. The dial and shuffle run in the browser from one API run, so experimenting costs no extra Qloo calls. An optional LLM writes the brief, but every entity it cites is checked against the Qloo results and unknown names are stripped. Tests run offline.

## Honest limits
Affinity is taste fit, not a prediction of success. The collision rules are creative rules of thumb filled in with your tags and entities. Distance depends on Qloo's tag coverage for the chosen entities.

## What's next
Saving boards, collaborating on a board with another creator, and pulling in a creator's own catalog as the starting taste.
