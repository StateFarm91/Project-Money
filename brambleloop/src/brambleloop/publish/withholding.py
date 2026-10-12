"""One durable release-eligibility record per stored release (C-67 / C-69, Codex M10).

Four things withhold a release, and until now each was remembered somewhere different: the
teardown QA (#163) wrote one string onto the stored certificate, the owner's veto (#228) was
audited at certification and read live at publish, the competitive standard (#220) and the
binding teardown requirements (#153-#160) were computed at publish and kept nowhere. So a
rebuild could draft a vetoed product's listing, and clearing the teardown QA's string -- the
only field -- would have cleared whatever else had been written into it.

This is the one record. It lives on the stored release (`PatternVersion.certificate[
"withholding"]`), keyed by reason kind, and three rules hold:

- **Every kind is written and cleared on its own.** `record(kind=..., reason=None)` clears
  that kind and no other; reconciling the live standards touches only the kinds they decide.
- **The build stages read the record's summary.** `certificate["withheld"]` is derived from
  the record -- the kinds that mean *no content is built* (the teardown QA and the owner's
  veto) -- so `listing.draft`, `chain.rebuild` and the rebuild sweep refuse on it exactly as
  before, and now on every reason that belongs there.
- **Publish reads every kind.** `release_gates.for_publish` reconciles the standards it
  computes into the record and refuses on the record's other reasons too, so a teardown-QA
  withhold refuses a hand-enqueued publish that never went through `launch.plan`.
"""
from __future__ import annotations

from datetime import datetime, timezone

RECORD = "withholding"
SUMMARY = "withheld"

TEARDOWN_QA = "teardown_qa"
OWNER_VETO = "owner_veto"
COMPETITIVE_STANDARD = "competitive_standard"
TEARDOWN_REQUIREMENTS = "teardown_requirements"

KINDS: tuple[str, ...] = (TEARDOWN_QA, OWNER_VETO, COMPETITIVE_STANDARD, TEARDOWN_REQUIREMENTS)
# Reasons that mean no content is built for the release at all (#163, #228). The standards
# withhold *publication*: a listing may be drafted and rebuilt while the bar is not yet met.
BUILD_BLOCKING: tuple[str, ...] = (TEARDOWN_QA, OWNER_VETO)


class WithholdingRefused(ValueError):
    """A reason kind this record does not know."""


def _release(s, slug: str, version: str):
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    product = s.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        return None
    return s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                 PatternVersion.version == version))


def _stored(cert: dict) -> dict:
    """The record as the certificate holds it, with a pre-record mark read as what it was.

    Before the record existed the teardown QA (#163) wrote its one string straight into
    `certificate["withheld"]`. A deployed release still carrying that bare mark and no record
    is withheld for that reason: it is read as the teardown QA's kind, never dropped as
    unknown, so migrating to the record can never un-withhold a release.
    """
    reasons = dict(cert.get(RECORD) or {})
    if not reasons and cert.get(SUMMARY):
        reasons[TEARDOWN_QA] = {"reason": str(cert[SUMMARY])[:400], "at": None,
                                "migrated_from": SUMMARY}
    return reasons


def _summary(reasons: dict) -> str | None:
    parts = [str(reasons[k]["reason"]) for k in BUILD_BLOCKING if reasons.get(k)]
    return "; ".join(parts) if parts else None


def _view(slug: str, version: str, reasons: dict) -> dict:
    return {"slug": slug, "version": version, "reasons": dict(reasons),
            "withheld": bool(reasons), "blocks_build": any(k in reasons for k in BUILD_BLOCKING),
            "blocks_publish": bool(reasons), "summary": _summary(reasons),
            "publish_reasons": [str(v["reason"]) for _k, v in sorted(reasons.items())]}


