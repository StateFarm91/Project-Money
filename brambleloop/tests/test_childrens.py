"""Children's-audience tests: the constraints that decide what we may publish for a child.

Research behind these: `research/CHILDRENS_CATEGORY.md`, 2026-09-24.

Three things are being pinned here, and each of them is a way this could go wrong quietly.

The first is that **a refusal stays a refusal**. Under 36 months a detachable applied part is
banned outright, not warned about, and the easiest future regression is somebody softening it to
a statement requirement because a product they liked failed. The tests assert the severity, not
only the finding.

The second is that **an unrecognised part blocks**. A vocabulary that silently treats what it
has never seen as safe reports a clean assessment for exactly the products nobody has thought
about, and it does so in the direction that hurts a child.

The third is that **no market number leaks into the safety table**. The module's authority is
its citations; a demand score sitting beside a regulation would borrow that authority for a
guess. There is a test whose whole job is to fail when somebody adds one.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.intel import childrens as ch  # noqa: E402
from brambleloop.intel.pods import POD_KEYS  # noqa: E402


def _concept(**kw) -> ch.Concept:
    base = dict(subject="Crochet Bear Amigurumi Pattern", subcategory="amigurumi_toy",
                audience=ch.THREE_TO_SIX)
    base.update(kw)
    return ch.Concept(**base)


def _codes(findings) -> set[str]:
    return {f.code for f in findings}


# ---- the evidence is attached, and its weaknesses are enumerable -----------


def test_every_constraint_names_a_source_that_exists():
    """A rule whose citation has gone missing looks exactly like one that can be re-checked."""
    assert ch.unsourced_constraints() == (), ch.unsourced_constraints()
    assert len(ch.CONSTRAINTS) >= 12


def test_every_source_carries_a_url_a_date_and_how_it_was_obtained():
    for key, s in ch.SOURCES.items():
        assert s.url.startswith("https://"), (key, s.url)
        assert s.read_on == ch.SNAPSHOT_DATE, (key, s.read_on)
        assert s.retrieval in ch.RETRIEVALS, (key, s.retrieval)
        assert s.jurisdiction and s.title


def test_the_sources_we_could_not_read_are_listed_rather_than_glossed():
    """etsy.com returns 403 here, so the platform prohibitions are second-hand.

    The gap is a field on every source rather than a caveat in prose, so it can be counted.
    This test asserts the counting works in both directions: the Etsy policy is in the list,
    and a page we genuinely fetched is not.
    """
    unfetched = ch.unfetched_sources()
    assert "etsy_children_policy" in unfetched
    assert "cpsc_small_parts" not in unfetched
    assert all(ch.SOURCES[k].retrieval != ch.FETCHED for k in unfetched)


def test_the_snapshot_is_dated():
    """Safety guidance with no date is a claim about the past that reads as a claim about now."""
    assert ch.SNAPSHOT_DATE == "2026-09-24"


# ---- the 36-month line -----------------------------------------------------


def test_the_regulatory_boundary_is_thirty_six_months_not_a_word():
    assert ch.age_band_for_months(35) == ch.UNDER_3
    assert ch.age_band_for_months(36) == ch.THREE_TO_SIX
    assert ch.age_band_for_months(71) == ch.THREE_TO_SIX
    assert ch.age_band_for_months(72) == ch.SIX_TO_TWELVE
    assert ch.age_band_for_months(156) == ch.OVER_TWELVE


def test_every_band_says_why_its_boundary_is_where_it_is():
    for key, band in ch.AGE_BANDS.items():
        assert len(band.why_the_boundary) > 60, key


# ---- small parts -----------------------------------------------------------


def test_safety_eyes_under_three_are_refused_not_warned_about():
    """16 CFR 1501 bans the part; no sentence at the bottom of page one satisfies that."""
    findings = ch.assess(_concept(audience=ch.UNDER_3, applied_parts=("safety_eyes",)))
    hit = next(f for f in findings if f.code == "SMALL_PART_UNDER_3")
    assert hit.severity == ch.REFUSE, hit
    assert "cpsc.gov" in hit.source_url
    assert ch.publishable(_concept(audience=ch.UNDER_3, applied_parts=("safety_eyes",))) is False


def test_an_embroidered_face_under_three_is_publishable():
    """The whole point of the default: an integral feature cannot detach."""
    concept = _concept(
        subcategory="lovey", audience=ch.UNDER_3,
        applied_parts=("embroidered_eyes", "embroidered_nose"),
        stated_statements=tuple(ch.required_statements("lovey", ch.UNDER_3)))
    assert ch.assess(concept) == [], ch.assess(concept)
    assert ch.publishable(concept) is True


def test_a_part_nobody_has_classified_blocks_rather_than_passes():
    """Unassessed is not safe. This is the direction the default has to fail in."""
    findings = ch.assess(_concept(applied_parts=("magnetic_clasp",)))
    hit = next(f for f in findings if f.code == "UNRECOGNISED_PART")
    assert hit.severity == ch.REFUSE
    assert ch.classify_part("magnetic_clasp") == "unknown"
    assert ch.classify_part("safety_eyes") == "detachable"
    assert ch.classify_part("embroidered_eyes") == "integral"


def test_the_two_part_vocabularies_do_not_overlap():
    assert not (ch.DETACHABLE_APPLIED_PARTS & ch.INTEGRAL_FEATURES)


def test_three_to_six_permits_the_part_and_requires_the_statement():
    """In this band the part is lawful and the silence is not."""
    without = ch.assess(_concept(applied_parts=("safety_eyes",)))
    hit = next(f for f in without if f.code == "CHOKING_STATEMENT_MISSING")
    assert hit.severity == ch.REQUIRE_STATEMENT
    assert ch.CHOKING_WARNING in hit.detail

    stated = ch.assess(_concept(
        applied_parts=("safety_eyes",),
        stated_statements=tuple(ch.required_statements("amigurumi_toy", ch.THREE_TO_SIX))))
    assert "CHOKING_STATEMENT_MISSING" not in _codes(stated)


def test_the_choking_statement_is_the_regulated_wording():
    assert ch.CHOKING_WARNING.startswith("WARNING: CHOKING HAZARD")
    assert "under 3 yrs" in ch.CHOKING_WARNING


# ---- drawstrings -----------------------------------------------------------


def test_a_hood_or_neck_tie_on_a_childs_garment_is_refused():
    """16 CFR 1120 lists such a garment as a substantial product hazard.

    A crochet pattern reaches this constraint by accident -- a chained tie through the neckline
    is the obvious way to close a hooded cardigan -- which is exactly why it is checked rather
    than remembered.
    """
    findings = ch.assess(_concept(subcategory="childrens_garment", audience=ch.SIX_TO_TWELVE,
                                  neck_or_hood_drawstring=True))
    hit = next(f for f in findings if f.code == "NECK_OR_HOOD_DRAWSTRING")
    assert hit.severity == ch.REFUSE


def test_a_waist_tie_is_measured_against_three_inches_not_judged():
    at_limit = ch.assess(_concept(subcategory="childrens_garment", audience=ch.SIX_TO_TWELVE,
                                  waist_tie_inches_outside_channel=3.0))
    assert "TIE_TOO_LONG" not in _codes(at_limit)

    over = ch.assess(_concept(subcategory="childrens_garment", audience=ch.SIX_TO_TWELVE,
                              waist_tie_inches_outside_channel=4.5))
    assert "TIE_TOO_LONG" in _codes(over)

    toggled = ch.assess(_concept(subcategory="childrens_garment", audience=ch.SIX_TO_TWELVE,
                                 waist_tie_inches_outside_channel=2.0,
                                 tie_ends_in_toggle_or_knot=True))
    assert "TIE_END_ATTACHMENT" in _codes(toggled)


# ---- subjects whose instructions we do not publish -------------------------


def test_the_marketplace_prohibition_reaches_the_pattern_not_only_the_product():
    """Etsy's policy names patterns, designs and instructions. A PDF can action a shop."""
    banned = ch.prohibited_subject("Crochet Crib Bumper Pattern PDF")
    assert banned is not None and banned.slug == "crib_bumper"
    assert ch.CONSTRAINTS[banned.constraint].severity == ch.REFUSE


