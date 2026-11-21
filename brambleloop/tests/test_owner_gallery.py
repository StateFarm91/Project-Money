"""ENG-OWNER-GALLERY: owner-supplied frames pass the same gates as generated ones.

`visual.owner_frames.ingest` is proven on the ENG-VIS-GALLERY world
(`test_vis_gallery_e2e`). That world has a certified release, its CIR anchor and reference
renders, the deterministic CONTENTS frame, the US/UK PDFs and drafted listing copy. The
"owner files" are the bytes that world's generated run made, handed back through the owner
door with the references they were conditioned on. They are then judged by the same
judges (`GalleryJudges`, whose doubles are labelled `test_double` in every reading).

Proven here:
1. An owner set that passes certifies like a generated set: the same listing-set
   certificate, kinds and order.
2. A frame whose scale contradicts the CIR is refused. Nothing is written, and the blocker
   names the file and the gate.
3. No buyer-facing alt text or label says "rendering". The pixels are stored unchanged, so
   no label or watermark is drawn on them.
4. Provenance is still recorded internally: the candidate row, the asset claims, the
   receipt audit and the lineage.
5. Copy that claims a made sample, a test or "I made this" is refused.
6. The wall stripe layout is measured in code against the CIR: a correct vessel strip
   passes, and the owner frames' wide stripe spacing fails.

The pointer (scale and wall-strip boxes) is a stub labelled as one; code does every
measurement.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_owner_gallery.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import hashlib
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

_S: dict = {}
ROLES = ("hero", "colour_context", "lifestyle", "angle", "detail", "size")
SCENES = {"hero": "on a sofa in a warm living room",
          "colour_context": "laid flat on a pale floor, every edge in view",
          "lifestyle": "draped over a chair by a window",
          "angle": "folded over the arm of a sofa, showing the reverse",
          "detail": "close view of the stitches and stripes",
          "size": "beside a bed pillow on a made bed"}
RENDER_RX = re.compile(r"\brender", re.IGNORECASE)


class Pointer:
    """Stub pointer (labelled): answers visual.scale with boxes that put the product at
    `factor` x its CIR size beside a bed pillow, and has no wall strip (not a vessel)."""

    name = "test_double pointer"

    def __init__(self, cir, *, factor=1.0, only_sha=None):
        from brambleloop.visual import scale as SC

        self.expected = SC.expected_cm(cir)
        self.factor, self.only_sha = factor, only_sha
        self.calls = 0

    def read(self, prompt, images, *, system, max_tokens):
        from PIL import Image

        from brambleloop.visual import scale as SC

        self.calls += 1
        if "Task: product_scale" not in prompt:
            return {"answered": False, "why": "stub: no wall strip on a flat piece"}
        w, h = Image.open(io.BytesIO(images[0])).size
        sha = hashlib.sha256(images[0]).hexdigest()
        f = self.factor if (self.only_sha is None or sha == self.only_sha) else 1.0
        a_px = 0.15 * h                     # pillow, upright and narrow: its height is long
        p_px = a_px * self.expected * f / SC.ANCHORS["pillow"]
        assert p_px / w < 0.95 and p_px > 0.05 * h, (p_px, w, h)
        return {"answered": True, "reading": {
            "anchor": "pillow", "anchor_box": [0.01, 0.05, 0.01 + 0.03 * h / w * 0.5, 0.20],
            "product_box": [0.02, 0.50, 0.02 + p_px / w, 0.55], "setting": "scene"}}


def world():
    """The e2e world, its generated run's bytes, and the owner file specs built from them."""
    if not _S.get("done"):
        import test_search_hero_publish as SH
        import test_vis_gallery_e2e as E
        from brambleloop.core.artifacts import ArtifactStore
        from brambleloop.core.db import Database
        from brambleloop.visual import image_production as IP
        from brambleloop.visual.image_records import ImageCandidate

        path, version, rh = SH._chain()
        db = Database(f"sqlite:///{path}")
        R = E.run_gallery(db)
        run = IP.get_run(db, R["key"])
        specs = []
        for role in ROLES:
            best = IP._best(db, listing=run["listing"], role=role, run=R["key"])
            assert best is not None, role
            with db.session() as s:
                row = s.get(ImageCandidate, best["candidate_id"])
                refs = [dict(r) for r in row.references or []]
                laura, outfit = bool(row.laura_present), row.outfit_id or None
            specs.append({"name": f"owner-{role}.png", "role": role, "laura_present": laura,
                          "outfit_id": outfit, "references": refs, "scene": SCENES[role],
                          "data": ArtifactStore().get(best["sha256"], db=db)})
        _S.update(db=db, R=R, cir=R["cir"], version=R["cir"].version, slug=R["cir"].slug,
                  specs=specs, E=E, done=True)
    return _S


