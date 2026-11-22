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
# LEARN-PROOF-2: the hooks for the eight lessons LEARN-PROOF stored unhooked, and two second
# effects (MM-L3's chenille yarn class, MM-L7's tension guidance).
PRICE_EFFECTIVE = "price_effective_not_strike"      # HC-L1  pricing
CONCEPT_CLUSTER = "concept_cluster_rank"            # HC-L2  product_creativity
ASSET_NO_FAKE_PHOTO = "asset_no_fake_photo_claims"  # HC-L3  creative_assets
PDF_COMPONENT_GROUPED = "pdf_component_grouped"     # HC-L4  pattern_engineering
DELIVERY_PDF = "delivery_pdf_not_link"              # HC-L6  customer_experience
SEO_FRONT_LOAD = "seo_front_load_object"            # HC-L7  seo_search
PDF_JOIN_AS_YOU_GO = "pdf_join_as_you_go"           # MM-L2  pattern_engineering
YARN_CHENILLE = "yarn_chenille_class"               # MM-L3  pattern_engineering (second)
HERO_HAND_SCALE = "hero_hand_scale"                 # MM-L5  creative_assets
PDF_TENSION = "pdf_tension_guidance"                # MM-L7  quality (second)
EFFECTS: tuple[str, ...] = (CONCEPT_RANK, PDF_EYE_OPTIONS, PDF_HOOK_RANGE, SEO_LOW_SEW,
                            QA_DEFECT_CLASS, PRICE_EFFECTIVE, CONCEPT_CLUSTER,
                            ASSET_NO_FAKE_PHOTO, PDF_COMPONENT_GROUPED, DELIVERY_PDF,
                            SEO_FRONT_LOAD, PDF_JOIN_AS_YOU_GO, YARN_CHENILLE,
                            HERO_HAND_SCALE, PDF_TENSION)
# The effects the PDF standard (and the techniques appendix) read from the snapshot.
PDF_EFFECTS: tuple[str, ...] = (PDF_EYE_OPTIONS, PDF_HOOK_RANGE, PDF_COMPONENT_GROUPED,
                                PDF_JOIN_AS_YOU_GO, YARN_CHENILLE, PDF_TENSION)

MISSING_GAUGE_CLASS = "missing_gauge->tension_complaints"


@dataclass(frozen=True)
class BenchmarkLesson:
    source: str              # HC | MM
    number: int              # L<n> in the teardown
    department: str          # improve.cells key
    lesson_class: str
    effect: str | None
    statement: str
    also: tuple[str, ...] = ()   # further hooks the same lesson switches on

    @property
    def key(self) -> str:
        return f"{self.source}-L{self.number}"

    @property
    def effects(self) -> tuple[str, ...]:
        return ((self.effect,) if self.effect else ()) + tuple(self.also)


