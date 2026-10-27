"""F-694: finance, policy and customer readings travel on the lesson bus.

The lesson bus routes by subject, carries provenance (`evidence_ref`) and tracks who acted.
Readings produced outside the improvement miner -- a month's spend refusals, a platform policy
page that materially changed, customers asking the same question about one product -- stayed in
their own modules. `publish_all(db)` turns each into a lesson on the existing bus:

* **finance** -- this month's ceiling refusals (`spend_report.refusals`) -> subject `cost`,
  from the `finance` cell, evidence `spend.refusals:<month>:<count>`;
* **policy** -- every unreviewed material change of a platform policy source
  (`platform_policy.unreviewed_changes`) -> subject `platform_policy`, from `quality`,
  evidence `policy_snapshot:<id>`;
* **customer** -- a product with at least `REPEAT_QUESTIONS` support cases in 30 days ->
  subject `instruction_clarity`, from `customer_experience`, evidence
  `support_cases:<slug>:<newest id>`.

The bus is idempotent on evidence + subject, so re-running publishes nothing new until the
reading changes. Nothing here acts on a lesson; the routed cells do.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

REPEAT_QUESTIONS = 3


def _finance(db, now) -> list[int]:
    from ..finance import spend_report
    from . import bus

    r = spend_report.refusals(db, now=now)
    if not r["count"]:
        return []
    which = ", ".join(f"{k} {v}" for k, v in r["by_ceiling"].items())
    return [bus.publish(db, origin_cell="finance", subject="cost", confidence="measured",
                        statement=(f"spending ceilings refused {r['count']} call(s) in "
                                   f"{r['month'][:7]} ({which}); work sized to the ceiling "
                                   f"is being cut off before it finishes"),
                        evidence_ref=f"spend.refusals:{r['month']}:{r['count']}")]


def _policy(db) -> list[int]:
    from ..gates import platform_policy
    from . import bus

    out = []
    for c in platform_policy.unreviewed_changes(db):
        out.append(bus.publish(
            db, origin_cell="quality", subject="platform_policy", confidence="observed",
            statement=(f"the {c['source']} policy page changed materially (version "
                       f"{c['version']}) and is unreviewed; affected workflows: "
                       f"{', '.join(c['affects']) or 'see source'}"),
            evidence_ref=f"policy_snapshot:{c['snapshot_id']}"))
    return out


def _customer(db, now) -> list[int]:
    from sqlalchemy import func, select

    from ..core.models import SupportCase
    from . import bus

    with db.session() as s:
        rows = s.execute(select(SupportCase.product_slug, func.count(), func.max(SupportCase.id))
                         .where(SupportCase.at >= now - timedelta(days=30),
                                SupportCase.product_slug.is_not(None))
                         .group_by(SupportCase.product_slug)).all()
    out = []
    for slug, n, newest in rows:
        if n >= REPEAT_QUESTIONS:
            # F-690: the recurring confusion is also a task for the pattern team.
            from ..autonomy import cross_team

            cross_team.create(db, from_dept="customer_experience", to_dept="product_catalogue",
                              request=(f"review the instructions of {slug}: {n} customers "
                                       f"asked about it in 30 days"),
                              evidence_ref=f"support_cases:{slug}:{newest}")
            out.append(bus.publish(
                db, origin_cell="customer_experience", subject="instruction_clarity",
                confidence="measured",
                statement=(f"{n} customers asked about {slug} in 30 days; the pattern's "
                           f"instructions are not answering what buyers need"),
                evidence_ref=f"support_cases:{slug}:{newest}"))
    return out


def publish_all(db, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    out = {}
    for name, fn in (("finance", lambda: _finance(db, now)), ("policy", lambda: _policy(db)),
                     ("customer", lambda: _customer(db, now))):
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001 - one reading's failure is named, not fatal
            out[name] = {"state": "UNKNOWN", "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return out
