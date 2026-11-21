"""ENG-FAMILIES: a researched concept is routed to the verified engine for its family.

Runs the real handlers -- `radar.concept_intake`, `radar.score`, `cir.draft`, `cir.compile`,
`gate.certify` -- through the worker on a scratch SQLite file. Every research source,
finding, competitor listing and taste judgement here is a TEST FIXTURE; none is an
observation, a customer or a judgement anybody made. No concept here is a catalogue or POOL
concept: each is a research-derived proposal, which is the route under test.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import dataclasses
import inspect
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    BenchmarkListing, Job, JobStatus, PatternVersion, Product,
)
from brambleloop.creative import construction_families as CF  # noqa: E402
from brambleloop.creative import fallback_constructions as FC  # noqa: E402
from brambleloop.creative import homedecor as HD  # noqa: E402
from brambleloop.intel import research  # noqa: E402
from brambleloop.intel.benchmarks import MJS_KEY  # noqa: E402
from brambleloop.products import production_inventory as inv  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.radar.opportunity import POOL  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

TODAY = date.today()
POOL_SLUGS = {s.slug for s in POOL}
CHAIN_AGENT = {"radar.concept_intake": "market_radar", "radar.score": "market_radar",
               "cir.draft": "crochet_engineer"}


# ---- fixtures ---------------------------------------------------------------------------------

# The files a certifying proof may live in (ENG-HOMEDECOR added its own vessel variants).
PROOF_FILES = ("tests/test_eng_families.py", "tests/test_eng_homedecor.py")


def _proof_exists(proof: str) -> bool:
    """`proof` names a test function that exists in one of PROOF_FILES."""
    import ast

    path, _, name = proof.partition("::")
    if path not in PROOF_FILES or not name:
        return False
    tree = ast.parse((ROOT / path).read_text())
    return any(isinstance(n, ast.FunctionDef) and n.name == name for n in tree.body)



def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='engfam_')}/f.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _answered_task(db) -> int:
    t = research.open_question(
        db, question="Is there durable buyer demand for this object in Canada?",
        trigger="test:eng-families", decision_ref="radar.concept_intake:test",
        domain="competitor_positioning", query_terms=["home"],
        evidence_needed="fixture listing census", stop_condition="a fact answers it",
        if_unresolved="record it unresolved")
    tid = t["task"]
    research.add_source(db, tid, source="fixture census", citation="https://example.invalid/c",
                        retrieval="fetched", read_on=TODAY - timedelta(days=5))
    research.add_finding(db, tid, statement="fixture: the object sells steadily year round",
                         claim_class="fact", rests_on=["S1"], confidence="medium")
    research.answer(db, tid, outcome="fixture: durable", confidence="medium",
                    effect={"kind": "constraint_established",
                            "statement": "fixture: demand is durable"},
                    conclusion={"alternatives": [], "constraints": ["fixture constraint"],
                                "unresolved": [], "next_test": {}, "applicability": None})
    return tid


def _benchmarks(db, pod: str) -> None:
    """Fixture benchmark listings so the pre-engineering anti-clone check can measure."""
    with db.session() as s:
        for i, title in enumerate(("Farmhouse Throw Pattern", "Boho Wall Hanging Pattern",
                                   "Rope Bowl Pattern", "Granny Pillow Pattern")):
            s.add(BenchmarkListing(benchmark_key=MJS_KEY, listing_ref=f"fx-{pod}-{i}",
                                   title=title, pod=pod, audit_state="audited", detail={}))


def _proposal(slug: str, title: str, category: str, **concept) -> dict:
    c = {"premise": (f"A {title.lower()} worked in quiet bands of driftwood grey and sea "
                     f"glass for an everyday shelf"),
         "pod": "home_decor", "form": "runner", "construction": "flat_rows",
         "motif": "tide lines", "palette_story": "driftwood grey and sea glass",
         "recipient": "host", "occasion": "housewarming", "feeling": "serene",
         "function": "dresses a dining table for guests"}
    c.update(concept)
    return {"slug": slug, "title": title, "category": category, "price_cad": 7.5,
            "maker_hours": [4.0, 9.0], "design_hours": 8.0,
            "rationale": ("fixture research shows this object sells steadily year round in "
                          "Canada and no profiled shop sells this coastal banded version"),
            "evergreen": True, "concept": c,
            "brief": {"thumbnail_storyboard": f"{title.lower()} on an oak shelf in grey",
                      "silhouette_qualifiers": ["motif_composition"]},
            "evidence": ["F1", "S1"]}


RUNNER = _proposal("tide-line-table-runner", "Tide Line Table Runner", "runner",
                   pod="kitchen_bath")
BASKET = _proposal("saltmarsh-reed-basket", "Saltmarsh Reed Basket", "basket",
                   form="basket", construction="in_the_round",
                   function="holds rolled towels by the bath", motif="saltmarsh stripes")
TAPESTRY = _proposal("checked-tapestry-shelf-basket", "Checked Tapestry Shelf Basket",
                     "basket", form="basket", construction="tapestry",
                     function="holds yarn by the sofa", motif="check band")
CUSHION = _proposal("hollow-fern-cushion-cover", "Hollow Fern Cushion Cover", "pillow",
                    form="pillow", function="fronts a sofa cushion", motif="fern rows")


def _run(db, job_type: str, inputs: dict | None = None) -> dict:
    if inputs is not None:
        JobQueue(db).enqueue(CHAIN_AGENT[job_type], job_type, inputs, priority=0,
                             idempotency_key=f"t:{job_type}:{id(inputs)}")
    with db.session() as s:
        job_id = s.scalar(select(Job.id).where(Job.job_type == job_type,
                                               Job.status == JobStatus.PENDING)
                          .order_by(Job.id).limit(1))
    assert job_id is not None, f"no pending {job_type}"
    assert Worker(db, "engfam", job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job_id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        return dict(row.outputs or {})


def _judged(slugs):
    """Stand in for the vision judge's recorded verdict (image_vision is CLOSED)."""
    from brambleloop.creative import intake as creative_intake

    real = creative_intake.judgement_for
    creative_intake.judgement_for = lambda db, key: (
        {"thumbnail_reads_small": True, "craft_impression": 4.2, "sources": ["fixture"]}
        if key in slugs else real(db, key))
    return lambda: setattr(creative_intake, "judgement_for", real)


