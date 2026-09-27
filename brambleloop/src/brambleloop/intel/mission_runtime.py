"""The MJs mission, run: what happens when the benchmark posts something.

Requirements 206, 211, 213-217, 219, 220, 226-228, 302, 306-309, 311, 313, 314, 316. Every
library this module calls existed and was unit-tested; an audit on 2026-09-27 found that
nothing in the running system called most of them. This is the runtime half: the `mjs.scan`
handler hands it the listings a scan just stored as new or changed, and each one is carried
through the same eight steps, in order, with every step's result written beside the decision
it produced:

1. **Director routing** (#211) -- `pods.Director` deduplicates on content, routes the listing
   to its pod and computes the company-level standing, `unknown` where either side has no
   evidence.
2. **Mechanism decomposition** (#214) -- the listing's observed fields become `Mechanism`
   rows through a closed rule table, checked by `mechanisms.decompose`, and
   `justifies_tournament` decides whether it is a note or a project.
3. **Panel gates** (#215, #219, #220, #227) -- `panel_state`, `mechanism_is_learnable`,
   `move_bar` (a standard is raised only by a mechanism two sellers show), `may_enter` and
   `ceiling_check`.
4. **`pods.lesson`** (#217) -- every mechanism lesson passes the protected-expression guard
   at the point of writing.
5. **`memory.learn`** (#316) -- the pod's versioned memory: a new interpretation starts with
   no standing, later listings are recorded against it as `benchmark_confirmed` or
   `benchmark_contradicted`, and a contradicted interpretation gets a challenger that wins
   on outcomes or not at all.
6. **`coverage.advance`** (#314) -- the arena's gap leaves `uncovered` when work actually
   starts, and says why when it does not.
7. **The response pipeline** (#306, #307, #309) -- `consider_arena` records the pod's answer
   (including no), `seasonalise` asks the next-season question on all eight lenses, and
   `PipelineRun` walks the fourteen stages until a gate stops it.
8. **The breakthrough tournament** (#216) -- a divergent `creative.tournament` is enqueued
   when the decomposition justifies one and the objective is not a ceiling.

No step reaches the network. Everything is read from rows the scan already stored, so the
whole pipeline runs in shadow mode against recorded fixture observations exactly as it runs
against a live scan.

Three smaller runtime paths live here too, because they read the same rows: the benchmark URL
health check (#206), the pods' capability readings (#226), the owner's veto memory (#228) and
the seasonal deadline sentinel for MJs-derived opportunities (#311).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from . import benchmarks, coverage, memory, panel, pods, response
from . import mechanisms as mech

# ---------------------------------------------------------------------------
# Constants, each one a decision with its reason

# Favourites across the benchmark's observed listings in one arena before the arena counts as
# *proven* (#306). Favourites are a demand proxy -- a buyer saving a listing is not a buyer
# paying for it -- and this is labelled as a proxy wherever it is used. The floor is set
# where one popular listing cannot carry an arena by itself in a shop with 8k+ favourites on
# its leaders.
PROVEN_ARENA_FAVOURITES = 200

# Customer make hours per arena, for the launch-date arithmetic before any CIR exists. Every
# figure is an ASSUMPTION drawn from the make-time evidence already recorded in
# `radar.market` (small decor 1-4 h, baby blanket 3-20 h, throw 30-40 h) and it is reported
# as assumed on every plan; the CIR's own twin replaces it once a pattern exists.
ARENA_MAKE_HOURS: dict[str, float] = {
    "cardigan": 30.0, "sweater": 30.0, "blanket": 35.0, "stocking": 8.0, "ornament": 2.0,
    "bag": 6.0, "hat": 5.0, "coaster": 1.0, "decor": 4.0, "amigurumi": 6.0,
    "scarf": 10.0, "pillow": 8.0,
}
MAKE_HOURS_BASIS = ("assumed from radar.market make-time evidence; replaced by the CIR's "
                    "digital twin once a pattern exists")

# Title words that name a `response.ARENAS` arena, singular (pods._words singularises).
ARENA_WORDS: dict[str, tuple[str, ...]] = {
    "cardigan": ("cardigan",),
    "sweater": ("sweater", "jumper", "pullover"),
    "stocking": ("stocking",),
    "blanket": ("blanket", "throw", "afghan"),
    "ornament": ("ornament", "bauble"),
    "bag": ("bag", "tote", "purse"),
    "hat": ("hat", "beanie", "toque", "tuque"),
    "coaster": ("coaster",),
    "amigurumi": ("amigurumi", "plushie", "stuffie"),
    "scarf": ("scarf", "cowl"),
    "pillow": ("pillow", "cushion"),
}

# Generic characteristics of a finished object (#306), read from the listing's own words. The
# keys are `response.GENERIC_CHARACTERISTICS`; nothing here is the seller's arrangement.
CHARACTERISTIC_WORDS: dict[str, tuple[str, ...]] = {
    "silhouette": ("cropped", "crop", "oversized", "longline", "fitted", "boxy"),
    "neckline": ("v neck", "vneck", "crew neck", "boat neck", "collar", "collared"),
    "closure": ("button", "open front", "zip", "zipper"),
    "colour_blocking": ("stripe", "striped", "colour block", "color block", "colorblock",
                        "ombre"),
    "texture_class": ("cable", "bobble", "ribbed", "textured"),
    "sleeve_form": ("raglan", "balloon sleeve", "drop shoulder"),
    "yarn_weight_class": ("dk", "worsted", "chunky", "aran", "bulky"),
}

# What this shop offers beyond parity when it enters an arena (#215). Both axes are true of
# how Brambleloop builds every product, not an aspiration: the compiler verifies every size
# before release and the instructions are generated from the verified CIR.
#
# C-60 (#215): these were passed to `may_enter` as constants, so every entry offered the same
# two axes whatever the benchmark listing showed. They are now the vocabulary only; `entry_axes`
# decides per listing which of them this shop can actually claim beyond that listing.
ENTRY_AXES: tuple[str, ...] = ("product_engineering", "usability")
ENTRY_HOW = ("every size is compiled and verified by the deterministic CIR compiler before "
             "release, and the written pattern is generated from that verified record rather "
             "than typed beside it")
AXIS_HOW: dict[str, str] = {
    "product_engineering": ("a graded run of {ours} sizes, every one compiled and verified "
                            "by the deterministic CIR compiler before release, where the "
                            "benchmark listing states {theirs}"),
    "usability": ("the listing states format, extent, contents, stitch terms, finished size, "
                  "yarn and hook, generated from the verified record, where the benchmark "
                  "listing leaves {unclear} of those unstated"),
}

# The arena's generic form, as `creative.family.FORM_CONSTRUCTIONS` names it, so the
# engineering axis is claimed only where the compiler can actually build the form.
ARENA_FORM: dict[str, str] = {
    "cardigan": "fitted_garment", "sweater": "fitted_garment", "blanket": "rectangle_throw",
    "amigurumi": "toy", "decor": "wall_hanging",
}
DIFFERENTIATOR = ("an independently engineered Brambleloop CIR: original construction, "
                  "compiler-verified grading across sizes, and Brambleloop-owned imagery")

# Occasion words that make a title name its buying occasion.
OCCASION_WORDS: tuple[str, ...] = ("christmas", "halloween", "easter", "valentine",
                                   "thanksgiving", "holiday", "festive", "winter")

# The seasonal vocabulary per calendar event (#307). Generic seasonal language that belongs to
# nobody; `response.check_generic` still reads every value.
_SEASON: dict[str, dict[str, str]] = {
    "Christmas": {"palette": "forest, cranberry, cream and gold",
                  "trim": "cream contrast edging with gold-toned buttons",
                  "motif": "evergreen and snowflake banding in the generic stripe layout",
                  "gift": "a handmade Christmas gift finished in time for the exchange",
                  "accessory": "a quick-make hat or ornament in the same palette",
                  "styling": "layered for a winter morning beside a lit tree"},
    "Halloween": {"palette": "pumpkin orange, charcoal, plum and bone",
                  "trim": "charcoal contrast edging",
                  "motif": "harvest-moon and bat banding in the generic stripe layout",
                  "gift": "a handmade piece for an autumn party or a trick-or-treat night",
                  "accessory": "a quick-make treat bag in the same palette",
                  "styling": "styled at dusk with lanterns and fallen leaves"},
    "Thanksgiving (CA)": {"palette": "rust, mustard, moss and oat",
                          "trim": "oat contrast edging with wooden buttons",
                          "motif": "leaf and wheat banding in the generic stripe layout",
                          "gift": "a hostess gift for a harvest dinner",
                          "accessory": "quick-make coasters in the same palette",
                          "styling": "styled at a harvest table in low autumn light"},
    "Valentine's": {"palette": "rose, blush, berry and cream",
                    "trim": "picot edging in berry",
                    "motif": "small heart banding in the generic stripe layout",
                    "gift": "a gift for a partner or a best friend",
                    "accessory": "a quick-make pouch in the same palette",
                    "styling": "styled for a slow weekend morning"},
    "Easter": {"palette": "sorbet, butter yellow, sage and cream",
               "trim": "scalloped edging in cream",
               "motif": "blossom banding in the generic stripe layout",
               "gift": "a spring gift for a child or a new parent",
               "accessory": "a quick-make basket liner in the same palette",
               "styling": "styled outdoors in spring daylight"},
    "Mother's Day": {"palette": "lilac, sage, cream and soft coral",
                     "trim": "shell edging in cream",
                     "motif": "small floral banding in the generic stripe layout",
                     "gift": "a gift a maker gives to their mother",
                     "accessory": "a quick-make scarf in the same palette",
                     "styling": "styled for a garden brunch"},
}


def season_lenses(event: str, arena: str) -> dict[str, str]:
    """All eight of #307's lenses for one event, or {} for an event with no vocabulary."""
    v = _SEASON.get(event)
    if v is None:
        return {}
    return {
        "colour_palette": v["palette"],
        "styling": f"the {arena} {v['styling']}",
        "trim": v["trim"],
        "motif_vocabulary": v["motif"],
        "gift_context": v["gift"],
        "supporting_accessories": v["accessory"],
        "bundles": f"the {arena} pattern sold beside {v['accessory']}",
        "merchandising": (f"a listing framed around the {event} make-by date, stating the "
                          f"latest start date for a customer to finish in time"),
    }


