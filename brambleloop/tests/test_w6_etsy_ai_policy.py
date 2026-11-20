"""ENG-ETSY-AI-POLICY / ENG-ETSY-AI-FIX (w6): listing copy may never claim human authorship.

Etsy Help 44297885802647 (edited 2026-11-11): sellers "cannot misrepresent AI-generated work
as handmade or entirely their own creation". The guard is structural (review H1): honest
authorship/making/testing sentences come only from a closed allowlist; any such claim in the
remaining free text is refused, through Unicode, case, spacing, inflection and UK spelling.

Pinned here:
  H1  an adversarial corpus is refused; a false-positive corpus of benign copy passes.
  H2a Etsy AI policy status UNKNOWN holds publication with a reason; internal work continues.
  H2b the design disclosure is required on EVERY listing package (`check_ai_disclosure`).
  H2c policy #39 (listing_image_rules) still holds publication only (ENG-RECOVERY compat).
  H3  the mutant `check_ai_disclosure -> []` fails this suite.
  M4  the guard is in gates.policy.check_listing (the listing-package gate) and in the
      owner-accepted live copy check (manual_adoption.truth_problems).
  M5  a refusal raises an owner hold card with its reason; "download my pattern" passes.
  FIX3 H1  listing copy is a COMPOSITION: every unit is an allowlisted honest statement, a
      closed code template (slots validated), or constrained free text refused on the lexical
      backstop OR the independent topic rule. The delta review's corpus is refused by both.
  FIX3 M-A  UNKNOWN -> one owner card -> the owner's step-up reading -> publication allowed;
      a stale reading -> held again, card back. The attestation is never inferred.
  FIX3 L-c  "Ideal handmade gift" / "Make a handmade gift" refused, the card says why.
  (L-a, the listing.seo hold-card wiring, is tests/test_w6_etsy_ai_fix3_seo.py.)

Run: cd brambleloop && python3 tests/test_w6_etsy_ai_policy.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - W3-HYG per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, OwnerAction  # noqa: E402
from brambleloop.gates import platform_policy  # noqa: E402
from brambleloop.gates import policy as gpolicy  # noqa: E402
from brambleloop.gates.platform_policy import DISCLOSURES  # noqa: E402
from brambleloop.integrations.etsy import EtsyRejected, build_payload  # noqa: E402
from brambleloop.publish import etsy_ai_policy as pol  # noqa: E402
from brambleloop.publish import release_gates  # noqa: E402
from brambleloop.publish.pdf import AI_DISCLOSURE  # noqa: E402

DESIGN = DISCLOSURES["ai_assisted_design"]
GOOD = dict(title="Cabled Cushion Crochet Pattern", price_cad=7.5,
            tags=["crochet pattern"], materials=["cotton yarn"],
            description="A digital crochet pattern. " + DESIGN)

# Every phrase the review found passing the old blacklist, then the tricks around them.
ADVERSARIAL = (
    # review H1, verbatim
    "I created this pattern", "Our team designed this", "I have designed", "Worked up by me",
    "Handmade crochet pattern", "handmade", "hand made", "Lovingly handcrafted",
    "tested by our testers", "Test-crocheted", "crocheted sample photo shows",
    "Made with love by our studio",
    # the first version's own cases
    "I designed this pattern", "hand-drawn charts", "Designed by a human crocheter",
    "tested by real crocheters", "my own design", "human-tested", "made by hand",
    "the sample we crocheted",
    # synonyms and inflections
    "We wrote every row", "I drew the chart myself", "I dreamt up this design",
    "Our designers created it", "We've crocheted every one", "I’ve tested it",
    "We came up with this motif", "I personally stitched the sample", "Crafted by me",
    "Developed by our team", "hand-crafted", "handcrocheted", "Hand-written instructions",
    "homemade", "Pattern tested", "Our testers loved it", "Tried and tested",
    "tech edited", "our original design", "entirely our own creation", "100% my own work",
    "made with care", "a labour of love", "Original design by Brambleloop",
    "the photo shows our finished sample", "pictured: my crocheted sample",
    "real swatch photographed", "Designer-made",
    # UK spellings
    "Trialled by makers", "Lovingly hand-coloured and handmade", "crocheted by our mum",
    # case, Unicode, spacing and joiner tricks
    "HANDMADE", "HaNdMaDe", "ＨＡＮＤＭＡＤＥ",  # fullwidth
    "hаndmаde",                       # Cyrillic a
    "hand​made", "hand­made",         # zero-width space, soft hyphen
    "h a n d m a d e", "h.a.n.d.m.a.d.e", "hand___made", "HAND-MADE", "hand — made",
    "h4ndmade", "désignéd by me", "de-signed by me", "I  d e s i g n e d  it",
    "t-e-s-t-e-d by crocheters",
)

# Benign listing copy that must pass (M5: narrow patterns for benign phrasing).
BENIGN = (
    "Download my pattern after purchase.", "Download my patterns from your Etsy account.",
    "A digital crochet pattern for a cabled cushion.",
    "Make a gauge swatch to test your tension.", "Worked in rounds from the centre.",
    "Designed for confident beginners.", "Made with worsted-weight cotton yarn.",
    "We recommend making a gauge swatch first.", "Each square is worked in two colours.",
    "Instructions are written in US terms.", "Hand wash cold, lay flat to dry.",
    "You will receive a PDF with charts and written instructions.",
    "Questions? Message me any time.", "Thank you for visiting the shop.",
    "Choose a yarn you love.", "Sizes are made to measure from the schematic.",
    "Use a 5 mm hook (US H-8).", "Gauge: 16 sts and 18 rows = 10 cm.",
    "Includes a stitch guide and a photo tutorial of each technique.",
    "Each and every row is charted.", "Colourwork is worked from the chart.",
    "Handy for quick gifts.", "Perfect for a handbag charm.",
    "Written in US crochet terms.", "Uses US crochet terms with a UK conversion chart.",
    "Contact us crochet lovers!",
)


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='w6ai-')}/a.db")
    db.create_all()
    return db


# ---- H1: structural guard --------------------------------------------------------------

def test_adversarial_corpus_is_refused():
    missed = [a for a in ADVERSARIAL if not pol.claims(f"Lovely cushion. {a}.")]
    assert not missed, missed
    assert len(ADVERSARIAL) >= 60


def test_false_positive_corpus_passes():
    flagged = [(b, pol.claims(b)) for b in BENIGN if pol.claims(b)]
    assert not flagged, flagged


def test_allowlisted_honest_sentences_pass_and_are_the_only_source():
    texts = pol.honest_statements()
    assert DESIGN in texts and AI_DISCLOSURE in texts and len(texts) >= 7
    for t in texts:
        assert pol.claims(t) == [], t
    # the allowlist is exact: a paraphrase of an honest sentence is free text, and refused
    assert pol.claims("This design was created by me with AI assistance.")
    assert pol.claims(DESIGN.replace("created with AI assistance", "handmade"))
    # an honest sentence does not shelter a claim beside it
    assert pol.claims(DESIGN + " Handmade by our team.")


def test_free_text_testing_claim_is_refused_even_if_true():
    # honest testing statements come only from the allowlist; free text does not get to say it
    assert pol.claims("This pattern is tested against its specification by code.")


# ---- M4: the listing-package gate ------------------------------------------------------

def _draft(**kw):
    base = dict(title="Cabled Cushion Crochet Pattern", description="A pattern. " + DESIGN,
                tags=["crochet pattern"], price_cad=7.5)
    base.update(kw)
    return gpolicy.ListingDraft(**base)


def _codes(findings):
    return {f.code for f in findings if f.is_error}


def test_check_listing_refuses_authorship_in_every_field():
    assert "POLICY_AUTHORSHIP_CLAIM" not in _codes(gpolicy.check_listing(_draft()))
    for kw in ({"title": "Handmade Cushion Crochet Pattern"},
               {"description": "A pattern. Our team designed this. " + DESIGN},
               {"tags": ["crochet pattern", "hand made"]}):
        assert "POLICY_AUTHORSHIP_CLAIM" in _codes(gpolicy.check_listing(_draft(**kw))), kw


def test_build_payload_refuses_claim_in_title_or_description():
    for field, value in (("description", GOOD["description"] + " Hand-drawn by me."),
                         ("title", "My Own Design Cushion Crochet Pattern")):
        try:
            build_payload(**dict(GOOD, **{field: value}))
        except EtsyRejected as exc:
            assert pol.CODE in str(exc)
        else:
            raise AssertionError(f"{field} claim was accepted")
    assert build_payload(**GOOD).who_made in ("i_did", "someone_else", "collective")


def test_owner_accepted_live_copy_is_guarded():
    from brambleloop.publish import manual_adoption

    db = _db()
    snap = {"title": "Cabled Cushion Crochet Pattern", "tags": ["handmade"],
            "description": "Lovingly handcrafted. " + DESIGN}
    problems = manual_adoption.truth_problems(db, slug="x", version="1", snap=snap)
    assert any(pol.CODE in p for p in problems), problems


# ---- H2b / H3: the disclosure is required on every package -----------------------------

def test_disclosure_missing_is_an_error_without_classification():
    # H3: the mutant `check_ai_disclosure -> []` fails here
    got = gpolicy.check_ai_disclosure("A pattern with no disclosure.", None)
    assert [f.code for f in got] == ["POLICY_AI_DISCLOSURE_MISSING"], got
    assert gpolicy.check_ai_disclosure("A pattern. " + DESIGN, None) == []
    assert "POLICY_AI_DISCLOSURE_MISSING" in _codes(
        gpolicy.check_listing(_draft(description="A pattern with no disclosure.")))
    assert "POLICY_AI_DISCLOSURE_MISSING" not in _codes(gpolicy.check_listing(_draft()))


def test_only_the_concept_stage_skips_the_disclosure_and_never_the_guard():
    bare = _draft(description="A pattern with no disclosure. Handmade.")
    codes = _codes(gpolicy.check_listing(bare, package=False))
    assert "POLICY_AI_DISCLOSURE_MISSING" not in codes
    assert "POLICY_AUTHORSHIP_CLAIM" in codes
    assert "POLICY_AI_DISCLOSURE_MISSING" in _codes(gpolicy.check_listing(bare))


def test_disclosure_missing_is_an_error_with_classification():
    owed = {"disclosures": [DESIGN, DISCLOSURES["generated_imagery"]]}
    got = gpolicy.check_ai_disclosure("A pattern. " + DESIGN, owed)
    assert len(got) == 1 and "generated_imagery" in got[0].message, got
    assert "POLICY_AI_DISCLOSURE_MISSING" in _codes(gpolicy.check_listing(
        _draft(), classification=owed))
    full = "A pattern. " + DESIGN + " " + DISCLOSURES["generated_imagery"]
    assert gpolicy.check_ai_disclosure(full, owed) == []


# ---- H2a: UNKNOWN holds publication, with a reason -------------------------------------

def _reading(db, actor="owner", **detail):
    # FIXTURE: a reading row shaped as record_reading writes it. Test data, not an attestation.
    full = {"policy_urls": list(pol.POLICY_URLS), "attested_via": pol.ATTESTED_VIA,
            "checked": "FIXTURE: test data, not an owner attestation"}
    full.update(detail)
    with db.session() as s:
        s.add(AuditLog(actor=actor, action=pol.READING_ACTION, artifact="etsy_ai_policy",
                       detail=full))
        s.commit()


def test_status_unknown_holds_publication_with_reason():
    db = _db()
    st = pol.publication_status(db)
    assert st["status"] == pol.UNKNOWN and st["hold"] is True
    assert "UNKNOWN" in st["reason"] and "internal work continues" in st["reason"]
    today = date.today().isoformat()
    # anonymous, stale (before the rules' last edit), future-dated, unparseable: UNKNOWN
    for bad in ({"status": "PERMITTED", "read_by": "", "read_on": today},
                {"status": "PERMITTED", "read_by": "owner", "read_on": "2026-10-01"},
                {"status": "PERMITTED", "read_by": "owner",
                 "read_on": (date.today() + timedelta(days=3)).isoformat()},
                {"status": "PERMITTED", "read_by": "owner", "read_on": "soon"},
                {"status": "PASS", "read_by": "owner", "read_on": today}):
        _reading(db, **bad)
        assert pol.publication_status(db)["status"] == pol.UNKNOWN, bad


def test_status_prohibited_holds_and_permitted_releases():
    db = _db()
    today = date.today().isoformat()
    _reading(db, status="PROHIBITED", read_by="owner", read_on=today)
    st = pol.publication_status(db)
    assert st["status"] == pol.PROHIBITED and st["hold"] and "PROHIBITED" in st["reason"]
    _reading(db, status="PERMITTED", read_by="owner", read_on=today)
    st = pol.publication_status(db)
    assert st["status"] == pol.PERMITTED and st["hold"] is False


def test_unreadable_status_is_unknown_never_permitted():
    class Broken:
        def session(self):
            raise RuntimeError("db down")
    assert pol.publication_status(Broken())["hold"] is True


def test_for_publish_carries_the_unknown_hold():
    db = _db()
    try:
        verdict = release_gates.for_publish(db, slug="nothing-here", version="1",
                                            read_only=True)
    except Exception as exc:  # noqa: BLE001 - an empty db may refuse earlier; then source-pin
        import inspect

        src = inspect.getsource(release_gates.for_publish)
        assert "etsy_ai_policy.publication_status(db)" in src and \
            'reasons.append(ai_policy["reason"])' in src, exc
        return
    assert verdict["blocks_release"] is True
    assert any("Etsy AI policy status UNKNOWN" in r for r in verdict["reasons"]), verdict
    assert verdict["etsy_ai_policy"]["status"] == pol.UNKNOWN


def test_unknown_does_not_hold_internal_work():
    db = _db()
    assert pol.publication_status(db)["hold"]
    gate = release_gates.staleness(db, slug="hexie-coaster-set")
    assert not any("Etsy AI policy" in r for r in gate["reasons"]), gate["reasons"]
    assert release_gates.retry_hold_reason(db, slug="hexie-coaster-set") is None


# ---- H2c: policy #39 holds publication only (ENG-RECOVERY compatible) ------------------

IMAGE_RULES = {"source": "listing_image_rules", "snapshot_id": 39, "checked_on": "2026-10-11",
               "version": "v2", "affects": ["creative_assets", "publishing"]}


def test_policy_39_holds_publication_only():
    db = _db()
    real = platform_policy.unreviewed_changes
    platform_policy.unreviewed_changes = lambda _db: [dict(IMAGE_RULES)]
    try:
        assert release_gates.retry_hold_reason(db, slug="hexie-coaster-set") is None
        gate = release_gates.staleness(db, slug="hexie-coaster-set")
        assert gate["blocks"] is True
        assert any("listing_image_rules" in r for r in gate["reasons"])
        assert gate["policy_publication_only"] == ["listing_image_rules"]
        assert release_gates.policy_holds_manufacturing([IMAGE_RULES]) == []
    finally:
        platform_policy.unreviewed_changes = real


# ---- M5: refusals are hold cards with reasons ------------------------------------------

def test_refusal_raises_a_hold_card_with_its_reason():
    db = _db()
    problems = pol.authorship_claim_problems("Handmade crochet pattern. " + DESIGN)
    assert problems
    card = pol.hold_card(db, artifact="cushion@1", problems=problems, where="listing.seo")
    assert card["id"] and "handmade" in card["reason"] and pol.CODE in card["reason"]
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == "authorship_copy_hold:cushion@1")))
    assert len(rows) == 1 and not rows[0].done and "publication of cushion@1" in rows[0].blocks
    # restated, not duplicated
    pol.hold_card(db, artifact="cushion@1", problems=problems)
    with db.session() as s:
        assert len(list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == "authorship_copy_hold:cushion@1")))) == 1
    # nothing to hold: no card
    assert pol.hold_card(db, artifact="cushion@2", problems=[]) == {}


def test_download_my_pattern_is_not_refused():
    assert pol.authorship_claim_problems("Download my pattern instantly. " + DESIGN) == []


def test_sources_are_recorded_verbatim_with_dates():
    assert {s["article"] for s in pol.SOURCES} == {"44297885802647", "115015663347"}
    assert all(s["edited_at"] and s["read_on"] == "2026-11-19" for s in pol.SOURCES)
    assert pol.LATEST_EDIT == "2026-11-11"


# ---- FIX3 H1: listing copy is a composition --------------------------------------------

from brambleloop.publish import listing_composition as lc  # noqa: E402

# The delta review's bypasses, verbatim, by class.
FIX3_CORPUS = {
    "AI denial": ("No AI used. 100% human.", "This is not AI generated.", "created without AI",
                  "AI-free"),
    "human attribution": ("Designed by Jane, our lead designer.", "Crafted by Sarah",
                          "Pattern by Emily Smith", "Designed by yours truly", "Self-designed",
                          "Independently designed", "I'm the designer",
                          "The designer behind this"),
    "own creation": ("From my hook to yours", "Straight from my hook", "Created in my studio",
                     "My original", "original design"),
    "craft or sample": ("Handspun", "Artisan made", "artisanal", "Photographed sample",
                        "Real photo", "Verified by crocheters",
                        "Each pattern goes through testing"),
    "typos": ("Ive designed", "I desgined", "designd by me", "hanmade", "Handmaid",
              "We conceived this pattern", "I dreamed this up"),
    "L-c": ("Ideal handmade gift", "Make a handmade gift"),
}
FIX3_ALL = tuple(x for group in FIX3_CORPUS.values() for x in group)


def test_fix3_corpus_is_refused_by_the_lexical_backstop():
    missed = [a for a in FIX3_ALL if not pol.claims(f"Lovely cushion. {a}.")]
    assert not missed, missed


def test_fix3_corpus_is_refused_by_the_topic_rule_independently():
    # the second rule alone catches every string: a lexical miss is not a pass
    missed = [a for a in FIX3_ALL if not lc.topics(a)]
    assert not missed, missed


def test_fix3_corpus_is_refused_in_listing_copy_every_way_it_arrives():
    for a in FIX3_ALL + ADVERSARIAL:
        assert pol.authorship_claim_problems(f"A digital crochet pattern. {a}. {DESIGN}"), a
        assert gpolicy.check_authorship(a, "listing.description"), a
    for a in FIX3_ALL:
        try:
            build_payload(**dict(GOOD, description=GOOD["description"] + " " + a))
        except EtsyRejected as exc:
            assert pol.CODE in str(exc), a
        else:
            raise AssertionError(f"build_payload accepted {a!r}")


def test_free_text_mentioning_an_authorship_topic_is_refused_with_its_reason():
    # no lexical claim, but the sentence mentions design / making / testing / photos / AI /
    # humans and is no allowlisted sentence: refused, and the refusal names the topic
    for sentence, topic in (("Designed for confident beginners.", "design"),
                            ("Make a gauge swatch to test your tension.", "testing"),
                            ("Includes a photo tutorial.", "photos"),
                            ("Includes an AI disclosure.", "AI"),
                            ("A real person answers.", "humans"),
                            ("Sizes are made to measure.", "making")):
        assert not pol.claims(sentence), sentence     # the lexical backstop lets it through
        got = lc.constrained_problems(sentence)
        assert got and topic in got[0] and pol.CODE in got[0], (sentence, got)
        # ...and the listing gates read it the same way
        assert pol.authorship_claim_problems(f"{sentence} {DESIGN}"), sentence
        assert "POLICY_AUTHORSHIP_CLAIM" in _codes(gpolicy.check_listing(
            _draft(description=f"A pattern. {sentence} {DESIGN}"))), sentence
    # product facts with no authorship content pass
    for sentence in ("A digital crochet pattern for a cabled cushion.", "Use a 5 mm hook.",
                     "Worked in rounds from the centre.", "Hand wash cold, lay flat to dry.",
                     "Instructions are written in US terms.", "yarn craft project"):
        assert lc.constrained_problems(sentence) == [], sentence


def _childrens():
    from brambleloop.intel import childrens as ch

    facts = ch.StatementFacts(audience="under_3", finished_size_cm=(76.0, 76.0),
                              colours=("Cream", "Sage"), fibres=("cotton",))
    return ch.render_statements("baby_blanket", "under_3", facts)


def _generated_listing(**over):
    from brambleloop.commerce import seo

    title = seo.build_title(over.pop("product_title", "Cloudline Baby Blanket"), "baby_blanket",
                            ["cloud"], "Christmas", sizes=2)

    class M:  # a CIR material
        name, yarn_weight, fibre_content = "Soft cotton DK", "DK", (("cotton", 100),)

    kw = dict(size_label="76 x 76 cm", yardage_lines=["Approx. 620 m of Cream"],
              tolerance_pct=10, difficulty="Easy", colors=["Cream", "Sage"], terminology="US",
              gauge_line="18 sts x 20 rows = 10 cm on a 4 mm hook",
              stitches=["ch", "dc", "sc"], season="Christmas (Dec 25)", pages=9,
              collapsed_repeats=True, childrens=_childrens(),
              key_phrases=["baby blanket pattern", "cloud blanket"],
              lesson_links=[{"url": "https://learn.example.org/magic-ring"}],
              why_it_matters=seo.value_proposition(sizes=2, difficulty="Easy", colours=2),
              yarn_lines=seo.yarn_lines([M()]))
    product = over.pop("product_title_desc", "Cloudline Baby Blanket")
    kw.update(over)
    desc = seo.build_description(product, **kw)
    desc += "\n\n" + platform_policy.disclosure_block(type("C", (), {"disclosures": [
        DISCLOSURES["generated_imagery"], DISCLOSURES["disclosed_render"]]})())
    return title, desc


def test_every_unit_of_a_generated_listing_is_a_template_or_passes_the_validator():
    title, desc = _generated_listing()
    units = lc.composition(title + "\n" + desc)
    assert units
    for u in units:
        assert u["kind"] in ("honest", "honest+free", "free") or u["kind"].startswith(
            "template:"), u
        assert u["problems"] == [], u
        if u["kind"] == "free":
            # a free unit is accepted ONLY because the constrained validator passes it
            assert lc.constrained_problems(u["text"]) == [], u
    kinds = {u["kind"] for u in units}
    for t in ("template:lead", "template:opening", "template:fact.size", "template:fact.skill",
              "template:fact.yarn", "template:fact.gauge_hook",
              "template:contents.us_uk_editions", "template:childrens.age_suitability"):
        assert t in kinds, (t, sorted(kinds))
    assert "honest" in kinds                       # the disclosure is the fixed template
    assert DESIGN in desc
    assert pol.authorship_claim_problems(title + "\n" + desc) == []
    # the concept-stage generators' AI sentences are allowlisted, from one source
    assert pol.CONCEPT_AI_SENTENCE in pol.honest_statements()
    assert pol.CERTIFIED_CONCEPT_AI_SENTENCE in pol.honest_statements()


def test_a_template_slot_carrying_authorship_is_refused():
    title, desc = _generated_listing(product_title_desc="Handmade Cloudline Blanket")
    got = pol.authorship_claim_problems(desc)
    assert got and "slot 'title'" in got[0] and "handmade" in got[0].lower(), got
    _t, desc = _generated_listing(key_phrases=["handmade gift", "baby blanket pattern"])
    got = pol.authorship_claim_problems(desc)
    assert got and "slot 'phrases'" in got[0], got
    _t, desc = _generated_listing(difficulty="Designed by Jane")
    assert pol.authorship_claim_problems(desc)
    # editing a template's fixed words turns the line into free text, and it is read as such
    _t, desc = _generated_listing()
    edited = desc.replace("every stitch count is checked before release",
                          "every stitch count is checked by our testers before release")
    assert pol.authorship_claim_problems(edited)


def test_lc_handmade_gift_hold_card_states_its_reason():
    db = _db()
    for i, phrase in enumerate(FIX3_CORPUS["L-c"]):
        problems = pol.authorship_claim_problems(f"{phrase}. {DESIGN}")
        assert problems, phrase
        card = pol.hold_card(db, artifact=f"gift@{i}", problems=problems, where="listing.seo")
        assert phrase.lower() in card["reason"].lower(), card["reason"]
        assert "handmade" in card["reason"] and "mentions" in card["reason"], card["reason"]
        assert pol.CODE in card["reason"]


# ---- FIX3 M-A: the owner's path out of UNKNOWN ------------------------------------------

def _card_rows(db, state=None):
    with db.session() as s:
        return [(r.id, r.done, r.state) for r in s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == pol.OWNER_CARD_KEY))]


def _record(db, today, **over):
    body = dict(status=pol.PERMITTED, policy_urls=list(pol.POLICY_URLS),
                read_on=today.isoformat(),
                checked="Read both Help articles and the Seller Handbook AI section; "
                        "AI-assisted patterns are allowed with disclosure",
                confirm=pol.READING_CONFIRMATION,
                expected_digest=pol.reading_preview()["digest"], actor="owner-test")
    body.update(over)
    return pol.record_reading(db, today=today, **body)


def test_unknown_raises_one_card_owner_reading_allows_then_stale_holds_again():
    db = _db()
    today = date.today()
    st = pol.publication_status(db)
    assert st["status"] == pol.UNKNOWN and st["hold"]
    card = pol.ensure_owner_card(db)
    assert card["id"] and pol.OWNER_CARD_KEY == card["requirement_key"]
    pol.ensure_owner_card(db)                       # restated, never duplicated
    assert len(_card_rows(db)) == 1 and not _card_rows(db)[0][1]
    # nothing but the owner's reading lifts it: a PERMITTED status is never inferred
    assert pol.publication_status(db)["hold"]
    out = _record(db, today)
    assert out["reading_audit_id"] and out["status"] == pol.PERMITTED
    st = pol.publication_status(db)
    assert st["status"] == pol.PERMITTED and st["hold"] is False
    assert st["reading"]["policy_urls"] and st["reading"]["checked"]
    assert st["reading"]["attested_via"] == pol.ATTESTED_VIA
    rows = _card_rows(db)
    assert len(rows) == 1 and rows[0][1] and rows[0][2] == "satisfied", rows
    assert pol.ensure_owner_card(db) == {}         # no card while a fresh reading stands
    # stale: past the bounded age the same reading is UNKNOWN again, and the card is back
    later = today + timedelta(days=pol.READING_MAX_AGE_DAYS + 1)
    st = pol.publication_status(db, today=later)
    assert st["status"] == pol.UNKNOWN and st["hold"] and "UNKNOWN" in st["reason"]
    real = pol.date

    class Later(real):
        @classmethod
        def today(cls):
            return later
    pol.date = Later
    try:
        assert pol.ensure_owner_card(db)["id"]
        assert sum(1 for r in _card_rows(db) if not r[1]) == 1
    finally:
        pol.date = real


def test_a_reading_is_refused_unless_it_is_complete_and_the_owners():
    db = _db()
    today = date.today()
    for over in ({"confirm": "ok"}, {"expected_digest": "x"}, {"status": "PASS"},
                 {"policy_urls": []}, {"policy_urls": ["https://example.com/ai"]},
                 {"checked": ""}, {"read_on": "2026-10-01"},
                 {"read_on": (today + timedelta(days=2)).isoformat()},
                 {"read_on": (today - timedelta(days=pol.READING_MAX_AGE_DAYS + 1)).isoformat()}):
        try:
            _record(db, today, **over)
        except pol.ReadingRefused:
            continue
        raise AssertionError(f"accepted {over}")
    assert pol.publication_status(db)["status"] == pol.UNKNOWN
    # a row not written through the owner's step-up path is not a reading
    for actor, over in (("system", {}), ("owner", {"attested_via": "heartbeat"}),
                        ("owner", {"checked": ""}), ("owner", {"policy_urls": []})):
        _reading(db, actor=actor, status="PERMITTED", read_by="x", read_on=today.isoformat(),
                 **over)
        assert pol.publication_status(db)["status"] == pol.UNKNOWN, (actor, over)


def test_the_owner_path_runs_through_the_command_center_step_up_action():
    from brambleloop.app.command_center import approvals

    assert approvals.ACTIONS["etsy_ai_policy.record_reading"][0] is True     # step-up
    assert approvals.ACTIONS["etsy_ai_policy.reading_preview"][0] is False
    db = _db()
    pol.ensure_owner_card(db)
    cards = approvals._ai_policy_card(db, [approvals._gate_card(
        {"requirement_key": pol.OWNER_CARD_KEY, "owner_action_id": 1, "action": "x"})])
    ours = [c for c in cards if c["card_id"] == "etsy_ai_policy:reading"]
    assert len(cards) == 1 and len(ours) == 1, cards                 # one consolidated card
    assert {a["action"] for a in ours[0]["actions"]} == {
        "etsy_ai_policy.reading_preview", "etsy_ai_policy.record_reading"}
    preview = approvals.execute(db, "etsy_ai_policy.reading_preview", {}, actor="owner-test")
    digest = preview["result"]["digest"]
    try:
        approvals.execute(db, "etsy_ai_policy.record_reading", {"confirm": "yes"},
                          actor="owner-test")
    except approvals.ActionRefused as exc:
        assert "confirm must be exactly" in str(exc)
    else:
        raise AssertionError("a bare record was accepted")
    out = approvals.execute(db, "etsy_ai_policy.record_reading", {
        "status": "PERMITTED", "policy_urls": list(pol.POLICY_URLS),
        "read_on": date.today().isoformat(), "confirm": pol.READING_CONFIRMATION,
        "checked": "Read both Help articles and the Seller Handbook AI section",
        "expected_digest": digest, "reason": "owner reviewed"}, actor="owner-test")
    assert out["result"]["reading_audit_id"] and out["audit_id"]
    assert pol.publication_status(db)["hold"] is False
    assert approvals._ai_policy_card(db, []) == []


if __name__ == "__main__":
    import traceback

    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests, "no tests collected"
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            print(f"FAIL {name}")
            fails += 1
    print(f"\n{len(tests) - fails} passed, {fails} failed")
    raise SystemExit(1 if fails else 0)
