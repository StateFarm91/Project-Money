"""Wave-3 lane K: full mechanical closure of Final Master v1.1 against one head, plus a strict triage.

Two layers, never mixed:

1. MECHANICAL (canonical): `research/final_build/aggregate.py` re-run on this head after
   `module_reachability.json` was regenerated with the FINAL_BUILD_RESUME_MANIFEST §14 snippet.
   Mapping rows are still the 6f9a2f7 / 019ebf0 rows, so this layer cannot see work merged since.
2. W3 TRIAGE (this file): a single-auditor re-check of every launch-critical OPEN row against this
   head. A row is only moved to RESOLVED when code at this head plus an existing test was checked;
   the overlay then re-runs aggregate.cap() + aggregate.completion(), so an unreached producer or a
   missing test still caps it mechanically. RESOLVED is a re-map claim, not certification (F-867):
   the integrator / an independent auditor must accept it before maturity rises in the canonical
   matrix (fold via mapping/remap_<sha7>/ or overrides.json).

Verdict codes used by the triage:
  R  resolved at head (re-map overlay; still subject to cap)
  G  only an owner/data/external gate remains (defect fixed at head)
  O  open, buildable now (cluster id)
  P  release process step on a successor candidate (freeze / suite / rehearsal / audit)
  S  structural: operator/build tooling outside src/ (or a test) can never be "reached";
     TESTED is its ceiling -> needs an integrator decision (override target), not code
  M  likely superseded by later merged work but NOT verified by this lane -> re-map needed

Run from brambleloop/:  PYTHONPATH=src <venv python> research/final_build/w3/closure_w3.py
"""
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
ROOT = FB.parents[1]
sys.path.insert(0, str(FB))
import aggregate as agg  # noqa: E402

HEAD = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                      text=True).stdout.strip()
H7 = HEAD[:7]

# ---------------------------------------------------------------- clusters (OPEN, buildable)
CLUSTERS = {
    "K1": ("Search/listing truth residuals", "M",
           "commerce/search.py, commerce/seo.py, publish/listing_assets.py, publish/eligibility.py, "
           "gates/platform_policy.py, app/main.py (search evidence route)",
           "G (SEO) primary; I for listing schema", "none (Launch-0 search certificate already PASS on merits)"),
    "K2": ("Storefront completion & shop trust gate", "M",
           "brand/storefront.py::check_storefront, commerce/shop_package.py, launch/readiness.py",
           "A (icon/banner assets), B (store UX), C (About/policy copy)",
           "needs A's produced icon/banner asset files + C's copy_v2 About/policies"),
    "K3": ("Listing-level measurement intake (ListingOutcome producer)", "M",
           "creative/style_learning.py::record_outcome, new opsauth POST route, growth/portfolio.py, "
           "growth/experiments.py, commerce/listing_tests.py",
           "G (SEO evidence) minor", "real numbers then data-gated on live_listings"),
    "K4": ("Launch verdict, demand-capture plan & visibility view", "L",
           "launch/readiness.py, commerce/launch.py, scale/leading.py, growth/mix.py, new visibility "
           "provider", "F (CC view), G (search), D (orchestrator)", "K3 for funnel inputs"),
    "K5a": ("Spend attribution & finance reporting residuals", "M",
            "finance/spend_report.py, finance/governor.py, finance/unit_cost.py, ops/provider_accounts.py, "
            "visual/reliability.py, app/main.py spend governance block",
            "none (lane E v1.1 accounting may overlap F-907)", "F-321 tagging (done)"),
    "K5b": ("Paid-call discipline in the gateway/worker", "L",
            "gateway/routing.py, gateway/model_gateway.py, queue/durable.py, swarm/orchestrate.py, "
            "runtime/worker.py, intel/vision.py, finance/spend_policy.py",
            "D owns runtime/worker.py + swarm/orchestrate.py (wiring requests)", "none"),
    "K6": ("Risk-based physical evidence model", "M",
           "new gates/risk_matrix.py, gates/certificate.py, gates/policy.py, launch/readiness.py, "
           "runtime/pipeline.py (re-test owner action)", "none", "none"),
    "K7": ("Ops truth, provenance & owner-surface residuals", "L",
           "ops/artefacts.py, ops/backfill.py, ops/health.py, ops/incident_lifecycle.py, core/models.py "
           "OwnerAction lifecycle, app/main.py dashboard, app/dashboard_truth.py",
           "F (CC/owner surfaces), D (core/db.py migration)", "none"),
    "K8": ("Etsy estate, orders & CX residuals", "L",
           "runtime/etsy_ops.py (census/files), intel/etsy_surfaces.py, commerce/terms.py, "
           "commerce/orders_ingest.py, support/, finance/reconcile.py, app/main.py routes",
           "I (Etsy technical) primary", "real data gated on transactions_r / live_listings"),
    "K9": ("Pattern product-truth residuals (graded/garments; not Launch-0)", "L",
           "cir/model.py, cir/graded.py, cir/stitches.py, publish/pdf.py, gates/policy.py, "
           "gates/originality.py, teardown/reader.py, intel/childrens.py", "none", "none"),
    "K10": ("Learn department residuals", "M", "learn/service.py, learn/api.py, improve/",
            "none (B Learn loops merged v1.1)", "none"),
    "K11": ("Authority & governance model", "L",
            "agents/registry.py, improve/governance.py, queue/durable.py (awaiting-approval state), "
            "new AuthorityPolicy table", "D (agents/registry.py, autonomy/**), F (CC approvals)",
            "none"),
    "K12": ("Visual residuals (model photography path; not Launch-0)", "M",
            "gateway/images.py, visual/identity.py, visual/provider_trial.py, visual/parity.py",
            "H (Visual R&D) primary", "Laura identity rulings (spec/07) bind identity work"),
    "K13": ("Closure/certification tooling in code", "M",
            "build2/closure.py, build2/maturity.py, build2/reachability.py, build2/final_proof.py, "
            "build2/executor.py, launch/readiness.py (LAUNCH_SCOPE)", "K (this lane: research side only)",
            "none"),
    "K14": ("Supply chain, deploy & operator-tooling residuals", "S",
            "Dockerfile, scripts/lock_requirements.py, tests/test_secret_scan.py, ops/registry.py, "
            "run_tests.sh, ops/deploy.sh", "none", "deploy itself is owner production_window"),
    "K15": ("v1.1 wiring: provider reachability + library-only accounting modules", "S",
            "app/command_center/providers.py (importlib indirection), build2/reachability.py, "
            "finance/accounting/{tax_pack,handoff,attribution,forecast,dashboard}.py, autonomy/status.py",
            "F (providers.py) + E (accounting) ; D (autonomy)", "none"),
    "K16": ("Store preview v2 (owner rejected v1)", "L",
            "store_foundation/preview.py + copy", "B (UX), C (copy), A (brand)", "owner Etsy login for live settings"),
}

