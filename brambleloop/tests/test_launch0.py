"""Launch-0 assortment tests: the gates that keep the catalogue honest about its own size.

Plan behind these: `research/LAUNCH0_CATALOGUE.md`. Children's constraints: `intel/childrens.py`
and `research/CHILDRENS_CATEGORY.md`.

Four things are pinned, and each is a way the hard rule -- *do not manufacture catalogue
completion ahead of Product Truth* -- gets broken quietly.

**Everything listed for launch passes every gate, measured now.** Not "the three we chose were
fine on the day"; the gates run against freshly compiled CIRs every time the suite runs, so a
design edited under a product either keeps its name honest or leaves Launch-0.

**The gates catch injected defects, not only the real ones.** Every gate here currently has real
failures in the generated catalogue to catch, and that is exactly the situation in which a gate
can be written to catch those specific nine and nothing else. So each gate is also tested
against a CIR built to fail it -- which is the form that survives somebody fixing the catalogue.
A check tested only against the defect it was written for stops being tested the moment the
defect is fixed, which is the failure this repository keeps finding elsewhere.

**Pipeline and catalogue stay different populations.** The easiest way to grow a catalogue on
paper is to put an aspiration in the product list "so it is not forgotten".

**No product claims calibration.** `twin.calibrated` is False catalogue-wide, and the report
says so in the same dict that carries the measurements.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir.model import (CIR, Component, Gauge, Material, Op, Row,  # noqa: E402
                                   Seam)
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.intel import childrens as ch  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402

TODAY = date(2026, 9, 25)


def _panel_cir(title: str, *, colors: dict | None = None, make: int = 1,
               two_colours_in_a_row: bool = False, seams: list | None = None) -> CIR:
    """A minimal flat panel, shaped so each gate can be aimed at it deliberately.

    `two_colours_in_a_row` cannot be built at all today -- `Row.color` is one value and `Op`
    has no colour field -- so the colourwork gate's positive case is constructed by declaring
    two colours and alternating them by row, which is what the real catalogue does. The gate's
    job is to notice that this is a stripe.
    """
    colors = colors or {"cream": "#FAF6EB", "wine": "#6E1F2A"}
    names = list(colors)
    rows = [Row(index=i + 1, ops=[Op("sc", 10)], declared_count=10, turning_chain=1,
                color=names[i % len(names)] if two_colours_in_a_row else names[0])
            for i in range(6)]
    return CIR(
        slug="test-panel", title=title, version="1.0.0", construction="flat_rows",
        risk_class="A", colors=dict(colors),
        gauge=Gauge(stitches_per_10cm=16, rows_per_10cm=18, stitch_type="sc", hook_mm=5.0),
        materials=[Material(name="worsted acrylic", yarn_weight="worsted", color_id=c)
                   for c in names],
        components=[Component(name="panel", construction="flat_rows", rows=rows,
                              foundation=10, foundation_kind="chain", make=make)],
        assembly=list(seams or []),
        designer_notes="A test panel.")


def _twin_for(cir: CIR):
    result = compile_cir(cir)
    assert result.ok, [str(f) for f in result.errors]
    return build_twin(cir, result)


# ---- the launch set, measured rather than declared -------------------------


def test_everything_listed_for_launch_passes_every_gate():
    """The one assertion the plan document is allowed to make, recomputed here."""
    assert l0.launch0_is_all_gate_clean()
    for product in l0.launch0():
        assert product["passes_gates"], (product["slug"], product["gates"])
        assert product["certified"]["compiles_with_no_errors"], product["slug"]
        assert product["certified"]["compiles_with_no_warnings"], product["slug"]


def test_launch0_is_small_and_every_item_is_reachable():
    """Small is the feature. Three listings, and each one resolves to a real builder."""
    assert 1 <= len(l0.LAUNCH0_SLUGS) <= 5, l0.LAUNCH0_SLUGS
    for slug in l0.LAUNCH0_SLUGS:
        cand = l0.candidate(slug)
        assert cand.variants, slug
        for variant in cand.variants:
            cir = l0.cir_for(variant.build)
            assert cir.components, (slug, variant.key)


def test_every_launch0_product_reports_finished_measurements_and_admits_they_are_arithmetic():
    """A measurement with no sample behind it must say so where the number is read."""
    for product in l0.launch0():
        assert product["certified"]["finished_measurements_computed"], product["slug"]
        assert product["aspiration"]["physically_calibrated"] is False, product["slug"]
        assert "twin.calibrated is False" in product["aspiration"]["why_not"]
        for variant in product["variants"]:
            assert variant["calibrated"] is False, (product["slug"], variant["variant"])


def test_no_launch0_product_is_calibrated_and_the_report_leads_with_that():
    report = l0.report(today=TODAY)
    assert report["calibration"]["any_product_calibrated"] is False
    assert "twin.calibrated is False catalogue-wide" in report["calibration"]["why"]


def test_every_candidate_states_what_would_disqualify_it_and_what_is_aspiration():
    """A product with no disqualifier is a product nobody has tried to break."""
    for cand in l0.CANDIDATES:
        assert cand.disqualifiers, cand.slug
        assert cand.aspiration, cand.slug
        assert cand.what_it_is and cand.why_at_launch, cand.slug


# ---- the gates, against injected defects ----------------------------------


def test_title_promise_gate_catches_a_count_the_cir_does_not_make():
    bad = _panel_cir("Ornament Set (6)", make=1)
    verdict = l0.title_promise(bad)
    assert verdict["claimed"] == 6 and verdict["makes"] == 1
    assert verdict["backed"] is False, verdict

    good = _panel_cir("Ornament Set (6)", make=6)
    assert l0.title_promise(good)["backed"] is True


def test_title_promise_gate_reads_a_counting_word_as_a_count():
    assert l0.title_promise(_panel_cir("Placemat Pair", make=1))["backed"] is False
    assert l0.title_promise(_panel_cir("Placemat Pair", make=2))["backed"] is True
    assert l0.title_promise(_panel_cir("Basket Trio", make=2))["backed"] is False


def test_title_promise_gate_reads_an_unnumbered_plural_as_more_than_one():
    """"Set" with no number promises more than one piece and nothing else."""
    assert l0.title_promise(_panel_cir("Coaster Set", make=1))["backed"] is False
    assert l0.title_promise(_panel_cir("Coaster Set", make=4))["backed"] is True


def test_title_promise_gate_does_not_invent_a_claim_that_is_not_there():
    verdict = l0.title_promise(_panel_cir("Cloudline Baby Blanket", make=1))
    assert verdict["claimed"] is None and verdict["plural_markers"] == ()
    assert verdict["backed"] is True


def test_assembly_gate_catches_an_assembled_form_with_no_assembly():
    bad = _panel_cir("Bunting Garland", make=1)
    assert l0.assembly_promise(bad)["backed"] is False

    with_seam = _panel_cir("Bunting Garland", make=1,
                           seams=[Seam(method="whipstitch", piece_a="panel",
                                       piece_b="panel")])
    assert l0.assembly_promise(with_seam)["backed"] is True

    many_pieces = _panel_cir("Bunting Garland", make=8)
    assert l0.assembly_promise(many_pieces)["backed"] is True


def test_assembly_gate_is_silent_about_a_single_piece_object():
    assert l0.assembly_promise(_panel_cir("Storage Basket"))["backed"] is True


def test_fabric_gate_refuses_a_colourwork_claim_a_striped_fabric_cannot_keep():
    """A two-colour motif needs two colours in one row; this fabric has one per row."""
    bad = _panel_cir("Overlay Mosaic Throw", two_colours_in_a_row=True)
    verdict = l0.fabric_truth(bad, _twin_for(bad))
    assert verdict["max_colours_in_one_row"] == 1, verdict
    assert verdict["colourwork_claims"] == ("mosaic", "overlay")
    assert verdict["backed"] is False


def test_fabric_gate_is_silent_when_no_technique_is_claimed():
    plain = _panel_cir("Cloudline Baby Blanket", two_colours_in_a_row=True)
    verdict = l0.fabric_truth(plain, _twin_for(plain))
    assert verdict["colourwork_claims"] == ()
    assert verdict["backed"] is True


def test_fabric_gate_reads_the_designer_notes_as_well_as_the_title():
    """A claim made in prose is a claim. The generated catalogue makes most of them there."""
    cir = _panel_cir("A Blanket")
    cir.designer_notes = "Worked in tapestry crochet on a 12-stitch repeat."
    verdict = l0.fabric_truth(cir, _twin_for(cir))
    assert "tapestry" in verdict["colourwork_claims"]
    assert verdict["backed"] is False


def test_the_cir_capability_the_gate_depends_on_is_measured_not_stated():
    """When per-stitch colour arrives, the gate re-opens by itself.

    This asserts the measurement reads the dataclass rather than returning a constant, which is
    what stops the finding becoming a stale sentence in a docstring. It does not assert the
    current answer as a permanent fact -- the answer is allowed to change, and when it does the
    colourwork half of the catalogue becomes buildable.
    """
    from dataclasses import fields as dc_fields

    op_field_names = {f.name for f in dc_fields(Op)}
    assert l0.per_stitch_colour_expressible() == bool(
        op_field_names & {"color", "colour"})
    assert l0.per_stitch_reach_down_expressible() == bool(
        op_field_names & {"into", "row_below", "below"})


# ---- the exclusions are the load-bearing part of a small assortment --------


def test_the_products_left_out_are_left_out_for_a_measured_reason():
    """Every excluded CIR is either gate-failing with a reason, or held on assortment grounds.

    No third category. A product excluded with no reason recorded is a product somebody
    dropped, and next month nobody will know whether it was truth or taste.
    """
    rows = l0.excluded_from_launch0()
    assert len(rows) >= 15, len(rows)
    for row in rows:
        if row.get("in_launch0"):
            assert row["gate_clean"], row["key"]
            continue
        assert row["gate_reasons"] or row.get("held_back_on"), row


def test_the_exclusion_survey_covers_every_product_with_a_cir():
    """A survey that quietly skips a product is how an over-claiming title stays unnoticed."""
    from brambleloop.products import builder, nordic_forest

    keys = {row["key"] for row in l0.excluded_from_launch0()}
    for slug in builder.CATALOGUE:
        assert slug in keys, slug
    for size in nordic_forest.SIZES:
        assert f"nordic-forest-{size}" in keys, size
    assert {"market-basket-small", "market-basket-medium", "market-basket-large",
            "hexagon-coaster-set"} <= keys


def test_at_least_one_product_is_excluded_on_taste_rather_than_on_truth():
    """The reserve exists so that "why only three" has an answer other than "that is all we have"."""
    held = [r for r in l0.excluded_from_launch0()
            if not r.get("in_launch0") and r.get("held_back_on")]
    assert held, "no product is held back on assortment grounds, so small is not a choice"


# ---- the children's half ---------------------------------------------------


def test_the_two_childrens_products_are_the_sub_categories_the_research_leads_with():
    """Nursery decor and baby blankets first; not amigurumi, not a fitted garment."""
    views = {s: l0.childrens_view(l0.candidate(s)) for s in l0.LAUNCH0_SLUGS}
    childrens = {s: v for s, v in views.items() if v["is_a_childrens_product"]}
    assert childrens, "Launch-0 carries no children's product at all"
    subs = {v["subcategory"] for v in childrens.values()}
    assert subs <= {"nursery_decor", "keepsake_blanket", "baby_blanket"}, subs
    for view in childrens.values():
        assert view["verdict"] in (ch.LEAD, ch.BUILD), view["subcategory"]


def test_a_non_childrens_product_says_so_rather_than_being_silent():
    view = l0.childrens_view(l0.candidate("hexagon-coaster-set"))
    assert view["is_a_childrens_product"] is False
    assert view["why"]


def test_no_launch0_product_carries_a_detachable_applied_part():
    """Under 36 months a detachable part is refused, not warned about, so none exists."""
    for slug in l0.LAUNCH0_SLUGS:
        view = l0.childrens_view(l0.candidate(slug))
        if not view["is_a_childrens_product"]:
            continue
        assert view["applied_parts"] == ()
        assert view["as_built"]["refusals"] == [], (slug, view["as_built"])
        for part in view["applied_parts"]:            # pragma: no cover - empty by design
            assert ch.classify_part(part) == "integral", part


def test_the_committed_statements_are_exactly_what_childrens_requires():
    """The statement set is computed by the module that holds the regulations, never retyped."""
    for slug in l0.LAUNCH0_SLUGS:
        cand = l0.candidate(slug)
        view = l0.childrens_view(cand)
        if not view["is_a_childrens_product"]:
            continue
        required = ch.required_statements(cand.subcategory, cand.audience)
        assert set(cand.committed_statements) == set(required), slug
        assert view["commitment_covers_requirement"], slug


def test_the_statement_gap_is_measured_on_the_document_and_is_closed():
    """The gap this module measured on 2026-09-25 has closed, and the instrument changed.

    What it used to assert: `as_built["ready_to_ship"] is False` and a non-empty
    `statements_missing`, because `childrens_view` passed `()` for "what the deliverable
    states today" and the deliverable stated nothing. That was honest and it was a constant,
    so it would have gone on reporting a gap after the gap closed, and reported none if
    somebody had changed the constant.

    What it asserts now: `as_built` is read out of the rendered customer PDF, and the
    products carry their sets. `as_planned` still exists and still differs in what it is
    asking -- the commitment, not the artefact -- which is why both are kept.
    """
    for slug in l0.LAUNCH0_SLUGS:
        cand = l0.candidate(slug)
        view = l0.childrens_view(cand)
        if not view["is_a_childrens_product"]:
            continue
        assert view["as_built"]["subject_is_allowed"] is True, slug
        assert view["as_built"]["statements_missing"] == [], (slug, view["as_built"])
        assert view["as_built"]["ready_to_ship"] is True, slug
        assert view["as_planned"]["ready_to_ship"] is True, slug
        # Measured, not declared: the statements came out of the PDF, and they are the set
        # the regulations module requires rather than whatever the renderer felt like.
        assert set(view["as_built_statements"]) == set(view["required_statements"]), slug
        assert "extracted" in view["as_built_measured_on"]


def test_the_rendering_gap_reads_the_artefact_rather_than_grepping_the_source():
    """A grep over `publish/*.py` cannot answer a question about a PDF.

    The old instrument searched three packages for a statement's distinctive words. It was
    the right alarm when it found zero files, and it is the wrong instrument: a comment
    saying "the choking statement is missing" satisfies it. The headline now comes from text
    extracted from the rendered document, in both terminologies sold, and the old reading is
    kept beside it so the history of the measurement is not lost.
    """
    gap = l0.statement_rendering_gap()
    assert gap["measured_on"] == "the text extracted from the rendered customer PDF"
    assert gap["can_render_the_statement_set"] is True
    assert gap["statements_missing"] == []
    assert gap["variants"], "a gap report with no variants proves nothing"
    assert {v["terminology"] for v in gap["variants"]} == {"US", "UK"}
    for row in gap["variants"]:
        assert row["complete"], row
        assert set(row["present"]) == set(row["required"]), row
    # The old reading survives, and is labelled as not being the answer.
    assert "publish/pdf.py" in gap["source_grep"]["files_mentioning_a_statement"]
    assert "artefact" in gap["source_grep"]["why_it_is_not_the_answer"]


def test_a_childrens_title_with_no_audience_assignment_is_reported():
    """The safety block is keyed on the assignment, so a missing assignment is silent.

    Found by this check: `nordic-forest-mosaic-throw-baby` is titled "Nordic Forest Overlay
    Mosaic Blanket (Baby)", carries no children's sub-category, and would therefore render
    with no safety block while every other gate passed. It is excluded from Launch-0 on the
    colourwork gate, so nothing ships today -- which is luck, not design. Reported rather
    than blocking, because whether a product is merchandised to a child is a decision and a
    title word is evidence for it.
    """
    unassigned = {row["slug"] for row in l0.childrens_titles_without_an_assignment()}
    assert "nordic-forest-mosaic-throw-baby" in unassigned, unassigned
    # And the products that DO carry an assignment are not in the list.
    assert "cloudline-baby-blanket" not in unassigned
    assert "market-basket-small" not in unassigned
    for row in l0.childrens_titles_without_an_assignment():
        assert row["words"] and row["why"]


def test_the_audience_assignment_is_computed_from_the_candidates_not_listed_twice():
    """A declared slug list would go stale the first time a variant's builder changed."""
    assert l0.childrens_assignment("cloudline-baby-blanket") == ("baby_blanket", ch.UNDER_3)
    assert l0.childrens_assignment("market-basket-large") == ("nursery_decor", ch.UNDER_3)
    assert l0.childrens_assignment("hexagon-coaster-set") is None
    assert l0.childrens_assignment("harvest-table-runner") is None
    for slug in l0.LAUNCH0_SLUGS:
        cand = l0.candidate(slug)
        for variant in cand.variants:
            got = l0.childrens_assignment(l0.cir_for(variant.build).slug)
            if cand.subcategory is None:
                assert got is None, slug
            else:
                assert got == (cand.subcategory, cand.audience), slug


