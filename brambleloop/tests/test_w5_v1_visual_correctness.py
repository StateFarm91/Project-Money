"""W5-V1, P0-VISUAL-CORRECTNESS (audit VISUAL_WIRING_AUDIT_5ba84bf7 section 4). Offline,
SHADOW, CA$0: stub generator (unpaid), stub vision readings, no provider is ever called.

* P0-a: a LIFESTYLE `lifestyle_evidence` FAIL on a chart (pattern-derived) reference is
  structural. The repair router returns None for it and the run blocks with the named reason
  after exactly one LIFESTYLE call; later worker ticks buy nothing. The policy is not relaxed.
* P0-d: one back-loop crease round is not ribbing; a repeating loop/post pattern is.
* P1-b: the PRODUCT section states the polygon side count, the colour bands and the rim, all
  derived from the certified CIR, and states no band for a single-colour or charted fabric.
* P2-b: the AI flat lay is never called a photograph.
* P1-c: a listing without Laura gets briefs without Laura.

Run: cd brambleloop && python tests/test_w5_v1_visual_correctness.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import socket
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))


def _no_network(*_a, **_k):
    raise OSError("network refused by the W5-V1 harness")


socket.socket.connect = _no_network  # type: ignore[assignment]

import test_w4_ownerimg as O  # noqa: E402  (stub generator, worker drain, png)

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, PatternVersion, Product  # noqa: E402

BASKET_LISTING = "hexagonal-bread-basket"


def _basket():
    from brambleloop.products.vessels import build_basket

    return build_basket("small")


def _rules(cir):
    from brambleloop.creative import pattern_refs as P

    return P.technical_rules(cir, release_hash=P.release_hash_of(cir))


def _prompt(cir, roles=None, role="lifestyle"):
    from brambleloop.creative import flux_prompt as FP

    return FP.build(rules=_rules(cir), roles=roles or (list(FP.PRODUCT_ROLES)
                                                       + ["product_candidate"]), role=role)


def _product_section(text: str) -> str:
    return next(line for line in text.splitlines() if line.startswith("PRODUCT:"))


# ---- P0-a ---------------------------------------------------------------------------------

def _basket_db():
    from brambleloop.creative.pattern_refs import release_hash_of
    from brambleloop.visual.launch_imagery import _listing_parts

    cir = _listing_parts(BASKET_LISTING)[1][0]
    rel = release_hash_of(cir)
    tmp = tempfile.mkdtemp(prefix="w5v1-db-")
    db = Database("sqlite:///" + str(Path(tmp) / "s.db"), scratch=True)
    db.create_all()
    with db.session() as s:
        p = Product(slug=cir.slug, title=cir.title or cir.slug)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True, release_hash=rel))
        j = Job(agent="synthetic", job_type="assets.build", inputs={"release": rel})
        s.add(j)
        s.flush()
        s.add(AuditLog(actor="synthetic", action="assets.built",
                       artifact=f"{cir.slug}@{cir.version}", job_id=j.id,
                       detail={"pdf_sha256_by_terminology": {"US": "a" * 64, "UK": "b" * 64}}))
    return db, cir, rel


def _judges(db):
    """The production `RealJudges.product_truth` (structural floor, fidelity, and
    `lifestyle_evidence` for LIFESTYLE), with only the vision-backed readings stubbed PASS so
    nothing but `lifestyle_evidence` can fail. No vision provider is called."""
    from brambleloop.visual import candidate_gates as CG

    class Judges(CG.RealJudges):
        def identity(self, c):
            return {"status": "PASS", "why": "stub"}

        def anatomy(self, c):
            return {"status": "PASS", "why": "stub"}

        def realism(self, c):
            return {"status": "PASS", "why": "stub"}

        def body_proportions(self, c):
            return {"status": "PASS", "why": "stub"}

        def outfit_consistency(self, c, outfit):
            return {"status": "PASS", "why": "stub"}

    return Judges(db)


class _FidelityPass:
    """Stub the fidelity verifier's reading (it needs a funded vision judge) to PASS."""

    def __enter__(self):
        from brambleloop.visual import candidate_gates as CG

        self.saved = CG.fidelity_reading
        CG.fidelity_reading = lambda *a, **k: {"status": "PASS", "why": "stub fidelity",
                                               "codes": [], "failed": [], "unknown": []}
        return self

    def __exit__(self, *exc):
        from brambleloop.visual import candidate_gates as CG

        CG.fidelity_reading = self.saved
        return False


