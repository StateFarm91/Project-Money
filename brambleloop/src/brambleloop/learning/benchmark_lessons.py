"""Benchmark teardown lessons as structured records, and the hooks they change (LEARN-PROOF).

The P0 condition "real learning" needs proof that a lesson changes a later output. The two
benchmark teardowns (`research/benchmarks/TEARDOWN_HIGHLAND_COW_AMIGURUMI.md` and
`TEARDOWN_MADELINEMAECO_CAPYBARA.md`, section "Lessons for each department") each end in seven
lessons, L1-L7. Until this module they were prose: nothing read them.

**What is stored.** One record per lesson (`LESSONS`, 14 in all), written into the existing
learning store (`learning_derived_lessons`, `loop == "benchmark"`). Each record has:

- `department`: the cell (`improve.cells`) that owns acting on it;
- `lesson_class`: what kind of thing was learned, as a stable identifier
  (`missing_gauge->tension_complaints`, `low_sew_character_amigurumi_demand`, ...);
- `effect`: the decision hook it changes, or None when the lesson is recorded but no hook
  reads it yet (said so in the readback, never counted as applied).

The statements are our own paraphrase of a structural observation. No competitor
instruction, chart, photograph, title or wording is stored: competitor research is demand and
merchandising intelligence only. Ingestion refuses to run if a source teardown no longer
carries the lesson it cites, so a record cannot outlive its evidence silently.

**The hooks.** Each is deterministic and bounded, and none weakens a gate:

- `concept_rank`  (Market Radar, MM-L1): `radar.scan` raises an amigurumi concept that is
  low-sew and/or character-named by +0.02 per trait (cap +0.04).
- `pdf_eye_options_age` (Pattern Engineering MM-L4, QA HC-L5): the premium PDF standard
  additionally requires, for amigurumi, the eye-options panel (embroidered and safety) with
  age guidance.
- `pdf_hook_range_chunky` (Pattern Engineering MM-L3): the standard requires a hook-size
  range for chunky (CYC 5+) or chenille yarn.
- `seo_low_sew_truth` (SEO, MM-L6): a title segment or tag saying "no sew" / "low sew" is
  refused unless the certified CIR's construction really is that (`low_sew`).
- `qa_defect_class` (QA, MM-L7): failure mining tags a defect that reads as a tension or
  missing-gauge complaint with the lesson class `missing_gauge->tension_complaints`.

**Applied is recorded, never inferred.** A hook that changed an output writes an `applied`
row (`learning_lesson_effects`) per lesson, department and subject; every run of a hook writes
an `evaluated` count. Pure hooks (the PDF standard, the SEO validator) have no database: they
note into a process buffer, which the worker flushes after every job (`flush`). The readback
reports applied counts per department, and UNKNOWN (never 0) when the store is unreadable, the
lessons are not ingested, no hook is wired for the department, or its hook has not run.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LOOP = "benchmark"
KEY_PREFIX = "benchmark:"
UNKNOWN = "UNKNOWN"
ROOT = Path(__file__).resolve().parents[3]      # brambleloop/

SOURCES: dict[str, str] = {
    "HC": "research/benchmarks/TEARDOWN_HIGHLAND_COW_AMIGURUMI.md",
    "MM": "research/benchmarks/TEARDOWN_MADELINEMAECO_CAPYBARA.md",
}

# ---- effects -------------------------------------------------------------------------------

CONCEPT_RANK = "concept_rank"
PDF_EYE_OPTIONS = "pdf_eye_options_age"
PDF_HOOK_RANGE = "pdf_hook_range_chunky"
SEO_LOW_SEW = "seo_low_sew_truth"
QA_DEFECT_CLASS = "qa_defect_class"
EFFECTS: tuple[str, ...] = (CONCEPT_RANK, PDF_EYE_OPTIONS, PDF_HOOK_RANGE, SEO_LOW_SEW,
                            QA_DEFECT_CLASS)

MISSING_GAUGE_CLASS = "missing_gauge->tension_complaints"


@dataclass(frozen=True)
class BenchmarkLesson:
    source: str              # HC | MM
    number: int              # L<n> in the teardown
    department: str          # improve.cells key
    lesson_class: str
    effect: str | None
    statement: str

    @property
    def key(self) -> str:
        return f"{self.source}-L{self.number}"


L = BenchmarkLesson
LESSONS: tuple[BenchmarkLesson, ...] = (
    L("HC", 1, "pricing", "effective_price_is_the_signal", None,
      "A bestselling amigurumi animal clears at a low impulse price; price research reads "
      "the effective price, never the strike price, and clear instructions drive reviews."),
    L("HC", 2, "product_creativity", "cosy_farm_animal_cluster", None,
      "Shaggy and cosy farm animals are a proven amigurumi demand cluster; a fur effect is a "
      "differentiator only when our own construction makes it."),
    L("HC", 3, "creative_assets", "component_diagrams_never_fake_photos", None,
      "Per-component progress imagery earns trust; without a sample we draw CIR component "
      "diagrams labelled as diagrams, never presented as photographs."),
    L("HC", 4, "pattern_engineering", "component_grouped_pattern_pages", None,
      "Amigurumi pattern pages group by component, with numbered assembly steps whose "
      "placement cues name round numbers."),
    L("HC", 5, "quality", "age_guidance_every_amigurumi", PDF_EYE_OPTIONS,
      "Every amigurumi release states age guidance and offers an embroidered face where "
      "safety requires it; the benchmark's absence of this is the gap we fill."),
    L("HC", 6, "customer_experience", "deliver_the_pdf_not_a_link", None,
      "Delivered files are the certified PDFs themselves, read back as downloadable and "
      "hash-matched, never a link page."),
    L("HC", 7, "seo_search", "front_load_object_and_true_badges", None,
      "Titles front-load the object and the words crochet pattern PDF; a badge such as "
      "beginner friendly appears only when the certified difficulty supports it."),
    L("MM", 1, "market_radar", "low_sew_character_amigurumi_demand", CONCEPT_RANK,
      "Low-sew amigurumi animals with a lovable character name and a small piece count are "
      "the concepts to rank first; every animal, character and construction is our own."),
    L("MM", 2, "pattern_engineering", "join_as_you_go_capability", None,
      "A join-as-you-go construction, limbs closed flat and crocheted into a named body "
      "round, is a technique class the compiler, twin and reverse must validate."),
    L("MM", 3, "pattern_engineering", "chunky_chenille_needs_hook_range", PDF_HOOK_RANGE,
      "Chunky and chenille yarn is a first-class yarn class: its pattern states a hook-size "
      "range and tension guidance because the fabric is easily worked too loose."),
    L("MM", 4, "pattern_engineering", "eye_options_with_age_guidance", PDF_EYE_OPTIONS,
      "An amigurumi PDF offers an eye-options panel, embroidered versus safety eyes, with "
      "the age guidance each option carries."),
    L("MM", 5, "creative_assets", "hero_in_hand_for_scale", None,
      "The hero shows the finished toy at a scale the buyer can read, matching the PDF "
      "cover, with variants filling the gallery."),
    L("MM", 6, "seo_search", "low_sew_modifier_only_when_true", SEO_LOW_SEW,
      "No sew and low sew are high-intent search modifiers; we use them only when the "
      "certified construction really is no-sew or low-sew."),
    L("MM", 7, "quality", MISSING_GAUGE_CLASS, QA_DEFECT_CLASS,
      "A complaint that stitches are too tight with the stated hook is a missing-gauge "
      "defect; QA records it under the lesson class missing gauge leads to tension "
      "complaints."),
)
del L
BY_KEY: dict[str, BenchmarkLesson] = {x.key: x for x in LESSONS}
DEPARTMENTS: tuple[str, ...] = tuple(sorted({x.department for x in LESSONS}))
# The department each hook's applications are counted under.
EFFECT_DEPARTMENTS: dict[str, tuple[str, ...]] = {
    e: tuple(sorted({x.department for x in LESSONS if x.effect == e})) for e in EFFECTS}


class IngestRefused(ValueError):
    """A lesson's source teardown no longer carries the lesson it cites."""