def _certify_research_concept(proposal: dict) -> dict:
    """Intake -> score -> draft -> compile -> certify, all real handlers. Returns the outputs
    and the stored release."""
    assert proposal["slug"] not in POOL_SLUGS, "the concept under test is research-derived"
    db = _db()
    _benchmarks(db, proposal["concept"]["pod"])
    tid = _answered_task(db)
    intake.attach_proposal(db, tid, proposal)
    got = _run(db, "radar.concept_intake", {})
    assert got["approved"] == [proposal["slug"]], got
    restore = _judged({proposal["slug"]})
    try:
        scored = _run(db, "radar.score")
        assert scored["promoted"] is True, scored
        drafted = _run(db, "cir.draft")
        assert drafted["drafted"] is True, drafted
        w = Worker(db, "engfam-certify", job_types=["cir.compile", "gate.certify"])
        while w.run_once():
            pass
    finally:
        restore()
    with db.session() as s:
        jobs = {j.job_type: j for j in s.scalars(select(Job).order_by(Job.id))}
        compiled = dict(jobs["cir.compile"].outputs or {})
        cir = jobs["cir.compile"].inputs["cir"]
        certified = dict(jobs["gate.certify"].outputs or {})
        pv = s.scalar(select(PatternVersion).join(Product, Product.id ==
                                                  PatternVersion.product_id)
                      .where(Product.slug == proposal["slug"]))
        cert = dict(pv.certificate or {}) if pv is not None else {}
    return {"db": db, "drafted": drafted, "compiled": compiled, "cir": cir,
            "certified": certified, "certificate": cert}


def _assert_certified_end_to_end(out: dict) -> None:
    assert out["compiled"]["compiled"] is True, out["compiled"]
    assert out["certified"]["granted"] is True, out["certified"]
    cert = out["certificate"]
    assert cert.get("granted") is True and cert.get("release_hash"), cert
    # Twin, independent reverse compile and Product Truth's size check ran and passed.
    for stage in ("compile", "twin", "reverse"):
        assert stage in cert["stages_run"], (stage, cert["stages_run"])
    codes = {f["code"] for f in cert.get("findings") or []}
    assert not {c for c in codes if c.startswith("OBJECT_SIZE")}, codes
    assert not [f for f in cert.get("findings") or [] if f["severity"] == "ERROR"], codes


# ---- verified families: research-derived concepts certify end to end --------------------------


def test_a_research_flat_runner_certifies_end_to_end():
    out = _certify_research_concept(RUNNER)
    assert out["drafted"]["construction"] == FC.FLAT_PANEL
    assert [c["construction"] for c in out["cir"]["components"]] == ["flat_rows"]
    _assert_certified_end_to_end(out)