T = {}  # uid -> dict(v=..., c=cluster, n=note, tests=[...], producer=..., gate={...})


def r(uid, note, tests=(), producer=None):
    T[uid] = {"v": "R", "n": note, "tests": list(tests), "producer": producer}


def g(uid, kind, key, note):
    T[uid] = {"v": "G", "gate": {"kind": kind, "key": key, "detail": note}, "n": note}


def o(uid, cluster, note, size="S"):
    T[uid] = {"v": "O", "c": cluster, "n": note, "size": size}


def p(uid, note):
    T[uid] = {"v": "P", "n": note}


def s(uid, note):
    T[uid] = {"v": "S", "n": note}


def m(uid, note):
    T[uid] = {"v": "M", "n": note}


# ---- R: SATISFIED in partial_classification_376c54b with existing tests, spot-checked at head
for uid, note in [
    ("F-011", "LISTING_TAG_SLOTS_UNUSED blocks <13 tags unless a tag_limitation is recorded"),
    ("F-015", "evidence share over observed phrases only; assumed phrases labelled"),
    ("F-020", "Query.provenance + read_at; tag_provenance persisted"),
    ("F-021", "stuffing blocking in search-copy gate; build_title never repeats a content word"),
    ("F-048", "release_gates.for_publish runs search_gate (category/attributes/copy/tags/description/hero)"),
    ("F-049", "claims_of binds tags, taxonomy_id, attributes"),
    ("F-052", "occasion/holiday property only from pattern facts"),
    ("F-071", "owner_of_the_blocker names the independent tester route"),
    ("F-116", "concept_to_cir derives gauge from declared yarn; certify gauge stage"),
    ("F-128", "ops/health capability signals read recorded probes, not env presence"),
    ("F-131", "configured dependency unproven until its gate probe succeeds"),
    ("F-179", "one owner queue merges OwnerAction rows into gate cards (executor:1432)"),
    ("F-181", "cards that unblock nothing are suppressed"),
    ("F-185", "dashboard dead-letter split 'N expected / M defects'"),
    ("F-202", "header names commit, labelled container start and last clean verify"),
    ("F-215", "structural only: a model frame is unusable unless whole-person morphology passes"),
    ("F-244", "ListingSearchProfile.coverage_matrix persists phrase/family/intent/provenance/field"),
    ("F-245", "stuffed title refused in the search-copy gate"),
    ("F-294", "listing-set certificate binds tags/taxonomy/attributes; stale on edit"),
    ("F-298", "stuffing and recency-only renewal refused"),
    ("F-418", "VACUOUS: no research agent exists; global ceilings bind every model/provider call"),
    ("F-425", "customer-facing claims carry provenance (children's statements)"),
    ("F-430", "VACUOUS: no research agent; every proposal passes improve/governance.check"),
    ("F-445", "children's statements need existing sources; learning signals need citations"),
    ("F-447", "VACUOUS: no research agent; check_owner_authority binds all proposals"),
    ("F-477", "certification independent of drafting; improvement approval refuses the proposer"),
    ("F-547", "seed_owner_queue adopts etsy_surfaces.owner_queue (release.py:3719)"),
    ("F-593", "seed_owner_queue writes the Etsy owner actions into OwnerAction"),
    ("F-663", "one ranked owner queue (executor:1462)"),
    ("F-696", "CUSTOMER_DATA_ROUTES behind operator read refusal (main.py:739); r2-SEC fixes"),
    ("F-749", "originality compares against benchmark 1 AND benchmark 2"),
    ("F-752", "PRODUCT_TRUTH needs deterministic structural_floor PASS"),
    ("F-757", "cir/model.py variant configuration; represented_variant enforced in certificate"),
    ("F-760", "dual pass: structural floor + realism, independent"),
    ("F-765", "construction_overview placed before instructions"),
    ("F-782", "wording shingles / numeric runs / features / construction vs both benchmarks"),
    ("F-783", "provenance required for authored designs; catalogue backfilled"),
    ("F-785", "benchmark/seller image refused as a generation reference before bytes read"),
    ("F-786", "upload route accepts machine-readable licence terms"),
    ("F-787", "observed public listings register pattern_rights=none licences"),
    ("F-790", "material-change aspects + design-difference ledger for competitor-informed designs"),
    ("F-798", "originality-provenance certificate stage"),
    ("F-815", "graph read route + consumers follow edges (fb4-LC)"),
    ("F-821", "byte-level lesson asset provenance vs benchmark corpus (fb4-LC)"),
    ("F-835", "_revalidate_publish_effect at execution (pipeline.py:1586)"),
    ("F-853", "disclosed renders: every pixel from certified CIR/twin, sha256-bound"),
    ("F-854", "glyph per twin cell, raised posts, verifier"),
    ("F-856", "structural PRODUCT_TRUTH independent of realism leg"),
]:
    r(uid, note)
r("F-726", "D-FB-10 durable sealed per-release owner grant (ops/publication_authority) replaces the env flag",
  ["tests/test_fb4_launch.py::test_a_change_in_any_bound_evidence_element_voids_the_grant"])
T["F-757"]["producer"] = "src/brambleloop/publish/listing_set.py::certify"
# ---- R: FB-4 / rc1 / r2 work verified at head
r("F-003", "commerce/ranking_readiness.profile called from launch plan (release.py:1843)",
  ["tests/test_ranking_readiness.py::test_dimensions_are_independent",
   "tests/test_ranking_readiness.py::test_launch_plan_calls_the_profile"],
  "src/brambleloop/commerce/ranking_readiness.py::profile")
