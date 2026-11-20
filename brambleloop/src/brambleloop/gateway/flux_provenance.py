"""ENG-VIS-FLUX: one provenance record per FLUX render, and a completeness check over it.

D-W4-F852-AMEND item 7 requires, for every generated image: the model, the references with their
fingerprints and order, the product version, the prompt version, the receipt and the disclosure.
ENG-VIS-GALLERY's F-852 exception evidence reads this record; it does not re-derive it.

The record is built from what was measured, never from what was asked for:

* references are the sha256s found **inside the exact request body sent** (the conditioning
  receipt, F-212), in order, each marked when it is one of Laura's three canonical originals
  (by fingerprint against `visual.canonical.CURRENT_REFERENCE_HASHES`, ENG-VIS-IDENTITY's
  register; read, never edited here);
* the receipt id is the provider's task id from the submit response;
* the cost is the reserved CA$ estimate the ledger row was written at, plus the provider's own
  credit figure when it reported one;
* the seed is the provider's, when its result reports one. FLUX 3 Image takes no seed
  (`flux_contract`), so `seed_supported` is False and an absent seed is recorded as None with
  that reason -- never filled in.

`missing(record)` names every required field that is absent. A record with anything missing is
incomplete, and incomplete provenance is UNKNOWN for F-852 purposes: it blocks.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from . import flux_contract

RECORD_VERSION = "flux-provenance/1"
DISCLOSURE = "AI-generated image (FLUX 3 Image); not a photograph of a made sample"

REQUIRED = ("record_version", "provider", "model", "endpoint", "contract_version",
            "prompt_version", "prompt_sha256", "references", "reference_order_sha256",
            "request_sha256", "receipt_id", "cost_cad", "cost_basis", "cost_entry_id",
            "output_sha256", "output_px", "output_format", "gallery", "disclosure",
            "generated_at", "seed_supported")


def _laura_hashes() -> dict[str, str]:
    try:
        from ..visual import canonical

        return {sha: frame for frame, sha in canonical.CURRENT_REFERENCE_HASHES.items()}
    except Exception:  # noqa: BLE001 - an unreadable register marks nothing canonical
        return {}


def build(*, provider: str, model: str, prompt: str, prompt_version: str, conditioning: dict,
          provider_receipt: dict, cost_cad: float | None, cost_basis: str,
          cost_entry_id: int | None, output_sha256: str, qc: dict | None, gallery: str,
          request: dict | None = None, product: str = "", reservation_id: int | None = None,
          now: datetime | None = None) -> dict:
    canon = _laura_hashes()
    refs = []
    for row in (conditioning or {}).get("references") or []:
        sha = str(row.get("sha256") or "")
        refs.append({"position": row.get("position"), "sha256": sha,
                     "field": row.get("field"), "transmitted": bool(row.get("transmitted")),
                     "canonical_laura": canon.get(sha)})
    order = "|".join(r["sha256"] for r in refs)
    pr = dict(provider_receipt or {})
    req = dict(request or {})
    return {
        "record_version": RECORD_VERSION, "provider": provider, "model": model,
        "endpoint": flux_contract.ENDPOINT, "contract_version": flux_contract.CONTRACT_VERSION,
        "prompt_version": str(prompt_version or ""),
        "prompt_sha256": hashlib.sha256(str(prompt or "").encode()).hexdigest(),
        "references": refs,
        "reference_order_sha256": hashlib.sha256(order.encode()).hexdigest() if refs else "",
        "references_all_transmitted": bool(refs) and all(r["transmitted"] for r in refs),
        "laura_canonical_positions": [r["position"] for r in refs if r["canonical_laura"]],
        "request_sha256": (conditioning or {}).get("request_sha256") or "",
        "request": {k: req.get(k) for k in ("aspect_ratio", "resolution", "width", "height",
                                             "safety_tolerance", "grounding", "version")
                    if k in req},
        "receipt_id": pr.get("task_id") or pr.get("id") or "",
        "provider_cost_credits": pr.get("cost"),
        "settled_cost_credits": pr.get("settled_cost_credits"),
        "cost_cad": cost_cad, "cost_basis": cost_basis, "cost_entry_id": cost_entry_id,
        "reservation_id": reservation_id,
        "seed_supported": False,
        "seed": pr.get("seed"),
        "seed_note": ("FLUX 3 Image accepts no seed (Flux3ImageInputs); the provider's own seed "
                      "is recorded when its result reports one, otherwise None"),
        "output_sha256": output_sha256,
        "output_px": (qc or {}).get("px"), "output_format": (qc or {}).get("format"),
        "generation_check": {k: (qc or {}).get(k) for k in ("ok", "reasons", "role")},
        "product": product, "gallery": gallery, "disclosure": DISCLOSURE,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
    }


def missing(record: dict | None) -> list[str]:
    """Required fields that are absent or empty. Zero is a value; None and '' are not."""
    rec = dict(record or {})
    out = []
    for key in REQUIRED:
        v = rec.get(key)
        if v is None or v == "" or v == []:
            out.append(key)
    for i, ref in enumerate(rec.get("references") or []):
        if not ref.get("sha256") or ref.get("position") is None:
            out.append(f"references[{i}]")
        elif not ref.get("transmitted"):
            out.append(f"references[{i}].transmitted")
    return out


def complete(record: dict | None) -> bool:
    return not missing(record)
