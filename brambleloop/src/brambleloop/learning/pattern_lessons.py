"""The pattern learning loop: engineering defects become lessons the next design reads (ENG-LEARN).

**What it learns from.** The engineering chain already records every outcome as a finished
job. The jobs are `cir.draft` (refused by a construction rule), `cir.compile` (compiled, or
not, with the compiler's findings) and `gate.certify` (granted, or blocked with the
certificate's blocking findings). A certificate's findings cover the twin, reverse, Product
Truth, size truth, originality, policy and the written deliverable. Each finished job holds
the full CIR it judged, so `harvest` reads the design parameters from the very payload that
was judged. Nothing is reconstructed.

`harvest` records one observation per job, idempotently by job id:
- the construction family (the CIR's construction) and the category;
- the binned design parameters;
- every defect code, with the stage that owns it.

**The metric.** A design (`slug@version`) is *first-pass* when it meets both conditions:
- its first compile passed;
- its first certification was granted with no revision round.

`first_pass_by_family` reports that rate per family over rolling windows. A window with
fewer than `stats.TREND_MIN_N` designs is UNKNOWN, and so is a trend that is not
statistically supported. A flat line is reported as flat, never as improvement.

**Lessons.** Within one family, a parameter region (one parameter in one bin) is tested
against the rest of the family on first-pass rate. The test is a one-sided Fisher exact test,
since engineering samples are small, Bonferroni-corrected over the comparisons in that
family.
- A region that fails significantly more is an "avoid" lesson. It is published on the bus as
  `engineering_risk`.
- A region that passes significantly more is a "prefer" lesson. It is published as
  `construction_preference`.

**Where the lessons are read.** Both subjects route to Market Radar and Pattern Engineering.
- `radar.score` already reads Market Radar lessons as a bounded score nudge, and the
  pattern_engineering "favours" lessons as a draft-order heuristic (`consume.matching`). So a
  known-failing region ranks lower and a proven one is drafted sooner. Each such decision is
  recorded with `bus.acted_on`, which is what this module reports as "lessons applied".
- `cir.draft` calls `advise` and records which regions the new CIR falls in. This is advice,
  and never a refusal. Deterministic validation decides whether a design certifies; a lesson
  never weakens or replaces a gate.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

from . import stats
from .store import DerivedLesson, PatternObservation, ensure_tables

PATTERN_MIN_N = 6            # designs per side for a region lesson
PATTERN_ALPHA = 0.01
WINDOW_DAYS = 14
WINDOWS = 6

# Which stage owns a defect code. Read by substring, most specific first; anything else is the
# certificate's own (`certify`), and is still recorded.
CODE_SOURCE: tuple[tuple[str, str], ...] = (
    ("REVERSE", "reverse"), ("ROUNDTRIP", "reverse"),
    ("TWIN", "twin"), ("PLAUSIB", "twin"), ("GEOMETRY", "twin"), ("ASSEMBLY", "twin"),
    ("TOPOLOGY", "twin"), ("SEAM", "twin"),
    ("SIZE", "size_truth"), ("GAUGE", "size_truth"), ("GRADING", "size_truth"),
    ("DIMENSION", "size_truth"), ("FINISHED", "size_truth"),
    ("NAME_", "product_truth"), ("SHAPE", "product_truth"), ("TECHNIQUE", "product_truth"),
    ("PRODUCT_TYPE", "product_truth"), ("CLAIM", "product_truth"), ("MOTIF", "product_truth"),
    ("PDF", "deliverable"), ("DOC", "deliverable"), ("WRITE", "deliverable"),
    ("TEXT", "deliverable"), ("CHART", "deliverable"), ("ABBREV", "deliverable"),
    ("COUNT", "compiler"), ("UNDERRUN", "compiler"), ("OVERRUN", "compiler"),
    ("STITCH", "compiler"), ("HOLD", "compiler"), ("ROW", "compiler"),
)
_CODE = re.compile(r"^\s*(?:ERROR|WARNING|WARN)?\s*([A-Z][A-Z0-9_]{2,})")

BINS: dict[str, tuple[tuple[float, str], ...]] = {
    "rows": ((20, "<20"), (50, "20-49"), (100, "50-99"), (math.inf, "100+")),
    "foundation": ((20, "<20"), (60, "20-59"), (120, "60-119"), (math.inf, "120+")),
    "colours": ((2, "1"), (3, "2"), (4, "3"), (math.inf, "4+")),
    "components": ((2, "1"), (4, "2-3"), (math.inf, "4+")),
}
REGION_PARAMS = ("rows", "foundation", "colours", "components", "yarn_weight", "risk_class",
                 "assembly", "stitch_count")


def source_of(code: str, stage: str) -> str:
    if stage == "draft":
        return "construction"
    for needle, src in CODE_SOURCE:
        if needle in code:
            return src
    return "compiler" if stage == "compile" else "certify"


def code_of(text: str) -> str:
    m = _CODE.match(str(text or ""))
    return m.group(1) if m else "UNCLASSIFIED"


def _bin(name: str, value) -> str:
    if value is None:
        return "unstated"
    for upper, label in BINS[name]:
        if value < upper:
            return label
    return "unstated"   # pragma: no cover


def _stitches(ops) -> set[str]:
    out: set[str] = set()
    for o in ops or []:
        if isinstance(o, dict) and "stitch" in o:
            out.add(str(o["stitch"]))
        elif isinstance(o, dict):
            out |= _stitches(o.get("ops"))
    return out


def params_of(cir: dict) -> dict:
    """Binned design parameters of a CIR payload. Read-only, deterministic."""
    comps = [c for c in (cir or {}).get("components") or [] if isinstance(c, dict)]
    rows = sum(len(c.get("rows") or []) for c in comps)
    foundation = max([int(c.get("foundation") or 0) for c in comps] or [0])
    stitches: set[str] = set()
    for c in comps:
        for r in c.get("rows") or []:
            stitches |= _stitches((r or {}).get("ops"))
    gauge = (cir or {}).get("gauge") or {}
    mats = (cir or {}).get("materials") or []
    weight = (gauge.get("yarn_weight") or (mats[0].get("weight") if mats and
              isinstance(mats[0], dict) else None) or "unstated")
    return {
        "rows": _bin("rows", rows), "foundation": _bin("foundation", foundation),
        "colours": _bin("colours", len((cir or {}).get("colors") or {}) or None),
        "components": _bin("components", len(comps) or None),
        "yarn_weight": str(weight)[:20], "risk_class": str((cir or {}).get("risk_class") or "A"),
        "assembly": "seamed" if (cir or {}).get("assembly") else "no_assembly",
        "stitch_count": "1" if len(stitches) <= 1 else "2-3" if len(stitches) <= 3 else "4+",
        "stitches": sorted(stitches)[:20],
        "raw": {"rows": rows, "foundation": foundation, "components": len(comps)},
    }


def family_of_cir(cir: dict, drafted: dict | None = None) -> str:
    """The construction family: the draft route's family (vessel, tote, panel_pair, a
    creative form...) when the `cir.drafted` record names one, else the CIR's construction."""
    slug = str((cir or {}).get("slug") or "")
    fam = (drafted or {}).get(slug)
    if fam:
        return str(fam)[:40]
    c = (cir or {}).get("construction")
    return str(c or "unknown")[:40]