r("F-004", "fb4-PUB 98c39f0: search certificate reaches PASS on the merits; no forced verdict",
  ["tests/test_search_hero_publish.py::test_certify_assets_seo_grant_publish_creates_exactly_one_draft_with_no_forced_verdict",
   "tests/test_search_hero_publish.py::test_a_failing_hero_refuses_and_publish_makes_no_request"])
r("F-043", "support/response_watch 24/36/48h watch in support.triage + opsauth owner intake (Etsy has no messages API; see F-556)",
  ["tests/test_fb4_ops.py::test_a_buyer_message_unanswered_for_30_hours_is_an_owner_action_and_an_incident",
   "tests/test_fb4_ops.py::test_the_owner_intake_route_requires_the_operator_credential"],
  "src/brambleloop/support/response_watch.py::watch")
r("F-074", "physical.record accepts a release blocked only on physical evidence (_load_examined_cir)",
  ["tests/test_physical_record_blocked.py::test_a_class_c_release_blocked_on_physical_evidence_takes_its_sample_and_certifies"])
r("F-125", "build2/maturity.disagreements + ops.maturity_disagreements cadence opens incidents",
  ["tests/test_fb4_ops.py::test_a_claim_the_measurement_contradicts_opens_an_incident_until_they_agree",
   "tests/test_fb4_ops.py::test_the_disagreement_check_runs_on_a_cadence_the_orchestrator_may_run"],
  "src/brambleloop/build2/maturity.py::record_disagreements")
r("F-186", "launch_inventory reads the certificate gauge_standard stamp",
  ["tests/test_fin_truth_closure.py::test_a_certified_launch0_product_with_the_current_gauge_standard_is_launch_cleared"])
r("F-188", "creative audit names its cohort; tournament separate",
  ["tests/test_fin_truth_closure.py::test_the_creative_audit_names_its_cohort_and_the_tournament_is_separate"])
r("F-189", "weekly/reinvestment/release read reported_probability (None when UNMEASURED)",
  ["tests/test_fin_truth_closure.py::test_the_weekly_growth_reading_carries_unmeasured_not_the_modelled_bound",
   "tests/test_fin_truth_closure.py::test_reinvestment_makes_no_recommendation_from_an_unmeasured_confidence"])
r("F-236", "storefront SEO check over tagline/About (fb4-STORE)",
  ["tests/test_storefront_fb4.py::test_the_drafted_storefront_passes_its_seo_check",
   "tests/test_storefront_fb4.py::test_a_stuffed_tagline_fails"], "src/brambleloop/brand/storefront.py::check_storefront")
r("F-238", "opening_grid ordering + coherence is a readiness requirement (readiness.py:873)",
  ["tests/test_storefront_fb4.py::test_the_opening_grid_refuses_uncleared_and_legacy_filler",
   "tests/test_storefront_fb4.py::test_readiness_registers_the_new_storefront_requirements"],
  "src/brambleloop/brand/storefront.py::opening_grid")
r("F-324", "break_even UNKNOWN (None) with no tagged creation cost",
  ["tests/test_fin_truth_closure.py::test_break_even_with_no_tagged_creation_cost_is_unknown_not_zero"])
r("F-329", "sustainability verdict computable once product-tagged spend exists (runtime attribution)",
  ["tests/test_fin_truth_closure.py::test_with_runtime_attribution_the_forecast_becomes_computable"])
r("F-541", "one reauth key etsy.auth:reauthorise; readiness never closes an action an open incident names",
  ["tests/test_fb4_ops.py::test_orders_and_publish_share_one_reauthorisation_key_and_incident",
   "tests/test_fb4_ops.py::test_orders_auth_failure_survives_launch_readiness_and_closes_when_cleared"])
r("F-704", "evidence-bound publication preview; UNKNOWN never displays as passing (fb4-LAUNCH); CC approvals approve/decline",
  ["tests/test_fb4_launch.py::test_preview_carries_every_evidence_section_and_unknown_never_displays_as_passing"])
r("F-754", "fail-closed: certify refuses a component gauge differing from the main gauge (per-region support stays F-753)",
  ["tests/test_fb4_lc.py::test_certify_refuses_a_component_gauge_that_differs_from_the_main_gauge"],
  "src/brambleloop/gates/certificate.py::component_gauge_findings")
r("F-874", "first-sale-only KYC asks deferred until a listing exists",
  ["tests/test_fb4_ops.py::test_a_shadow_shop_is_not_asked_for_kyc_until_the_step_before_first_sale"])
for uid, t in [("F-178", "tests/test_final_closure_matrix.py::test_completion_is_computed_per_row_and_the_open_count_is_summarised"),
               ("F-836", "tests/test_final_closure_matrix.py::test_a_fact_only_tests_write_cannot_hold_integrated"),
               ("F-837", "tests/test_final_closure_matrix.py::test_all_proxy_evidence_refuses_integrated_but_one_direct_item_does_not"),
               ("F-847", "tests/test_final_closure_matrix.py::test_launch_scope_classifies_every_row_and_every_reclassification_has_a_reason")]:
    T[uid] = {"v": "R", "n": "implemented in research/final_build/aggregate.py (offline adjudicator; "
              "producer is research tooling, so the cap keeps it below INTEGRATED -> see S)", "tests": [t],
              "producer": None}

