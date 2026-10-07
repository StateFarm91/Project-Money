"""W4-VISUAL (F-030 / F-254): verified gallery frames enter the listing-set certificate.

The disclosed gallery frames (MATERIALS, COLOUR_CONTEXT, CONSTRUCTION, SIZING) and the vessel
ANGLE view are offered to the disclosed set's certificate only after re-verification on their
exact bytes against the certified CIR, follow the disclosed frames in order, each do a job no
other frame does, carry the disclosure first in their alt text, and add their own readings to
the four promotion gates without replacing any. Local, deterministic, no network, no spend.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_visual_cg_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from PIL import Image  # noqa: E402

from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.publish import disclosed_listing as DL  # noqa: E402
from brambleloop.publish import eligibility as el  # noqa: E402
from brambleloop.publish import layout_qa  # noqa: E402
from brambleloop.publish import listing_set as ls  # noqa: E402
from brambleloop.visual import launch_imagery as LI  # noqa: E402

_C: dict = {}


def primaries():
    if not _C:
        for listing in launch0.LAUNCH0_SLUGS:
            cand = launch0.candidate(listing)
            _C[listing] = launch0.cir_for(cand.variants[0].build)
    return _C


def _offer(cir):
    return LI.supplements_for_certificate(cir.slug, cir.version, start=4,
                                          store=ArtifactStore(os.path.join(_TMP, "a")),
                                          release_fingerprint=cir.fingerprint)


def test_every_launch0_primary_is_offered_its_verified_applicable_jobs():
    cirs = primaries()
    # One explicit entry per Launch-0 listing, derived from launch0.LAUNCH0_SLUGS: a listing
    # promoted into Launch-0 without an entry here FAILS (it is never silently skipped).
    # Offered without a database, so CONTENTS (which needs the release's assets.built PDF)
    # is refused here with its reason; it is certified on the release path
    # (tests/test_w4_visual2.py, test_disclosed_certified_upload).
    want = {"nursery-nesting-baskets": ["ANGLE", "CONSTRUCTION", "COLOUR_CONTEXT", "SIZING",
                                        "MATERIALS"],
            "cloudline-baby-blanket": ["COLOUR_CONTEXT", "MATERIALS"],
            "hexagon-coaster-set": ["COLOUR_CONTEXT", "MATERIALS"],
            # promoted by lane PIPE (18baa94); both are flat colourwork pieces
            "nordic-star-ornaments": ["COLOUR_CONTEXT", "MATERIALS"],
            "winter-village-graphghan": ["COLOUR_CONTEXT", "MATERIALS"]}
    assert cirs and list(cirs) == list(launch0.LAUNCH0_SLUGS), cirs.keys()
    missing = sorted(set(cirs) - set(want))
    assert not missing, f"Launch-0 listings with no expected gallery jobs: {missing}"
    for listing, cir in cirs.items():
        offer = _offer(cir)
        jobs = [f["job"] for f in offer["frames"]]
        assert jobs == want[listing], (listing, jobs, offer["refused"])
        assert "CONTENTS" in offer["refused"], (listing, offer["refused"])
        assert [f["position"] for f in offer["frames"]] == list(range(4, 4 + len(jobs)))
        for f in offer["frames"]:
            assert hashlib.sha256(f["png"]).hexdigest() == f["sha256"]
            assert LI.check_supplement(cir.slug, cir.version, f["job"], f["png"])["status"] \
                == "PASS", (listing, f["job"])
            assert f["alt_text"].startswith(DL.DISCLOSURE) and DL._phrase_in(f["alt_text"])
            assert len(f["alt_text"]) <= DL.ALT_TEXT_MAX
            assert f["alt_text"] == LI.expected_alt_text(cir.slug, f["job"])
            assert f["purpose"] in el.JOB_PURPOSES[f["job"]]
            # The release path keeps a frame only if layout QA passes it at listing scale
            # with type expected; every offered Launch-0 frame must (MATERIALS failed
            # FRAME_FLAT at gallery-frames/1.0.0).
            report = layout_qa.inspect(Image.open(io.BytesIO(f["png"])).convert("RGB"),
                                       position=f["position"], expect_text=True)
            assert not report.problems, (listing, f["job"], report.problems)


def test_tampered_bytes_another_version_or_a_non_primary_slug_never_verify():
    cir = primaries()["hexagon-coaster-set"]
    offer = _offer(cir)
    assert offer["frames"], offer
    png = offer["frames"][0]["png"]
    job = offer["frames"][0]["job"]
    bad = bytearray(png)
    bad[-20] ^= 0xFF
    assert LI.check_supplement(cir.slug, cir.version, job, bytes(bad))["status"] == "FAIL"
    assert LI.check_supplement(cir.slug, "0.0.1", job, png)["status"] == "FAIL"
    assert LI.check_supplement("market-basket-medium", cir.version, job, png)["status"] == "FAIL"
    assert LI.check_supplement(cir.slug, cir.version, "LIFESTYLE", png)["status"] == "FAIL"
    # A release whose CIR is not the certified one gets no frames at all.
    other = LI.supplements_for_certificate(cir.slug, cir.version, start=4,
                                           release_fingerprint="0" * 64)
    assert other["frames"] == [] and other["refused"], other
    # A disclosed set already doing a job is not offered a second frame for it.
    excl = LI.supplements_for_certificate(cir.slug, cir.version, start=4,
                                          exclude_jobs={"MATERIALS"},
                                          release_fingerprint=cir.fingerprint)
    assert "MATERIALS" not in [f["job"] for f in excl["frames"]], excl


def _fake_set(slug="hexagon-coaster-set", version="1.2.0"):
    """A minimal disclosed record and exported images, bound by hash (listing_set unit level)."""
    frames, images = [], []
    for pos, (view, job) in enumerate((("hero", "DESIRE"), ("scale", "SCALE"),
                                       ("detail", "DETAIL")), start=1):
        data = f"{view}-bytes".encode()
        alt = f"{DL.DISCLOSURE}. {view}"
        frames.append({"position": pos, "view": view, "alt_text": alt,
                       "image": {"sha256": hashlib.sha256(data).hexdigest()},
                       "structural_truth": {"status": "PASS"},
                       "disclosed_render": {"job": job, "finished_dimensions_cm": {}}})
        images.append((f"{view}.png", data, alt))
    ok = {"ok": True}
    rec = {"kind": ls.DISCLOSED_RENDER, "slug": slug, "version": version,
           "usable_as_listing_asset": True, "frames": frames,
           "qa": {"asset_truth": ok, "layout_qa": ok, "frame_set": ok, "mobile": ok,
                  "hero_thumbnail": ok,
                  "frames": {v: {"legibility_340": ok} for v in ("hero", "scale", "detail")}}}
    return rec, images


def _supp(position, job, kind=ls.DISCLOSED_SUPPLEMENT):
    return ls.CertifiedFrame(position=position, asset_id=f"s-{job}", sha256="ab" * 32, job=job,
                             purpose=el.CUSTOMER_INFORMATION, medium="digital_twin_render",
                             honesty_label=DL.DISCLOSURE, kind=kind,
                             alt_text=f"{DL.DISCLOSURE}. {job}")


def _certify(rec, images, supplements, qa):
    return ls.certify_disclosed(slug=rec["slug"], version=rec["version"], rec=rec,
                                images=images, geometry={"w": 1}, claims={},
                                policy_version="p", dimensions_ok=True,
                                supplements=supplements, supplement_qa=qa)


def test_the_certificate_takes_supplements_only_in_order_with_readings_and_distinct_jobs():
    from brambleloop.gates.asset_truth import AssetClass

    medium = AssetClass.DIGITAL_TWIN_RENDER.value
    rec, images = _fake_set()
    good = {"verified": [True, True], "layout_qa": {"ok": True}, "frame_set": {"ok": True}}
    sup = [_supp(4, "COLOUR_CONTEXT"), _supp(5, "MATERIALS")]
    sup = [ls.CertifiedFrame(**{**f.__dict__, "medium": medium}) for f in sup]
    cert = _certify(rec, images, sup, good)
    jobs = [f.job for f in sorted(cert.frames, key=lambda f: f.position)]
    assert jobs == ["DESIRE", "SCALE", "DETAIL", "COLOUR_CONTEXT", "MATERIALS"], jobs
    assert set(cert.gate_results.values()) == {el.PASSED}, cert.gate_results
    refusals = [
        (sup, None),                                                    # no readings
        (sup, {**good, "verified": [True]}),                            # a frame unread
        ([sup[1].__class__(**{**sup[1].__dict__, "position": 6})], good | {"verified": [True]}),
        ([sup[0].__class__(**{**sup[0].__dict__, "job": "DETAIL"})], good | {"verified": [True]}),
        ([sup[0].__class__(**{**sup[0].__dict__, "kind": ls.DISCLOSED_RENDER})],
         good | {"verified": [True]}),
    ]
    for supplements, qa in refusals:
        try:
            _certify(rec, images, supplements, qa)
        except ls.ListingSetRefused:
            continue
        raise AssertionError(f"certified a set it must refuse: {supplements} {qa}")
    # A disclosed-gallery frame without the disclosure in its alt text cannot even be built.
    try:
        ls.CertifiedFrame(**{**sup[0].__dict__, "alt_text": "A photo of coasters"})
    except ls.ListingSetRefused:
        pass
    else:
        raise AssertionError("a disclosed gallery frame was built without its disclosure")


def test_supplement_readings_add_to_the_gates_and_never_replace_them():
    rec, _images = _fake_set()
    base = ls.disclosed_gate_results(rec, exported=True, dimensions_ok=True)
    assert set(base.values()) == {el.PASSED}
    good = {"verified": [True], "layout_qa": {"ok": True}, "frame_set": {"ok": True}}
    assert ls.disclosed_gate_results(rec, exported=True, dimensions_ok=True,
                                     supplement_qa=good) == base
    for key, gate in (("verified", el.DATA_TRUTH), ("layout_qa", el.LAYOUT_QA),
                      ("frame_set", el.COMMERCIAL_QA)):
        bad = dict(good)
        bad[key] = [False] if key == "verified" else {"ok": False}
        got = ls.disclosed_gate_results(rec, exported=True, dimensions_ok=True,
                                        supplement_qa=bad)
        assert got[gate] == el.FAILED, (key, got)
        unread = dict(good)
        unread[key] = [True] if key == "verified" else {}
        if key != "verified":
            got = ls.disclosed_gate_results(rec, exported=True, dimensions_ok=True,
                                            supplement_qa=unread)
            assert got[gate] == el.NOT_RUN, (key, got)
    # The set's own failing reading still fails with perfect supplement readings.
    rec["qa"]["layout_qa"] = {"ok": False}
    got = ls.disclosed_gate_results(rec, exported=True, dimensions_ok=True, supplement_qa=good)
    assert got[el.LAYOUT_QA] == el.FAILED, got


def test_relief_tone_clears_separation_without_moving_launch0_palettes():
    from brambleloop.visual import render_contract as K

    gold = K.hex_rgb("#C49545")
    assert K._dist(gold, K.relief(gold)) >= K.MIN_SEPARATION, K.relief(gold)
    assert K.MIN_SEPARATION == 40.0   # the minimum itself is unchanged
    # Launch-0 yarns keep the exact pre-W4 tone (15 % darker light, 30 % lighter dark).
    for hexv in ("#FAF6EB", "#6E1F2A", "#1A2B3C"):
        r, g, b = K.hex_rgb(hexv)
        light = 0.2126 * r + 0.7152 * g + 0.0722 * b > 128
        old = ((int(r * 0.85), int(g * 0.85), int(b * 0.85)) if light else
               (int(r + (255 - r) * 0.3), int(g + (255 - g) * 0.3), int(b + (255 - b) * 0.3)))
        assert K.relief((r, g, b)) == old, hexv


def test_catalogue_products_get_a_render_authority_and_verified_gallery_frames():
    from brambleloop.visual import disclosed_render as DR
    from brambleloop.visual import render_verification as RV

    for slug in ("pet-snuggle-mat", "harvest-table-runner"):
        cir = RV.authoritative_cir(slug)
        assert cir is not None and cir.slug == slug, slug
        assert RV.authoritative_cir(slug, "0.0.1") is None
        fr = DR.render(cir, "hero")   # refused before: gold sat 39.4 from its relief tone
        assert RV.verify(fr.png, cir=cir, view="hero")["status"] == "PASS", slug
        offer = _offer(cir)
        assert [f["job"] for f in offer["frames"]] == ["COLOUR_CONTEXT", "MATERIALS"], offer
    assert RV.authoritative_cir("unregistered-design-no-authority") is None


def test_a_basket_sibling_released_under_its_own_slug_gets_its_own_frames_without_sizing():
    med = launch0.cir_for("basket_medium")
    offer = _offer(med)
    assert [f["job"] for f in offer["frames"]] == ["ANGLE", "CONSTRUCTION", "COLOUR_CONTEXT",
                                                   "MATERIALS"], offer
    for f in offer["frames"]:
        assert LI.check_supplement(med.slug, med.version, f["job"], f["png"])["status"] == "PASS"
    # Its own CIR: the shape-bearing frames differ from the small basket's (MATERIALS may
    # legitimately be identical -- same yarns, hook and gauge).
    small = {f["job"]: f["sha256"] for f in _offer(primaries()["nursery-nesting-baskets"])["frames"]}
    mine = {f["job"]: f["sha256"] for f in offer["frames"]}
    assert all(mine[j] != small[j] for j in ("ANGLE", "CONSTRUCTION")), (mine, small)


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    assert tests
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