# ---------------------------------------------------------------------------
# The mechanism rule table (#214, #217)
#
# A mechanism is taken only from a field the scan actually observed. A rule whose input was
# never read answers None -- unknown -- and contributes nothing, rather than counting as the
# mechanism being absent.


@dataclass(frozen=True)
class Rule:
    key: str
    klass: str
    pod_mechanism: str      # pods.MECHANISMS, where lessons are stored
    generic: str            # the mechanism in words that name no listing
    effect: str
    standard: str = ""      # the CompetitiveStandard this can raise, if any
    adoptable: bool = True  # False: learned about, never copied (a display discount)


RULES: tuple[Rule, ...] = (
    Rule("gallery_depth", mech.PRESENTATION, "photography_coverage", "a deep image gallery",
         "shows the finished object from enough angles that a buyer can judge fit and "
         "finish before asking", standard="gallery_images"),
    Rule("gallery_video", mech.PRESENTATION, "photography_coverage",
         "a video in the listing gallery",
         "shows the fabric moving and draping, which still photographs cannot demonstrate "
         "before purchase", standard="video_in_gallery"),
    Rule("deliverable_stated", mech.INFORMATION, "delivery_format",
         "a clear statement of what arrives in the download",
         "answers the question a buyer would otherwise ask before committing to the "
         "purchase"),
    Rule("size_range", mech.RANGE, "size_presentation", "a wide graded size range",
         "lets one listing serve buyers across a wide body range instead of losing them",
         standard="size_options"),
    Rule("bundle", mech.PACKAGING, "bundle_logic", "several patterns sold as one purchase",
         "makes each included pattern look cheaper than buying it on its own"),
    Rule("sale_display", mech.PRICING, "merchandising",
         "a reduced price shown against a higher reference price",
         "anchors the price against a larger number the buyer sees first",
         adoptable=False),
    # #208: options and variants read from the API's listing fields (has_variations,
    # is_personalizable). Unknown where the scan did not carry them.
    Rule("options_offered", mech.RANGE, "merchandising",
         "buyer-selectable options or personalisation on the listing",
         "lets one listing answer several buyers' choices instead of sending them elsewhere"),
    Rule("occasion_title", mech.INFORMATION, "seasonal_timing",
         "the buying occasion named in the listing title",
         "puts the listing in front of buyers searching for that occasion during its "
         "buying window"),
)
RULE_BY_KEY: dict[str, Rule] = {r.key: r for r in RULES}

# Why a rule is never adopted, in the words the refusal uses.
NOT_ADOPTED = {"sale_display": ("a perpetual display discount is refused here: the owner's "
                                "directive forbids deceptive discounts, so this is learned "
                                "about and never copied")}

MIN_GALLERY = 5
MIN_SIZES = 5
CLEAR_DELIVERABLE = 0.75


def _listing_snapshot(row) -> dict:
    return {"benchmark_key": row.benchmark_key, "listing_ref": row.listing_ref,
            "title": row.title or "", "pod": row.pod or pods.UNCLASSIFIED,
            "product_type": row.product_type or "", "fingerprint": row.fingerprint or "",
            "media_count": int(row.media_count or 0), "on_sale": bool(row.on_sale),
            "detail": dict(row.detail or {})}


def evaluate(rule: Rule, snap: dict) -> tuple[bool | None, str, float | None]:
    """(present, what, standard value) for one rule on one observed listing."""
    d = snap["detail"]
    if rule.key == "gallery_depth":
        if not d.get("gallery_audited"):
            return None, "", None
        n = snap["media_count"]
        return n >= MIN_GALLERY, f"a gallery of {n} images", float(n)
    if rule.key == "gallery_video":
        if "has_video" not in d:
            return None, "", None
        present = bool(d["has_video"])
        return present, rule.generic, 1.0 if present else 0.0
    if rule.key == "deliverable_stated":
        facts = d.get("deliverable") or {}
        if facts.get("clarity") is None:
            return None, "", None
        return facts["clarity"] >= CLEAR_DELIVERABLE, rule.generic, None
    if rule.key == "size_range":
        sr = d.get("size_range")
        if not sr or not sr.get("stated"):
            return None, "", None
        n = int(sr.get("sizes") or 0)
        return n >= MIN_SIZES, f"a pattern graded across {n} sizes", float(n)
    if rule.key == "bundle":
        present = (snap["pod"] == "collections"
                   or pods.counts_its_own_patterns(snap["title"]))
        return present, rule.generic, None
    if rule.key == "sale_display":
        return snap["on_sale"], rule.generic, None
    if rule.key == "options_offered":
        opts = d.get("options") or {}
        if not any(k in opts for k in ("has_variations", "is_personalizable")):
            return None, "", None
        return (bool(opts.get("has_variations")) or bool(opts.get("is_personalizable")),
                rule.generic, None)
    if rule.key == "occasion_title":
        words = set(pods._words(snap["title"]))  # noqa: SLF001 - the router's own tokeniser
        return bool(words & set(OCCASION_WORDS)), rule.generic, None
    raise KeyError(rule.key)


def our_mechanisms(db) -> dict:
    """Which of the rule table's mechanisms this shop demonstrably has, from its own rows.

    A mechanism we cannot show from our own tables is not assumed: it is reported as
    unmeasured and counts as not had, so a tournament is never refused on a capability
    nobody checked.
    """
    from sqlalchemy import select

    from ..core.models import Listing
    from . import deliverable

    with db.session() as s:
        rows = [(r.title or "", r.description or "") for r in s.scalars(select(Listing))]
    have: set[str] = set()
    for title, desc in rows:
        low = desc.lower()
        if "what you get" in low or "you receive" in low:
            have.add("deliverable_stated")
        sizes = deliverable.size_range({"description": desc}, pod="garments")
        if sizes and int(sizes.get("sizes") or 0) >= MIN_SIZES:
            have.add("size_range")
        if pods.counts_its_own_patterns(title):
            have.add("bundle")
        if set(pods._words(title)) & set(OCCASION_WORDS):  # noqa: SLF001
            have.add("occasion_title")
    return {"have": sorted(have), "listings_read": len(rows),
            "unmeasured": ["gallery_depth", "gallery_video"],
            "never_adopted": sorted(NOT_ADOPTED)}


def arena_for(title: str, pod: str) -> str:
    """The `response.ARENAS` arena a listing sells into, or "" when none is recorded."""
    words = pods._words(title)  # noqa: SLF001
    best, at = "", len(words) + 1
    for arena, needles in ARENA_WORDS.items():
        for i, w in enumerate(words):
            if w in needles and i < at:
                best, at = arena, i
    if best:
        return best
    return "decor" if pod == "home_decor" else ""


def entry_axes(snap: dict, arena: str) -> tuple[tuple[str, ...], str]:
    """Which superiority axes this shop can claim beyond *this* benchmark listing (#215).

    Read from the observed listing, never assumed: engineering is claimed only where the
    compiler builds the arena's form, size is a variable there, and the listing is observed to
    grade across fewer sizes than the compiler's verified run (`cir.benchmarks.SIZES`); usability only where the listing's own description leaves part of what
    arrives unstated. An unread field claims nothing. With no axis the answer is parity, which
    `panel.may_enter` refuses.
    """
    from ..creative.family import FORM_CONSTRUCTIONS

    axes: list[str] = []
    how: list[str] = []
    d = snap.get("detail") or {}
    form = ARENA_FORM.get(arena, arena)
    sizes = d.get("size_range") or {}
    facts = d.get("deliverable") or {}
    their_sizes = int(sizes.get("sizes") or 0) if sizes.get("stated") else 0
    # Only where size is a real variable (`deliverable.SIZED_PODS`), and only where the size
    # reading exists -- `size_range` is stored only once the description was read.
    from .deliverable import SIZED_PODS
    sized = snap.get("pod") in SIZED_PODS and bool(sizes)
    from ..cir.benchmarks import SIZES as GRADABLE
    if arena and FORM_CONSTRUCTIONS.get(form) and sized and their_sizes < len(GRADABLE):
        axes.append("product_engineering")
        how.append(AXIS_HOW["product_engineering"].format(
            ours=len(GRADABLE), theirs=their_sizes))
    clarity = facts.get("clarity")
    if clarity is not None and clarity < CLEAR_DELIVERABLE:
        axes.append("usability")
        how.append(AXIS_HOW["usability"].format(
            unclear=f"{round((1 - clarity) * 100)}%"))
    if not axes:
        return (panel.PARITY,), ""
    return tuple(axes), "; ".join(how)


def same_arena_objective(arena: str, axes: tuple[str, ...], how: str) -> str:
    """The objective a same-arena response is briefed with -- the text #227 checks."""
    beyond = [a for a in axes if a != panel.PARITY]
    return (f"an original Brambleloop {arena} that goes beyond the benchmark on "
            f"{' and '.join(a.replace('_', ' ') for a in beyond) or 'nothing yet'} ({how}), "
            f"and a search for white space beyond what the benchmark currently offers")


def characteristics(snap: dict) -> tuple[str, ...]:
    """Generic characteristics of the finished object, read from the listing's own words."""
    tags = " ".join(str(t) for t in (snap["detail"].get("tags") or []))
    phrase = f' {" ".join(pods._words(snap["title"] + " " + tags))} '  # noqa: SLF001
    found = [key for key, needles in CHARACTERISTIC_WORDS.items()
             if any(f" {' '.join(pods._words(n))} " in phrase for n in needles)]  # noqa: SLF001
    sr = snap["detail"].get("size_range") or {}
    if int(sr.get("sizes") or 0) > 1:
        found.append("size_range")
    return tuple(sorted(set(found)))


