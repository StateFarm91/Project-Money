"""The canonical-model tournament (#199): a field, a screen, a stress test, and no winner.

The owner's instruction is the whole design: *do not generate one woman and make her
canonical because she happened to be first*. So this module is built to make that impossible
rather than merely discouraged. It produces candidates, screens them, stress-tests the
survivors and stops -- `present()` returns a package for a person to choose from, and there
is no function anywhere in it that selects.

Four things it is careful about.

**A field, not a family.** Twenty renders of one prompt are twenty photographs of nearly the
same woman, and choosing between them is not a choice. The seed notes vary hair, colouring,
build, stature and facial character across a deliberately wide spread, from one shared base
prompt -- one brief with varying notes rather than twenty differently-worded briefs, because
twenty briefs would be comparing the prompts.

**The stress test is where identity is actually measured.** A candidate's neutral portrait
becomes a provisional pack; every other scene is conditioned on it and compared against it.
Five flattering portraits would prove only that the generator can repeat a portrait, so the
scenes are materially different by construction: a fitted garment where the body is readable,
a loose one where it is mostly not, a winter context, and a non-garment scene.

**Face and body are independent hard floors.** After the first reference-conditioned trial
returned the right face on a different chest, a blended identity score is not an option. A
finalist that holds its face and loses its morphology fails, and the report says which.

**Nothing here is built from a photograph of a real person.** `brief.FORBIDDEN` says so and
`plan()` refuses a reference image, because the one moment that rule would be broken is the
moment somebody has a picture and a deadline.
"""
from __future__ import annotations

from ..core.resilience import PermanentError, TransientError
from . import brief, identity, model_registry

TOURNAMENT_ACTION = "model.tournament"
CANDIDATE_ACTION = "model.candidate"

JUDGE_TASK = "image_benchmark_judging"
SCREEN_MAX_TOKENS = 600

# The spread. Each note changes what she looks like without changing what she is for: every
# one of them still has to satisfy the brief's qualities, and none of them names a person.
SEED_NOTES: tuple[str, ...] = (
    "Warm mid-brown hair, shoulder length, loose natural wave. Fair complexion with freckles "
    "across the nose. Slim build, average height.",
    "Dark brown hair worn long and straight. Olive complexion. Athletic build, tall.",
    "Deep black hair in a shoulder-length bob. Deep brown complexion. Softly curved build, "
    "average height.",
    "Auburn hair, long and curly. Very fair complexion. Slender build, petite.",
    "Light brown hair in a blunt collarbone cut. Medium tan complexion. Broad-shouldered, "
    "strong build, tall.",
    "Dark hair pulled into a low bun. Rich brown complexion. Full figure, average height.",
    "Honey-blonde hair, long with a centre part. Fair-medium complexion. Lean build, "
    "long-limbed, tall.",
    "Black tightly-coiled natural hair worn short. Deep complexion. Compact athletic build, "
    "petite.",
    "Chestnut hair in a shaggy shoulder cut. Warm ivory complexion. Soft build, average "
    "height, short torso.",
    "Salt-and-pepper dark hair, chin length. Light olive complexion. Slim, angular, tall.",
    "Copper-red hair, long and wavy. Pale freckled complexion. Curvy build, average height.",
    "Dark ash-brown hair in a long layered cut. Medium complexion. Broad build, wide "
    "shoulders, average height.",
    "Warm black hair worn in a sleek ponytail. Golden complexion. Very slim, long torso, "
    "tall.",
    "Mousy-brown hair, short pixie cut. Freckled fair complexion. Small frame, petite.",
    "Dark brown hair with soft curls to mid-back. Brown complexion. Hourglass build, average "
    "height.",
    "Platinum-blonde hair in a sharp bob. Cool fair complexion. Narrow shoulders, slight "
    "build, average height.",
    "Deep brown hair in shoulder-length twists. Deep warm complexion. Tall, strong-shouldered.",
    "Light golden-brown hair worn long. Sun-warmed complexion. Softly athletic, average "
    "height.",
    "Near-black hair in a straight long cut with a fringe. Fair-medium complexion. Petite, "
    "short-limbed, slim.",
    "Warm brown hair in loose shoulder waves. Medium-deep complexion. Full-figured, tall, "
    "long torso.",
    "Dark blonde hair in a messy mid-length cut. Fair complexion with rosy tone. Wiry build, "
    "average height.",
    "Black hair worn in a short curly crop. Medium-deep complexion. Compact, broad build, "
    "petite.",
    "Rich brown hair in a long braid. Olive-tan complexion. Slim-hipped, broad-shouldered, "
    "tall.",
    "Ash-blonde hair to the collarbone. Very fair complexion. Rounded build, short stature.",
)