def test_the_prohibitions_match_on_words_so_plurals_and_phrases_both_land():
    for title, slug in (
        ("Crochet Crib Bumpers Pattern", "crib_bumper"),
        ("Baby Nest Lounger Crochet Pattern", "infant_sleep_pillow"),
        ("Crochet Ring Sling Pattern for Newborns", "baby_sling"),
        ("Toddler Nightgown Crochet Pattern", "childrens_sleepwear"),
        ("Crochet Baby Neck Float", "infant_neck_float"),
    ):
        hit = ch.prohibited_subject(title)
        assert hit is not None and hit.slug == slug, (title, hit)


def test_an_ordinary_baby_blanket_is_not_swept_up_by_the_prohibitions():
    """A prohibition list that refuses the category's best product is not a safety feature."""
    assert ch.prohibited_subject("Heirloom Baby Blanket Crochet Pattern") is None
    assert ch.prohibited_subject("Nursery Bunting Crochet Pattern") is None


def test_the_never_subcategories_refuse_even_with_every_statement_present():
    """No amount of good labelling makes a crocheted sling publishable."""
    for slug in ("infant_sleep_accessory", "baby_carrier", "childrens_sleepwear"):
        concept = ch.Concept(subject="a well-written pattern", subcategory=slug,
                             audience=ch.UNDER_3,
                             stated_statements=tuple(ch.STATEMENTS))
        findings = ch.assess(concept)
        assert "SUBCATEGORY_NOT_PUBLISHED" in _codes(findings), slug
        assert ch.publishable(concept) is False, slug


