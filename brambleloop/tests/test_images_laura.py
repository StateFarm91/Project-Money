"""ENG-IMAGES-LAURA: the owner's two-step method, step 2.

The owner, verbatim: "Then when it made the product, I sent the product with Laura's identity
images." Every Laura frame is conditioned on exactly the product frame this gallery already
ACCEPTED through the fidelity gate (by its stored sha256) and Laura's canonical identity images
(laura-r2-a42aeac7), with the listing's assigned outfit. Offline: stub provider, stub judges,
no network, no spend.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_images_laura.py
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import base64
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_ownerimg as O  # noqa: E402  (artifact dir, certified scratch DB, drain)

CLOUD = "cloudline-baby-blanket"


def _canonical_bytes():
    """Laura's canonical set, read from the committed files of laura-r2-a42aeac7."""
    from brambleloop.visual import canonical, conditioning

    out = []
    for frame in conditioning.FRAME_ORDER:
        data = Path(canonical.reference_file(frame)).read_bytes()
        assert hashlib.sha256(data).hexdigest() == canonical.CURRENT_REFERENCE_HASHES[frame]
        out.append(data)
    return out


class OwnerGen(O.StubGenerator):
    """The stub provider, declaring the owner's method; records what each role was handed."""

    accepts_owner_method = True
    accepts_staged_method = True     # stage A must still be skipped under the owner method
    name = "owner-method-stub"

    def __init__(self, paid=False):
        super().__init__()
        self.handed = []
        self.paid = paid
        self.max_cost_cad_per_call = 0.05 if paid else 0.0

    def generate(self, **kw):
        self.handed.append({"role": kw["role"], "stage": kw["stage"], "outfit": kw["outfit"],
                            "refs": [(r["kind"], r.get("label"), r.get("sha256"), r["data"])
                                     for r in kw["references"]]})
        out = super().generate(**kw)
        return {**out, "cost_cad": self.max_cost_cad_per_call}


def _go(db, gen, judges, **kw):
    from brambleloop.visual import image_production as IP

    follow, _ = O.drain(db, generator=gen, judges=judges)
    IP.trigger(follow, slug=CLOUD, version="1.2.0", release=O.RELEASE)
    O.drain(db, generator=gen, judges=judges, **kw)
    return IP.run_key(CLOUD, "1.2.0", O.RELEASE)


def _sent(h):
    """What a Laura request transmits: everything but the binding-only pattern references."""
    return [(k, lbl, sha) for k, lbl, sha, _d in h["refs"] if k != "pattern_derived"]


def test_lifestyle_request_carries_the_accepted_product_frame_and_canonical_laura_in_order():
    from brambleloop.visual import canonical, conditioning
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.image_records import ImageCandidate

    db = O.make_db()
    gen = OwnerGen()
    key = _go(db, gen, O.StubJudges())
    run = IP.get_run(db, key)
    assert run["state"] == "ready_for_owner_review", run
    anchor = IP._best(db, listing=CLOUD, role=IP.ANCHOR_ROLE, run=key)
    assert anchor["technical_status"] == "PASS"
    want = ([("laura_canonical", None, canonical.CURRENT_REFERENCE_HASHES[f])
             for f in conditioning.FRAME_ORDER]
            + [("prior_candidate", IP.PRODUCT_FRAME_LABEL, anchor["sha256"])])
    laura = [h for h in gen.handed if h["role"] != IP.ANCHOR_ROLE]
    assert [h["role"] for h in laura] == ["lifestyle", "size", "colour_context"], laura
    for h in laura:
        assert _sent(h) == want, (h["role"], _sent(h))              # deterministic order
        assert h["outfit"]["outfit_id"] == run["outfit_id"]          # the assigned outfit
        assert not any(lbl in ("identity_anchor", "edit_base", "outfit_reference")
                       for _k, lbl, _s in _sent(h))
    # stage A is not bought under the owner method
    assert IP.IDENTITY_ANCHOR_ROLE not in [h["role"] for h in gen.handed]
    assert "owner_two_step" in IP._stage_data(db, key)["identity_anchor"]["outputs"]["skipped"]
    # provenance: the reference hashes, in the order sent, on every Laura candidate
    with db.session() as s:
        rows = s.query(ImageCandidate).filter(ImageCandidate.run_key == key,
                                              ImageCandidate.laura_present.is_(True)).all()
        provs = [dict((r.checks or {}).get("_reference_provenance") or {}) for r in rows]
    assert len(provs) == 3 and all(p for p in provs)
    for p in provs:
        assert p["method"] == IP.OWNER_METHOD and p["identity_id"] == "laura-r2-a42aeac7"
        assert [i["sha256"] for i in p["images"]] == [w[2] for w in want]
        assert [i["role"] for i in p["images"]] == ["laura_face", "laura_torso", "laura_body",
                                                    "product_candidate"]
        assert p["accepted_product_frame"]["sha256"] == anchor["sha256"]
        assert p["outfit_id"] == run["outfit_id"] and len(p["input_digest"]) == 64
    # within the documented FLUX 3 maximum
    from brambleloop.gateway import flux_contract

    assert len(want) <= flux_contract.MAX_REFERENCES


