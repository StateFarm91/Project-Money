"""A8 P0-CULTURE-TO-IDEATION: a rising culture signal opens a research task for ideation.

Before this, `culture.sweep` turned a signal into learning notes and lessons only (wiring #6,
P0_WIRING_50937469.md s5): no rising topic ever became a concept. This is the bridge, and
nothing else. A rising, non-sensitive, measurable signal whose topic names a pod the studio
already merchandises (`intel.pods.route`) becomes one coverage gap for that pod
(`benchmark_key` CULTURE_KEY, `arena` "culture:<signal>"), and the gap goes to A4(a)'s own
research-to-concept chain (`radar.ideation.open_briefs` -> `research.investigate` ->
`radar.concept_intake` -> `radar.score` -> `cir.draft`). That chain, not this module, decides
whether a concept is proposed, and it proposes only from recorded market observations, with
its own originality and children's checks, bounded by its MAX_IN_FLIGHT.

What it never does:

* route a sensitive topic, a topic with fewer than two readings, or a falling or flat one;
* put a culture topic's words, or any protected token, into a concept: the gap names only the
  pod, so the concept comes from the pod's recorded market, and the signal is evidence;
* invent a pod: a topic `pods.route` cannot place is recorded once, by name, and skipped;
* re-open: one gap per signal (the coverage unique key), and A4(a) gives a gap one brief.

Deterministic, CA$0, no model call, no network. Runs as `culture.ideate` (daily).
"""
from __future__ import annotations

from datetime import date, timedelta
import hashlib

CULTURE_KEY = "culture_radar"
ARENA_PREFIX = "culture:"
OPENED = "culture.ideation_gap"
UNPLACED = "culture.ideation_unplaced"
SKIPPED = "culture.ideation_skipped"
# A trend without recent, comparable dated reference readings is unknown.
MAX_REFERENCE_AGE_DAYS = 30


def _topic(signal: str) -> str:
    return " ".join(str(signal or "").replace("_", " ").replace("-", " ").split())


def _reference_momentum(db, signal: str, *, today: date) -> dict | None:
    """Compare distinct dates from one sourced reference series, never mixed scales."""
    from sqlalchemy import select
    from ..core.models import CultureObservation

    with db.session() as session:
        rows = list(session.scalars(select(CultureObservation).where(
            CultureObservation.signal_key == signal,
            CultureObservation.channel == "reference").order_by(CultureObservation.id)))
    grouped = {}
    for row in rows:
        try:
            day = date.fromisoformat(row.observed_on)
            value = float(row.interest)
        except (TypeError, ValueError):
            continue
        source = str(row.source or "").strip()
        if not source or not (today - timedelta(days=MAX_REFERENCE_AGE_DAYS) <= day <= today):
            continue
        if not 0.0 <= value <= 1.0:
            continue
        grouped.setdefault(source, {})[day] = (row.id, value)
    choices = []
    for source, days in grouped.items():
        dates = sorted(days)
        if len(dates) >= 2:
            last, previous = dates[-1], dates[-2]
            choices.append((last, days[last][0], source, previous, days))
    if not choices:
        return None
    last, _, _source, previous, days = max(choices)
    latest, prior = days[last][1], days[previous][1]
    return {"direction": ("rising" if latest > prior else "falling" if latest < prior else "flat"),
            "latest": latest, "peak": max(v for _, v in days.values()),
            "observations": len(days)}