def test_structural_lifestyle_failure_blocks_after_one_call_and_buys_nothing_more():
    from brambleloop.visual import image_production as IP

    db, cir, rel = _basket_db()
    gen = O.StubGenerator()
    judges = _judges(db)
    with _FidelityPass():
        follow, _ = O.drain(db, generator=gen, judges=judges)
        assert IP.trigger(follow, slug=cir.slug, version=cir.version, release=rel)["enqueued"]
        O.drain(db, generator=gen, judges=judges)
        key = IP.run_key(cir.slug, cir.version, rel)
        run = IP.get_run(db, key)
        lifestyle_calls = [r for r, _k, _o in gen.seen if r == "lifestyle"]
        assert len(lifestyle_calls) == 1, gen.seen                       # exactly one
        assert not any(gen.repairs), gen.repairs                         # no repair bought
        assert run["state"] == "blocked" and run["attempts_exhausted"], run
        assert "lifestyle_evidence: chart reference" in run["blocked_reason"], run
        assert run["blocked_reason"].startswith("lifestyle:")
        calls = run["generation_calls"]
        assert calls == gen.calls
        # the router: structural -> None (never an empty repair)
        best = IP._best(db, listing=BASKET_LISTING, role="lifestyle", run=key)
        assert best["technical_status"] == "FAIL"
        assert best["structural"] == "lifestyle_evidence: chart reference"
        assert IP._repair_for(best) is None
        # the policy is unchanged: the reading still FAILs, on the informational reference
        assert IP.restartable(db, key)["restartable"] is False
        # later worker ticks: nothing is enqueued or generated, the trigger is idempotent
        for _ in range(3):
            O.drain(db, generator=gen, judges=judges)
            IP.trigger(follow, slug=cir.slug, version=cir.version, release=rel)
            O.drain(db, generator=gen, judges=judges)
        again = IP.get_run(db, key)
        assert again["generation_calls"] == calls and gen.calls == calls, (again, gen.calls)
        assert again["state"] == "blocked"
        # one named notification, no owner card claiming readiness
        notes = IP.notification_candidates(db)
        assert len(notes) == 1 and "lifestyle_evidence: chart reference" in str(notes[0])


def test_lifestyle_reading_names_the_structural_reason_and_keeps_the_policy():
    from brambleloop.visual import candidate_gates as CG

    cand = {"slug": "x", "version": "1", "references": [{"kind": "pattern_derived"}]}
    le = CG.lifestyle_reading(cand, {"pieces": 1, "cir_fingerprint": "f"})
    assert le["status"] == "FAIL" and le["structural"] == "lifestyle_evidence: chart reference"
    assert any("informational" in f for f in le["failed"])
    # a photographic reference class is not structural (it is missing evidence, not a FAIL)
    ph = CG.lifestyle_reading({**cand, "references": [{"kind": "physical_product_photo"}]},
                              {"pieces": 1})
    assert ph["status"] != "PASS" and "structural" not in ph


def test_router_still_repairs_routable_codes_and_refuses_unrouted_ones():
    from brambleloop.visual import image_production as IP

    routed = IP._repair_for({"failure_categories": ["product_fidelity", "INVENTED_EDGING"]})
    assert routed and routed["directives"]
    assert IP._repair_for({"failure_categories": ["SOMETHING_NEW"]}) is None
    assert IP._repair_for({"failure_categories": ["product_fidelity"],
                           "structural": "lifestyle_evidence: chart reference"}) is None
    # a routable code beside the structural failure is still repaired (wardrobe, edging)
    both = IP._repair_for({"failure_categories": ["product_fidelity", "INVENTED_EDGING"],
                           "structural": "lifestyle_evidence: chart reference"})
    assert both and both["directives"]
    assert IP.structural_failure({"product_truth": {"lifestyle_evidence": {
        "status": "FAIL", "structural": "lifestyle_evidence: chart reference"}}}) == \
        "lifestyle_evidence: chart reference"
    assert IP.structural_failure({"product_truth": {"status": "FAIL"}}) is None


# ---- P0-d ---------------------------------------------------------------------------------

def test_one_back_loop_crease_round_is_not_ribbing():
    from brambleloop.creative import pattern_refs as P

    rules = _rules(_basket())
    assert rules["fabric"]["ribbing_declared"] is False
    assert any(n.startswith("ribbing anywhere") for n in rules["negatives"])
    assert "ribbing anywhere" in _prompt(_basket()).text
    assert P.VERSION.startswith("pattern-refs/3.1")