def arena_demand(db, *, benchmark_key: str, arena: str) -> dict:
    """Favourites across the benchmark's observed listings in one arena (#306's 'proven')."""
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    with db.session() as s:
        rows = [(r.title or "", r.pod or "", (r.detail or {}).get("num_favorers"))
                for r in s.scalars(select(BenchmarkListing).where(
                    BenchmarkListing.benchmark_key == benchmark_key,
                    BenchmarkListing.audit_state != "withdrawn"))]
    in_arena = [fav for title, pod, fav in rows if arena_for(title, pod) == arena]
    counted = [int(f) for f in in_arena if isinstance(f, (int, float))]
    total = sum(counted)
    return {"arena": arena, "listings": len(in_arena), "with_favourites": len(counted),
            "favourites": total if counted else None,
            "threshold": PROVEN_ARENA_FAVOURITES,
            "proven": bool(counted) and total >= PROVEN_ARENA_FAVOURITES,
            "basis": "favourites are a demand proxy: a saved listing is not a sale"}


def seasonal_target(arena: str, today: date) -> dict | None:
    """The next calendar event a customer can still finish this arena's product for."""
    from ..radar.market import SEASONAL_EVENTS
    from ..seasonal.leadtime import MISSED, compile_launch, next_occurrence

    hours = ARENA_MAKE_HOURS.get(arena)
    if hours is None:
        return None
    skipped = []
    for ev in sorted(SEASONAL_EVENTS, key=lambda e: next_occurrence(e.event_date, today)):
        when = next_occurrence(ev.event_date, today)
        plan = compile_launch(ev.name, when, make_hours=hours)
        state = plan.status(today)
        if state == MISSED:
            skipped.append({"event": ev.name, "latest_effective_launch":
                            plan.latest_effective_launch.isoformat()})
            continue
        return {"event": ev.name, "event_date": when.isoformat(), "arena": arena,
                "make_hours": hours, "make_hours_basis": MAKE_HOURS_BASIS,
                "lane": plan.lane, "status": state,
                "preferred_launch": plan.preferred_launch.isoformat(),
                "latest_effective_launch": plan.latest_effective_launch.isoformat(),
                "days_to_preferred": plan.days_to_preferred(today),
                "days_to_latest": plan.days_to_latest(today),
                "skipped_as_missed": skipped}
    return None


# ---------------------------------------------------------------------------
# Finding what to process


def pending(db, *, benchmark_key: str = benchmarks.MJS_KEY, observations: int = 20) -> list:
    """New or changed listings in the recent scan observations not yet carried through.

    Baseline scans are not events: the first scan finds every listing at once, which is the
    same rule `observe.adaptive_interval` applies. Idempotent on the listing's content
    fingerprint, so a listing is reasoned over once per version of it.
    """
    from sqlalchemy import desc, select

    from ..core.models import BenchmarkListing, BenchmarkObservation, MjsMissionEvent

    with db.session() as s:
        obs = list(s.scalars(select(BenchmarkObservation).where(
            BenchmarkObservation.benchmark_key == benchmark_key,
            BenchmarkObservation.kind == "official_api_read")
            .order_by(desc(BenchmarkObservation.id)).limit(observations)))
        done = {(e.listing_ref, e.fingerprint) for e in s.scalars(
            select(MjsMissionEvent).where(MjsMissionEvent.benchmark_key == benchmark_key))}
        rows = {r.listing_ref: r for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key))}
        out, seen = [], set()
        for o in obs:
            d = o.detail or {}
            if d.get("baseline"):
                continue
            for change in d.get("changes") or []:
                what = change.get("what")
                ref = str(change.get("listing_ref") or "")
                if what not in ("new listing", "materially changed") or ref in seen:
                    continue
                seen.add(ref)
                row = rows.get(ref)
                if row is None or row.audit_state == "withdrawn":
                    continue
                if (ref, row.fingerprint or "") in done:
                    continue
                out.append({"observation_id": o.id, "listing_ref": ref, "what": what,
                            "snapshot": _listing_snapshot(row)})
    return out


# ---------------------------------------------------------------------------
# Step 3 helpers: the panel and the standards


def panel_members(db, today: date) -> list[panel.Member]:
    """Who is on the elite panel today, from rows: benchmarks observed and products bought."""
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, BenchmarkProduct

    members: dict[str, dict] = {}
    with db.session() as s:
        for r in s.scalars(select(BenchmarkListing)):
            m = members.setdefault(r.benchmark_key, {"cats": set(), "first": None})
            m["cats"].add(r.pod or pods.UNCLASSIFIED)
            first = r.first_seen.date() if r.first_seen else today
            m["first"] = first if m["first"] is None else min(m["first"], first)
        for p in s.scalars(select(BenchmarkProduct)):
            m = members.setdefault(p.seller, {"cats": set(), "first": None})
            m["cats"].add(p.pod or pods.UNCLASSIFIED)
            try:
                first = date.fromisoformat(p.purchased_on) if p.purchased_on else today
            except ValueError:
                first = today
            m["first"] = first if m["first"] is None else min(m["first"], first)
    return [panel.Member(seller_ref=key, categories=tuple(sorted(v["cats"])),
                         added_on=min(v["first"] or today, today),
                         is_anchor=(key == benchmarks.MJS_KEY))
            for key, v in sorted(members.items())]


def sellers_showing(db, rule: Rule, pod: str) -> tuple[str, ...]:
    """Every benchmark seller whose observed listings in this pod show the mechanism."""
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    with db.session() as s:
        snaps = [_listing_snapshot(r) for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.pod == pod))]
    return tuple(sorted({sn["benchmark_key"] for sn in snaps
                         if evaluate(rule, sn)[0] is True}))


def apply_bar(db, *, rule: Rule, value: float, learnable: dict, prompted_by: str,
              because: str) -> dict:
    """`panel.move_bar` for one standard, applied only when two sellers show the mechanism."""
    from sqlalchemy import select

    from ..core.models import CompetitiveStandard

    now = datetime.now(timezone.utc)
    with db.session() as s:
        row = s.scalar(select(CompetitiveStandard).where(
            CompetitiveStandard.key == rule.standard))
        if row is None:
            row = CompetitiveStandard(key=rule.standard, value=None, higher_is_better=True,
                                      history=[])
            s.add(row)
            s.flush()
        current = row.value
        outcome = panel.move_bar(panel.StandardChange(
            standard=rule.standard, from_value=float(current or 0.0), to_value=float(value),
            higher_is_better=bool(row.higher_is_better), prompted_by=prompted_by,
            because=because))
        applied = False
        if outcome["outcome"] == panel.RAISED and learnable.get("learnable"):
            row.value = float(value)
            applied = True
        elif outcome["outcome"] == panel.RAISED:
            outcome = {**outcome, "held": True,
                       "held_because": learnable.get("why", "")}
        if outcome["outcome"] != panel.UNCHANGED:
            row.history = list(row.history or []) + [{
                "at": now.isoformat(), "outcome": outcome["outcome"], "applied": applied,
                "from": current, "to": float(value), "prompted_by": prompted_by,
                "because": because, "sellers": learnable.get("sellers", [])}]
            row.updated_at = now
    return {**outcome, "applied": applied, "standard": rule.standard,
            "current_before": current}


# ---------------------------------------------------------------------------
# Step 5 helpers: the pods' versioned memory


CHALLENGE_MARGIN = 2  # contradictions beyond supports before a challenger is raised


def _statement(pod: str, rule: Rule, polarity: str) -> str:
    if polarity == "present":
        return (f"New {pod} listings from the benchmark will carry {rule.generic}, "
                f"because it {rule.effect}")
    return (f"New {pod} listings from the benchmark will usually not carry {rule.generic}; "
            f"it is occasional there rather than the category norm")


def _set_detail(db, lesson_id: int, **fields) -> None:
    from ..core.models import PodLesson

    with db.session() as s:
        row = s.get(PodLesson, lesson_id)
        row.detail = {**(row.detail or {}), **fields}


def _has_evidence(row, evidence_ref: str) -> bool:
    return any(e.get("evidence_ref") == evidence_ref
               for e in list(row.supported_by or []) + list(row.contradicted_by or []))


def record_outcomes(db, *, pod: str, snap: dict, evidence_ref: str) -> list[dict]:
    """Score every standing interpretation in this pod against a listing it did not come from.

    `benchmark_confirmed` when the benchmark did what the interpretation predicts, and
    `benchmark_contradicted` when it did the opposite (#316's closed outcome list). A rule
    whose input this listing never showed is skipped: unknown is not a contradiction.
    """
    from sqlalchemy import select

    from ..core.models import PodLesson

    with db.session() as s:
        rows = [(r.id, r.subject, dict(r.detail or {}), _has_evidence(r, evidence_ref))
                for r in s.scalars(select(PodLesson).where(
                    PodLesson.pod == pod, PodLesson.subject.like("mjs:%")))]
    out = []
    for lesson_id, subject, detail, already in rows:
        rule = RULE_BY_KEY.get(subject.split(":", 1)[1])
        if rule is None or already or detail.get("origin_listing") == snap["listing_ref"]:
            continue
        present = evaluate(rule, snap)[0]
        if present is None:
            continue
        confirms = present if detail.get("polarity", "present") == "present" else not present
        kind = "benchmark_confirmed" if confirms else "benchmark_contradicted"
        out.append(memory.outcome(db, lesson_id, kind, evidence_ref=evidence_ref))
    return out


