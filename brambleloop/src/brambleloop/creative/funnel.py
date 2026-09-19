"""The staged selection tournament, and the arithmetic that stops it being a queue.

Requirement 3. The instruction is one sentence -- do not fully engineer the first ideas --
and the mechanism the requirement specifies is a funnel with a shape: roughly 75-100 cheap
concepts, about 40 researched, about 20 developed into real propositions, 10-15 prototyped
through the digital twin, and only 5-10 released.

The shape is the point, and it is the part that quietly disappears. A funnel that starts with
twelve concepts is not a tournament, it is the first ideas with a process wrapped around
them; and a stage that advances everything that entered it is not a gate, it is a queue with
a name. Both look identical in a report that counts only what came out of the end.

So four rules, each of them arithmetic rather than judgement:

**Every entrant is accounted for.** Survivors plus killed equals entrants, and a stage that
loses concepts without saying so is refused. This is the same rule as counting database rows
rather than taking an argument's word for it: a funnel is only honest if nothing can leave it
quietly.

**A stage that kills nothing is refused.** Not warned about. A kill gate with no kills either
had nothing to judge or was not applied, and both mean the stage did not happen.

**Every kill names a cause from a closed vocabulary.** "Not strong enough" aggregates to
nothing, and the aggregate is the entire value of running a tournament rather than choosing:
a funnel dying mostly of sameness has a generation problem and one dying of cost has a brief
problem, and those are opposite fixes.

**Entering a stage below its floor is refused.** The floor is what makes the shape real. A
prototype stage fed four concepts is choosing among four concepts whatever happens next.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Why a concept died. Closed, because "not strong enough" aggregates to nothing and the
# aggregate is the reason for running a tournament instead of simply choosing.
KILL_CAUSES: dict[str, str] = {
    "sameness": "the same idea as something already in the catalogue or the field",
    "genericness": "a product description rather than a visual premise",
    "emotional_appeal": "nobody in particular is being made to feel anything",
    "derivative": "anchored too closely on an observed competitor product",
    "thumbnail": "depends on detail that does not survive the grid",
    "complexity": "asks more of the maker than the idea repays",
    "shopping_window": "the buyer cannot finish it before the occasion it is for",
    "no_family": "produces exactly one product where a collection was wanted",
    "saturation": "the archetype is crowded and no unmet angle was named",
    "margin": "the contribution does not survive platform fees at a plausible price",
    "unverifiable": "the claim it rests on cannot be checked by this company",
    "capacity": "good, and beaten by better for the slots that exist",
}


@dataclass(frozen=True)
class Stage:
    """One round of the tournament: what enters it, and what it is allowed to pass."""

    key: str
    what: str
    floor_in: int          # fewer entrants than this and the stage is not a selection
    target_out: tuple[int, int]
    gate: str              # the kill gate this stage applies, in words a reader can check


STAGES: tuple[Stage, ...] = (
    Stage("ideation", "cheap concepts, generated rather than engineered", 75, (75, 100),
          "structural refusal: a concept with no premise, no recipient and no function is "
          "not a concept"),
    Stage("research", "checked against the catalogue, the field and the calendar", 75,
          (35, 45),
          "the jury: sameness, genericness, emotional appeal, derivativeness, thumbnail, "
          "complexity and the shopping window"),
    Stage("proposition", "developed into a commercial and visual proposition", 35, (18, 24),
          "does it seed a family, does it have an unmet angle, does the margin survive"),
    Stage("prototype", "run through the deterministic compiler and the digital twin", 18,
          (10, 15),
          "deterministic validation: the CIR compiles, the twin agrees, the reverse "
          "compiler recovers the construction"),
    Stage("release", "engineered, certified and released", 10, (5, 10),
          "the release gates: quality director, asset truth, policy"),
)

STAGE_BY_KEY: dict[str, Stage] = {s.key: s for s in STAGES}
STAGE_ORDER: tuple[str, ...] = tuple(s.key for s in STAGES)


class FunnelRefused(ValueError):
    """A stage that lost concepts quietly, killed nothing, or was fed too few to choose from."""


@dataclass
class Round:
    stage: str
    entered: int
    survived: list[str]
    killed: dict[str, str]          # concept key -> kill cause

    @property
    def kill_rate(self) -> float:
        return round(len(self.killed) / self.entered, 3) if self.entered else 0.0

    def to_dict(self) -> dict:
        stage = STAGE_BY_KEY[self.stage]
        low, high = stage.target_out
        return {"stage": self.stage, "what": stage.what, "gate": stage.gate,
                "entered": self.entered, "survived": len(self.survived),
                "killed": len(self.killed), "kill_rate": self.kill_rate,
                "target_out": [low, high],
                "within_target": low <= len(self.survived) <= high,
                "causes": _tally(self.killed)}


def _tally(killed: dict[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for cause in killed.values():
        out[cause] = out.get(cause, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


@dataclass
class Tournament:
    """One opportunity run through every stage, with the shape it actually produced."""

    opportunity: str
    rounds: list[Round] = field(default_factory=list)

    @property
    def stage_reached(self) -> str | None:
        return self.rounds[-1].stage if self.rounds else None

    def survivors(self) -> list[str]:
        return list(self.rounds[-1].survived) if self.rounds else []


def advance(tournament: Tournament, *, stage: str, entrants: list[str],
            survived: list[str], killed: dict[str, str]) -> Round:
    """Run one stage, refusing every way the funnel could stop being one.

    Refusals rather than warnings throughout. A warned-about funnel is a funnel that ran.
    """
    spec = STAGE_BY_KEY.get(stage)
    if spec is None:
        raise FunnelRefused(f"{stage!r} is not a stage: {list(STAGE_ORDER)}")

    expected_index = len(tournament.rounds)
    if STAGE_ORDER.index(stage) != expected_index:
        wanted = STAGE_ORDER[expected_index] if expected_index < len(STAGE_ORDER) else None
        raise FunnelRefused(
            f"{stage} ran out of order; {wanted} has not happened. A stage skipped is a "
            f"concept engineered without having been chosen, which is the thing this "
            f"tournament exists to prevent")

    if tournament.rounds:
        previous = set(tournament.rounds[-1].survived)
        strangers = [e for e in entrants if e not in previous]
        if strangers:
            raise FunnelRefused(
                f"{sorted(strangers)} entered {stage} without surviving "
                f"{tournament.rounds[-1].stage}. A concept that joins late has been chosen "
                f"by somebody rather than by the tournament")

    if len(entrants) < spec.floor_in:
        raise FunnelRefused(
            f"{stage} was fed {len(entrants)} concepts against a floor of {spec.floor_in}. "
            f"A stage below its floor is choosing among whatever happened to be there, and "
            f"no amount of judging repairs a field that was never wide")

    accounted = set(survived) | set(killed)
    if accounted != set(entrants) or len(survived) + len(killed) != len(entrants):
        missing = sorted(set(entrants) - accounted)
        extra = sorted(accounted - set(entrants))
        raise FunnelRefused(
            f"{stage} does not account for every entrant "
            f"(unaccounted: {missing}; not entrants: {extra}). Survivors plus killed equals "
            f"entrants, or concepts are leaving the funnel quietly")

    if not killed:
        raise FunnelRefused(
            f"{stage} killed nothing. A kill gate with no kills either had nothing to judge "
            f"or was not applied, and both mean the stage did not happen")

    unknown = sorted({c for c in killed.values() if c not in KILL_CAUSES})
    if unknown:
        raise FunnelRefused(
            f"kill causes {unknown} are not in the vocabulary: {sorted(KILL_CAUSES)}. "
            f"'Not strong enough' aggregates to nothing, and the aggregate is the whole "
            f"value of running a tournament rather than choosing")

    round_ = Round(stage=stage, entered=len(entrants), survived=list(survived),
                   killed=dict(killed))
    tournament.rounds.append(round_)
    return round_


def may_engineer(tournament: Tournament, concept_key: str) -> None:
    """Refuse engineering a concept the tournament has not carried to the prototype stage.

    This is the requirement's opening sentence made mechanical. Everything else here is
    arithmetic about a funnel; this is the thing the arithmetic is for.
    """
    reached = [r for r in tournament.rounds if r.stage == "prototype"]
    if not reached:
        raise FunnelRefused(
            f"{concept_key} cannot be engineered: the tournament has not reached the "
            f"prototype stage. Do not fully engineer the first ideas (#3)")
    if concept_key not in reached[0].survived:
        raise FunnelRefused(
            f"{concept_key} did not survive the prototype stage, so engineering it is "
            f"choosing outside the tournament")


def report(tournament: Tournament) -> dict:
    """The shape the tournament actually produced, against the shape it was meant to have."""
    rounds = [r.to_dict() for r in tournament.rounds]
    causes: dict[str, int] = {}
    for r in tournament.rounds:
        for cause, count in _tally(r.killed).items():
            causes[cause] = causes.get(cause, 0) + count

    dominant = max(causes, key=causes.get) if causes else None
    started = tournament.rounds[0].entered if tournament.rounds else 0
    finished = len(tournament.survivors())

    off_shape = [r["stage"] for r in rounds if not r["within_target"]]
    return {
        "opportunity": tournament.opportunity,
        "rounds": rounds,
        "started_with": started,
        "survivors": finished,
        "overall_survival": round(finished / started, 3) if started else None,
        "deaths_by_cause": dict(sorted(causes.items(), key=lambda kv: -kv[1])),
        "dominant_cause": dominant,
        "diagnosis": KILL_CAUSES.get(dominant or "", ""),
        "stages_off_target_shape": off_shape,
        "complete": len(tournament.rounds) == len(STAGES),
        "note": (
            "the tournament has not finished, so its survivors are not a selection yet"
            if len(tournament.rounds) != len(STAGES) else
            f"{started} concepts became {finished}, and the commonest death was "
            f"{dominant}: {KILL_CAUSES.get(dominant or '', '')}"),
    }