# ---- G: defect fixed at head, only a gate remains
g("F-005", "owner", "etsy_api", "certified_payload refuses UNKNOWN taxonomy; real seller taxonomy read needs the Etsy credential gate")
g("F-007", "owner", "etsy_api", "set_listing_property wired (pipeline); node property schema read needs etsy_api")
g("F-081", "owner", "tester_roster", "physical intake fixed (fb4-PUB); Class C needs an independent tester's make")
g("F-118", "owner", "tester_roster", "first_customer gate wired via eligibility; calibration needs a recruited tester")
g("F-160", "owner", "credential_rotation", "rotation card wired into owner queue (fb4-OPS); exposed ANTHROPIC_API_KEY rotation is an owner act")
g("F-243", "owner", "etsy_api", "category/property truth needs the real seller taxonomy snapshot")
g("F-247", "owner", "etsy_api", "taxonomy_id read-back needs the credentialed Etsy run")
g("F-253", "owner", "image_vision", "Launch-0 disclosed renders; parity HERO judgement + competitive blind review (data) remain")
g("F-273", "owner", "transactions_r", "offsite-ads fee set from ledger evidence; real rows need transactions_r")
g("F-321", "data", "live_listings", "spend rows tagged with product_slug at runtime (6d86a8b); maintenance cost needs a live listing")
g("F-461", "owner", "deploy_trigger_config", "guard runs in ops/hooks/pre-push + ops/deploy.sh (ffcb62e); a client hook can be skipped and Railway auto-deploys on push -> server-side enforcement (Railway 'wait for CI' / branch protection) is an owner setting")
g("F-515@v0.16", "owner", "etsy_shop", "daily etsy.shop_snapshot judges getShop; needs a usable shop credential on the deployed build")
g("F-524", "data", "live_listings", "store.publish sends certified images; hero experiments need a live listing")
g("F-540", "owner", "production_window", "credential_health cadence built; rotation proof needs owner-authorised exercise on the deployed build")
g("F-542", "owner", "etsy_api", "store.publish reads back fields/properties/files; the controlled round trip is owner-authorised")
g("F-543", "owner", "publication_authority", "store.activate built with revalidated authority; going live is the owner's grant + phase change")
g("F-556", "external", "no_messages_api", "SLA watch + opsauth owner intake built (fb4-OPS); Etsy exposes no conversation API")
g("F-577", "owner", "payout", "drift monitor built; owner completes Etsy Payments onboarding")
g("F-594", "owner", "etsy_api", "readiness reads exercise evidence; the owner-authorised create/read/delete round trip remains")
g("F-674", "external", "visual_v1_provider_capability", "generative redraw refused (F-852); B+C photoreal stays R&D, not launch-critical under D-FB-7")
g("F-676", "external", "model_bearing_render", "F-852 refusal; protected-region enhancement waits on V2/provider fidelity")
g("F-718", "owner", "production_window", "approved pack fingerprint only in a production audit row (CANON f0c2d12 adds MANIFEST v2; frozen v15 body missing_canonical OA-CANON-1)")
g("F-733", "owner", "production_window", "same as F-718: production approval row / OA-CANON-1")
g("F-734", "external", "model_bearing_render", "no provider renders a model-bearing frame clearing every floor")
g("F-851", "external", "visual_v1_provider_capability", "V1 redraw refused; protected photoreal presentation waits on V2 R&D")

# ---- P: release-process steps (successor candidate on the integrated wave-3 head)
for uid, note in [
    ("F-169", "release-eligible clean-tree suite on the successor head (last: ddf9c6e 6,384/0; head has moved by r2 + CANON)"),
    ("F-177", "fold this triage (and wave-3 work) into mapping/remap_<sha>/ and re-aggregate on the frozen successor"),
    ("F-839", "final-head re-audit by an independent session on the frozen successor"),
    ("F-840", "verdict citing the successor's suite record + final_proof report for the same SHA"),
    ("F-841", "Build 2 freeze is a historical tag (build2-candidate-63f2493); producer None -> process row"),
    ("F-843", "matrix rows still 6f9a2f7-era; canonical fold of the re-map pending (this lane produced the overlay)"),
    ("F-845", "candidates 3be3096 and ddf9c6e were frozen; r2 repairs land on a successor that is not frozen yet"),
    ("F-846", "ddf9c6e audited (0 LB; HIGH/MEDIUM repaired in r2-*); successor freeze + re-audit outstanding"),
    ("F-848", "rehearsal recorded on ddf9c6e; re-run on the successor"),
    ("F-878", "launch/packet.py + scripts/launch_packet.py exist (offline, unreached by design); generate on the successor SHA"),
]:
    p(uid, note)

# ---- S: operator/build tooling or tests as producer; TESTED is the ceiling
for uid in ["F-170", "F-205", "F-332", "F-334", "F-340", "F-345", "F-346", "F-347", "F-348", "F-349",
            "F-344", "F-350"]:
    s(uid, "producer is run_tests.sh / tests/ / repo-root ops/*.py: never reachable from a runtime root; "
           "integrator decision needed (override target TESTED for operator tooling, with reason)")

# ---- M: likely superseded by later merged work, not verified here
m("F-608", "v1.1 lane E reconciliation (F-904) may cover reverse check/payout reconciliation; re-map against finance/accounting")
m("F-609", "v1.1 lane E double-entry ledger (F-903) may supersede LedgerEntry gaps; re-map")
m("F-558", "v1.1 lane E + rc1-ORD order truth may cover; remaining linkage support/cancel/payment unverified; re-map")