def _ingest(S, specs, pointer):
    from brambleloop.visual import owner_frames as OF

    with S["E"].laura_publication_double(S["db"]):
        return OF.ingest(S["db"], S["slug"], S["version"], specs, actor="owner",
                         judges=S["R"]["judges"], pointer=pointer)


def _gallery_assets(db):
    from sqlalchemy import select

    from brambleloop.core.models import ListingAsset

    with db.session() as s:
        return [a for a in s.scalars(select(ListingAsset))
                if (a.claims or {}).get("route") == "generated_gallery"]


# ---- 2 first: a refusal writes nothing, so the passing set below starts clean ---------------

def test_1_a_frame_whose_scale_contradicts_the_cir_is_refused():
    S = world()
    size = next(s for s in S["specs"] if s["role"] == "size")
    sha = hashlib.sha256(size["data"]).hexdigest()
    p = Pointer(S["cir"], factor=2.1, only_sha=sha)
    out = _ingest(S, S["specs"], p)
    assert out["certified"] is False, out.get("why")
    assert p.calls >= len(S["specs"]), p.calls        # every frame was asked, none skipped
    mine = [b for b in out["blockers"] if b["gate"] == "product_scale"]
    assert len(mine) == 1 and mine[0]["file"] == "owner-size.png", out["blockers"]
    assert mine[0]["status"] == "FAIL" and "against the CIR's" in mine[0]["why"], mine
    # only the contradicted frame is refused on scale; every other frame passed it
    others = [f for f in out["frames"] if f["role"] != "size"]
    assert len(others) == 5 and all(f["gates"]["product_scale"]["status"] == "PASS"
                                    for f in others), [f["gates"]["product_scale"]
                                                       for f in others]
    assert _gallery_assets(S["db"]) == [], "a refused set writes nothing"
    S["refused"] = out


def test_2_an_owner_set_that_passes_certifies_like_a_generated_set():
    from sqlalchemy import select

    from brambleloop.core.models import ListingSetCertificateRecord

    S = world()
    out = _ingest(S, S["specs"], Pointer(S["cir"]))
    assert out["blockers"] == [], [(b["file"], b["gate"], b["status"], b["why"][:200])
                                   for b in out["blockers"]]
    assert out["certified"] is True, out.get("why")
    with S["db"].session() as s:
        cert = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.state == "valid"))
    frames = cert.certificate["frames"]
    # the same certificate a generated gallery gets (test_vis_gallery_e2e test_2)
    assert [f["job"] for f in frames] == ["DESIRE", "COLOUR_CONTEXT", "LIFESTYLE", "ANGLE",
                                          "DETAIL", "SCALE", "CONTENTS"], frames
    assert all(f["kind"] == "generated_render" for f in frames[:6])
    assert frames[6]["kind"] == "disclosed_gallery_frame"
    assert [f["sha256"] for f in frames[:6]] == [hashlib.sha256(s["data"]).hexdigest()
                                                 for s in S["specs"]]
    assert len(_gallery_assets(S["db"])) == 6
    S["certified"], S["cert"] = out, cert.certificate


