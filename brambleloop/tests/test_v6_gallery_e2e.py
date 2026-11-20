"""V6: one end-to-end gallery run through the real image-production handlers, stub judges.

Main decision I-V6-ACCEPTANCE: one end-to-end run through real handlers with stub judges,
every machine gate green, the remaining owner gates named (F-852, F-853, OA-PAID-KEYS); no
certified-gallery claim, nothing handed to listing.package. On V1 (Main 6705476730 (a)) the
run stops at `owner_card` on one named gate, V1-SCENE-END-BANDS: V1 never promotes an anchor's
end-band measurement into a scene frame, so Cloudline's in-scene frames stay UNKNOWN on craft.

What is real here and what is a test double:

* **Real:** `IP.trigger`, the durable `JobQueue` drained by a worker loop (`test_w4_ownerimg
  .drain`), every `image_production` stage handler, `candidate_gates.evaluate`, the release
  binding, the quality floor, the outfit registry, `readiness`, `campaign_consistency`,
  `naturalism`, the publication verdict (F-852 / F-853), `approve`, and the FLUX 3 generator
  (`creative.flux3_generator.Flux3Generator`) on its `StubRenderer`, which builds every
  request, references in order, exactly as production would, with no network and no spend.
* **Real deterministic verifiers:** the product anchor is judged by `visual.fidelity
  .verify_anchor` (through `candidate_gates.RealJudges.product_truth`) on a synthetic flat lay
  of the certified CIR (`test_w4_fidelity.flat_lay`); every Laura frame by `visual.fidelity
  .verify_lifestyle` (anchor PASS, region palette, blind anchor consistency compared in code
  by `vision_judges.compare_items`); `visual.room_references.same_room`; `visual.scale.verify`;
  `visual.vessel.verify` on the basket's own fixtures.
* **Test doubles:** the vision-judge transport (`StubVision`: answers each blind task with a
  fixed reading consistent with the CIR, as a vision model would if it saw the product), the
  identity / anatomy / realism / body / outfit judges (`test_w4_ownerimg.StubJudges`), and the
  image bytes: the StubRenderer writes a 1/16-size placeholder, below the 2000 px listing
  floor, so the generator double returns a 2048 px synthetic flat lay of the CIR instead. The
  request the real generator built is kept beside it and asserted on.

Nothing here is a certified gallery, and nothing reaches listing.package, store.publish or Etsy.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_v6_gallery_e2e.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  per-process temp sandbox, removed at exit
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_ownerimg as O  # noqa: E402  (artifact dir, certified scratch DB, drain, stubs)
import test_w4_fidelity as T  # noqa: E402  (synthetic flat lays of the certified CIR)

from PIL import Image  # noqa: E402

CLOUD = "cloudline-baby-blanket"
VERSION = "1.2.0"
GALLERY_ROLES = ["lifestyle", "size", "colour_context"]       # the generated gallery frames


# ---- the vision-judge transport double ------------------------------------------------------

def _item(exp) -> dict:
    """What a vision model sees in a faithful frame of this CIR, in `item_prompt`'s keys."""
    return {"item_visible": "yes", "craft": exp.craft,
            "border_or_edging_visible": "yes" if exp.edging_declared else "no",
            "plain_end_bands_visible": "yes" if any(p.bands for p in exp.pieces) else "no",
            "raised_cables_visible": "no",
            "distinct_yarn_colours": len(exp.palette_hex)}


class StubVision:
    """The `image_vision` judge transport, doubled: one fixed blind answer per task.

    It only answers the questions the real transport is asked (`vision_judges.ask` prefixes
    each with `Task: <name>`); every comparison and measurement stays in code."""

    name = "stub-vision"

    def __init__(self, cir, *, same_room="yes", scale_reading=None):
        from brambleloop.visual import fidelity as F

        self.exp = F.expectation(cir)
        self.same_room = same_room
        self.scale_reading = scale_reading
        self.tasks: list[str] = []

    def read(self, prompt, images, **kw):
        task = prompt.split("\n", 1)[0][len("Task: "):] if prompt.startswith("Task: ") else ""
        self.tasks.append(task or "craft_texture")
        if task == "item_description":
            return {"answered": True, "reading": {"image_1": _item(self.exp),
                                                  "image_2": _item(self.exp)}}
        if task == "product_region":
            return {"answered": True, "reading": {"item_visible": "yes",
                                                  "patches": [[0.36, 0.36, 0.64, 0.64]]}}
        if task == "same_room":
            return {"answered": True, "reading": {"same_room": self.same_room,
                                                  "differences": ""}}
        if task == "product_scale":
            return {"answered": self.scale_reading is not None, "reading": self.scale_reading,
                    "why": "no scale reading configured"}
        # visual.fidelity.craft_texture asks without a task prefix. On V1 the Cloudline
        # flat lay's declared end bands pass only when the reading places the edging at the
        # ends with every edge in view (V1's PASSING_BANDS_JUDGE describes that image).
        return T.PASSING_BANDS_JUDGE.read(prompt, images, **kw)


