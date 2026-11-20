"""V4 / audit P1-a: owner-approved room reference images, and a same-room check.

Laura's home (`visual.laura_home`) is described in words only. Text cannot lock geometry
for an image model, so the kitchen in one listing's photographs is not the kitchen in the
next. The audit names a room reference image as the only practical geometry lock.

This module holds the plumbing for that lock. It creates no room image and approves none:
generating or approving one is owner direction (OA in the audit).

* **The manifest** (`visual/room_refs/MANIFEST.json`) is one entry per room. Each entry
  records the file, its sha256, its provenance and the owner decision that approved it. It
  ships empty.
* **`approved(room)`** returns the entry only if all of these hold:
  - the file exists and its bytes still hash to the recorded sha256;
  - an owner `decision_id` is recorded;
  - its provenance is stated.
  Anything else returns None, with the reason in `refusal(room)`.
* **`scene_supplement(room)`** is the reference pair every in-room generation carries: the
  Laura lifestyle frame, its stage-D variants, and the product-only styled scene. It is
  `("scene_reference", path)` after the product references. It never displaces the
  canonical three or the certified product references; `image_stages.campaign_references`
  enforces that order.
* **`same_room(judge, ref, candidate)`** is a blind vision reading, run only through the
  owner-gated `image_vision` judge.
  - "same room" → PASS;
  - "different room" → FAIL `home_consistency`;
  - unanswered or unclear → UNKNOWN, never PASS.

With no approved room the generation proceeds exactly as before, and the check reports UNKNOWN
"no approved room reference".
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROLE = "scene_reference"
CHECK = "home_consistency"
MANIFEST = Path(__file__).resolve().parent / "room_refs" / "MANIFEST.json"
REQUIRED = ("room", "file", "sha256", "provenance", "decision_id")


def _manifest(path: Path | None = None) -> list[dict]:
    p = Path(path or MANIFEST)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return list(data.get("rooms") or [])


def _resolve(entry: dict, manifest: Path) -> Path:
    f = Path(entry["file"])
    return f if f.is_absolute() else manifest.parent / f


def refusal(room: str, *, manifest: Path | None = None) -> str | None:
    """Why `room` has no usable reference (None when it has one)."""
    m = Path(manifest or MANIFEST)
    entries = [e for e in _manifest(m) if e.get("room") == room]
    if not entries:
        return f"no approved room reference for {room!r}"
    if len(entries) > 1:
        return f"{len(entries)} manifest entries for {room!r}; one room, one reference"
    e = entries[0]
    missing = [k for k in REQUIRED if not str(e.get(k) or "").strip()]
    if missing:
        return f"{room!r} reference lacks {missing}"
    f = _resolve(e, m)
    if not f.exists():
        return f"{room!r} reference file {e['file']} is missing"
    if hashlib.sha256(f.read_bytes()).hexdigest() != e["sha256"]:
        return f"{room!r} reference bytes no longer match sha256 {e['sha256'][:12]}"
    return None


def approved(room: str, *, manifest: Path | None = None) -> dict | None:
    m = Path(manifest or MANIFEST)
    if refusal(room, manifest=m) is not None:
        return None
    e = next(e for e in _manifest(m) if e.get("room") == room)
    return {**e, "path": str(_resolve(e, m))}


def scene_supplement(room: str | None, *, manifest: Path | None = None) -> list[tuple[str, str]]:
    """[("scene_reference", path)] for an approved room, else []."""
    if not room:
        return []
    e = approved(room, manifest=manifest)
    return [(ROLE, e["path"])] if e else []


def same_room_prompt() -> str:
    return ("Image 1 is a reference photograph of a room. Image 2 is another photograph. "
            "Ignore the people, the products and any small objects. Compare only the room: "
            "its walls, floor, windows, cabinets or built-in furniture and their layout. "
            'Answer as JSON: {"same_room": "yes" | "no" | "unclear", "differences": '
            '"<short list or empty>"}')


def same_room(judge, ref_bytes: bytes | None, candidate_bytes: bytes, *, room: str) -> dict:
    """The blind same-room reading for one generated frame against its room reference."""
    from . import vision_judges as VJ

    if not ref_bytes:
        return VJ._c(CHECK, VJ.UNKNOWN, f"no approved room reference for {room!r}",
                     needs="owner-approved room reference")
    got = VJ.ask(judge, "same_room", same_room_prompt(), [ref_bytes, candidate_bytes])
    if not got["answered"]:
        return VJ._c(CHECK, VJ.UNKNOWN, f"not judged: {got['why']}", needs="vision judge")
    v = VJ._tri(got["reading"].get("same_room"))
    if v is True:
        return VJ._c(CHECK, VJ.PASS, f"the frame is in the approved {room}",
                     judge=got["judge"])
    if v is False:
        return VJ._c(CHECK, VJ.FAIL, f"a different room from the approved {room}: "
                                     f"{str(got['reading'].get('differences') or '')[:200]}",
                     code=CHECK, judge=got["judge"])
    return VJ._c(CHECK, VJ.UNKNOWN, "the judge could not tell whether it is the same room",
                 judge=got["judge"])