def test_a_prohibited_subject_would_be_refused_even_dressed_as_nursery_decor():
    """The gate that matters most is the one no current product trips."""
    concept = ch.Concept(subject="Nursery Crib Bumper Pattern", subcategory="nursery_decor",
                         audience=ch.UNDER_3)
    findings = ch.assess(concept)
    assert not ch.publishable(concept)
    assert "PROHIBITED_SUBJECT" in {f.code for f in findings}


def test_the_subjects_we_never_publish_are_enumerated_from_the_constraint_module():
    never = l0.never_published()
    slugs = {row["slug"] for row in never}
    assert {"infant_sleep_accessory", "baby_carrier", "childrens_sleepwear",
            "rattle_or_teether"} <= slugs, slugs
    for row in never:
        assert row["why"] and row["constraints"]


# ---- seasonality ----------------------------------------------------------


def test_the_two_measured_series_are_counter_seasonal():
    """Amigurumi's annual maximum lands in baby-occasion's annual minimum."""
    s = l0.seasonality()
    assert s["series"]["Amigurumi"]["peak_month"] == "2025-12"
    assert s["series"]["Baby_shower"]["trough_month"] == "2025-12"
    assert s["counter_seasonal"] is True
    assert s["label"] == l0.SOURCED and s["blend_label"] == l0.DERIVED