# ---- the judges: real Product Truth paths, stub person judges -------------------------------

class V6Judges(O.StubJudges):
    """`test_w4_ownerimg.StubJudges` for identity, anatomy, realism, body and outfit; Product
    Truth through the real fidelity verifier on the vision double.

    * the product anchor: `candidate_gates.RealJudges.product_truth` unchanged (structural
      floor + `fidelity.verify_anchor`);
    * a gallery frame: `candidate_gates.fidelity_reading` (`fidelity.verify_lifestyle` with
      `vision_judges.blind_consistency` and `locate_product`). Its anchor-consistency check
      records the blind `image_1` / `image_2` reading, and `image_production._item_reading`
      hands `image_2` to `campaign_consistency`. The one part of the real lifestyle Product
      Truth not applied is `compose.lifestyle_evidence`, which needs a photographic reference
      of a made sample (owner gate; see `REMAINING_GATES`)."""

    def __init__(self, db, vision):
        super().__init__()
        from brambleloop.visual import candidate_gates as CG

        self.db, self.vision = db, vision
        self.real = CG.RealJudges(db, vision=vision)
        self.calls: dict[str, list[str]] = {}

    def _seen(self, name, c):
        self.calls.setdefault(name, []).append(c.get("role"))

    def product_truth(self, c, bind):
        from brambleloop.visual import candidate_gates as CG
        from brambleloop.visual import image_production as IP
        from brambleloop.visual.vision_judges import blind_consistency

        self._seen("product_truth", c)
        if c.get("role") == IP.ANCHOR_ROLE:
            return self.real.product_truth(c, bind)
        fid = CG.fidelity_reading(self.db, c, bind, judge=self.vision,
                                  consistency=blind_consistency,
                                  locate=self.real.adapters().product_region)
        return CG._c(fid["status"], f"fidelity {fid['status']} (lifestyle_evidence not "
                                    f"applied: stub)", codes=list(fid.get("codes") or []),
                     fidelity=fid)

    def identity(self, c):
        self._seen("identity", c)
        return super().identity(c)


# ---- the generator: the real FLUX 3 request builder, synthetic listing-size bytes -----------

class V6Generator:
    """`Flux3Generator` on its `StubRenderer` builds and "sends" every request (references in
    order, the approved room included); the bytes handed back are a 2048 px synthetic flat lay
    of the certified CIR, since the StubRenderer's placeholder is below the listing floor.

    Not paid, as the real generator on a StubRenderer is not (`flux3_generator`)."""

    paid = False
    max_cost_cad_per_call = 0.0

    def __init__(self, db, cir):
        from brambleloop.creative import flux3_generator as FG
        from brambleloop.creative import image_stages as S

        self.stub = S.StubRenderer()
        self.real = FG.Flux3Generator(db, renderer=self.stub,
                                      work_root=tempfile.mkdtemp(prefix="v6-gen-"))
        assert self.real.paid is False
        self.name = "v6-" + self.real.name
        self.accepts_staged_method = self.real.accepts_staged_method
        self.accepts_outfit_reference = self.real.accepts_outfit_reference
        self.cir = cir
        self.requests: list[dict] = []
        self.n = 0

    # the orchestrator sets this per generation; the real generator reads its own run's anchor
    @property
    def current_run_key(self):
        return self.real.current_run_key

    @current_run_key.setter
    def current_run_key(self, v):
        self.real.current_run_key = v

    def prepare_references(self, **kw):
        return self.real.prepare_references(**kw)

    def generate(self, **kw):
        from brambleloop.creative import flux3_generator as FG

        before = len(self.stub.calls)
        out = self.real.generate(**kw)
        sent = self.stub.calls[before:]
        assert len(sent) == 1, sent
        self.requests.append({"role": kw["role"], "stage": kw["stage"],
                              "refs": [_sha_of(p) for p in sent[0]["refs"]],
                              "prompt": sent[0]["prompt"]})
        self.n += 1
        if kw["role"] == FG.IDENTITY_ANCHOR_ROLE:
            data = O.png(1024, 1024)            # an intermediate reference, never a frame
        else:
            data = T.flat_lay(self.cir, rotate=[0.0, 2.0, -3.0, 4.0, -1.5][self.n % 5],
                              fill=[0.72, 0.68, 0.75, 0.70, 0.66][self.n % 5])
        return {"data": data, "provider": "stub", "model": "stub-1", "prompt": out["prompt"],
                "cost_cad": 0.0, "latency_s": 0.01}


