"""F-226 Canonical Model Naturalism: locked identity, natural variation, no copy-paste (W4-C08).

"The canonical Brambleloop model must remain identity- and morphology-locked while still
looking like a real person photographed on different days. Permit natural variation in pose,
expression, hair and setting; reject copy-paste sameness, over-smoothed skin and artificial
glamour that makes the model look synthetic."

What already existed and is reused, not rebuilt:
* identity and morphology lock: `candidate_gates` `identity` / `body_proportions` checks (two
  blind judges plus the biometric floor, `visual.identity_gate`);
* over-smoothed skin and artificial glamour: `visual.photoreal` (`skin_looks_real`,
  `processing_is_restrained`), carried into each candidate's `realism` check.

What was missing is the sequence-level property: two frames of Laura that are the same
photograph. `check_sequence(frames)` adds it, deterministically:
* `COPY_PASTE_SAMENESS` -- identical bytes, or a perceptual difference hash (dHash, 64 bits)
  within `MAX_COPY_DISTANCE` bits of another frame: the same picture re-used, re-encoded or
  lightly re-toned is not "photographed on a different day";
* `NO_NATURAL_VARIATION` -- three or more frames whose declared pose, expression, hair and
  setting are all identical;
* `IDENTITY_NOT_LOCKED` / `SYNTHETIC_LOOK` -- any frame whose identity / realism check failed.
Undeclared variation attributes or unreadable bytes are UNKNOWN, never a pass. Natural
variation (different pose, expression, hair or setting) is never penalised: only sameness is.
Local, deterministic, CA$0; no model is asked.
"""
from __future__ import annotations

import hashlib
import io

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
HASH_BITS = 64
# A re-encode, resize or small tone shift of one photograph stays within a few bits; two
# different photographs of the same person in a different pose land near HASH_BITS / 2.
MAX_COPY_DISTANCE = 6
VARIATION_AXES = ("pose", "expression", "hair", "setting")
MIN_FRAMES_FOR_VARIATION = 3
KIND = "visual.naturalism"


def dhash(data: bytes) -> int | None:
    """64-bit difference hash of an image's bytes; None when the bytes are not an image."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("L").resize((9, 8))
    except Exception:  # noqa: BLE001 - unreadable bytes are UNKNOWN, not an error
        return None
    px = list(img.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
    return bits


def distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _status(v) -> str:
    if isinstance(v, dict):
        v = v.get("status") or v.get("verdict")
    v = str(v or "").upper()
    return {"MATCH": PASS, "DRIFT": FAIL}.get(v, v if v in (PASS, FAIL) else UNKNOWN)


def check_sequence(frames: list[dict]) -> dict:
    """Frames: [{"sha256", "data": bytes|None, "identity", "realism", pose/expression/...}]."""
    findings: list[dict] = []
    unknown: list[str] = []
    if not frames:
        return {"status": UNKNOWN, "findings": [], "unknown": ["no frames"], "frames": 0}
    hashes: dict[int, int] = {}
    for i, f in enumerate(frames):
        if _status(f.get("identity")) == FAIL:
            findings.append({"code": "IDENTITY_NOT_LOCKED", "frames": [i],
                             "why": "identity or morphology drifted on this frame"})
        elif _status(f.get("identity")) == UNKNOWN:
            unknown.append(f"frame {i}: identity not verified")
        if _status(f.get("realism")) == FAIL:
            findings.append({"code": "SYNTHETIC_LOOK", "frames": [i],
                             "why": "realism failed (over-smoothed skin / artificial glamour "
                                    "are realism checks)"})
        data = f.get("data")
        h = dhash(data) if data else None
        if h is None:
            unknown.append(f"frame {i}: bytes unreadable, sameness not measured")
        else:
            hashes[i] = h
    seen_sha: dict[str, int] = {}
    for i, f in enumerate(frames):
        sha = f.get("sha256") or (hashlib.sha256(f["data"]).hexdigest() if f.get("data")
                                  else None)
        if sha and sha in seen_sha:
            findings.append({"code": "COPY_PASTE_SAMENESS", "frames": [seen_sha[sha], i],
                             "distance": 0, "why": "the same image bytes appear twice"})
            hashes.pop(i, None)
        elif sha:
            seen_sha[sha] = i
    idx = sorted(hashes)
    for a_pos, a in enumerate(idx):
        for b in idx[a_pos + 1:]:
            d = distance(hashes[a], hashes[b])
            if d <= MAX_COPY_DISTANCE:
                findings.append({"code": "COPY_PASTE_SAMENESS", "frames": [a, b],
                                 "distance": d,
                                 "why": (f"frames {a} and {b} differ by {d}/{HASH_BITS} "
                                         f"perceptual bits: one photograph, not two days")})
    declared = [f for f in frames if all(f.get(ax) for ax in VARIATION_AXES)]
    if len(frames) >= MIN_FRAMES_FOR_VARIATION:
        if len(declared) < len(frames):
            unknown.append("pose/expression/hair/setting not declared on every frame")
        elif len({tuple(str(f[ax]) for ax in VARIATION_AXES) for f in declared}) == 1:
            findings.append({"code": "NO_NATURAL_VARIATION",
                             "frames": list(range(len(frames))),
                             "why": "every frame has the same pose, expression, hair and "
                                    "setting"})
    status = FAIL if findings else (UNKNOWN if unknown else PASS)
    return {"status": status, "findings": findings, "unknown": unknown,
            "frames": len(frames), "max_copy_distance": MAX_COPY_DISTANCE,
            "permitted_variation": list(VARIATION_AXES)}


def frames_from_candidates(rows: list[dict], *, db=None, store=None) -> list[dict]:
    """Laura frames of one gallery from `image_production._best`-shaped rows."""
    from ..core.artifacts import ArtifactStore

    store = store or ArtifactStore()
    out = []
    for r in rows:
        if not r.get("laura_present") or not r.get("sha256"):
            continue
        try:
            data = store.get(r["sha256"], db=db)
        except Exception:  # noqa: BLE001 - missing bytes are UNKNOWN
            data = None
        failed, unknown = r.get("failed") or {}, set(r.get("unknown") or [])
        out.append({"sha256": r["sha256"], "data": data,
                    "identity": (FAIL if "identity" in failed or "body_proportions" in failed
                                 else UNKNOWN if "identity" in unknown else PASS),
                    "realism": (FAIL if "realism" in failed
                                else UNKNOWN if "realism" in unknown else PASS)})
    return out


def sameness_only(rows: list[dict], *, db=None, store=None) -> dict:
    """The copy-paste part alone, for the gallery consistency gate: the identity and realism
    parts are already their own per-frame checks and are not double-counted there."""
    frames = frames_from_candidates(rows, db=db, store=store)
    if len(frames) < 2:
        return {"status": PASS, "findings": [], "frames": len(frames)}
    full = check_sequence([{"sha256": f["sha256"], "data": f["data"]} for f in frames])
    same = [f for f in full["findings"] if f["code"] == "COPY_PASTE_SAMENESS"]
    return {"status": FAIL if same else PASS, "findings": same, "frames": len(frames)}