# ---- O: open, buildable now
for uid, cl, size, note in [
    ("F-001", "K1", "M", "ranking stage exists (F-003) but search_share still blends match+competition; separate the two stages in score_coverage"),
    ("F-002", "K1", "S", "coverage_matrix persisted; per-listing query->field matrix not served"),
    ("F-013", "K1", "S", "tag diversity lexical only; intent-level/synonym dedup missing"),
    ("F-022", "K1", "S", "strongest differentiator not placed early in title"),
    ("F-028", "K1", "S", "no measured-evidence exception path for hero text restraint (no test cited)"),
    ("F-030", "K1", "M", "per-category gallery frame roles not required"),
    ("F-058", "K1", "M", "no single search evidence dashboard/route"),
    ("F-060", "K1", "S", "may_scale_ads lacks search-specific rungs"),
    ("F-242", "K1", "M", "search guidance not a watched policy source; tag/title limits undated constants"),
    ("F-251", "K1", "S", "ASCII non-English tokens pass language rule"),
    ("F-254", "K1", "S", "gallery job vocabulary lacks alternate angle/construction detail/colour context"),
    ("F-255", "K1", "S", "description lacks value-lead and fibre line"),
    ("F-257", "K1", "S", "permanent-sale refusal lives in unwired commerce/promotion.propose"),
    ("F-291", "K1", "S", "ads thresholds and search guidance not in the watched readings"),
    ("F-233", "K2", "M", "check_storefront still passes on banner/icon BRIEF strings (storefront.py:249) - no asset file"),
    ("F-234", "K2", "S", "shop_package.check_package not a launch requirement"),
    ("F-235", "K2", "S", "check_about not called by the launch gate"),
    ("F-237", "K2", "S", "section vocabulary/occasion coverage not checked"),
    ("F-263", "K2", "S", "trust.shop_complete inherits F-233 brief proxy; add search/attribution prerequisites (ads stay owner-gated)"),
    ("F-279", "K2", "S", "no featured/banner vs launch-set continuity check"),
    ("F-258", "K3", "M", "ListingOutcome has no runtime producer (record_outcome uncalled)"),
    ("F-259", "K3", "S", "same root F-258"),
    ("F-260", "K3", "M", "growth.conclude bypasses listing_tests exposure discipline"),
    ("F-261", "K3", "S", "same root F-258"),
    ("F-282", "K3", "S", "same root F-258"),
    ("F-297", "K3", "M", "no 'measurement proven' gate before ads/steer optimise"),
    ("F-275", "K4", "M", "no per-product demand-capture plan object"),
    ("F-276", "K4", "S", "no Christmas search-readiness checkpoints"),
    ("F-281", "K4", "S", "day 1/3/7 reviews and metric set not predefined"),
    ("F-286", "K4", "S", "no multi-signal launch-success verdict"),
    ("F-287", "K4", "M", "no visibility command-center view"),
    ("F-288", "K4", "M", "recommendations lack listings/mechanism/confidence/rollback schema"),
    ("F-289", "K4", "S", "traffic-source table on visibility view (ingest label fixed)"),
    ("F-300", "K4", "M", "readiness does not answer the six questions; phase change does not require readiness.ready"),
    ("F-070", "K5a", "S", "post-purchase information value per benchmark not tracked"),
    ("F-103", "K5a", "S", "estimate drift not a verify readback"),
    ("F-105", "K5a", "S", "no historical-unknown spend bucket"),
    ("F-106", "K5a", "S", "no incident on ledger vs reported discrepancy (provider API itself owner-gated)"),
    ("F-110", "K5a", "S", "escalation 'what_is_constrained' not collected"),
    ("F-183", "K5a", "S", "spend headline lacks infra/research/ad-authority rows"),
    ("F-184", "K5a", "S", "no binding-ceiling indicator"),
    ("F-303", "K5a", "M", "no closed economic class (one-time vs recurring)"),
    ("F-304", "K5a", "M", "CostEntry lacks listing id/units/observed cost/evidence ref"),
    ("F-305", "K5a", "S", "no tolerance incident on unattributed spend"),
    ("F-319", "K5a", "S", "no cost per requirement/listing advanced"),
    ("F-320", "K5a", "M", "no per-stage per-product creation cost"),
    ("F-322", "K5a", "S", "cost per usable gallery excludes judging spend"),
    ("F-325", "K5a", "S", "observation cadence not a named forecast input"),
    ("F-326", "K5a", "M", "no hourly/tier/repetition/divergence anomaly detectors"),
    ("F-629", "K5a", "S", "credits not separated from cash; dept caps empty (seeding waits on owner figures)"),
    ("F-098", "K5b", "M", "no single degradation plan parking AI-dependent jobs"),
    ("F-109", "K5b", "S", "no test that refusal row survives outer rollback"),
    ("F-306", "K5b", "S", "routing.cached_analysis still has no runtime caller"),
    ("F-307", "K5b", "M", "paid call not linked to durable completion on lease reclaim"),
    ("F-308", "K5b", "S", "no retry-storm financial incident"),
    ("F-309", "K5b", "M", "systematic-failure breaker only for photography paths"),
    ("F-310", "K5b", "S", "'new evidence' inferred from output change only"),
    ("F-311", "K5b", "S", "same root F-306"),
    ("F-312", "K5b", "S", "no per-task deterministic-alternative rule"),
    ("F-313", "K5b", "M", "may_downgrade_for_cost uncalled; routing not evidence-guarded"),
    ("F-314", "K5b", "M", "no cheap-first/deep-on-ambiguity escalation"),
    ("F-315", "K5b", "S", "no input-token control/alert"),
    ("F-316", "K5b", "S", "no per-task schema/max_tokens review test"),
    ("F-317", "K5b", "S", "no general batching isolation policy"),
    ("F-318", "K5b", "S", "backlog processors don't report pending_before"),
    ("F-328", "K5b", "S", "paid calls don't declare the question/evidence produced"),
    ("F-339", "K5b", "M", "reclaimed paid job can re-spend (see F-307)"),
    ("F-472", "K5b", "M", "breaker/rate state per-process, not shared"),
    ("F-474", "K5b", "M", "no intra-handler checkpoints"),
    ("F-659", "K5b", "M", "no long-job checkpoints"),
    ("F-072", "K6", "M", "evidence classes incomplete (teardown/model review/human review/swatch vs full make)"),
    ("F-073", "K6", "M", "risk class manual; no feature-derived minimum-evidence matrix"),
    ("F-078", "K6", "S", "invalidated binding says 'needs a re-test' but no owner/tester action is opened"),
    ("F-080", "K6", "S", "no defined confidence threshold for A/B without full make"),
    ("F-086", "K6", "S", "risk matrix (F-073) not in readiness"),
    ("F-117", "K6", "M", "no general finished-dimension tolerance stage in certify"),
    ("F-115", "K7", "M", "legacy unprovenanced artefacts not graduated/invalidated on re-engineering"),
    ("F-121", "K7", "M", "no claim-to-evidence field on every console card"),
    ("F-122", "K7", "M", "no shared positive-evidence vocabulary/lint"),
    ("F-124", "K7", "S", "no uniform post-deploy postcondition readback"),
    ("F-127", "K7", "M", "same build as F-122"),
    ("F-154", "K7", "M", "no security-controls inventory with functional probes"),
    ("F-161", "K7", "S", "provenance coverage ratio not reported"),
    ("F-162", "K7", "M", "graduation estate-wide, not per class"),
    ("F-167", "K7", "S", "backfill lacks Launch-0 prioritisation/retirement"),
    ("F-168", "K7", "S", "no systemic halt escalation"),
    ("F-173", "K7", "M", "no single owner-gate inventory report incl. Final Master gates"),
    ("F-174", "K7", "S", "no Final Master data-gate inventory surface"),
    ("F-176", "K7", "S", "no single rollback baseline artefact"),
    ("F-180", "K7", "M", "OwnerAction has only boolean done (no lifecycle states)"),
    ("F-195", "K7", "S", "incidents lack remediation owner/last-confirmed on dashboard"),
    ("F-197", "K7", "S", "owner UI does not link tester roster status"),
    ("F-199", "K7", "S", "readiness lacks per-product launch-standard row"),
    ("F-203", "K7", "M", "as-of is query time, not source-row time"),
    ("F-204", "K7", "S", "empty owner block not conditioned on fresh assessment"),
    ("F-337", "K7", "S", "no per-job_type duration watchdog in runtime health"),
    ("F-338", "K7", "S", "no blocked/duplicated diagnosis"),
    ("F-343", "K7", "S", "health vocabulary lacks blocked/observer-waiting"),
    ("F-392", "K7", "S", "incident resolution lacks root_cause/prevention_ref"),
    ("F-623", "K7", "M", "KPI drilldown not uniform (v1.1 CC drill covers money only)"),
    ("F-665", "K7", "M", "no universal evidence envelope beyond dashboard headline"),
    ("F-870", "K7", "S", "approval cards lack why_software_cannot"),
    ("F-250", "K8", "S", "renewal_decision TESTED, not wired to a renewal cadence"),
    ("F-514@v0.16", "K8", "S", "surface inventory not served; no re-verification"),
    ("F-518@v0.15", "K8", "M", "no runtime rollback of a changed live listing field"),
    ("F-535", "K8", "M", "refund/cancel reason codes and repeated-cause trigger missing"),
    ("F-537", "K8", "S", "live shop policy text not checked vs canonical"),
    ("F-544", "K8", "S", "census does not compare files/images"),
    ("F-545", "K8", "M", "no unified listing lifecycle table"),
    ("F-553", "K8", "S", "census lacks properties/files/images/expiry"),
    ("F-559", "K8", "S", "no daily file re-read on live listings"),
    ("F-568", "K8", "S", "no owner route to record a policy violation"),
    ("F-585", "K8", "M", "browser-only shop options registry missing"),
    ("F-592", "K8", "S", "no OAuth posture reading/incident in health"),
    ("F-689", "K8", "M", "no CX workspace joining case/order/review/refund"),
    ("F-362", "K9", "S", "no 'measurements govern fit' statement for multi-size children's garments"),
    ("F-363", "K9", "M", "opening/closure plausibility checks missing"),
    ("F-750", "K9", "M", "no work direction/step order; s76 sleeve-swap test missing"),
    ("F-751", "K9", "M", "star/cluster anchor semantics; no suite star compile test"),
    ("F-753", "K9", "M", "no per-region gauge; apparent gauge not measured in non-render frames"),
    ("F-755", "K9", "M", "all-size benchmark parser only in research/"),
    ("F-756", "K9", "S", "no external schematic CONFLICT/UNKNOWN reconciliation"),
    ("F-761", "K9", "M", "PDF lacks size chart/ease/care completeness checklist"),
    ("F-762", "K9", "M", "no single SizeMatrix incl. yardage"),
    ("F-763", "K9", "S", "fit intent/ease not printed or checked against copy"),
    ("F-768", "K9", "S", "grading recompute only in tests, not at certify"),
    ("F-770", "K9", "S", "unsupported modifications not recorded"),
    ("F-777", "K9", "S", "care/fit/speed claims not traced to evidence"),
    ("F-779", "K9", "S", "SEO/listing-test variants not re-checked against the brief"),
    ("F-784", "K9", "S", "no presentation comparison vs benchmark listing"),
    ("F-792", "K9", "S", "no spec-freeze event before instruction generation"),
    ("F-794", "K9", "S", "graded Provenance drops benchmarks_consulted"),
    ("F-795", "K9", "S", "presentation comparison + separate pre-publish job"),
    ("F-799", "K10", "M", "Learn metrics + improve cell missing"),
    ("F-801", "K10", "S", "finishing/seaming/blocking topics not extracted"),
    ("F-805", "K10", "M", "lesson swatches not compiled/reverse-compiled"),
    ("F-806", "K10", "M", "technique visuals rest on human attestation (proxy)"),
    ("F-826", "K10", "S", "no test for non-gap draft refusal (422)"),
    ("F-497", "K11", "S", "no read-only build-session token scope"),
    ("F-658", "K11", "L", "no persisted cross-department work DAG (lane D orchestrator may partly cover; verify)"),
    ("F-669", "K11", "M", "no eleven-class action authority"),
    ("F-700", "K11", "M", "no single constitution check"),
    ("F-702", "K11", "M", "no awaiting-approval task state blocking only dependants"),
    ("F-703", "K11", "M", "no owner authority-policy object + safe-history"),
    ("F-708", "K11", "S", "credentials/legal/tax/customer-remedy protected-surface tests missing"),
    ("F-721", "K11", "S", "covered by F-702/F-658"),
    ("F-743", "K11", "S", "canonical identity not an explicit protected surface in improve/governance (CANON added visual/canonical guards; add governance refusal test)"),
    ("F-212", "K12", "M", "no per-request proof reference bytes were transmitted"),
    ("F-213", "K12", "S", "no explicit reference-expiry invalidation"),
    ("F-219", "K12", "S", "no human review band for borderline identity"),
    ("F-677", "K12", "M", "model/owned photography truth floor still a vision proxy"),
    ("F-732", "K12", "M", "identity is a vision judgement, not a biometric floor"),
    ("F-877", "K12", "S", "no standard VisualExperiment record"),
    ("F-123", "K13", "M", "vacuity BASELINE not shrunk; producer is a test (structural cap)"),
    ("F-129", "K13", "M", "no live Final Master closure computation"),
    ("F-130", "K13", "S", "parked not split owner/data/external in executor report"),
    ("F-133", "K13", "S", "aggregate does not refuse PARTIAL rows with null missing_part/next_action"),
    ("F-136", "K13", "M", "Final Master completion not a live gate"),
    ("F-382", "K13", "M", "ladder not per Final Master row/improvement"),
    ("F-400", "K13", "M", "readiness not driven by LAUNCH_SCOPE launch-critical set"),
    ("F-831", "K13", "M", "closure does not require full consumer->effect chain in code"),
    ("F-832", "K13", "S", "unreached refusal applied offline only (aggregate)"),
    ("F-833", "K13", "M", "reachability module-level; importlib indirection invisible (see K15)"),
    ("F-834", "K13", "M", "final_proof never run on real packets"),
    ("F-838", "K13", "M", "explicit-park semantics not applied to Final Master matrix in code"),
    ("F-844", "K13", "S", "ladder lacks INTEGRATED/COMMERCIALLY-EVIDENCED rungs"),
    ("F-860", "K13", "S", "no s92 test: visual-blocked lane does not stall unrelated work"),
    ("F-867", "K13", "S", "no independent-review receipt required per COMPLETE row"),
    ("F-879", "K13", "M", "readiness not tied to launch-critical set; mature items not excluded"),
    ("F-135", "K14", "S", "no recorded production lease-recovery drill (run after authorised deploy)"),
    ("F-158", "K14", "S", "lock change record not in release evidence; image never built from lock"),
    ("F-159", "K14", "S", "PDF streams / production logs not scanned"),
    ("F-331", "K14", "S", "run_tests.sh does not self-enrol"),
    ("F-333", "K14", "S", "no attach-to-existing operation"),
    ("F-335", "K14", "S", "run_tests.sh writes no EXIT sentinel"),
    ("F-341", "K14", "S", "late-observer/fenced-out propagation tests missing"),
    ("F-342", "K14", "S", "registry has no work|observer role"),
    ("F-380", "K14", "S", "no deploy evidence audit row (guard wired client-side: F-461)"),
    ("F-381", "K14", "S", "previous Railway deployment id not recorded/rehearsed"),
    ("F-397", "K14", "S", "no test for runtime reads outside package/ArtifactStore"),
    ("F-416", "K14", "S", "base image not digest-pinned; apt unpinned"),
]:
    o(uid, cl, note, size)