def _lessons_section(text: str) -> str:
    m = re.search(r"^## \d+\. Lessons for each department.*?$(.*?)(?=^## |\Z)", text,
                  re.S | re.M)
    return m.group(1) if m else ""


# sha256 of each teardown's lessons section when these records were written. The production
# image does not ship `research/` (Dockerfile copies src, release, tests), so there the pinned
# digest is the evidence; in a checkout the file must still match it, and
# `tests/test_learn_proof.py` holds the two together.
SOURCE_SHA256: dict[str, str] = {
    "HC": "87923accb84ba3a49a9cbea7bed881d898511d26c54443d64b70db2e93a6d1d9",
    "MM": "c2b1f72ca0615fa7d9377bd1fc6cb0a00a3af11f67d4bbd93713a4baee74deb5",
}


def source_digests(root: Path | None = None) -> dict[str, str]:
    """sha256 of each source teardown's lessons section, after checking every cited lesson
    is still there and the section is the one these records were written from. A source file
    absent from this deployment falls back to the pinned digest. Raises IngestRefused when a
    present file no longer supports its lessons."""
    root = root or ROOT
    out = {}
    for src, rel in SOURCES.items():
        path = root / rel
        if not path.exists():
            out[src] = SOURCE_SHA256[src]
            continue
        section = _lessons_section(path.read_text(encoding="utf-8"))
        for lesson in (x for x in LESSONS if x.source == src):
            if f"**L{lesson.number}," not in section:
                raise IngestRefused(f"{rel} no longer carries L{lesson.number} under "
                                    f"'Lessons for each department'")
        digest = hashlib.sha256(section.encode("utf-8")).hexdigest()
        if digest != SOURCE_SHA256[src]:
            raise IngestRefused(f"{rel}'s lessons section changed since these records were "
                                f"written; re-read it and update LESSONS and SOURCE_SHA256")
        out[src] = digest
    return out