def _flat(slug, rows, colors, title="Test Piece"):
    from brambleloop.cir.model import CIR, Component, Material
    from brambleloop.products.texture import CHUNKY

    return CIR(slug=slug, title=title, version="1.0.0", construction="flat_rows",
               risk_class="A", colors=dict(colors), gauge=replace(CHUNKY),
               materials=[Material(name="chunky acrylic", yarn_weight="chunky",
                                   colorway=c, color_id=c) for c in colors],
               components=[Component(name="piece", construction="flat_rows", rows=rows,
                                     foundation=12)])


def _row(i, color, loop="both", note=None, n=12):
    from brambleloop.cir.model import Op, Row

    return Row(index=i, ops=[Op("sc", n, loop=loop) if loop != "both" else Op("sc", n)],
               declared_count=n, color=color, turning_chain=1, note=note)


def test_a_genuinely_ribbed_fabric_still_reads_ribbed():
    from brambleloop.creative import pattern_refs as P
    from brambleloop.products.texture import build_ribbed_scarf

    scarf = build_ribbed_scarf()                              # catalogue: fpdc/bpdc ribbing
    assert P.fabric_facts(scarf)["ribbing_declared"] is True
    assert not any(n.startswith("ribbing anywhere") for n in _rules(scarf)["negatives"])
    pine = {"pine": "#244A3A"}
    blo_every = _flat("blo-rib", [_row(1, "pine")] + [_row(i, "pine", "back")
                                                      for i in range(2, 21)], pine)
    assert P.fabric_facts(blo_every)["ribbing_declared"] is True
    blo_alt = _flat("blo-alt", [_row(1, "pine")] + [_row(i, "pine", "back" if i % 2 else
                                                         "both") for i in range(2, 21)], pine)
    assert P.fabric_facts(blo_alt)["ribbing_declared"] is True
    one = _flat("blo-one", [_row(i, "pine", "back" if i == 6 else "both")
                            for i in range(1, 21)], pine)
    assert P.fabric_facts(one)["ribbing_declared"] is False
    fold = _flat("blo-fold", [_row(i, "pine", "back" if i in (6, 7) else "both",
                                   note="fold line" if i in (6, 7) else None)
                              for i in range(1, 21)], pine)
    assert P.fabric_facts(fold)["ribbing_declared"] is False      # fold rows are construction


def test_separated_front_and_back_posts_are_not_ribbing():
    from brambleloop.cir.model import Op
    from brambleloop.creative import pattern_refs as P

    rows = [_row(i, "pine") for i in range(1, 22)]
    rows[1].ops = [Op("fpdc", 12)]
    rows[-1].ops = [Op("bpdc", 12)]
    cir = _flat("separated-posts", rows, {"pine": "#244A3A"})
    facts = P.fabric_facts(cir)
    assert facts["ribbing_declared"] is None, facts
    assert not any(n.startswith("ribbing anywhere") for n in _rules(cir)["negatives"])
    assert "ribbing anywhere" not in _prompt(cir).text
    from brambleloop.visual import fidelity
    exp = fidelity.expectation(cir)
    reading = {"fabric_visible_clearly": "true", "craft": "crochet", "cable_style": "none",
               "ribbing_visible": "false", "border_or_edging_visible": "false"}
    assert fidelity.compare_craft(reading, exp)["status"] == "UNKNOWN"


def test_mixed_post_rib_requires_repetition_on_nearby_rows():
    from brambleloop.cir.model import Op, Repeat
    from brambleloop.creative import pattern_refs as P

    def make(slug, post_rows):
        rows = [_row(i, "pine") for i in range(1, 22)]
        for index in post_rows:
            rows[index - 1].ops = [Repeat([Op("fpdc", 2), Op("bpdc", 2)], times=3)]
        return _flat(slug, rows, {"pine": "#244A3A"})

    assert P.fabric_facts(make("one-mixed", [2]))["ribbing_declared"] is None
    assert P.fabric_facts(make("two-separated", [2, 21]))["ribbing_declared"] is None
    assert P.fabric_facts(make("two-adjacent", [2, 3]))["ribbing_declared"] is True


def test_shifted_post_columns_remain_unknown():
    from brambleloop.cir.model import Op, Repeat
    from brambleloop.creative import pattern_refs as P
    rows = [_row(i, "pine") for i in range(1, 6)]
    rows[1].ops = [Repeat([Op("fpdc", 2), Op("bpdc", 2)], times=3)]
    rows[2].ops = [Op("sc", 1), Repeat([Op("fpdc", 2), Op("bpdc", 2)], times=2),
                   Op("fpdc", 2), Op("bpdc", 1)]
    assert P.fabric_facts(_flat("shifted-rib", rows, {"pine": "#244A3A"}))["ribbing_declared"] is None