# ---------------------------------------------------------------- v1.1 (F-880..F-930)
V11 = {
    "F-880": ("G", {"kind": "owner", "key": "production_window", "detail": "deploy successor + 24h PC-off soak (§95)"}),
    "F-881": ("G", {"kind": "owner", "key": "production_window", "detail": "v1.1 orchestrator not deployed"}),
    "F-895": ("G", {"kind": "owner", "key": "production_window", "detail": "hosted overnight evidence needs deploy"}),
    "F-897": ("G", {"kind": "owner", "key": "casl_notification_authority", "detail": "external channels need CASL review + owner authority"}),
    "F-904": ("G", {"kind": "data", "key": "bank_and_payment_ledger_feed", "detail": "no real bank/Etsy ledger feed"}),
    "F-908": ("G", {"kind": "data", "key": "bank_and_payment_ledger_feed", "detail": "cash UNKNOWN until a feed exists"}),
    "F-923": ("G", {"kind": "owner", "key": "production_window", "detail": "external probe on the hosted service"}),
    "F-924": ("G", {"kind": "data", "key": "hosted_operating_history", "detail": "needs hosted history"}),
    "F-926": ("O", "K16", "owner rejected store preview v1 (wave-3 directive); plus owner Etsy login for live settings"),
    "F-909": ("O", "K15", "finance/accounting/tax_pack.py has no runtime caller (only tests)"),
    "F-916": ("O", "K15", "finance/accounting/handoff.py has no runtime caller (only tests)"),
    "F-907": ("O", "K15", "finance/accounting/attribution.py unreached from any live root"),
    "F-913": ("O", "K15", "finance/accounting/forecast.py reached only via dashboard.py, which is loaded by importlib (unreached by the C-65 rule)"),
    "F-914": ("O", "K15", "finance/accounting/dashboard.py loaded by importlib from CC providers -> unreached by rule"),
    "F-915": ("O", "K15", "drill() in dashboard.py, same importlib indirection"),
    "F-927": ("O", "K15", "autonomy/status.timeline loaded by importlib -> unreached by rule"),
}
V11_DEFAULT = ("C*", None, "TESTED-LOCAL: built, wired, suite-green on ddf9c6e; J audit 0 LB; r2 repairs "
               "not yet re-certified -> COMPLETE pending successor freeze + re-certification")