def ingest(db, *, root: Path | None = None) -> dict:
    """Write (or refresh) the 14 lesson records. Idempotent: the same teardowns are the same
    rows. Returns what was created and updated, and refreshes this process's snapshot."""
    from sqlalchemy import select

    from .store import DerivedLesson, ensure_tables

    ensure_tables(db)
    digests = source_digests(root)
    created, updated = [], []
    with db.session() as s:
        have = {r.key: r for r in s.scalars(select(DerivedLesson)
                                            .where(DerivedLesson.loop == LOOP))}
        for lesson in LESSONS:
            key = KEY_PREFIX + lesson.key
            evidence = {"source": SOURCES[lesson.source], "lesson": f"L{lesson.number}",
                        "department": lesson.department, "lesson_class": lesson.lesson_class,
                        "effect": lesson.effect, "source_sha256": digests[lesson.source]}
            row = have.get(key)
            if row is None:
                s.add(DerivedLesson(loop=LOOP, key=key, scope=lesson.department,
                                    direction=1 if lesson.effect == CONCEPT_RANK else 0,
                                    statement=lesson.statement, evidence=evidence,
                                    active=True))
                created.append(lesson.key)
            elif (row.statement, row.evidence, row.scope) != (lesson.statement, evidence,
                                                               lesson.department):
                row.statement, row.evidence, row.scope = (lesson.statement, evidence,
                                                          lesson.department)
                updated.append(lesson.key)
    refresh(db, force=True)
    return {"lessons": len(LESSONS), "created": created, "updated": updated,
            "work_done": len(created) + len(updated)}


