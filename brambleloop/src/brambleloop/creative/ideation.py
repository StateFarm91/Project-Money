"""The ideation plan: every input a tournament or expedition must consume, read from the database.

Requirements 85, 101, 105, 117, 118, 119, 120, 121, 122, 124, 142, 232. Each of them had a
library that was tested and a runtime that never called it: lessons were persisted and read
only by an API route, the universe had cells nobody generated against, saturation and the
creative floor were functions with no caller. This module is the one place the ideation
handlers (`creative.tournament`, `creative.expedition`) assemble those inputs, and the one
place their consequences are applied to the field:

- **before generation** (`plan`): lessons and the creative reference brief (#85, #101),
  the universe cells to brief against (#105), franchise-free themes (#142), non-holiday
  occasions (#122), the current four-season programme (#121), white-space hypotheses (#118),
  saturation of each form with the angle that permits entry or the exclusion that forbids it
  (#117), a mechanism transferred from another holiday (#120), the portfolio role the field is
  aimed at (#232) and the moving creativity floor (#124);
- **during generation** (`BriefingGateway`): each model call's brief carries one rotation of
  those constraints, and the gateway records what it asked, so the audit row proves the model
  was asked against a cell rather than a keyword;
- **after generation** (`select`): the floor cuts survivors below it, per-axis diversity
  quotas defer survivors that would let one value dominate (#119), the winner is the best
  survivor whose make lane fits the role, and it is presented to the pre-engineering gate.

Everything returned is JSON-safe and lands in the run's audit row under `ideation`, which is
what lets a test prove that the runtime consumed each input rather than that a library exists.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from . import discovery, standard, universe

# The audit actions this module reads. The two ideation actions are the runs themselves; the
# other two are the standing agents' latest outputs.
TOURNAMENT_ACTION = "creative.tournament"
EXPEDITION_ACTION = "creative.expedition"
WHITE_SPACE_ACTION = "creative.white_space"
PROGRAMME_ACTION = "creative.four_season"

# How many prior ideation rows the floor and the transfer evidence are read from. The floor's
# own cohort is `standard.COHORT_SIZE` survivors; rows are read generously so a run of empty
# tournaments does not starve the cohort.
HISTORY_ROWS = 40

# How many lessons a brief carries into the prompt. The provenance row records every lesson
# the brief was assembled with; the prompt carries the most recent few, because a prompt that
# quotes forty lessons is a prompt nobody can read the answer to.
LESSONS_IN_PROMPT = 4

# Which franchise-free territories (#142) each occasion's ideation draws on. A territory is an
# emotion, so several occasions share one; an occasion absent here draws on the evergreen ones.
THEME_OCCASIONS: dict[str, tuple[str, ...]] = {
    "christmas": ("magical_childhood_christmas", "retro_toy_shop_winter",
                  "chaotic_family_holiday", "over_the_top_decorating", "awkward_relatives",
                  "winter_road_trip", "office_holiday_party", "cozy_movie_night"),
    "halloween": ("spooky_cute_halloween", "over_the_top_decorating", "cozy_movie_night",
                  "chaotic_family_holiday"),
    "valentines": ("romantic_comedy_valentine", "cozy_movie_night"),
    "thanksgiving": ("chaotic_family_holiday", "awkward_relatives", "cozy_movie_night"),
}
EVERGREEN_THEMES: tuple[str, ...] = ("chaotic_family_holiday", "cozy_movie_night",
                                     "over_the_top_decorating")


class IdeationRefused(ValueError):
    """An ideation plan that cannot be built honestly."""


# ---------------------------------------------------------------------------
# Reading history


def _rows(db, actions: tuple[str, ...], *, limit: int = HISTORY_ROWS) -> list:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action.in_(
            ("creative.tournament", "creative.expedition", "creative.white_space",
             "creative.four_season")))
            .order_by(desc(AuditLog.id)).limit(limit * 4)))
        # Detached copies: the session closes here and callers only read.
        out = [(r.id, r.action, r.artifact, dict(r.detail or {})) for r in rows
               if r.action in actions]
    return out[:limit]


def _survivor_entries(detail: dict) -> list[dict]:
    # A tournament's research survivors are the ones the jury and catalogue judged; an
    # expedition's `survivors` are the same stage. Final-stage survivors are a subset.
    entries = list(detail.get("research_survivors") or []) or list(detail.get("survivors") or [])
    return [e for e in entries if isinstance(e, dict)]


def _event_of(artifact: str) -> str:
    return (artifact or "").split("/", 1)[0]


def latest(db, action: str) -> dict | None:
    got = _rows(db, (action,), limit=1)
    if not got:
        return None
    row_id, _action, artifact, detail = got[0]
    return {"id": row_id, "artifact": artifact, "detail": detail}


# ---------------------------------------------------------------------------
# The inputs, one function each


def lessons(db, *, kind: str, event: str, pod: str) -> dict:
    """#85, #101: lessons and the creative reference brief, through their public readers."""
    from ..improve.bus import brief_lessons
    from . import benchmark_memory, reference

    memory = brief_lessons(db, artifact=f"ideation:{kind}:{event}/{pod}")
    ref = {"usable": False, "reason": "not read"}
    # #116: the stored decomposition first -- the record the reference cadence wrote -- and
    # the live computation only where none is stored yet.
    stored = reference.stored_decomposition(db, pod)
    if stored and stored.get("primitives"):
        ref = {"usable": True, "primitives": stored["primitives"],
               "reason": f"stored decomposition of {stored.get('as_of')}"}
    else:
        try:
            ref = reference.brief(db, pod)
        except Exception as e:  # noqa: BLE001 - a missing reference is reported, not fatal
            ref = {"usable": False, "reason": f"{type(e).__name__}: {e}"[:200]}
    return {
        "lesson_ids": list(memory["lesson_ids"]),
        "lessons_available": len(memory["lessons"]),
        "in_prompt": [{"id": l["id"], "subject": l["subject"],
                       "statement": str(l["statement"])[:220]}
                      for l in memory["lessons"][:LESSONS_IN_PROMPT]],
        "provenance": memory["provenance"],
        "reference": {"usable": bool(ref.get("usable")),
                      "primitives": ref.get("primitives") or {},
                      "reason": ref.get("reason", "")},
        # #86: the attributes the market is rewarding, from the stored creativity benchmark
        # memory. Empty while the memory is UNMEASURED, and the brief says nothing rather
        # than guessing what sells.
        "market_attributes": benchmark_memory.rewarded(db, pod=pod),
        "state": ("drew on accumulated lessons" if memory["lesson_ids"] else
                  "no lesson recorded yet: this run starts from the company's absence of "
                  "memory, and the provenance row says so (#101)"),
    }