def test_laura_references_are_byte_identical_to_the_canonical_set():
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    gen = OwnerGen()
    _go(db, gen, O.StubJudges())
    canon = _canonical_bytes()
    assert gen.handed, "the owner-method run handed nothing to the generator"
    for h in gen.handed:
        if h["role"] == IP.ANCHOR_ROLE:
            assert not any(k == "laura_canonical" for k, *_ in h["refs"])
            continue
        sent = [d for k, _l, _s, d in h["refs"] if k == "laura_canonical"]
        assert sent == canon, h["role"]                         # bytes, not only hashes


def test_nothing_runs_before_a_product_frame_is_accepted():
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    gen = OwnerGen()
    key = _go(db, gen, O.StubJudges(product="FAIL"))
    run = IP.get_run(db, key)
    assert run["state"] == "blocked", run
    assert {h["role"] for h in gen.handed} == {IP.ANCHOR_ROLE}     # only step 1 ran
    assert IP._accepted_product_frame(db, key, CLOUD) is None
    # A run still in flight (step 1 made a frame that FAILed and nothing is accepted yet): a
    # lifestyle or later job delivered anyway (a misroute, a redrive) blocks and spends nothing.
    db = O.make_db()
    gen = OwnerGen()
    key = _go(db, gen, O.StubJudges(product="FAIL"), limit=3)      # up to product_generation
    run = IP.get_run(db, key)
    assert run["state"] != "blocked" and IP._best(
        db, listing=CLOUD, role=IP.ANCHOR_ROLE, run=key)["technical_status"] == "FAIL", run
    before = len(gen.handed)
    for stage in ("lifestyle_generation", "remaining_roles"):
        IP._update(db, key, stage="fidelity_gate", status="product_generation")  # in flight
        IP.run_stage(db, {"slug": CLOUD, "version": "1.2.0", "release": O.RELEASE,
                          "stage": stage}, follow=lambda *a, **k: None, generator=gen,
                     judges=O.StubJudges())
        assert len(gen.handed) == before, stage
        run = IP.get_run(db, key)
        assert run["state"] == "blocked" and "no product frame accepted" in \
            run["blocked_reason"], run


class _CapturingRenderer:
    """StubRenderer that keeps the bytes of every reference at the moment of the call."""

    def __init__(self):
        from brambleloop.creative import image_stages as S

        self.inner = S.StubRenderer()
        self.reference_limit = self.inner.reference_limit
        self.provider_key = "stub"
        self.calls = self.inner.calls
        self.ref_bytes = []

    def __call__(self, prompt, *, reference_urls, **kw):
        self.ref_bytes.append([Path(r).read_bytes() for r in reference_urls])
        return self.inner(prompt, reference_urls=reference_urls, **kw)


def test_the_generator_refuses_a_product_frame_that_is_not_the_accepted_one():
    import test_w4_flux3generator as FG3
    from brambleloop.creative import flux3_generator as FG
    from brambleloop.gateway import images as I

    g, stub = FG3._gen(renderer=_CapturingRenderer())
    refs = FG3._orchestrator_refs(g.prepare_references(slug=FG3.SLUG, version=FG3.VER,
                                                       release=FG3.REL))
    out = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="flat",
                     references=refs, outfit=None, attempt=1)
    sha = hashlib.sha256(out["data"]).hexdigest()
    g.anchor_lookup = lambda s, v, r, **k: {"data": out["data"], "status": "PASS",
                                            "sha256": sha}
    pf = {"kind": "prior_candidate", "label": FG.PRODUCT_FRAME_LABEL, "sha256": sha,
          "data": out["data"]}
    life = g.generate(stage="lifestyle_generation", role="lifestyle", brief="on the sofa",
                      references=refs + FG3._laura_refs() + [pf], outfit=FG3.OUTFIT,
                      attempt=1)
    ev = life["identity_evidence"]
    # ENG-MANUAL-METHOD (manual_method/1) carries step 2 forward: the same four inputs, in
    # the same order (canonical three, then the accepted product frame as the master).
    assert ev["method"] == "manual_method/1"
    assert [r["role"] for r in ev["references"]] == ["laura_face", "laura_torso",
                                                     "laura_body", "product_master"]
    assert ev["input_sha256s"] == [r["sha256"] for r in FG3._laura_refs()] + [sha]
    assert FG3.OUTFIT["description"] in stub.calls[-1]["prompt"]       # the outfit travels
    # The FLUX 3 body actually built from those inputs: `images`, in that order, these bytes.
    import json
    import tempfile

    assert stub.ref_bytes[-1] == _canonical_bytes() + [out["data"]]
    tmp = Path(tempfile.mkdtemp())
    paths = []
    for i, b in enumerate(stub.ref_bytes[-1]):
        (tmp / f"{i}.png").write_bytes(b)
        paths.append(str(tmp / f"{i}.png"))
    url, _h, body = I._request_for(I.BY_KEY["flux-3-image"], "dummy-key",
                                   stub.calls[-1]["prompt"], paths, "2048x2048")

    body = json.loads(body)
    assert url.endswith("/v1/flux-3-image") and "input_image" not in body
    assert [base64.standard_b64decode(b) for b in body["images"]] == \
        _canonical_bytes() + [out["data"]]
    # a product frame that is not the accepted one is refused before any render
    n = len(stub.calls)
    other = dict(pf, data=O.png(), sha256=None)
    other["sha256"] = hashlib.sha256(other["data"]).hexdigest()
    try:
        g.generate(stage="lifestyle_generation", role="lifestyle", brief="on the sofa",
                   references=refs + FG3._laura_refs() + [other], outfit=FG3.OUTFIT,
                   attempt=1)
        raise AssertionError("an unaccepted product frame was used")
    except FG.GeneratorRefused:
        pass
    g.anchor_lookup = lambda s, v, r, **k: {"data": out["data"], "status": "FAIL",
                                            "sha256": sha}
    try:
        g.generate(stage="lifestyle_generation", role="lifestyle", brief="on the sofa",
                   references=refs + FG3._laura_refs() + [pf], outfit=FG3.OUTFIT, attempt=1)
        raise AssertionError("a FAILed product frame was used")
    except FG.GeneratorRefused:
        pass
    assert len(stub.calls) == n