def active(db) -> dict[str, dict]:
    """Active stored benchmark lessons, by lesson key ("MM-L6"), with their record."""
    from sqlalchemy import select

    from .store import DerivedLesson, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        rows = list(s.scalars(select(DerivedLesson).where(DerivedLesson.loop == LOOP,
                                                          DerivedLesson.active.is_(True))))
        out = {}
        for r in rows:
            k = r.key[len(KEY_PREFIX):]
            if k in BY_KEY:
                out[k] = {"department": r.scope, **dict(r.evidence or {})}
        return out


def effects_of(lessons: dict[str, dict]) -> dict[str, tuple[str, ...]]:
    """effect -> the active lesson keys that switch it on."""
    out: dict[str, list[str]] = {}
    for k in sorted(lessons):
        e = BY_KEY[k].effect
        if e:
            out.setdefault(e, []).append(k)
    return {e: tuple(v) for e, v in out.items()}


# ---- the process snapshot pure hooks read --------------------------------------------------

_SNAPSHOT: dict = {"effects": {}, "loaded_at": 0.0, "db": None}
_PENDING: list[dict] = []
_LOCK = threading.Lock()
REFRESH_SECONDS = 300.0


def refresh(db, *, force: bool = False) -> dict[str, tuple[str, ...]]:
    """Reload the active effects from the store (at most every REFRESH_SECONDS per database)."""
    now = time.monotonic()
    with _LOCK:
        fresh = (_SNAPSHOT["db"] == id(db.engine)
                 and now - _SNAPSHOT["loaded_at"] < REFRESH_SECONDS)
    if fresh and not force:
        return dict(_SNAPSHOT["effects"])
    eff = effects_of(active(db))
    with _LOCK:
        _SNAPSHOT.update(effects=eff, loaded_at=now, db=id(db.engine))
    return dict(eff)


def active_effects() -> dict[str, tuple[str, ...]]:
    """The effects this process last loaded. Empty until `refresh` or `ingest` ran."""
    with _LOCK:
        return dict(_SNAPSHOT["effects"])


def reset_snapshot() -> None:
    with _LOCK:
        _SNAPSHOT.update(effects={}, loaded_at=0.0, db=None)
        _PENDING.clear()


def note(effect: str, *, applied: bool, subject: str, lessons=(), detail: dict | None = None,
         ) -> None:
    """A pure hook ran (and, if `applied`, changed its output because of `lessons`)."""
    with _LOCK:
        _PENDING.append({"effect": effect, "applied": applied, "subject": subject[:200],
                         "lessons": tuple(lessons), "detail": dict(detail or {})})


def pending() -> list[dict]:
    with _LOCK:
        return list(_PENDING)


def record(db, effect: str, *, applied: bool, subject: str, lessons=(),
           detail: dict | None = None, evaluations: int = 1) -> int:
    """Write one hook run: an `evaluated` count per department, and an `applied` row per
    lesson and department when the output changed. Returns applied rows written."""
    from sqlalchemy import select

    from .store import LessonEffect, ensure_tables

    ensure_tables(db)
    now = datetime.now(timezone.utc)
    written = 0
    with db.session() as s:
        for dept in EFFECT_DEPARTMENTS.get(effect, ()):
            ek = f"evaluated:{effect}:{dept}"
            row = s.scalar(select(LessonEffect).where(LessonEffect.key == ek))
            if row is None:
                s.add(LessonEffect(key=ek, kind="evaluated", lesson_key="", department=dept,
                                   hook=effect, subject="", count=evaluations,
                                   first_at=now, last_at=now, detail={}))
                s.flush()
            else:
                row.count = int(row.count or 0) + evaluations
                row.last_at = now
        if applied:
            for lk in lessons:
                lesson = BY_KEY.get(lk)
                if lesson is None or lesson.effect != effect:
                    continue
                ak = f"applied:{lk}:{lesson.department}:{subject}"[:300]
                row = s.scalar(select(LessonEffect).where(LessonEffect.key == ak))
                if row is None:
                    s.add(LessonEffect(key=ak, kind="applied", lesson_key=lk,
                                       department=lesson.department, hook=effect,
                                       subject=subject[:200], count=1, first_at=now,
                                       last_at=now, detail=dict(detail or {})))
                    s.flush()
                    written += 1
                else:
                    row.count = int(row.count or 0) + 1
                    row.last_at = now
    return written