def test_a_research_basket_routes_to_the_vessel_engine_and_certifies():
    out = _certify_research_concept(BASKET)
    assert out["drafted"]["construction"] == FC.VESSEL
    comp = out["cir"]["components"][0]
    assert comp["construction"] == "joined_rounds", "a basket is worked in the round"
    counts = out["compiled"]["counts"]
    assert counts[0] == 6 and counts[1] > counts[0], "a flat base increases before the wall"
    _assert_certified_end_to_end(out)


def test_a_research_tapestry_basket_routes_to_its_chart_and_certifies():
    out = _certify_research_concept(TAPESTRY)
    assert out["drafted"]["construction"] == FC.TAPESTRY
    def colours(ops):
        for op in ops:
            if "ops" in op:
                yield from colours(op["ops"])
            elif op.get("color"):
                yield op["color"]

    rows = out["cir"]["components"][0]["rows"]
    charted = [r["index"] for r in rows if list(colours(r["ops"]))]
    assert len(charted) >= len(FC.TAPESTRY_CHARTS["check"]), \
        "the chart band paints the contrast colour stitch by stitch, never a plain stripe"
    assert {c for r in rows for c in colours(r["ops"])} == {list(out["cir"]["colors"])[1]}
    _assert_certified_end_to_end(out)


def test_a_research_cushion_is_physical_gated_not_flattened():
    out = _certify_research_concept(CUSHION)
    assert out["drafted"]["construction"] == FC.PANEL_PAIR
    assert [c["name"] for c in out["cir"]["components"]] == ["front", "back"]
    assert out["compiled"]["compiled"] is True
    reasons = out["certified"]["reasons"]
    assert out["certified"]["granted"] is False and reasons, out["certified"]
    assert all("PHYSICAL_TEST_REQUIRED" in r for r in reasons), reasons


# ---- holds: never mislabelled, never flattened ------------------------------------------------


HELD = {
    "tide-cable-table-runner": (
        _proposal("tide-cable-table-runner", "Tide Cable Table Runner", "runner",
                  construction="cable_panel", motif="rope cables", pod="kitchen_bath"),
        "cable"),
    "meadow-hare-amigurumi": (
        _proposal("meadow-hare-amigurumi", "Meadow Hare", "toy", form="toy",
                  construction="amigurumi_shaping", motif="hare"),
        "amigurumi"),
    "simple-drawstring-pouch": (
        _proposal("simple-drawstring-pouch", "Simple Drawstring Pouch", "bag", form="pouch",
                  construction="in_the_round", motif="eyelet band",
                  function="holds small notions"),
        FC.POUCH),
    # Declares tapestry, but the title claims no colourwork: the draft would build a plain
    # striped vessel, so drafting it would mislabel the product.
    "harbour-stripe-reed-basket": (
        _proposal("harbour-stripe-reed-basket", "Harbour Stripe Reed Basket", "basket",
                  form="basket", construction="tapestry", motif="stripes"),
        FC.TAPESTRY),
    # A basket in a category whose template drafts a flat panel.
    "linen-ridge-shelf-basket": (
        _proposal("linen-ridge-shelf-basket", "Linen Ridge Shelf Basket", "placemat",
                  form="basket", construction="in_the_round", motif="ridges"),
        FC.VESSEL),
    # Declared a flat pet mat, but the title names a bed: the draft would build a vessel.
    "hearthside-cat-bed": (
        _proposal("hearthside-cat-bed", "Cosy Cat Bed", "pet", form="flat_panel",
                  motif="hearth bands", function="gives a cat a place by the fire"),
        FC.VESSEL),
    # Declared flat, and the cat-bed vessel engine refuses the title: the hold names the
    # engine that refused it, not the flat panel the concept declared.
    "tabby-hearth-cat-bed": (
        _proposal("tabby-hearth-cat-bed", "Tabby Cat Bed", "pet", form="flat_panel",
                  motif="tabby bands", function="gives a cat a place by the fire"),
        FC.VESSEL),
    # A flat runner the flat engine refuses (one draft is one size): held, not drafted.
    "tide-line-runner-sizes": (
        _proposal("tide-line-runner-sizes", "Tide Line Runner In Three Sizes", "runner",
                  pod="kitchen_bath"),
        FC.FLAT_PANEL),
    # The tapestry engine has no heron chart: held under its family, never drafted plain.
    "heron-tapestry-basket": (
        _proposal("heron-tapestry-basket", "Heron Tapestry Basket", "basket", form="basket",
                  construction="tapestry", motif="herons"),
        FC.TAPESTRY),
}


