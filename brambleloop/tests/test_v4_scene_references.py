"""V4 / audit P1-a: owner-approved room references reach every in-room request; same-room check.

No network and no spend. The FLUX 3 generator runs on `StubRenderer`, exactly as
test_opus2_laura_home drives it, and the reference paths each request would send are read
back. The room image is a test fixture written to a temporary manifest; the committed
manifest ships empty, because approving a room image is owner direction.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_v4_scene_references.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from brambleloop.creative import flux3_generator as FG  # noqa: E402
from brambleloop.visual import laura_home as H  # noqa: E402
from brambleloop.visual import room_references as RR  # noqa: E402

import test_opus2_laura_home as LH  # noqa: E402


def _png(colour=(180, 170, 150)):
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), colour).save(buf, "PNG")
    return buf.getvalue()


def _manifest(entries):
    d = Path(tempfile.mkdtemp(prefix="rooms_"))
    rooms = []
    for e in entries:
        e = dict(e)
        if "data" in e:
            (d / e["file"]).write_bytes(e.pop("data"))
        rooms.append(e)
    (d / "MANIFEST.json").write_text(json.dumps({"version": 1, "rooms": rooms}))
    return d / "MANIFEST.json"


ROOM = H.scene_for(LH.CIR.slug)["room"]          # the blanket's room (the nursery)
DATA = _png()
GOOD = {"room": ROOM, "file": "nursery.png", "sha256": hashlib.sha256(DATA).hexdigest(),
        "provenance": "test fixture (not an owner-approved image)", "decision_id": "D-TEST",
        "data": DATA}


def test_the_committed_manifest_ships_empty_and_nothing_is_approved():
    assert json.loads(RR.MANIFEST.read_text())["rooms"] == []
    for room in H.ROOMS:
        assert RR.approved(room) is None and RR.scene_supplement(room) == []
        assert "no approved room reference" in RR.refusal(room)


def test_only_a_complete_unaltered_owner_decided_entry_is_used():
    m = _manifest([GOOD])
    assert RR.approved(ROOM, manifest=m)["sha256"] == GOOD["sha256"]
    assert RR.scene_supplement(ROOM, manifest=m)[0][0] == "scene_reference"
    tampered = _manifest([{**GOOD, "sha256": "0" * 64}])
    assert "no longer match" in RR.refusal(ROOM, manifest=tampered)
    undecided = _manifest([{**GOOD, "decision_id": ""}])
    assert "decision_id" in RR.refusal(ROOM, manifest=undecided)
    twice = _manifest([GOOD, {**GOOD, "file": "other.png", "data": _png((1, 2, 3))}])
    assert "one room, one reference" in RR.refusal(ROOM, manifest=twice)
    gone = _manifest([{k: v for k, v in GOOD.items() if k != "data"}])
    assert "missing" in RR.refusal(ROOM, manifest=gone)


def _with_manifest(m):
    real = RR.MANIFEST
    RR.MANIFEST = m
    return real


def _requests(m):
    real = _with_manifest(m)
    try:
        g, stub = LH._gen()
        refs = LH._refs(g)
        out = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="flat",
                         references=refs, outfit=None, attempt=1)
        anchor = {"data": out["data"], "sha256": hashlib.sha256(out["data"]).hexdigest(),
                  "status": "PASS", "checker": "stub judge"}
        g.anchor_lookup = lambda s, v, r: anchor
        product_only = list(stub.calls[-1]["refs"])
        g.generate(stage="lifestyle_generation", role="lifestyle", brief="Laura folds it",
                   references=refs + LH._laura_refs(), outfit=LH.OUTFIT, attempt=1)
        lifestyle = list(stub.calls[-1]["refs"])
        g.generate(stage="role_generation", role="detail", brief="the lattice up close",
                   references=refs, outfit=None, attempt=1)
        styled = list(stub.calls[-1]["refs"])
        return product_only, lifestyle, styled
    finally:
        RR.MANIFEST = real


def _shas(paths):
    """A reference's identity: its bytes' hash while the file exists (stage work files are
    removed after the call, and are named by their own hash)."""
    out = []
    for p in paths:
        f = Path(p)
        out.append(hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else f.stem)
    return out


def test_every_in_room_request_carries_the_same_room_reference():
    m = _manifest([GOOD])
    product_only, lifestyle, styled = _requests(m)
    assert GOOD["sha256"] in _shas(lifestyle) and GOOD["sha256"] in _shas(styled)
    # The product-only flat lay is not set in a room, so it carries no room.
    assert GOOD["sha256"] not in _shas(product_only)
    # It comes after the canonical three and the product references, never in place of one.
    life = _shas(lifestyle)
    assert life.index(GOOD["sha256"]) >= 7 and len(life) == len(set(life))


def test_without_an_approved_room_the_requests_are_unchanged():
    empty = _manifest([])
    _po, lifestyle, styled = _requests(empty)
    assert GOOD["sha256"] not in _shas(lifestyle) + _shas(styled)


class _Judge:
    name = "stub-judge"

    def __init__(self, answer):
        self.answer = answer

    def read(self, prompt, images, *, system, max_tokens):
        assert "same_room" in prompt and len(images) == 2
        return {"answered": self.answer is not None, "reading": self.answer,
                "why": "not answered"}


def test_the_same_room_reading_passes_fails_or_stays_unknown():
    frame = _png((120, 110, 100))
    ok = RR.same_room(_Judge({"same_room": "yes"}), DATA, frame, room=ROOM)
    bad = RR.same_room(_Judge({"same_room": "no", "differences": "tiled floor"}), DATA, frame,
                       room=ROOM)
    unclear = RR.same_room(_Judge({"same_room": "unclear"}), DATA, frame, room=ROOM)
    unread = RR.same_room(_Judge(None), DATA, frame, room=ROOM)
    noref = RR.same_room(_Judge({"same_room": "yes"}), None, frame, room=ROOM)
    nojudge = RR.same_room(None, DATA, frame, room=ROOM)
    assert ok["status"] == "PASS" and ok["check"] == "home_consistency"
    assert bad["status"] == "FAIL" and bad["code"] == "home_consistency", bad
    assert "tiled floor" in bad["why"]
    for v in (unclear, unread, noref, nojudge):
        assert v["status"] == "UNKNOWN", v


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