def cells(db, *, occasion: str | None, forms, cycle: int, limit: int = 12) -> dict:
    """#105: the universe cells this run briefs against, unbriefed cells first."""
    if occasion is None or occasion not in universe.UNIVERSE:
        return {"occasion": occasion, "has_universe": False, "cells": [],
                "reason": (f"{occasion!r} has no seasonal universe; this run is briefed "
                           f"from the four-season programme and non-holiday occasions "
                           f"instead of a keyword")}
    wanted = universe.departments_for(occasion, forms)
    all_cells = universe.cells(occasion)
    pool = [c for c in all_cells if c["department"] in wanted] or all_cells
    briefed: set[str] = set()
    for _id, _action, _artifact, detail in _rows(db, (TOURNAMENT_ACTION, EXPEDITION_ACTION)):
        for key in ((detail.get("ideation") or {}).get("cells_briefed") or []):
            briefed.add(key)
    fresh = [c for c in pool if f'{occasion}|{c["department"]}|{c["context"]}' not in briefed]
    ordered = fresh or pool
    start = cycle % len(ordered)
    chosen = (ordered[start:] + ordered[:start])[:limit]
    return {
        "occasion": occasion, "has_universe": True,
        "departments": wanted or sorted(universe.UNIVERSE[occasion]),
        "pool": len(pool), "previously_briefed": len(briefed & {
            f'{occasion}|{c["department"]}|{c["context"]}' for c in pool}),
        "cells": [{"department": c["department"], "context": c["context"],
                   "meaning": c["context_meaning"]} for c in chosen],
    }


def themes(occasion: str | None, *, cycle: int, limit: int = 3) -> list[dict]:
    """#142: the franchise-free territories this run's briefs are written in."""
    from ..culture.translate import THEMES

    keys = [k for k in THEME_OCCASIONS.get(occasion or "", EVERGREEN_THEMES) if k in THEMES]
    start = cycle % len(keys)
    chosen = (keys[start:] + keys[:start])[:limit]
    return [{"key": k, "meaning": THEMES[k]} for k in chosen]


def occasions(*, cycle: int, limit: int = 3) -> list[dict]:
    """#122: the non-holiday occasions this run extends its briefs to, rotating."""
    keys = list(universe.NON_HOLIDAY_OCCASIONS)
    start = (cycle * limit) % len(keys)
    chosen = (keys[start:] + keys[:start])[:limit]
    return [{"key": k, "meaning": universe.NON_HOLIDAY_OCCASIONS[k]} for k in chosen]


def programme_for(today: date, *, cycle: int) -> dict:
    """#121: this cycle's four-season programme, independent of any named holiday."""
    season = universe.season_for(today.month)
    programs = universe.FOUR_SEASON_PROGRAMS[season]
    program = programs[cycle % len(programs)]
    upcoming = universe.next_season(season)
    return {
        "season": season, "program": program,
        "meaning": universe.PROGRAM_MEANING[program],
        "next_season": upcoming,
        "next_program": universe.FOUR_SEASON_PROGRAMS[upcoming][
            cycle % len(universe.FOUR_SEASON_PROGRAMS[upcoming])],
        "between_holidays": universe.between_holidays(season),
    }


def programme(db, *, today: date, cycle: int) -> dict:
    """The standing four-season agent's latest assignment, or this cycle's own if none ran."""
    got = latest(db, PROGRAMME_ACTION)
    if got and (got["detail"].get("season") == universe.season_for(today.month)):
        detail = got["detail"]
        return {"season": detail["season"], "program": detail["program"],
                "meaning": detail.get("meaning", ""),
                "occasion": detail.get("occasion"),
                "source": f"creative.four_season row {got['id']}"}
    own = programme_for(today, cycle=cycle)
    return {"season": own["season"], "program": own["program"], "meaning": own["meaning"],
            "occasion": None, "source": "computed for this cycle (no programme row this season)"}