L = BenchmarkLesson
LESSONS: tuple[BenchmarkLesson, ...] = (
    L("HC", 1, "pricing", "effective_price_is_the_signal", PRICE_EFFECTIVE,
      "A bestselling amigurumi animal clears at a low impulse price; price research reads "
      "the effective price, never the strike price, and clear instructions drive reviews."),
    L("HC", 2, "product_creativity", "cosy_farm_animal_cluster", CONCEPT_CLUSTER,
      "Shaggy and cosy farm animals are a proven amigurumi demand cluster; a fur effect is a "
      "differentiator only when our own construction makes it."),
    L("HC", 3, "creative_assets", "component_diagrams_never_fake_photos",
      ASSET_NO_FAKE_PHOTO,
      "Per-component progress imagery earns trust; without a sample we draw CIR component "
      "diagrams labelled as diagrams, never presented as photographs."),
    L("HC", 4, "pattern_engineering", "component_grouped_pattern_pages",
      PDF_COMPONENT_GROUPED,
      "Amigurumi pattern pages group by component, with numbered assembly steps whose "
      "placement cues name round numbers."),
    L("HC", 5, "quality", "age_guidance_every_amigurumi", PDF_EYE_OPTIONS,
      "Every amigurumi release states age guidance and offers an embroidered face where "
      "safety requires it; the benchmark's absence of this is the gap we fill."),
    L("HC", 6, "customer_experience", "deliver_the_pdf_not_a_link", DELIVERY_PDF,
      "Delivered files are the certified PDFs themselves, read back as downloadable and "
      "hash-matched, never a link page."),
    L("HC", 7, "seo_search", "front_load_object_and_true_badges", SEO_FRONT_LOAD,
      "Titles front-load the object and the words crochet pattern PDF; a badge such as "
      "beginner friendly appears only when the certified difficulty supports it."),
    L("MM", 1, "market_radar", "low_sew_character_amigurumi_demand", CONCEPT_RANK,
      "Low-sew amigurumi animals with a lovable character name and a small piece count are "
      "the concepts to rank first; every animal, character and construction is our own."),
    L("MM", 2, "pattern_engineering", "join_as_you_go_capability", PDF_JOIN_AS_YOU_GO,
      "A join-as-you-go construction, limbs closed flat and crocheted into a named body "
      "round, is a technique class the compiler, twin and reverse must validate."),
    L("MM", 3, "pattern_engineering", "chunky_chenille_needs_hook_range", PDF_HOOK_RANGE,
      "Chunky and chenille yarn is a first-class yarn class: its pattern states a hook-size "
      "range and tension guidance because the fabric is easily worked too loose.",
      also=(YARN_CHENILLE,)),
    L("MM", 4, "pattern_engineering", "eye_options_with_age_guidance", PDF_EYE_OPTIONS,
      "An amigurumi PDF offers an eye-options panel, embroidered versus safety eyes, with "
      "the age guidance each option carries."),
    L("MM", 5, "creative_assets", "hero_in_hand_for_scale", HERO_HAND_SCALE,
      "The hero shows the finished toy at a scale the buyer can read, matching the PDF "
      "cover, with variants filling the gallery."),
    L("MM", 6, "seo_search", "low_sew_modifier_only_when_true", SEO_LOW_SEW,
      "No sew and low sew are high-intent search modifiers; we use them only when the "
      "certified construction really is no-sew or low-sew."),
    L("MM", 7, "quality", MISSING_GAUGE_CLASS, QA_DEFECT_CLASS,
      "A complaint that stitches are too tight with the stated hook is a missing-gauge "
      "defect; QA records it under the lesson class missing gauge leads to tension "
      "complaints.", also=(PDF_TENSION,)),
)
del L
BY_KEY: dict[str, BenchmarkLesson] = {x.key: x for x in LESSONS}
DEPARTMENTS: tuple[str, ...] = tuple(sorted({x.department for x in LESSONS}))
# The department each hook's applications are counted under.
EFFECT_DEPARTMENTS: dict[str, tuple[str, ...]] = {
    e: tuple(sorted({x.department for x in LESSONS if e in x.effects})) for e in EFFECTS}


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
                        "effect": lesson.effect, "effects": list(lesson.effects),
                        "source_sha256": digests[lesson.source]}
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
        for e in BY_KEY[k].effects:
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
         relevant: bool | None = None) -> None:
    """A pure hook ran (and, if `applied`, changed its output because of `lessons`).

    `relevant` (LEARNING-APPLY): the subject met the lesson's applicability predicate, whether
    or not the output then changed. Defaults to `applied` (an application is always relevant).
    It is counted apart from applications and never turned into one."""
    with _LOCK:
        _PENDING.append({"effect": effect, "applied": applied, "subject": subject[:200],
                         "lessons": tuple(lessons), "detail": dict(detail or {}),
                         "relevant": bool(applied if relevant is None else relevant)})


def pending() -> list[dict]:
    with _LOCK:
        return list(_PENDING)


def record(db, effect: str, *, applied: bool, subject: str, lessons=(),
           detail: dict | None = None, evaluations: int = 1,
           relevant: bool | None = None) -> int:
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
            # LEARNING-APPLY: how many runs met the lesson's applicability predicate, so a
            # zero "applied" can be told apart: no relevant subject, or relevant and unchanged.
            if evaluations and (applied if relevant is None else relevant):
                rk = f"relevant:{effect}:{dept}"
                rrow = s.scalar(select(LessonEffect).where(LessonEffect.key == rk))
                if rrow is None:
                    s.add(LessonEffect(key=rk, kind="relevant", lesson_key="", department=dept,
                                       hook=effect, subject="", count=evaluations,
                                       first_at=now, last_at=now, detail={}))
                    s.flush()
                else:
                    rrow.count = int(rrow.count or 0) + evaluations
                    rrow.last_at = now
        if applied:
            for lk in lessons:
                lesson = BY_KEY.get(lk)
                if lesson is None or effect not in lesson.effects:
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
                   lessons=n["lessons"], detail=n["detail"], relevant=n.get("relevant"))
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
    if CHUNKY_CHENILLE_TEXT.search(text.replace("-", " ")):
        traits.append("chunky_chenille")
    return traits