def _sha_of(path) -> str:
    """A reference's identity: its bytes' hash while the file exists (stage work files are
    named by their own hash and removed after the call), as test_v4_scene_references reads."""
    f = Path(path)
    return hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else f.stem


# ---- an owner-approved room, as a temporary manifest (test fixture) -------------------------

def _room_manifest(room: str):
    d = Path(tempfile.mkdtemp(prefix="v6-rooms-"))
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (180, 170, 150)).save(buf, "PNG")
    data = buf.getvalue()
    (d / f"{room}.png").write_bytes(data)
    entry = {"room": room, "file": f"{room}.png", "sha256": hashlib.sha256(data).hexdigest(),
             "provenance": "test fixture (not an owner-approved image)",
             "decision_id": "D-TEST-V6"}
    (d / "MANIFEST.json").write_text(json.dumps({"version": 1, "rooms": [entry]}))
    return d / "MANIFEST.json", entry, data


# ---- the run, once ----------------------------------------------------------------------------

_RUN: dict = {}


def _run() -> dict:
    """Trigger and drain one gallery run, with the room manifest swapped in for its duration."""
    if _RUN:
        return _RUN
    from brambleloop.visual import image_production as IP
    from brambleloop.visual import laura_home as H
    from brambleloop.visual import room_references as RR

    db = O.make_db()
    cir = T._cir(CLOUD)
    room = H.scene_for(cir.slug)["room"]
    manifest, entry, room_bytes = _room_manifest(room)
    real_manifest = RR.MANIFEST
    RR.MANIFEST = manifest
    try:
        vision = StubVision(cir)
        judges = V6Judges(db, vision)
        gen = V6Generator(db, cir)
        follow, _ = O.drain(db, generator=gen, judges=judges)
        first = IP.trigger(follow, slug=CLOUD, version=VERSION, release=O.RELEASE)
        _, ran = O.drain(db, generator=gen, judges=judges)
    finally:
        RR.MANIFEST = real_manifest
    key = IP.run_key(CLOUD, VERSION, O.RELEASE)
    _RUN.update(db=db, cir=cir, room=room, entry=entry, room_bytes=room_bytes, vision=vision,
                judges=judges, gen=gen, first=first, ran=ran, key=key, run=IP.get_run(db, key))
    return _RUN


def _frames(R) -> dict:
    from brambleloop.visual import image_production as IP

    return {r: IP._best(R["db"], listing=CLOUD, role=r, run=R["key"]) for r in GALLERY_ROLES}


def _bytes(R, sha) -> bytes:
    from brambleloop.core.artifacts import ArtifactStore

    return ArtifactStore().get(sha, db=R["db"])


# ---- 6. the run reaches the owner card, through the real handlers -----------------------------

IN_SCENE = ("lifestyle", "size", "colour_context")
END_BAND_WHY = "visible edge treatment cannot be distinguished from declared bands or components"


