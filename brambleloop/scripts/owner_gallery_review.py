"""Run the owner-frame intake (`visual.owner_frames.ingest`) on a set of owner files, locally.

Builds a scratch database with the product certified and its assets built through the real
handlers (the same chain `tests/test_search_hero_publish._chain` drives), then ingests the
files with the PRODUCTION judges (`candidate_gates.RealJudges`). With no funded vision
transport those judges read UNKNOWN, as production would. The only stand-in is the
pointer that answers `visual.scale` and the wall-strip question. Its boxes are a builder's
reading of each frame, labelled `stub_pointer` in every check they feed. Code does all the
measuring.

Usage (from brambleloop/):
  PYTHONPATH=src:tests python3 scripts/owner_gallery_review.py OUT.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import _tmp; _tmp.install()  # noqa: E402,E702

ASSETS = ROOT / "research" / "owner_assets" / "flux_basket_2026-11-21"
SLUG, CATEGORY = "market-basket-small", "basket"
HEAD = [0.559, 0.056, 0.729, 0.239]     # chin to crown, both Laura frames (same pose)

# name -> (role, alternate, laura, scene, scale reading, wall strip)
FRAMES = {
    "5fc4ac77": ("hero", False, False,
                 "standing alone on a pale wood table against a plain cream wall",
                 {"anchor": "none", "setting": "plain"}, [0.459, 0.459, 0.547, 0.833]),
    "2fb50fed": ("colour_context", False, False,
                 "on a wooden dresser beside a vase of eucalyptus and a folded cloth",
                 {"anchor": "none", "setting": "scene"}, [0.4331, 0.5451, 0.4715, 0.7031]),
    "0394c9ef": ("lifestyle", False, False,
                 "on a wooden dresser holding rolled cloths and small knitted items",
                 {"anchor": "none", "setting": "scene"}, [0.4464, 0.4876, 0.4799, 0.7200]),
    "7fe9128f": ("angle", False, False,
                 "on a wooden dresser, seen from above to show the inside",
                 {"anchor": "none", "setting": "scene"}, [0.3618, 0.5660, 0.4057, 0.7535]),
    "6c6539b4": ("detail", False, False,
                 "close view of the stitches and stripes on a wooden dresser",
                 {"anchor": "none", "setting": "scene"}, [0.4715, 0.4080, 0.5154, 0.6814]),
    "f37f518e": ("size", False, True,
                 "held in both hands by a woman in a sage blouse in a bright room",
                 {"anchor": "adult head, chin to crown", "anchor_box": HEAD,
                  "product_box": [0.545, 0.432, 0.806, 0.595], "setting": "scene"},
                 [0.6579, 0.4792, 0.7018, 0.5929]),
    "7b132c05": ("size", True, True,
                 "held by a woman placing a folded cloth inside it",
                 {"anchor": "adult head, chin to crown", "anchor_box": HEAD,
                  "product_box": [0.545, 0.451, 0.798, 0.608], "setting": "scene"},
                 [0.7018, 0.4948, 0.7456, 0.6059]),
}


class StubPointer:
    """Answers the two pointing questions with a builder's fixed reading per frame."""

    name = "stub_pointer (builder reading; NOT a production judge)"

    def __init__(self):
        import hashlib

        self.by_sha = {}
        for n, (_r, _a, _l, _s, sc, wall) in FRAMES.items():
            sha = hashlib.sha256((ASSETS / f"{n}-image.png").read_bytes()).hexdigest()
            self.by_sha[sha] = (sc, wall)

    def read(self, prompt, images, *, system, max_tokens):
        import hashlib

        sc, wall = self.by_sha.get(hashlib.sha256(images[0]).hexdigest(), (None, None))
        if "Task: product_scale" in prompt and sc is not None:
            return {"answered": True, "reading": sc}
        if "Task: wall_column" in prompt and wall is not None:
            return {"answered": True, "reading": {"wall_box": wall}}
        return {"answered": False, "why": "stub has no reading for this frame/question"}


def main(out_path: str) -> int:
    import test_search_hero_publish as SH
    from brambleloop.core.db import Database
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import owner_frames as OF

    path, version, rh = SH._chain(SLUG, CATEGORY)
    db = Database(f"sqlite:///{path}")
    files = [{"name": f"{n}-image.png", "path": str(ASSETS / f"{n}-image.png"), "role": r,
              "alternate": a, "laura_present": la, "scene": sc}
             for n, (r, a, la, sc, _s, _w) in FRAMES.items()]
    out = OF.ingest(db, SLUG, version, files, actor="owner",
                    judges=CG.RealJudges(db), pointer=StubPointer())
    keep = {"slug": out["slug"], "version": out["version"], "release": out["release"],
            "certified": out["certified"], "why": out.get("why"),
            "consistency": {k: out["consistency"].get(k) for k in ("status", "why")},
            "blockers": out["blockers"],
            "frames": [{k: f[k] for k in ("name", "sha256", "role", "job", "alternate",
                                          "laura_present", "alt_text", "ok")}
                       | {"gates": {g: {"status": v["status"], "why": v["why"][:400]}
                                    for g, v in f["gates"].items()}}
                       for f in out["frames"]]}
    Path(out_path).write_text(json.dumps(keep, indent=2, default=str))
    print(json.dumps({"certified": out["certified"], "blockers": len(out["blockers"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "owner_gallery_review.json"))