def raise_challengers(db, *, pod: str) -> list[dict]:
    """A contradicted interpretation gets an alternative, which competes on outcomes (#316).

    The challenger inherits the incumbent's recorded outcomes inverted -- the same benchmark
    listings, read the other way -- so it competes on evidence already in hand rather than
    waiting for new listings, and `memory.resolve` then decides on outcomes alone.
    """
    from sqlalchemy import select

    from ..core.models import PodLesson

    with db.session() as s:
        by_subject: dict[str, list] = {}
        for r in s.scalars(select(PodLesson).where(
                PodLesson.pod == pod, PodLesson.subject.like("mjs:%"))):
            by_subject.setdefault(r.subject, []).append(
                (r.id, r.origin, r.active, len(r.supported_by or []),
                 len(r.contradicted_by or []), list(r.supported_by or []),
                 list(r.contradicted_by or []), dict(r.detail or {})))
    raised = []
    for subject, rows in by_subject.items():
        if any(origin == "challenger" for _i, origin, *_ in rows):
            continue
        incumbent = next((r for r in rows if r[2]), rows[0])
        lid, _o, _a, sup, con, sup_rows, con_rows, detail = incumbent
        if con - sup < CHALLENGE_MARGIN:
            continue
        rule = RULE_BY_KEY.get(subject.split(":", 1)[1])
        if rule is None:
            continue
        cid = memory.challenge(db, lid, statement=_statement(pod, rule, "absent"),
                               mechanism=rule.pod_mechanism)
        _set_detail(db, cid, polarity="absent", rule=rule.key,
                    origin_listing=detail.get("origin_listing", ""),
                    benchmark=detail.get("benchmark", ""))
        for e in con_rows:
            memory.outcome(db, cid, "benchmark_confirmed", evidence_ref=e["evidence_ref"])
        for e in sup_rows:
            memory.outcome(db, cid, "benchmark_contradicted", evidence_ref=e["evidence_ref"])
        resolved = memory.resolve(db, pod=pod, subject=subject)
        raised.append({"subject": subject, "incumbent": lid, "challenger": cid,
                       "resolved_to": resolved.get("active_lesson_id"),
                       "changed": resolved.get("changed")})
    return raised


# ---------------------------------------------------------------------------
# The eight steps


def _enqueue_breakthrough(db, enqueue: Callable, *, event_id: int, arena: str, pod: str,
                          ref: str, benchmark_key: str, today: date,
                          seasonal: dict | None) -> dict:
    from sqlalchemy import select

    from ..core.models import Job
    from ..creative import breakthrough
    from ..swarm.orchestrate import priority_for

    inputs = breakthrough.release_brief(db, arena=arena, pod=pod, listing_ref=ref)
    inputs.update({"mjs_event_id": event_id,
                   "seasonal_target": (seasonal or {}).get("event", "")})
    year, week, _ = today.isocalendar()
    key = f"mjs.breakthrough:{benchmark_key}:{arena}:{year}-W{week:02d}"
    job = enqueue("creative_director", "creative.tournament", inputs,
                  priority=priority_for("creative.tournament"), idempotency_key=key)
    if job is None:
        with db.session() as s:
            existing = s.scalar(select(Job).where(Job.idempotency_key == key))
            job_id = existing.id if existing is not None else None
        return {"enqueued": False, "job_id": job_id, "idempotency_key": key,
                "why": "a breakthrough tournament for this arena is already queued this week",
                "diverged_from": inputs["diverged_from"]}
    return {"enqueued": True, "job_id": job.id, "idempotency_key": key,
            "diverged_from": inputs["diverged_from"], "briefs": len(inputs["briefs"])}