def test_a_portfolio_holding_both_swings_less_than_either_alone():
    """The research asserted this; it is arithmetic, so it is computed."""
    s = l0.seasonality()
    ami = s["series"]["Amigurumi"]["peak_over_trough"]
    baby = s["series"]["Baby_shower"]["peak_over_trough"]
    assert s["blended"]["peak_over_trough"] < min(ami, baby), s["blended"]
    assert s["flatter_than_either_alone"] is True


def test_the_pairing_conclusion_does_not_depend_on_the_mix_weight():
    """A finding that only holds at exactly 50/50 is a coincidence, not a portfolio argument."""
    baby = l0.seasonality()["series"]["Baby_shower"]["peak_over_trough"]
    for share in (0.3, 0.4, 0.5, 0.6):
        blended = l0.seasonality(share)["blended"]["peak_over_trough"]
        assert blended < baby, (share, blended)


def test_the_series_carries_its_source_and_its_caveats():
    s = l0.seasonality()
    assert s["source"].startswith("https://wikimedia.org/")
    assert len(s["caveats"]) >= 3
    assert len(l0.MONTHS) == 12
    for name, values in l0.PAGEVIEWS.items():
        assert len(values) == 12, name


def test_an_impossible_mix_weight_raises_rather_than_being_clamped():
    for share in (-0.1, 1.5):
        try:
            l0.seasonality(share)
        except ValueError:
            pass
        else:                                          # pragma: no cover
            raise AssertionError(f"accepted a share of {share}")