def drafted_families(db) -> dict[str, str]:
    """slug -> construction family, from the newest `cir.drafted` audit row per slug."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    out: dict[str, str] = {}
    with db.session() as s:
        for art, detail in s.execute(select(AuditLog.artifact, AuditLog.detail).where(
                AuditLog.action == "cir.drafted").order_by(AuditLog.id)):
            d = detail if isinstance(detail, dict) else {}
            fam = d.get("form") or d.get("construction")
            if art and fam:
                out[str(art).split("@", 1)[0]] = str(fam)
    return out


def category_of(db, slug: str) -> str:
    try:
        from ..runtime.pipeline import _seed_for

        seed = _seed_for(slug, db)
        if seed is not None and seed.category:
            return str(seed.category)[:40]
    except Exception:  # noqa: BLE001
        pass
    from .image_lessons import family_of

    return family_of(slug)


def _aware(v):
    if v is not None and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


# ---- harvest -----------------------------------------------------------------------------

def _observation(job, category_for, drafted: dict | None = None) -> dict | None:
    out = job.outputs if isinstance(job.outputs, dict) else None
    inputs = job.inputs if isinstance(job.inputs, dict) else {}
    if out is None:
        return None
    if job.job_type == "cir.compile":
        cir = inputs.get("cir") if isinstance(inputs.get("cir"), dict) else None
        if cir is None or "compiled" not in out:
            return None
        passed = bool(out["compiled"])
        codes = [] if passed else [code_of(e) for e in out.get("errors") or []]
        stage = "compile"
        revision = int(inputs.get("revision") or 0)
    elif job.job_type == "gate.certify":
        cir = inputs.get("cir") if isinstance(inputs.get("cir"), dict) else None
        # A halt, an older-than-newest refusal, a duplicate or a version conflict says
        # nothing about the design; only a certificate's own verdict is an outcome.
        if (cir is None or "granted" not in out or out.get("duplicate")
                or out.get("halted_by_incident") or out.get("refused")
                or out.get("superseded") or out.get("older_than_newest")):
            return None
        passed = bool(out["granted"])
        codes = [] if passed else [code_of(r) for r in out.get("reasons") or []]
        stage = "certify"
        revision = 0
    elif job.job_type == "cir.draft":
        if out.get("drafted") is not False or out.get("gate") not in ("construction", "engine"):
            return None
        cir = {"construction": out.get("construction") or "refused"}
        passed = False
        codes = [str(out.get("hold") or out.get("gate") or "REFUSED")[:60].upper()]
        stage = "draft"
        revision = 0
    else:
        return None
    slug = str(cir.get("slug") or inputs.get("slug") or "")[:80]
    return {"source_key": f"job:{job.id}", "at": _aware(job.finished_at or job.created_at),
            "slug": slug, "version": str(cir.get("version") or "")[:20],
            "fingerprint": str(inputs.get("fingerprint") or "")[:80], "stage": stage,
            "passed": passed, "family": family_of_cir(cir, drafted),
            "category": category_for(slug) if slug else "unknown",
            "params": params_of(cir) if stage != "draft" else {},
            "codes": [{"code": c, "source": source_of(c, stage)} for c in codes],
            "revision": revision}


def harvest(db, *, limit: int = 20000, category_for=None) -> dict:
    """One observation per finished engineering job not yet observed. Idempotent."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    ensure_tables(db)
    category_for = category_for or (lambda slug: category_of(db, slug))
    cache: dict[str, str] = {}

    def cat(slug):
        if slug not in cache:
            cache[slug] = category_for(slug)
        return cache[slug]

    made = 0
    with db.session() as s:
        seen = set(s.scalars(select(PatternObservation.source_key)))
        jobs = list(s.scalars(select(Job).where(
            Job.job_type.in_(("cir.compile", "gate.certify", "cir.draft")),
            Job.status == JobStatus.DONE).order_by(Job.id).limit(limit)))
        drafted = drafted_families(db)
        rows = [o for o in (_observation(j, cat, drafted) for j in jobs
                            if f"job:{j.id}" not in seen) if o]
        for o in rows:
            s.add(PatternObservation(**{**o, "at": o["at"] or datetime.now(timezone.utc)}))
            made += 1
    return {"observed": made, "work_done": made}