def white_space(db) -> dict:
    """#118: the white-space agent's latest hypotheses, as this run reads them."""
    got = latest(db, WHITE_SPACE_ACTION)
    if got is None:
        return {"source": None, "minable": False, "hypotheses": [],
                "reason": "the white-space agent has not run"}
    detail = got["detail"]
    return {"source": f"creative.white_space row {got['id']}",
            "minable": bool(detail.get("minable")),
            "hypotheses": [{"complaint_kind": h["complaint_kind"], "proposal": h["proposal"],
                            "support": h.get("support", 0)}
                           for h in (detail.get("hypotheses") or [])][:5],
            "reason": detail.get("reason", "")}


_FORM_WORDS: dict[str, tuple[str, ...]] = {
    "hat": ("hat", "beanie"), "rectangle_throw": ("blanket", "throw"),
    "toy": ("amigurumi", "toy"), "wall_hanging": ("wall hanging",),
    "flat_panel": ("panel",), "round_disc": ("doily", "mat"),
    "fitted_garment": ("sweater", "cardigan"), "draped_garment": ("shawl", "poncho"),
}


def saturation(db, *, event: str, forms, white: dict) -> dict:
    """#117: each form's crowding in observed search results, and whether it may be entered.

    Measured from `SerpSnapshot.total_count` for queries naming both the occasion and the
    form. A form with no such query is UNMEASURED and is not enforced -- absence of a search
    reading is not evidence of open ground. A crowded form may be entered only on a named
    unmet angle, and the only angles admitted here are those the white-space agent mined from
    what buyers said; a crowded form with none is excluded from this run.
    """
    from sqlalchemy import desc, select

    from ..core.models import SerpSnapshot

    event_word = (event or "").lower().split(" ")[0].replace("'s", "")
    with db.session() as s:
        snaps = [(r.query.lower(), r.total_count) for r in s.scalars(
            select(SerpSnapshot).order_by(desc(SerpSnapshot.captured_at),
                                          desc(SerpSnapshot.id)).limit(500))]
    angles = []
    for h in white.get("hypotheses") or []:
        kind = discovery.COMPLAINT_ANGLE.get(h["complaint_kind"])
        if kind:
            angles.append((kind, h))

    archetypes: list[discovery.Archetype] = []
    unmeasured: list[str] = []
    for form in forms:
        words = _FORM_WORDS.get(form, (form.replace("_", " "),))
        counts = [n for q, n in snaps if n is not None and event_word and event_word in q
                  and any(w in q for w in words)]
        if not counts:
            unmeasured.append(form)
            continue
        archetypes.append(discovery.Archetype(key=form, listings=max(counts)))

    report = discovery.saturation(archetypes)
    decisions: dict[str, dict] = {}
    excluded: list[str] = []
    for a in archetypes:
        if not a.crowded:
            decisions[a.key] = discovery.may_enter(a)
            continue
        if not angles:
            excluded.append(a.key)
            try:
                discovery.may_enter(a)
            except discovery.DiscoveryRefused as e:
                decisions[a.key] = {"may_enter": False, "archetype": a.key,
                                    "listings": a.listings, "why": str(e)[:300]}
            continue
        kind, h = angles[0]
        angle = (f"designed so that {discovery.COMPLAINT_KINDS[h['complaint_kind']]} is "
                 f"solved, which {h.get('support', 0)} recorded buyer complaint(s) say the "
                 f"category leaves unsolved")
        decisions[a.key] = discovery.may_enter(a, angle_kind=kind, angle=angle)
    return {
        "measured": [{"form": a.key, "listings": a.listings, "crowded": a.crowded}
                     for a in archetypes],
        "unmeasured": unmeasured,
        "threshold": report["threshold"],
        "decisions": decisions,
        "excluded_forms": excluded,
        "angles": {k: d.get("angle", "") for k, d in decisions.items() if d.get("angle")},
    }


def transfer(db, *, event: str, theme: dict, cycle: int) -> dict:
    """#120: a mechanism carried from another holiday's evidence, with this holiday's theme.

    Evidence is survivors of earlier runs at *other* holidays whose own description exhibits
    a transferable mechanism. With none, the mechanism is an exploratory rotation and says
    so -- a transfer whose source is unmeasured is not presented as learned.
    """
    support: dict[tuple[str, str], int] = {}
    for _id, _action, artifact, detail in _rows(db, (TOURNAMENT_ACTION, EXPEDITION_ACTION)):
        source = _event_of(artifact)
        if not source or source == event:
            continue
        for entry in _survivor_entries(detail):
            text = " ".join(str(entry.get(k) or "") for k in ("title", "premise", "function"))
            for mechanism in discovery.detect_mechanisms(text):
                support[(mechanism, source)] = support.get((mechanism, source), 0) + 1
    theme_text = f'{theme["key"].replace("_", " ")}: {theme["meaning"]}'
    if support:
        (mechanism, source), n = sorted(support.items(),
                                        key=lambda kv: (-kv[1], kv[0]))[0]
        carried = discovery.transfer(mechanism, from_season=source, to_season=event,
                                     original_theme=theme_text)
        return {**carried, "evidence": "measured", "support": n,
                "evidence_basis": (f"{n} surviving concept(s) at {source} exhibit "
                                   f"{mechanism}")}
    mechanism = sorted(discovery.TRANSFERABLE)[cycle % len(discovery.TRANSFERABLE)]
    carried = discovery.transfer(mechanism, from_season="no_recorded_source",
                                 to_season=event, original_theme=theme_text)
    return {**carried, "evidence": "UNMEASURED", "support": 0,
            "evidence_basis": ("no surviving concept at another holiday exhibits a "
                               "transferable mechanism yet; this is an exploratory rotation, "
                               "not a learned transfer")}