DEFAULT_CANDIDATES = brief.TARGET_CANDIDATES[0]


class TournamentRefused(ValueError):
    """A run that would compare prompts, or build her from somebody's photograph."""


# ---------------------------------------------------------------------------
# Plan


def plan(db=None, *, count: int = DEFAULT_CANDIDATES, reference_image: str = "",
         env: dict | None = None) -> dict:
    """What the tournament would render and what it would cost, before anything is spent."""
    from ..gateway import image_bench, images

    if reference_image:
        raise TournamentRefused(
            "the canonical model is not built from a reference photograph of a real person. "
            "A persistent commercial brand identity made from somebody's picture is that "
            "person's likeness in commercial use, and it is the celebrity resemblance the "
            "owner's own direction rules out (visual.brief.FORBIDDEN)")
    count = max(5, min(count, len(SEED_NOTES)))

    provider = preferred_provider(db, env)
    per_image = images.BY_KEY[provider].cad_per_image if provider in images.BY_KEY else 0.0
    finalists = brief.TARGET_FINALISTS
    stress_renders = finalists * len(brief.STRESS_SCENES)
    observations = finalists * (len(brief.STRESS_SCENES) + 1)

    from ..gateway import routing

    judge_rate = routing.estimate_cad(JUDGE_TASK)
    render_cad = round((count + stress_renders) * per_image, 4)
    judge_cad = round((count + observations) * judge_rate, 4)
    return {
        "provider": provider,
        "candidates": count,
        "stress_renders": stress_renders,
        "observations": observations,
        "render_cad": render_cad,
        "judging_cad": judge_cad,
        "total_cad": round(render_cad + judge_cad, 4),
        "finalists": finalists,
        "scenes": [k for k, _ in brief.STRESS_SCENES],
        "spends_against": ("the CA$100 monthly model ceiling as Build-2 work, not the "
                           "CA$50 image-benchmark authorization, which measured providers "
                           "rather than faces"),
        "selects_nothing": (
            "there is no function in this module that makes a candidate canonical. The "
            "finalists are presented and the owner chooses"),
    }


def preferred_provider(db=None, env: dict | None = None) -> str:
    """The strongest verified provider available, without locking anything.

    The benchmark's leader is used for work while it stays provisional -- Google is an
    eligible candidate nobody could render, so nothing is locked, and using the measured
    leader meanwhile is not the same as declaring it the production stack.
    """
    from ..gateway import image_bench, images

    available = set(images.available(env))
    if db is not None:
        measured = [(image_bench.stored_result(db, c), c) for c in image_bench.CANDIDATES
                    if c.can_hold_an_identity and c.key in available]
        scored = [(r.overall() or 0.0, c.key) for r, c in measured if r is not None]
        if scored:
            return max(scored)[1]
    for fallback in ("gpt-image-2", "flux-2-pro", "nano-banana-2"):
        if fallback in available:
            return fallback
    return ""


# ---------------------------------------------------------------------------
# Generate and screen


SCREEN_SYSTEM = (
    "You are screening a generated portrait for use as a craft brand's recurring model. "
    "Judge the photograph in front of you, not what it could become with better styling."
)


def screen_prompt() -> str:
    return (
        "Reply with a single JSON object and nothing else, mapping each key below to an "
        f"integer from 0 (fails completely) to 5 (excellent), plus a key `notes` mapping any "
        "score below 2 to one short phrase, plus a key `reads_as_public_figure` which is "
        "true or false.\n\n"
        + "\n".join(f"- {k}" for k in brief.SCREEN_ON))


