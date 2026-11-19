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


def test_disclosure_missing_is_an_error_with_classification():
    owed = {"disclosures": [DESIGN, DISCLOSURES["generated_imagery"]]}
    got = gpolicy.check_ai_disclosure("A pattern. " + DESIGN, owed)
    assert len(got) == 1 and "generated_imagery" in got[0].message, got
    assert "POLICY_AI_DISCLOSURE_MISSING" in _codes(gpolicy.check_listing(
        _draft(), classification=owed))
    full = "A pattern. " + DESIGN + " " + DISCLOSURES["generated_imagery"]
    assert gpolicy.check_ai_disclosure(full, owed) == []


# ---- H2a: UNKNOWN holds publication, with a reason -------------------------------------

def _reading(db, **detail):
    with db.session() as s:
        s.add(AuditLog(actor="owner", action=pol.READING_ACTION, artifact="etsy_ai_policy",
                       detail=detail))
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