def flush(db) -> int:
    """Write the notes pure hooks buffered in this process. Returns notes written."""
    with _LOCK:
        batch = list(_PENDING)
        _PENDING.clear()
    for n in batch:
        try:
            record(db, n["effect"], applied=n["applied"], subject=n["subject"],
                   lessons=n["lessons"], detail=n["detail"])
        except Exception:  # noqa: BLE001 - a lost note under-counts; it never fails a job
            continue
    return len(batch)


# ---- hook (a): concept ranking -------------------------------------------------------------

CONCEPT_STEP = 0.02
CONCEPT_CAP = 0.04
LOW_SEW_TEXT = re.compile(r"\b(?:no|low)[- ]?sew\b|\bjoin[- ]as[- ]you[- ]go\b|"
                          r"\bminimal[- ]sew(?:ing)?\b", re.I)
# "<Name> the <animal>": a capitalised given name, then "the", then a lower or capitalised noun.
CHARACTER_NAME = re.compile(r"\b[A-Z][a-z]{2,}\s+the\s+[A-Za-z][a-z]+")


def concept_traits(seed) -> list[str]:
    """Which MM-L1 traits a radar concept has. Amigurumi only."""
    if (getattr(seed, "category", "") or "").lower() != "amigurumi":
        return []
    text = " ".join(str(getattr(seed, a, "") or "") for a in ("slug", "title", "rationale"))
    traits = []
    if LOW_SEW_TEXT.search(text.replace("-", " ")) or LOW_SEW_TEXT.search(text):
        traits.append("low_sew")
    if CHARACTER_NAME.search(str(getattr(seed, "title", "") or "")):
        traits.append("character_named")
    return traits


def concept_rank_delta(seed, effects: dict[str, tuple[str, ...]]) -> tuple[float, list[str]]:
    if CONCEPT_RANK not in effects:
        return 0.0, []
    traits = concept_traits(seed)
    return min(CONCEPT_CAP, CONCEPT_STEP * len(traits)), traits


def concept_rank_adjustments(db, seeds) -> dict[str, float]:
    """The MM-L1 nudge for each seed, recorded as applied for every seed it moved."""
    effects = refresh(db)
    out: dict[str, float] = {}
    for seed in seeds:
        delta, traits = concept_rank_delta(seed, effects)
        if delta:
            out[seed.slug] = delta
            record(db, CONCEPT_RANK, applied=True, subject=f"concept:{seed.slug}",
                   lessons=effects[CONCEPT_RANK], detail={"traits": traits, "delta": delta},
                   evaluations=0)
    if CONCEPT_RANK in effects:
        record(db, CONCEPT_RANK, applied=False, subject="", evaluations=1)
    return out


# ---- hook (c): SEO low-sew truth -----------------------------------------------------------

SEWN_METHODS = frozenset({"whipstitch", "mattress", "sew"})
LOW_SEW_MAX_SEWN = 1
NO_SEW_CLAIM = re.compile(r"\bno[- ]?sew\b", re.I)
LOW_SEW_CLAIM = re.compile(r"\b(?:low|minimal)[- ]?sew(?:ing)?\b", re.I)


def construction_sewing(cir) -> dict:
    """How much sewing the certified construction asks for: seams by method."""
    seams = list(getattr(cir, "assembly", None) or [])
    sewn = [s for s in seams if getattr(s, "method", None) in SEWN_METHODS]
    return {"seams": len(seams), "sewn": len(sewn),
            "no_sew": not sewn, "low_sew": len(sewn) <= LOW_SEW_MAX_SEWN}