def test_unsupported_and_mislabelled_families_are_held_by_name_and_shown_in_inventory():
    db = _db()
    tid = _answered_task(db)
    for proposal, _family in HELD.values():
        intake.attach_proposal(db, tid, proposal)
    out = _run(db, "radar.concept_intake", {})
    assert out["approved"] == [], out
    reasons = {r["slug"]: r["reasons"] for r in out["refused"]}
    for slug, (_p, family) in HELD.items():
        held = [r for r in reasons[slug] if r.startswith(CF.HOLD_PREFIX)]
        assert held and CF.hold_family(held[0]) == family, (slug, reasons[slug])
    # Which check held it is named: an engine refusal is not reported as a mislabel.
    assert "engine refuses this title" in " ".join(reasons["heron-tapestry-basket"])
    assert "engine refuses this title" in " ".join(reasons["tide-line-runner-sizes"])
    assert "declares flat rows" in " ".join(reasons["hearthside-cat-bed"])
    with db.session() as s:
        assert not list(s.scalars(select(Job).where(Job.job_type.in_(
            ["radar.score", "cir.draft", "cir.compile"])))), "a held concept is never built"

    items = {it["slug"]: it for it in inv.derive(db)["items"]}
    for slug, (_p, family) in HELD.items():
        it = items[slug]
        assert it["state"] == inv.RESEARCH_CANDIDATE, (slug, it["state"], it["why"])
        kinds = [h for h in it["holds"] if h["kind"] == inv.HOLD_CONSTRUCTION]
        assert kinds and CF.hold_family(kinds[0]["why"]) == family, (slug, it["holds"])
    summary = inv.production_summary(db)
    assert summary["held_by_reason"][inv.HOLD_CONSTRUCTION] == len(HELD), summary


def test_a_construction_refused_at_draft_is_a_named_hold_in_inventory_not_in_development():
    """`cir.draft` refusing a construction records the family it holds, and the inventory
    shows that hold rather than 'CIR drafted; not yet compiled'."""
    slug = "woodland-fox-amigurumi"
    seed = pipeline._seed_for(slug)
    # Run the real handler on a database where the design is established (a rebuild), the
    # route `test_opus2_draft_constructions` uses, to obtain its real refusal outputs.
    src = _db()
    with src.session() as s:
        p = Product(slug=slug, title=seed.title)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={}, certified=True))
    payload = {k: v for k, v in dataclasses.asdict(seed).items() if not isinstance(v, tuple)}
    payload.update(pipeline.concept_geometry(seed))
    audits, emitted = [], []
    ctx = SimpleNamespace(db=src, job=SimpleNamespace(inputs=payload),
                          audit=lambda action, **kw: audits.append((action, kw)),
                          enqueue=lambda *a, **kw: emitted.append(a))
    result = pipeline.handle_cir_draft(ctx)
    assert result["drafted"] is False and not emitted, result
    assert result["hold"].startswith(CF.HOLD_PREFIX), result
    refused = [kw["detail"] for a, kw in audits if a == "cir.draft_refused"]
    assert refused and refused[0]["hold"] == result["hold"]

    # The inventory reads that recorded job.
    db = _db()
    q = JobQueue(db)
    q.enqueue("market_radar", "radar.score", {"slug": slug}, idempotency_key="t:score")
    q.enqueue("crochet_engineer", "cir.draft", {"slug": slug}, idempotency_key="t:draft")
    with db.session() as s:
        for j in s.scalars(select(Job)):
            j.status = JobStatus.DONE
            j.outputs = ({"slug": slug, "promoted": True, "score": 0.7}
                         if j.job_type == "radar.score" else result)
    it = next(i for i in inv.derive(db)["items"] if i["slug"] == slug)
    assert it["state"] == inv.RESEARCH_APPROVED, (it["state"], it["why"])
    assert it["why"].startswith(f"held: {CF.HOLD_PREFIX}"), it["why"]
    assert [h["kind"] for h in it["holds"]] == [inv.HOLD_CONSTRUCTION], it["holds"]


# ---- children's safety stays intact -----------------------------------------------------------


