"""Download the identity floor's two ONNX models and verify them by pinned sha256.

    python3 scripts/fetch_face_models.py [MODEL_DIR]     (default: $BRAMBLELOOP_FACE_MODEL_DIR
                                                           or /app/models/face)

YuNet (MIT) and SFace (Apache-2.0), from the OpenCV model zoo mirror on Hugging Face. A file
whose sha256 is not the pinned one is deleted and the script exits non-zero; the embedder
refuses unpinned weights anyway (`visual.face_embedder`). No key, no cost (~39 MB).
"""
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from brambleloop.visual.face_embedder import DEFAULT_MODEL_DIR, MODELS  # noqa: E402


def main(target: str) -> int:
    d = Path(target)
    d.mkdir(parents=True, exist_ok=True)
    bad = 0
    for m in MODELS.values():
        p = d / m["file"]
        if not (p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == m["sha256"]):
            with urllib.request.urlopen(m["url"], timeout=300) as r:
                p.write_bytes(r.read())
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != m["sha256"]:
            p.unlink()
            print(f"REFUSED {m['file']}: sha256 {got} is not the pinned {m['sha256']}")
            bad += 1
        else:
            print(f"ok {m['file']} {got[:12]} ({m['licence']})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else
                  os.environ.get("BRAMBLELOOP_FACE_MODEL_DIR", DEFAULT_MODEL_DIR)))