def test_a_redrive_makes_no_repeat_paid_call():
    from brambleloop.queue.durable import DuplicateJob, JobQueue
    from brambleloop.visual import gallery
    from brambleloop.visual import image_production as IP

    real = gallery.gates_now
    gallery.gates_now = lambda db, keys=("image_generation",): {k: True for k in keys}
    try:
        with O.admitted_for_sale():
            db = O.make_db()
            O._admit_for_sale(db)
            gen = OwnerGen(paid=True)
            key = _go(db, gen, O.StubJudges())
            run = IP.get_run(db, key)
            assert run["state"] == "ready_for_owner_review", run
            calls, spent = len(gen.handed), run["spent_cad"]
            assert calls == 4 and spent > 0
            q = JobQueue(db)

            def follow(inputs, k, *, session=None):
                try:
                    return q.enqueue(IP.AGENT, IP.JOB_TYPE, inputs, idempotency_key=k,
                                     session=session)
                except DuplicateJob:
                    if session is not None:
                        raise
                    return None

            # 1. a duplicate delivery of the same stage jobs
            for stage in ("lifestyle_generation", "remaining_roles"):
                IP.run_stage(db, {"slug": CLOUD, "version": "1.2.0", "release": O.RELEASE,
                                  "stage": stage}, follow=lambda *a, **k: None,
                             generator=gen, judges=O.StubJudges())
            assert len(gen.handed) == calls
            # 2. a capability redrive: a new restart epoch, same inputs
            IP._update(db, key, stage="lifestyle_generation",
                       blocked="image_generation gate closed: test")
            out = IP.restart(db, key, follow=follow, by=IP.REDRIVE_BY,
                             reason="image_generation opened after the run blocked on it")
            assert out["restarted"] and out["epoch"] == 1, out
            O.drain(db, generator=gen, judges=O.StubJudges())
            run = IP.get_run(db, key)
            assert run["state"] == "ready_for_owner_review", run
            assert len(gen.handed) == calls, [h["role"] for h in gen.handed[calls:]]
            assert run["spent_cad"] == spent and run["generation_calls"] == calls
    finally:
        gallery.gates_now = real


def test_operation_keys_follow_the_input_hashes():
    from brambleloop.visual import image_production as IP

    pf = {"sha256": "a" * 64, "candidate_id": 1}
    laura = [{"frame": "neutral_portrait", "sha256": "1" * 64},
             {"frame": "torso_fit_reference", "sha256": "2" * 64},
             {"frame": "full_length_standing", "sha256": "3" * 64}]
    p1 = IP.reference_provenance(pf, laura, outfit_id="o1", identity_id="x")
    p2 = IP.reference_provenance(pf, list(reversed(laura)), outfit_id="o1", identity_id="x")
    assert p1 == p2                              # order is FRAME_ORDER, not the input order
    p3 = IP.reference_provenance({**pf, "sha256": "b" * 64}, laura, outfit_id="o1",
                                 identity_id="x")
    p4 = IP.reference_provenance(pf, laura, outfit_id="o2", identity_id="x")
    assert len({p1["input_digest"], p3["input_digest"], p4["input_digest"]}) == 3
    k = lambda p: IP._owner_operation("run", "lifestyle_generation", "lifestyle",  # noqa: E731
                                      p["input_digest"], False)
    assert k(p1) == k(p2) and k(p1) != k(p3)


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and fn.__module__ == __name__:
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except BaseException as e:  # noqa: BLE001 - Refused is a SystemExit
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