def process_listing(db, item: dict, *, director: pods.Director, enqueue: Callable,
                    today: date, ours: dict, objective: str | None = None) -> dict | None:
    """Carry one new or changed listing through the eight steps. None when a duplicate."""
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, CoverageGap, Job, JobStatus, MjsMissionEvent
    from ..culture import rights

    snap = item["snapshot"]
    key, ref, fp = snap["benchmark_key"], snap["listing_ref"], snap["fingerprint"]
    obs_id = item["observation_id"]
    evidence_ref = f"benchmark_observation:{obs_id}/listing:{ref}@{fp[:12]}"
    steps: dict = {}

    # -- 1. director routing (#211) ------------------------------------------------------
    payload = {"benchmark": key, "listing_ref": ref, "content": fp}
    if director.is_duplicate(payload):
        return None
    pod = director.route_observation(snap["title"], snap["product_type"])
    if pod != snap["pod"]:
        with db.session() as s:
            row = s.scalar(select(BenchmarkListing).where(
                BenchmarkListing.benchmark_key == key, BenchmarkListing.listing_ref == ref))
            if row is not None:
                row.pod = pod
        snap = {**snap, "pod": pod}
    standing = _standing(db, director, key=key, pod=pod)
    steps["routing"] = {"pod": pod, "event_fingerprint": pods.fingerprint(payload),
                        "standing": standing}

    with db.session() as s:
        event = MjsMissionEvent(benchmark_key=key, listing_ref=ref, fingerprint=fp,
                                event_fingerprint=pods.fingerprint(payload),
                                observation_id=obs_id, what=item["what"], pod=pod)
        s.add(event)
        s.flush()
        event_id = event.id

    # -- 2. mechanism decomposition (#214) -----------------------------------------------
    present: list[tuple[Rule, str, float | None]] = []
    unknown: list[str] = []
    for rule in RULES:
        got, what, value = evaluate(rule, snap)
        if got is None:
            unknown.append(rule.key)
        elif got:
            present.append((rule, what, value))
    tokens = [rights.ProtectedToken(benchmarks.MJS_SHOP, rights.LOGO,
                                    source="the benchmark shop's name")]
    mechanisms = [mech.Mechanism(listing_ref=ref, klass=r.klass, what=what, effect=r.effect,
                                 evidence_ref=evidence_ref, pod=pod)
                  for r, what, _v in present]
    decomposition = mech.decompose(listing_ref=ref, mechanisms=mechanisms,
                                   protected_tokens=tokens)
    arena = arena_for(snap["title"], pod)
    demand = (arena_demand(db, benchmark_key=key, arena=arena) if arena else
              {"proven": False, "why": "no recorded arena for this listing"})
    proven = bool(demand.get("proven"))
    adoptable_whats = {what for r, what, _v in present if r.adoptable}
    for_tournament = {**decomposition, "mechanisms": [
        m for m in decomposition["mechanisms"] if m["what"] in adoptable_whats]}
    already = {what for r, what, _v in present if r.key in set(ours["have"])}
    tournament = mech.justifies_tournament(decomposition=for_tournament,
                                           already_have=already,
                                           arena_has_evidence=proven)
    steps["decomposition"] = {**decomposition, "unknown_rules": unknown,
                              "not_adopted": {r.key: NOT_ADOPTED[r.key]
                                              for r, _w, _v in present if not r.adoptable},
                              "arena": arena, "demand": demand, "tournament": tournament}

    # -- 3. panel gates (#219, #220, #215, #227) -----------------------------------------
    members = panel_members(db, today)
    pstate = panel.panel_state(members, on=today, category=pod)
    learnable: dict[str, dict] = {}
    bars: list[dict] = []
    for rule, what, value in present:
        learnable[rule.key] = panel.mechanism_is_learnable(
            mechanism=rule.key, seen_in=sellers_showing(db, rule, pod))
        if rule.standard and value is not None and rule.adoptable:
            bars.append(apply_bar(db, rule=rule, value=value,
                                  learnable=learnable[rule.key],
                                  prompted_by=evidence_ref, because=what))
    axes, how = entry_axes(snap, arena)
    try:
        entry = panel.ArenaEntry(
            arena=arena or pod, benchmark_ref=f"{key}/{ref}",
            what_makes_theirs_work="; ".join(m.what for m in mechanisms),
            axes=axes, how=how)
        may = panel.may_enter(entry)
    except panel.PanelRefused as e:
        may = {"may_enter": False, "arena": arena or pod, "why": str(e)}
    may = {**may, "axes_claimed": list(axes), "how": how}
    # #227: the objective checked is the one the downstream work is actually briefed with --
    # the breakthrough tournament's own brief when one is justified, otherwise the same-arena
    # response objective built from the axes above -- never a default string written to pass.
    if objective is None:
        if tournament["decision"] == mech.TOURNAMENT and arena:
            from ..creative import breakthrough as _bt
            objective = _bt.release_brief(db, arena=arena, pod=pod,
                                          listing_ref=ref)["objective"]
        else:
            objective = same_arena_objective(arena or pod, axes, how)
    try:
        ceiling = panel.ceiling_check(objective=objective)
    except panel.PanelRefused as e:
        ceiling = {"permitted": False, "objective": objective, "why": str(e)}
    entered = bool(arena) and proven and may["may_enter"] and ceiling["permitted"]
    steps["panel"] = {"panel_state": pstate, "learnable": learnable, "bar": bars,
                      "may_enter": may, "ceiling": ceiling, "entered": entered}

    # -- 4. pods.lesson (#217) ----------------------------------------------------------
    lessons, refused = [], []
    for rule, what, _v in present:
        try:
            le = pods.lesson(pod, rule.pod_mechanism, f"{what}: {rule.effect}",
                             evidence_ref=evidence_ref)
            lessons.append({**le.to_dict(), "rule": rule.key})
        except pods.MechanismRefused as e:
            refused.append({"rule": rule.key, "why": str(e)})
    steps["lessons"] = {"written": lessons, "refused": refused}

    # -- 5. memory.learn (#316) ----------------------------------------------------------
    outcomes = record_outcomes(db, pod=pod, snap=snap, evidence_ref=evidence_ref)
    learned = []
    from ..core.models import PodLesson
    for le in lessons:
        rule = RULE_BY_KEY[le["rule"]]
        subject = f"mjs:{rule.key}"
        with db.session() as s:
            exists = s.scalar(select(PodLesson.id).where(
                PodLesson.pod == pod, PodLesson.subject == subject).limit(1))
        if exists is not None:
            learned.append({"subject": subject, "learned": False, "lesson_id": exists,
                            "why": "already held; seeing it again is repetition, and only "
                                   "the outcome recorded above moves its standing"})
            continue
        try:
            lid = memory.learn(db, pod=pod, subject=subject,
                               statement=_statement(pod, rule, "present"),
                               mechanism=rule.pod_mechanism, origin="observation")
        except (memory.MemoryRefused, pods.MechanismRefused) as e:
            learned.append({"subject": subject, "learned": False, "why": str(e)})
            continue
        _set_detail(db, lid, polarity="present", rule=rule.key, origin_listing=ref,
                    origin_event=event_id, benchmark=key,
                    panel=pstate["is_a_panel"],
                    learnable=learnable.get(rule.key, {}).get("learnable", False),
                    adoptable=rule.adoptable)
        learned.append({"subject": subject, "learned": True, "lesson_id": lid})
    challengers = raise_challengers(db, pod=pod)
    steps["memory"] = {"outcomes": outcomes, "learned": learned, "challengers": challengers,
                       "lesson_ids": sorted({x["lesson_id"] for x in learned
                                             if x.get("lesson_id")}
                                            | {o["lesson_id"] for o in outcomes})}

    # -- 6. coverage.advance (#314) ------------------------------------------------------
    will_tournament = (tournament["decision"] == mech.TOURNAMENT and ceiling["permitted"])
    with db.session() as s:
        gap = s.scalar(select(CoverageGap).where(CoverageGap.benchmark_key == key,
                                                 CoverageGap.pod == pod))
        gap_id, gap_state = (gap.id, gap.state) if gap is not None else (None, None)
    moves = []
    if gap_id is None:
        cov = {"gap": None, "why": ("no coverage gap for this pod: this shop already sells "
                                    "into it, or the scan has not opened one")}
    elif entered or will_tournament:
        why = (f"benchmark listing {ref}: "
               + ("the pod entered the arena" if entered else "a breakthrough tournament "
                  "was justified") + " and concept work starts now")
        try:
            if gap_state == coverage.NOT_PURSUING:
                moves.append(coverage.advance(db, gap_id, coverage.UNCOVERED,
                                              reason=f"reopened by {why}"))
                gap_state = coverage.UNCOVERED
            if gap_state == coverage.UNCOVERED:
                moves.append(coverage.advance(db, gap_id, coverage.CONCEPTING, reason=why))
        except coverage.GapRefused as e:
            moves.append(f"refused: {e}")
        cov = {"gap": gap_id, "from": gap_state, "moves": moves}
    else:
        cov = {"gap": gap_id, "from": gap_state, "moves": [],
               "why": ("left where it is: no work started, because "
                       + ("the arena's demand is not demonstrated" if not proven else
                          may.get("why", "") if not may["may_enter"] else
                          ceiling.get("why", "")))[:400]}
    steps["coverage"] = cov

    # -- 7. the response pipeline (#306, #307, #309) --------------------------------------
    decision = None
    if arena:
        if entered:
            reason = (f"the benchmark demonstrates demand in the {arena} arena "
                      f"({demand.get('favourites')} favourites across {demand['listings']} "
                      f"observed listings) and this shop can enter with "
                      f"{', '.join(may.get('axes') or axes)} beyond parity")
        elif not proven:
            reason = (f"demand in the {arena} arena is not demonstrated: "
                      f"{demand.get('favourites')} favourites across {demand['listings']} "
                      f"observed listings, against the {PROVEN_ARENA_FAVOURITES} this lane "
                      f"requires before entering")
        else:
            reason = ("the arena is proven but entry was refused by the panel gates: "
                      + (may.get("why", "") if not may["may_enter"]
                         else ceiling.get("why", "")))[:600]
        try:
            decision = response.consider_arena(
                arena, enter=entered, reason=reason,
                preserved=characteristics(snap) if entered else (),
                differentiator=(f"{DIFFERENTIATOR}; beyond this listing: {how}"
                                if entered else ""), pod=pod).to_dict()
        except response.ResponseRefused as e:
            decision = {"arena": arena, "enter": False, "refused": str(e)}
            entered = False
    seasonal = seasonal_target(arena, today) if (arena and proven) else None
    seasonalised = None
    if seasonal is not None:
        lenses = season_lenses(seasonal["event"], arena)
        if lenses:
            try:
                seasonalised = response.seasonalise(
                    f"brambleloop-{arena}-{seasonal['event']}", arena, lenses)
            except response.ResponseRefused as e:
                seasonalised = {"complete": False, "refused": str(e)}
    steps["response"] = {"consider_arena": decision, "seasonal_target": seasonal,
                         "seasonalise": seasonalised}

    # -- 8. the breakthrough tournament (#216) ------------------------------------------
    if will_tournament:
        bt = _enqueue_breakthrough(db, enqueue, event_id=event_id, arena=arena or pod,
                                   pod=pod, ref=ref, benchmark_key=key, today=today,
                                   seasonal=seasonal)
    else:
        bt = {"enqueued": False, "job_id": None,
              "why": (tournament["why"] if tournament["decision"] != mech.TOURNAMENT
                      else ceiling.get("why", ""))}
    steps["breakthrough"] = bt

    # -- #309: walk the stages until a gate stops the run ----------------------------------
    run = response.PipelineRun(signal=f"{key}/{ref}@{fp[:12]}")
    tournament_done = False
    if bt.get("job_id"):
        with db.session() as s:
            job = s.get(Job, bt["job_id"])
            tournament_done = job is not None and job.status == JobStatus.DONE
    gates = [
        ("observation", obs_id is not None, evidence_ref),
        ("pod_routing", pod != pods.UNCLASSIFIED, pod),
        ("market_decomposition", bool(mechanisms), f"{len(mechanisms)} mechanism(s)"),
        ("demand_and_season_fit", proven and seasonal is not None,
         f"{demand.get('favourites')} favourites; target "
         f"{(seasonal or {}).get('event', 'none')}"),
        ("seasonal_tournament",
         bool(seasonalised and seasonalised.get("complete")) and tournament_done,
         (f"tournament job {bt.get('job_id')} has not run yet" if bt.get("job_id")
          and not tournament_done else "no seasonal tournament has run")),
    ]
    stopped = None
    for stage, passed, evidence in gates:
        res = run.advance(stage, gate_passed=passed, evidence=str(evidence))
        if not res["advanced"]:
            stopped = {**res, "evidence": str(evidence)}
            break
    pipeline_state = {**run.to_dict(), "stopped": stopped}

    with db.session() as s:
        ev = s.get(MjsMissionEvent, event_id)
        ev.arena = arena
        ev.proven = proven
        ev.decision = tournament["decision"]
        ev.entered = entered
        ev.gap_id = gap_id
        ev.tournament_job_id = bt.get("job_id")
        ev.seasonal = {"target": seasonal, "seasonalise": seasonalised}
        ev.steps = steps
        ev.pipeline = pipeline_state

    return {"event_id": event_id, "listing_ref": ref, "pod": pod, "arena": arena,
            "proven": proven, "decision": tournament["decision"], "entered": entered,
            "tournament_job_id": bt.get("job_id"),
            "seasonal_event": (seasonal or {}).get("event"),
            "pipeline_stopped_at": (stopped or {}).get("stage"),
            "coverage": cov.get("moves")}


def _median(values: list[float]) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    mid = len(ordered) // 2
    return float(ordered[mid]) if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _our_dims(db, pod: str) -> dict:
    """This shop's side of the director's standing for one pod, from its own rows (#211).

    `photography_coverage` is the median count of approved listing images per product in the
    pod -- the same measure the benchmark side uses (images per audited gallery). A pod this
    shop has no product in reads None on every dimension but breadth: no product is not the
    same as no photographs of a product. Size presentation and delivery clarity are read from
    our own drafted listings with the same reader applied to the benchmark.
    """
    from sqlalchemy import select

    from ..core.models import Listing, ListingAsset, Product
    from . import deliverable

    with db.session() as s:
        slugs = [p.slug for p in s.scalars(select(Product))
                 if pods.route(p.slug.replace("-", " ")) == pod]
        images: dict[str, int] = {}
        for a in s.scalars(select(ListingAsset).where(ListingAsset.product_slug.in_(slugs))):
            if a.approved:
                images[a.product_slug] = images.get(a.product_slug, 0) + 1
        listings = [(r.product_slug, r.description or "") for r in s.scalars(
            select(Listing).where(Listing.product_slug.in_(slugs)))]
    sizes, clarity = [], []
    for _slug, desc in listings:
        sr = deliverable.size_range({"description": desc}, pod=pod)
        if sr and sr.get("stated"):
            sizes.append(float(sr.get("sizes") or 0))
        facts = deliverable.read({"description": desc})
        if facts is not None and facts.get("clarity") is not None:
            clarity.append(float(facts["clarity"]))
    return {"catalogue_breadth": float(len(slugs)),
            "photography_coverage": (_median([float(images.get(sl, 0)) for sl in slugs])
                                     if slugs else None),
            "size_presentation": _median(sizes),
            "delivery_format": _median(clarity),
            "_slugs": slugs}


