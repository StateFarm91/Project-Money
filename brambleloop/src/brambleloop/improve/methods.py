"""F-707: method versions change only through the versioned, testable, reversible path.

F-707 (Evidence-Backed Self-Improvement): "Agents may improve prompts, models, tools,
workflows, product selection, patterns, Visual methods, Etsy/SEO, marketing, CX, finance,
reliability and strategy only through versioned, testable, reversible changes with
post-promotion monitoring."

Prompts, models, tools and policies already change only that way (`improve.league`,
`improve.cells`, `improve.upgrades`). The methods did not: a Visual method version, the SEO
strategy version, the blind-review method, the certificate document version are constants in
code, bumped by hand, and nothing compared the running constant with a promoted change.
A hand-bumped `METHOD_VERSION` was an unversioned self-improvement that looked versioned.

This module puts each of those constants under the loop:

* `METHODS` names every hand-maintained method version, the department cell it moves and the
  risk surface it touches (so `improve.tiers` grades it; the gate policy is gate tier and so
  owner-gated). The running value is read from the source file, never imported.
* `propose_change()` is the only sanctioned way to change one: an `improve.cells` proposal with
  the from/to versions, a rollback to the running version, failure memory and governance --
  and, given `max_days`, a bounded experiment (`improve.bounded`). A promoted change on a
  non-trial cell metric is watched by `improve.monitor` like any other: post-promotion
  monitoring is the existing monitor, not a second one.
* `audit()` runs every `improve.sandbox` pass. The first sight of a method records its running
  version as the baseline. Afterwards a running version that differs from the last recorded
  one is *backed* when a PROMOTED improvement changed this method to exactly that version, and
  otherwise is an **unversioned change**: an open incident naming the method, the versions and
  the remedy, resolved automatically once a promoted change backs the running version.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import cells

ACTION = "improve.method_version"
SIGNATURE = "improve-method-unversioned"
KIND = "method_version"


@dataclass(frozen=True)
class Method:
    key: str
    path: str            # source file, relative to the brambleloop package (or absolute)
    attr: str
    cell: str
    touches: tuple[str, ...]
    what: str

    def source(self) -> Path:
        p = Path(self.path)
        return p if p.is_absolute() else Path(__file__).resolve().parents[1] / p


METHODS: dict[str, Method] = {m.key: m for m in (
    Method("visual.owned_photography", "publish/owned_photography.py", "METHOD_VERSION",
           "creative_assets", ("code",), "owned-photography render method (Visual)"),
    Method("visual.model_photography", "publish/model_photography.py", "METHOD_VERSION",
           "creative_assets", ("code",), "on-model photography method (Visual)"),
    Method("visual.listing_sequence", "visual/rnd/sequence.py", "POLICY_VERSION",
           "creative_assets", ("code",), "listing image sequence policy (Visual)"),
    Method("visual.image_benchmark", "gateway/image_bench.py", "METHOD_VERSION",
           "creative_assets", ("code",), "image-provider benchmark method (Visual)"),
    Method("creative.blind_review", "creative/blind_review.py", "METHOD_VERSION",
           "product_creativity", ("code",), "blind concept review (product selection)"),
    Method("seo.strategy", "seo/strategy.py", "STRATEGY_VERSION", "seo_search", ("code",),
           "SEO strategy (Etsy/SEO, strategy)"),
    Method("growth.free_asset", "growth/free_assets.py", "VERSION", "growth", ("code",),
           "free lead asset content (marketing)"),
    Method("intel.acceptance", "intel/acceptance.py", "METHOD_VERSION", "market_radar",
           ("code",), "benchmark acceptance method (research)"),
    Method("patterns.certificate", "gates/certificate.py", "DOC_VERSION", "pattern_engineering",
           ("code",), "pattern certificate document (patterns)"),
    Method("gates.policy", "gates/policy.py", "POLICY_VERSION", "quality", ("policy",),
           "release gate policy (gate tier: owner decision)"),
)}


class MethodRefused(ValueError):
    """A method change outside the versioned path."""


def running(method: Method) -> str | None:
    """The constant as written in the source file (literal assignments only)."""
    try:
        tree = ast.parse(method.source().read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign) else
                   [node.target] if isinstance(node, ast.AnnAssign) else [])
        for t in targets:
            if isinstance(t, ast.Name) and t.id == method.attr and node.value is not None:
                try:
                    return str(ast.literal_eval(node.value))
                except ValueError:
                    return None
    return None


def propose_change(db, key: str, *, to_version: str, hypothesis: str, expected_effect: str,
                   proposed_by: str, max_days: int | None = None,
                   evidence_ids: tuple[str, ...] = (), premise: str = "") -> int:
    """Open the improvement that may change this method's version (F-707)."""
    from ..core.models import Improvement

    m = METHODS.get(key)
    if m is None:
        raise MethodRefused(f"{key!r} is not a registered method: {sorted(METHODS)}")
    current = running(m)
    if current is None:
        raise MethodRefused(f"{m.path}:{m.attr} is unreadable; nothing to version against")
    to = str(to_version).strip()
    if not to or to == current:
        raise MethodRefused(f"{key} already runs {current!r}; a change names a new version")
    iid = cells.propose(
        db, cell=m.cell, hypothesis=hypothesis, expected_effect=expected_effect,
        rollback_ref=f"method:{key}:{current}", touches=m.touches, proposed_by=proposed_by,
        method=f"method:{key}:{to}", evidence_ids=evidence_ids, premise=premise,
        scope=({"max_days": int(max_days)} if max_days else None))
    with db.session() as s:
        row = s.get(Improvement, iid)
        row.evidence = {**(row.evidence or {}),
                        "method_change": {"kind": KIND, "method": key, "from": current,
                                          "to": to, "path": m.path, "attr": m.attr}}
    return iid