def test_3_no_buyer_facing_alt_text_or_label_contains_rendering():
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.visual import owner_frames as OF

    S = world()
    if "cert" not in S:
        test_2_an_owner_set_that_passes_certifies_like_a_generated_set()
    owner = S["cert"]["frames"][:6]
    assert len(owner) == 6
    for f in owner:
        alt = f["alt_text"]
        assert not RENDER_RX.search(alt), alt
        assert not re.search(r"\bphoto", alt, re.IGNORECASE), alt
        assert alt.startswith(OF.product_phrase(S["cir"])), alt
        # no label drawn: the stored bytes are the owner's bytes, unchanged
        assert hashlib.sha256(ArtifactStore().get(f["sha256"], db=S["db"])).hexdigest() \
            == f["sha256"]
    assert {f["alt_text"] for f in owner} == {OF.alt_text(S["cir"], SCENES[r]) for r in ROLES}
    # a scene that says "rendering" is refused at intake, never certified
    from brambleloop.visual import candidate_gates as CG

    bad = OF.alt_text(S["cir"], "a digital rendering on a sofa")
    assert OF.buyer_text_problems(bad, surface="alt"), bad
    # and the listing set re-checks an owner selection's alt text on its own path
    from brambleloop.publish import release_gates as RG
    from brambleloop.visual import gallery_persist as GP

    sel = RG.generated_selection(S["db"], S["slug"], S["version"])
    assert sel and sel.get("supplied_by") == "owner"
    tampered = {**sel, "frames": [dict(x) for x in sel["frames"]]}
    tampered["frames"][0]["alt_text"] = "Digital rendering of the basket"
    from brambleloop.core.models import AuditLog

    with S["db"].session() as s:
        s.add(AuditLog(actor="test", action=GP.SELECTED_ACTION,
                       artifact=f"{S['slug']}@{S['version']}", detail=tampered))
    try:
        ls = RG.listing_set(S["db"], slug=S["slug"], version=S["version"], issue=False,
                            store_renders=True)
        assert ls["blocks_release"] and any("render" in r for r in ls["reasons"]), \
            ls["reasons"]
    finally:
        with S["db"].session() as s:
            s.add(AuditLog(actor="test", action=GP.SELECTED_ACTION,
                           artifact=f"{S['slug']}@{S['version']}", detail=sel))
    assert CG.PASS == "PASS"


def test_4_provenance_is_still_recorded_internally():
    from sqlalchemy import select

    from brambleloop.core.models import ArtefactProvenance, AuditLog
    from brambleloop.visual import canonical
    from brambleloop.visual import owner_frames as OF
    from brambleloop.visual.image_records import ImageCandidate

    S = world()
    if "certified" not in S:
        test_2_an_owner_set_that_passes_certifies_like_a_generated_set()
    shas = {hashlib.sha256(s["data"]).hexdigest() for s in S["specs"]}
    assets = _gallery_assets(S["db"])
    assert {a.sha256 for a in assets} == shas
    for a in assets:
        c = a.claims
        assert c["supplied_by"] == "owner" and c["is_photograph"] is False, c
        assert c["provenance_kind"] == OF.PROVENANCE_KIND and c["is_render"] is True, c
        assert c["physical_sample_evidence"] is False
    with S["db"].session() as s:
        rows = [r for r in s.scalars(select(ImageCandidate).where(
            ImageCandidate.method == OF.METHOD)) if r.sha256 in shas]
        received_rows = [(r.id, r.detail) for r in s.scalars(select(AuditLog).where(
            AuditLog.action == OF.RECEIVED_ACTION))]
    received = [d for _i, d in received_rows]
    receipts = {hashlib.sha256(f"{OF.RECEIVED_ACTION}:{i}:{d['sha256']}".encode()).hexdigest()
                for i, d in received_rows}
    assert rows and {r.sha256 for r in rows} == shas
    for r in rows:
        assert r.provenance_kind == OF.PROVENANCE_KIND
        assert (r.checks.get("_route") or {}).get("supplied_by") == "owner", r.checks.get(
            "_route")
        assert r.provider == OF.DEFAULT_PROVIDER and "FLUX 3" in r.model, (r.provider,
                                                                          r.model)
        assert r.run_key.endswith(OF.RUN_SUFFIX)
        # the receipt binds the candidate to its own intake audit row and bytes
        assert ((r.checks.get("_identity_evidence") or {}).get("request") or {}).get(
            "request_sha256") in receipts, r.checks.get("_identity_evidence")
    with S["db"].session() as s:
        lineage = {r.sha256: r for r in s.scalars(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "visual_truth")) if r.sha256 in shas}
    assert set(lineage) == shas, sorted(lineage)
    for r in lineage.values():
        assert r.provider == OF.DEFAULT_PROVIDER and "FLUX 3" in r.model, (r.provider, r.model)
    got = {d["sha256"]: d for d in received}
    assert set(got) >= shas
    for sha in shas:
        d = got[sha]
        assert d["is_photograph"] is False and d["supplied_by"] == "owner"
        assert d["generator"] == OF.DEFAULT_GENERATOR and len(d["sha256"]) == 64
        if d["laura_present"]:
            assert d["laura_identity"] == canonical.IDENTITY_ID
    # ...and none of it reaches a buyer: the alt texts never name the generator or model
    assert len(S["cert"]["frames"][:6]) == 6
    for f in S["cert"]["frames"][:6]:
        assert "FLUX" not in f["alt_text"] and "laura-" not in f["alt_text"].lower()