def commerce_directives(db, *, today: date | None = None) -> dict:
    """What the daily order readings ask ideation to do (#22, #233): read, never computed here."""
    try:
        from ..commerce.order_readings import directives

        return directives(db, today=today)
    except Exception as exc:  # noqa: BLE001 - a missing reading must not stop ideation
        return {"replication": None, "ladder_gaps": [], "error": str(exc)[:200]}


def role(db) -> dict:
    """#232: the portfolio role this run's winner is created for."""
    from ..growth import mix

    pending = []
    for _id, _action, _artifact, detail in _rows(db, (TOURNAMENT_ACTION, EXPEDITION_ACTION)):
        chosen = ((detail.get("ideation") or {}).get("winner") or {})
        if chosen.get("key") and chosen.get("role"):
            pending.append(chosen["role"])
    return mix.next_role(mix.positions_from_db(db), pending=pending)


def history(db) -> list[standard.Scored]:
    """The trailing cohort the moving floor is derived from: prior survivors' novelty."""
    scored: list[standard.Scored] = []
    for _id, _action, artifact, detail in reversed(
            _rows(db, (TOURNAMENT_ACTION, EXPEDITION_ACTION))):
        for entry in _survivor_entries(detail):
            value = entry.get("novelty_distance")
            if isinstance(value, (int, float)):
                scored.append(standard.Scored(key=str(entry.get("key")), score=float(value),
                                              cohort=artifact or "",
                                              make_lane=str(entry.get("make_lane") or "")))
    return scored


# Which concept forms a culture-engine family can be developed as (#138). The culture engine
# names families (`culture.translate.TRANSLATION_FAMILIES`); the generator is asked per form.
CULTURE_FAMILY_FORMS: dict[str, tuple[str, ...]] = {
    "blanket": ("rectangle_throw",), "stocking": ("stocking",), "ornament": ("ornament",),
    "coaster": ("coaster",), "wreath": ("wreath",), "garland": ("garland",),
    "tableware": ("runner", "coaster"), "amigurumi": ("toy",),
    "wearable": ("hat", "scarf", "fitted_garment", "draped_garment"),
    "bag": ("bag", "pouch"), "pillow": ("pillow",), "nursery": ("rectangle_throw", "toy"),
    "pet": ("toy", "tube"), "kitchen": ("coaster", "tube"), "interactive": ("toy",),
}


def culture(db, forms) -> dict:
    """#138: live culture-engine candidates, as a concept source beside the universe cells.

    A candidate is a translated premise, not a concept: it has no construction, recipient or
    feeling, and inventing those here would be fabricating the fields the jury judges. So a
    candidate is handed to the generator as the thing to develop, and what comes back is an
    ordinary concept that meets the same vocabulary refusals, the same jury and gauntlet, the
    same floor and quotas, and the same pre-engineering gate as every other entrant.
    """
    from ..culture.engine import candidates

    try:
        live = candidates(db, status="candidate")
    except Exception as e:  # noqa: BLE001 - a missing table is reported, not fatal
        return {"available": 0, "matching": [], "reason": f"{type(e).__name__}: {e}"[:200]}
    wanted = set(forms)
    matching = [{"id": c["id"], "slug": c["slug"], "family": c["family"],
                 "premise": str(c["premise"])[:300], "theme": c["theme"], "era": c["era"],
                 "forms": [f for f in CULTURE_FAMILY_FORMS.get(c["family"], ())
                           if f in wanted]}
                for c in live]
    matching = [m for m in matching if m["forms"]]
    return {"available": len(live), "matching": matching[:24],
            "reason": ("" if matching else
                       "no live culture candidate is in a family this arena's forms can "
                       "develop" if live else "the culture engine holds no live candidate")}


def vision(db, pod: str) -> dict:
    """#278: judged competitor photography for this department, as concept evidence.

    Read from `gallery_image_observation` rows the vision pods recorded. With none, the state
    says UNMEASURED and nothing is invented -- absence of a reading is not a reading.
    """
    from .intake import vision_readings

    return vision_readings(db, pod)


SKILL_GAP_ACTION = "radar.skill_gap"


def skill_gap(db) -> dict:
    """#114: the radar's latest measured skill gap for the wave, consumed as a brief."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == SKILL_GAP_ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        if row is None:
            return {"source": None, "missing": [], "over": [],
                    "reason": "the radar has not measured a skill gap in any wave"}
        detail = dict(row.detail or {})
        return {"source": f"radar.skill_gap row {row.id}",
                "missing": list(detail.get("missing") or []),
                "over": list(detail.get("over") or []),
                "brief": detail.get("brief", ""), "as_of": detail.get("as_of")}


def preproduction_interest(db) -> dict:
    """#4: concepts whose pre-production post drew interest a platform reported, as a brief."""
    from ..commerce import preproduction_cycle

    return preproduction_cycle.brief(db)


