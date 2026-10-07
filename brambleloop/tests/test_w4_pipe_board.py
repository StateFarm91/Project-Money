"""W4-PIPE: the product pipeline board and the product inventory."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.products import inventory, pipeline_board as pb  # noqa: E402

FAILED: list[str] = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FAIL ") + name + (f" -- {detail}" if not cond and detail else ""))
    if not cond:
        FAILED.append(name)


def main():
    # Every proposal is pattern software that clears Product Truth deterministically.
    assert pb.PROPOSALS, "no proposals"
    from brambleloop.gates.certificate import certify
    from brambleloop.publish.eligibility import name_truth
    for p in pb.PROPOSALS:
        cir = pb.proposal_cir(p)
        cert = certify(cir)
        check(f"proposal_certifies:{p.slug}", cert.granted, [str(f) for f in cert.findings][:2])
        check(f"proposal_name_true:{p.slug}", name_truth(cir) == [], name_truth(cir))
        check(f"proposal_prerelease_version:{p.slug}", cir.version.startswith("0."), cir.version)
    # A proposal that names a fabric the tiler cannot make is refused at Product Truth.
    bad = replace(pb.PROPOSALS[0], slug="w4-false-mosaic", title="Diamond Mosaic Dishcloth")
    check("false_fabric_name_refused", name_truth(pb.proposal_cir(bad)) != [])

    import json
    findings = json.loads((ROOT / "research/final_build/w4/MJS_FINDINGS.json").read_text())
    assert findings.get("findings"), "no competitor findings on file"
    res = pb.board(today=date(2026, 10, 7), visual=False, findings=findings)
    rows = res["candidates"]
    assert rows, "empty board"
    check("publication_never_advanced", res["advances_publication"] is False
          and all(r["stages"].get("PUBLICATION", {}).get("status") != pb.PASS for r in rows))
    # No stage is PASS unless every stage before it is PASS.
    ok = True
    for r in rows:
        seen_gap = False
        for s in pb.STAGES:
            st = r["stages"].get(s, {}).get("status")
            if st != pb.PASS:
                seen_gap = True
            elif seen_gap:
                ok = False
    check("no_stage_skipped", ok)
    check("several_stages_occupied", sum(1 for v in res["at_stage"].values() if v) >= 3,
          res["at_stage"])
    by = {r["slug"]: r for r in rows}
    check("proposals_reach_visual",
          all(by[p.slug]["highest_passed"] == "PRODUCT_TRUTH" for p in pb.PROPOSALS),
          {p.slug: by[p.slug]["highest_passed"] for p in pb.PROPOSALS})
    check("retired_concept_blocked_at_design", by["hexie-coaster-set"]["stage"] == "DESIGN"
          and by["hexie-coaster-set"]["stage_status"] == pb.BLOCKED)
    check("uncalibrated_stitch_is_owner_gated",
          by["heirloom-cable-blanket"]["stage"] == "PRODUCT_TRUTH"
          and by["heirloom-cable-blanket"]["clearer"] == "OWNER")
    # Creative candidates (W4-CREATIVE briefs) sit at DESIGN with the exact engineering named.
    creative = [r for r in rows if r["source"] == "creative"]
    assert creative, "no creative candidates"
    waiting = [r for r in creative if r["slug"] not in pb.CREATIVE_ENGINEERED]
    if waiting:
        check("creative_candidates_at_design",
              all(r["stage"] == "DESIGN" and r["highest_passed"] == "INTELLIGENCE"
                  for r in waiting), [(r["slug"], r["stage"]) for r in waiting])
    else:
        # W4-PIPE2 engineered the rest of the queue: every brief now has a design that
        # passed DESIGN and PRODUCT (compiled), never one left at INTELLIGENCE.
        check("every_creative_candidate_engineered",
              all(r["stages"].get("PRODUCT", {}).get("status") == pb.PASS for r in creative),
              [(r["slug"], r["stage"]) for r in creative])
    # The engineered pencil roll carries its pocket, tie and seams, and clears Product Truth.
    roll = by["teacher-chevron-pencil-roll"]
    check("pencil_roll_clears_product_truth", roll["highest_passed"] == "PRODUCT_TRUTH", roll)
    cir = pb.pencil_roll_cir()
    check("pencil_roll_is_assembled", len(cir.assembly) == 3
          and [c.name for c in cir.components] == ["panel", "tie"])
    flat = replace(cir, components=cir.components[:1], assembly=[])
    check("flat_pencil_roll_fails_name_truth",
          any(n.startswith("assembly") for n in name_truth(flat)), name_truth(flat))
    # The Christmas stocking (CREATIVE engineering queue, first): flat pieces, every
    # cross-piece join measured on both sides, and the title says relief, not colourwork.
    stocking = by["first-christmas-stocking"]
    check("stocking_clears_product_truth", stocking["highest_passed"] == "PRODUCT_TRUTH",
          stocking)
    from brambleloop.cir import assembly as _asm
    from brambleloop.cir.compiler import compile_cir as _cc
    from brambleloop.cir.twin import build_twin as _bt
    sc = pb.stocking_cir()
    _r = _cc(sc)
    geo = _asm.assemble(sc, {k.name: _bt(sc, _r, component=k.name) for k in sc.components})
    check("stocking_assembles", geo.verdict == "assembles" and len(geo.joins) == 15
          and all(j.verdict == "sound" for j in geo.joins) and not _r.warnings,
          (geo.verdict, geo.why))
    check("stocking_names_relief_not_colourwork",
          "relief" in sc.title.lower() and "colourwork" not in sc.title.lower(), sc.title)
    check("legless_stocking_fails_name_truth",
          any(n.startswith("assembly") for n in name_truth(
              replace(sc, components=sc.components[:1], assembly=[]))))
    # Competitor findings become intelligence candidates; answered arenas are not repeated.
    intel = [r for r in rows if r["source"] == "intelligence"]
    assert intel, "no intelligence candidates"
    check("intel_candidates_cite_finding",
          all(r["stages"]["INTELLIGENCE"]["evidence"]["finding"]["key"] == "coverage_gaps"
              for r in intel))
    check("answered_arena_not_repeated", "gap-kitchen-and-bath-textiles" not in by
          and "gap-christmas-stockings" not in by)
    check("finding_proposal_reaches_visual",
          by["fir-star-relief-table-runner"]["highest_passed"] == "PRODUCT_TRUTH")
    # Without the findings on file, a proposal that cites one is not evidenced.
    bare = {r["slug"]: r for r in pb.board(today=date(2026, 10, 7), visual=False,
                                           include_pool=False)["candidates"]}
    check("cited_finding_missing_is_unknown",
          bare["fir-star-relief-table-runner"]["stages"]["INTELLIGENCE"]["status"] == pb.UNKNOWN
          and bare["fir-star-relief-table-runner"]["stage"] == "INTELLIGENCE")
    check("no_intel_candidates_without_findings",
          not any(r["source"] == "intelligence" for r in bare.values()))
    check("kitchen_bundle_ready",
          res["bundle_families"]["kitchen_texture"]["bundle_ready_for_pricing"],
          res["bundle_families"])
    # A pillow cover made of one front panel promises a make its CIR does not contain; the
    # released cover (1.3.0) carries its back panel and a sound perimeter seam, so only the
    # owner-gated stitch calibration remains.
    from brambleloop.products import texture
    pillow = texture.build_bobble_pillow()
    front_only = replace(pillow, components=pillow.components[:1], assembly=[])
    check("pillow_front_only_fails_name_truth",
          any(n.startswith("assembly") for n in name_truth(front_only)), name_truth(front_only))
    check("pillow_release_is_name_true", name_truth(pillow) == [] and pillow.version == "1.3.0"
          and [c.name for c in pillow.components] == ["front", "back"], name_truth(pillow))
    bp = by["bobble-floor-pillow"]
    check("pillow_only_owner_calibration_remains",
          bp["stage"] == "PRODUCT_TRUTH" and bp["clearer"] == "OWNER"
          and bp["stages"]["PRODUCT_TRUTH"]["evidence"]["name_truth"] == [], bp["stages"].get(
              "PRODUCT_TRUTH"))
    check("launch_scope_drafts_include_coasters",
          "hexagon-coaster-set" in pb.launch_scope_drafts())

    # The handler body: records the board and queues only cir.draft for unbuilt Launch-0 slugs.
    import tempfile
    from types import SimpleNamespace
    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog
    from sqlalchemy import select
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/b.sqlite"); db.create_all()
    queued = []
    ctx = SimpleNamespace(db=db, job=SimpleNamespace(inputs={"as_of": "2026-10-07"}),
                          enqueue=lambda agent, jt, inp, **kw: queued.append((jt, inp["slug"])))
    out = pb.handle_product_pipeline(ctx)
    check("handler_queues_only_cir_draft", queued and all(jt == "cir.draft" for jt, _ in queued),
          queued)
    check("handler_queues_coasters", ("cir.draft", "hexagon-coaster-set") in queued, queued)
    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == pb.AUDIT_ACTION)))
    check("handler_records_board", len(rows) == 1 and rows[0].detail["candidates"], len(rows))
    check("handler_never_publishes", out["advances_publication"] is False)

    # Inventory: company work is never reported as somebody else's job.
    check("unknown_reason_is_company", inventory.classify_reason("anything new")[1] == "COMPANY")
    check("taxonomy_is_external",
          inventory.classify_reason("search certificate (F-005): category UNKNOWN -- x")[1]
          == "EXTERNAL")
    st = inventory.static_truth("cloudline-baby-blanket")
    check("cloudline_product_truth", st["product_truth_ok"] and st["launch_scope"], st)
    # The garlands (1.3.0) are pennants on a cord: assembled, certified, name-true.
    from brambleloop.products import builder as _bld, launch0 as _l0
    for g in ("spooky-garland", "valentine-heart-garland"):
        st = inventory.static_truth(g)
        b = inventory._blockers(st, None, None)
        check(f"garland_assembled:{g}", st["certified"] and st["assembly_promise"]["backed"]
              and not any(x["gate"].startswith("name_") for x in b), (st, b))
    gcir = _bld.for_slug("valentine-heart-garland")
    bare = replace(gcir, components=gcir.components[:1], assembly=[])
    check("garland_without_cord_is_not_a_garland",
          not _l0.assembly_promise(bare)["backed"]
          and any(n.startswith("assembly") for n in name_truth(bare)))
    check("ornaments_now_true", inventory.static_truth("nordic-star-ornaments")["title_promise"]["backed"])

    # A reserve (outside Launch-0) is held to the Launch-0 standard before it is a candidate:
    # render authority, usable imagery and the first-customer gate on its stored release.
    st = inventory.static_truth("pet-snuggle-mat")
    check("pet_mat_is_reserve", st["product_truth_ok"] and not st["launch_scope"], st)
    owner_ext = ["FIRST_CUSTOMER_BLOCKING: gauge_and_size_claims: UNRESOLVED -- no sample",
                 "FIRST_CUSTOMER_BLOCKING: etsy_remote_state: UNVERIFIABLE -- 9 open",
                 "FIRST_CUSTOMER_BLOCKING: fulfilment_and_download: FAIL -- not durable"]
    ch = {"release": {"version": st["version"], "certified": True},
          "imagery": {"usable": True}, "publish_verdict": {"reasons": []},
          "render_authority": True, "reserve_first_customer": owner_ext}
    b = inventory._blockers(st, ch, None)
    company = [x for x in b if x["clearer"] == "COMPANY"]
    check("reviewed_reserve_has_no_company_blocker", not company and len(b) == 3, b)
    check("reviewed_reserve_is_owner_gated",
          inventory.classify(st, b) == "OWNER_AND_DEPLOY_GATED", inventory.classify(st, b))
    unreviewed = {k: v for k, v in ch.items() if k != "reserve_first_customer"}
    check("unreviewed_reserve_stays_company", any(
        x["gate"] == "outside_launch_scope" and x["clearer"] == "COMPANY"
        for x in inventory._blockers(st, unreviewed, None)))
    no_auth = {**ch, "render_authority": False}
    check("reserve_without_render_authority_stays_company", any(
        x["gate"] == "outside_launch_scope" for x in inventory._blockers(st, no_auth, None)))
    bad_img = {**ch, "imagery": {"usable": False}}
    check("reviewed_reserve_needs_usable_imagery", any(
        x["gate"] == "listing_imagery" and x["clearer"] == "COMPANY"
        for x in inventory._blockers(st, bad_img, None)))
    new_area = {**ch, "reserve_first_customer": ["FIRST_CUSTOMER_BLOCKING: pattern_text: FAIL -- x"]}
    check("reserve_unknown_area_is_company", any(
        x["clearer"] == "COMPANY" for x in inventory._blockers(st, new_area, None)))

    # merge_chain: a drafted listing's search certificate replaces the board's synthetic copy.
    real_ev = inventory.chain_evidence
    ext = ["search certificate (F-005): category UNKNOWN -- none assumed",
           "search certificate (F-004) attributes: no category, so no property schema"]
    try:
        inventory.chain_evidence = lambda db, slug, version, today=None: {
            "listing": {"id": 7, "title": "Drafted", "tags": 13, "price_cad": 7.5},
            "publish_verdict": {"reasons": ext, "search": "REFUSED"}}
        row = {"slug": "x", "source": "launch0", "stage": "SEARCH", "stage_status": "FAIL",
               "next_step": "fix the listing copy the gates refuse", "clearer": "COMPANY",
               "stages": {"PRODUCT": {"evidence": {"version": "1.0.0"}},
                          "SEARCH": {"status": "FAIL"}}}
        pb.merge_chain({"candidates": [row]}, db=None)
    finally:
        inventory.chain_evidence = real_ev
    check("merge_chain_search_from_drafted_listing",
          row["stages"]["SEARCH"]["status"] == "UNKNOWN" and row["clearer"] == "EXTERNAL"
          and row["stages"]["SEARCH"]["evidence"]["source"] == "release chain listing.seo", row)
    check("merge_chain_readiness_external_only",
          row["stages"]["LISTING_READINESS"]["clearer"] == "EXTERNAL", row["stages"])
    if FAILED:
        raise SystemExit(f"{len(FAILED)} failed: {FAILED}")


if __name__ == "__main__":
    main()
