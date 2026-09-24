"""Whether the tiling failure is this provider's, measured against the production blocker.

Six product-first renders under `gpt-image-2`, across three method versions and two
products, were all blocked on `texture_not_repeating` -- while a real crochet photograph
passed all ten gallery checks with nothing unjudged. The check discriminates, so the
renders genuinely tile, and two method changes did not move it. What is left untested is
whether the *provider* is the variable.

**This is not another tournament.** The image-provider benchmark already ran and chose
`gpt-image-2` on prompt adherence (B-050/B-051), and those dimensions are settled. This
asks one question the benchmark never asked, because the failure had not happened yet: can
a second already-integrated provider work crochet fabric without tiling, while holding
every other launch-critical floor?

The comparison is only meaningful if nothing else changes, so the trial drives
`owned_photography.make` -- the exact production path, with the same certified products,
the same CIR-derived prompt, the same chart reference, the same independent judges and the
same gates -- and varies `provider_key` alone.

**A provider does not win by clearing `texture_not_repeating` alone.** A render that stops
tiling and starts inventing seams, losing the motif or reading as a render has traded one
launch blocker for another, so every dimension is reported and the recommendation names
what regressed.

Trial renders are filed under this module's own action and are never listing assets. A
trial is evidence about a provider; reading one back as a product's photograph is the
row-for-capability defect this system keeps finding.
"""
from __future__ import annotations

ACTION = "visual.provider_trial"

# The owner's authorisation of 2026-09-23, enforced here rather than remembered.
#
# "Hard spend ceiling for this experiment: CA$4.00. Stop at the ceiling." A ceiling that
# lives in a sentence is one a loop walks through at three in the morning, so this is
# checked before every render against the trial's own running total *plus* the next
# render's known price -- not after, which is how a ceiling is discovered by exceeding it.
CEILING_CAD = 4.00

# Which floors this trial reports, grouped as the owner asked for them.
#
# `gallery.REALISM_CHECKS` mixes two different questions and the split matters here: a
# provider that fixes tiling by flattening the fabric has not helped. Structural fidelity
# is whether the crochet could be worked at all; texture fidelity is whether it repeats a
# patch of itself.
STRUCTURAL: tuple[str, ...] = ("stitch_scale_plausible", "yarn_continuity",
                               "edge_construction", "drape", "joins_make_sense",
                               "no_impossible_seams", "garment_fit")
TEXTURE: tuple[str, ...] = ("texture_not_repeating",)


class CeilingReached(RuntimeError):
    """The authorised spend for this experiment is exhausted."""


def _price_of(provider_key: str) -> float:
    from ..gateway import images

    provider = images.BY_KEY.get(provider_key)
    return round(float(provider.usd_per_image) * images.USD_TO_CAD, 4) if provider else 0.0


def attempt(db, cir, twin, *, provider_key: str, work_dir: str, spent_so_far: float,
            **judges) -> dict:
    """One render on one provider, judged by the production gates and nothing else.

    Refuses rather than renders when the next render's known price would carry the trial
    past its ceiling. The refusal is a record, so a trial that stops early says so instead
    of looking like a trial that found less.
    """
    from ..publish import owned_photography
    from . import photoreal

    price = _price_of(provider_key)
    if spent_so_far + price > CEILING_CAD:
        raise CeilingReached(
            f"the next {provider_key} render costs CA${price} and CA${spent_so_far} of the "
            f"CA${CEILING_CAD} authorised for this experiment is already spent. Stopping at "
            f"the ceiling is the instruction, and a partial trial that says so is worth "
            f"more than a complete one that went over")

    record = owned_photography.make(db, cir, twin, work_dir=work_dir,
                                    provider_key=provider_key, **judges)
    if not record.get("made"):
        return {"provider": provider_key, "slug": cir.slug, "made": False,
                "why": record.get("why", ""), "spent_cad": 0.0}

    realism = ((record.get("inspection") or {}).get("realism")) or {}
    truth = record.get("asset_truth") or {}
    motif = record.get("motif") or {}
    spent = float(record.get("spent_cad") or 0.0)

    # Photographic realism is asked separately and explicitly, because the product-first
    # path does not run it: `gallery.REALISM_CHECKS` asks whether the crochet is possible,
    # `photoreal.CHECKS` asks whether the picture reads as a photograph, and a provider
    # that fixes fabric while producing an obvious render has not cleared the owner's
    # Final Master standard.
    photo_reading = photoreal.judge(record.get("image_ref") or "", db=db,
                                    provider=judges.get("realism_judger"))
    photo = photoreal.gate(photo_reading)

    return {
        "provider": provider_key,
        "slug": cir.slug,
        "version": cir.version,
        "made": True,
        "method_version": owned_photography.METHOD_VERSION,
        "image_ref": record.get("image_ref"),
        # 1. crochet/fabric structural fidelity
        "structural_failed": sorted(k for k in STRUCTURAL if realism.get(k) is False),
        "structural_unjudged": sorted(k for k in STRUCTURAL if k not in realism),
        # 2. repeating texture fidelity -- the production blocker itself
        "texture_failed": sorted(k for k in TEXTURE if realism.get(k) is False),
        # 3. product truth: does the fabric work the certified chart
        "product_truth": motif.get("verdict"),
        "motif_observed": (motif.get("observed") or {}).get("repeating_unit_shape"),
        # 4. photographic realism, asked with the same standard the model path uses
        "photographic_realism": photo["verdict"],
        "photoreal_failed": photo["failed"],
        "photoreal_unjudged": photo["unjudged"],
        # 5. canonical identity/morphology -- stated, not silently skipped
        "identity": "not_applicable",
        "why_identity_not_applicable": IDENTITY_NOT_APPLICABLE,
        # 7. failure modes
        "asset_truth": truth.get("verdict"),
        "semantic_problems": list(truth.get("semantic_problems") or ()),
        "third_party_marks": list(truth.get("third_party_marks") or ()),
        # 8. cost
        "spent_cad": round(spent, 4),
        "usable_as_listing_asset": bool(record.get("usable_as_listing_asset")),
    }