def candidates(db, *, limit: int = 20, today: date | None = None) -> tuple[list[dict], list[dict]]:
    """(rising signals with their pod, skipped with why), from the radar's own findings."""
    from sqlalchemy import select
    from ..core.models import CultureSignal
    from ..intel import pods
    from . import classify, radar

    today = today or date.today()
    found = radar.findings(db, limit=limit)        # initial bounded signal list
    out, skipped = [], []
    for f in found["findings"]:
        signal = f["signal"]
        moment = _reference_momentum(db, signal, today=today)
        if f.get("sensitive") or classify.sensitive(signal):
            skipped.append({"signal": signal, "why": "sensitive: never routed anywhere"})
            continue
        # A reference-feed observation is not a rights declaration. Only a
        # filed, sourced signal can assert its token set; protected or unknown
        # sets remain held until the original-concept chain checks them end-to-end.
        with db.session() as session:
            filed = session.scalar(select(CultureSignal).where(CultureSignal.key == signal))
            declared = (filed is not None and isinstance(filed.sources, list)
                        and any(isinstance(src, str) and src.strip() for src in filed.sources)
                        and isinstance(filed.protected_tokens, list)
                        and filed.state != radar.EXITED and not classify.sensitive(filed.topic))
            protected = bool(filed.protected_tokens) if declared else True
        if not declared or protected:
            skipped.append({"signal": signal, "why": "rights hold: token-safe original concept not verified"})
            continue
        if moment is None:
            skipped.append({"signal": signal, "why": "unknown: no recent comparable reference series"})
            continue
        if moment.get("direction") != "rising":
            skipped.append({"signal": signal,
                            "why": f"{moment.get('direction') or 'unknown'}, not rising"})
            continue
        pod = pods.route(_topic(signal))
        if not pod or pod == pods.UNCLASSIFIED:
            skipped.append({"signal": signal, "why": "unplaced: no pod the studio merchandises",
                            "unplaced": True})
            continue
        out.append({"signal": signal, "pod": pod, "momentum": {
            k: moment.get(k) for k in ("direction", "latest", "peak", "observations")}})
    return out, skipped


def _arena(signal: str) -> str:
    """Fit the database field without equating different long signal keys."""
    full = f"{ARENA_PREFIX}{signal}"
    if len(full) <= 80:
        return full
    suffix = hashlib.sha256(signal.encode("utf-8")).hexdigest()[:32]
    return f"{full[:47]}-{suffix}"


def _gap_for(db, signal: str, pod: str, momentum: dict) -> tuple[int, str]:
    """The signal's coverage gap: created once with its evidence, never re-written (A4(a)
    keeps its ideation record in the same evidence)."""
    from sqlalchemy import select

    from ..core.models import CoverageGap
    from ..intel import coverage

    arena = _arena(signal)
    with db.session() as s:
        # Preserve an older truncated gap only when its recorded full signal
        # matches. An ambiguous prefix must never inherit another signal's work.
        legacy = f"{ARENA_PREFIX}{signal}"[:80]
        for candidate in dict.fromkeys((arena, legacy)):
            row = s.scalar(select(CoverageGap).where(CoverageGap.benchmark_key == CULTURE_KEY,
                                                     CoverageGap.arena == candidate))
            if row is not None and (row.evidence or {}).get("culture_signal") == signal:
                return row.id, candidate
            if row is not None and candidate == arena:
                raise ValueError("culture signal arena identity conflict")
    gid = coverage.upsert(db, benchmark_key=CULTURE_KEY, arena=arena, pod=pod,
                          evidence={"culture_signal": signal, "momentum": momentum,
                                    "source": "culture.radar.findings"})
    return gid, arena


def _already(db, action: str, artifact: str) -> bool:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        return s.scalar(select(AuditLog.id).where(AuditLog.action == action,
                                                  AuditLog.artifact == artifact)
                        .limit(1)) is not None


def run(ctx, *, today: date | None = None, limit: int = 20) -> dict:
    """Open an ideation brief (through A4(a)) for every rising, placeable culture signal."""
    from ..radar import ideation

    today = today or date.today()
    found, skipped = candidates(ctx.db, limit=limit, today=today)
    gaps = []
    for c in found:
        artifact = f"culture_signal:{c['signal']}"
        gid, arena = _gap_for(ctx.db, c["signal"], c["pod"], c["momentum"])
        if not _already(ctx.db, OPENED, artifact):
            ctx.audit(OPENED, artifact=artifact,
                      detail={"gap": gid, "pod": c["pod"], "momentum": c["momentum"]})
        gaps.append({"gap": gid, "pod": c["pod"],
                     "arena": arena})
    for sk in skipped:
        if sk.get("unplaced"):
            artifact = f"culture_signal:{sk['signal']}"
            if not _already(ctx.db, UNPLACED, artifact):
                ctx.audit(UNPLACED, artifact=artifact, detail={"why": sk["why"]})
    briefs = ideation.open_briefs(ctx, gaps, today=today) if gaps else {
        "opened": [], "already": [], "waiting": [], "in_flight": [], "completed": []}
    return {"rising": [c["signal"] for c in found], "gaps": [g["gap"] for g in gaps],
            "opened": briefs["opened"], "already": briefs["already"],
            "waiting": briefs["waiting"], "skipped": skipped[:20],
            "work_done": len(briefs["opened"])}