# ---- the pipeline ---------------------------------------------------------


def test_the_pipeline_is_not_the_catalogue():
    assert l0.pipeline_is_not_catalogue()
    catalogue_slugs = {c.slug for c in l0.CANDIDATES}
    for entry in l0.PIPELINE:
        assert entry.slug not in catalogue_slugs, entry.slug


def test_every_pipeline_entry_names_a_blocker_and_who_owns_it():
    """An aspiration with no blocker is either already possible or nobody has looked."""
    for entry in l0.PIPELINE:
        assert entry.blocked_on, entry.slug
        assert entry.owner_of_the_blocker, entry.slug
        assert entry.why_this_position, entry.slug


def test_no_pipeline_entry_claims_a_cir():
    for row in l0.pipeline_plan(today=TODAY):
        assert row["has_a_cir"] is False, row["slug"]


def test_the_pipeline_order_matches_the_researched_entry_order():
    """Nursery and keepsake before amigurumi, amigurumi before fitted garments."""
    waves = {e.subcategory: e.wave for e in l0.PIPELINE if e.subcategory}
    assert waves["keepsake_blanket"] <= waves["lovey"], waves
    assert waves["lovey"] < waves["childrens_garment"], waves
    assert waves["baby_wearables"] < waves["childrens_garment"], waves