# What the trial renders, and why these two.
#
# The owner asked for the simple case and an appropriately harder one, so that provider
# capability can be told apart from product complexity -- which is exactly what separated
# the last two findings. Both already have incumbent records on the same gates, so the
# comparison is against measured production behaviour rather than a fresh baseline nobody
# has seen fail.
CASES: tuple[tuple[str, str], ...] = (
    ("spooky-garland", "simple: a garland, few stitches visible at once, no pictorial motif"),
    ("winter-village-graphghan",
     "hard: a pictorial picture-blanket, the most demanding fabric in the catalogue"),
)

INCUMBENT = "gpt-image-2"

# Challengers in the order they answer the question best, and the reason for the order.
#
# `nano-banana-2` is first on the merits: its own row in the provider table reads
# "fine-grained fabric and material texture at up to 4K... whether that buys anything on
# crochet", which is precisely the failing dimension. Live, 2026-09-23, it returned
# `402 prepayment credits are depleted` on every attempt and rendered nothing, so it could
# not be tested at all.
#
# `flux-2-pro` is the fallback because it is the only other credentialled provider that
# conditions on reference images, and its probe is green. Substituting it is not widening
# the experiment: the authorised question is whether the tiling blocker is provider-
# specific, one challenger at a time, inside the same ceiling. A challenger that cannot
# render is not a cheaper answer, it is no answer.
CHALLENGERS: tuple[str, ...] = ("nano-banana-2", "flux-2-pro")


def pick_challenger(env: dict | None = None, *, exclude: tuple[str, ...] = ()) -> str:
    """The strongest credentialled challenger that is not the incumbent.

    Credentialled is not the same as usable -- `nano-banana-2` held a key and a depleted
    balance -- so a caller that has already watched one fail passes it in `exclude`. This
    returns a name, never a promise that it will render.
    """
    from ..gateway import images

    have = set(images.available(env))
    for key in CHALLENGERS:
        if key in have and key != INCUMBENT and key not in exclude:
            return key
    return ""

# Why the identity dimension is reported rather than silently absent.
#
# The owner asked for canonical identity and morphology "where applicable", and the honest
# answer is that it is not: every certified product is product-first. Saying so is the
# difference between a dimension that does not apply and one nobody measured, which is the
# distinction this system spends most of its time defending.
IDENTITY_NOT_APPLICABLE = (
    "every certified product is product-first and carries no model, so there is no "
    "identity in these frames to compare. The canonical-model blocker is separate and "
    "untouched by this trial: nothing here renders her")