def main():
    cm = json.loads((FB / "closure_matrix.json").read_text())
    reach = json.loads((FB / "module_reachability.json").read_text())["modules"]
    pc = {x["uid"]: x for x in json.loads(
        (FB / "mapping" / "remap_6f9a2f7" / "partial_classification_376c54b.json").read_text())}
    rows = cm["matrix"]
    lc = [x for x in rows if x["launch_class"] == "LAUNCH-CRITICAL"]
    open_rows = [x for x in lc if x["completion"] == "OPEN"]
    missing = sorted(x["uid"] for x in open_rows if x["uid"] not in T)
    extra = sorted(u for u in T if u not in {x["uid"] for x in open_rows})
    assert not missing, f"untriaged OPEN rows: {missing}"
    assert not extra, f"triage names rows that are not launch-critical OPEN: {extra}"

    out_rows = []
    for row in lc:
        uid = row["uid"]
        rec = {"uid": uid, "id": row["id"], "title": row["title"],
               "mechanical": row["completion"], "mechanical_reasons": row["completion_reasons"],
               "maturity": row["maturity"], "mapped_on": row["mapped_on"][:7]}
        if row["completion"] != "OPEN":
            rec.update(w3=row["completion"], gate=row.get("gate") if row["completion"] == "GATED" else None)
            out_rows.append(rec)
            continue
        t = T[uid]
        rec["triage"] = t["v"]
        rec["note"] = t["n"]
        if t["v"] == "R":
            ov = json.loads(json.dumps(row))
            tests = list(t["tests"])
            for e in (pc.get(uid) or {}).get("evidence") or []:
                if isinstance(e, str) and e.startswith("tests/"):
                    tests.append(e.split()[0])
            ov["tests"] = sorted(set(ov.get("tests") or []) | set(tests))
            if t.get("producer"):
                ov["producer"] = t["producer"]
            if agg.LEVELS.index(ov["maturity_claimed"]) < agg.LEVELS.index("INTEGRATED"):
                ov["maturity"] = "INTEGRATED"
            else:
                ov["maturity"] = ov["maturity_claimed"]
            ov.update(coverage="FULL", defect=None, missing_part=None)
            lvl, notes = agg.cap(ov, reach)
            ov["maturity"] = lvl
            verdict, reasons = agg.completion(ov)
            rec.update(w3=verdict, w3_reasons=reasons, w3_maturity=lvl, cap_notes=notes,
                       tests=[x for x in ov["tests"] if agg._test_exists(x)])
            if verdict != "COMPLETE":
                rec["note"] += " | overlay capped: " + "; ".join(notes)
        elif t["v"] == "G":
            rec.update(w3="GATED", gate=t["gate"])
        elif t["v"] == "O":
            rec.update(w3="OPEN", cluster=t["c"], size=t["size"])
        elif t["v"] == "P":
            rec.update(w3="OPEN", cluster="PROCESS")
        elif t["v"] == "S":
            rec.update(w3="OPEN", cluster="STRUCTURAL")
        elif t["v"] == "M":
            rec.update(w3="OPEN", cluster="REMAP")
        out_rows.append(rec)

    # residual R rows that the cap kept below COMPLETE: give them a home
    for rec in out_rows:
        if rec.get("triage") == "R" and rec["w3"] == "OPEN":
            rec["cluster"] = "STRUCTURAL" if not rec.get("tests") or "research tooling" in rec["note"] \
                else "K13"

    v11reg = json.loads((FB / "master_registry_v1_1.json").read_text())["requirements"]
    v11c = {x["id"]: x for x in json.loads((FB / "v1_1" / "V11_CLOSURE.json").read_text())["rows"]}
    v11_rows = []
    for req in v11reg:
        fid = req["id"]
        spec = V11.get(fid)
        rec = {"id": fid, "title": req["title"], "lanes": v11c[fid]["lanes"],
               "v11_closure_status": v11c[fid]["status"]}
        if spec is None:
            rec.update(w3="COMPLETE-PENDING-RECERT", note=V11_DEFAULT[2])
        elif spec[0] == "G":
            rec.update(w3="GATED", gate=spec[1])
        else:
            rec.update(w3="OPEN", cluster=spec[1], note=spec[2])
        v11_rows.append(rec)

    by_cluster = defaultdict(list)
    for rec in out_rows:
        if rec["w3"] == "OPEN":
            by_cluster[rec.get("cluster")].append(rec["id"])
    for rec in v11_rows:
        if rec["w3"] == "OPEN":
            by_cluster[rec["cluster"]].append(rec["id"])

    summary = {
        "head": HEAD,
        "v1_0": {
            "rows": len(rows),
            "mechanical_completion_all": dict(Counter(x["completion"] for x in rows)),
            "mechanical_launch_critical": dict(Counter(x["completion"] for x in lc)),
            "mechanical_not_launch_critical": dict(Counter(x["completion"] for x in rows
                                                           if x["launch_class"] != "LAUNCH-CRITICAL")),
            "w3_launch_critical": dict(Counter(x["w3"] for x in out_rows)),
            "w3_open_by_kind": dict(Counter(x.get("cluster") if x.get("cluster") in
                                            ("PROCESS", "STRUCTURAL", "REMAP") else "BUILDABLE"
                                            for x in out_rows if x["w3"] == "OPEN")),
            "w3_triage_codes": dict(Counter(x.get("triage") for x in out_rows if x.get("triage"))),
        },
        "v1_1": {"rows": len(v11_rows), "w3": dict(Counter(x["w3"] for x in v11_rows))},
        "clusters": {k: {"title": CLUSTERS[k][0] if k in CLUSTERS else k,
                         "size": CLUSTERS[k][1] if k in CLUSTERS else None,
                         "files": CLUSTERS[k][2] if k in CLUSTERS else None,
                         "overlap": CLUSTERS[k][3] if k in CLUSTERS else None,
                         "dependencies": CLUSTERS[k][4] if k in CLUSTERS else None,
                         "ids": sorted(v)} for k, v in sorted(by_cluster.items())},
        "gated": sorted(({"id": x["id"], **(x.get("gate") or {})} for x in out_rows + v11_rows
                         if x["w3"] == "GATED"), key=lambda g_: (g_.get("kind") or "", g_.get("key") or "", g_["id"])),
    }
    out = {"basis": {"head": HEAD,
                     "reachability": "module_reachability.json regenerated on this head (FINAL_BUILD_RESUME_MANIFEST §14 snippet)",
                     "mechanical": "aggregate.py re-run on this head -> closure_matrix.json / LAUNCH_SCOPE.json",
                     "mapping_rows": "unchanged (019ebf0 + 6f9a2f7 remap); work merged since is invisible to the mechanical layer",
                     "triage": "single-auditor (wave-3 lane K) re-check of every launch-critical OPEN row; R rows re-capped by aggregate.cap; not certification (F-867)",
                     "v1_1": "master_registry_v1_1.json + v1_1/V11_CLOSURE.json re-checked against head reachability"},
           "summary": summary, "launch_critical": out_rows, "v1_1": v11_rows}
    (HERE / f"CLOSURE_{H7}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: summary[k] for k in ("v1_0", "v1_1")}, indent=1))
    for k, v in summary["clusters"].items():
        print(k, len(v["ids"]), v["title"])


if __name__ == "__main__":
    main()