def test_the_seasonal_entry_carries_a_computed_launch_date_and_names_its_evidence():
    """The date is arithmetic over assumptions, and the plan says none is measured yet."""
    rows = {r["slug"]: r for r in l0.pipeline_plan(today=TODAY)}
    timing = rows["amigurumi-lovey-embroidered-face"]["launch_timing"]
    assert timing["latest_effective_launch"] < timing["event_date"]
    assert timing["preferred_launch"] <= timing["latest_effective_launch"]
    assert timing["work_must_start_by"] <= timing["preferred_launch"]
    assert timing["every_assumption_measured"] is False


def test_the_amigurumi_entry_defaults_to_an_embroidered_face():
    """The research's positioning decision, checked against the constraint module's vocabulary."""
    entry = next(e for e in l0.PIPELINE if e.subcategory == "lovey")
    assert "embroidered" in entry.title.lower() or "embroidered" in entry.what_it_is.lower()
    assert "embroidered_eyes" in ch.INTEGRAL_FEATURES
    assert "safety_eyes" in ch.DETACHABLE_APPLIED_PARTS
    # And the refusal it protects: safety eyes on an under-3 lovey is not a warning case.
    concept = ch.Concept(subject="Bunny Lovey", subcategory="lovey", audience=ch.UNDER_3,
                         applied_parts=("safety_eyes",))
    assert not ch.publishable(concept)


