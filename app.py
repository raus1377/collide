"""Collide: a taste dial and collision board for creators, from Qloo's taste graph."""
import os
import threading
import time

import requests
from flask import Flask, jsonify, request, send_from_directory

import brief
import pipeline
import qloo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"), static_url_path="/static")

_hits = {}
_hits_lock = threading.Lock()
RATE = int(os.environ.get("COLLIDE_RATE_PER_MIN", "6"))


def rate_ok(ip):
    now = time.time()
    with _hits_lock:
        recent = [t for t in _hits.get(ip, []) if now - t < 60]
        if len(recent) >= RATE:
            _hits[ip] = recent
            return False
        recent.append(now)
        _hits[ip] = recent
    return True


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "qloo_key_configured": bool(qloo.KEY), "llm_configured": bool(os.environ.get("LLM_API_KEY")), **qloo.stats()})


@app.route("/api/collide", methods=["POST"])
def api_collide():
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "?").split(",")[0].strip()
    if not rate_ok(ip):
        return jsonify({"error": "Too many runs in a minute. Wait a moment and try again."}), 429
    body = request.get_json(silent=True) or {}
    seeds = [s.strip()[:60] for s in body.get("seeds", []) if isinstance(s, str) and s.strip()][:3]
    city = (body.get("city") or "").strip()[:60]
    medium = body.get("medium") if body.get("medium") in brief.MEDIUMS else "music"
    if not seeds:
        return jsonify({"error": "Add at least one artist, brand or show you love."}), 400
    try:
        result = pipeline.run(seeds, city)
        result["medium"] = medium
        result["title"] = brief.title(result)
        result["rules"] = brief.rules(medium, result)
        result["brief"] = brief.build(medium, result)
        result["mock"] = qloo.is_mock()
        return jsonify(result)
    except pipeline.PipelineError as e:
        return jsonify({"error": str(e)}), 422
    except qloo.BudgetExceeded as e:
        return jsonify({"error": str(e)}), 429
    except qloo.QlooError as e:
        return jsonify({"error": str(e)}), 502
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 502
        return jsonify({"error": f"Qloo error ({code})."}), 502
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Something went wrong: {e}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