def test_post_blocks_and_fold_rows_do_not_prove_ribbing():
    from brambleloop.cir.model import Op
    from brambleloop.creative import pattern_refs as P
    rows = [_row(i, "pine") for i in range(1, 6)]
    for i in (1, 2): rows[i].ops = [Op("fpdc", 6), Op("bpdc", 6)]
    assert P.fabric_facts(_flat("post-blocks", rows, {"pine": "#244A3A"}))["ribbing_declared"] is None
    for i in (1, 2): rows[i].note = "fold and crease line"
    assert P.fabric_facts(_flat("post-folds", rows, {"pine": "#244A3A"}))["ribbing_declared"] is False


def test_sparse_loop_only_stitches_do_not_prove_whole_row_ribbing():
    from brambleloop.cir.model import Op
    from brambleloop.creative import pattern_refs as P
    rows = [_row(i, "pine") for i in range(1, 6)]
    for i in (1, 2): rows[i].ops = [Op("sc", 1, loop="back"), Op("sc", 11)]
    cir = _flat("sparse-loop", rows, {"pine": "#244A3A"})
    assert P.fabric_facts(cir)["ribbing_declared"] is None
    from brambleloop.visual import fidelity
    reading = {"fabric_visible_clearly": "true", "craft": "crochet", "cable_style": "none",
               "ribbing_visible": "false", "border_or_edging_visible": "false"}
    assert fidelity.compare_craft(reading, fidelity.expectation(cir))["status"] == "UNKNOWN"


def test_expected_ribbing_cannot_pass_when_not_visible():
    from brambleloop.products.texture import build_ribbed_scarf
    from brambleloop.visual import fidelity
    exp = fidelity.expectation(build_ribbed_scarf())
    assert exp.ribbing_declared is True
    reading = {"fabric_visible_clearly": "true", "craft": "crochet", "cable_style": "none",
               "ribbing_visible": "false", "border_or_edging_visible": "false"}
    assert fidelity.compare_craft(reading, exp)["status"] == "FAIL"
    reading["fabric_visible_clearly"] = "false"
    assert fidelity.compare_craft(reading, exp)["status"] == "UNKNOWN"
    reading["fabric_visible_clearly"] = "true"
    reading["ribbing_visible"] = "unclear"
    assert fidelity.compare_craft(reading, exp)["status"] == "UNKNOWN"
    reading["ribbing_visible"] = "true"
    assert fidelity.compare_craft(reading, exp)["status"] == "PASS"


def test_small_ribbed_component_prevents_global_no_ribbing_claim():
    from brambleloop.cir.model import Op, Repeat
    from brambleloop.creative import pattern_refs as P
    from brambleloop.visual import fidelity
    pine = {"pine": "#244A3A"}
    cir = _flat("large-plain-small-rib", [_row(i, "pine") for i in range(1, 22)], pine)
    small_rows = [_row(i, "pine") for i in range(1, 5)]
    for i in (1, 2):
        small_rows[i].ops = [Repeat([Op("fpdc", 2), Op("bpdc", 2)], times=3)]
    small = _flat("small-rib", small_rows, pine).components[0]
    small.name = "cuff"
    cir.components.append(small)
    facts = P.fabric_facts(cir)
    assert facts["ribbing_declared"] is None, facts
    assert not any(n.startswith("ribbing anywhere") for n in _rules(cir)["negatives"])
    reading = {"fabric_visible_clearly": "true", "craft": "crochet", "cable_style": "none",
               "ribbing_visible": "false", "border_or_edging_visible": "false"}
    assert fidelity.compare_craft(reading, fidelity.expectation(cir))["status"] == "UNKNOWN"


# ---- P1-b + P2-b ----------------------------------------------------------------------------