def low_sew_findings(cir, terms: list[str]) -> list[str]:
    """TERM_MISLEADING findings for each no-sew / low-sew claim the construction does not
    support. An unknown construction (no CIR) supports neither."""
    out = []
    sewing = construction_sewing(cir) if cir is not None else None
    for term in terms:
        if NO_SEW_CLAIM.search(term) and not (sewing and sewing["no_sew"]):
            out.append(f"TERM_MISLEADING: {term!r} claims no sew, but the certified "
                       f"construction has {sewing['sewn'] if sewing else 'unknown'} sewn "
                       f"seam(s) (benchmark lesson MM-L6)")
        elif LOW_SEW_CLAIM.search(term) and not (sewing and sewing["low_sew"]):
            out.append(f"TERM_MISLEADING: {term!r} claims low sew, but the certified "
                       f"construction has {sewing['sewn'] if sewing else 'unknown'} sewn "
                       f"seam(s), more than {LOW_SEW_MAX_SEWN} (benchmark lesson MM-L6)")
    return out


def low_sew_modifiers(cir) -> list[str]:
    """The modifiers the certified construction earns, for SEO to use (and only these)."""
    sewing = construction_sewing(cir)
    return (["no sew", "low sew"] if sewing["no_sew"] else
            ["low sew"] if sewing["low_sew"] else [])