def experiment_spend_cad(db, *, limit: int = 40) -> float:
    """What this experiment has already spent, across every challenger run.

    The ceiling is on the experiment, not on the run. `run` used to start its counter at
    zero, so each challenger got a fresh CA$4.00 and the authorised total was whatever the
    ceiling happened to be multiplied by however many challengers were tried. That held only
    while exactly one challenger ever rendered, which stopped being true the moment
    `nano-banana-2` became reachable again -- so a control that had never been wrong was
    about to be wrong for the first time on the next deploy.

    Filed runs are summed regardless of render method. A method change does not refund
    money, and the owner authorised an amount rather than an amount per attempt at the
    question.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    total = 0.0
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                             .order_by(desc(AuditLog.id)).limit(limit)):
            total += float((row.detail or {}).get("spent_cad") or 0.0)
    return round(total, 4)


def incumbent_evidence(db, *, limit: int = 40) -> list[dict]:
    """Incumbent attempts already measured under the current render method.

    Read from the filed trials rather than re-rendered. A measurement is evidence about a
    provider and a method, and both are recorded on the attempt, so nothing here has to be
    bought twice.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..publish import owned_photography

    out: list[dict] = []
    seen: set[tuple] = set()
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                             .order_by(desc(AuditLog.id)).limit(limit)):
            for a in (row.detail or {}).get("attempts") or []:
                if (a.get("provider") != INCUMBENT or not a.get("made")
                        or a.get("method_version") != owned_photography.METHOD_VERSION):
                    continue
                key = (a.get("slug"), a.get("image_ref"))
                if key in seen:
                    continue
                seen.add(key)
                out.append({**a, "reused_from_an_earlier_trial": True})
    return out


def run(db, *, challenger: str, work_dir: str, attempts: int = 2,
        incumbent_arm: int = 1, cases=CASES, prior_incumbent=None, **judges) -> dict:
    """Render the cases on both providers and report every dimension. Switches nothing.

    The incumbent gets a smaller arm on purpose. Its behaviour on the blocker is already
    measured -- six production renders, three method versions, two products -- and re-running
    settled ground would spend the owner's ceiling to re-learn it. What history does *not*
    carry is photographic realism, because the product-first path never ran that judge, so
    the incumbent renders just enough to measure the dimensions nothing has measured yet.
    """
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..ops import funding
    from ..products.builder import for_slug

    # Refused before the first render, for the reason the portrait repair refuses: every
    # floor this trial compares on is a vision call, so a render made now could not be
    # scored on the one question the trial exists to answer. A comparison of two
    # unjudgeable images is not a comparison.
    held = funding.blocked(db)
    if held.get("blocked"):
        return {"ran": False, "waiting_on": "model_provider_balance",
                "challenger": challenger, "incumbent": INCUMBENT,
                "spent_cad": 0.0, "attempts": [],
                "why": ("every dimension this trial compares on is a vision call, and the "
                        "balance that serves them is spent. Rendering now would buy images "
                        "that cannot be scored. " + held.get("why_this_stops_spending", ""))}

    # Seeded from what the experiment has already spent, not from zero. The ceiling governs
    # the authorisation the owner gave once, so every challenger after the first draws from
    # what is left of it rather than from a fresh copy of it.
    prior = experiment_spend_cad(db)
    spent = prior
    rows: list[dict] = []
    stopped = ""

    # Incumbent evidence is collected once and reused.
    #
    # Every challenger run would otherwise re-render the incumbent arm to re-learn what it
    # already knows -- two renders a time, for a provider whose behaviour on this blocker is
    # measured across six production renders and three method versions. The owner's
    # instruction is explicit: reuse the existing `gpt-image-2` measurements and do not
    # re-run collected evidence unless technically necessary. It is only necessary when the
    # render method changes, and that is exactly what `method_version` records.
    reused = list(prior_incumbent or ())
    if reused:
        rows.extend(reused)
        incumbent_arm = 0

    for provider, n in ((challenger, attempts), (INCUMBENT, incumbent_arm)):
        for slug, difficulty in cases:
            cir = for_slug(slug)
            if cir is None:
                continue
            result = compile_cir(cir)
            if not result.ok:
                continue
            twin = build_twin(cir, result)
            for _ in range(n):
                try:
                    row = attempt(db, cir, twin, provider_key=provider,
                                  work_dir=work_dir, spent_so_far=spent, **judges)
                except CeilingReached as exc:
                    stopped = str(exc)
                    break
                row["difficulty"] = difficulty
                spent = round(spent + float(row.get("spent_cad") or 0.0), 4)
                rows.append(row)
            if stopped:
                break
        if stopped:
            break

    return {
        "ran": True,
        "challenger": challenger,
        "incumbent": INCUMBENT,
        "ceiling_cad": CEILING_CAD,
        # This run's own spend, which is what `experiment_spend_cad` sums and therefore must
        # never include the prior total, or the ceiling would compound every time it is read.
        "spent_cad": round(spent - prior, 4),
        "experiment_spent_cad": round(spent, 4),
        "prior_spend_cad": prior,
        "incumbent_reused": len(reused),
        "why_the_incumbent_was_not_re_rendered": (
            "its behaviour on this blocker is already measured under this render method, "
            "and re-buying it once per challenger would spend the ceiling to learn nothing"
            if reused else ""),
        "stopped_at_ceiling": bool(stopped),
        "why_stopped": stopped,
        "attempts": rows,
        "by_provider": {p: _summarise([r for r in rows if r.get("provider") == p])
                        for p in (challenger, INCUMBENT)},
        "verdict": _recommend(rows, challenger=challenger),
        "switches_nothing": (
            "this trial records evidence and changes no production setting. The image "
            "stack is the owner's decision and the instruction was to bring the measured "
            "evidence and a recommendation before changing it"),
    }