def test_5_copy_claiming_a_made_sample_is_refused():
    from brambleloop.gates.estimate_claims import ESTIMATE_NOTE
    from brambleloop.visual import owner_frames as OF

    refused = ["I made this basket over a weekend.",
               "Photos show my finished sample in our living room.",
               "Pattern tested by our testers.",
               "The sample measures 16 cm across.",
               "Handmade by me and photographed at home.",
               "We crocheted this one in cream and wine."]
    assert len(refused) == 6
    for text in refused:
        try:
            OF.check_listing_copy(text)
        except OF.CopyRefused as exc:
            assert str(exc), text
        else:
            raise AssertionError(f"made-sample copy passed: {text!r}")
    honest = ("Crochet pattern for a hexagonal basket, about 16 cm across the points. "
              + ESTIMATE_NOTE + " Images are illustrative of the design.")
    assert OF.check_listing_copy(honest)["ok"] is True
    assert OF.buyer_text_problems("not yet tested on a physical sample") == []


def _strip(rows: list[tuple[str, int]], px_per_row: int = 12) -> bytes:
    from PIL import Image, ImageDraw

    from brambleloop.visual import vessel as V
    from brambleloop.products import launch0

    pal = V.vessel_models(launch0.cir_for("basket_small"))[0].palette
    h = sum(n for _c, n in rows) * px_per_row
    img = Image.new("RGB", (300, h + 200), (120, 110, 100))
    d = ImageDraw.Draw(img)
    y = 100 + h
    for colour, n in rows:                                   # bottom to top
        rgb = tuple(int(pal[colour].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        d.rectangle((100, y - n * px_per_row, 200, y - 1), fill=rgb)
        y -= n * px_per_row
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue(), [110 / 300, 100 / (h + 200), 190 / 300, (100 + h) / (h + 200)]


class _Wall:
    name = "test_double wall pointer"

    def __init__(self, box):
        self.box = box

    def read(self, prompt, images, *, system, max_tokens):
        assert "Task: wall_column" in prompt
        return {"answered": True, "reading": {"wall_box": self.box}}


def test_6_stripe_layout_is_measured_against_the_cir():
    from brambleloop.products import launch0
    from brambleloop.visual import owner_frames as OF

    cir = launch0.cir_for("basket_small")
    # the CIR's own wall: cream 4, wine 2, cream 1, wine 2, cream 3 (rounds 11-22)
    good, box = _strip([("cream", 4), ("wine", 2), ("cream", 1), ("wine", 2), ("cream", 3)])
    v = OF.stripe_layout(_Wall(box), good, cir)
    assert v["status"] == "PASS", v
    # the owner frames' wall: two thin stripes far apart (measured on 5fc4ac77)
    wide, box = _strip([("cream", 3), ("wine", 1), ("cream", 4), ("wine", 1), ("cream", 3)])
    v = OF.stripe_layout(_Wall(box), wide, cir)
    assert v["status"] == "FAIL" and v["code"] == "WRONG_COLOUR_LAYOUT", v
    # one stripe where the CIR has two
    one, box = _strip([("cream", 5), ("wine", 2), ("cream", 5)])
    v = OF.stripe_layout(_Wall(box), one, cir)
    assert v["status"] == "FAIL" and v["stripes_seen"] == 1 and v["stripes_expected"] == 2, v
    # nothing pointed: UNMEASURED, never PASS
    assert OF.stripe_layout(None, good, cir)["status"] == "UNKNOWN"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e)[:3000])
    sys.exit(1 if fails else 0)
