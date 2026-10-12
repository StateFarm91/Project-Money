"""F-278: the hero thumbnail tournament needs at least two truthful hero candidates per product.

`creative.grid_tournament` ranked one hero per product, so it could say how the shop's hero
compared with the benchmark, but never which of two of our own first images to lead with.
That second question is the tournament F-278 names. It also handed the judges each hero's
`image_ref`. For a disclosed render that is a content address (`sha256:...`), which the
vision provider cannot open (`gateway.anthropic._image_block` refuses anything that is
neither a URL nor a file). So every judge call on a Launch-0 hero failed, and the grid could
never be judged.

This module supplies the candidates, every one a verified, truthful first image:
* the product's usable hero on file. A disclosed render's bytes are read from the artifact
  store by their hash and written to a local file the judge can be shown; a photograph that
  cleared its floors is used as it is;
* for a vessel, the disclosed ANGLE view: the finished piece seen from above, verified on
  its bytes by `render_verification`;
* for a multi-piece round hero (a coaster set), the same pieces at another spacing
  (`hero_gap_ratio`), verified on its bytes. The spacing moves whole pieces only; it never
  changes a stitch.
Nothing is generated, and nothing is judged here. A candidate that does not verify is left
out with its reason. A product with fewer than two candidates is reported as such by the
tournament, never padded.
"""
from __future__ import annotations

import hashlib
import os

MIN_CANDIDATES = 2
ALT_GAP_RATIO = 0.06       # the Visual R&D challenger spacing (coasters), inside LAYOUT_PARAMS


def _write(work_dir: str, name: str, data: bytes) -> str:
    path = os.path.join(work_dir, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def _readable(ref: str) -> bool:
    return ref.startswith(("http://", "https://")) or os.path.isfile(ref)


def candidates(db, slug: str, *, work_dir: str) -> dict:
    """Every verified hero candidate for `slug`: {candidates: [...], refused: {label: why}}."""
    from ..core.artifacts import ArtifactStore
    from ..publish import listing_asset

    out: list[dict] = []
    refused: dict[str, str] = {}
    frames = listing_asset.frames_for(db, slug=slug)
    hero = next((f for f in frames if (f.get("role") or "hero") == "hero"), None)
    if hero is not None:
        ref = str(hero.get("image_ref") or hero.get("image") or "")
        sha = str((hero.get("image") or {}).get("sha256") or "") if isinstance(
            hero.get("image"), dict) else ""
        if ref.startswith("sha256:") or (sha and not _readable(ref)):
            sha = sha or ref.split(":", 1)[1]
            try:
                data = ArtifactStore(hero.get("artifact_dir") or None).get(sha, db=db)
                ref = _write(work_dir, f"{slug}-hero.png", data)
            except Exception as exc:  # noqa: BLE001 - an unreadable hero is no candidate
                refused["hero"] = f"the hero's bytes could not be read: {exc}"[:200]
                ref = ""
        if ref and _readable(ref):
            out.append({"slug": slug, "candidate": "hero", "image_ref": ref,
                        "source": hero.get("kind") or "frame", "made": True})
        elif "hero" not in refused:
            refused["hero"] = "the hero on file has no image a judge can be shown"
    else:
        refused["hero"] = "no hero on file"

    if hero is not None and hero.get("kind") == "disclosed_render":
        out.extend(_disclosed_alternatives(slug, hero, work_dir, refused))
    return {"slug": slug, "candidates": out, "refused": refused,
            "enough": len(out) >= MIN_CANDIDATES}


def _disclosed_alternatives(slug: str, hero: dict, work_dir: str, refused: dict) -> list[dict]:
    from . import disclosed_render as DR
    from . import render_verification as RV

    out = []
    try:
        cir = RV.authoritative_cir(slug, (hero.get("disclosed_render") or {}).get("version")
                                   or hero.get("version"))
    except Exception as exc:  # noqa: BLE001
        refused["*"] = f"no authoritative CIR: {exc}"[:200]
        return out
    tries = []
    if len(cir.components) == 1:
        tries.append(("angle", "angle", None))
        if cir.components[0].make > 1:
            tries.append((f"hero_gap_{ALT_GAP_RATIO}", "hero",
                          {"hero_gap_ratio": ALT_GAP_RATIO}))
    for label, view, layout in tries:
        try:
            frame = DR.render(cir, view, layout=layout)
        except DR.RenderRefused as exc:
            refused[label] = f"not drawable: {exc}"[:200]
            continue
        if layout is not None and (frame.manifest.get("layout") or {}).get("objects", 1) < 2:
            refused[label] = "the spacing does not apply to this product's hero"
            continue
        sha = hashlib.sha256(frame.png).hexdigest()
        if sha == (hero.get("image") or {}).get("sha256"):
            refused[label] = "identical to the hero on file"
            continue
        verdict = RV.verify(frame.png, cir=cir, view=view)
        if verdict.get("status") != "PASS":
            refused[label] = (f"does not verify: failed {verdict.get('failed')} "
                              f"unknown {verdict.get('unknown')}")[:200]
            continue
        out.append({"slug": slug, "candidate": label, "made": True, "source": "disclosed_render",
                    "image_ref": _write(work_dir, f"{slug}-{label}.png", frame.png),
                    "sha256": sha, "verified": "PASS"})
    return out


def winner(candidate_scores: dict[str, dict]) -> dict:
    """The best-ranked candidate, when at least two were scored on every judge field."""
    from ..creative.blinded import GRID_JUDGE_FIELDS

    complete = {c: s for c, s in candidate_scores.items()
                if s and all(s.get(f) is not None for f in GRID_JUDGE_FIELDS)}
    if len(candidate_scores) < MIN_CANDIDATES:
        return {"verdict": "insufficient_candidates", "candidates": len(candidate_scores),
                "why": f"{len(candidate_scores)} hero candidate(s); a tournament needs "
                       f"{MIN_CANDIDATES}"}
    if len(complete) < len(candidate_scores):
        return {"verdict": "unjudged", "candidates": len(candidate_scores),
                "why": "not every candidate was scored on every judge field"}
    means = {c: round(sum(s[f] for f in GRID_JUDGE_FIELDS) / len(GRID_JUDGE_FIELDS), 4)
             for c, s in complete.items()}
    best = max(sorted(means), key=lambda c: means[c])
    return {"verdict": "decided", "winner": best, "means": means,
            "candidates": len(candidate_scores),
            "why": f"{best} ranked highest on the blinded panel's mean of "
                   f"{list(GRID_JUDGE_FIELDS)}"}