def record(db, *, stage: str, cir: dict, passed: bool, codes: list[str], source_key: str,
           category: str = "", revision: int = 0, at: datetime | None = None,
           family: str = "") -> bool:
    """Record one outcome directly (deliverable QA and tests use this). Idempotent by key."""
    from sqlalchemy import select

    ensure_tables(db)
    with db.session() as s:
        if s.scalar(select(PatternObservation.id).where(
                PatternObservation.source_key == source_key)) is not None:
            return False
        s.add(PatternObservation(
            source_key=source_key[:120], at=at or datetime.now(timezone.utc),
            slug=str(cir.get("slug") or "")[:80], version=str(cir.get("version") or "")[:20],
            stage=stage, passed=bool(passed), family=family or family_of_cir(cir),
            category=category or "unknown", params=params_of(cir),
            codes=[{"code": c, "source": source_of(c, stage)} for c in codes],
            revision=int(revision)))
    return True


# ---- the metric --------------------------------------------------------------------------

def _rows(db) -> list[PatternObservation]:
    from sqlalchemy import select

    ensure_tables(db)
    with db.session() as s:
        rows = list(s.scalars(select(PatternObservation).order_by(PatternObservation.at,
                                                                  PatternObservation.id)))
        s.expunge_all()
    return rows


def designs(db) -> list[dict]:
    """Each design (slug@version) with its first-pass verdict, or pending."""
    by: dict[str, dict] = {}
    for o in _rows(db):
        if o.stage == "draft" or not o.slug:
            continue
        d = by.setdefault(f"{o.slug}@{o.version}", {
            "design": f"{o.slug}@{o.version}", "slug": o.slug, "family": o.family,
            "category": o.category, "params": o.params, "first_at": _aware(o.at),
            "compile": None, "certify": None, "revised": False, "codes": []})
        if o.revision > 0:
            d["revised"] = True
        if o.stage == "compile" and d["compile"] is None:
            d["compile"] = o.passed
        if o.stage == "certify" and d["certify"] is None:
            d["certify"] = o.passed
        d["codes"] += [c["code"] for c in o.codes or []]
    out = []
    for d in by.values():
        if d["compile"] is False or d["revised"] or d["certify"] is False:
            d["first_pass"] = False
        elif d["compile"] and d["certify"]:
            d["first_pass"] = True
        else:
            d["first_pass"] = None            # still in the chain: not counted either way
        out.append(d)
    return out


