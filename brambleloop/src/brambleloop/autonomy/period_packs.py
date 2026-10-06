"""`finance.accounting.period_pack`: the accountant's packs get a runtime caller (closure K15).

F-909 (`finance.accounting.tax_pack`) and F-916 (`finance.accounting.handoff`) were built and
tested but nothing at runtime ever called them. This daily job builds both for the LAST CLOSED
calendar month and keeps the result as one `company_memory` row per period
(`finance.period_pack:<YYYY-MM>`): status, CAD summary, open exceptions, the handoff file
manifest (a SHA-256 per file) and a content fingerprint. The Command Center and Laura read the
row; the owner (or a human accountant) can export the files on demand with
`handoff.export(db, out_dir, spec)`.

Shadow-safe and GREEN: it reads the books, writes one memory row and one timeline event when
the pack's content changed, and nothing else -- no file is written, nothing is filed, remitted
or sent, no money moves (tax_pack: "PREPARED ONLY -- NOT FILED").

Honest work count: `work_done` is 1 only when the pack for the period is new or its content
(journal, trial balance, exceptions, statement lines, tax figures) changed since the last run.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from ..runtime.worker import JobContext, handlers

JOB = "finance.accounting.period_pack"
# Files whose bytes embed the preparation time; excluded from the content fingerprint.
_TIMESTAMPED = ("tax_summary.json",)


def last_closed_month(now: datetime) -> str:
    y, m = now.year, now.month - 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def build(db, *, now: datetime | None = None, spec: str | None = None) -> dict:
    from ..finance.accounting import handoff, tax_pack
    from . import memory

    now = now or datetime.now(timezone.utc)
    spec = spec or last_closed_month(now)
    tp = tax_pack.pack(db, spec, now=now)
    hp = handoff.pack(db, spec, now=now)
    content = {"files": {k: v for k, v in hp["manifest"].items() if k not in _TIMESTAMPED},
               "summary_cad": tp.get("summary_cad"), "periods": tp.get("periods")}
    fp = hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()
                        ).hexdigest()[:32]
    key = f"finance.period_pack:{spec}"
    prev = memory.get(db, key)
    changed = prev is None or (prev.get("body") or {}).get("fingerprint") != fp
    body = {"spec": spec, "status": tp.get("status"), "fingerprint": fp,
            "prepared_at": now.isoformat(), "summary_cad": tp.get("summary_cad"),
            "sales_reading": tp.get("sales_reading"),
            "open_exceptions": len(hp.get("open_exceptions") or []),
            "questions_for_accountant": len(tp.get("questions_for_accountant") or []),
            "manifest": hp["manifest"], "files": sorted(hp["files"]),
            "export": "finance.accounting.handoff.export(db, out_dir, spec) -- owner/accountant"}
    if changed:
        memory.remember(db, key, kind="finance.period_pack", department="finance",
                        subject=f"accountant tax + handoff pack {spec} (prepared, not filed)",
                        state="prepared", body=body,
                        sources=["finance.accounting.tax_pack.pack",
                                 "finance.accounting.handoff.pack",
                                 f"acct_journal_entries:period={spec}"], now=now)
        memory.record_event(db, f"finance.period_pack:{spec}:{fp}", kind="finance.period_pack",
                            department="finance", actor="cfo",
                            summary=(f"Accountant pack {spec} prepared (not filed): "
                                     f"{len(hp['files'])} files, "
                                     f"{body['open_exceptions']} open exception(s)"),
                            refs=[f"company_memory:{key}"], at=now)
    return {"ran": True, "spec": spec, "fingerprint": fp, "changed": changed,
            "work_done": 1 if changed else 0, "files": len(hp["files"]),
            "open_exceptions": body["open_exceptions"], "status": body["status"],
            "filed": False, "files_written": 0}


@handlers.register(JOB)
def handle_period_pack(ctx: JobContext) -> dict:
    out = build(ctx.db)
    ctx.audit(JOB, detail={k: v for k, v in out.items() if k != "fingerprint"})
    return out