def _their_dims(db, pod: str, key: str | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    with db.session() as s:
        stmt = select(BenchmarkListing).where(BenchmarkListing.pod == pod,
                                              BenchmarkListing.audit_state != "withdrawn")
        if key:
            stmt = stmt.where(BenchmarkListing.benchmark_key == key)
        theirs = list(s.scalars(stmt))
        s.expunge_all()
    audited = [float(r.media_count or 0) for r in theirs
               if (r.detail or {}).get("gallery_audited")]
    sizes = [float((r.detail or {}).get("size_range", {}).get("sizes") or 0) for r in theirs
             if ((r.detail or {}).get("size_range") or {}).get("stated")]
    clarity = [float(((r.detail or {}).get("deliverable") or {}).get("clarity"))
               for r in theirs
               if ((r.detail or {}).get("deliverable") or {}).get("clarity") is not None]
    return {"catalogue_breadth": float(len(theirs)),
            "photography_coverage": _median(audited),
            "size_presentation": _median(sizes),
            "delivery_format": _median(clarity)}


def _standing(db, director: pods.Director, *, key: str, pod: str) -> dict:
    """The company-level view for one pod, from rows (#211). Unknown where unmeasured."""
    ours = _our_dims(db, pod)
    theirs = _their_dims(db, pod, key)
    return director.standing({k: v for k, v in ours.items() if not k.startswith("_")},
                             theirs)


COMPANY_STANDING_KIND = "mjs.company_standing"
# Products per run the director sends for photography when the company is behind there.
PHOTOGRAPHY_REQUESTS_PER_RUN = 3


def company_standing(db, *, enqueue: Callable | None = None,
                     today: date | None = None) -> dict:
    """The director's company-level view: ahead, parity or behind per dimension (#211).

    Aggregated across every pod the benchmark panel sells into (all observed sellers, so a
    second elite seller widens the view rather than being ignored), persisted once per day as
    an `OperatingReading`, and acted on: a pod where the company has products and is behind
    on photography coverage has those products queued for owned photography, so being behind
    is a job rather than a sentence. `unknown` is never counted as parity.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, OperatingReading
    from ..swarm.orchestrate import priority_for

    today = today or datetime.now(timezone.utc).date()
    with db.session() as s:
        pod_keys = sorted({p for (p,) in s.execute(select(BenchmarkListing.pod).distinct())
                           if p and p in pods.POD_KEYS and p != pods.UNCLASSIFIED})
    director = pods.Director()
    per_pod: dict[str, dict] = {}
    summary = {d: {pods.AHEAD: [], pods.PARITY: [], pods.BEHIND: [], pods.UNKNOWN: []}
               for d in pods.DIMENSIONS}
    behind_photography: list[tuple[str, list[str]]] = []
    for pod in pod_keys:
        ours = _our_dims(db, pod)
        theirs = _their_dims(db, pod)
        standing = director.standing({k: v for k, v in ours.items() if not k.startswith("_")},
                                     theirs)
        per_pod[pod] = {"standing": standing,
                        "ours": {k: v for k, v in ours.items() if not k.startswith("_")},
                        "theirs": theirs}
        for dim, pos in standing.items():
            summary[dim][pos].append(pod)
        if standing["photography_coverage"] == pods.BEHIND and ours["_slugs"]:
            behind_photography.append((pod, ours["_slugs"]))

    requested: list[dict] = []
    if enqueue is not None:
        for pod, slugs in behind_photography:
            for slug in slugs:
                if len(requested) >= PHOTOGRAPHY_REQUESTS_PER_RUN:
                    break
                job = enqueue("publishing", "assets.owned_photography",
                              {"slug": slug, "requested_by": "mjs.director",
                               "because": f"behind the benchmark on photography coverage "
                                          f"in {pod}"},
                              priority=priority_for("assets.owned_photography"),
                              idempotency_key=f"director.photography:{slug}:{today}")
                requested.append({"pod": pod, "slug": slug,
                                  "job_id": job.id if job is not None else None})

    counts = {d: {pos: len(v) for pos, v in by.items()} for d, by in summary.items()}
    payload = {"as_of": today.isoformat(), "pods": per_pod, "summary": summary,
               "counts": counts, "photography_requested": requested,
               "note": ("ahead/parity/behind per concrete dimension against every observed "
                        "benchmark seller; unknown where either side has no evidence, never "
                        "parity. A position is not permission to copy protected expression")}
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == COMPANY_STANDING_KIND,
            OperatingReading.period_key == today.isoformat()))
        if row is None:
            s.add(OperatingReading(kind=COMPANY_STANDING_KIND, period_key=today.isoformat(),
                                   payload=payload))
        else:
            row.payload = payload
    return payload


# ---------------------------------------------------------------------------
# #215: the same-arena lane, consumed

SAME_ARENA_LANE = "same_arena"


def consume_concepting(db, *, enqueue: Callable, today: date | None = None,
                       limit: int = 3) -> dict:
    """Start the original same-arena design for every CONCEPTING gap nobody has started (#215).

    `coverage.advance` moves a gap to CONCEPTING when a pod enters an arena; until this
    existed nothing read that state, so "entered" was a label. Each such gap now gets a
    `creative.tournament` in the same arena, briefed with what makes the benchmark compelling,
    the axes this shop enters on and the objective #227 checked -- or, where the entry event
    already queued a breakthrough tournament, that job is recorded as the gap's design work.
    The job id is written on the gap, so a gap is started exactly once.
    """
    from sqlalchemy import desc, select
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.models import CoverageGap, MjsMissionEvent
    from ..creative import breakthrough
    from ..swarm.orchestrate import priority_for

    today = today or datetime.now(timezone.utc).date()
    started, skipped = [], []
    with db.session() as s:
        gaps = [(g.id, g.benchmark_key, g.arena, g.pod, dict(g.evidence or {}))
                for g in s.scalars(select(CoverageGap).where(
                    CoverageGap.state == coverage.CONCEPTING))]
    # #210: the pods' own opportunity maps decide which gap's design starts first.
    priority = _pod_priority(db)
    gaps.sort(key=lambda g: (0 if g[3] in priority else 1, -priority.get(g[3], 0.0), g[0]))
    for gap_id, key, _arena, pod, evidence in gaps:
        if evidence.get("design_job_id"):
            continue
        if len(started) >= limit:
            skipped.append({"gap": gap_id, "why": "run limit; picked up next run"})
            continue
        with db.session() as s:
            ev = s.scalar(select(MjsMissionEvent).where(
                MjsMissionEvent.gap_id == gap_id, MjsMissionEvent.entered == True)  # noqa: E712
                .order_by(desc(MjsMissionEvent.id)).limit(1))
            if ev is None:
                ev = s.scalar(select(MjsMissionEvent).where(
                    MjsMissionEvent.gap_id == gap_id,
                    MjsMissionEvent.tournament_job_id.is_not(None))
                    .order_by(desc(MjsMissionEvent.id)).limit(1))
            info = None if ev is None else {
                "id": ev.id, "arena": ev.arena, "ref": ev.listing_ref,
                "job": ev.tournament_job_id, "steps": dict(ev.steps or {})}
        if info is None:
            skipped.append({"gap": gap_id, "why": "no entry event names this gap"})
            continue
        panel_step = info["steps"].get("panel") or {}
        may = panel_step.get("may_enter") or {}
        if info["job"]:
            job_id, how = info["job"], "breakthrough tournament queued by the entry event"
        else:
            arena = info["arena"] or pod
            inputs = breakthrough.release_brief(db, arena=arena, pod=pod,
                                                listing_ref=info["ref"])
            objective = (panel_step.get("ceiling") or {}).get("objective") or \
                same_arena_objective(arena, tuple(may.get("axes") or ()), may.get("how", ""))
            inputs.update({
                "lane": SAME_ARENA_LANE, "mjs_event_id": info["id"], "gap_id": gap_id,
                "objective": objective, "entry_axes": list(may.get("axes") or []),
                "entry_how": may.get("how", ""),
                "what_makes_theirs_work": "; ".join(
                    m.get("what", "") for m in
                    (info["steps"].get("decomposition") or {}).get("mechanisms") or [])[:600]})
            job = enqueue("creative_director", "creative.tournament", inputs,
                          priority=priority_for("creative.tournament"),
                          idempotency_key=f"same_arena:{key}:{gap_id}")
            if job is None:
                skipped.append({"gap": gap_id, "why": "already queued"})
                continue
            job_id, how = job.id, "same-arena tournament queued from the CONCEPTING gap"
        with db.session() as s:
            g = s.get(CoverageGap, gap_id)
            g.evidence = {**(g.evidence or {}), "design_job_id": job_id,
                          "design_started_on": today.isoformat(), "design_how": how}
            flag_modified(g, "evidence")
        started.append({"gap": gap_id, "job_id": job_id, "how": how})
    return {"started": started, "skipped": skipped}


def seeded_director(db, *, benchmark_key: str = benchmarks.MJS_KEY) -> pods.Director:
    """A Director that already knows every listing version the mission has processed."""
    from sqlalchemy import select

    from ..core.models import MjsMissionEvent

    with db.session() as s:
        seen = {e.event_fingerprint for e in s.scalars(select(MjsMissionEvent).where(
            MjsMissionEvent.benchmark_key == benchmark_key)) if e.event_fingerprint}
    return pods.Director(seen=set(seen))


def process(db, *, enqueue: Callable, today: date | None = None,
            benchmark_key: str = benchmarks.MJS_KEY, limit: int = 25,
            objective: str | None = None) -> dict:
    """Run the eight steps for every pending listing, and report the whole-company view."""
    today = today or datetime.now(timezone.utc).date()
    items = pending(db, benchmark_key=benchmark_key)
    director = seeded_director(db, benchmark_key=benchmark_key)
    ours = our_mechanisms(db)
    done = []
    for item in items[:limit]:
        out = process_listing(db, item, director=director, enqueue=enqueue, today=today,
                              ours=ours, objective=objective)
        if out is not None:
            done.append(out)
    return {"pending": len(items), "processed": len(done), "deferred": max(0,
            len(items) - limit), "events": done,
            "cross_category": cross_category(db),
            "our_mechanisms": ours}


def cross_category(db) -> list[dict]:
    """Mechanisms held by two or more pods -- what siloed cells cannot see (#211)."""
    from sqlalchemy import select

    from ..core.models import PodLesson

    with db.session() as s:
        rows = [(r.pod, r.mechanism) for r in s.scalars(select(PodLesson).where(
            PodLesson.active == True, PodLesson.origin == "observation"))]  # noqa: E712
    lessons = [pods.Lesson(pod=p, mechanism=m, note="held") for p, m in rows
               if m in pods.MECHANISMS]
    return pods.Director.cross_category(lessons)


# ---------------------------------------------------------------------------
# #206: the benchmark URL, checked on a cadence


def benchmark_health(db, *, fetch: Callable | None = None,
                     env: dict[str, str] | None = None,
                     reader_factory: Callable | None = None) -> dict:
    """Resolve every registered benchmark and record the result; never re-point to a stranger.

    With no proven fetch capability every benchmark reads `unverified`, which is the honest
    state. `wrong_shop` and `unreachable` open an incident; a healthy or moved result closes
    it. `record_resolution` follows a move and ignores a wrong shop.
    """
    from ..ops import incident_lifecycle as lifecycle

    fetch = fetch if fetch is not None else benchmarks.fetcher_for(db, env)
    # With no rendered-page capability, the sanctioned read API answers the same question
    # (C-40): findShops by exact name and the shop URL Etsy reports. Still `unverified` with
    # no credential; never `healthy` unchecked.
    reader = None
    if fetch is None and reader_factory is not None:
        reader = reader_factory()
    elif fetch is None:
        from ..integrations.http import UrllibTransport
        from .etsy_public import PublicReader, ReadCredential
        if ReadCredential.from_env(env) is not None:
            reader = PublicReader(UrllibTransport(), env=env)
    results, problems = [], {}
    for spec in benchmarks.REGISTRY:
        res = (benchmarks.api_resolve(spec, reader) if reader is not None
               else benchmarks.resolve(spec, fetch))
        benchmarks.record_resolution(db, res)
        results.append(res.to_dict())
        if res.state in (benchmarks.WRONG_SHOP, benchmarks.UNREACHABLE):
            problems[f"benchmark.url_health:{spec.key}"] = res
    with db.session() as s:
        life = lifecycle.reconcile(
            s, "benchmark.url_health:",
            lambda row: row.signature in problems,
            resolution="the benchmark URL resolves to the named shop again")
        opened = []
        for signature, res in problems.items():
            _row, new = lifecycle.open_or_restate(
                s, signature=signature, severity="P3",
                summary=(f"{res.key}: the benchmark URL is {res.state} ({res.problem}). The "
                         f"registry is not re-pointed at anybody else; a different seller "
                         f"is a different benchmark and needs the owner (#206)."),
                detail=res.to_dict())
            if new:
                opened.append(signature)
    return {"checked": len(results), "results": results,
            "capability": ("fetcher" if fetch is not None else
                           "etsy_api" if reader is not None else "unverified"),
            "incidents_opened": opened, "incidents_resolved": life["resolved"]}


# ---------------------------------------------------------------------------
# #226: pod capability, computed from rows


def pod_capability(db) -> dict:
    """Discernment and creativity per pod, from the rows the mission writes (#226).

    Records: interpretations learned (new mechanisms), challengers, superseded
    interpretations (category mistakes), benchmark events (current benchmarks), coverage
    outcomes and owner vetoes (responses). Judgements: every tournament call a pod made,
    settled only when its arena's gap reached a verdict. Responses: every arena the pod
    entered, with the axes it entered on. Unmeasured halves stay unmeasured.
    """
    from sqlalchemy import select

    from ..core.models import (
        CoverageGap, MjsMissionEvent, OwnerVeto, PodCapabilityReading, PodLesson,
    )
    from . import pod_learning as pl

    with db.session() as s:
        lessons = list(s.scalars(select(PodLesson)))
        events = list(s.scalars(select(MjsMissionEvent)))
        gaps = {g.id: g for g in s.scalars(select(CoverageGap))}
        vetoes = list(s.scalars(select(OwnerVeto).where(OwnerVeto.owner_vetoed == True)))  # noqa: E712
        records: list = []
        judgements: list = []
        responses: dict[str, list] = {}
        for le in lessons:
            if le.pod not in pods.POD_KEYS:
                continue
            kind = (pl.CHALLENGER_STRATEGY if le.origin == "challenger" else
                    pl.CATEGORY_MISTAKE if le.superseded_by else pl.NEW_MECHANISM)
            records.append(pl.Record(pod=le.pod, kind=kind, subject=le.subject,
                                     evidence_ref=f"pod_lesson:{le.id}"))
        event_pod = {}
        for ev in events:
            if ev.pod not in pods.POD_KEYS:
                continue
            event_pod[ev.id] = ev.pod
            records.append(pl.Record(pod=ev.pod, kind=pl.CURRENT_BENCHMARK,
                                     subject=ev.listing_ref,
                                     evidence_ref=f"mjs_event:{ev.id}"))
            gap = gaps.get(ev.gap_id) if ev.gap_id else None
            worked = None
            if gap is not None and gap.state == coverage.VALIDATED_WINNER:
                worked = True
            elif gap is not None and gap.state == coverage.NOT_PURSUING and gap.product_slug:
                worked = False
            if ev.decision:
                judgements.append(pl.Judgement(
                    pod=ev.pod, subject=ev.listing_ref,
                    predicted_worth_doing=ev.decision == mech.TOURNAMENT,
                    outcome_worked=worked))
            if ev.entered:
                responses.setdefault(ev.pod, []).append(
                    {"subject": ev.listing_ref,
                     "axes": list(((ev.steps or {}).get("panel") or {})
                                  .get("may_enter", {}).get("axes") or [])})
        for g in gaps.values():
            if g.pod not in pods.POD_KEYS:
                continue
            if g.state in (coverage.LAUNCHED, coverage.VALIDATED_WINNER):
                records.append(pl.Record(pod=g.pod, kind=pl.SUCCESSFUL_RESPONSE,
                                         subject=g.arena, evidence_ref=f"coverage_gap:{g.id}"))
            elif g.state == coverage.NOT_PURSUING and g.product_slug:
                records.append(pl.Record(pod=g.pod, kind=pl.FAILED_RESPONSE,
                                         subject=g.arena, evidence_ref=f"coverage_gap:{g.id}"))
        for v in vetoes:
            if v.subject_ref.startswith("mjs_event:"):
                try:
                    pod = event_pod.get(int(v.subject_ref.split(":", 1)[1]))
                except ValueError:
                    pod = None
                if pod:
                    records.append(pl.Record(pod=pod, kind=pl.FAILED_RESPONSE,
                                             subject=v.reason,
                                             evidence_ref=f"owner_veto:{v.id}"))

        touched = sorted({r.pod for r in records} | {j.pod for j in judgements})
        readings = {}
        for pod in touched:
            cap = pl.capability(pod, judgements=judgements,
                                responses=responses.get(pod, []), records=records)
            s.add(PodCapabilityReading(pod=pod, measured=cap["measured"],
                                       discernment=cap["discernment"],
                                       creativity=cap["creativity"],
                                       balance=cap["memory_balance"],
                                       detail={"why": cap["why"],
                                               "stale_after_hours": cap["stale_after_hours"]}))
            readings[pod] = {"measured": cap["measured"],
                             "discernment": cap["discernment"]["reading"],
                             "creativity": cap["creativity"]["reading"],
                             "balance": cap["memory_balance"]["reading"]}
    return {"pods": readings, "records": len(records), "judgements": len(judgements),
            "note": ("computed from pod lessons, mission events, coverage outcomes and "
                     "owner vetoes; a half with too little evidence reads unmeasured")}


# ---------------------------------------------------------------------------
# #210: each pod's own opportunity map, persisted and read

POD_MAPS_KIND = "mjs.pod_maps"


def pod_maps(db, *, today: date | None = None) -> dict:
    """Every specialist cell's category history, rubric, opportunity map and lessons (#210).

    Built from rows: observed depth and forms, the arbitrage card's weakness opening and
    market score, image evidence from judged galleries (`vision.by_pod`, which says "empty"
    rather than implying a quiet department when nothing is judged), the pod's open coverage
    gaps, its held lessons and its newest capability reading. Persisted daily as an
    `OperatingReading`; `consume_concepting` reads it to decide which pod's same-arena design
    starts first, so the map changes what happens next rather than describing it.
    """
    from sqlalchemy import desc, select

    from ..core.models import (
        BenchmarkListing, CoverageGap, OperatingReading, PodCapabilityReading, PodLesson,
    )
    from ..creative import prospecting
    from ..radar import arbitrage
    from . import vision

    today = today or datetime.now(timezone.utc).date()
    steer = arbitrage.steering(db)
    images = vision.by_pod(db)
    maps: dict[str, dict] = {}
    with db.session() as s:
        depth: dict[str, int] = {}
        for r in s.scalars(select(BenchmarkListing).where(
                BenchmarkListing.audit_state != "withdrawn")):
            if r.pod and r.pod in pods.POD_KEYS and r.pod != pods.UNCLASSIFIED:
                depth[r.pod] = depth.get(r.pod, 0) + 1
        gaps = [(g.pod, g.arena, g.state) for g in s.scalars(select(CoverageGap))]
        lessons = [(le.pod, le.mechanism, le.active) for le in s.scalars(select(PodLesson))]
        latest = {}
        for r in s.scalars(select(PodCapabilityReading).order_by(desc(PodCapabilityReading.id))):
            latest.setdefault(r.pod, r)
        caps = {p: {"measured": r.measured, "discernment": (r.discernment or {}).get("reading"),
                    "creativity": (r.creativity or {}).get("reading")}
                for p, r in latest.items()}
    for pod in sorted(depth):
        spec = pods.BY_KEY.get(pod)
        hunt = arbitrage.weakness_hunt(db, pod=pod)
        maps[pod] = {
            "history": {"observed_listings": depth[pod],
                        "forms": prospecting.arena_forms(db, pod).get("forms") or {}},
            "rubric": list(spec.rubric) if spec else [],
            "opportunity": {
                "market_score": (steer.get(pod) or {}).get("score"),
                "weakness_opening": arbitrage._opportunity(hunt),  # noqa: SLF001
                "image_evidence": images.get(pod, {"state": "no listing observed"}),
                "open_gaps": [{"arena": a, "state": st} for p, a, st in gaps if p == pod],
            },
            "lessons": {"held": sum(1 for p, _m, act in lessons if p == pod and act),
                        "mechanisms": sorted({m for p, m, act in lessons if p == pod and act})},
            "capability": caps.get(pod, {"measured": False}),
        }
    payload = {"as_of": today.isoformat(), "pods": maps}
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == POD_MAPS_KIND,
            OperatingReading.period_key == today.isoformat()))
        if row is None:
            s.add(OperatingReading(kind=POD_MAPS_KIND, period_key=today.isoformat(),
                                   payload=payload))
        else:
            row.payload = payload
    return payload


def _pod_priority(db) -> dict[str, float]:
    """Each pod's opportunity from its newest persisted map; absent pods sort last."""
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == POD_MAPS_KIND)
            .order_by(desc(OperatingReading.period_key)).limit(1))
        maps = ((row.payload or {}).get("pods") or {}) if row is not None else {}
    out = {}
    for pod, m in maps.items():
        opp = m.get("opportunity") or {}
        vals = [v for v in (opp.get("market_score"), opp.get("weakness_opening"))
                if isinstance(v, (int, float))]
        if vals:
            out[pod] = sum(vals) / len(vals)
    return out


