"""Owner-assisted image intake: an optional launch fallback beside autonomous production.

This module is thin on purpose (owner redirect, 2026-10-19). An owner-made image, such as
one from the FLUX 3 dashboard experiment (`w4/FLUX3_MANUAL_EXPERIMENT.md`), goes through
exactly the binding, checks, gallery assembly and publication gates the autonomous workflow
uses (`visual.candidate_gates.evaluate`, `visual.image_production.readiness`). Intake does
only five things:

1. It stores the original bytes unchanged in the artefact store, keyed by sha256 and kept
   durable.
2. It records provenance kind `ai_generated_owner_submitted`. An owner upload is never a
   photograph: a photograph of a made sample has its own path, `physical_upgrade.intake`.
3. It records the owner's visual approval in its own field (`owner_visual_approval`), which
   no gate reads.
4. It runs the shared evaluation and records the candidate. Missing evidence stays UNKNOWN.
5. It returns the per-image verdict and the listing's gallery-readiness view.

Entry points:

* Command Center: `POST /api/cc/owner-images` (owner session, CSRF, nonce), from the
  "Images" tab.
* CLI fallback:
  `python -m brambleloop.publish.owner_images intake --file IMG --slug S --version V
  --release R --role lifestyle --provider bfl-dashboard --model "FLUX 3 Image" ...`
"""
from __future__ import annotations

import argparse
import json
import re
import sys

MAX_BYTES = 25_000_000
PROVENANCE_KIND = "ai_generated_owner_submitted"
_SHA = re.compile(r"^[0-9a-f]{64}$")


class IntakeRefused(ValueError):
    pass


def parse_references(lines) -> list[dict]:
    """'sha256 [kind]' per line, or [{"sha256", "kind"}]. A missing kind is 'other'."""
    from ..visual.candidate_gates import REFERENCE_KINDS

    out = []
    items = lines.splitlines() if isinstance(lines, str) else list(lines or [])
    for item in items:
        if isinstance(item, dict):
            sha, kind = str(item.get("sha256") or ""), str(item.get("kind") or "other")
        else:
            parts = str(item).split()
            if not parts:
                continue
            sha, kind = parts[0], (parts[1] if len(parts) > 1 else "other")
        sha, kind = sha.strip().lower(), kind.strip().lower()
        if not _SHA.match(sha):
            raise IntakeRefused(f"reference {sha[:20]!r} is not a sha256")
        if kind not in REFERENCE_KINDS:
            raise IntakeRefused(f"reference kind {kind!r} is not one of {REFERENCE_KINDS}")
        out.append({"sha256": sha, "kind": kind})
    return out


def intake(db, *, data: bytes, slug: str, version: str, release: str, role: str,
           prompt: str = "", references=(), provider: str = "", model: str = "",
           cost_usd: float | None = None, laura_present: bool = False,
           outfit_id: str | None = None, owner_visual_approval: bool | None = None,
           submitted_by: str = "owner") -> dict:
    from ..visual import candidate_gates as CG
    from ..visual import image_production as IP
    from ..visual import outfits

    if not isinstance(data, (bytes, bytearray)) or not data:
        raise IntakeRefused("no image bytes")
    if len(data) > MAX_BYTES:
        raise IntakeRefused(f"image is over {MAX_BYTES // 1_000_000} MB")
    if not slug or not version:
        raise IntakeRefused("product slug and version are required")
    data = bytes(data)
    refs = parse_references(references)
    sha = IP.store_bytes(db, data, key=f"owner-image/{slug}@{version}",
                         why="owner-submitted AI image (never a photograph)")
    cost_cad = None
    if cost_usd is not None:
        from ..core import fx

        cost_cad = round(float(cost_usd) / fx.ASSUMED_USD_PER_CAD, 4)
    cand = {"data": data, "sha256": sha, "slug": slug, "version": version,
            "release": release, "role": role, "prompt": prompt, "references": refs,
            "provider": provider, "model": model, "laura_present": bool(laura_present),
            "outfit_id": (outfit_id or "").strip().lower() or None,
            "listing": outfits.listing_of(slug), "provenance_kind": PROVENANCE_KIND,
            "cost_cad": cost_cad,
            "cost_basis": ("owner-reported USD, converted at core.fx.ASSUMED_USD_PER_CAD"
                           if cost_usd is not None else "not reported")}
    verdict = CG.evaluate(db, cand)
    rec = IP.record_candidate(db, cand, verdict, method="owner_submitted",
                              owner_visual_approval=owner_visual_approval,
                              submitted_by=submitted_by)
    listing = verdict["listing"]
    try:
        gallery = IP.readiness(db, listing)
    except Exception as exc:  # noqa: BLE001 - a listing outside Launch-0 has no plan
        gallery = {"listing": listing, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {"candidate": rec, "sha256": sha, "bytes": len(data),
            "provenance_kind": PROVENANCE_KIND, "is_photograph": False,
            "owner_visual_approval": owner_visual_approval,
            "technical_status": verdict["technical_status"],
            "publishable": verdict["publishable"], "checks": verdict["checks"],
            "unknown": verdict["unknown"], "publication": verdict["publication"],
            "laura_gates": verdict.get("laura_gates"), "gallery": gallery,
            "note": ("owner visual approval is recorded separately and never counts as "
                     "technical verification")}


def _cli(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m brambleloop.publish.owner_images")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("intake", help="submit one owner-made AI image")
    i.add_argument("--file", required=True)
    i.add_argument("--slug", required=True)
    i.add_argument("--version", required=True)
    i.add_argument("--release", required=True)
    i.add_argument("--role", required=True)
    i.add_argument("--prompt", default="")
    i.add_argument("--prompt-file")
    i.add_argument("--ref", action="append", default=[], help="'sha256 kind' (repeatable)")
    i.add_argument("--provider", default="")
    i.add_argument("--model", default="")
    i.add_argument("--cost-usd", type=float)
    i.add_argument("--laura", action="store_true")
    i.add_argument("--outfit")
    i.add_argument("--owner-approved-look", action="store_true")
    r = sub.add_parser("readiness", help="gallery readiness for a listing")
    r.add_argument("--listing", required=True)
    a = p.parse_args(argv)
    from ..core.db import Database

    db = Database()
    if a.cmd == "readiness":
        from ..visual.image_production import readiness

        print(json.dumps(readiness(db, a.listing), indent=2, default=str))
        return 0
    prompt = a.prompt
    if a.prompt_file:
        with open(a.prompt_file, encoding="utf-8") as fh:
            prompt = fh.read()
    with open(a.file, "rb") as fh:
        data = fh.read()
    try:
        out = intake(db, data=data, slug=a.slug, version=a.version, release=a.release,
                     role=a.role, prompt=prompt, references=a.ref, provider=a.provider,
                     model=a.model, cost_usd=a.cost_usd, laura_present=a.laura,
                     outfit_id=a.outfit, owner_visual_approval=a.owner_approved_look or None,
                     submitted_by="owner:cli")
    except IntakeRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({k: v for k, v in out.items() if k != "gallery"}, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