def first_pass_by_family(db, *, now: datetime | None = None, window_days: int = WINDOW_DAYS,
                         windows: int = WINDOWS) -> dict:
    """First-pass certification rate per family over rolling windows, with an honest trend."""
    now = now or datetime.now(timezone.utc)
    ds = [d for d in designs(db) if d["first_pass"] is not None]
    fams = sorted({d["family"] for d in ds}) + ["ALL"]
    out = {}
    for fam in fams:
        mine = ds if fam == "ALL" else [d for d in ds if d["family"] == fam]
        series = []
        for w in range(windows - 1, -1, -1):
            hi = now - timedelta(days=w * window_days)
            lo = hi - timedelta(days=window_days)
            ins = [d for d in mine if lo < d["first_at"] <= hi]
            series.append({"from": lo.date().isoformat(), "to": hi.date().isoformat(),
                           **stats.rate(sum(1 for d in ins if d["first_pass"]), len(ins))})
        out[fam] = {"series": series, "trend": trend(series),
                    "all_time": stats.rate(sum(1 for d in mine if d["first_pass"]), len(mine))}
    return {"metric": "first_pass_certification_rate", "window_days": window_days,
            "families": out}


def trend(series: list[dict]) -> dict:
    """Earliest vs latest MEASURED window. UNKNOWN unless both exist; 'improving' or
    'worsening' only when the difference is significant (one-sided p < 0.05)."""
    m = [w for w in series if w.get("status") == "MEASURED"]
    if len(m) < 2:
        return {"status": stats.UNKNOWN,
                "why": f"{len(m)} measured window(s); a trend needs two"}
    a, b = m[0], m[-1]
    up = stats.two_proportion(a["k"], a["n"], b["k"], b["n"])
    down = stats.two_proportion(b["k"], b["n"], a["k"], a["n"])
    if up["p"] < 0.05:
        verdict = "improving"
    elif down["p"] < 0.05:
        verdict = "worsening"
    else:
        verdict = "no_significant_change"
    return {"status": "MEASURED", "verdict": verdict, "before": [a["k"], a["n"]],
            "after": [b["k"], b["n"]], "p_improving": up["p"], "p_worsening": down["p"]}