# ---------------------------------------------------------------------------
# #228: the owner's veto, recorded and counted


def record_veto(db, *, subject_ref: str, scope: str, reason: str = "", note: str = "",
                owner_vetoed: bool = True, predicted_veto: bool | None = None,
                predicted_at: datetime | None = None) -> dict:
    """Record one owner ruling, then let the whole veto memory act.

    Repeated reasons become improvement lessons routed through `improve.bus`; a veto on an
    MJs-derived proposal (`mjs_event:<id>`) is an `owner_veto` outcome against every pod
    interpretation that proposal was built on. Alignment is reported and never retires the
    veto by argument.
    """
    from sqlalchemy import select

    from ..core.models import MjsMissionEvent, OwnerVeto
    from ..improve import bus
    from . import veto

    now = datetime.now(timezone.utc)
    if not subject_ref.strip():
        raise veto.VetoRefused("a ruling names the proposal it is about")
    if owner_vetoed:
        veto.Veto(subject_ref=subject_ref, scope=scope, reason=reason, note=note, at=now)
    elif scope not in veto.VETO_SCOPE:
        raise veto.VetoRefused(f"{scope!r} is not within the owner's veto")
    if predicted_veto is not None:
        if predicted_at is None:
            raise veto.VetoRefused("a prediction is dated, or it cannot be shown to precede "
                                   "the ruling")
        if predicted_at.tzinfo is None:
            predicted_at = predicted_at.replace(tzinfo=timezone.utc)
        veto.Prediction(subject_ref=subject_ref, predicted_veto=predicted_veto,
                        owner_vetoed=owner_vetoed, predicted_at=predicted_at,
                        owner_ruled_at=now)

    with db.session() as s:
        row = OwnerVeto(subject_ref=subject_ref, scope=scope,
                        reason=reason if owner_vetoed else "", note=note[:2000],
                        owner_vetoed=owner_vetoed, predicted_veto=predicted_veto,
                        predicted_at=predicted_at, at=now)
        s.add(row)
        s.flush()
        veto_id = row.id

    state = veto_state(db)
    published = []
    for finding in state["memory"]["findings"]:
        lesson_id = bus.publish(
            db, origin_cell="quality", subject="creative_rejection",
            statement=(f"The owner has refused {finding['count']} flagship proposals for "
                       f"{finding['reason']!r} ({finding['means']}); the automated "
                       f"evaluator does not yet know what the owner means by it and is to "
                       f"be retrained on these rulings"),
            evidence_ref=f"owner_veto_finding:{finding['reason']}")
        published.append({"reason": finding["reason"], "lesson_id": lesson_id})

    contradicted = []
    if owner_vetoed and subject_ref.startswith("mjs_event:"):
        try:
            event_id = int(subject_ref.split(":", 1)[1])
        except ValueError:
            event_id = None
        with db.session() as s:
            ev = s.get(MjsMissionEvent, event_id) if event_id else None
            lesson_ids = list(((ev.steps or {}).get("memory") or {}).get("lesson_ids") or []) \
                if ev is not None else []
        for lid in lesson_ids:
            contradicted.append(memory.outcome(db, int(lid), "owner_veto",
                                               evidence_ref=f"owner_veto:{veto_id}"))
    return {"recorded": veto_id, "memory": state["memory"], "alignment": state["alignment"],
            "lessons_published": published, "pod_lessons_contradicted": contradicted}