def test_6_the_run_reaches_the_owner_card_and_stops_only_on_scene_end_bands():
    """Main 6705476730 (a): on V1 the run reaches `owner_card` and stops there, and the one
    reason is V1-SCENE-END-BANDS: each in-scene frame's Product Truth is UNKNOWN, nothing else."""
    from brambleloop.visual import image_production as IP

    R = _run()
    run = R["run"]
    assert R["first"]["enqueued"] and R["ran"] >= 10, R["ran"]
    assert run["stage"] == "owner_card" and run["state"] == "blocked", run
    want = "; ".join(f"{r}: UNKNOWN (failed [], unknown ['product_truth'])" for r in IN_SCENE)
    assert run["blocked_reason"] == want, run["blocked_reason"]
    # stage A (identity anchor) ran, because the real generator carries the staged method
    assert "identity_anchor" in run["stages"] and "verification" in run["stages"]
    roles = [r["role"] for r in R["gen"].requests]
    assert roles[0] == IP.ANCHOR_ROLE and IP.IDENTITY_ANCHOR_ROLE in roles
    assert sorted(set(roles) - {IP.ANCHOR_ROLE, IP.IDENTITY_ANCHOR_ROLE}) == sorted(
        GALLERY_ROLES), roles
    card = run["card"]
    by_role = {r["role"]: r for r in card["roles"]}
    assert [r["role"] for r in card["roles"]] == ["hero", "lifestyle", "detail", "size",
                                                  "colour_context", "materials",
                                                  "whats_included"]
    for r in GALLERY_ROLES:
        assert by_role[r]["source"] == "generated", by_role[r]
        assert by_role[r]["candidate"]["technical_status"] == "UNKNOWN", by_role[r]
        assert by_role[r]["candidate"]["publishable"] is False        # F-852: never claimed
    assert card["set_check"]["ok"] is True, card["set_check"]
    assert card["owner_approval_is_not_technical_verification"]
    assert card["spent_cad"] == 0.0 and run["spent_cad"] == 0.0


def test_6_every_other_machine_gate_is_green_and_unknown_stays_unknown():
    from brambleloop.visual import fidelity as F
    from brambleloop.visual import image_production as IP

    R = _run()
    anchor = IP._best(R["db"], listing=CLOUD, role=IP.ANCHOR_ROLE, run=R["key"])
    ia = IP._best(R["db"], listing=CLOUD, role=IP.IDENTITY_ANCHOR_ROLE, run=R["key"])
    assert anchor["technical_status"] == "PASS" and anchor["unknown"] == [], anchor
    assert ia["technical_status"] == "PASS" and ia["unknown"] == [], ia
    exp = F.expectation(R["cir"])
    frames = _frames(R)
    assert frames and set(frames) == set(GALLERY_ROLES), sorted(frames)
    for role, b in frames.items():
        assert b["technical_status"] == "UNKNOWN", (role, b)
        assert b["unknown"] == ["product_truth"] and b["failed"] == {}, (role, b)
        fid = b["fidelity"]
        assert fid["status"] == "UNKNOWN" and fid["unknown"] == ["craft_texture"], fid
        assert fid["failed"] == [] and fid["codes"] == [], fid
        other = [c for c in fid["checks"] if c["check"] != "craft_texture"]
        assert other and all(c["status"] == "PASS" for c in other), (role, other)
        craft = next(c for c in fid["checks"] if c["check"] == "craft_texture")
        assert craft["status"] == "UNKNOWN" and craft["why"] == END_BAND_WHY, craft
        # The judge saw edging at the ends only, every edge in view. Only V1's rule (an
        # anchor's band measurement is never promoted into a scene frame) keeps it UNKNOWN:
        # the same reading with the bands verified would pass. That is the named gate.
        r = craft["reading"]
        assert r["edge_placement"] == "ends_only" and r["all_edges_visible"] == "true", r
        assert F.compare_craft(r, exp, end_bands_verified=False)["status"] == "UNKNOWN"
        assert F.compare_craft(r, exp, end_bands_verified=True)["status"] == "PASS"
    card = IP.gallery_card(R["db"], R["key"])
    assert card["decisions"]["technical_certification"]["state"] == "UNKNOWN"
    assert card["decisions"]["technical_certification"]["campaign_consistency"][
        "status"] == "PASS"
    # ... and publication is still not available: this is no certified gallery.
    assert card["decisions"]["publication_authorization"]["state"] == "not_available"


# ---- 1. product fidelity -------------------------------------------------------------------

