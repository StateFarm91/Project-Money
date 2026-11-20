"""Download the identity floor's two ONNX models and verify them by pinned sha256.

    python3 scripts/fetch_face_models.py [MODEL_DIR]     (default: $BRAMBLELOOP_FACE_MODEL_DIR
                                                           or /app/models/face)
    python3 scripts/fetch_face_models.py --best-effort MODEL_DIR

YuNet (MIT) and SFace (Apache-2.0), from the OpenCV model zoo mirror on Hugging Face. A file
whose sha256 is not the pinned one is deleted and the script exits non-zero; the embedder
refuses unpinned weights anyway (`visual.face_embedder`). No key, no cost (~39 MB).

The pins are read from `src/brambleloop/visual/face_embedder.py` by file path, without
importing the `brambleloop` package, so the image build can run this before the rest of the
source is copied (the Docker layer is then rebuilt only when the pins change).

`--best-effort` (used by the Dockerfile) always exits 0 so an unreachable mirror can never
break a deploy. The identity floor then reads UNMEASURED and every Laura frame HOLDs: a
missing or mismatched model is never a PASS, because `SFaceEmbedder.load` re-verifies both
sha256 pins every time it loads.
"""
import hashlib
import importlib.util
import os
import sys
import urllib.request
from pathlib import Path

EMBEDDER_PY = Path(__file__).resolve().parents[1] / "src/brambleloop/visual/face_embedder.py"


def _pins(path: Path = EMBEDDER_PY):
    spec = importlib.util.spec_from_file_location("_face_embedder_pins", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # stdlib-only at import time (hashlib, io, os, pathlib)
    return mod.MODELS, mod.DEFAULT_MODEL_DIR


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(target: str, models=None) -> int:
    models = models if models is not None else _pins()[0]
    d = Path(target)
    d.mkdir(parents=True, exist_ok=True)
    bad = 0
    for m in models.values():
        p = d / m["file"]
        try:
            if not (p.is_file() and _sha(p) == m["sha256"]):
                tmp = p.with_suffix(p.suffix + ".part")
                with urllib.request.urlopen(m["url"], timeout=300) as r, tmp.open("wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                tmp.replace(p)
        except Exception as exc:  # noqa: BLE001 - reported; the embedder then refuses to load
            print(f"UNAVAILABLE {m['file']}: {type(exc).__name__}: {exc}")
            bad += 1
            continue
        got = _sha(p)
        if got != m["sha256"]:
            p.unlink()
            print(f"REFUSED {m['file']}: sha256 {got} is not the pinned {m['sha256']}")
            bad += 1
        else:
            print(f"ok {m['file']} {got[:12]} ({m['licence']})")
    return 1 if bad else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    best_effort = "--best-effort" in args
    args = [a for a in args if a != "--best-effort"]
    target = args[0] if args else os.environ.get("BRAMBLELOOP_FACE_MODEL_DIR") or _pins()[1]
    rc = main(target)
    if rc and best_effort:
        print("face models are NOT installed: the identity floor reads UNMEASURED and Laura "
              "identity HOLDs (never PASS) until a rebuild fetches them")
        rc = 0
    sys.exit(rc)
