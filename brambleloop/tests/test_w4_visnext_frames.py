"""W-VISNEXT follow-ups: (7) the approved outfit reference carried to FLUX after the canonical
three, and (6) generated ListingAsset frames with a truthful provenance, judged per role by
both listing-set paths, still refused by F-852.

No network and no spend: `StubRenderer` everywhere, scratch databases.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import hashlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_flux3generator as FG3  # noqa: E402
import test_w4_fluxstages as FS  # noqa: E402

from brambleloop.creative import flux3_generator as FG  # noqa: E402
from brambleloop.creative import image_stages as S  # noqa: E402

LAURA = list(S.LAURA_ROLES)


def _outfit_png(rgb=(10, 200, 10)) -> str:
    return FS._png(f"outfit-{rgb[0]}-{rgb[1]}.png", rgb)


# ---- (7) the outfit reference ----------------------------------------------------------------

def test_outfit_reference_follows_the_canonical_three_and_is_in_the_receipt():
    rel = FS._release()
    stub = S.StubRenderer()
    prod = FS._product(stub)
    path = _outfit_png()
    c = FS._life(rel, prod, FS._canon_paths(), {**FS.OUTFIT, "image": path}, renderer=stub,
                 work_dir=str(FS._WORK / "vn-outfit"))
    roles = [r["role"] for r in c.receipt["references"]]
    assert roles[:3] == LAURA, roles
    assert roles == list(S.CAMPAIGN_MINIMUM) + ["product_candidate", "outfit"]
    assert len(roles) == 9 <= c.receipt["reference_limit"] == 10
    want = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert c.receipt["outfit_reference"] == {"position": 9, "sha256": want}
    assert stub.calls[-1]["refs"][8] == path                        # actually sent, 9th
    assert tuple(c.receipt["input_sha256s"][:3]) == S.canonical_laura_hashes()


def test_over_the_limit_uses_the_combined_sheet_or_refuses_never_drops():
    rel = FS._release()
    stub8 = S.StubRenderer(reference_limit=8)
    prod = FS._product(stub8)
    c = FS._life(rel, prod, FS._canon_paths(), {**FS.OUTFIT, "image": _outfit_png((9, 9, 9))},
                 renderer=stub8, work_dir=str(FS._WORK / "vn-sheet"))
    roles = [r["role"] for r in c.receipt["references"]]
    assert roles == LAURA + ["product_combined", "product_candidate", "outfit"], roles
    assert "merged losslessly" in c.receipt["limitation"]
    assert c.receipt["outfit_reference"]["position"] == 6
    tiny = S.StubRenderer(reference_limit=5)
    before = len(tiny.calls)
    assert FS._refused(lambda: FS._life(rel, prod, FS._canon_paths(),
                                        {**FS.OUTFIT, "image": _outfit_png((8, 8, 8))},
                                        renderer=tiny, work_dir=str(FS._WORK / "vn-tiny")))
    assert len(tiny.calls) == before                                # nothing was sent


def test_an_identity_reference_can_never_be_the_outfit_reference():
    rel = FS._release()
    stub = S.StubRenderer()
    prod = FS._product(stub)
    face = FS._canon_paths()[0]
    before = len(stub.calls)
    assert FS._refused(lambda: FS._life(rel, prod, FS._canon_paths(),
                                        {**FS.OUTFIT, "image": face}, renderer=stub,
                                        work_dir=str(FS._WORK / "vn-face")))
    assert len(stub.calls) == before


def test_the_generator_sends_only_the_outfits_approved_reference():
    g, stub = FG3._gen()
    assert g.accepts_outfit_reference is True
    refs = FG3._orchestrator_refs(g.prepare_references(slug=FG3.SLUG, version=FG3.VER,
                                                       release=FG3.REL))
    out = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="flat",
                     references=refs, outfit=None, attempt=1)
    g.anchor_lookup = lambda s, v, r: {"data": out["data"], "status": "PASS",
                                       "sha256": hashlib.sha256(out["data"]).hexdigest(),
                                       "checker": "stub"}
    data = Path(_outfit_png((40, 90, 160))).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    oref = {"kind": "prior_candidate", "label": "outfit_reference", "sha256": sha,
            "data": data}
    outfit = {**FG3.OUTFIT, "approved_reference": sha}
    life = g.generate(stage="lifestyle_generation", role="lifestyle", brief="sofa",
                      references=refs + FG3._laura_refs() + [oref], outfit=outfit, attempt=1)
    ev = life["identity_evidence"]
    assert tuple(ev["input_sha256s"][:3]) == S.canonical_laura_hashes()
    assert ev["outfit_reference"]["sha256"] == sha and ev["input_sha256s"][-1] == sha
    # not the outfit's approved reference: refused before anything is sent
    n = len(stub.calls)
    assert FG3._refused(lambda: g.generate(
        stage="lifestyle_generation", role="lifestyle", brief="sofa",
        references=refs + FG3._laura_refs() + [oref],
        outfit={**FG3.OUTFIT, "approved_reference": "0" * 64}, attempt=1), FG.GeneratorRefused)
    assert len(stub.calls) == n
    # no reference handed in: nothing extra is sent (unchanged behaviour)
    plain = g.generate(stage="lifestyle_generation", role="lifestyle", brief="sofa",
                       references=refs + FG3._laura_refs(), outfit=FG3.OUTFIT, attempt=1)
    assert plain["identity_evidence"]["outfit_reference"] is None


# ---- (6) generated ListingAsset frames ---------------------------------------------------------

def _candidate(db):
    """A real stored generated candidate (stub judges), as image production records one."""
    import test_w4_ownerimg as O
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_production as IP

    c = O.cand(role="lifestyle", release=O.RELEASE, provenance_kind="ai_generated_autonomous")
    v = CG.evaluate(db, c, judges=O.StubJudges(), record_outfit_use=False)
    IP.store_bytes(db, c["data"], key="t/lifestyle/1", why="test")
    rec = IP.record_candidate(db, c, v, method="autonomous", run="t")
    return rec["candidate_id"], v["sha256"]


def test_written_frame_gets_a_truthful_ai_generated_provenance_row():
    import test_w4_ownerimg as O
    from sqlalchemy import select

    from brambleloop.core.models import ArtefactProvenance, AuditLog, ListingAsset
    from brambleloop.ops import artefacts as provenance
    from brambleloop.visual import gallery_persist as GP

    db = O.make_db()
    cid, sha = _candidate(db)
    w = GP.write_frames(db, O.CLOUD if hasattr(O, "CLOUD") else "cloudline-baby-blanket",
                        "1.2.0", [{"position": 2, "role": "lifestyle", "job": "LIFESTYLE",
                                   "candidate_id": cid, "sha256": sha}], run_key="t")
    assert w["written"] == [2], w
    with db.session() as s:
        asset = s.scalar(select(ListingAsset))
        row = s.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "visual_truth",
            ArtefactProvenance.artefact_key == provenance.visual_key(
                "cloudline-baby-blanket", "1.2.0", asset.id)))
        audit = s.scalar(select(AuditLog).where(
            AuditLog.action == "images.listing_asset_written"))
        assert row is not None and row.sha256 == sha and asset.sha256 == sha
        assert row.evidence["kind"] == "ai_generated_autonomous"
        assert row.evidence["is_photograph"] is False
        assert row.evidence["audit_id"] == audit.id and row.source == "backfilled"
        assert asset.claims["is_photograph"] is False
    # bytes with no matching generated-candidate record: refused, nothing written
    db2 = O.make_db()
    bad = GP.write_frames(db2, "cloudline-baby-blanket", "1.2.0",
                          [{"position": 2, "role": "lifestyle", "candidate_id": 1,
                            "sha256": "c" * 64}], run_key="t")
    assert bad["refused"] and bad["written"] == []
    with db2.session() as s:
        assert s.scalar(select(ListingAsset)) is None


def test_listing_set_judges_the_generated_frame_on_its_own_record_and_f852_refuses():
    import test_w4_ownerimg as O
    from brambleloop.publish import release_gates as RG
    from brambleloop.visual import gallery_persist as GP

    db = O.make_db()
    cid, sha = _candidate(db)
    GP.write_frames(db, "cloudline-baby-blanket", "1.2.0",
                    [{"position": 2, "role": "lifestyle", "job": "LIFESTYLE",
                      "candidate_id": cid, "sha256": sha}], run_key="t")
    out = RG.listing_set(db, slug="cloudline-baby-blanket", version="1.2.0", issue=True)
    f = [x for x in out["frames"] if x["position"] == 2][0]
    assert f["job"] == "LIFESTYLE"
    # judged on its own verification record, not "assets.build never ran"
    assert f["gates"]["POLICY_PROVENANCE"] == "passed"
    assert f["gates"]["DATA_TRUTH"] == "passed" and f["gates"]["LAYOUT_QA"] == "passed"
    assert f["may_export"] is False and "F-852" in f["why"]
    assert out["blocks_release"] is True and not (out.get("certificate") or {}).get("valid")


def test_the_disclosed_path_judges_generated_frames_and_excludes_refused_ones():
    import test_w4_ownerimg as O
    from brambleloop.publish import release_gates as RG
    from brambleloop.visual import gallery_persist as GP

    db = O.make_db()
    cid, sha = _candidate(db)
    GP.write_frames(db, "cloudline-baby-blanket", "1.2.0",
                    [{"position": 2, "role": "lifestyle", "job": "LIFESTYLE",
                      "candidate_id": cid, "sha256": sha}], run_key="t")
    cir, release_hash = RG._release(db, "cloudline-baby-blanket", "1.2.0")
    out = RG.disclosed_listing_set(
        db, slug="cloudline-baby-blanket", version="1.2.0", cir=cir, twin=RG._twin(db, cir),
        listing=None, rec={"frames": []}, frames=RG._frames(db, "cloudline-baby-blanket",
                                                            "1.2.0"),
        release_hash=release_hash, issue=False, persist_supplements=False)
    assert out["generated_frames"] and out["generated_frames"][0]["position"] == 2
    assert out["generated_frames"][0]["may_export"] is False
    assert "F-852" in out["generated_frames"][0]["why"]
    assert out["generated_excluded"] == [2]
    # a generated frame that somehow passed would block, never ride on the disclosed cert
    saved = RG.generated_frame_verdict
    try:
        RG.generated_frame_verdict = lambda *a, **k: {"position": 2, "role": "lifestyle",
                                                      "job": "LIFESTYLE", "may_export": True,
                                                      "why": ""}
        forced = RG.disclosed_listing_set(
            db, slug="cloudline-baby-blanket", version="1.2.0", cir=cir,
            twin=RG._twin(db, cir), listing=None, rec={"frames": []},
            frames=RG._frames(db, "cloudline-baby-blanket", "1.2.0"),
            release_hash=release_hash, issue=False, persist_supplements=False)
    finally:
        RG.generated_frame_verdict = saved
    assert forced["blocks_release"] and any("mixed set" in r for r in forced["reasons"])


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and fn.__module__ == __name__:
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
