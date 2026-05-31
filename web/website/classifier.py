import os
from io import BytesIO

from PIL import Image

from website.errors import MalformedImage

_model = None
_healthy = False


def boot():
    global _model, _healthy
    try:
        from ultralytics import YOLO
        weights = os.environ.get("YOLO_WEIGHTS", "yolov8n-cls.pt")
        _model = YOLO(weights)
        _model(Image.new("RGB", (64, 64), color="red"), verbose=False)
        _healthy = True
    except Exception:
        _model = None
        _healthy = False


def health() -> bool:
    return _healthy


def classify(file_bytes: bytes, filename: str):
    # interface.md is literal: 'images uploaded MUST end in ".png" or ".jpeg"'.
    # Match it exactly (case-sensitive) — ".PNG"/".JPEG" do NOT satisfy the spec.
    name = filename or ""
    if not (name.endswith(".png") or name.endswith(".jpeg")):
        raise MalformedImage("filename must end with .png or .jpeg")

    try:
        probe = Image.open(BytesIO(file_bytes))
        fmt = probe.format          # actual decoded format: 'PNG' | 'JPEG' | 'GIF' | ...
        probe.verify()
        img = Image.open(BytesIO(file_bytes)).convert("RGB")
    except Exception as exc:
        raise MalformedImage("undecodable image bytes") from exc

    # interface.md: 'Supported image types SHALL be PNG and JPEG.'
    # Enforce by actual content, not just the filename — GIF/WEBP/BMP bytes
    # named .png must still be rejected.
    if fmt not in ("PNG", "JPEG"):
        raise MalformedImage(f"unsupported image format: {fmt}")

    if _model is None:
        raise MalformedImage("classifier not loaded")

    results = _model(img, verbose=False)
    if not results:
        raise MalformedImage("no inference result")

    r0 = results[0]
    probs = getattr(r0, "probs", None)
    names = getattr(r0, "names", None)
    if probs is None or names is None:
        raise MalformedImage("model returned no probabilities")

    top_indices = list(probs.top5)
    raw = []
    for i in top_indices:
        s = float(probs.data[i])
        if s > 0.0:
            raw.append((str(names[i]), s))

    matches = []
    running = 0.0
    for name_, score in raw:
        if score > 1.0:
            score = 1.0
        if running + score > 1.0:
            break
        matches.append({"name": name_, "score": score})
        running += score

    if not matches and raw:
        n, s = raw[0]
        matches.append({"name": n, "score": min(s, 1.0)})

    return matches