def test_1_the_product_anchor_passes_the_deterministic_fidelity_verifier():
    from brambleloop.visual import image_production as IP

    R = _run()
    anchor = IP._best(R["db"], listing=CLOUD, role=IP.ANCHOR_ROLE, run=R["key"])
    fid = anchor["fidelity"]
    assert fid["status"] == "PASS" and fid["failed"] == [] and fid["unknown"] == [], fid
    # the run passed the fidelity gate on this anchor's stored verdict, then went on
    stages = R["run"]["stages"]
    assert stages.index("fidelity_gate") < stages.index("load_laura_references"), stages
    gate = IP._stage_data(R["db"], R["key"])["fidelity_gate"]["evidence"]
    assert gate["sha256"] == anchor["sha256"] and gate["technical_status"] == "PASS", gate
    # The verdict is the verifier's, measured on the stored bytes: re-running it agrees.
    from brambleloop.visual import fidelity as F

    again = F.verify_anchor(_bytes(R, anchor["sha256"]), R["cir"], judge=R["vision"])
    assert again["status"] == "PASS" and again["kind"] == "anchor"
    measured = {c["check"]: c["status"] for c in again["checks"]}
    assert {"isolation", "piece_count", "panel:palette", "panel:colour_layout",
            "panel:repeat_count", "panel:edges", "craft_texture"} <= set(measured), measured
    assert set(measured.values()) == {"PASS"}, measured
    # ... and it is not a rubber stamp: a planted defect on the same CIR FAILs.
    bad = F.verify_anchor(T.flat_lay(R["cir"], piece_edit=T.fewer_repeats(10, 11)), R["cir"],
                          judge=R["vision"])
    assert bad["status"] == "FAIL" and "WRONG_REPEAT_COUNT" in bad["codes"], bad["codes"]


def test_1_a_vessel_is_verified_from_top_and_side_on_its_own_fixtures():
    """Gap: the orchestrated run produces one product image (no `side_data`), and Cloudline
    is not a vessel, so the V2 top+side path is shown on the basket's own fixtures."""
    import test_v2_vessel_fidelity as VF
    from brambleloop.visual import fidelity as F
    from brambleloop.visual import vessel as V

    assert V.is_vessel(VF.CIR) and not V.is_vessel(_run()["cir"])
    good = F.verify_anchor(VF.top_view(), VF.CIR, side=VF.side_view(), judge=T.PASSING_JUDGE)
    assert good["status"] == "PASS" and good["kind"] == "vessel_anchor", [
        (c["check"], c["status"]) for c in good["checks"]]
    alone = F.verify_anchor(VF.top_view(), VF.CIR)
    assert alone["status"] == "UNKNOWN" and [c["check"] for c in alone["checks"]] == [
        "vessel_views"]
    bad = F.verify_anchor(VF.top_view(8), VF.CIR, side=VF.side_view(), judge=T.PASSING_JUDGE)
    assert bad["status"] == "FAIL" and "WRONG_REPEAT_COUNT" in bad["codes"]


# ---- 2. identity gating ----------------------------------------------------------------------

def test_2_every_laura_frame_is_identity_judged_and_gated():
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.image_records import ImageCandidate

    R = _run()
    judged = R["judges"].calls.get("identity") or []
    assert set(GALLERY_ROLES) <= set(judged) and IP.IDENTITY_ANCHOR_ROLE in judged, judged
    frames = _frames(R)
    assert frames and set(frames) == set(GALLERY_ROLES), sorted(frames)
    with R["db"].session() as s:
        for role, b in frames.items():
            row = s.get(ImageCandidate, b["candidate_id"])
            assert row.laura_present and row.outfit_id == R["run"]["outfit_id"]
            for k in ("identity", "body_proportions", "outfit", "outfit_consistency",
                      "outfit_distinctness", "anatomy", "realism"):
                assert row.checks[k]["status"] == "PASS", (role, k, row.checks[k])
            # the Laura publication gate is separate: these bytes are not approved for it
            assert any("Laura publication gate" in x for x in
                       row.checks["_publication"]["blockers"]), role
    # every Laura request led with the canonical three, unchanged
    from brambleloop.visual import canonical

    shas = list(canonical.CURRENT_REFERENCE_HASHES.values())
    for req in R["gen"].requests:
        if req["role"] != IP.ANCHOR_ROLE:
            assert req["refs"][:3] == shas, (req["role"], req["refs"][:3])
    assert canonical.verify()["ok"]
    # A failing identity reading still blocks the frame (the gate is live, not bypassed).
    from brambleloop.visual import candidate_gates as CG

    class Drift(V6Judges):
        def identity(self, c):
            return {"status": "FAIL", "why": "stub drift"}

    lif = _frames(R)["lifestyle"]
    v = CG.evaluate(R["db"], O.cand(data=_bytes(R, lif["sha256"]), role="lifestyle",
                                    release=O.RELEASE, laura_present=True,
                                    outfit_id=R["run"]["outfit_id"]),
                    judges=Drift(R["db"], R["vision"]), record_outfit_use=False)
    assert v["checks"]["identity"]["status"] == "FAIL" and v["technical_status"] == "FAIL"