def _summarise(rows: list[dict]) -> dict:
    made = [r for r in rows if r.get("made")]
    if not made:
        return {"attempted": len(rows), "measured": False,
                "why": "no render on this provider completed, so there is nothing to score"}

    def rate(key) -> float:
        return round(sum(1 for r in made if not r.get(key)) / len(made), 3)

    usable = [r for r in made if r.get("usable_as_listing_asset")]
    spend = round(sum(float(r.get("spent_cad") or 0.0) for r in made), 4)
    # Consistency across frames: whether repeated renders of the same product agree on the
    # blocker. A provider that clears it once in three is not a provider that clears it.
    per_slug: dict[str, list[bool]] = {}
    for r in made:
        per_slug.setdefault(r["slug"], []).append(not r.get("texture_failed"))
    consistent = [s for s, oks in per_slug.items() if len(set(oks)) == 1]

    return {
        "attempted": len(rows),
        "measured": True,
        "renders": len(made),
        "texture_clear_rate": rate("texture_failed"),
        "structural_clear_rate": rate("structural_failed"),
        "product_truth_match_rate": round(
            sum(1 for r in made if r.get("product_truth") == "match") / len(made), 3),
        "photoreal_clear_rate": round(
            sum(1 for r in made if r.get("photographic_realism") == "clear") / len(made), 3),
        "usable_rate": round(len(usable) / len(made), 3),
        "consistent_on_the_blocker": sorted(consistent),
        "inconsistent_on_the_blocker": sorted(s for s in per_slug if s not in consistent),
        "total_spend_cad": spend,
        "cad_per_render": round(spend / len(made), 4),
        "cad_per_usable": round(spend / len(usable), 4) if usable else None,
        "failure_modes": sorted({f for r in made
                                 for f in (list(r.get("texture_failed") or ())
                                           + list(r.get("structural_failed") or ())
                                           + list(r.get("photoreal_failed") or ()))}),
    }


def _recommend(rows: list[dict], *, challenger: str) -> dict:
    """What the evidence supports, including "not enough of it".

    A provider does not win by clearing the blocker while regressing something else, and
    it does not win on one render either -- the sampling floor is the same one
    `visual.reliability` applies to everything else here.
    """
    ours = [r for r in rows if r.get("provider") == challenger and r.get("made")]
    theirs = [r for r in rows if r.get("provider") == INCUMBENT and r.get("made")]
    if not ours:
        return {"recommendation": "unproven",
                "why": f"no {challenger} render completed, so nothing about it was measured"}

    cleared = [r for r in ours if not r.get("texture_failed")]
    if not cleared:
        return {"recommendation": "keep_the_incumbent",
                "why": (f"{challenger} tiled on every render too, so the blocker is not "
                        f"specific to {INCUMBENT}. That is a finding about rendering "
                        f"crochet rather than about either provider, and switching would "
                        f"cost money and change nothing")}

    # It cleared the blocker at least once. Did it hold everything else?
    regressed = sorted({f for r in cleared
                        for f in (list(r.get("structural_failed") or ())
                                  + list(r.get("photoreal_failed") or ()))})
    truth_lost = [r for r in cleared if r.get("product_truth") != "match"]
    if regressed or truth_lost:
        return {"recommendation": "no_switch_on_this_evidence",
                "regressed": regressed,
                "product_truth_lost_on": sorted({r["slug"] for r in truth_lost}),
                "why": (f"{challenger} cleared the blocker and did not hold the rest. A "
                        f"provider that stops tiling and starts breaking structure, truth "
                        f"or photographic realism has traded one launch blocker for "
                        f"another, which is not a win")}

    if len(cleared) < len(ours):
        return {"recommendation": "promising_but_inconsistent",
                "cleared": len(cleared), "of": len(ours),
                "why": (f"{challenger} cleared the blocker on {len(cleared)} of "
                        f"{len(ours)} renders with nothing else regressing. Real, and not "
                        f"yet a rate: a provider that clears it sometimes needs a bounded "
                        f"retry budget costed before it is relied on")}

    return {"recommendation": "switch_worth_making",
            "why": (f"{challenger} cleared the blocker on every render, held structure, "
                    f"product truth and photographic realism, and {INCUMBENT} has failed "
                    f"the same check on every production render across three method "
                    f"versions. The owner decides; this is the evidence for it"),
            "incumbent_renders_compared": len(theirs)}