def test_basket_prompt_names_six_corners_two_wine_stripes_and_the_plain_cream_rim():
    cir = _basket()
    f = _rules(cir)["fabric"]
    assert f["polygon"]["sides"] == 6 and f["polygon"]["name"] == "hexagon"
    assert [(b["colour"], b["rounds"]) for b in f["colour_bands"]] == [("wine", [15, 16]),
                                                                        ("wine", [18, 19])]
    assert f["ground_colour"] == "cream" and f["colour_layout"] == "stripes"
    assert f["final_round"] == {"round": 22, "stitch": "sc", "colour": "cream",
                                "hex": "#FAF6EB", "plain": True}
    built = _prompt(cir)
    product = _product_section(built.text)
    assert ("Shape: a vessel with a flat 6-sided (hexagon) base: exactly 6 corners where the "
            "increases stack, and walls rising from it.") in product
    assert ("Colour layout: cream #FAF6EB ground with 2 wine stripes of 2 rounds each "
            "(rounds 15-16 and rounds 18-19); 2 stripes in total, no others.") in product
    assert ("Edge: the top rim is the plain final round (round 22) of sc in cream #FAF6EB, "
            "with no edging.") in product
    assert "sample.." not in product
    assert any(s["ref"] == "image.flux3.product@3" for s in built.sections)
    from brambleloop.creative import flux_prompt as FP

    assert built.receipt()["builder_version"] == FP.BUILDER_VERSION == \
        "flux3-prompt-builder/2.1.0"
    # derived, not hard-coded: the medium basket's own rounds and rim
    from brambleloop.products.vessels import build_basket

    med = _product_section(_prompt(build_basket("medium")).text)
    assert "(rounds 22-23 and rounds 28-29)" in med and "(round 35)" in med
    assert "6 corners" in med


def test_ai_flat_lay_is_never_called_a_photograph():
    built = _prompt(_basket())
    refs = built.text.splitlines()[0]
    assert ("image 5 = AI-generated product-only flat lay of this exact product (verified "
            "against the pattern)") in refs
    assert "photograph" not in refs
    assert "approved product photograph" not in built.text


def test_striped_flat_piece_gets_exact_bands_and_no_corners():
    two = {"oat": "#E8DCC4", "rust": "#A0522D"}
    rows = [_row(i, "rust" if i in (5, 6, 7, 12) else "oat") for i in range(1, 17)]
    cir = _flat("stripe-test", rows, two, "Stripe Test Mat")
    f = _rules(cir)["fabric"]
    assert f["polygon"] is None and f["colour_layout"] == "stripes"
    product = _product_section(_prompt(cir).text)
    assert ("Colour layout: oat #E8DCC4 ground with 1 rust stripe of 3 rows (rows 5-7); "
            "1 rust stripe of 1 row (row 12); 2 stripes in total, no others.") in product
    assert "corner" not in product and "rim" not in product
    assert "Edge: the last row is the plain final row (row 16) of sc in oat" in product


def test_single_colour_and_charted_fabrics_state_no_spurious_bands():
    from brambleloop.products.texture import build_ribbed_scarf
    from brambleloop.visual.launch_imagery import _listing_parts

    scarf = _product_section(_prompt(build_ribbed_scarf()).text)
    assert "Colour layout: pine #244A3A throughout; no stripes or colour blocks." in scarf
    assert "stripe of" not in scarf and "stripes of" not in scarf
    # rows mixing stitch heights (mosaic/relief drop stitches) are charted, never "stripes"
    mosaic = _listing_parts("winter-village-graphghan")[1][0]
    text = _product_section(_prompt(mosaic).text)
    assert "Colour layout: exactly as charted in image 3." in text
    assert "stripe of" not in text and "stripes of" not in text
    # a single-colour vessel: no band, the rim still stated
    from brambleloop.creative import flux_prompt as FP

    one = _rules(_basket())
    one["fabric"] = {**one["fabric"], "colour_layout": "single_colour", "colour_bands": []}
    assert FP._colour_layout(one, "image 3") == ("cream #FAF6EB throughout; no stripes or "
                                                 "colour blocks")


# ---- P1-c ---------------------------------------------------------------------------------

def test_briefs_follow_whether_the_listing_uses_laura():
    from brambleloop.visual import shot_plans as SP

    basket = SP.campaign_plan(BASKET_LISTING)
    assert basket["laura_in_campaign"] is False
    gen = [r for r in basket["roles"] if r.get("generate")]
    assert gen and {r["role"] for r in gen} >= {"lifestyle", "size"}
    for r in basket["roles"]:
        assert "Laura" not in (r.get("brief") or "") and "Laura" not in str(
            r.get("campaign_role")), r
    size = next(r for r in gen if r["role"] == "size")
    assert "no person" in size["brief"] and "known size" in size["brief"]
    cloud = SP.campaign_plan("cloudline-baby-blanket")
    assert cloud["laura_in_campaign"] is True
    csize = next(r for r in cloud["roles"] if r.get("generate") and r["role"] == "size")
    assert csize["brief"] == SP.CAMPAIGN_GENERATED[csize["job"]] and "Laura" in csize["brief"]


if __name__ == "__main__":
    fails = passes = 0
    only = sys.argv[1:]
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and (not only or name in only):
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e)[:300])
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
