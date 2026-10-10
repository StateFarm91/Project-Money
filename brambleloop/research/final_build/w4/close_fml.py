"""Wave-4 lane FMLEDGER: recover the Final Master launch-critical ledger on the release candidate
line (claude/w4-SHADOWFIX 56d7b38) and close the OPEN rows that merged work now closes.

Same discipline as `close_fm2.py`, whose plan/run-tests/apply machinery this reuses unchanged
(only the row table, tag and result files differ): each entry records what was re-read or
implemented on this branch (`checked`) and the corrected mapping fields. Nothing here certifies
a row -- `aggregate.cap()/completion()` adjudicates the overlay, and a row is written back only
when the overlay computes COMPLETE or GATED (or the entry is an honest `refresh` that stays
OPEN) AND every cited test file was green in this lane's own sequential run
(w4/close_fml_test_results.json) or the cc4a129 full run.

No override is added or changed (overrides.json untouched).

Run (from brambleloop/):
  python3 research/final_build/w4/close_fml.py --plan
  python3 research/final_build/w4/close_fml.py --run-tests tests/x.py ...   # sequential
  python3 research/final_build/w4/close_fml.py --apply
  python3 research/final_build/aggregate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import close_fm2 as base  # noqa: E402

S = "src/brambleloop/"
AW = "tests/test_w4_auto_spend_wiring.py::"
AS = "tests/test_w4_auto_status.py::"
CK = "tests/test_w4_fml_checkpoint_adoption.py::"
NONE = {"kind": "none", "key": "none",
        "detail": "no external/owner/data gate on the remaining step"}
VB1 = {"kind": "owner", "key": "visual_paid_generation",
       "detail": "OWNER_ACTIONS batch 'visual' (Paid image generation): VB-1 P2 LIFESTYLE "
                 "protected composites for the Launch-0 listings (max CA$2.00 of the CA$4.01 "
                 "batch; VISUAL_STATUS ceiling CA$4.76 incl. V0), or the no-API alternative: "
                 "physical sample photographs"}
CONTENTS_PROOF = ("research/final_build/w4/visual/contents_gallery_proof_all_2026-10-07.json "
                  "(a68db01): listing-set certificate valid with CONTENTS certified on "
                  "cloudline-baby-blanket 1.2.0 and market-basket-small/medium/large 1.2.0 "
                  "(the nursery-nesting-baskets Launch-0 sizes, products/launch0.py "
                  "superseded_by), first_customer_imagery PASS; search_evidence_gallery "
                  "missing only LIFESTYLE")

ROWS = {
    "F-514@v0.16": dict(
        checked="W4-AUTO wired the WIRING REQUEST: runtime/worker.py CADENCES "
                "('etsy_openapi_reverify', 'orchestrator', 'etsy.openapi_reverify', weekly) and "
                "agents/registry.py orchestrator allow-list carries 'etsy.openapi_reverify'; "
                "the reverify job is now scheduled, authorised, banded and judged",
        set=dict(coverage="FULL", defect=None, missing_part=None, gate=dict(NONE),
                 next_action="none: weekly etsy.openapi_reverify keeps the surface "
                             "classification current; deploy carries it"),
        tests=[AS + "test_fm2_openapi_reverify_is_scheduled_authorised_banded_and_judged"]),
    "F-098": dict(
        checked="W4-AUTO: runtime/worker.py::park_if_model_down / model_provider_down is "
                "called by Worker.run_once before every handler; a MODEL_JOB_TYPES job is "
                "parked (pending, attempt not counted, audited ai.parked) only on outage "
                "evidence (failover DOWN, open Anthropic funding action, failed probe); an "
                "unprobed provider is UNKNOWN and parks nothing; a non-model job always runs; "
                "a job parked >24h runs and reports its own refusal (no substitute verdict)",
        set=dict(coverage="FULL", defect=None, missing_part=None, maturity="INTEGRATED",
                 producer=S + "runtime/worker.py::park_if_model_down / model_provider_down "
                          "(+ ops/funding.py::note, gateway circuit breaker)",
                 consumer=S + "runtime/worker.py::Worker.run_once (every claimed job)",
                 durable_state="audit_log (ai.parked; ops.funding_exhausted); jobs.status/"
                               "run_after (parked pending); owner_actions",
                 gate=dict(NONE),
                 next_action="none: deploy carries the outage mode (fcb982d does not)"),
        tests=[AW + "test_model_job_parks_while_the_provider_is_down",
               AW + "test_unprobed_provider_is_unknown_not_down_and_parks_nothing",
               AW + "test_non_model_job_is_never_parked",
               AW + "test_failed_probe_and_spent_balance_are_outage_evidence",
               AW + "test_long_parked_job_runs_and_reports_its_own_refusal"]),
    "F-310": dict(
        checked="W4-AUTO: swarm/orchestrate.py::_progress counts new content-distinct durable "
                "audit rows per job type (new_evidence_rows; bookkeeping prefixes job./ai."
                "parked/paid_call.replayed excluded) and folds them into the state sequence, "
                "so identical outputs with a new observation are progress and a restated row "
                "is not; thrash_sweep (ops.thrash, hourly cadence) reads it for backoff",
        set=dict(coverage="FULL", defect=None, missing_part=None, maturity="INTEGRATED",
                 producer=S + "swarm/orchestrate.py::_progress / thrash_sweep",
                 durable_state="jobs.outputs; audit_log (new evidence rows); incidents",
                 gate=dict(NONE),
                 next_action="none: deploy carries the durable-evidence progress measure"),
        tests=[AW + "test_progress_counts_new_evidence_rows_and_ignores_restatements",
               AW + "test_bookkeeping_audits_are_not_evidence"]),
    "F-659": dict(
        checked="W4-AUTO: queue/checkpoints.py (job_checkpoints; fenced to the lease token; "
                "cleared on completion; kept on dead letter) via JobQueue.checkpoint/restore "
                "and JobContext.checkpoint/restore; W4-FMLEDGER adopted it in the longest "
                "handlers: runtime/release.py handle_model_photography (render step "
                "'render:<slug>@<version>') and handle_seasonal_cycle_proof ('cycle_report'), "
                "so a worker that dies after the long step resumes without repeating it. "
                "queue/checkpoints.py is reached on 56d7b38 (module_reachability regenerated "
                "here: load is live via queue/durable.py:JobQueue.restore). Lease fencing/"
                "renewal and the dead-letter classifier are on this head; production fcb982d "
                "predates them (deploy pending, owner production window)",
        set=dict(coverage="FULL", defect=None, missing_part=None, maturity="INTEGRATED",
                 producer=S + "queue/checkpoints.py::save / load (JobQueue.checkpoint/"
                          "restore; JobContext.checkpoint/restore)",
                 consumer=S + "runtime/release.py::handle_model_photography / "
                          "handle_seasonal_cycle_proof (via runtime/worker.py::Worker)",
                 durable_state="job_checkpoints; jobs table: idempotency_key unique, "
                               "lease_expires_at, lease_token, attempts, status DEAD",
                 gate=dict(NONE),
                 next_action="none: deploy carries checkpoints, fencing and renewal"),
        tests=[AW + "test_checkpoint_resumes_after_reclaim_without_repeating_steps",
               AW + "test_stale_worker_cannot_overwrite_a_checkpoint",
               CK + "test_cycle_proof_resumes_from_the_checkpointed_report",
               CK + "test_model_photography_resumes_without_rendering_again",
               CK + "test_a_direct_call_without_a_queued_job_still_runs_the_step"]),
    "F-030": dict(
        checked="W4-VISUAL2 runtime proof " + CONTENTS_PROOF + "; the only gallery job not "
                "produced is LIFESTYLE, which needs paid image generation or photographs",
        set=dict(coverage="PARTIAL", defect=None, gate=dict(VB1),
                 missing_part="LIFESTYLE frames for the Launch-0 listings (owner VB-1 P2 "
                              "paid composites or physical sample photographs); CONTENTS is "
                              "certified on every renderable Launch-0 release",
                 next_action="owner: approve OWNER_ACTIONS 'visual' / visual_paid_generation "
                             "(P2 max CA$2.00) or supply sample photos; then the visual lane "
                             "certifies LIFESTYLE through the supplement path"),
        tests=[]),
    "F-254": dict(
        checked="W4-VISUAL2 runtime proof " + CONTENTS_PROOF + "; eligibility.check_set "
                "passes the certified sets; LIFESTYLE is the only missing gallery job",
        set=dict(coverage="PARTIAL", defect=None, gate=dict(VB1),
                 missing_part="LIFESTYLE frames for the Launch-0 listings (owner VB-1 P2 "
                              "paid composites or physical sample photographs); CONTENTS is "
                              "certified on every renderable Launch-0 release",
                 next_action="owner: approve OWNER_ACTIONS 'visual' / visual_paid_generation "
                             "(P2 max CA$2.00) or supply sample photos; then the visual lane "
                             "certifies LIFESTYLE through the supplement path"),
        tests=[]),
    "F-839": dict(
        refresh=True,
        checked="the recorded defect (closure_matrix basis label stale) no longer holds: the "
                "basis now records the mapping base, every remap SHA and per-row mapped_on, "
                "and module_reachability.json was regenerated on 56d7b38 (W4-FMLEDGER: 654 "
                "modules, 559 reached, none lost vs 8b67414). The final-head audit itself "
                "still needs a frozen candidate",
        set=dict(coverage="PARTIAL", defect=None,
                 missing_part="no frozen launch candidate (F-845), so the function-level "
                              "re-audit has not been run on that exact SHA by an independent "
                              "session",
                 next_action="END-STAGE: freeze the RC (F-845), regenerate reachability on it, "
                             "re-run aggregate.py and the function-level audit there by an "
                             "independent session, commit the verdict"),
        tests=[]),
    "F-848": dict(
        refresh=True,
        checked="scripts/shadow_rehearsal.py exists (boot of the production start command on a "
                "fresh DB, shadow chain to store.publish refusal, simulated past-shadow publish "
                "against tests/fake_etsy, orders/support/ledger) and has run four times "
                "(research/final_build/evidence/shadow_rehearsal_{d85ee19,1dddb9d,3be3096,"
                "ddf9c6e}*.json); the latest (ddf9c6e) is complete:false, blocked by "
                "search_certificate_not_pass, grant_snapshot_refused (taxonomy UNKNOWN) and "
                "past_shadow_publish_blocked",
        set=dict(coverage="PARTIAL", defect=None,
                 missing_part="no complete recorded rehearsal: the latest run (ddf9c6e) stops "
                              "at the owner publication grant (search certificate REFUSED; "
                              "taxonomy UNKNOWN) and none has run on a frozen candidate",
                 next_action="END-STAGE: on the frozen RC run scripts/shadow_rehearsal.py and "
                             "commit the evidence JSON; each not_complete_because item must "
                             "be fixed or carry its recorded gate"),
        tests=[]),
    "F-878": dict(
        refresh=True,
        checked="launch/packet.py::build assembles candidate SHA, recorded suite, phase, every "
                "Launch-0 product's certification/listing/search/price/economics, owner queue, "
                "spend limits, rollback path and activation steps (UNKNOWN never shown as "
                "pass); scripts/launch_packet.py writes it; tests test_fb4_launch / "
                "test_rc1_own_packet. It is not reached from a runtime root and no packet has "
                "been generated for a candidate",
        set=dict(coverage="PARTIAL", defect=None,
                 missing_part="the packet is operator tooling only (launch/packet.py not "
                              "reached from a runtime root) and no packet exists for a frozen "
                              "candidate",
                 next_action="CC lane (WIRING REQUEST): serve packet.build(db, sha=build."
                             "commit()) on an operator-gated GET (security.OPERATOR_GET_ROUTES)"
                             "; END-STAGE: run scripts/launch_packet.py on the frozen RC and "
                             "commit the packet"),
        tests=[]),
}

base.TAG = "w4-FMLEDGER"
base.RESULTS = HERE / "close_fml_test_results.json"
base.REPORT = HERE / "CLOSE_REPORT_FMLEDGER.json"
base.ROWS = ROWS

if __name__ == "__main__":
    cands = base.plan()
    if "--plan" in sys.argv:
        for c in cands:
            print(c["uid"], c["verdict"], c["maturity"], "refresh" if c["refresh"] else "",
                  "| missing tests:", c["missing_tests"], "|", "; ".join(c["reasons"])[:300])
        print(sorted({f for c in cands for f in c["test_files"]}))
    elif "--run-tests" in sys.argv:
        only = [a for a in sys.argv[2:] if a.startswith("tests/")]
        base.run_tests(cands, only or None)
    elif "--apply" in sys.argv:
        base.apply(cands)
