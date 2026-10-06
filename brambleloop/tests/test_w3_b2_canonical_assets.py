"""Wave 3 lane B2: the owner's canonical logo and banner (D-FB-17) -- immutable, fail-closed,
protected from score-driven replacement, at the top of the brand hierarchy, and the banner's
publication assessment honest (no PASS without evidence; UNKNOWN never PASS).

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_b2_canonical_assets.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.brand import canonical_assets as CA  # noqa: E402
from brambleloop.store_foundation import owner_banner as OB  # noqa: E402

LOGO_SHA = "28f301b28766acea7b0f632ceefcb1c66e271a6fba8da0c84a65c94647d35998"
BANNER_SHA = "048a199133f7589cc243cb876a7ee5b0f68b5d6530929a922c79de9eda64eb98"
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
FAILS = 0


def check(name: str, fn) -> None:
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


class _TamperedDir:
    """A temp copy of owner_source; `mutate(dir)` alters it. Restores OWNER_SOURCE_DIR."""

    def __init__(self, mutate):
        self.mutate = mutate

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b2_canon_"))
        shutil.copytree(CA.OWNER_SOURCE_DIR, self.tmp / "owner_source")
        self.dir = self.tmp / "owner_source"
        self.mutate(self.dir)
        self.saved = CA.OWNER_SOURCE_DIR
        CA.OWNER_SOURCE_DIR = self.dir
        return self.dir

    def __exit__(self, *exc):
        CA.OWNER_SOURCE_DIR = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def _flip_byte(name):
    def go(d: Path):
        p = d / name
        b = bytearray(p.read_bytes())
        b[len(b) // 2] ^= 0xFF
        p.write_bytes(bytes(b))
    return go


# ---- immutability ---------------------------------------------------------------------------

def test_registry_matches_the_owner_files():
    assert CA.ASSETS[CA.HERO_LOGO].sha256 == LOGO_SHA
    assert CA.ASSETS[CA.STOREFRONT_BANNER].sha256 == BANNER_SHA
    assert CA.ASSETS[CA.HERO_LOGO].size == (1536, 1024)
    assert CA.ASSETS[CA.STOREFRONT_BANNER].size == (1983, 793)
    v = CA.verify()
    assert v["ok"], v["problems"]
    assert v["assets"]
    for row in v["assets"]:
        assert row["ok"] and row["sha256"] == row["expected_sha256"], row
    # the bytes on disk, independently of the module
    for role, sha in ((CA.HERO_LOGO, LOGO_SHA), (CA.STOREFRONT_BANNER, BANNER_SHA)):
        assert hashlib.sha256(CA.path(role).read_bytes()).hexdigest() == sha
    sums = (CA.OWNER_SOURCE_DIR / "SHA256SUMS").read_text()
    assert LOGO_SHA in sums and BANNER_SHA in sums
    log = (ROOT / "DECISION_LOG.md").read_text()
    assert "D-FB-17" in log and LOGO_SHA in log and BANNER_SHA in log
    assert CA.AUTHORISED_BRAND_CHANGES == ("D-FB-17",)


def test_tampered_copy_fails_closed():
    with _TamperedDir(_flip_byte("brambleloop_owner_banner_canonical.png")) as d:
        v = CA.verify(d)
        assert not v["ok"] and any("storefront_banner" in p for p in v["problems"]), v
        for fn in (lambda: CA.verified_bytes(CA.STOREFRONT_BANNER),
                   lambda: CA.require_verified(), lambda: CA.image(CA.STOREFRONT_BANNER)):
            try:
                fn()
            except CA.CanonicalAssetError:
                pass
            else:
                raise AssertionError("tampered banner was accepted")
        # the assessment and the storefront gate fail closed on the altered file
        r = OB.assess()
        assert r["gates"][0]["gate"] == "canonical_integrity"
        assert r["gates"][0]["status"] == "FAIL" and not r["publishable"]
        codes = {f["code"] for f in OB.storefront_findings(r)}
        assert "STORE_BANNER_CANONICAL_UNVERIFIED" in codes, codes
    # the real files are untouched
    assert CA.verify()["ok"]


def test_missing_file_or_sums_fails_closed():
    with _TamperedDir(lambda d: (d / "brambleloop_owner_logo_canonical.png").unlink()) as d:
        v = CA.verify(d)
        assert not v["ok"] and any("missing" in p for p in v["problems"]), v
    with _TamperedDir(lambda d: (d / "SHA256SUMS").unlink()) as d:
        assert not CA.verify(d)["ok"]


# ---- protection -----------------------------------------------------------------------------

OTHER = hashlib.sha256(b"a challenger that scores higher").hexdigest()


def test_replacement_needs_an_owner_decision_naming_the_bytes():
    for role in CA.ROLES:
        assert CA.require_brand_change_authorised(role, CA.ASSETS[role].sha256)["change"] is False
        for approval in (None, {}, {"score": 0.99, "objective": 0.97, "requested_by": "visual"},
                         {"owner_decision_id": "D-FB-17"},      # names only today's bytes
                         {"owner_decision_id": "D-FB-99"},      # not an authorised id
                         {"owner_decision_id": ""}):
            try:
                CA.require_brand_change_authorised(role, OTHER, approval)
            except CA.BrandChangeRefused as exc:
                assert "owner decision" in str(exc)
            else:
                raise AssertionError((role, approval))
    try:
        CA.require_brand_change_authorised("favicon", OTHER, None)
    except CA.BrandChangeRefused:
        pass
    else:
        raise AssertionError("unknown role accepted")
    # a recorded decision that names the exact bytes is the only way through
    saved_a, saved_d = CA.AUTHORISED_BRAND_CHANGES, dict(CA.DECISIONS)
    try:
        CA.AUTHORISED_BRAND_CHANGES = saved_a + ("D-TEST-1",)
        CA.DECISIONS["D-TEST-1"] = {CA.STOREFRONT_BANNER: OTHER}
        ok = CA.require_brand_change_authorised(CA.STOREFRONT_BANNER, OTHER,
                                                {"owner_decision_id": "D-TEST-1"})
        assert ok["change"] and ok["decision"] == "D-TEST-1"
        # ...for that role and those bytes only
        assert not CA.is_authorised(CA.HERO_LOGO, OTHER, {"owner_decision_id": "D-TEST-1"})
        assert not CA.is_authorised(CA.STOREFRONT_BANNER, "0" * 64,
                                    {"owner_decision_id": "D-TEST-1"})
    finally:
        CA.AUTHORISED_BRAND_CHANGES = saved_a
        CA.DECISIONS.pop("D-TEST-1", None)
        assert CA.DECISIONS == saved_d


def test_a_higher_scoring_challenger_is_refused_everywhere():
    from brambleloop.brand import judge, takeover
    from brambleloop.visual.rnd import objective as O

    # canonical_assets.select: scores change nothing
    for role in CA.ROLES:
        r = CA.select(role, [{"id": "challenger", "sha256": OTHER, "score": 0.999},
                             {"id": "canonical", "sha256": CA.ASSETS[role].sha256,
                              "score": 0.1}])
        assert r["held"]["sha256"] == CA.ASSETS[role].sha256 and not r["replaced"], r
        assert r["refused"] and r["refused"][0]["status"] == "OWNER_REVIEW_REQUIRED"
    # the Visual objective: a challenger that out-scores the canonical banner is not adopted
    gates = {g: {"status": "PASS"} for g in O.HARD_GATES}
    assert gates

    def cand(cid, sha, v):
        return {"id": cid, "brand_role": "storefront_banner", "sha256": sha, "gates": gates,
                "components": {"desirability": {"value": v, "basis": "PROXY"},
                               "brand_consistency": {"value": v, "basis": "PROXY"}}}

    sel = O.select([cand("challenger", OTHER, 0.99), cand("canonical", BANNER_SHA, 0.20)])
    assert sel["winner"] == "canonical", sel
    assert [x["id"] for x in sel["owner_review"]] == ["challenger"], sel
    assert sel["owner_review"][0]["status"] == "OWNER_REVIEW_REQUIRED"
    sel = O.select([cand("challenger", OTHER, 0.99)])
    assert sel["winner"] is None and sel["owner_review"], sel
    # ordinary (non-brand) candidates are unaffected
    plain = cand("listing-hero", OTHER, 0.5)
    plain.pop("brand_role")
    assert O.select([plain])["winner"] == "listing-hero"
    assert O.brand_target("storefront_banner")["sha256"] == BANNER_SHA
    # a seasonal takeover may not swap the canonical banner or logo
    for role in CA.ROLES:
        try:
            takeover.plan("christmas", datetime(2026, 12, 25).date(),
                          {"banner": "Winter at Brambleloop"},
                          today=datetime(2026, 10, 6).date(), replaces_assets={role: OTHER},
                          approval={"score": 0.99})
        except takeover.TakeoverRefused as exc:
            assert "TAKEOVER_REPLACES_CANONICAL_ASSET" in str(exc)
        else:
            raise AssertionError(role)
    assert {"canonical_logo", "canonical_banner"} <= set(takeover.CONTINUITY_INVARIANTS)
    # the brand judge ranks research directions only
    v = judge.cached_verdict()
    assert v["may_replace_canonical"] is False


# ---- hierarchy ------------------------------------------------------------------------------

def test_hierarchy_owner_raster_is_the_hero():
    from brambleloop.brand import identity_system as I

    assert I.asset_for("hero_lockup")["asset"] == CA.HERO_LOGO
    assert I.asset_for("storefront_banner")["asset"] == CA.STOREFRONT_BANNER
    assert hashlib.sha256(I.hero_artwork_png()).hexdigest() == LOGO_SHA
    assert I.owner_logo_path() == CA.path(CA.HERO_LOGO)
    for use in ("mono_reversed", "small_or_svg"):
        h = I.asset_for(use)
        assert h["derivative"] and "not the hero" in h["label"], h
    assert I.STATUS["state"] == "SUPPORTING_PRODUCTION_SYSTEM"
    assert any("exactly as supplied" in r for r in I.USAGE_RULES)
    d = I.to_dict(include_svgs=False)
    assert d["canonical"]["assets"]["hero_logo"]["sha256"] == LOGO_SHA


def test_micro_mark_only_where_the_artwork_is_measured_illegible():
    c = CA.shop_icon_choice((40, 70))
    mono = c["report"]["measurements"]["owner_monogram_crop"]
    assert mono
    failing = [px for px in (40, 70) if not mono[px]["ok"]]
    if c["derivative"]:
        assert failing, c                       # a derivative needs a measured failure
        assert c["owner_approval"]["decision"] == "D-FB-18" and c["status"] == "OWNER_APPROVED"
        assert c["asset"] == "a3_micro_mark" and "derivative" in c["label"].lower()
        assert "contrast" in c["why"] or "covers" in c["why"]
    else:
        assert not failing and c["asset"] == "owner_monogram_crop"
    # the exact artwork is legible at large sizes, where it is what gets used
    assert mono[500]["ok"] and mono[160]["ok"], mono
    # and the storefront gate reports the same choice
    from brambleloop.store_foundation import storefront_gate as G

    _f, info = G.check_icon()
    assert info["choice"]["asset"] == c["asset"]


def test_owner_files_read_from_the_repo_not_a_session_scratchpad():
    from brambleloop.brand import comparison, owner_identity

    saved = {k: os.environ.pop(k, None) for k in ("BRAMBLELOOP_OWNER_BRAND_DIR",
                                                  "BRAMBLELOOP_OWNER_LOGO_CONCEPT")}
    try:
        paths = owner_identity.concept_paths()
        assert paths["logo"] == CA.path(CA.HERO_LOGO), paths
        assert paths["banner"] == CA.path(CA.STOREFRONT_BANNER), paths
        assert comparison.owner_path() == CA.path(CA.HERO_LOGO)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    srcs = list((ROOT / "src/brambleloop/brand").glob("*.py"))
    assert srcs
    for p in srcs:
        assert "/scratchpad" not in p.read_text(), p


# ---- banner assessment honesty -------------------------------------------------------------

MUST_BE_UNKNOWN = ("laura_photorealism_anatomy", "product_truth", "visible_text_complete",
                   "ai_generated_imagery_disclosure")
ASSUMPTIONS = ("f233_banner_canvas_4to1", "f233_identity_block_survives_4to1",
               "f233_identity_block_in_phone_window")


def test_banner_assessment_is_honest():
    r = OB.assess()
    gates = {g["gate"]: g for g in r["gates"]}
    assert gates
    for g in r["gates"]:
        assert g["status"] in OB.STATUSES, g
        assert g["basis"] and g["why"], g
        if g["status"] == "PASS":
            assert g["evidence"], g               # no PASS without evidence
        if g["status"] == "UNKNOWN":
            assert g["gate"] not in r["passed"]
    for name in MUST_BE_UNKNOWN:                  # unmeasurable image content: never PASS
        assert gates[name]["status"] == "UNKNOWN", gates[name]
    assert gates["canonical_integrity"]["status"] == "PASS"
    # D-FB-18 item 4: 4:1 is not verified by Etsy -> advisory, never a pass or a verified fail
    for name in ASSUMPTIONS:
        assert gates[name]["status"] == "UNVERIFIED_ASSUMPTION", gates[name]
        assert name in r["unverified_assumptions"] and name not in r["passed"]
    assert gates["f233_banner_canvas_4to1"]["evidence"]["aspect"] == 2.501
    # D-FB-18 item 1: owner human review of THIS banner -> PASS with provenance
    li = gates["laura_identity"]
    assert li["status"] == "PASS" and li["evidence"]["sha256"] == BANNER_SHA
    assert li["evidence"]["owner_human_review"]["decision"] == "D-FB-18"
    assert "owner human identity review" in li["basis"]
    # identity is not publication: not flipped
    assert gates["laura_publication_status"]["status"] == "FAIL"
    assert gates["laura_publication_status"]["evidence"]["asset_status"] == \
        "not_for_publication"
    # D-FB-18 item 2: concept crochet, mapped to nothing; Product Truth not weakened
    pt = gates["product_truth"]["evidence"]["crochet_classification"]
    assert pt["class"] == "brand_lifestyle_concept" and pt["mapped_to_patterns"] == []
    # D-FB-18 item 9: no marketing sentence demanded because of C2PA
    ai = gates["ai_generated_imagery_disclosure"]
    assert ai["evidence"]["marketing_sentence_required"] is False
    assert ai["evidence"]["provenance_kept"] is True
    assert gates["nav_categories_truth"]["status"] == "FAIL"
    assert set(gates["nav_categories_truth"]["evidence"]["empty"]) == {
        "Wearables", "Gifts", "Seasonal"}
    assert ai["evidence"]["c2pa"]["present"] and ai["evidence"]["c2pa"]["signature_verified"] \
        is False
    assert not r["publishable"] and r["status"] == "BLOCKED"
    # every non-passing gate is a named storefront finding
    codes = {f["code"] for f in OB.storefront_findings(r)}
    for g in r["gates"]:
        code = f"STORE_BANNER_OWNER_{g['gate'].upper()}_{g['status']}"
        assert (code in codes) == (g["status"] in OB.BLOCKING), code


def test_owner_review_is_recorded_and_covers_this_banner_only():
    import dataclasses

    from brambleloop.core.db import Database
    from brambleloop.store_foundation import preview
    from brambleloop.visual import identity_gate as IG

    db = Database("sqlite://", scratch=True)
    db.create_all()
    rid = OB.identity_review_request(db)
    assert rid is not None and OB.identity_review_request(db) == rid      # idempotent
    done = IG.queue(db, state="resolved")
    assert len(done) == 1 and done[0]["decision"] == "confirmed_same_person"
    assert done[0]["image_sha256"] == BANNER_SHA and not IG.queue(db)
    item = next(x for x in preview.summary(db)["items"] if x["key"] == "storefront_banner")
    assert "laura_identity" not in item["unknown"], item
    # any other image: no owner review, the normal gate and queue apply
    other = hashlib.sha256(b"another frame of a woman").hexdigest()
    assert CA.owner_identity_review(other) is None
    assert CA.owner_identity_review(BANNER_SHA.upper())["decision"] == "D-FB-18"
    assert IG.assess({})["status"] == "UNKNOWN"
    saved = CA.ASSETS[CA.STOREFRONT_BANNER]
    try:
        CA.ASSETS[CA.STOREFRONT_BANNER] = dataclasses.replace(saved, sha256=other)
        g = next(x for x in OB._laura_gates() if x["gate"] == "laura_identity")
        assert g["status"] == "UNKNOWN" and "review" in g, g
    finally:
        CA.ASSETS[CA.STOREFRONT_BANNER] = saved
    assert CA.verify()["ok"]


def test_navigation_shows_only_populated_categories():
    import re

    from brambleloop.store_foundation import navigation as N, preview, preview_v2

    arch = {s["name"] for s in N.architecture()}
    public = {s["name"] for s in N.public_nav()}
    hidden = {s["name"] for s in N.hidden()}
    assert {"Wearables", "Gifts", "Seasonal"} <= arch          # kept in the data model
    assert {"Wearables", "Gifts", "Seasonal"} <= hidden and not ({"Wearables", "Gifts",
                                                                  "Seasonal"} & public)
    assert public and all(s["listings"] >= 1 for s in N.public_nav())
    for vp in ("mobile", "desktop"):
        html = preview.render_preview(None, vp, now=NOW, variant="v2")
        shop = html.split('<div class="frame">', 1)[1].split('<section class="board"', 1)[0]
        text = preview_v2.visible_text(shop)
        assert not N.empty_categories_named(text), N.empty_categories_named(text)
        chips = re.findall(r'<ul class="secs"[^>]*>(.*?)</ul>', shop, re.S)
        assert chips and not N.empty_categories_named(preview_v2.visible_text(chips[0]))
    # the banner's baked-in nav stays a reported truth finding (owner kept the source file)
    g = next(x for x in OB.assess()["gates"] if x["gate"] == "nav_categories_truth")
    assert g["status"] == "FAIL" and set(g["evidence"]["empty"]) == {"Wearables", "Gifts",
                                                                       "Seasonal"}


def test_etsy_evidence_is_recorded_with_sources():
    ev = {e["key"]: e for e in OB.ETSY_EVIDENCE}
    assert ev
    for e in ev.values():
        assert e["url"] and e["retrieved_at"].startswith("2026-10-06T"), e
        if e["status"].startswith("VERIFIED"):
            assert e["quotes"] and e.get("edited_at"), e
        else:
            assert not e["quotes"], e            # nothing quoted from an unread page
    assert ev["seller_policy_and_creativity_standards"]["status"] == "BLOCKED_403"
    assert "The recommended size is 1600 x 400px." in ev["big_banner_size"]["quotes"]
    assert ev["banner_aspect_or_crop"]["status"] == "NOT_STATED"
    tasks = {t["id"]: t for t in OB.VISUAL_TASKS}
    assert tasks["VT-B2-1"]["status"] == "GATED"
    assert tasks["VT-B2-2"]["status"] == "NOT_REQUIRED_BY_EVIDENCE"
    for t in tasks.values():
        assert "owner spend approval" in " ".join(t["gated_on"])
    # provenance metadata is never stripped from the canonical file
    assert b"caBX" in CA.verified_bytes(CA.STOREFRONT_BANNER)


def test_unknown_alone_blocks_publication():
    only_unknown = OB._rollup([{"gate": "laura_identity", "status": "UNKNOWN"},
                               {"gate": "canonical_integrity", "status": "PASS"}],
                              db_used=False)
    assert not only_unknown["publishable"] and only_unknown["status"] == "BLOCKED"
    all_pass = OB._rollup([{"gate": "canonical_integrity", "status": "PASS"}], db_used=False)
    assert all_pass["publishable"]
    adv = OB._rollup([{"gate": "canonical_integrity", "status": "PASS"},
                      {"gate": "f233_banner_canvas_4to1", "status": "UNVERIFIED_ASSUMPTION"}],
                     db_used=False)
    assert adv["publishable"] and "f233_banner_canvas_4to1" not in adv["passed"]


def test_identity_block_is_measured_not_declared():
    b = OB.measure_identity_block()
    assert b["found"] and b["elements"] >= 5, b
    y0, y1 = b["rows"]
    assert 0 < y0 < y1 < 793 and b["height_px"] > 1983 / 4      # taller than any 4:1 crop
    x0, x1 = b["cols"]
    assert 0 < x0 < 1983 / 2 < x1 < 1983


def test_candidates_are_owner_review_only_and_change_no_owner_pixel():
    import numpy as np

    orig = np.asarray(CA.image(CA.STOREFRONT_BANNER))
    cands = OB.candidates()
    assert len(cands) == 2
    for c in cands:
        assert c["status"] == "REJECTED_BY_OWNER" and c["adopted"] is False
        assert c["rejected_by"] == "D-FB-18 item 4"
        assert c["changes"]["owner_pixels_altered"] == 0
        assert abs(c["aspect"] - 4.0) <= 0.02, c["aspect"]
        a = np.asarray(c["image"])
        if c["id"].startswith("A"):
            t0, t1 = c["changes"]["rows_kept"]
            assert np.array_equal(a, orig[t0:t1 + 1]), c["id"]
        else:
            lp = c["changes"]["columns_added_left"]
            assert np.array_equal(a[:, lp:lp + orig.shape[1]], orig), c["id"]
        assert c["does_not_fix"]
        import io

        buf = io.BytesIO()
        c["image"].save(buf, "PNG")
        sha = hashlib.sha256(buf.getvalue()).hexdigest()
        assert not CA.is_authorised(CA.STOREFRONT_BANNER, sha, {"owner_decision_id": "D-FB-17"})


def test_committed_evidence_matches_the_code():
    ev = ROOT / "research/final_build/w3/owner_banner_candidates/owner_banner_assessment.json"
    md = ROOT / "research/final_build/w3/OWNER_BANNER_ASSESSMENT.md"
    assert ev.is_file() and md.is_file()
    rec = json.loads(ev.read_text())
    now = {g["gate"]: g["status"] for g in OB.assess()["gates"]}
    then = {g["gate"]: g["status"] for g in rec["assessment"]["gates"]}
    assert then == now, (then, now)
    text = md.read_text()
    assert then
    for gate, status in then.items():
        assert gate in text, gate
    assert rec["candidates"]
    for c in rec["candidates"]:
        p = ROOT / c["review_file"]
        assert p.is_file() and p.stat().st_size <= OB.REVIEW_MAX_BYTES, p
        assert hashlib.sha256(p.read_bytes()).hexdigest() == c["review_file_sha256"]
        assert c["status"] == "REJECTED_BY_OWNER" and c["adopted"] is False


# ---- storefront and visual consume the canonical assets -------------------------------------

def test_preview_is_built_around_the_owner_files():
    from brambleloop.store_foundation import preview

    html = preview.render_preview(None, "mobile", now=NOW, variant="v2")
    shop = html.split('<div class="frame">', 1)[1].split('<section class="board"', 1)[0]
    assert '--owner-banner:url("data:image/jpeg;base64,' in html
    assert 'class="bn obn"' in shop and "D-FB-17" in shop
    assert "confirmed by the owner's review of this banner (D-FB-18)" in shop
    assert "Internal preview" in shop and "not publication-approved" in shop
    assert 'class="herologo"' in shop
    choice = CA.shop_icon_choice()
    if choice["derivative"]:
        assert "small-size derivative of the owner artwork" in shop
    cards = __import__("re").findall(r'<article class="card">.*?</article>', shop, 16)
    assert len(cards) == 3
    for c in cards:
        assert "No picture of the finished piece yet" in c   # never a fabricated lifestyle
        assert "Digital rendering, not a photograph" in c
    board = html.split('<section class="board"', 1)[1]
    for needle in ("Canonical owner assets (D-FB-17)", "rejected by the owner",
                   "Etsy evidence", "VT-B2-1", "Hidden until populated",
                   "every publication gate on the exact file", "Truth findings for the owner",
                   "Listing image order"):
        assert needle in board, needle


def test_visual_judges_target_the_canonical_assets():
    from brambleloop.visual.rnd import judges as J

    t = J.brand_target()
    assert t["verified"] and t["banner_art_target"] == BANNER_SHA
    assert t["assets"]["hero_logo"]["sha256"] == LOGO_SHA
    png = CA.display_bytes(CA.STOREFRONT_BANNER, 400, fmt="PNG")
    r = J.brand_consistency(png)
    assert r["value"] is not None and r["metrics"]["brand_target_decision"] == "D-FB-17"
    with _TamperedDir(_flip_byte("brambleloop_owner_logo_canonical.png")):
        r = J.brand_consistency(png)
        assert r["value"] is None and r["reading"] == "UNKNOWN", r
    assert J.describe()["brand_target"]["verified"]


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)

if FAILS:
    print(f"FAILS {FAILS}")
    sys.exit(1)
print(f"OK all {len(_TESTS)} tests")