# ---------------------------------------------------------------------------
# The plan


def plan(db, *, kind: str, event: str, pod: str, forms, cycle: int,
         today: date | None = None) -> dict:
    """Every input this run consumes, read now, before anything is generated."""
    from .prospecting import EVENT_OCCASION

    if kind not in ("tournament", "expedition"):
        raise IdeationRefused(f"{kind!r} is not an ideation run")
    today = today or date.today()
    forms = list(forms)
    occasion = EVENT_OCCASION.get(event)
    white = white_space(db)
    chosen_themes = themes(occasion, cycle=cycle)
    prog = programme(db, today=today, cycle=cycle)
    floor = standard.floor(history(db))
    out = {
        "kind": kind, "event": event, "pod": pod, "occasion": occasion, "cycle": cycle,
        "lessons": lessons(db, kind=kind, event=event, pod=pod),
        "universe": cells(db, occasion=occasion, forms=forms, cycle=cycle),
        "themes": chosen_themes,
        "non_holiday_occasions": occasions(cycle=cycle),
        "four_season": prog,
        "white_space": white,
        "saturation": saturation(db, event=event, forms=forms, white=white),
        "transfer": transfer(db, event=event, theme=chosen_themes[0], cycle=cycle),
        "role": role(db),
        "floor": floor,
        "history": [h.to_dict() for h in history(db)],
        "culture": culture(db, forms),
        "commerce": commerce_directives(db, today=today),
        "vision": vision(db, pod),
        "skill_gap": skill_gap(db),
        "preproduction": preproduction_interest(db),
    }
    out["briefs"] = _rotation(out)
    return out


def _rotation(p: dict) -> list[dict]:
    """One constraint set per model call, walked in order so a field spans the plan."""
    cell_list = p["universe"]["cells"] or [{"department": None, "context": None,
                                            "meaning": None}]
    n = max(len(cell_list), len(p["themes"]), len(p["non_holiday_occasions"]))
    out = []
    for i in range(n):
        cell = cell_list[i % len(cell_list)]
        out.append({
            "cell": (f'{p["occasion"]}|{cell["department"]}|{cell["context"]}'
                     if cell["department"] else None),
            "cell_meaning": cell["meaning"],
            "theme": p["themes"][i % len(p["themes"])]["key"],
            "non_holiday_occasion": p["non_holiday_occasions"][
                i % len(p["non_holiday_occasions"])]["key"],
        })
    return out


def constraints_text(p: dict, index: int) -> tuple[str, dict]:
    """The paragraph appended to call `index`'s brief, and the assignment it carried."""
    from ..culture.translate import THEMES

    b = p["briefs"][index % len(p["briefs"])]
    lines = ["Brambleloop constraints for this batch (design within them; originality is "
             "still required):"]
    if b["cell"]:
        _occ, department, context = b["cell"].split("|")
        lines.append(f"- universe cell: the {department.replace('_', ' ')} department, for "
                     f"{context.replace('_', ' ')} ({b['cell_meaning']})")
    lines.append(f"- franchise-free territory: {b['theme'].replace('_', ' ')} -- "
                 f"{THEMES[b['theme']]}")
    lines.append(f"- also make it work as a {b['non_holiday_occasion'].replace('_', ' ')} "
                 f"gift ({universe.NON_HOLIDAY_OCCASIONS[b['non_holiday_occasion']]}), so it "
                 f"sells after the holiday")
    prog = p["four_season"]
    lines.append(f"- season programme: {prog['season']} / "
                 f"{prog['program'].replace('_', ' ')} ({prog['meaning']})")
    t = p["transfer"]
    lines.append(f"- mechanism to explore (transfer the mechanism, never a design): "
                 f"{t['mechanism'].replace('_', ' ')} -- {t['meaning']}")
    r = p["role"]
    lines.append(f"- portfolio role: {r['role']} -- {r['brief']}")
    for h in p["white_space"]["hypotheses"][:1]:
        lines.append(f"- buyers say: {h['proposal']}")
    seen = p.get("vision") or {}
    if seen.get("judged_images"):
        # #278: what this department's competitor photography was judged to show. Evidence
        # of what sells, never a photograph or a design to reproduce.
        lines.append("- observed in this department's competitor photography (evidence of "
                     "what sells; never copy a photograph or a design): "
                     + "; ".join(f"{k.replace('_', ' ')}: {', '.join(v[:3])}"
                                 for k, v in sorted((seen.get("attributes") or {}).items())
                                 if v)[:600])
    gap = p.get("skill_gap") or {}
    if gap.get("missing"):
        # #114: the radar measured the wave and found a skill level missing.
        lines.append(f"- this seasonal wave is missing {', '.join(gap['missing'])} work; a "
                     f"concept that fills it is preferred")
    if (p.get("preproduction") or {}).get("measured"):
        # #4: interest a platform measured on a concept post before engineering, with the
        # receipt row. Never a number this system wrote.
        from ..commerce.preproduction_cycle import brief_lines

        lines.extend(brief_lines(p["preproduction"]))
    for form, angle in sorted(p["saturation"]["angles"].items()):
        lines.append(f"- if the form is {form.replace('_', ' ')}, enter only on this angle: "
                     f"{angle}")
    bt = p.get("breakthrough")
    if bt:
        # #216: a divergent run triggered by a benchmark release. Each call carries one of the
        # divergent questions, so the field explores away from what was released.
        lines.append(f"- breakthrough objective: {bt.get('objective')}")
        lines.append(f"- diverge from (never reproduce): {bt.get('diverged_from')}")
        qs = bt.get("briefs") or []
        if qs:
            q = qs[index % len(qs)]
            lines.append(f"- divergent question ({q.get('axis')}): {q.get('question')}")
    cd = p.get("commerce") or {}
    study = cd.get("replication")
    # #22: a credible winner's study takes its capacity share of the field -- one call in
    # every round(1/share) -- as adjacent experiments that hold a candidate cause and change
    # the rest. Never a palette clone.
    if study and study.get("capacity_share"):
        every = max(1, round(1 / float(study["capacity_share"])))
        if index % every == 0:
            held = [e["dimension"] for e in (study.get("explanations") or [])[:1]]
            lines.append(
                f"- replication study of {study['winner']} (until {study['ends']}): an "
                f"adjacent experiment that holds {held or 'one of its dimensions'} and changes "
                f"the rest -- never the same product in another palette")
    # #233: a rung of the value ladder with nothing on it is a place a buyer arrives and
    # finds nothing.
    if cd.get("ladder_gaps"):
        gap = cd["ladder_gaps"][index % len(cd["ladder_gaps"])]
        lines.append(f"- value ladder: the {gap.replace('_', ' ')} rung is empty; a concept "
                     f"that could fill it is wanted")
    for lesson in p["lessons"]["in_prompt"]:
        lines.append(f"- learned: {lesson['statement']}")
    prims = p["lessons"]["reference"]["primitives"]
    if prims:
        lines.append("- reference primitives: " + "; ".join(
            f"{k}={v}" for k, v in sorted(prims.items())))
    # #86: what the market is rewarding, as attributes of how an offer is built to sell --
    # never the depicted design -- with the lift each was measured at.
    for attr in p["lessons"].get("market_attributes") or []:
        lines.append(
            f"- market rewards {attr['attribute']} (favourites x{attr['demand_lift']} across "
            f"{attr['listings']} judged listings): " + "; ".join(attr["phrases"]))
    return "\n".join(lines), b