# ---- prices and make time -------------------------------------------------


def test_every_price_clears_the_pricing_module_rather_than_being_asserted():
    for slug in l0.LAUNCH0_SLUGS:
        plan = l0.price_plan(l0.candidate(slug))
        assert plan["price_cad"] >= 3.00, plan
        assert plan["net_cad_after_fees"] > 0, plan
        assert plan["band_basis"] in l0.LABELS and plan["band_why"], plan
        assert plan["held_at_proposal"], plan


def test_a_price_band_must_declare_how_it_was_established():
    try:
        l0.PriceBand(4.0, 12.0, proposed_cad=6.0, basis="gut feel", why="")
    except ValueError:
        pass
    else:                                              # pragma: no cover
        raise AssertionError("a price band with an unlabelled basis was accepted")


def test_an_inverted_price_band_raises():
    try:
        l0.PriceBand(12.0, 4.0, proposed_cad=6.0, basis=l0.SOURCED, why="x")
    except ValueError:
        pass
    else:                                              # pragma: no cover
        raise AssertionError("an inverted band was accepted")


def test_make_time_is_multiplied_by_the_pieces_the_pattern_makes():
    """A set of four coasters is not a one-piece make, and the listing must not say it is.

    Checked against an independent single-coaster estimate, not against the row's own total
    divided by four: the previous version of this test asserted
    `hours_total == hours_per_piece * 4` where `hours_per_piece` was the number the total had
    been computed from, so it held for any figure whatsoever. It passed throughout the period
    when this function was building a twin for the first component only.
    """
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.seasonal import leadtime

    rows = {r["variant"]: r for r in l0.make_time(l0.candidate("hexagon-coaster-set"))["variants"]}
    row = rows["set_of_four"]
    assert row["pieces"] == 4
    assert row["evidence"] == "assumed"

    cir = l0.cir_for([v for v in l0.candidate("hexagon-coaster-set").variants
                      if v.key == "set_of_four"][0].build)
    compiled = compile_cir(cir)
    assert sum(c.make for c in cir.components) == 4
    one = leadtime.estimate_make_hours(
        [build_twin(cir, compiled, component=cir.components[0].name)],
        makes={cir.components[0].name: 1})
    assert abs(row["hours_total"] - one.hours * 4) < 0.05, (row, one.hours)
    assert [c["make"] for c in row["per_component"]] == [4]


def test_make_time_is_labelled_an_estimate_because_the_stitch_rate_is_assumed():
    for slug in l0.LAUNCH0_SLUGS:
        estimate = l0.make_time(l0.candidate(slug))
        assert estimate["label"] == l0.ESTIMATED, slug
        assert "assumed" in estimate["basis"], slug


# ---- the report -----------------------------------------------------------


def test_the_report_carries_no_demand_or_velocity_score_for_a_product():
    """Same refusal intel.childrens makes, for the same reason, one layer up.

    A plan is where an invented 0.8 is most tempting and most damaging: it sits beside compiled
    measurements and borrows their authority. The pageview series is measurement and is labelled
    SOURCED; there is no per-product score anywhere.
    """
    from dataclasses import fields as dc_fields

    forbidden = ("demand", "competition", "score", "velocity", "volume", "revenue", "rank",
                 "conversion")
    for cls in (l0.Candidate, l0.Variant, l0.PipelineEntry):
        names = [f.name for f in dc_fields(cls)]
        for name in names:
            assert not any(word in name for word in forbidden), (cls.__name__, name)


def test_the_report_runs_end_to_end_and_answers_the_hard_rule():
    report = l0.report(today=TODAY)
    assert report["snapshot"] == l0.SNAPSHOT_DATE
    assert report["launch0_is_all_gate_clean"] is True
    assert report["pipeline_is_not_catalogue"] is True
    assert len(report["launch0"]) == len(l0.LAUNCH0_SLUGS)
    assert report["cir_capability"]["per_stitch_colour"] in (True, False)
    assert report["never_published"]
    assert report["prices"] and report["make_time"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
