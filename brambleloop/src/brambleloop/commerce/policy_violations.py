"""Every Policy Violations item becomes a severity-ranked incident (F-568).

The census already turns a listing that vanished or changed state into a halting
`policy_violation_suspected:<id>` with a deadline and closure evidence -- an alarm, because
Etsy exposes no violations API and the reason is only on the page. What was missing was the
other half: the owner reads Shop Manager > Policy Violations and records what it says
(`commerce.shop_observations.record(page="policy_violations")`), and each listed item becomes
an incident with everything F-568 names:

- **severity** ranked by what the notice threatens: the account (P0, halts publication), an
  intellectual-property claim (P1, halts, *and* legal escalation), a removed or suppressed
  listing (P1, halts), a warning (P2);
- **source text** exactly as the owner recorded it (truncated, never paraphrased);
- **affected listing / action**;
- **deadline**: the notice's own date when the owner records one, otherwise a two-day review
  deadline stated as ours, not Etsy's;
- **remediation owner** and **owner/legal escalation**: an IP claim or an account notice is
  the owner's (and, for IP, legal review's), a listing-content notice is the listing
  department's under the owner's review;
- **closure proof**: an incident closes only on a later *complete* reading of the page that no
  longer lists the item. A complete empty reading also closes the census's suspected-takedown
  alarms that opened before it -- the closure evidence those alarms already named.

Nothing here contacts Etsy, appeals anything or edits a listing.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

PREFIX = "etsy.policy_violation:"
SUSPECTED = "policy_violation_suspected:"
REVIEW_DAYS = 2

#: kind -> (severity, halts publication, remediation owner, legal escalation)
KINDS: dict[str, tuple[str, bool, str, bool]] = {
    "account_restriction": ("P0", True, "owner", True),
    "suspension": ("P0", True, "owner", True),
    "payment_hold": ("P0", True, "owner", False),
    "ip_claim": ("P1", True, "owner", True),
    "listing_removed": ("P1", True, "listing", False),
    "listing_suppressed": ("P1", True, "listing", False),
    "warning": ("P2", False, "listing", False),
}
UNKNOWN_KIND = ("P1", True, "owner", False)


def _key(item: dict) -> str:
    text = f"{item.get('kind')}|{item.get('listing_id')}|{(item.get('source_text') or '')[:400]}"
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def classify(item: dict) -> dict:
    """Severity, halting, remediation owner and escalation for one recorded item."""
    kind = str(item.get("kind") or "").strip().lower()
    severity, halts, owner, legal = KINDS.get(kind, UNKNOWN_KIND)
    return {"kind": kind or "unclassified", "severity": severity, "halts": halts,
            "remediation_owner": owner, "legal_escalation": legal,
            "classified": kind in KINDS}


def apply_observation(db, *, observation_id: int, observed_at: datetime, complete: bool,
                      items: list, now: datetime | None = None) -> dict:
    """Open or restate one incident per item; close only on a complete reading."""
    from ..ops import incident_lifecycle as lifecycle

    now = now or datetime.now(timezone.utc)
    opened, restated, escalated = [], [], []
    seen: set[str] = set()
    with db.session() as s:
        for raw in items:
            if not isinstance(raw, dict) or not str(raw.get("source_text") or "").strip():
                continue
            item = dict(raw)
            cls = classify(item)
            sig = f"{PREFIX}{_key(item)}"
            seen.add(sig)
            deadline = str(item.get("deadline") or "") or (
                now + timedelta(days=REVIEW_DAYS)).isoformat()
            detail = {"source_text": str(item["source_text"])[:2000],
                      "listing_id": item.get("listing_id"), "action": item.get("action"),
                      "deadline": deadline,
                      "deadline_basis": "the notice" if item.get("deadline") else
                      f"ours: {REVIEW_DAYS}-day review, not an Etsy date",
                      **cls, "observation_id": observation_id,
                      "observed_at": observed_at.isoformat(),
                      "closure_proof": ("a later complete reading of Shop Manager > Policy "
                                        "Violations that no longer lists this item")}
            row, new = lifecycle.open_or_restate(
                s, signature=sig, severity=cls["severity"], halts_publication=cls["halts"],
                summary=(f"Etsy Policy Violations ({cls['kind']}, {cls['severity']}): "
                         f"{str(item['source_text'])[:200]} -- remediation owner "
                         f"{cls['remediation_owner']}, deadline {deadline}"
                         + ("; legal review required" if cls["legal_escalation"] else "")),
                detail=detail)
            (opened if new else restated).append(sig)
            if cls["legal_escalation"] and new:
                escalated.append(sig)
                _escalate(s, sig, cls, item, deadline)
        resolved: list[str] = []
        if complete:
            life = lifecycle.reconcile(
                s, PREFIX, lambda row: row.signature in seen,
                resolution=(f"a complete Policy Violations reading (observation "
                            f"{observation_id}, {observed_at.isoformat()}) no longer lists it"))
            resolved += life["resolved"]
            if not seen:
                def before(row) -> bool:
                    first = str((row.detail or {}).get("first_seen") or "")
                    return bool(first) and first <= observed_at.isoformat()

                life = lifecycle.reconcile(
                    s, SUSPECTED, lambda row: not before(row),
                    resolution=(f"a dated, complete Policy Violations reading (observation "
                                f"{observation_id}, {observed_at.isoformat()}) is empty"))
                resolved += life["resolved"]
    return {"opened": opened, "restated": restated, "resolved": resolved,
            "legal_escalations": escalated}


def _escalate(s, sig: str, cls: dict, item: dict, deadline: str) -> None:
    """One owner action per escalated notice, keyed on the incident."""
    from sqlalchemy import select

    from ..core.models import OwnerAction

    key = f"legal_review:{sig}"
    if s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key)) is not None:
        return
    s.add(OwnerAction(
        requirement_key=key,
        action=(f"Review the Etsy {cls['kind']} notice"
                + (f" on listing {item.get('listing_id')}" if item.get("listing_id") else "")
                + " and decide whether to take legal advice before responding."),
        reason=("An IP claim or account-level notice can end the shop; the response is a "
                "legal decision no software here may make."),
        max_cost_cad=0.0, minutes=20,
        consequence_of_delay=f"Etsy's response window may close; review deadline {deadline}.",
        blocks="publication (the incident halts it)"))


def open_items(db) -> list[dict]:
    """Open violation incidents, most severe first. No customer content is involved."""
    from sqlalchemy import select

    from ..core.models import Incident

    with db.session() as s:
        rows = [i for i in s.scalars(select(Incident).where(
            Incident.signature.like(f"{PREFIX}%"), Incident.resolved == False))  # noqa: E712
            if i.signature.startswith(PREFIX)]
        return sorted(({"signature": r.signature, "severity": r.severity,
                        "halts": r.halts_publication, "summary": r.summary,
                        "deadline": (r.detail or {}).get("deadline"),
                        "remediation_owner": (r.detail or {}).get("remediation_owner")}
                       for r in rows), key=lambda d: d["severity"])


def escalate_overdue(db, *, now: datetime | None = None) -> dict:
    """Daily: an open violation past its deadline is restated OVERDUE with an owner action.

    The deadline is the notice's own date or our two-day review; either way, a violation
    nobody acted on by then is the owner's to see today, not on the next page read.
    """
    from sqlalchemy import select

    from ..core.models import Incident, OwnerAction

    now = now or datetime.now(timezone.utc)
    overdue = []
    with db.session() as s:
        for row in s.scalars(select(Incident).where(
                Incident.signature.like(f"{PREFIX}%"), Incident.resolved == False)):  # noqa: E712
            if not row.signature.startswith(PREFIX):
                continue
            detail = dict(row.detail or {})
            try:
                due = datetime.fromisoformat(str(detail.get("deadline") or ""))
            except ValueError:
                continue
            due = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
            if due > now:
                continue
            overdue.append(row.signature)
            if not detail.get("overdue_since"):
                detail["overdue_since"] = now.isoformat()
                row.detail = detail
                if not row.summary.startswith("OVERDUE"):
                    row.summary = f"OVERDUE since {due.date().isoformat()}: {row.summary}"[:2000]
            key = f"policy_violation_overdue:{row.signature}"
            if s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key)) is None:
                s.add(OwnerAction(
                    requirement_key=key,
                    action=("Resolve or respond to the overdue Etsy Policy Violations item "
                            f"({detail.get('kind')}), then record a fresh complete reading of "
                            "the page."),
                    reason="its deadline has passed with the item still listed",
                    max_cost_cad=0.0, minutes=15,
                    consequence_of_delay="Etsy may escalate to listing removal or account "
                                         "restriction.",
                    blocks="publication while the incident halts it"))
    return {"overdue": overdue}