class BriefingGateway:
    """The model gateway, with each call's brief carrying one rotation of the plan.

    A proxy rather than a change to the generator, so every existing refusal, budget check
    and vocabulary check in `prospecting.propose` runs unchanged. It records every assignment
    it sent, so the audit row can prove what the model was asked rather than what the plan
    intended.
    """

    def __init__(self, inner, ideation_plan: dict):
        self._inner = inner
        self._plan = ideation_plan
        self.sent: list[dict] = []

    def complete_json(self, ref, *, agent, values, required=None):
        values = dict(values or {})
        text, assignment = constraints_text(self._plan, len(self.sent))
        form = str(values.get("form") or "").replace(" ", "_")
        # #138: a live culture candidate whose family this form can develop, rotated so the
        # field spreads across candidates rather than developing the first one repeatedly.
        fits = [c for c in (self._plan.get("culture") or {}).get("matching") or []
                if form in c["forms"]]
        chosen = None
        if fits:
            used = sum(1 for b in self.sent if b.get("culture_id"))
            chosen = fits[used % len(fits)]
            text += (f"\n- develop this Brambleloop cultural concept (culture candidate "
                     f"{chosen['slug']}): {chosen['premise']}")
        values["brief"] = f'{values.get("brief", "")}\n\n{text}'
        entry = {**assignment, "form": values.get("form"),
                 "culture_id": chosen["id"] if chosen else None}
        self.sent.append(entry)
        answer = self._inner.complete_json(ref, agent=agent, values=values, required=required)
        # The titles this call produced, so a survivor can be traced to the culture
        # candidate it developed without trusting the model to report its own origin.
        entry["titles"] = [str(r.get("title") or "").strip()
                           for r in ((answer or {}).get("concepts") or [])
                           if isinstance(r, dict)][:24]
        return answer

    def culture_origin(self, title: str) -> int | None:
        for entry in self.sent:
            if entry.get("culture_id") and title in (entry.get("titles") or []):
                return entry["culture_id"]
        return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


# ---------------------------------------------------------------------------
# After generation


def _entrant(c) -> universe.Entrant:
    k = c.concept
    return universe.Entrant(key=k.key, form=k.form, function=k.function,
                            emotional_tone=k.feeling, construction=k.construction,
                            motif_family=k.motif, recipient=k.recipient, make_time=k.make_lane)