def test_childrens_gates_still_apply_to_a_routed_family_and_baby_items_are_not_reshaped():
    db = _db()
    tid = _answered_task(db)
    # A verified family does not bypass the children's pre-check: a prohibited subject on a
    # basket (verified vessel family) is still refused by it.
    from brambleloop.intel.childrens import prohibited_subject

    banned_words = None
    for words in ("infant sleep positioner", "baby sleep positioner", "crib bumper",
                  "teething necklace", "baby walker"):
        if prohibited_subject(words) is not None:
            banned_words = words
            break
    assert banned_words, "fixture: the children's register names a prohibited subject"
    intake.attach_proposal(db, tid, _proposal(
        "willow-nursery-reed-basket", "Willow Nursery Reed Basket", "basket", form="basket",
        construction="in_the_round", recipient="new_parent", motif="willow bands",
        function=f"holds a {banned_words} beside the cot"))
    # A baby item declared in the round is not reshaped into the vessel engine: the baby
    # category drafts a flat blanket template, so the declaration is held, not mislabelled.
    intake.attach_proposal(db, tid, _proposal(
        "lullaby-reed-basket", "Lullaby Reed Basket", "baby", form="basket",
        construction="in_the_round", recipient="new_parent", motif="lullaby bands"))
    out = _run(db, "radar.concept_intake", {})
    assert out["approved"] == [], out
    reasons = {r["slug"]: r["reasons"] for r in out["refused"]}
    assert any(r.startswith("children's policy (product_creation)")
               for r in reasons["willow-nursery-reed-basket"]), reasons
    held = [r for r in reasons["lullaby-reed-basket"] if r.startswith(CF.HOLD_PREFIX)]
    assert held and CF.hold_family(held[0]) == FC.VESSEL, reasons["lullaby-reed-basket"]


# ---- the router itself ------------------------------------------------------------------------


def _proof_exists(proof: str) -> bool:
    """A proof is `tests/<file>.py::<test>` naming a test function that exists in that file."""
    import ast

    path, _, name = proof.partition("::")
    if not (path.startswith("tests/test_") and name):
        return False
    tree = ast.parse((ROOT / path).read_text())
    return any(isinstance(n, ast.FunctionDef) and n.name == name for n in tree.body)


def test_router_admits_only_verified_or_physical_gated_families():
    admitted = {k for k, f in CF.FAMILIES.items() if f.status in CF.ADMITTED_STATUSES}
    assert admitted == {FC.FLAT_PANEL, FC.VESSEL, FC.TAPESTRY, FC.PANEL_PAIR,
                        FC.COLOURWORK_TAPESTRY,
                        FC.AMIGURUMI, FC.ENVELOPE, FC.APPLIQUE, FC.LOVEY,
                        CF.GARMENT_RAGLAN, CF.GARMENT_ONE_PIECE,           # ENG-GARMENT
                        *CF.WEARABLE_FAMILIES,                              # ENG-GARMENT-2
                        *HD.VARIANTS}, admitted                             # ENG-HOMEDECOR
    # Every admitted family names the test that proves it, and that test exists (ENG-PLUSH:
    # the core-family proofs live in tests/test_eng_plush.py).
    for key in admitted:
        proof = CF.FAMILIES[key].proof
        assert _proof_exists(proof), (key, proof)
    # A partial engine is held even when the route and the declaration agree.
    got = CF.route(category="bag", title="Simple Drawstring Pouch", form="pouch",
                   construction="in_the_round")
    assert not got["admitted"] and got["reason"].startswith("construction_unsupported:pouch")
    ok = CF.route(category="basket", title="Saltmarsh Reed Basket", form="basket",
                  construction="seamless_tube")
    assert ok == {"admitted": True, "family": FC.VESSEL, "status": CF.VERIFIED, "reason": ""}


def test_router_family_table_is_the_report_and_names_every_unbuilt_family():
    table = {r["family"]: r for r in CF.family_table()}
    for key in ("mosaic", "cable", "motif", "garment", "ornament"):
        assert table[key]["status"] == CF.NONE and table[key]["gaps"], key
    report = (ROOT / "research/final_build/w6/construction_families.md").read_text()
    for key, row in table.items():
        assert f"`{key}`" in report, f"construction_families.md omits {key}"


# ---- H1/M1 (fix round 1): named features, held categories, every admitted pair ----------------