# ---- lessons -----------------------------------------------------------------------------

def _p(v: float) -> str:
    return "<1e-6" if v < 1e-6 else f"{v:.2g}"


def fisher_greater(k_a: int, n_a: int, k_b: int, n_b: int) -> float:
    """One-sided Fisher exact p that group A's success share exceeds B's."""
    n, k = n_a + n_b, k_a + k_b
    if n_a == 0 or n_b == 0:
        return 1.0
    denom = math.comb(n, k)
    return round(sum(math.comb(n_a, x) * math.comb(n_b, k - x)
                     for x in range(k_a, min(n_a, k) + 1) if 0 <= k - x <= n_b) / denom, 6)


def derive_lessons(db, *, now: datetime | None = None, publish: bool = True) -> dict:
    from sqlalchemy import select

    now = now or datetime.now(timezone.utc)
    ds = [d for d in designs(db) if d["first_pass"] is not None]
    found: dict[str, dict] = {}
    for fam in sorted({d["family"] for d in ds}):
        mine = [d for d in ds if d["family"] == fam]
        tests = []
        for p in REGION_PARAMS:
            for v in sorted({str((d["params"] or {}).get(p, "unstated")) for d in mine}):
                if v == "unstated":
                    continue
                a = [d for d in mine if str((d["params"] or {}).get(p)) == v]
                b = [d for d in mine if str((d["params"] or {}).get(p)) != v]
                if len(a) >= PATTERN_MIN_N and len(b) >= PATTERN_MIN_N:
                    tests.append((p, v, a, b))
        if not tests:
            continue
        alpha = PATTERN_ALPHA / len(tests)
        for p, v, a, b in tests:
            ka = sum(1 for d in a if d["first_pass"])
            kb = sum(1 for d in b if d["first_pass"])
            better = fisher_greater(ka, len(a), kb, len(b))
            worse = fisher_greater(len(a) - ka, len(a), len(b) - kb, len(b))
            for direction, pv in ((1, better), (-1, worse)):
                if pv >= alpha:
                    continue
                codes: dict[str, int] = {}
                for d in a:
                    for c in d["codes"]:
                        codes[c] = codes.get(c, 0) + 1
                top = sorted(codes.items(), key=lambda x: -x[1])[:3]
                cats = sorted({d["category"] for d in a})[:4]
                names = sorted({d["slug"].replace("-", " ") for d in a})[:4]
                fam_w = fam.replace("_", " ")
                if direction < 0:
                    statement = (
                        f"{fam_w} designs with {p.replace('_', ' ')} {v} certify first time "
                        f"{ka}/{len(a)} versus {kb}/{len(b)} for other {fam_w} designs "
                        f"(Fisher p={_p(pv)}); avoid this region for "
                        f"{', '.join(c.replace('_', ' ') for c in cats)}"
                        + (f"; recurring defects {', '.join(c for c, _ in top)}" if top else "")
                        + f"; seen on {', '.join(names)}.")
                else:
                    statement = (
                        f"{fam_w} designs with {p.replace('_', ' ')} {v} certify first time "
                        f"{ka}/{len(a)} versus {kb}/{len(b)} for other {fam_w} designs "
                        f"(Fisher p={_p(pv)}); prefer this proven region for "
                        f"{', '.join(c.replace('_', ' ') for c in cats)}; proven on "
                        f"{', '.join(names)}.")
                key = f"pattern:{fam}:{p}:{v}:{'+' if direction > 0 else '-'}"
                found[key] = {"scope": fam, "direction": direction, "statement": statement,
                              "evidence": {"family": fam, "param": p, "value": v,
                                           "with": [ka, len(a)], "without": [kb, len(b)],
                                           "p": pv, "alpha": round(alpha, 8),
                                           "tests_in_family": len(tests),
                                           "categories": cats, "codes": dict(top)}}
    made = updated = deactivated = 0
    with db.session() as s:
        existing = {r.key: r for r in s.scalars(select(DerivedLesson).where(
            DerivedLesson.loop == "pattern"))}
        for key, f in found.items():
            row = existing.get(key)
            if row is None:
                s.add(DerivedLesson(loop="pattern", key=key, at=now, scope=f["scope"],
                                    direction=f["direction"], statement=f["statement"],
                                    evidence=f["evidence"], active=True))
                made += 1
            else:
                if not row.active or row.evidence != f["evidence"]:
                    updated += 1
                row.active, row.statement, row.evidence = True, f["statement"], f["evidence"]
        for key, row in existing.items():
            if key not in found and row.active:
                row.active = False
                deactivated += 1
    published = _publish(db) if publish else 0
    return {"lessons": len(found), "new": made, "updated": updated, "deactivated": deactivated,
            "published": published, "work_done": made + updated + deactivated}