def quotas(ordered: list, *, share: float = universe.DOMINANCE_ALARM) -> dict:
    """#119: admit survivors in merit order while no axis value exceeds its quota.

    The quota is a share of the *admitted* shortlist, recomputed as it grows, with a floor of
    one so the first entrant of any value is always admissible. A survivor that would push
    one value of one axis past the quota is deferred (kept, not killed) and the axis is named.

    An axis on which the whole field holds a single value is fixed by the arena (a one-form
    arena, a one-lane runway) rather than chosen by the tournament; it is reported as
    dominated in the field diversity and not used to defer, because no admissible
    alternative exists to prefer.
    """
    admitted: list = []
    deferred: list[dict] = []
    counts: dict[str, dict[str, int]] = {a: {} for a in universe.DIVERSITY_AXES}
    varied = [a for a in universe.DIVERSITY_AXES
              if len({_entrant(c).axis(a) for c in ordered}) > 1]
    for c in ordered:
        e = _entrant(c)
        size = len(admitted) + 1
        cap = max(1, int(share * size))
        over = [a for a in varied if counts[a].get(e.axis(a), 0) + 1 > cap]
        # With one or two admitted, every value is necessarily a large share; the quota bites
        # from the third entrant, which is where "dominated" starts to mean anything.
        if over and size >= 3:
            deferred.append({"key": e.key, "axes": over})
            continue
        admitted.append(c)
        for a in universe.DIVERSITY_AXES:
            counts[a][e.axis(a)] = counts[a].get(e.axis(a), 0) + 1
    return {"admitted": admitted, "deferred": deferred, "enforced_axes": varied,
            "fixed_by_arena": [a for a in universe.DIVERSITY_AXES if a not in varied]}


def select(ideation_plan: dict, *, candidates: list, survivors: list,
           window: dict | None = None) -> dict:
    """Apply the floor, the quotas and the role to what survived, and name the winner.

    `window` is `family.shift_capacity` over the survivors at the arena's real days to the
    event (#112): a survivor whose buyer can still comfortably finish it is preferred over one
    that needs a hurry, and the radar's missing skill level (#114) is preferred next.
    """
    field_diversity = universe.diversity([_entrant(c) for c in candidates])
    required = ideation_plan["floor"]["floor"]
    below = [c for c in survivors if c.nearest_distance < required]
    clearing = sorted((c for c in survivors if c.nearest_distance >= required),
                      key=lambda c: (-c.nearest_distance, c.concept.key))
    # #129: the human-quality standard. Every concept that cleared the floor is judged for
    # taste by `standard.meets_standard` with the deterministic taste judge, and a taste
    # rejection is final -- no novelty or correctness score overrides "obvious" or "boring".
    # The winner is chosen from what has taste, so the department is rewarded for the hit,
    # never for the size of the field.
    history_scores = [standard.Scored(**h) if isinstance(h, dict) else h
                      for h in (ideation_plan.get("history") or [])]
    tasteful, taste_rejected = [], []
    field_concepts = [getattr(c, "concept", c) for c in candidates]
    for c in clearing:
        verdict = standard.meets_standard(
            c.nearest_distance, make_lane=c.concept.make_lane, history=history_scores,
            taste_rejection=standard.taste_judge(c.concept, field=field_concepts,
                                                 nearest_distance=c.nearest_distance,
                                                 floor_value=required))
        if verdict["passes"]:
            tasteful.append(c)
        else:
            taste_rejected.append({"key": c.concept.key, "rejected_on": verdict["rejected_on"],
                                   "reason": verdict.get("reason")})
    quota = quotas(tasteful)
    admitted = quota["admitted"]
    lanes = ideation_plan["role"]["lanes"]
    fitting = [c for c in admitted if c.concept.make_lane in lanes]
    pool = fitting or admitted
    hurry = {g["concept"] for g in ((window or {}).get("hurry") or [])}
    comfortable = [c for c in pool if c.concept.key not in hurry]
    if comfortable:
        pool = comfortable
    from .preengineering import skill_level_for_make_lane

    missing = set((ideation_plan.get("skill_gap") or {}).get("missing") or [])
    filling = [c for c in pool if skill_level_for_make_lane(c.concept.make_lane) in missing]
    winner = (filling or pool or [None])[0]
    return {
        "taste_rejected": taste_rejected,
        "hit_quality": (None if winner is None else winner.nearest_distance),
        "field_diversity": field_diversity,
        "shortlist_diversity": universe.diversity([_entrant(c) for c in admitted]),
        "floor_applied": required,
        "below_floor": [{"key": c.concept.key, "novelty_distance": c.nearest_distance}
                        for c in below],
        "quota_deferred": quota["deferred"],
        "quota_enforced_axes": quota["enforced_axes"],
        "quota_fixed_by_arena": quota["fixed_by_arena"],
        "shortlist": [c.concept.key for c in admitted],
        "winner_object": winner,
        "winner": ({"key": winner.concept.key, "title": winner.concept.title,
                    "form": winner.concept.form, "make_lane": winner.concept.make_lane,
                    "novelty_distance": winner.nearest_distance,
                    "role": ideation_plan["role"]["role"],
                    "role_fit": winner.concept.make_lane in lanes,
                    "fills_skill_gap": bool(filling) and winner in filling,
                    "window_hurry": winner.concept.key in hurry}
                   if winner is not None else None),
        "window_deferred": sorted(hurry & {c.concept.key for c in admitted}),
    }