# ---- 3. consistent rooms -----------------------------------------------------------------------

def test_3_every_in_room_request_carries_the_approved_room_and_reads_same_room():
    from brambleloop.visual import image_production as IP
    from brambleloop.visual import room_references as RR

    R = _run()
    sha = R["entry"]["sha256"]
    in_room = [q for q in R["gen"].requests if q["role"] in GALLERY_ROLES]
    assert sorted(q["role"] for q in in_room) == sorted(GALLERY_ROLES), in_room
    for q in in_room:
        assert sha in q["refs"], (q["role"], q["refs"])
        assert q["refs"].index(sha) >= 3            # after the canonical three, never instead
    # the product-only flat lay and the identity anchor are not in a room
    for q in R["gen"].requests:
        if q["role"] in (IP.ANCHOR_ROLE, IP.IDENTITY_ANCHOR_ROLE):
            assert sha not in q["refs"], q["role"]
    # the committed manifest is untouched and still ships empty
    assert json.loads(RR.MANIFEST.read_text())["rooms"] == []
    # the blind same-room reading of each stored frame against the room: PASS
    for role, b in _frames(R).items():
        v = RR.same_room(R["vision"], R["room_bytes"], _bytes(R, b["sha256"]), room=R["room"])
        assert v["status"] == "PASS" and v["check"] == RR.CHECK, (role, v)
    # with no approved room, it is UNKNOWN, never PASS
    assert RR.same_room(R["vision"], None, b"x", room=R["room"])["status"] == "UNKNOWN"


# ---- 4. scale ------------------------------------------------------------------------------------

def test_4_scale_verify_passes_on_a_gallery_frame():
    from brambleloop.visual import scale

    R = _run()
    expected = scale.expected_cm(R["cir"])
    assert expected and expected > 50, expected
    # The judge only points: a pillow (66 cm) box and a product box. Code measures the ratio.
    side = 0.30 * expected / scale.ANCHORS["pillow"]
    reading = {"anchor": "pillow", "anchor_box": [0.05, 0.05, 0.35, 0.25],
               "product_box": [0.40, 0.10, 0.40 + side, 0.10 + side * 0.8]}
    frame = _bytes(R, _frames(R)["size"]["sha256"])
    v = scale.verify(StubVision(R["cir"], scale_reading=reading), frame, R["cir"])
    assert v["status"] == "PASS" and v["check"] == scale.CHECK, v
    assert abs(v["implied_cm"] - expected) / expected < 0.05, v
    # a hamper-sized blanket is caught; no reading is UNKNOWN
    big = {**reading, "product_box": [0.40, 0.05, 0.99, 0.99]}
    wrong = scale.verify(StubVision(R["cir"], scale_reading=big), frame, R["cir"])
    assert wrong["status"] == "FAIL" and wrong["code"] == scale.CHECK, wrong
    assert scale.verify(StubVision(R["cir"]), frame, R["cir"])["status"] == "UNKNOWN"


# ---- 5. cross-frame consistency ------------------------------------------------------------------

def test_5_campaign_consistency_passes_on_the_judges_item_readings():
    from brambleloop.visual import candidate_gates as CG

    R = _run()
    frames = _frames(R)
    assert frames and set(frames) == set(GALLERY_ROLES), sorted(frames)
    for role, b in frames.items():
        assert b["item_reading"] == _item(R["vision"].exp), (role, b["item_reading"])
    cc = R["run"]["card"]["campaign_consistency"]
    assert cc["status"] == "PASS" and "blocker" not in cc, cc
    assert cc["pairwise"]["compared"] == 3 and cc["pairwise"]["unjudged"] == 0, cc
    assert not any(b.startswith(CG.UNJUDGED_BLOCKER)
                   for b in R["run"]["card"]["publication_blockers"])
    # the comparison is live: a frame whose reading disagrees fails the gallery
    rows = list(frames.values())
    odd = {**rows[1], "item_reading": {**rows[1]["item_reading"], "distinct_yarn_colours": 3}}
    assert CG.campaign_consistency([rows[0], odd, rows[2]])["status"] == "FAIL"