FLAT_PAIR_TITLES = {
    "blanket": ("Tidewater Line Throw", "rectangle_throw"),
    "baby": ("Tidewater Line Baby Blanket", "rectangle_throw"),
    "runner": ("Tidewater Line Table Runner", "runner"),
    "placemat": ("Tidewater Line Placemat Pair", "flat_panel"),
    "dishcloth": ("Tidewater Line Dishcloth", "flat_panel"),
    "wall_decor": ("Tidewater Line Wall Decor", "wall_hanging"),
    "pet": ("Tidewater Line Pet Mat", "flat_panel"),
    "scarf": ("Tidewater Line Scarf", "scarf"),
}
# A word for each feature in the shared vocabulary (one sample each; the meta-guard below
# fails when a feature is added to the vocabulary without one).
FEATURE_SAMPLES = {
    "granny_square": "Granny Square", "cable": "Cable", "bobble": "Bobble",
    "waffle_stitch": "Waffle", "lid": "Lidded", "handles": "Handled",
    "closure": "Zippered", "straps": "Strap", "outline_round": "Round",
    "outline_oval": "Oval", "bowl": "Bowl", "planter": "Planter",
    "stitch_texture": "Moss Stitch",
    "amigurumi_features": "Bunny Ears", "trim": "Fringe", "lining_pocket": "Lined",
    "motif_assembly": "Hexie", "colourwork": "Fair Isle", "garment_or_wearable": "Beanie",
    "mosaic_or_c2c": "Mosaic", "charted_tapestry": "Charted",
    "embroidery": "Embroidered",
}
# One plain, admitted concept per admitted family: (category, form, construction, title).
ADMITTED_PLAIN = {
    FC.FLAT_PANEL: ("runner", "runner", "flat_rows", "Tide Line Table Runner"),
    FC.VESSEL: ("basket", "basket", "in_the_round", "Saltmarsh Reed Basket"),
    FC.TAPESTRY: ("basket", "basket", "tapestry", "Checked Tapestry Shelf Basket"),
    FC.PANEL_PAIR: ("pillow", "pillow", "flat_rows", "Hollow Fern Cushion Cover"),
    FC.COLOURWORK_TAPESTRY: ("blanket", "rectangle_throw", "tapestry",
                             "Modern Step Tapestry Throw"),
}


def _route(family: str, title: str, premise: str = "") -> dict:
    cat, form, constr, base = ADMITTED_PLAIN[family]
    return CF.route(category=cat, title=title or base, form=form, construction=constr,
                    premise=premise)


def test_plain_concepts_are_still_admitted_in_every_admitted_family():
    for family in ADMITTED_PLAIN:
        got = _route(family, "")
        assert got["admitted"] and got["family"] == family, (family, got)
    # Plain baskets, with and without a premise that names nothing unbuilt.
    for title in ("Saltmarsh Reed Basket", "Everyday Storage Basket", "Cosy Yarn Basket"):
        got = CF.route(category="basket", title=title, form="basket",
                       construction="in_the_round",
                       premise="holds rolled towels by the bath, in quiet bands of sea glass")
        assert got["admitted"], (title, got)


def test_every_named_feature_is_held_for_every_admitted_family():
    assert set(FEATURE_SAMPLES) == {f for f, _, _ in CF.NAMED_FEATURES}, \
        "a feature in the shared vocabulary has no sample here (or a sample has no feature)"
    honest = {f: fams for f, _, fams in CF.NAMED_FEATURES}
    for family in ADMITTED_PLAIN:
        base = ADMITTED_PLAIN[family][3]
        for feature, word in FEATURE_SAMPLES.items():
            if family in honest[feature]:
                continue    # the family's own technique word (tapestry for the tapestry families)
            # The title names it.
            got = _route(family, f"{word} {base}")
            honest_fams = next(h for f, _, h in CF.NAMED_FEATURES if f == feature)
            # ENG-HOMEDECOR: a title naming a feature an engine builds drafts in THAT engine
            # ("Round ... Basket" is the round vessel); it is never admitted to this family.
            # (b19-c B1: `honest_fams`, not `honest`, which is the feature -> families dict.)
            assert (got["admitted"] and got["family"] in honest_fams) or \
                (not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX)), \
                (family, feature, "title", got)
            assert got["family"] != family or not got["admitted"], (family, feature, got)
            # The premise names it, and the title is plain: the premise is read too.
            got = _route(family, "", premise=f"A plain piece, made with {word.lower()} work")
            assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), \
                (family, feature, "premise", got)
            if feature not in ("handles", "straps"):    # the tote is where these belong
                assert feature in got["reason"], (family, feature, got["reason"])


def test_the_reported_basket_features_are_held_not_certified_as_plain_baskets():
    for title in ("Granny Square Basket", "Cable Knit Look Basket", "Bobble Storage Basket",
                  "Bunny Ears Nursery Basket", "Waffle Stitch Basket"):
        got = CF.route(category="basket", title=title, form="basket",
                       construction="in_the_round")
        assert not got["admitted"], (title, got)
        assert got["reason"].startswith(CF.HOLD_PREFIX), (title, got["reason"])
    # ENG-HOMEDECOR: the lid is now built, so a lidded basket drafts as the lidded vessel and
    # is never certified as the plain one.
    got = CF.route(category="basket", title="Lidded Storage Basket", form="basket",
                   construction="in_the_round")
    assert got["admitted"] and got["family"] == HD.LIDDED, got
    # Through intake, so the hold reaches the concept's refusal reasons.
    reasons = intake.construction_verdict("basket", "basket", "in_the_round",
                                          title="Granny Square Basket")
    assert reasons and reasons[0].startswith("construction_unsupported:granny_square"), reasons