def veto_state(db) -> dict:
    """`veto.memory` and `veto.alignment` over the recorded rulings."""
    from sqlalchemy import select

    from ..core.models import OwnerVeto
    from . import veto

    def _aware(v):
        return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)

    with db.session() as s:
        rows = list(s.scalars(select(OwnerVeto).order_by(OwnerVeto.id)))
        vetoes = [veto.Veto(subject_ref=r.subject_ref, scope=r.scope, reason=r.reason,
                            note=r.note or "", at=_aware(r.at))
                  for r in rows if r.owner_vetoed and r.reason in veto.REASONS
                  and r.scope in veto.VETO_SCOPE]
        predictions = []
        for r in rows:
            if r.predicted_veto is None or r.predicted_at is None:
                continue
            try:
                predictions.append(veto.Prediction(
                    subject_ref=r.subject_ref, predicted_veto=bool(r.predicted_veto),
                    owner_vetoed=bool(r.owner_vetoed), predicted_at=_aware(r.predicted_at),
                    owner_ruled_at=_aware(r.at)))
            except veto.VetoRefused:
                continue
    return {"rulings": len(rows), "memory": veto.memory(vetoes),
            "alignment": veto.alignment(predictions)}


# ---------------------------------------------------------------------------
# #311: the deadline sentinel for MJs-derived opportunities


def seasonal_sentinel(db, *, today: date | None = None) -> dict:
    """Days to preferred and latest launch for every MJs-derived seasonal opportunity.

    At risk: a correlated P2 per event, and the opportunity's queued work is moved to the
    seasonal-deadline band -- or queued there if nothing is -- because this is the window
    where reallocating effort still changes the outcome. Missed: never an incident (#297
    decided what happens to those); the recommendation is recorded, simplification is
    offered only where a CIR exists to prove the simpler product true, and otherwise the
    opportunity is deferred to the next event a customer can still finish it for.
    """
    from sqlalchemy import select

    from ..core.models import Job, JobStatus, MjsMissionEvent
    from ..ops import incident_lifecycle as lifecycle
    from ..seasonal.leadtime import (
        AT_RISK, MISSED, SIMPLIFY, compile_launch,
    )
    from ..swarm.orchestrate import priority_for

    today = today or datetime.now(timezone.utc).date()
    seasonal_band = priority_for("mjs.seasonal_sentinel")
    rows_out, at_risk_by_event = [], {}
    with db.session() as s:
        events = list(s.scalars(select(MjsMissionEvent).where(
            MjsMissionEvent.entered == True)))  # noqa: E712
        for ev in events:
            target = (ev.seasonal or {}).get("target")
            if not target or not ev.arena:
                continue
            plan = compile_launch(target["event"], date.fromisoformat(target["event_date"]),
                                  make_hours=float(target["make_hours"]))
            status = plan.status(today)
            action, because = plan.recommendation(today)
            row = {"event_id": ev.id, "arena": ev.arena, "pod": ev.pod,
                   "event": target["event"], "event_date": target["event_date"],
                   "status": status, "days_to_preferred": plan.days_to_preferred(today),
                   "days_to_latest": plan.days_to_latest(today),
                   "recommendation": action, "because": because, "reallocated": []}
            if status == AT_RISK:
                at_risk_by_event.setdefault(
                    f"mjs.seasonal_at_risk:{target['event']}:{target['event_date'][:4]}",
                    []).append(row)
                jobs = [j for j in s.scalars(select(Job).where(
                    Job.status == JobStatus.PENDING))
                    if (j.inputs or {}).get("mjs_event_id") == ev.id]
                for j in jobs:
                    if j.priority > seasonal_band:
                        row["reallocated"].append({"job_id": j.id, "from": j.priority,
                                                   "to": seasonal_band})
                        j.priority = seasonal_band
                if not jobs and not ev.tournament_job_id:
                    row["reallocated"].append({"queue": "creative.tournament",
                                               "priority": seasonal_band})
            elif status == MISSED:
                # Simplify only when product truth permits: with no CIR there is no simpler
                # product anybody can prove true, so the opportunity defers.
                if action == SIMPLIFY:
                    row["recommendation"] = "defer_to_next_season"
                    row["because"] = ("a simpler quick-make needs a CIR to be proven true, "
                                      "and none exists for this opportunity yet; " + because)
                nxt = seasonal_target(ev.arena, today)
                ev.seasonal = {**(ev.seasonal or {}), "target": nxt,
                               "deferred_from": target}
                row["deferred_to"] = (nxt or {}).get("event")
            ev.sentinel = {**row, "as_of": today.isoformat()}
            rows_out.append(row)

        life = lifecycle.reconcile(
            s, "mjs.seasonal_at_risk:", lambda inc: inc.signature in at_risk_by_event,
            resolution="no MJs-derived opportunity for this event is at risk any longer")
        opened = []
        for signature, rows in at_risk_by_event.items():
            _row, new = lifecycle.open_or_restate(
                s, signature=signature, severity="P2",
                summary=(f"{len(rows)} MJs-derived opportunity(ies) for "
                         f"{rows[0]['event']} are past their preferred launch with "
                         f"{min(r['days_to_latest'] for r in rows)} day(s) to the latest "
                         f"viable launch; their queued work was moved to the seasonal "
                         f"band (#311)."),
                detail={"opportunities": rows[:20], "as_of": today.isoformat()})
            if new:
                opened.append(signature)

    return {"as_of": today.isoformat(), "opportunities": len(rows_out),
            "counts": {st: sum(1 for r in rows_out if r["status"] == st)
                       for st in ("on_track", "past_preferred", "at_risk", "missed")},
            "rows": rows_out, "incidents_opened": opened,
            "incidents_resolved": life["resolved"],
            "needs_tournament": [r["event_id"] for r in rows_out
                                 if any(x.get("queue") for x in r["reallocated"])]}