# ---- 7. the remaining gates, named --------------------------------------------------------------

# The gates this run cannot clear, each with where it actually stands. `card` means it is a
# publication blocker on the owner card itself; `production` means it is what the production
# judges / generator / manifest read instead of the stub, and is not (yet) a card blocker.
REMAINING_GATES = {
    "F-852": ("card", "generated product imagery exports only through the verified-exception "
                      "route (D-W4-F852-AMEND); approve() refuses on it"),
    "F-853": ("card", "certified-pixel compositing is mandatory for SCALE and COLOUR_CONTEXT, "
                      "so the generated size and colour_context frames are refused"),
    "OA-PAID-KEYS": ("production", "image_vision and image_generation are closed: the "
                                   "production judges read UNKNOWN and the default FLUX 3 "
                                   "generator is paid and refused"),
    "V3": ("production", "no qualified identity embedder (identity_gate.QUALIFIED_EMBEDDERS "
                         "is empty): the production identity reading is UNKNOWN"),
    "OA-ROOM-IMAGES": ("production", "the committed room manifest is empty: no room reference "
                                     "is sent and same_room reads UNKNOWN"),
    "ETSY-POLICY": ("card", "the Etsy listing-image policy reading is UNKNOWN (VISGATE V1)"),
    "LAURA-PUBLICATION": ("card", "Laura's generated bytes are not publication_approved"),
    "LIFESTYLE-EVIDENCE": ("production", "compose.lifestyle_evidence needs a photographic "
                                         "reference of a made sample; from the pattern-derived "
                                         "references it FAILs"),
    "V1-SCENE-END-BANDS": ("run", "V1 never promotes an anchor's end-band measurement into a "
                                  "scene frame: every in-scene frame of an end-band design "
                                  "reads craft_texture UNKNOWN, so the run stops at owner_card. "
                                  "Lifted by a deterministic in-scene band reading (Codex "
                                  "follow-up, Main 6705476730 (c))"),
}