def _recorded(db) -> dict[str, dict]:
    """The last recorded version of each method. Kept in `operating_readings`, which
    `ops.retention` never prunes: a baseline the audit horizon forgot would be re-taken from
    whatever runs then, and a hand bump made in the meantime would become the baseline."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    out: dict[str, dict] = {}
    with db.session() as s:
        for a in s.scalars(select(OperatingReading).where(OperatingReading.kind == ACTION)
                           .order_by(OperatingReading.id)):
            d = dict(a.payload or {})
            out[d.get("method")] = d
    return out


def _record(db, detail: dict) -> None:
    import uuid

    from ..core.models import OperatingReading

    with db.session() as s:
        s.add(OperatingReading(kind=ACTION, period_key=uuid.uuid4().hex[:20], payload=detail))


def _backing(db, key: str, version: str) -> int | None:
    from sqlalchemy import select

    from ..core.models import Improvement

    with db.session() as s:
        for r in s.scalars(select(Improvement).where(Improvement.state == cells.PROMOTED)
                           .order_by(Improvement.id.desc())):
            mc = (r.evidence or {}).get("method_change") or {}
            if mc.get("method") == key and mc.get("to") == version:
                return r.id
    return None


def audit(db, *, now: datetime | None = None) -> dict:
    """Compare every method's running version with the versioned path (F-707)."""
    from sqlalchemy import select

    from ..core.models import Incident

    now = now or datetime.now(timezone.utc)
    recorded = _recorded(db)
    items, unversioned, resolved = [], [], []
    for key, m in METHODS.items():
        value = running(m)
        last = recorded.get(key)
        backed = _backing(db, key, value) if value is not None else None
        sig = f"{SIGNATURE}:{key}"[:120]
        entry = {"method": key, "running": value, "cell": m.cell}
        if value is None:
            entry["state"] = "unreadable"
        elif last is None:
            _record(db, {"method": key, "version": value,
                         "basis": "baseline at registration"})
            entry["state"] = "baseline"
        elif last.get("version") == value:
            entry["state"] = "backed" if (backed or last.get("basis") != "unbacked") else \
                "unversioned"
        else:
            basis = f"improvement:{backed}" if backed else "unbacked"
            _record(db, {"method": key, "version": value, "from": last.get("version"),
                         "basis": basis})
            entry["state"] = "backed" if backed else "unversioned"
            entry["from"] = last.get("version")
        with db.session() as s:
            open_inc = s.scalar(select(Incident).where(Incident.signature == sig,
                                                       Incident.resolved.is_(False)))
            if entry["state"] == "unversioned" and open_inc is None:
                s.add(Incident(
                    severity="P2", signature=sig, halts_publication=False,
                    summary=(f"{m.path}:{m.attr} changed to {value!r} without a promoted "
                             f"improvement (F-707). Revert it, or open the change with "
                             f"improve.methods.propose_change so it is tested, reversible "
                             f"and monitored"),
                    detail={"owner": "orchestrator", "method": key, "running": value,
                            "from": entry.get("from") or (last or {}).get("version")}))
            elif entry["state"] == "backed" and backed and open_inc is not None:
                open_inc.resolved = True
                resolved.append(key)
        if entry["state"] == "unversioned":
            unversioned.append(key)
        items.append(entry)
    return {"at": now.isoformat(), "methods": items, "unversioned": unversioned,
            "resolved": resolved}