def test_mutant_without_the_feature_vocabulary_admits_a_granny_basket():
    """Mutate: with the shared vocabulary emptied, the granny basket is admitted again, so the
    vocabulary is what holds it (and the tests above fail without it). ("Granny Stripe": the
    vessel route itself refuses "Square" as an outline since ENG-HOMEDECOR.)"""
    real = CF.NAMED_FEATURES
    try:
        CF.NAMED_FEATURES = ()
        got = CF.route(category="basket", title="Granny Stripe Basket", form="basket",
                       construction="in_the_round")
        assert got["admitted"], "the mutant must admit it, or the guard is not what holds it"
    finally:
        CF.NAMED_FEATURES = real
    assert not CF.route(category="basket", title="Granny Stripe Basket", form="basket",
                        construction="in_the_round")["admitted"]


def test_a_pet_bed_is_held_until_it_certifies():
    for title in ("Cat Bed", "Snug Cat Bed", "Kitten Nest"):
        got = CF.route(category="pet", title=title, form="basket", construction="in_the_round")
        assert not got["admitted"] and got["reason"].startswith("construction_unsupported:pet_bed"), \
            (title, got)
    # The flat pet mat is a different, certifying pair and stays admitted.
    assert CF.route(category="pet", title="Tidewater Line Pet Mat", form="flat_panel",
                    construction="flat_rows")["admitted"]


def test_every_admitted_flat_category_certifies_end_to_end():
    for category, (title, form) in FLAT_PAIR_TITLES.items():
        got = CF.route(category=category, title=title, form=form, construction="flat_rows")
        assert got["admitted"] and got["family"] == FC.FLAT_PANEL, (category, got)
        slug = "tidewater-" + category.replace("_", "-")
        pod = "kitchen_bath" if category in ("runner", "placemat", "dishcloth") else "home_decor"
        out = _certify_research_concept(_proposal(slug, title, category, form=form, pod=pod))
        assert out["drafted"]["construction"] == FC.FLAT_PANEL, (category, out["drafted"])
        _assert_certified_end_to_end(out)


WEARABLE_PROBES = [
    ("hat", "hat", "in_the_round", "Hollin Ridge Beanie"),
    ("hat", "hat", "in_the_round", "Baby Beanie"),
    ("hat", "hat", "in_the_round", "Kids Toque"),
    ("baby", "fitted_garment", "bottom_up", "Sorrel Baby Dress"),
    ("dress", "fitted_garment", "bottom_up", "Wren Song Baby Pinafore"),
    ("baby", "fitted_garment", "bottom_up", "Meadowlark Baby Romper"),
    ("top", "fitted_garment", "flat_rows", "Harbour Light Boxy Tee"),
    ("top", "fitted_garment", "flat_rows", "Seagrass Tank"),
    ("top", "fitted_garment", "flat_rows", "Rockpool Kids Tank"),
    ("cardigan", "fitted_garment", "top_down_yoke", "Larkspur V-Neck Cardigan"),
    ("cardigan", "fitted_garment", "top_down_yoke", "Chestnut Kids V-Neck Cardigan"),
    ("baby", "fitted_garment", "top_down_yoke", "Snowberry Baby V-Neck Cardigan"),
    ("sock", "fitted_garment", "in_the_round", "Moorland Socks"),
    ("sock", "fitted_garment", "in_the_round", "Puddle Jump Kids Socks"),
    ("slipper", "fitted_garment", "in_the_round", "Inglenook Slippers"),
    ("slipper", "fitted_garment", "in_the_round", "Burrow Kids Slippers"),
    ("shawl", "draped_garment", "flat_rows", "Saltgrass Shawl"),
    ("shawl", "draped_garment", "flat_rows", "Lantern Hour Wrap"),
    ("bag", "bag", "in_the_round", "Chandlers Row Tote"),
    ("bag", "bag", "in_the_round", "Saturday Stall Market Bag"),
]