def test_7_the_remaining_owner_and_provider_gates_are_the_actual_blockers():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import gallery
    from brambleloop.visual import identity_gate
    from brambleloop.visual import image_production as IP
    from brambleloop.visual import room_references as RR

    R = _run()
    db = R["db"]
    blockers = R["run"]["card"]["publication_blockers"]
    joined = "\n".join(blockers)
    seen = {}
    # F-852 and F-853, on the card
    seen["F-852"] = [b for b in blockers if b.startswith("F-852")]
    seen["F-853"] = [b for b in blockers if "F-853: certified pixels are feasible for" in b]
    assert seen["F-852"], blockers
    assert {"SCALE", "COLOUR_CONTEXT"} <= {b.split("feasible for ")[1].split(" ")[0]
                                           for b in seen["F-853"]}, seen["F-853"]
    # One F-852 line is the generator double's, not a remaining gate: the double returns its
    # own synthetic bytes, so it attaches no provider receipt (the real receipt describes the
    # StubRenderer placeholder, not these bytes). A real FLUX 3 call records one.
    assert any(b.endswith("provenance incomplete: ['receipt']") for b in seen["F-852"])
    seen["ETSY-POLICY"] = [b for b in blockers if b == CG.ETSY_POLICY_UNKNOWN]
    seen["LAURA-PUBLICATION"] = [b for b in blockers if b.startswith("Laura publication gate")]
    assert seen["ETSY-POLICY"] and seen["LAURA-PUBLICATION"], joined
    # V1-SCENE-END-BANDS on the card: Product Truth UNKNOWN is what F-852 and the DATA_TRUTH
    # gate (worst(binding, product_truth)) report; it is the run's stop reason.
    derived = ("F-852 (D-W4-F852-AMEND) verified exception refused: product_truth is UNKNOWN",
               "F-852 (D-W4-F852-AMEND) verified exception refused: structural_fidelity is "
               "UNKNOWN", "never ran: DATA_TRUTH")
    seen["V1-SCENE-END-BANDS"] = [b for b in blockers if b.startswith(derived)]
    assert len(seen["V1-SCENE-END-BANDS"]) == 3, blockers
    assert R["run"]["stage"] == "owner_card" and R["run"]["state"] == "blocked"
    # The card carries no other kind of blocker: everything else on it is one of these.
    assert all(b.startswith(("F-852", "Laura publication gate", "never ran: DATA_TRUTH"))
               or b == CG.ETSY_POLICY_UNKNOWN for b in blockers), blockers
    # OA-PAID-KEYS: the real vision and generation gates are closed in this database.
    gates = gallery.gates_now(db, keys=("image_generation", "image_vision"))
    assert not gates.get("image_generation") and not gates.get("image_vision"), gates
    assert IP.resolve_generator(db).paid is True
    lif = _frames(R)["lifestyle"]
    c = O.cand(data=_bytes(R, lif["sha256"]), role="lifestyle", release=O.RELEASE,
               laura_present=True, outfit_id=R["run"]["outfit_id"])
    prod = CG.RealJudges(db)
    ident = prod.identity({**c, "sha256": lif["sha256"]})
    assert ident["status"] == "UNKNOWN" and "image_vision" in ident["why"], ident
    seen["OA-PAID-KEYS"] = [ident["why"]]
    # V3: even with vision funded, no qualified embedder exists for the biometric floor.
    assert identity_gate.QUALIFIED_EMBEDDERS == {}
    seen["V3"] = ["identity_gate.QUALIFIED_EMBEDDERS is empty"]
    # OA-ROOM-IMAGES: none committed; no room reference is sent, same_room is UNKNOWN.
    assert RR.approved(R["room"]) is None and "no approved room" in RR.refusal(R["room"])
    assert RR.scene_supplement(R["room"]) == []
    seen["OA-ROOM-IMAGES"] = [RR.refusal(R["room"])]
    # LIFESTYLE-EVIDENCE: the real lifestyle Product Truth on the stored frame's references.
    le = CG.lifestyle_reading({**c, "references": [{"kind": "pattern_derived"}]}, {})
    assert le["status"] == "FAIL", le
    seen["LIFESTYLE-EVIDENCE"] = [le["status"]]
    assert set(seen) == set(REMAINING_GATES) and all(seen.values()), seen
    for name, (where, _why) in REMAINING_GATES.items():
        assert where in ("card", "production", "run"), name
    # The owner cannot approve a run that stopped on an unverified gate.
    dec = IP.approve(db, R["key"], decided_by="owner:test")
    assert dec["approved"] is False and "not ready_for_owner_review" in dec["why"], dec
    assert IP.get_run(db, R["key"])["state"] == "blocked"
    card = IP.gallery_card(db, R["key"])
    assert card["decisions"]["publication_authorization"]["state"] == "not_available"
    assert set(card["decisions"]["publication_authorization"]["blockers"]) == set(blockers)


# ---- 8. nothing reaches listing.package, store.publish or Etsy ------------------------------

def test_8_nothing_is_enqueued_for_listing_package_publish_or_etsy():
    from sqlalchemy import select

    from brambleloop.core.models import Job

    R = _run()
    # after approve() was refused (test 7, or here if run alone)
    from brambleloop.visual import image_production as IP

    IP.approve(R["db"], R["key"], decided_by="owner:test")
    with R["db"].session() as s:
        jobs = [(j.agent, j.job_type) for j in s.scalars(select(Job))]
    types = {t for _a, t in jobs}
    assert types <= {"assets.build", IP.JOB_TYPE}, types
    for t in types:
        assert not t.startswith(("listing.", "store.", "etsy")), t
    from brambleloop.core.models import AuditLog, ListingAsset

    with R["db"].session() as s:
        assert list(s.scalars(select(ListingAsset))) == []
        actions = [a.action for a in s.scalars(select(AuditLog))]
    assert not any(x.startswith(("listing.", "store.", "etsy", "publish")) for x in actions), \
        actions
    assert IP.get_run(R["db"], R["key"])["state"] != "approved_for_publication"


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and fn.__module__ == __name__:
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except BaseException as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
