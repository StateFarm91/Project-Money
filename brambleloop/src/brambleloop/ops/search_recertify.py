"""GALLERY-START (2026-11-22): re-certify search profiles refused only on an attribute gap a
deployed rule now decides.

Production at 06:55Z: every Launch-0 release on Etsy's Patterns & Blueprints node (6343) held a
search certificate REFUSED on `attributes`, because that node's "Self-published" property had no
rule and read UNDECIDED. `certified_payload` therefore raised, the listing package carried a
non-image blocker, and `sale_admission` refused all 14 FLUX gallery runs, so no gallery, frame
or certified listing could ever be made. `commerce.category` now decides the property; but a
certificate is only computed inside `listing.seo`, which nothing re-runs for a release whose
chain has finished.

Once per deployed commit, this enqueues `listing.seo` for the newest search profile of each
product whose stored certificate failed `attributes` and nothing outside {attributes, hero}
(hero is completed later by the listing-set gates). It uses the inputs of that release's last
completed `listing.seo` and the chain's own rebuild-token key, exactly as the taxonomy-drift
re-certification does (`integrations.taxonomy_drift.after_refresh`). The re-run recomputes the
certificate with today's rules: a property still undecided stays a gap, so nothing is waved
through; it only stops a decided fact from being judged by yesterday's code. No spend, no
model, no Etsy call. Owner authority: D-OWNER-APPROVE-ALL-3 (re-certification re-runs the
release chain, which still ends at every publication gate).
"""
from __future__ import annotations

ELIGIBLE_FAILED = frozenset({"attributes", "hero"})
CAP = 40


def candidates(session) -> list[dict]:
    """Newest search profile per product whose certificate failed `attributes` and nothing
    outside {attributes, hero}."""
    from ..integrations.taxonomy_drift import _newest_profiles

    out = []
    for row in _newest_profiles(session):
        cert = row.certificate or {}
        failed = {str(f) for f in (cert.get("failed") or [])}
        if row.verdict == "REFUSED" and "attributes" in failed and failed <= ELIGIBLE_FAILED:
            out.append({"slug": row.product_slug, "version": row.version})
    return out[:CAP]


def run(db, enqueue, *, commit: str) -> dict:
    """Enqueue one `listing.seo` re-certification per candidate for this commit.

    `enqueue(agent, job_type, inputs, idempotency_key=...)` returns the job or raises a
    duplicate; a duplicate (an earlier boot of the same commit) is counted, not an error."""
    from ..integrations.taxonomy_drift import _last_seo_inputs
    from ..runtime.release import chain_key

    token = f"recert-{(commit or 'dev')[:12]}"
    enqueued, skipped, duplicates = [], [], 0
    with db.session() as s:
        cands = candidates(s)
        planned = [(c, _last_seo_inputs(s, c["slug"], c["version"])) for c in cands]
    for c, inputs in planned:
        if inputs is None:
            skipped.append({**c, "why": "no completed listing.seo to re-run from"})
            continue
        key = chain_key("seo", c["slug"], c["version"], inputs.get("release", ""), token)
        try:
            enqueue("listing", "listing.seo", {**inputs, "rebuild": token},
                    idempotency_key=key)
            enqueued.append(f"{c['slug']}@{c['version']}")
        except Exception as exc:  # noqa: BLE001 - one release never stops the rest
            if type(exc).__name__ == "DuplicateJob":
                duplicates += 1
            else:
                skipped.append({**c, "why": f"{type(exc).__name__}"})
    return {"token": token, "candidates": len(cands), "enqueued": enqueued,
            "duplicates": duplicates, "skipped": skipped[:20]}