def seo_check(cir, slug: str, terms: list[str],
              effects: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    effects = active_effects() if effects is None else effects
    if SEO_LOW_SEW not in effects:
        return []
    claims = [t for t in terms if NO_SEW_CLAIM.search(t) or LOW_SEW_CLAIM.search(t)]
    found = low_sew_findings(cir, claims)
    note(SEO_LOW_SEW, applied=bool(claims), subject=f"listing:{slug}",
         lessons=effects[SEO_LOW_SEW],
         detail={"claims": len(claims), "refused": len(found)})
    return found


# ---- hook (b): PDF standard ----------------------------------------------------------------

def pdf_lessons(effects: dict[str, tuple[str, ...]] | None = None) -> frozenset[str]:
    effects = active_effects() if effects is None else effects
    return frozenset(e for e in (PDF_EYE_OPTIONS, PDF_HOOK_RANGE) if e in effects)


def note_pdf(effects_required: list[str], subject: str, switched_on) -> None:
    """The PDF standard ran with these lesson effects on; `effects_required` are the ones
    whose rule applied to this document (and so changed what it must contain)."""
    eff = active_effects()
    for e in (PDF_EYE_OPTIONS, PDF_HOOK_RANGE):
        if e in switched_on:
            keys = eff.get(e) or tuple(x.key for x in LESSONS if x.effect == e)
            note(e, applied=e in effects_required, subject=subject, lessons=keys)


# ---- hook (d): QA defect classes -----------------------------------------------------------

TENSION_COMPLAINT = re.compile(
    r"\b(?:too (?:tight|loose)|stitches (?:are |were )?(?:too )?(?:tight|loose)|"
    r"tension|no gauge|missing gauge|gauge (?:is )?(?:missing|not (?:given|stated))|"
    r"wrong size|came out (?:too )?(?:small|big|large))\b", re.I)
GAUGE_CODES = re.compile(r"gauge_every_fabric|GAUGE_(?:MISSING|ABSENT|UNSTATED)|"
                         r"no gauge statement", re.I)


def defect_class(text: str) -> str | None:
    """The benchmark lesson class a defect report belongs to, or None."""
    if TENSION_COMPLAINT.search(text or "") or GAUGE_CODES.search(text or ""):
        return MISSING_GAUGE_CLASS
    return None


def qa_classify(db, read: dict) -> dict:
    """Tag mined defects (incidents, gate refusals) with the MM-L7 lesson class."""
    effects = refresh(db)
    if QA_DEFECT_CLASS not in effects:
        return {"active": False, "classified": []}
    classified = []
    for inc in read.get("incidents") or ():
        text = " ".join((inc.get("signature") or "", inc.get("summary") or ""))
        cls = defect_class(text)
        if cls:
            classified.append({"subject": f"incident:{inc['id']}", "class": cls,
                               "product": inc.get("product_slug")})
    for row in read.get("blocked") or ():
        detail = row.get("detail") or {}
        text = " ".join(str(detail.get(k) or "") for k in ("reason", "why", "code", "failures"))
        cls = defect_class(text)
        if cls:
            classified.append({"subject": f"audit:{row['id']}", "class": cls,
                               "product": (row.get("artifact") or "").split("@", 1)[0]})
    for c in classified:
        record(db, QA_DEFECT_CLASS, applied=True, subject=c["subject"],
               lessons=effects[QA_DEFECT_CLASS], detail={"class": c["class"],
                                                         "product": c["product"]},
               evaluations=0)
    record(db, QA_DEFECT_CLASS, applied=False, subject="", evaluations=1)
    return {"active": True, "classified": classified}


def defect_classes(db) -> dict[str, int]:
    """Recorded defects per lesson class."""
    from sqlalchemy import select

    from .store import LessonEffect, ensure_tables

    ensure_tables(db)
    out: dict[str, int] = {}
    with db.session() as s:
        for r in s.scalars(select(LessonEffect).where(LessonEffect.kind == "applied",
                                                      LessonEffect.hook == QA_DEFECT_CLASS)):
            cls = (r.detail or {}).get("class")
            if cls:
                out[cls] = out.get(cls, 0) + 1
    return out


# ---- readback ------------------------------------------------------------------------------

def readback(db) -> dict:
    """Per department: lessons ingested, lessons wired to a hook, and lessons applied.

    `applied` is a count only when it was measured: the store is readable, the lessons are
    ingested, the department has a wired hook, and that hook has run at least once. Otherwise
    it is UNKNOWN with the reason. A zero is a hook that ran and changed nothing."""
    from sqlalchemy import select

    from .store import LessonEffect

    try:
        stored = active(db)
        with db.session() as s:
            effects = [(r.kind, r.lesson_key, r.department, r.hook, int(r.count or 0))
                       for r in s.scalars(select(LessonEffect))]
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never zero
        return {"readable": False, "error_class": type(exc).__name__[:80],
                "ingested": UNKNOWN,
                "departments": {d: {"ingested": UNKNOWN, "wired": UNKNOWN,
                                    "applied": UNKNOWN, "why": "store unreadable"}
                                for d in DEPARTMENTS}}
    departments = {}
    for d in DEPARTMENTS:
        ours = [x for x in LESSONS if x.department == d]
        ingested = [x for x in ours if x.key in stored]
        wired = [x for x in ingested if x.effect]
        runs = sum(c for kind, _lk, dept, _h, c in effects if kind == "evaluated" and dept == d)
        applied_keys = sorted({lk for kind, lk, dept, _h, _c in effects
                               if kind == "applied" and dept == d})
        applications = sum(1 for kind, _lk, dept, _h, _c in effects
                           if kind == "applied" and dept == d)
        rec = {"ingested": len(ingested), "wired": len(wired)}
        if not ingested:
            rec.update(applied=UNKNOWN, applications=UNKNOWN,
                       why="benchmark lessons not ingested")
        elif not wired:
            rec.update(applied=UNKNOWN, applications=UNKNOWN,
                       why="no decision hook reads this department's lessons yet")
        elif not runs:
            rec.update(applied=UNKNOWN, applications=UNKNOWN,
                       why="the department's hook has not run since ingestion")
        else:
            rec.update(applied=len(applied_keys), applications=applications,
                       hook_runs=runs, lessons_applied=applied_keys)
        departments[d] = rec
    return {"readable": True, "ingested": len(stored), "of": len(LESSONS),
            "departments": departments}