# MM-L1 names chunky chenille alongside low-sew and a character name (LEARN-PROOF-2).
CHUNKY_CHENILLE_TEXT = re.compile(r"\b(?:chenille|chunky|jumbo|blanket yarn|plush yarn)\b",
                                  re.I)
# HC-L2: the cosy / shaggy farm-animal cluster. The animal is read from the concept's own
# words; the fur effect, if any, is our own construction (the concept pipeline scores that).
FARM_ANIMAL_TEXT = re.compile(r"\b(?:cow|calf|highland|sheep|lamb|goat|alpaca|llama|pig|"
                              r"piglet|donkey|pony|horse|hen|chicken|chick|duck|duckling|"
                              r"goose|bunny|rabbit|yak)s?\b", re.I)
CLUSTER_STEP = 0.02
CONCEPT_TOTAL_CAP = CONCEPT_CAP + CLUSTER_STEP   # +0.06: every trait of both lessons


def cluster_traits(seed) -> list[str]:
    """Which HC-L2 traits a radar concept has. Amigurumi only."""
    if (getattr(seed, "category", "") or "").lower() != "amigurumi":
        return []
    text = " ".join(str(getattr(seed, a, "") or "") for a in ("slug", "title", "rationale"))
    return ["cosy_farm_animal"] if FARM_ANIMAL_TEXT.search(text.replace("-", " ")) else []


def concept_rank_delta(seed, effects: dict[str, tuple[str, ...]]) -> tuple[float, list[str]]:
    """MM-L1 (+0.02 per trait, cap +0.04) and HC-L2 (+0.02), together at most +0.06."""
    traits: list[str] = []
    delta = 0.0
    if CONCEPT_RANK in effects:
        mm = concept_traits(seed)
        traits += mm
        delta += min(CONCEPT_CAP, CONCEPT_STEP * len(mm))
    if CONCEPT_CLUSTER in effects:
        hc = cluster_traits(seed)
        traits += hc
        delta += CLUSTER_STEP * len(hc)
    return round(min(CONCEPT_TOTAL_CAP, delta), 4), traits


_CLUSTER_TRAITS = frozenset({"cosy_farm_animal"})


def concept_rank_adjustments(db, seeds) -> dict[str, float]:
    """The MM-L1 / HC-L2 nudge for each seed, recorded as applied, per lesson, for every
    seed it moved."""
    effects = refresh(db)
    out: dict[str, float] = {}
    for seed in seeds:
        delta, traits = concept_rank_delta(seed, effects)
        if delta:
            out[seed.slug] = delta
            mm = [t for t in traits if t not in _CLUSTER_TRAITS]
            hc = [t for t in traits if t in _CLUSTER_TRAITS]
            if mm:
                record(db, CONCEPT_RANK, applied=True, subject=f"concept:{seed.slug}",
                       lessons=effects[CONCEPT_RANK], detail={"traits": mm, "delta": delta},
                       evaluations=0)
            if hc:
                record(db, CONCEPT_CLUSTER, applied=True, subject=f"concept:{seed.slug}",
                       lessons=effects[CONCEPT_CLUSTER], detail={"traits": hc,
                                                                 "delta": delta},
                       evaluations=0)
    for e in (CONCEPT_RANK, CONCEPT_CLUSTER):
        if e in effects:
            record(db, e, applied=False, subject="", evaluations=1)
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
    note(SEO_LOW_SEW, applied=bool(found), subject=f"listing:{slug}",
         lessons=effects[SEO_LOW_SEW], relevant=bool(claims),
         detail={"claims": len(claims), "refused": len(found)})
    return found


# MM-L6 on the generator side (LEARNING-APPLY). The validator above only refuses a false
# claim, and the listing builder never makes one, so on its own the lesson could never change
# a listing. Here the certified construction earns the modifier for the tag set.
SEW_TAG_FAMILY = "amigurumi"