def _publish(db) -> int:
    from sqlalchemy import select

    from ..improve import bus

    n = 0
    with db.session() as s:
        pending = [(r.id, r.statement, r.key, r.direction) for r in s.scalars(
            select(DerivedLesson).where(DerivedLesson.loop == "pattern",
                                        DerivedLesson.active == True,  # noqa: E712
                                        DerivedLesson.bus_lesson_id.is_(None)))]
    for rid, statement, key, direction in pending:
        subject = "construction_preference" if direction > 0 else "engineering_risk"
        try:
            lid = bus.publish(db, origin_cell="quality", subject=subject, statement=statement,
                              evidence_ref=key[:200], confidence="measured")
        except bus.LessonRefused:
            continue
        with db.session() as s:
            s.get(DerivedLesson, rid).bus_lesson_id = lid
        n += 1
    return n


def advise(db, *, cir: dict, family: str = "") -> dict:
    """Which measured regions a new CIR falls in, at draft time. Advice; never a refusal."""
    from sqlalchemy import select

    ensure_tables(db)
    fam = family or family_of_cir(cir, drafted_families(db))
    params = params_of(cir)
    with db.session() as s:
        rows = [(r.key, r.direction, dict(r.evidence), r.bus_lesson_id) for r in s.scalars(
            select(DerivedLesson).where(DerivedLesson.loop == "pattern",
                                        DerivedLesson.scope == fam,
                                        DerivedLesson.active == True))]  # noqa: E712
    hits = [{"key": k, "direction": "prefer" if d > 0 else "avoid", "param": e["param"],
             "value": e["value"], "evidence": [e["with"], e["without"]], "p": e["p"],
             "lesson_id": lid}
            for k, d, e, lid in rows if str(params.get(e["param"])) == str(e["value"])]
    return {"family": fam, "params": {k: v for k, v in params.items() if k != "raw"},
            "avoid": [h for h in hits if h["direction"] == "avoid"],
            "prefer": [h for h in hits if h["direction"] == "prefer"],
            "measured_regions": len(rows)}


def lessons_applied(db) -> dict:
    """How many of this loop's bus lessons a department has acted on (bus.acted_on)."""
    from sqlalchemy import select

    from ..core.models import Lesson

    ensure_tables(db)
    with db.session() as s:
        ids = {r.bus_lesson_id: r.loop for r in s.scalars(select(DerivedLesson))
               if r.bus_lesson_id}
        acted: dict[str, dict] = {}
        for les in s.scalars(select(Lesson).where(Lesson.id.in_(list(ids) or [-1]))):
            loop = ids[les.id]
            a = acted.setdefault(loop, {"published": 0, "acted_on": 0, "by": {}})
            a["published"] += 1
            if les.acted_on_by:
                a["acted_on"] += 1
                for c in les.acted_on_by:
                    cell = c.get("cell") if isinstance(c, dict) else str(c)
                    a["by"][cell] = a["by"].get(cell, 0) + 1
    return acted


def cycle(db, *, now: datetime | None = None) -> dict:
    h = harvest(db)
    d = derive_lessons(db, now=now)
    return {"harvest": h, "lessons": d, "work_done": h["work_done"] + d["work_done"]}