def record(db, slug: str, version: str, *, kind: str, reason: str | None) -> dict:
    """Set (a reason) or clear (None) one kind on the release's record; every other kind stays.

    The derived `withheld` summary is rebuilt from the record each time, so a stage that reads
    the summary sees every build-blocking reason and nothing a different kind's clearing took
    away. A release that is not stored gets no record: there is nothing to withhold.
    """
    if kind not in KINDS:
        raise WithholdingRefused(f"{kind!r} is not a withholding reason: {list(KINDS)}")
    with db.session() as s:
        pv = _release(s, slug, version)
        if pv is None:
            return {"slug": slug, "version": version, "recorded": False, "reasons": {},
                    "why": "no stored release to withhold"}
        cert = dict(pv.certificate or {})
        reasons = _stored(cert)
        changed = False
        if reason:
            entry = reasons.get(kind) or {}
            if entry.get("reason") != str(reason):
                reasons[kind] = {"reason": str(reason)[:400],
                                 "at": datetime.now(timezone.utc).isoformat()}
                changed = True
        elif kind in reasons:
            reasons.pop(kind)
            cleared = dict(cert.get("withholding_cleared") or {})
            cleared[kind] = datetime.now(timezone.utc).isoformat()
            cert["withholding_cleared"] = cleared
            changed = True
        if changed or (RECORD in cert) != bool(reasons) or cert.get(SUMMARY) != _summary(reasons):
            if reasons:
                cert[RECORD] = reasons
            else:
                cert.pop(RECORD, None)
            summary = _summary(reasons)
            if summary:
                cert[SUMMARY] = summary
            else:
                cert.pop(SUMMARY, None)
            pv.certificate = cert
        return {**_view(slug, version, reasons), "recorded": True, "changed": changed}


def reasons(db, slug: str, version: str) -> dict:
    """The record as stored, without re-evaluating anything."""
    with db.session() as s:
        pv = _release(s, slug, version)
        stored = _stored(dict(pv.certificate or {})) if pv is not None else {}
    return _view(slug, version, stored)


def reconcile(db, slug: str, version: str, *, standards: dict) -> dict:
    """Write what the publish standards decided into the record, kind by kind.

    `standards` is `release_gates.standards_gate`'s verdict. Each kind it decides is set or
    cleared from that verdict alone; the teardown QA's kind is not its to decide and is left
    exactly as it stands.
    """
    veto = standards.get("veto") or {}
    record(db, slug, version, kind=OWNER_VETO,
           reason=(f"owner veto (#228): {veto.get('why')}" if veto.get("vetoed") else None))
    below = [c for c in (standards.get("competitive") or []) if c.get("verdict") != "met"]
    record(db, slug, version, kind=COMPETITIVE_STANDARD,
           reason=(("competitive standard (#220): "
                    + "; ".join(f"{c['standard']} bar {c['bar']}, ours "
                                f"{c['ours'] if c.get('ours') is not None else 'unmeasured'}"
                                for c in below)) if below else None))
    teardown = standards.get("teardown") or {}
    failing = sorted(set(teardown.get("unmet") or []) | set(teardown.get("unmeasured") or []))
    record(db, slug, version, kind=TEARDOWN_REQUIREMENTS,
           reason=(("binding teardown requirements (#153-#160): "
                    + ", ".join(failing)) if teardown.get("blocks") else None))
    return reasons(db, slug, version)


def current(db, slug: str, version: str, *, stage: str = "build") -> dict:
    """The record, with the owner's ruling re-read before it is trusted.

    The veto is the one reason that can change without any stage running (the owner rules
    again), so every reader re-evaluates it from the rulings and writes the result back. The
    other kinds are reconciled where they are computed: the publish gates and the QA.
    """
    from ..intel.mission_runtime import active_veto

    with db.session() as s:
        if _release(s, slug, version) is None:
            return _view(slug, version, {})
    veto = active_veto(db, slug)
    record(db, slug, version, kind=OWNER_VETO,
           reason=(f"owner veto (#228): {veto.get('why')}" if veto.get("vetoed") else None))
    out = reasons(db, slug, version)
    out["stage"] = stage
    return out


def state() -> dict:
    return {"record": f"PatternVersion.certificate[{RECORD!r}]", "kinds": list(KINDS),
            "build_blocking": list(BUILD_BLOCKING),
            "summary": f"certificate[{SUMMARY!r}] is derived from the build-blocking kinds",
            "readers": ["listing.draft", "chain.rebuild", "chain.rebuild sweep",
                        "release_gates.for_publish (store.publish)"]}