def pre_engineering_gate(db, winner, *, ctx=None, source: str = "ideation",
                         brief: dict | None = None) -> dict:
    """Present the winner to the pre-engineering gate before anything reaches engineering.

    ### PRE-ENGINEERING GATE CALL SITE ###
    The gate (`gate_concept`) is owned by another implementer. It is looked up by name in the
    creative modules and called only if it exists; while it is absent the winner is recorded
    as held, and nothing in the ideation handlers sends a concept to engineering either way.
    """
    import importlib
    import pkgutil

    from .. import creative as package

    if winner is None:
        return {"gate": "not_called", "reason": "no winner", "cleared_for_engineering": False}
    gate = None
    where = ""
    # The owner module first; the scan only matters if the gate ever moves.
    names = ["preengineering"] + [i.name for i in pkgutil.iter_modules(package.__path__)
                                  if i.name != "preengineering"]
    for name in names:
        try:
            module = importlib.import_module(f"{package.__name__}.{name}")
        except ImportError:
            continue
        if hasattr(module, "gate_concept"):
            gate, where = module.gate_concept, name
            break
    if gate is None:
        return {"gate": "absent", "cleared_for_engineering": False,
                "reason": ("creative.*.gate_concept does not exist yet; the winner is held "
                           "and is not sent to engineering")}
    try:
        # The brief (#88 storyboard, #110 motifs, #115 wow, #108 qualifiers, #290 trend
        # domain) is generated deterministically from the winner by `creative.intake`; a
        # gate called without one fails its brief checks by absence, which is C-61.
        verdict = (gate(db, winner.concept, brief=brief) if brief is not None
                   else gate(db, winner.concept))
    except Exception as e:  # noqa: BLE001 - a gate that errors blocks, it does not pass
        return {"gate": f"creative.{where}.gate_concept", "cleared_for_engineering": False,
                "error": f"{type(e).__name__}: {e}"[:300]}
    if isinstance(verdict, dict):
        passed = bool(verdict.get("engineer", verdict.get("passes", False)))
    else:
        passed = bool(verdict)
    effects = None
    if ctx is not None and isinstance(verdict, dict) and "checks" in verdict:
        # The gate owner's own recorder: every verdict audited, a refusal returned to
        # creative development with an autopsy, a waiting concept's grid requested.
        from . import preengineering

        if hasattr(preengineering, "record"):
            try:
                effects = preengineering.record(ctx, verdict, source=source)
            except Exception as e:  # noqa: BLE001 - recording failure is reported
                effects = {"error": f"{type(e).__name__}: {e}"[:200]}
    summary = ({k: verdict.get(k) for k in ("decision", "engineer", "failed", "unmeasured",
                                             "waiting_on", "reasons")}
               if isinstance(verdict, dict) else {"result": bool(verdict)})
    return {"gate": f"creative.{where}.gate_concept", "cleared_for_engineering": passed,
            "verdict": summary, "effects": effects}


def restrict(arena, excluded_forms) -> object:
    """The arena with saturated, angle-less forms removed (#117)."""
    return replace(arena, forms={f: n for f, n in arena.forms.items()
                                 if f not in set(excluded_forms)})


def record(ideation_plan: dict, *, gateway: BriefingGateway | None,
           selection: dict | None, gate: dict | None) -> dict:
    """The JSON-safe `ideation` block stored in the run's audit row."""
    sent = gateway.sent if gateway is not None else []
    if selection and selection.get("winner") and gateway is not None:
        selection = {**selection, "winner": {
            **selection["winner"],
            "culture_origin": gateway.culture_origin(selection["winner"]["title"])}}
    return {
        **{k: v for k, v in ideation_plan.items() if k != "briefs"},
        "calls_briefed": len(sent),
        "briefs_sent": sent[:40],
        "cells_briefed": sorted({b["cell"] for b in sent if b.get("cell")}),
        "themes_briefed": sorted({b["theme"] for b in sent}),
        "occasions_briefed": sorted({b["non_holiday_occasion"] for b in sent}),
        "culture_briefed": sorted({b["culture_id"] for b in sent if b.get("culture_id")}),
        **({k: v for k, v in selection.items() if k != "winner_object"} if selection else
           {"winner": None}),
        "pre_engineering_gate": gate or {"gate": "not_called",
                                         "cleared_for_engineering": False},
    }


# ---------------------------------------------------------------------------
# The standing agents


def mine_complaints(db) -> list[discovery.Complaint]:
    """#118's inputs: recorded review themes and support cases, classified deterministically."""
    from sqlalchemy import select

    from ..core.models import BenchmarkObservation, SupportCase

    out: list[discovery.Complaint] = []
    with db.session() as s:
        observations = [(r.id, dict(r.detail or {})) for r in s.scalars(
            select(BenchmarkObservation).where(
                BenchmarkObservation.kind == "official_api_read"))]
        cases = [(r.id, r.question or "") for r in s.scalars(select(SupportCase))]
    for obs_id, detail in observations:
        themes_ = ((detail.get("reviews") or {}).get("themes") or {})
        for theme, n in themes_.items():
            kind = discovery.REVIEW_THEME_KIND.get(theme)
            if not kind or not isinstance(n, int):
                continue
            for i in range(min(n, 50)):
                out.append(discovery.Complaint(
                    kind=kind, source=f"benchmark_observation:{obs_id}",
                    statement=f"review theme {theme} ({i + 1} of {n})"))
    for case_id, question in cases:
        kind = discovery.classify_complaint(question)
        if kind:
            out.append(discovery.Complaint(kind=kind, source=f"support_case:{case_id}",
                                           statement="classified from a support question"))
    return out