def test_every_admitted_family_category_pair_names_an_existing_certifying_proof():
    """The meta-guard over (family, category) pairs, not families: sweep the router across every
    category and plain title, and require each pair it admits to name a proof that exists."""
    from brambleloop.radar import intake as I

    here = {n for n, _ in inspect.getmembers(sys.modules[__name__], inspect.isfunction)}
    probes = []
    for cat, forms in I.SUPPORTED_FORMS.items():
        for noun in (I._NOUN.get(cat, cat.title()), cat.replace("_", " ").title()):
            for form in forms:
                probes.append((cat, form, "flat_rows", f"Tidewater Line {noun}"))
    probes += [("basket", "basket", "in_the_round", "Saltmarsh Reed Basket"),
               ("basket", "basket", "tapestry", "Checked Tapestry Shelf Basket"),
               ("pillow", "pillow", "flat_rows", "Hollow Fern Cushion Cover"),
               ("wedding", "pillow", "flat_rows", "Wedding Ring Cushion"),
               ("pet", "basket", "in_the_round", "Snug Cat Bed"),
               ("pet", "basket", "in_the_round", "Cat Bed"),
               ("pet", "basket", "in_the_round", "Kitten Nest"),
               # ENG-HOMEDECOR vessel variants.
               ("basket", "basket", "in_the_round", "Round Tide Reed Basket"),
               ("basket", "basket", "in_the_round", "Tide Catchall Bowl"),
               ("basket", "basket", "in_the_round", "Lidded Tide Reed Basket"),
               ("basket", "basket", "in_the_round", "Tide Reed Basket With Handles"),
               # ENG-COLOURWORK: the colourwork family across every category it could reach.
               *[(cat, form, "tapestry", f"Modern Step Tapestry {noun}")
                 for cat, form, noun in (
                     ("blanket", "rectangle_throw", "Throw"), ("placemat", "flat_panel",
                                                                "Placemat"),
                     ("pillow", "pillow", "Cushion Cover"), ("basket", "basket", "Basket"),
                     ("bag", "bag", "Tote"), ("runner", "runner", "Table Runner"),
                     ("scarf", "scarf", "Scarf"), ("dishcloth", "flat_panel", "Dishcloth"),
                     ("wall_decor", "wall_hanging", "Wall Hanging"),
                     ("baby", "rectangle_throw", "Baby Blanket"))],
               ("basket", "basket", "tapestry", "Wave Tapestry Basket"),
               ("toy", "toy", "amigurumi_shaping", "Ball Bear Amigurumi"),
               ("amigurumi", "toy", "in_the_round", "Cosy Rabbit"),
               ("pillow", "pillow", "flat_rows", "Linen Envelope Cushion Cover"),
               ("pillow", "pillow", "flat_rows", "Highland Cow Cushion Cover"),
               ("baby", "toy", "amigurumi_shaping", "Bear Lovey"),
               ("toy", "toy", "amigurumi_shaping", "Bunny Lovey"),
               ("amigurumi", "toy", "in_the_round", "Cosy Rabbit Lovey"),
               # ENG-GARMENT: graded garments (each pair pinned in tests/test_eng_garment.py)
               ("cardigan", "fitted_garment", "top_down_yoke", "Fernway Raglan Cardigan"),
               ("baby", "fitted_garment", "top_down_yoke", "Hush Baby Cardigan"),
               ("sweater", "fitted_garment", "flat_rows", "Puddle Lane Kids Sweater"),
               ("sweater", "fitted_garment", "flat_rows", "Cosy Adult Sweater"),
               ("vest", "fitted_garment", "side_to_side", "Driftline Vest"),
               ("pullover", "fitted_garment", "bottom_up", "Kestrel Pullover")]
    # ENG-GARMENT-2: wearable families (each pair pinned in tests/test_eng_garment2.py).
    probes += WEARABLE_PROBES
    admitted = set()
    for cat, form, constr, title in probes:
        got = CF.route(category=cat, title=title, form=form, construction=constr)
        if got["admitted"]:
            admitted.add((got["family"], cat))
    assert (FC.VESSEL, "pet") not in admitted, "pet beds do not certify and must stay held"
    for pair in sorted(admitted):
        proof = CF.PAIR_PROOFS.get(pair)
        assert proof, f"{pair} is admitted but names no certifying proof (CF.PAIR_PROOFS)"
        assert _proof_exists(proof), (pair, proof)
        if proof.startswith("tests/test_eng_families.py::"):
            assert proof.split("::")[1] in here, (pair, proof)
    # And no proof is claimed for a pair the router never admits.
    assert set(CF.PAIR_PROOFS) >= admitted
    assert set(CF.PAIR_PROOFS) == admitted, \
        set(CF.PAIR_PROOFS) - admitted


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    failures = 0
    for t in TESTS:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            print("FAIL", t.__name__, repr(exc))
            traceback.print_exc()
    print(f"{failures} failure(s)")
    sys.exit(1 if failures else 0)