# ---- the statement set -----------------------------------------------------


def test_a_baby_blanket_must_state_the_safe_sleep_position():
    """AAP 2022 keeps loose bedding out of the sleep area, and the blanket is the audience's
    most merchandised object. The answer is to say so, not to leave the buyer to assume."""
    assert "safe_sleep" in ch.required_statements("baby_blanket", ch.UNDER_3)
    findings = ch.assess(ch.Concept(subject="Heirloom Baby Blanket Pattern",
                                    subcategory="baby_blanket", audience=ch.UNDER_3))
    missing = [f for f in findings if f.code == "STATEMENT_MISSING"]
    assert any("sleep space" in f.detail for f in missing), missing


def test_a_mobile_must_state_when_it_comes_out_of_the_cot():
    assert "mobile_removal" in ch.required_statements("crib_mobile", ch.UNDER_3)


def test_every_children_pattern_points_at_the_maker_who_sells():
    """A buyer who sells finished items becomes the manufacturer. We are not entitled to let
    them assume otherwise, and we are not their lawyer either."""
    for slug, sub in ch.SUBCATEGORIES.items():
        if sub.verdict == ch.NEVER:
            continue
        for audience in sub.audiences:
            needed = ch.required_statements(slug, audience)
            assert "selling_finished_items" in needed, (slug, audience)
            assert "not_legal_advice" in needed, (slug, audience)


def test_every_named_statement_exists_and_is_explained():
    for slug, sub in ch.SUBCATEGORIES.items():
        for statement in sub.statements:
            assert statement in ch.STATEMENTS, (slug, statement)
    for key, text in ch.STATEMENTS.items():
        assert len(text) > 40, key


def test_a_complete_pattern_produces_no_findings_at_all():
    """The assessment has to be satisfiable, or it is a refusal wearing a checklist's clothes."""
    for slug, sub in ch.SUBCATEGORIES.items():
        if sub.verdict == ch.NEVER:
            continue
        for audience in sub.audiences:
            concept = ch.Concept(subject=f"a {sub.label}", subcategory=slug, audience=audience,
                                 applied_parts=("embroidered_eyes",),
                                 stated_statements=ch.required_statements(slug, audience))
            assert ch.assess(concept) == [], (slug, audience, ch.assess(concept))


# ---- the table itself ------------------------------------------------------


def test_every_subcategory_points_at_a_form_pod_that_exists():
    """Children's is an audience, not a pod. Each sub-category names the form that owns it."""
    for slug, sub in ch.SUBCATEGORIES.items():
        assert sub.pod in POD_KEYS, (slug, sub.pod)
        assert sub.verdict in ch.VERDICTS, (slug, sub.verdict)
        assert sub.audiences and all(a in ch.AGE_BANDS for a in sub.audiences), slug
        assert all(c in ch.CONSTRAINTS for c in sub.constraints), slug
        assert len(sub.why) > 60, slug


def test_the_table_covers_both_ends_of_the_decision():
    verdicts = {s.verdict for s in ch.SUBCATEGORIES.values()}
    assert ch.LEAD in verdicts and ch.NEVER in verdicts
    assert len(ch.SUBCATEGORIES) >= 12


def test_no_demand_price_or_competition_number_lives_in_the_safety_table():
    """The module's authority is its citations. A score nobody measured spends that on a guess."""
    assert ch.carries_no_market_numbers() is True


def test_every_constraint_states_what_it_measures_and_why():
    for key, c in ch.CONSTRAINTS.items():
        assert c.severity in ch.SEVERITIES, key
        assert len(c.measures) > 40, key
        assert len(c.why) > 80, key
        assert c.jurisdictions, key


# ---- sizing ----------------------------------------------------------------


def test_the_cyc_tables_match_the_published_charts():
    assert ch.chest_for_size("3 months").chest_in == 16.0
    assert ch.chest_for_size("24 months").chest_cm == 50.5
    assert ch.chest_for_size("8").chest_in == 26.5
    assert ch.chest_for_size("16").chest_cm == 82.5


def test_sizes_increase_monotonically_within_each_chart():
    """A grading table that is not monotonic produces a size 8 smaller than a size 6."""
    for chart in (ch.BABY_SIZES, ch.CHILD_YOUTH_SIZES):
        chests = [r.chest_in for r in chart]
        assert chests == sorted(chests) and len(set(chests)) == len(chests), chart
        for row in chart:
            # The published charts round to the nearest half centimetre, so the ratio is near
            # 2.54 rather than exactly it. A transposed column would be nowhere near.
            assert 2.4 < row.chest_cm / row.chest_in < 2.7, row


def test_an_unknown_size_raises_rather_than_guessing():
    try:
        ch.chest_for_size("18")
    except KeyError:
        pass
    else:                                          # pragma: no cover
        raise AssertionError("an unpublished size was answered")


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