def _judge(db, image_refs: list[str], system: str, prompt: str, max_tokens: int) -> str:
    from ..finance import spend_report
    from ..gateway import anthropic as gw

    provider = gw.provider_for(JUDGE_TASK)
    response = provider.see(system, prompt, image_refs, max_tokens=max_tokens)
    if db is not None:
        spend_report.record(
            db, agent="creative_director",
            amount_cad=round(
                response.input_tokens * provider.cost_per_1k_input_cad / 1000
                + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8),
            purpose="model_tournament", provider="anthropic", model=provider.model,
            department="creative", tokens_in=response.input_tokens,
            tokens_out=response.output_tokens, detail={"price_basis": "assumed"})
    return response.text


def parse_screen(text: str) -> dict:
    import json

    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    parsed = json.loads(body)
    parsed.pop("notes", None)
    flagged = bool(parsed.pop("reads_as_public_figure", False))
    missing = [k for k in brief.SCREEN_ON if k not in parsed]
    if missing:
        raise TournamentRefused(
            f"{missing} were not scored. A screen that averages over the criteria it "
            f"happened to reach ranks the candidates it looked at least hard at")
    scores = {k: int(parsed[k]) for k in brief.SCREEN_ON}
    if any(v < 0 or v > 5 for v in scores.values()):
        raise TournamentRefused(f"a score outside 0..5: {scores}")
    return {"scores": scores, "reads_as_public_figure": flagged,
            "mean": round(sum(scores.values()) / len(scores), 3)}


def generate_candidates(db, *, count: int = DEFAULT_CANDIDATES, env: dict | None = None,
                        work_dir: str | None = None, generator=None, judge=None) -> dict:
    """Render the field and screen it. Stores every candidate with its provenance."""
    from ..gateway import images

    plan(db, count=count, env=env)          # refuses a reference photograph
    provider = preferred_provider(db, env)
    if not provider and generator is None:
        return {"ran": False, "reason": "no image provider holds a credential"}

    made: list[dict] = []
    failures: list[dict] = []
    spent = 0.0
    for index, note in enumerate(SEED_NOTES[:count]):
        key = f"cand-{index:02d}"
        try:
            render = (generator(brief.base_prompt(note), env=env, size="1024x1024")
                      if generator else
                      images.generate(brief.base_prompt(note), env=env,
                                      provider_key=provider, size="1024x1024",
                                      work_dir=work_dir))
            spent += float(render.get("cad") or 0.0)
            ref = render.get("image_ref") or render.get("url") or ""
            answer = (judge or (lambda *_a, **_k: _judge(
                db, [ref], SCREEN_SYSTEM, screen_prompt(), SCREEN_MAX_TOKENS)))(db, ref)
            screened = parse_screen(answer)
        except (PermanentError, TransientError, TournamentRefused, ValueError) as exc:
            failures.append({"candidate": key, "stage": "render" if "render" in locals()
                             else "screen", "why": f"{type(exc).__name__}: {str(exc)[:220]}"})
            continue

        row = {"key": key, "seed_note": note, "image_ref": ref,
               "provider": render.get("provider") or provider,
               "mean": screened["mean"], "scores": screened["scores"],
               "reads_as_public_figure": screened["reads_as_public_figure"],
               "cad": render.get("cad")}
        made.append(row)
        if db is not None:
            from ..agents.registry import Registry

            Registry(db).audit("creative_director", CANDIDATE_ACTION, detail=row)

    # A candidate that reads as a recognisable public figure is out on the rule, not on its
    # score -- exactly as a model with no reference conditioning leaves the provider
    # benchmark on a requirement rather than on taste.
    eligible = [c for c in made if not c["reads_as_public_figure"]]
    excluded = [{"candidate": c["key"], "why": "reads as a recognisable public figure"}
                for c in made if c["reads_as_public_figure"]]
    eligible.sort(key=lambda c: (-c["mean"], c["key"]))
    return {"ran": True, "generated": len(made), "failures": failures,
            "excluded": excluded, "candidates": eligible, "spent_cad": round(spent, 4),
            "provider": provider}


# ---------------------------------------------------------------------------
# The stress test