def sew_modifier_relevant(cir) -> bool:
    """MM-L6 is about multi-piece toys: an amigurumi CIR with more than one component. A
    one-piece blanket or basket has no assembly to speak of, so the modifier says nothing."""
    if cir is None or len(getattr(cir, "components", None) or ()) < 2:
        return False
    from ..publish.premium_standard import family_of

    try:
        return family_of(cir) == SEW_TAG_FAMILY
    except Exception:  # noqa: BLE001 - an unplaceable CIR earns nothing
        return False


def earned_sew_tags(cir, effects: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    """The sew modifiers (as tags) the certified construction earns, when MM-L6 is stored."""
    effects = active_effects() if effects is None else effects
    if SEO_LOW_SEW not in effects or not sew_modifier_relevant(cir):
        return []
    return [f"{m} amigurumi" for m in low_sew_modifiers(cir)]


def note_sew_tags(cir, slug: str, earned: list[str], final_tags: list[str],
                  effects: dict[str, tuple[str, ...]] | None = None) -> bool:
    """Record the generator-side MM-L6 run. Applied only when an earned modifier is in the
    final tag set (the lesson changed the listing)."""
    effects = active_effects() if effects is None else effects
    if SEO_LOW_SEW not in effects:
        return False
    added = [t for t in earned if t in final_tags]
    note(SEO_LOW_SEW, applied=bool(added), subject=f"listing:{slug}:tags",
         lessons=effects[SEO_LOW_SEW], relevant=sew_modifier_relevant(cir),
         detail={"earned": list(earned), "added": added})
    return bool(added)


# ---- hook (b): PDF standard ----------------------------------------------------------------

def pdf_lessons(effects: dict[str, tuple[str, ...]] | None = None) -> frozenset[str]:
    effects = active_effects() if effects is None else effects
    return frozenset(e for e in PDF_EFFECTS if e in effects)


def note_pdf(effects_required: list[str], subject: str, switched_on) -> None:
    """The PDF standard ran with these lesson effects on; `effects_required` are the ones
    whose rule applied to this document (and so changed what it must contain)."""
    eff = active_effects()
    for e in PDF_EFFECTS:
        if e in switched_on:
            keys = eff.get(e) or tuple(x.key for x in LESSONS if e in x.effects)
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


# ---- LEARN-PROOF-2 hooks -------------------------------------------------------------------

# HC-L1 (pricing): the effective price is the signal, the strike price is noise. A listing
# payload that carries a sale / effective price beside its listed price is read at the
# effective price, and the listed one is kept apart as `strike_price`, which no band reads.
EFFECTIVE_KEYS = ("effective_price", "sale_price", "price_after_discount", "discounted_price")


def _money(v) -> float | None:
    if isinstance(v, dict):
        try:
            div = float(v.get("divisor") or 1) or 1.0
            return round(float(v.get("amount")) / div, 2)
        except (TypeError, ValueError):
            return None
    if isinstance(v, bool) or v is None or v == "":
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def effective_price(listing: dict, listed: float | None,
                    effects: dict[str, tuple[str, ...]] | None = None) -> dict:
    """{"price", "strike_price", "applied"}: the price research reads. Without the lesson,
    the listed price as before. With it, an effective price below the listed one replaces
    it and the listed price becomes `strike_price` (noise, never banded). A payload with no
    effective price is unchanged: absent is not "no discount"."""
    effects = active_effects() if effects is None else effects
    out = {"price": listed, "strike_price": None, "applied": False}
    if PRICE_EFFECTIVE not in effects or listed is None:
        return out
    for k in EFFECTIVE_KEYS:
        eff = _money(listing.get(k))
        if eff is not None and 0 < eff < listed:
            return {"price": eff, "strike_price": listed, "applied": True, "basis": k}
    return out


# HC-L1 on the pricing department's own cadence (LEARNING-APPLY). The live SERP capture is
# not the only place price research reads competitor prices: every `pricing.decide` job
# anchors on the benchmark catalogue's observed prices (`release._outcome_price`). A listing
# observed on sale carries its listed price as `price_cad`; that is the strike price, which
# the lesson says research never reads. With the lesson, an on-sale row is read at the
# effective price the observation recorded (`detail.effective_price_cad`), or left out of
# the anchor when no effective price was observed. A row not on sale is read as before.

def anchor_prices(db, rows, *, subject: str,
                  effects: dict[str, tuple[str, ...]] | None = None) -> list[float]:
    """The prices a pricing anchor reads from `rows` (BenchmarkListing-shaped). Records one
    hook run, and an application only when an on-sale row's strike price was replaced or
    dropped, which changes what the anchor is computed from."""
    rows = list(rows)
    base = [float(r.price_cad) for r in rows if r.price_cad and r.price_cad > 0]
    if effects is None:
        effects = refresh(db)
    if PRICE_EFFECTIVE not in effects:
        return base
    out: list[float] = []
    replaced = dropped = 0
    for r in rows:
        listed = float(r.price_cad or 0)
        if listed <= 0:
            continue
        if not getattr(r, "on_sale", False):
            out.append(listed)
            continue
        eff = _money((getattr(r, "detail", None) or {}).get("effective_price_cad"))
        if eff is not None and 0 < eff < listed:
            out.append(eff)
            replaced += 1
        else:
            dropped += 1
    on_sale = sum(1 for r in rows if getattr(r, "on_sale", False) and (r.price_cad or 0) > 0)
    record(db, PRICE_EFFECTIVE, applied=bool(replaced or dropped), subject=subject,
           lessons=effects[PRICE_EFFECTIVE], relevant=bool(on_sale),
           detail={"read": len(out), "strike_replaced": replaced, "strike_dropped": dropped})
    return out


def observed_effective_price(listing: dict, listed: float | None) -> float | None:
    """The effective (sale) price a catalogue payload states below its listed price, or None.
    A fact of the observation, stored whatever lessons are active; only the lesson reads it."""
    if listed is None or listed <= 0:
        return None
    for k in EFFECTIVE_KEYS:
        eff = _money(listing.get(k))
        if eff is not None and 0 < eff < listed:
            return eff
    return None


# HC-L3 (creative assets): without a physical sample there is no progress photo, so listing
# copy may not promise photos of the making. Our diagrams are labelled diagrams.
PHOTO_CLAIM = re.compile(r"\b(?:photo|picture)\s+tutorial\b|\bstep[- ]by[- ]step\s+"
                         r"(?:photos?|pictures?|pics)\b|\bprogress\s+(?:photos?|pictures?|"
                         r"pics)\b|\b(?:with|includes?|real)\s+(?:photos?|pictures?)\b|"
                         r"\bphoto\s+(?:pattern|guide|instructions)\b", re.I)


def photo_claim_findings(terms: list[str], *, slug: str = "",
                         effects: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    effects = active_effects() if effects is None else effects
    if ASSET_NO_FAKE_PHOTO not in effects:
        return []
    found = [f"TERM_MISLEADING: {t!r} promises photos of the making; without a physical "
             f"sample our progress imagery is CIR diagrams labelled as diagrams (benchmark "
             f"lesson HC-L3)" for t in terms if PHOTO_CLAIM.search(t or "")]
    note(ASSET_NO_FAKE_PHOTO, applied=bool(found), subject=f"listing:{slug}",
         lessons=effects[ASSET_NO_FAKE_PHOTO], detail={"refused": len(found)})
    return found


# HC-L7 (SEO): front-load the object and "crochet pattern PDF". (The badge half of HC-L7,
# "beginner friendly" only on a certified beginner pattern, is already a base rule:
# `commerce.search.tag_truth`.)
FRONT_LOAD_CHARS = 60
_PATTERN_WORD = re.compile(r"\bpattern\b", re.I)


def front_load_findings(title: str, *, slug: str = "",
                        effects: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    """Soft findings: the title does not say "pattern" within its first FRONT_LOAD_CHARS
    characters, or opens with something other than the object."""
    effects = active_effects() if effects is None else effects
    if SEO_FRONT_LOAD not in effects:
        return []
    title = title or ""
    found = []
    if not _PATTERN_WORD.search(title[:FRONT_LOAD_CHARS]):
        found.append(f"TITLE_NOT_FRONT_LOADED: 'pattern' is not within the first "
                     f"{FRONT_LOAD_CHARS} characters (benchmark lesson HC-L7)")
    first = re.split(r"[|,\-–—]", title, maxsplit=1)[0].strip().lower()
    if re.match(r"(?:easy|beginner|cute|gift|new|best|sale)\b", first):
        found.append(f"TITLE_NOT_FRONT_LOADED: the title opens with {first.split()[0]!r}, "
                     f"not the object (benchmark lesson HC-L7)")
    note(SEO_FRONT_LOAD, applied=bool(found), subject=f"listing:{slug}",
         lessons=effects[SEO_FRONT_LOAD], relevant=bool(title.strip()),
         detail={"findings": len(found)})
    return found


# HC-L6 (customer experience): the delivered file is the certified PDF itself, never a link
# page. Checked on the bytes about to be uploaded.
_HTML = re.compile(rb"<\s*(?:!doctype\s+html|html|head|body|a\s+href|meta\s+http-equiv)", re.I)


def delivery_refusals(filename: str, data: bytes, *, certified_sha256: str | None = None,
                      effects: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    effects = active_effects() if effects is None else effects
    if DELIVERY_PDF not in effects or not data:
        return []
    out = []
    head = data[:1024]
    if not data.startswith(b"%PDF-"):
        out.append(f"{filename} is not a PDF (it does not begin with %PDF-): the delivered "
                   f"file must be the certified PDF itself, never a link page (benchmark "
                   f"lesson HC-L6)")
    if _HTML.search(head):
        out.append(f"{filename} reads as a web page: a link page is not a deliverable "
                   f"(benchmark lesson HC-L6)")
    if data.startswith(b"%PDF-") and b"%%EOF" not in data[-2048:]:
        out.append(f"{filename} is a truncated PDF (no %%EOF trailer) (benchmark lesson HC-L6)")
    if certified_sha256 and hashlib.sha256(data).hexdigest() != certified_sha256:
        out.append(f"{filename} does not match the certified hash (benchmark lesson HC-L6)")
    note(DELIVERY_PDF, applied=bool(out), subject=f"file:{filename}",
         lessons=effects[DELIVERY_PDF], detail={"refusals": len(out)})
    return out


# MM-L5 (creative assets): the scale frame of a toy is the finished toy held in a hand.
HAND_SCALE_CATEGORIES = frozenset({"amigurumi", "toy", "stuffed_animal"})
HAND_SCALE_BRIEF = ("scale: the finished toy held in one open hand, showing its size against "
                    "the hand, on a real textured background, the same toy and colourway as "
                    "the PDF cover")


def scale_brief(category: str, brief: str, *, subject: str = "",
                effects: dict[str, tuple[str, ...]] | None = None) -> str:
    effects = active_effects() if effects is None else effects
    if HERO_HAND_SCALE not in effects:
        return brief
    applies = (category or "").lower() in HAND_SCALE_CATEGORIES
    note(HERO_HAND_SCALE, applied=applies, subject=f"campaign:{subject or category}",
         lessons=effects[HERO_HAND_SCALE])
    return HAND_SCALE_BRIEF if applies else brief


# MM-L2 (pattern engineering): a piece crocheted into a named round of another (a slip-stitch
# or picked-up join at a stated round) is a join-as-you-go construction, and the techniques
# appendix explains it.
JOIN_AS_YOU_GO_METHODS = frozenset({"slst", "pick_up"})


def join_as_you_go_seams(cir) -> list:
    return [s for s in (getattr(cir, "assembly", None) or [])
            if getattr(s, "method", None) in JOIN_AS_YOU_GO_METHODS
            and getattr(s, "at_round", None) is not None]


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
        wired = [x for x in ingested if x.effects]
        runs = sum(c for kind, _lk, dept, _h, c in effects if kind == "evaluated" and dept == d)
        relevant = sum(c for kind, _lk, dept, _h, c in effects if kind == "relevant" and dept == d)
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
                       hook_runs=runs, relevant_runs=relevant, lessons_applied=applied_keys)
            if not applied_keys:
                # LEARNING-APPLY: a measured zero says which kind of zero it is.
                rec["why_zero"] = (
                    "no evaluated subject was recorded as meeting the lessons' "
                    "applicability predicate (no relevant product)" if not relevant else
                    "relevant subjects were evaluated and already satisfied the lessons; "
                    "no output changed")
        departments[d] = rec
    return {"readable": True, "ingested": len(stored), "of": len(LESSONS),
            "departments": departments}
