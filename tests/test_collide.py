import os
import sys

os.environ["FOIL_MOCK"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brief  # noqa: E402
import pipeline  # noqa: E402


def _run(city="Chicago"):
    return pipeline.run(["Kickline"], city)


def test_pipeline_has_all_three_pools_for_the_board():
    r = _run()
    assert r["audience"] and r["opposites"] and r["bridges"]
    assert all("distance" in x for v in r["opposites"].values() for x in v)
    assert all("strength" in x for v in r["bridges"].values() for x in v)


def test_title_format():
    t = brief.title(_run())
    assert " × " in t and len(t) > 5


def test_every_medium_writes_a_verified_brief():
    r = _run()
    for medium in brief.MEDIUMS:
        out = brief.build(medium, r)
        assert out["removed"] == 0 and out["verified"] >= 2
        assert brief.MEDIUMS[medium] in out["text"]


def test_verify_strips_unknown_names():
    text, ok, bad = brief.verify("Try [[Real One]] and [[Made Up]].", ["Real One"])
    assert ok == 1 and bad == 1 and "[[Made Up]]" not in text


def test_bridges_touch_both_sides():
    r = _run()
    real = [b for v in r["bridges"].values() for b in v if b["strength"] > 0]
    assert real and all(b["audience_side"] and b["opposite_side"] for b in real)


def test_empty_seed_is_rejected():
    try:
        pipeline.run([" "], "")
    except pipeline.PipelineError:
        return
    raise AssertionError("expected PipelineError")


def test_baseline_reports_measured_vs_popularity_only():
    b = _run()["baseline"]
    assert b["naive"] is not None and b["measured"] >= b["naive"]


def test_fallback_when_nothing_outside_audience_tags(monkeypatch):
    real = pipeline.qloo.insights

    def fake(params):
        if "filter.exclude.tags" in params:
            return {"results": {"entities": []}}
        return real(params)

    monkeypatch.setattr(pipeline.qloo, "insights", fake)
    r = pipeline.run(["Kickline"], "Chicago")
    assert r["opposites"] and any("farthest related" in w for w in r["warnings"])


def test_llm_scratchpad_is_rejected_and_titles_skip_generic_tags():
    import brief
    leak = "We need to produce a creative brief with sections: **Your taste** ... Must use ONLY entities."
    assert not brief._looks_clean(leak)
    ok = "**Your taste** a. **Your opposite** b. **The collision** c. **Make this week** d."
    assert brief._looks_clean(ok)
    assert brief.clean_tags([{"name": "Other"}, {"name": "Fashion"}, {"name": "fashion"}, {"name": "Baroque"}], 3) == ["Fashion", "Baroque"]