def stress_test(db, finalist: dict, *, env: dict | None = None, work_dir: str | None = None,
                generator=None, observer=None) -> dict:
    """Render one finalist across the controlled scenes and measure what held.

    The finalist's own neutral portrait is the provisional pack: it is observed once, and
    every scene is conditioned on it and compared against it. That is the same mechanism the
    canonical identity will use, which is the point -- a finalist is being tested on whether
    she can *be* a canonical identity, not on whether she photographs well once.
    """
    from ..gateway import images

    provider = finalist.get("provider") or preferred_provider(db, env)
    reference = finalist["image_ref"]
    seen = (observer or model_registry.observe)(db, reference)
    if seen.get("error") or seen.get("no_person"):
        return {"finalist": finalist["key"], "usable": False,
                "why": f"the reference portrait could not be read: {seen.get('error', '')}"}

    fields = {identity.DIMENSION_FIELD[d]: seen.get(d) for d in identity.DRIFT_DIMENSIONS}
    unpinned = [f for f in identity.IDENTITY_FIELDS
                if not fields.get(f) or str(fields.get(f)).lower() == identity.UNMEASURABLE]
    provisional = identity.ReferencePack(version=0, fields=fields,
                                         approved_by_owner_at="provisional")

    scenes: list[dict] = []
    spent = 0.0
    for key, prompt in brief.STRESS_SCENES:
        if key == "neutral_reference":
            continue
        try:
            render = (generator(prompt, env=env, size="1024x1024",
                                reference_urls=[reference])
                      if generator else
                      images.generate(prompt, env=env, provider_key=provider,
                                      reference_urls=[reference], size="1024x1024",
                                      work_dir=work_dir))
            spent += float(render.get("cad") or 0.0)
            ref = render.get("image_ref") or ""
            observed = (observer or model_registry.observe)(db, ref)
            verdict = identity.drift_check(observed, provisional)
        except (PermanentError, TransientError) as exc:
            scenes.append({"scene": key, "rendered": False, "why": str(exc)[:200]})
            continue
        scenes.append({
            "scene": key, "rendered": True, "image_ref": ref,
            "provider": render.get("provider") or provider,
            "verdict": verdict["verdict"],
            "face": verdict["face"].get("verdict"),
            "morphology": verdict["morphology"].get("verdict"),
            "drifted": verdict.get("failed", []),
            "unmeasurable": (verdict["face"].get("unmeasurable", [])
                             + verdict["morphology"].get("unmeasurable", [])),
        })

    rendered = [s for s in scenes if s.get("rendered")]
    face_ok = all(s["face"] == "pass" for s in rendered)
    body_ok = all(s["morphology"] == "pass" for s in rendered)
    return {
        "finalist": finalist["key"], "usable": True, "provider": provider,
        "reference_image": reference, "reference_observation": seen,
        "unpinned_fields": unpinned,
        "scenes": scenes, "scenes_rendered": len(rendered),
        "scenes_expected": len(brief.STRESS_SCENES) - 1,
        "complete": len(rendered) == len(brief.STRESS_SCENES) - 1,
        "face_floor": "pass" if face_ok else "fail",
        "morphology_floor": "pass" if body_ok else "fail",
        # Both, independently. The first reference-conditioned trial held a face across a
        # regeneration and changed the chest, and a blended score would have called that a
        # good result.
        "clears_both_floors": bool(rendered) and face_ok and body_ok,
        "spent_cad": round(spent, 4),
    }


def present(db, results: list[dict]) -> dict:
    """The package the owner chooses from. Names no winner."""
    clear = [r for r in results if r.get("clears_both_floors")]
    return {
        "finalists": results,
        "clear_both_floors": [r["finalist"] for r in clear],
        "hard_floors": list(brief.HARD_FLOORS),
        "scenes": [k for k, _ in brief.STRESS_SCENES],
        "decision": "owner",
        "why_nothing_is_chosen": (
            "selection is a consequential brand decision and stays the owner's. A candidate "
            "that became canonical by being first, or by topping a table, is an identity "
            "nobody chose -- discovered a hundred listings later"),
        "what_selection_does": (
            "freezes the identity, persists the reference pack durably, binds it to a "
            "version, makes it the reference-conditioning source for every model-bearing "
            "frame, and makes changing her afterwards an explicit brand redesign"),
    }
