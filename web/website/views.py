import os
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from website import classifier, status_tracker
from website.auth import require_auth
from website.errors import MalformedImage, make_error

views = Blueprint("views", __name__)


@views.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        github_url=os.environ.get("GITHUB_URL", "https://github.com"),
        year=datetime.utcnow().year,
    )


@views.route("/classifier", methods=["POST"])
@require_auth
def classify_image():
    if "image" not in request.files:
        status_tracker.bump_fail()
        return make_error(400, "Missing image field")
    f = request.files["image"]
    try:
        data = f.read()
        matches = classifier.classify(data, f.filename or "")
    except MalformedImage:
        status_tracker.bump_fail()
        return make_error(400, "Unsupported image format")
    except Exception:
        status_tracker.bump_fail()
        return make_error(500, "Classifier failure")
    status_tracker.bump_success()
    return jsonify({"matches": matches}), 200


@views.route("/status", methods=["GET"])
@require_auth
def status():
    s, f = status_tracker.snapshot()
    return jsonify({
        "status": {
            "uptime": status_tracker.uptime(),
            "processed": {"success": s, "fail": f},
            "health": "ok" if classifier.health() else "error",
            "api_version": 1,
        }
    }), 200
