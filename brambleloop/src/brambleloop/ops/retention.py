"""What this system may forget, and the evidence it may never forget.

Nothing pruned anything. Measured 2026-09-24: the audit log grows about 4,700 rows a day, the
job table about 900, the dead-letter queue about 21. At those rates the audit log passes 1.7
million rows within a year, on the Postgres instance that dominates the CA$20/month
infrastructure ceiling, and `/api/status` was already measurably slower than `/health` because
of a query over that table. `JobQueue.purge_dead` existed and was called from nowhere in
`src/`, which is the honest state of retention here: a function with no policy behind it.

**The hard part is not deleting; it is knowing what a gate reads.** Several checks in this
system are *lifetime* counts over `audit_log`, and a lifetime count over a pruned table is a
different claim from the one it says it is making:

* `/api/verify`'s `publication_was_actually_attempted_and_refused` requires
  `store.publish_refused > 0` over all time. Prune those rows and the check that stops
  `nothing_published` passing by absence goes red -- and the fix somebody reaches for is to
  weaken it.
* `gateway.image_bench.spent_to_date` **sums every `image.benchmark` row ever written** to
  enforce the owner's cumulative CA$50 authorisation. That figure is cumulative precisely
  because it was once applied per run and four runs each stayed inside a budget approved once.
  Pruning those rows would rebuild the defect the owner's decision was made to close: a
  ceiling that forgets what it has spent.
* `scale.confidence` counts `continuity.verified` and `store.publish_refused` over all time,
  and `jobs_done >= 100` is one of its gate conditions.
* Two dozen readers ask for the *latest* row of one action. An action whose every row is older
  than the horizon would answer "never happened" instead of "happened, a while ago".

So retention is expressed as three rules rather than one horizon:

1. **Protected actions are never deleted at any age.** Each entry names the reader that makes
   it evidence, because a protected list with no reasons is a list somebody prunes.
2. **The most recent rows of every action survive**, protected or not, so no "latest row"
   reader can be made to answer differently by retention.
3. **Everything else goes after the horizon.**

`KNOWN_READ_ACTIONS` is the other half of that. Every action name the codebase reads by name
is listed with how it is read, and a test scans `src/` and fails when a reader names an action
this module has not heard of. That is the check that matters in a year: the danger is not this
policy, it is the next lifetime aggregate somebody writes over a table that is now pruned.

**Cost rows are never touched.** `cost_entries` is what every ceiling in the company is
computed from and what the ledger reconciles against; it grows at about 1,200 rows a month,
which is not a problem this decade. A retention policy that pruned the money would be a
retention policy that lowered a ceiling.

**A job row that other evidence points at is not deletable.** `audit_log.job_id`,
`cost_entries.job_id` and `spend_reservations.job_id` are real foreign keys, so deleting such a
job either raises or -- worse, on a database with the constraint off -- orphans the evidence.
Those jobs are kept and counted, and in practice that is most of them, which is a finding
rather than a disappointment: the job table cannot be pruned much without deleting audit
evidence, and the audit evidence is the part with a policy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# How long an ordinary audit row is kept. Ninety days covers every window any signal in this
# system reads (the longest is `improve.weekly`'s seven days and the maturity reader's
# thirty), with a wide margin, and it is long enough that a quarter's retrospective can still
# be argued from rows rather than from summaries.
AUDIT_RETENTION_DAYS = 90

# Kept per action whatever their age, so a reader that asks for the most recent row of an
# action cannot be given a different answer by retention. Two rather than one: some readers
# compare the latest against the one before it.
KEEP_PER_ACTION = 2

# Finished jobs. This has to exceed the longest cadence period, and that is arithmetic rather
# than taste: the scheduler's idempotency key is `cadence:<name>:<window>` where the window is
# `now // period`, so deleting the job that holds a key whose window is still open lets the
# cadence run twice in one window. The longest period is `strategy_review` at thirty days, so
# forty-five leaves fifteen days of margin, and a test computes the longest period from
# `worker.CADENCES` and refuses a horizon that does not clear it.
JOB_RETENTION_DAYS = 45

# Kept per job type regardless of age, so `build2.maturity`'s `jobs_seen` -- the set of job
# types this company has ever run -- cannot be narrowed by retention.
KEEP_PER_JOB_TYPE = 3

# `scale.confidence` gates on `jobs_done >= 100` over all time. Retention must not be able to
# make a true claim false, so it stops well above the threshold rather than at it.
JOBS_DONE_FLOOR = 1000

# Dead letters. Only deliberate refusals are ever removed -- see `prune_dead_letters`.
DEAD_LETTER_RETENTION_DAYS = 90

# The OAuth tables, and the decision about each, because "retention does not know about this
# table" is how a credential gets pruned by a policy that was correct when it was written.
#
# `oauth_credentials` is **never touched at any age**. It is the company's only write
# credential; a horizon that reached it would log the company out of its own shop and the
# only repair is the owner in a browser. It is one row.
#
# `oauth_handshakes` is pruned, by `core.oauth_store.prune_handshakes`, and the rule lives
# there rather than here because it is a property of the flow rather than of the horizon: a
# **live** handshake is never deleted (deleting one strands the owner mid-authorization and
# turns a legitimate callback into `state_unknown`), and a spent one is kept for
# `REPLAY_MEMORY_DAYS` so that a replayed callback can still be answered with "this state was
# already used" rather than "no such state". Those are different facts and the operator
# staring at a browser deserves the true one.
NEVER_PRUNED_TABLES = ("oauth_credentials",)


# Every audit action this codebase reads by name, and how it is read. The value is what decides
# whether it can be pruned:
#
#   lifetime_total  a count or sum over *all* rows. Pruning changes the answer. Protected.
#   latest          the most recent row. Rule 2 keeps it whatever the horizon.
#   windowed        read inside a bounded recent window. The horizon is far outside it.
#
# `unknown_read_actions` below reads the action literals out of `src/` -- from equality tests
# and membership tests against the action column -- and a test fails on one that is not here.
# The point is not this list's current contents; it is that the next lifetime aggregate
# somebody writes has to come here and make a decision.
KNOWN_READ_ACTIONS: dict[str, tuple[str, str]] = {
    # W4-FMBATCH1: readers added on that branch without an entry (caught by
    # test_cost_governance_wave2; F-549 scorecard, F-099 trigger, F-661 executive block), and
    # F-723's learning-value report, which reads the newest 200 rows.
    "etsy.credential_health": ("latest", "intel.etsy_scorecard reads the newest reading"),
    "gateway.provider_change": ("windowed", "scale.dependency counts the last 30 days"),
    "plan.strategy_reviewed": ("latest", "command_center.executive reads the newest review"),
    "finance.tool_evaluation": ("lifetime_total",
                                "finance.tool_decisions.check_scope reads an evaluation by id "
                                "for as long as its spend limit exists"),
    "seasonal.childrens_series": ("lifetime_total",
                                  "seasonal.childrens_demand reads the newest series per "
                                  "sub-category (4 rows a month)"),
    "learning_value.expected": ("latest", "finance.learning_value.report: newest 200 rows"),
    "learning_value.realised": ("latest", "finance.learning_value.report: newest 200 rows"),
    "learning_value.refused": ("latest", "finance.learning_value.report: newest 200 rows"),
    # W4-RETENTIONFIX: two readers merged in W4 without an entry. F-399's "repeated failures
    # avoided" counts refusals inside the retrospective window (days); the owner overview
    # reads the newest production self-check only.
    "improve.repeat_refused": ("windowed",
                               "improve.cells.learning_health counts the retrospective "
                               "window (default 7 days)"),
    "verify.completed": ("latest", "command_center.overview reads the newest self-check"),
    # W3 K4/K7: the launch verdict, rollback baseline and stale-artefact sentinel are read as
    # the newest row only (assurance, owner_queue, command_center.tabs, launch.visibility,
    # core.phase readiness evidence), so pruning older rows changes nothing they show.
    "launch.assessed": ("latest", "assurance/owner_queue/cc tabs/launch.visibility/core.phase "
                                  "read the newest verdict"),
    "ops.rollback_baseline": ("latest", "ops.assurance reads the newest baseline"),
    "ops.sentinel": ("latest", "ops.assurance reads the newest sentinel run"),
    # W3 K4: a product's launch plan/hold is read over ALL rows (launch.demand, launch.readiness
    # "uncalendared"): a product planned once stays planned, so pruning would un-plan it.
    "launch.planned": ("lifetime_total", "launch.demand/readiness: ever planned per product"),
    "launch.held": ("lifetime_total", "launch.demand: ever held per product"),
    # K8: the customer workspace lists the newest 50 defect candidates only, so pruning rows
    # older than the horizon cannot change what it shows.
    "support.defect_candidate": ("windowed",
                                 "support.workspace reads the newest 50 rows"),
    # Spend refusals are counted over a bounded window only: finance.spend_report.refusals
    # reads the calendar month and ops.slo.soak_report reads the lights-out soak window
    # (hours), both far inside the retention horizon, so pruning older rows changes neither.
    "spend.refused": ("windowed",
                      "spend_report.refusals reads the calendar month; ops.slo soak window"),
    # Audit ddf9c6e M-3: the soak's "no duplicated external effect" criterion reads reclaims
    # and guard-refused duplicates inside the soak window only (hours).
    "queue.lease_reclaimed": ("windowed", "ops.slo.soak_report reads the soak window"),
    "effect.duplicate_refused": ("windowed", "ops.slo.soak_report reads the soak window"),
    # C-60 (#201): the identity drift series reads 60 days of model-bearing frames and
    # persists its own daily reading, so pruning older rows cannot change the series.
    "assets.model_photography": ("windowed",
                                 "visual.drift_series reads WINDOW_DAYS=60 of frames"),
    # rc1-AUTH D1/D2: owner authority families are sealed hash chains verified from their
    # genesis on every read; pruning any row of one breaks the chain (fail closed, but it
    # would refuse every grant and drop the recorded phase to shadow).
    "owner.phase.transition": ("lifetime_total",
                               "core.phase.chain verifies every transition from genesis"),
    "owner.publication.approved": ("lifetime_total",
                                   "ops.publication_authority grant chain (sealed_chain)"),
    "owner.publication.revoked": ("lifetime_total",
                                  "ops.publication_authority grant chain (sealed_chain)"),
    "owner.publication.rebased": ("lifetime_total",
                                  "ops.publication_authority grant chain (sealed_chain)"),
    "owner.activation.approved": ("lifetime_total",
                                  "ops.activation_authority grant chain (sealed_chain)"),
    "owner.activation.revoked": ("lifetime_total",
                                 "ops.activation_authority grant chain (sealed_chain)"),
    "owner.activation.rebased": ("lifetime_total",
                                 "ops.activation_authority grant chain (sealed_chain)"),
    # rc1-ORD2: the owner's Etsy ledger mapping verification is a sealed chain like the
    # families above; pruning a row breaks it and every ledger fee reverts to unverified.
    "owner.etsy_ledger_mapping.verified": ("lifetime_total",
                                           "finance.reconcile mapping verification chain "
                                           "(sealed_chain)"),
    "owner.etsy_ledger_mapping.revoked": ("lifetime_total",
                                          "finance.reconcile mapping verification chain "
                                          "(sealed_chain)"),
    "owner.etsy_ledger_mapping.rebased": ("lifetime_total",
                                          "finance.reconcile mapping verification chain "
                                          "(sealed_chain)"),
    "store.published": ("lifetime_total",
                        "app.verify_checks (/api/verify) counts all of them, and in a live "
                        "phase reads each one's read-back verdict"),
    # A3-10: in a live phase /api/verify proves every listing on Etsy is covered by an owner
    # publication grant by reading these rows; a pruned one would read as "no grant".
    "store.publish_incomplete": ("lifetime_total",
                                 "app.verify_checks (/api/verify) counts every draft left "
                                 "incomplete on Etsy; pruning one would hide a shop write"),
    "store.execution_revalidated": ("lifetime_total",
                                    "app.verify_checks proves the owner publication grant "
                                    "of every listing on Etsy from these rows"),
    "store.publish_refused": ("lifetime_total",
                              "app.main /api/verify "
                              "`publication_was_actually_attempted_and_refused`, and "
                              "scale.confidence, both count all of them"),
    "continuity.verified": ("lifetime_total",
                            "scale.confidence counts every restore ever proved"),
    "continuity.failed": ("latest", "app.main /api/continuity reads the last proof"),
    "image.benchmark": ("lifetime_total",
                        "gateway.image_bench.spent_to_date sums these to enforce the "
                        "owner's cumulative CA$50 authorisation"),
    "image.reference_probe": ("lifetime_total",
                              "gateway.image_bench.spent_to_date sums these too "
                              "(images.REFERENCE_PROBE_ACTION)"),
    "image.benchmark_blocked": ("latest", "gateway.image_bench.last_run"),
    "image.benchmark_capped": ("latest", "gateway.image_bench.last_run"),
    "model.frozen": ("lifetime_total",
                     "visual.freeze and visual.bible read the canonical identity freeze, "
                     "which is permanent provenance and not re-derivable"),
    "model.replaced": ("lifetime_total",
                       "visual.model_registry.replacements reads every owner-approved "
                       "replacement of the canonical identity: the lineage from one "
                       "version to the next is permanent provenance and not re-derivable"),
    "design.provenance": ("lifetime_total",
                          "ops.artefacts proves what each derived artefact was made from; "
                          "a missing row reads as unproven, which blocks publication"),
    "model.probe": ("latest", "gateway.anthropic.provider_usable reads a successful call"),
    "model.analysis": ("windowed", "gateway.routing reads recent analyses"),
    "ops.health": ("windowed", "runtime.release reads the last sweep; ops.dependencies reads "
                               "the 24h record as the host probe (C-80)"),
    "ops.requeued_for_commit": ("latest", "runtime.pipeline reads the last re-drive"),
    "improve.nightly": ("latest", "runtime.release reads the last nightly"),
    "improve.promoted": ("windowed", "improve.tiers and improve.roi read recent promotions"),
    "assets.built": ("lifetime_total",
                     "runtime.pipeline._certified_pdf_hashes reads the certified PDF hashes "
                     "of a release at publish time and refuses PDF_HASH_DRIFT without them; "
                     "pruning the row would make a certified release unpublishable"),
    "creative.expedition": ("windowed",
                            "creative.audit reads expeditions after its own last cursor, and "
                            "unit_cost counts recent ones; history behind the cursor is spent. "
                            "creative.standard.north_star_cohorts (C-64) also reads them by "
                            "month inside the horizon; older cohorts live on in the daily "
                            "creative.north_star operating_readings rows"),
    "cir.drafted": ("windowed",
                    "creative.standard.north_star_cohorts (CB2-O10) counts the month's drafted "
                    "CIRs as the engineering event behind concept_to_engineering_survival, "
                    "inside the horizon; older cohorts live on in the daily "
                    "creative.north_star operating_readings rows"),
    "store.pdf_hash_verified": ("latest",
                                "commerce.first_hundred reads the latest verification to "
                                "say whether the delivery path is proven"),
    "improve.mine": ("latest", "improve.mine reads its own last run as the watermark"),
    "improve.monitor": ("latest", "improve.monitor reads its own last run as the watermark"),
    "creative.style_learning": ("latest", "the style learner's latest pass is its reading"),
    "finance.governor": ("windowed", "parallelism history covers 7 days; may_claim reads the "
                         "latest governor advice"),
    "improve.league.run": ("windowed", "the league compares on recorded runs in its window"),
    "improve.replay.challenger": ("windowed", "improve.roles counts the challengers the "
                                  "Prompt / Tool Challenger registered in its 90-day window"),
    "creative.white_space": ("latest", "creative.ideation reads the latest white-space "
                             "hypotheses into every tournament/expedition brief"),
    "creative.four_season": ("latest", "creative.ideation reads the latest four-season "
                             "programme row for the current season"),
    "creative.outcome_learning": ("latest", "the outcome learner's latest pass is its reading"),
    "seasonal.harvest": ("latest", "the harvest pass; SeasonHarvest rows hold the history"),
    "creative.tournament": ("lifetime_total",
                            "improve.measure scores product_creativity over every recorded "
                            "tournament (survival rate beside the research kill rate); a "
                            "pruned history would change the capability reading, and "
                            "runtime.release counts them for the weekly cadence proof"),
    "finance.forecast": ("lifetime_total",
                         "improve.measure compares realised revenue against every recorded "
                         "forecast; pruning a forecast would flatter the finance cell"),
    "creative.blinded": ("latest", "runtime.release reads the last blinded run"),
    "creative.blind_review": ("latest", "runtime.release reads the last review"),
    "creative.grid_tournament": ("latest", "the #126 verdict is read from the last run; "
                                 "creative.standard.north_star_cohorts (C-64) reads our grid "
                                 "scores by month inside the horizon, and the daily "
                                 "creative.north_star operating_readings rows keep older "
                                 "cohorts"),
    # CLOSE5: a complete grid-judge panel by content address; reused only inside
    # creative.blinded.PANEL_REUSE_DAYS (56), far inside the 90-day horizon.
    "creative.grid_panel": ("windowed", "creative.blinded.cached_panel reuses a complete "
                            "panel for an identical grid judged within PANEL_REUSE_DAYS"),
    "concept.autopsy": ("windowed", "runtime.pipeline reads recent autopsies"),
    "seasonal.cycle_proof": ("latest", "runtime.release reads the last cycle proof"),
    "etsy.probe": ("latest", "intel.etsy_public reads the last probe"),
    # FB-1 B (F-594): launch.readiness reads the controlled Etsy round trip's ledger, and
    # integrations.etsy_exercise.outstanding_drafts pairs every created draft with its
    # verified removal. Pruning a created row forgets a draft that may still be in the shop;
    # pruning a removed row resurrects one; pruning the finished run erases the only proof.
    "etsy.exercise_finished": ("lifetime_total",
                               "launch.readiness etsy_integration reads whether any full "
                               "round trip against openapi.etsy.com finished ok"),
    "etsy.exercise_draft_created": ("lifetime_total",
                                    "etsy_exercise.outstanding_drafts and launch.readiness "
                                    "pair every created draft with its removal"),
    "etsy.exercise_draft_removed": ("lifetime_total",
                                    "the matching half of every created draft's pair"),
    "owned_surface.probe": ("latest", "the owned_surfaces gate reads the last probe (C-38)"),
    "etsy.oauth_callback": ("latest",
                            "app.main /api/etsy/oauth/start reports the last authorization "
                            "attempt so an operator can tell a flow that was never finished "
                            "from one that failed"),
    # C-69: the moat inventory counts every product photograph ever made (#44), and the
    # teardown QA reads whether a release's deliverable recorded problems (#169).
    "assets.owned_photography": ("lifetime_total",
                                 "brand.moat.evidence counts made product photographs as "
                                 "the photography-language signature's evidence"),
    "assets.deliverable_problems": ("lifetime_total",
                                    "teardown.lab.measured_self_scores reads whether a "
                                    "release's PDF recorded problems (instruction clarity)"),
    # C-80 (#81): the parity verdict resumes the escalation ladder from the rung results the
    # photography job persisted; pruning one would re-run a strategy already tried.
    "creative.escalation_result": ("lifetime_total",
                                   "visual.gallery.escalation_progress reads every rung "
                                   "result for a release to place the next attempt"),
    # C-80 (#54): the launch gate reads each release's search baseline at drafting and the
    # latest rollback rehearsal (aged 3 days) per listed release.
    "listing.query_portfolio": ("lifetime_total",
                                "launch.readiness reads whether every listed release has a "
                                "search-coverage baseline recorded at drafting"),
    "launch.rollback_rehearsed": ("latest", "launch.readiness reads the latest rehearsal per "
                                            "release, aged out after 3 days"),
    "runtime.started": ("windowed",
                        "ops.health.container_starts reads a 24-hour window to tell a "
                        "restart from a deploy"),
    # C-60 (#17): the proof sweep attaches each tester pass and sale once; pruning a row
    # would re-attach it and double-count the trust base.
    # C-75: growth.steer reads the last fortnight's receipts for its steer-once set; the ids
    # live in the receipt, so pruning inside the window would let a job be steered again.
    "growth.steered": ("windowed",
                       "runtime.growth_ops.steer reads 14 days of receipts (job_ids) so a "
                       "steered job is never moved twice"),
    "trust.proof": ("lifetime_total",
                    "runtime.growth_ops.proof_sweep reads every attached proof to attach "
                    "each row once"),
    # C-61: the original-design pipeline.
    "creative.winner_intake": ("lifetime_total",
                               "cir.draft verifies a design's funnel run from its winner "
                               "intake, and regate re-presents held winners from it; a pruned "
                               "intake makes a held winner unengineerable"),
    "concept.judged": ("lifetime_total",
                       "creative.intake reads the vision judgement recorded per design; a "
                       "pruned judgement silently returns a design to unjudged"),
    "radar.skill_gap": ("latest", "creative.ideation reads the latest measured wave gap"),
    "cir.drafted": ("lifetime_total",
                    "intel.mission_runtime reads whether a response's CIR was ever drafted "
                    "to walk #309's pipeline"),
    "seasonal.transformations": ("latest",
                                 "creative.tournament seeds the last run's derived seasonal "
                                 "transformations of the catalogue into its field (#279)"),
    # #194: the weekly cycle reads its own last two rows' unmeasured cells for the streak.
    "improve.weekly": ("windowed",
                       "improve.evolution.metric_revisions reads the last two weekly rows' "
                       "cells_unmeasured (a three-week streak) inside the horizon"),
    # #4: pre-production demand validation. Posts and refusals are re-derivable from the
    # concepts and are re-prepared after the horizon at worst; a platform's interest
    # observation and the validated reading built on it are evidence nothing can re-derive.
    "preproduction.concept_post": ("windowed",
                                   "commerce.preproduction_cycle prepares a post once per "
                                   "concept and channel it finds a row for"),
    "preproduction.post_refused": ("windowed",
                                   "commerce.preproduction_cycle records a refusal once per "
                                   "concept and channel it finds a row for"),
    "preproduction.interest": ("windowed",
                               "commerce.preproduction_cycle re-records a reading only when "
                               "it changed from the last row"),
    "preproduction.interest_observed": ("lifetime_total",
                                        "commerce.preproduction_cycle reads the platform's "
                                        "observation of a concept post; the only evidence of "
                                        "interest and never authored here"),
    "preproduction.validated": ("lifetime_total",
                                "creative.ideation reads validated interest into every "
                                "brief, and the cycle acts on an observation once"),
}

# W4-FMBATCH1 (retention guard, 2026-10-26): actions the code reads through constants,
# imported constants, dict keys, loop tuples and helper parameters, found by the AST scan in
# `ops.read_actions` and invisible to the old literal regex. Each names its reader(s). The
# rules used: a newest-row read filtered by artifact, a per-entity "last N" read, or a window
# longer than the horizon (the seasonal 365-day evidence windows) is `lifetime_total`
# (protected), because the global keep-per-action does not preserve it; an unwindowed count or
# listing is `lifetime_total`; a 30-day or lights-out window is `windowed`; a global newest-row
# read is `latest`. An entry already present above wins (setdefault).
_RESOLVED_READ_ACTIONS: dict[str, tuple[str, str]] = {
    "ai.parked": ("windowed",
        "finance.funding_packet._audit: a bounded window inside the horizon"),
    "asset.rendered": ("windowed",
        "finance.unit_cost.unit_costs: a bounded window inside the horizon"),
    "assets.disclosed_render": ("lifetime_total",
        "publish.disclosed_listing.disclosed_shas, "
        "publish.disclosed_listing.last_asset: read with no window or row limit "
        "(counted or listed over all rows)"),
    "assets.frame_review": ("lifetime_total",
        "runtime.release.frame_review_state: the newest row per artifact, which the "
        "global keep-per-action does not protect"),
    "assets.gallery_frames": ("lifetime_total",
        "visual.launch_imagery.last: the newest row per artifact, which the global "
        "keep-per-action does not protect"),
    "assets.image_provenance": ("lifetime_total",
        "commerce.buyer_trust.gallery_proof_on_file, "
        "runtime.growth_ops.gallery_reading: the newest row per artifact, which the "
        "global keep-per-action does not protect"),
    "assets.listing_images_blocked": ("lifetime_total",
        "publish.release_gates._audit_detail: the newest row per artifact, which the "
        "global keep-per-action does not protect"),
    "assets.listing_images_built": ("lifetime_total",
        "publish.release_gates._audit_detail, seasonal.calendar.milestone_evidence, "
        "seasonal.compression.preparation_started: the seasonal evidence window is 365 "
        "days, longer than the retention horizon"),
    "brand.recognisability_measured": ("lifetime_total",
        "brand.moat.recorded_recognisability: the newest row per artifact, which the "
        "global keep-per-action does not protect"),
    "browser.probe": ("latest",
        "intel.browser.last_probe: the newest row(s) of the action"),
    "cc.check.run": ("lifetime_total",
        "ops.on_demand._last_run: the newest row per artifact, which the global "
        "keep-per-action does not protect"),
    "cir.compiled": ("lifetime_total",
        "seasonal.calendar.milestone_evidence: the seasonal evidence window is 365 "
        "days, longer than the retention horizon"),
    "collection.assembled": ("lifetime_total",
        "seasonal.compression.preparation_started: the seasonal evidence window is 365 "
        "days, longer than the retention horizon"),
    "commerce.orders_ingested": ("latest",
        "commerce.orders_ingest.source_state: the newest row(s) of the action"),
    "concept.scored": ("windowed",
        "finance.unit_cost.unit_costs: a bounded window inside the horizon"),
    "continuity.offsite_write": ("latest",
        "core.offsite.last_archive, core.offsite.prune: the newest row(s) of the action"),
    "creative.benchmark_challenge": ("latest",
        "intel.mission.mission_status: the newest row(s) of the action"),
    "creative.concept_board": ("lifetime_total",
        "products.moment_candidates.board_record: the newest row per artifact, which "
        "the global keep-per-action does not protect"),
    "creative.construction_reading_refused": ("lifetime_total",
        "creative.reference.reading_refused: the newest row per artifact, which the "
        "global keep-per-action does not protect"),
    "creative.defect_fixture": ("lifetime_total",
        "publish.defects.fixtures: read with no window or row limit (counted or listed "
        "over all rows)"),
    "culture.probe": ("lifetime_total",
        "culture.feeds.state: read with no window or row limit (counted or listed over "
        "all rows)"),
    "culture.sweep": ("lifetime_total",
        "seasonal.compression.preparation_started: the seasonal evidence window is 365 "
        "days, longer than the retention horizon"),
    "etsy.quarterly_audit": ("lifetime_total",
        "intel.etsy_ops_report.run: read with no window or row limit (counted or listed "
        "over all rows)"),
    "etsy.shop_observation": ("lifetime_total",
        "commerce.shop_observations.latest: the newest row per artifact, which the "
        "global keep-per-action does not protect"),
    "etsy.shop_resolution_failed": ("latest",
        "integrations.etsy_shop_binding.backoff_remaining: the newest row(s) of the "
        "action"),
    "etsy.shop_resolution_refused": ("latest",
        "integrations.etsy_shop_binding.backoff_remaining: the newest row(s) of the "
        "action"),
    "etsy.shop_resolved": ("latest",
        "integrations.etsy_shop_binding.backoff_remaining: the newest row(s) of the "
        "action"),
    "etsy.webhook_refused": ("lifetime_total",
        "integrations.etsy_webhooks.summary: read with no window or row limit (counted "
        "or listed over all rows)"),
    "experiment.controlled_opened": ("latest",
        "visual.experiment.refuse_if_experiment: the newest row(s) of the action"),
    "experiment.opened": ("lifetime_total",
        "visual.experiment._opened, visual.experiment.open_experiment, "
        "visual.experiment.refuse_if_experiment: read with no window or row limit "
        "(counted or listed over all rows)"),
    "gate.blocked": ("lifetime_total",
        "improve.presale._audits, runtime.pipeline._content_certified_at, "
        "runtime.release._load_examined_cir: read with no window or row limit (counted "
        "or listed over all rows)"),
    "gate.certified": ("lifetime_total",
        "finance.governor.spend_to_progress, finance.unit_cost.unit_costs, "
        "improve.presale._audits, ops.backfill._latest_audit, "
        "runtime.pipeline._content_certified_at, runtime.release._load_examined_cir: "
        "read with no window or row limit (counted or listed over all rows)"),
    "gate.lane_routed": ("lifetime_total",
        "swarm.capacity.product_lane: the newest row per artifact, which the global "
        "keep-per-action does not protect"),
    "gate.listing_copy_refused": ("lifetime_total",
        "improve.presale._audits: read with no window or row limit (counted or listed "
        "over all rows)"),
    "gateway.compat_pack": ("latest",
        "gateway.compat_pack.latest: the newest row(s) of the action"),
    "gateway.contract_eval": ("latest",
        "gateway.fallback_contract._latest: the newest row(s) of the action"),
    "gateway.contract_latency": ("latest",
        "gateway.fallback_contract._latest: the newest row(s) of the action"),
    "gateway.provider_snapshot": ("latest",
        "gateway.provider_watch.watch: the newest row(s) of the action"),
    "image.benchmark_candidate": ("latest",
        "gateway.image_bench.stored_result: the newest row(s) of the action"),
    "image.benchmark_trial": ("latest",
        "gateway.image_bench.stored_trial: the newest row(s) of the action"),
    "image.probe": ("latest",
        "gateway.images.last_probe: the newest row(s) of the action"),
    "improve.presale": ("latest",
        "improve.presale.history: the newest row(s) of the action"),
    "intel.gallery_analysis_blocked": ("latest",
        "intel.findings.gather: the newest row(s) of the action"),
    "intel.panel_discovery_blocked": ("latest",
        "intel.findings.gather: the newest row(s) of the action"),
    "lanes.capacity": ("latest",
        "swarm.capacity.lane_limits: the newest row(s) of the action"),
    "launch.learning_review": ("lifetime_total",
        "launch.demand._recorded_reviews: read with no window or row limit (counted or "
        "listed over all rows)"),
    "launch.reproved": ("latest",
        "ops.assurance.record_reproof: the newest row(s) of the action"),
    "learning.ingested": ("lifetime_total",
        "seasonal.compression.preparation_started: the seasonal evidence window is 365 "
        "days, longer than the retention horizon"),
    "ledger.sale": ("windowed",
        "finance.unit_cost.unit_costs: a bounded window inside the horizon"),
    "listing.classified": ("lifetime_total",
        "runtime.pipeline._release_classification: the newest row per artifact, which "
        "the global keep-per-action does not protect"),
    "listing.drafted": ("lifetime_total",
        "finance.governor.spend_to_progress, finance.unit_cost.unit_costs, "
        "seasonal.compression.preparation_started: the seasonal evidence window is 365 "
        "days, longer than the retention horizon"),
    "listing.lifecycle": ("lifetime_total",
        "commerce.listing_lifecycle.trail: read with no window or row limit (counted or "
        "listed over all rows)"),
    "listing.mobile_qa": ("windowed",
        "finance.governor.spend_to_progress: a bounded window inside the horizon"),
    "listing.parity": ("windowed",
        "finance.governor.spend_to_progress: a bounded window inside the horizon"),
    "listing.seo_blocked": ("lifetime_total",
        "seo.packages._latest_audit: the newest row per artifact, which the global "
        "keep-per-action does not protect"),
    "listing.seo_drafted": ("lifetime_total",
        "finance.governor.spend_to_progress, ops.backfill._latest_audit, "
        "seasonal.compression.preparation_started, seo.packages._latest_audit: the "
        "seasonal evidence window is 365 days, longer than the retention horizon"),
    "marketing.scheduled": ("lifetime_total",
        "seasonal.calendar.milestone_evidence: the seasonal evidence window is 365 "
        "days, longer than the retention horizon"),
    "mjs.reviews_blocked": ("latest",
        "intel.findings.gather: the newest row(s) of the action"),
    "mjs.scan_blocked": ("latest",
        "intel.findings.gather: the newest row(s) of the action"),
    "mjs.scanned": ("lifetime_total",
        "seasonal.compression.preparation_started: the seasonal evidence window is 365 "
        "days, longer than the retention horizon"),
    "model.attempt": ("lifetime_total",
        "gateway.failover.health: the newest row per artifact, which the global "
        "keep-per-action does not protect"),
    "model.reference_pack": ("latest",
        "app.main.tournament_image_refusal, runtime.release._pack_attempts, "
        "runtime.release._pack_on_file, visual.freeze.candidates_on_file: the newest "
        "row(s) of the action"),
    "model.tournament": ("latest",
        "app.main.tournament_image_refusal, runtime.release._tournament_on_file, "
        "visual.bible._declined_finalists: the newest row(s) of the action"),
    "ops.capacity": ("latest",
        "swarm.capacity.latest_mix: the newest row(s) of the action"),
    "ops.disk_sample": ("latest",
        "ops.signal_hygiene.disk_watch: the newest row(s) of the action"),
    "ops.funding_exhausted": ("windowed",
        "finance.funding_packet._audit: a bounded window inside the horizon"),
    "originality.spec_freeze": ("lifetime_total",
        "gates.spec_freeze.frozen: read with no window or row limit (counted or listed "
        "over all rows)"),
    "paid.backlog_run": ("lifetime_total",
        "finance.spend_hygiene.flat_backlogs: the last runs per processor, which the "
        "global keep-per-action does not protect"),
    "paid.floor_outcome": ("lifetime_total",
        "finance.systematic.measure: the newest row per artifact, which the global "
        "keep-per-action does not protect"),
    "photoreal.calibration": ("latest",
        "runtime.release.photoreal_calibration: the newest row(s) of the action"),
    "physical.recorded": ("lifetime_total",
        "seasonal.calendar.milestone_evidence: the seasonal evidence window is 365 "
        "days, longer than the retention horizon"),
    "policy.access_evidence": ("latest",
        "gates.policy_access._previous: the newest row(s) of the action"),
    "policy.page_reading_recorded": ("lifetime_total",
        "gates.platform_policy.page_readings_status: read with no window or row limit "
        "(counted or listed over all rows)"),
    "preproduction.cycle": ("latest",
        "app.main.api_preproduction: the newest row(s) of the action"),
    "pricing.positioned": ("lifetime_total",
        "launch.readiness._launch_package_items, seo.packages._latest_audit: the newest "
        "row per artifact, which the global keep-per-action does not protect"),
    "provenance.class_graduated": ("latest",
        "ops.artefacts.graduated_classes: the newest row(s) of the action"),
    "provider.credential_health": ("lifetime_total",
        "gateway.credentials._previous: the newest row per artifact, which the global "
        "keep-per-action does not protect"),
    "provider.fallback_drill": ("latest",
        "scale.dependency.latest_fallback_drill: the newest row(s) of the action"),
    "publish.document": ("windowed",
        "finance.unit_cost.unit_costs: a bounded window inside the horizon"),
    "quality.tester_plan": ("latest",
        "quality.physical_truth._latest_plan: the newest row(s) of the action"),
    "queue.stale_lease_refused": ("windowed",
        "ops.slo.soak_report: a bounded window inside the horizon"),
    "queue.unfenced_write_refused": ("windowed",
        "ops.slo.soak_report: a bounded window inside the horizon"),
    "radar.scored": ("lifetime_total",
        "seasonal.calendar.milestone_evidence: the seasonal evidence window is 365 "
        "days, longer than the retention horizon"),
    "routing.evidence": ("lifetime_total",
        "gateway.routing._latest_evidence: the newest row per artifact, which the "
        "global keep-per-action does not protect"),
    "routing.override": ("lifetime_total",
        "gateway.routing.effective_route: the newest row per artifact, which the global "
        "keep-per-action does not protect"),
    "seasonal.remerchandising": ("lifetime_total",
        "seasonal.calendar.milestone_evidence: the seasonal evidence window is 365 "
        "days, longer than the retention horizon"),
    "serp.capture_blocked": ("latest",
        "intel.findings.gather: the newest row(s) of the action"),
    "spend.provider_settlement": ("lifetime_total",
        "ops.provider_accounts.last_settlements: the newest row per artifact, which the "
        "global keep-per-action does not protect"),
    "store.activate_incomplete": ("lifetime_total",
        "commerce.listing_lifecycle.trail: read with no window or row limit (counted or "
        "listed over all rows)"),
    "store.activated": ("lifetime_total",
        "commerce.listing_lifecycle.trail: read with no window or row limit (counted or "
        "listed over all rows)"),
    "store.live_observation": ("latest",
        "store_foundation.live_state._observations: the newest row(s) of the action"),
    "store.owner_confirmed": ("latest",
        "store_foundation.shop_sync._confirmations: the newest row(s) of the action"),
    "store.release_gates": ("lifetime_total",
        "improve.presale._audits: read with no window or row limit (counted or listed "
        "over all rows)"),
    "support.answered": ("windowed",
        "finance.unit_cost.unit_costs: a bounded window inside the horizon"),
    "vision.probe": ("latest",
        "gateway.anthropic.last_vision_probe, ops.provider_health.latest_rows, "
        "ops.smoke.probe_recency: the newest row(s) of the action"),
    "visual.carried_portrait_realism": ("latest",
        "visual.photoreal.filed_portrait_verdict: the newest row(s) of the action"),
    "visual.exported_frame_review": ("lifetime_total",
        "visual.exported_review.review_state: the newest row per artifact, which the "
        "global keep-per-action does not protect"),
    "visual.hero_review": ("lifetime_total",
        "visual.hero_review.latest_for: the newest row per artifact, which the global "
        "keep-per-action does not protect"),
    "visual.portrait_repair": ("latest",
        "app.main.api_portrait_repair, runtime.release._repair_on_file: the newest "
        "row(s) of the action"),
    "visual.provider_trial": ("lifetime_total",
        "app.main.api_provider_trial, improve.bootstrap.record_trial_outcomes, "
        "runtime.release._trial_on_file, visual.provider_trial.experiment_spend_cad, "
        "visual.provider_trial.incumbent_evidence: read with no window or row limit "
        "(counted or listed over all rows)"),
    "visual.reference_realism": ("latest",
        "visual.photoreal.filed_verdict: the newest row(s) of the action"),
}

for _action, _decision in _RESOLVED_READ_ACTIONS.items():
    KNOWN_READ_ACTIONS.setdefault(_action, _decision)

# Prefix reads (`AuditLog.action.like("recovery.%")`). A protected prefix protects every
# action that starts with it.
KNOWN_READ_PREFIXES: dict[str, tuple[str, str]] = {
    "recovery.": ("lifetime_total", "ops.recovery reads each request's first recovery row "
                                    "(per artifact) and lists the recent ones"),
    "deploy": ("latest", "autonomy.master_view reads the newest five deploy rows"),
}

# Read sites the AST scan cannot resolve, keyed `path::function`, with what they read and
# where that is classified. Every entry is checked to still exist; an unresolved site not
# listed here makes `unknown_read_actions` fail closed.
UNRESOLVED_READ_SITES: dict[str, str] = {
    "app/command_center/emergency.py::_live_grants": (
        "loops over (publication_authority, activation_authority) modules and reads "
        "mod.APPROVED: owner.publication.approved / owner.activation.approved, both "
        "lifetime_total above"),
    "core/sealed_chain.py::load": (
        "GrantLedger instance actions (approved/revoked/rebased of each sealed chain); every "
        "chain family is classified lifetime_total by its owner above"),
    "core/sealed_chain.py::refusal": (
        "GrantLedger.revoked of each sealed chain; lifetime_total above"),
}

PROTECTED_ACTIONS: frozenset[str] = frozenset(
    action for action, (how, _why) in KNOWN_READ_ACTIONS.items() if how == "lifetime_total")


PROTECTED_PREFIXES: tuple[str, ...] = tuple(
    p for p, (how, _why) in KNOWN_READ_PREFIXES.items() if how == "lifetime_total")


class RetentionRefused(ValueError):
    """A retention run that would have deleted evidence something reads."""


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def unknown_read_actions(source_root=None) -> list[str]:
    """Audit actions the code reads by name that this module has no decision about.

    Read out of the source rather than maintained by hand, because a list somebody has to
    remember to update is wrong exactly when new work lands. The risk this guards is specific:
    somebody adds a lifetime count over `audit_log` in six months and retention, which is
    correct today, silently starts lowering it.

    Resolved with `ops.read_actions` (an AST scan that follows constants, imports, dict keys,
    loop tuples and helper parameters), not a literal regex: 101 actions read through constants
    were invisible to the regex. Unclassified prefixes are returned as `prefix:<p>`, and a read
    site the scan cannot resolve that is not in `UNRESOLVED_READ_SITES` as `unresolved:<site>`
    -- the guard fails closed rather than trusting what it could not read.
    """
    from . import read_actions

    found = read_actions.scan(source_root)
    out = [a for a in found.exact if a not in KNOWN_READ_ACTIONS]
    out += [f"prefix:{p}" for p in found.prefixes if p not in KNOWN_READ_PREFIXES]
    out += [f"unresolved:{u['key']}" for u in found.unresolved
            if u["key"] not in UNRESOLVED_READ_SITES]
    return sorted(set(out))


def _protected(action: str) -> bool:
    return action in PROTECTED_ACTIONS or action.startswith(PROTECTED_PREFIXES)


def audit_plan(db, *, now: datetime | None = None,
               days: int = AUDIT_RETENTION_DAYS,
               keep_per_action: int = KEEP_PER_ACTION) -> dict:
    """Which audit rows are deletable, and what is being kept and why.

    A plan rather than a delete, so the decision can be read before it is taken and so
    `/api/status` can report what retention would do without doing it.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(1, int(days)))
    deletable: list[int] = []
    kept_protected = 0
    kept_recent_per_action = 0
    seen_per_action: dict[str, int] = {}
    with db.session() as s:
        # Newest first, because rule 2 is "the most recent rows of every action survive" and
        # that is only cheap to decide in this order.
        rows = list(s.execute(select(AuditLog.id, AuditLog.action, AuditLog.at)
                             .order_by(desc(AuditLog.id))).all())
    for row_id, action, at in rows:
        # Rule 2 first: the newest rows of every action survive whatever the horizon says,
        # because a "latest row" reader must not be able to get a different answer from
        # retention than from the truth.
        seen = seen_per_action.get(action, 0)
        if seen < max(1, int(keep_per_action)):
            seen_per_action[action] = seen + 1
            kept_recent_per_action += 1
            continue
        if _protected(action):
            kept_protected += 1
            continue
        if (_aware(at) or now) >= cutoff:
            continue
        deletable.append(row_id)
    return {
        "table": "audit_log",
        "total_rows": len(rows),
        "deletable": len(deletable),
        "deletable_ids": deletable,
        "kept_because_protected": kept_protected,
        "kept_because_recent_for_their_action": kept_recent_per_action,
        "horizon_days": int(days),
        "cutoff": cutoff.isoformat(),
        "protected_actions": sorted(PROTECTED_ACTIONS),
        "why_protected": {a: KNOWN_READ_ACTIONS[a][1] for a in sorted(PROTECTED_ACTIONS)},
        "unknown_read_actions": unknown_read_actions(),
        "why": ("a lifetime count over a pruned table is a different claim from the one it "
                "says it is making. These actions are counted or summed over all time by a "
                "gate, so they are kept at any age"),
    }


def job_plan(db, *, now: datetime | None = None, days: int = JOB_RETENTION_DAYS,
             keep_per_type: int = KEEP_PER_JOB_TYPE,
             done_floor: int = JOBS_DONE_FLOOR) -> dict:
    """Which finished jobs are deletable, and every reason the rest are not.

    Four reasons a finished job stays, and they are different faults if any of them is got
    wrong:

    * It is inside the horizon, which must clear the longest cadence period or a cadence's
      idempotency key is freed while its window is still open.
    * Something points at it. `audit_log.job_id`, `cost_entries.job_id` and
      `spend_reservations.job_id` are foreign keys, so deleting the job breaks the evidence or
      orphans it.
    * It is one of the most recent of its job type, so the set of job types this company has
      ever run (`build2.maturity`) cannot be narrowed by retention.
    * Removing it would take the lifetime count of completed jobs below the floor that
      `scale.confidence`'s gate reads. Retention must not be able to make a true claim false.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, CostEntry, Job, JobStatus, SpendReservation

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(1, int(days)))
    with db.session() as s:
        referenced: set[int] = set()
        for table in (AuditLog, CostEntry, SpendReservation):
            referenced.update(
                job_id for (job_id,) in s.execute(
                    select(table.job_id).where(table.job_id.is_not(None))).all())
        rows = list(s.execute(
            select(Job.id, Job.job_type, Job.status, Job.finished_at, Job.created_at)
            .order_by(desc(Job.id))).all())

    done_total = sum(1 for _i, _t, status, _f, _c in rows if status == JobStatus.DONE)
    deletable: list[int] = []
    kept: dict[str, int] = {"referenced": 0, "recent_for_their_type": 0,
                            "inside_horizon": 0, "not_finished": 0,
                            "protecting_the_done_floor": 0}
    seen_per_type: dict[str, int] = {}
    surviving_done = done_total
    for job_id, job_type, status, finished_at, created_at in rows:
        seen = seen_per_type.get(job_type, 0)
        if seen < max(1, int(keep_per_type)):
            seen_per_type[job_type] = seen + 1
            kept["recent_for_their_type"] += 1
            continue
        if status not in (JobStatus.DONE, JobStatus.CANCELLED):
            # A dead letter is not retention's business -- `prune_dead_letters` has its own
            # much stricter rule -- and a pending or running job is live work.
            kept["not_finished"] += 1
            continue
        when = _aware(finished_at) or _aware(created_at) or now
        if when >= cutoff:
            kept["inside_horizon"] += 1
            continue
        if job_id in referenced:
            kept["referenced"] += 1
            continue
        if status == JobStatus.DONE and surviving_done - 1 < int(done_floor):
            kept["protecting_the_done_floor"] += 1
            continue
        if status == JobStatus.DONE:
            surviving_done -= 1
        deletable.append(job_id)

    return {
        "table": "jobs",
        "total_rows": len(rows),
        "done_rows": done_total,
        "deletable": len(deletable),
        "deletable_ids": deletable,
        "kept": kept,
        "surviving_done_rows": surviving_done,
        "done_floor": int(done_floor),
        "horizon_days": int(days),
        "cutoff": cutoff.isoformat(),
        "why_referenced_are_kept": (
            "audit_log.job_id, cost_entries.job_id and spend_reservations.job_id are foreign "
            "keys. Deleting the job breaks the evidence that points at it, and the evidence "
            "is the part with a policy"),
        "why_the_floor_exists": (
            "scale.confidence gates on 100 completed jobs over all time. Retention must not "
            "be able to make a true claim false, so it stops far above the threshold"),
    }


def dead_letter_plan(db, *, now: datetime | None = None,
                     days: int = DEAD_LETTER_RETENTION_DAYS) -> dict:
    """Which dead letters may be removed: the deliberate refusals, and only those.

    "The one thing a dead-letter queue must never do is lose a failure nobody looked at" is
    `purge_dead`'s own rule and this does not soften it. A shadow-mode publication refusal and
    a replica standing aside for the build that can run it are the system working -- there are
    149 of them in production and every one is a refusal -- and after three months they are a
    fact nobody is going to act on. A defect is never pruned at any age.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog, CostEntry, Job, JobStatus, SpendReservation
    from ..queue.durable import deliberate_refusal

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(1, int(days)))
    with db.session() as s:
        referenced: set[int] = set()
        for table in (AuditLog, CostEntry, SpendReservation):
            referenced.update(
                job_id for (job_id,) in s.execute(
                    select(table.job_id).where(table.job_id.is_not(None))).all())
        rows = list(s.execute(
            select(Job.id, Job.job_type, Job.last_error, Job.finished_at, Job.created_at)
            .where(Job.status == JobStatus.DEAD)).all())

    deletable: list[int] = []
    kept = {"is_a_defect": 0, "inside_horizon": 0, "referenced": 0}
    for job_id, job_type, last_error, finished_at, created_at in rows:
        if not deliberate_refusal(job_type, last_error or ""):
            kept["is_a_defect"] += 1
            continue
        when = _aware(finished_at) or _aware(created_at) or now
        if when >= cutoff:
            kept["inside_horizon"] += 1
            continue
        if job_id in referenced:
            kept["referenced"] += 1
            continue
        deletable.append(job_id)
    return {
        "table": "jobs (dead)",
        "total_rows": len(rows),
        "deletable": len(deletable),
        "deletable_ids": deletable,
        "kept": kept,
        "horizon_days": int(days),
        "cutoff": cutoff.isoformat(),
        "classified_by": "queue.durable.deliberate_refusal",
        "why": ("only refusals working correctly are ever removed. A dead letter that is a "
                "defect is work the company still owes and is kept at any age"),
    }


def plan(db, *, now: datetime | None = None) -> dict:
    """Everything retention would do, without doing any of it."""
    now = now or datetime.now(timezone.utc)
    audit = audit_plan(db, now=now)
    jobs = job_plan(db, now=now)
    dead = dead_letter_plan(db, now=now)
    from ..core import oauth_store
    from ..finance import reservations

    return {
        "at": now.isoformat(),
        "audit_log": {k: v for k, v in audit.items() if k != "deletable_ids"},
        "jobs": {k: v for k, v in jobs.items() if k != "deletable_ids"},
        "dead_letters": {k: v for k, v in dead.items() if k != "deletable_ids"},
        "reservations_kept_hours": reservations.KEEP_RELEASED_HOURS,
        "oauth_handshakes": oauth_store.prune_handshakes(db, now=now, dry_run=True),
        "never_touched": {
            "cost_entries": ("every ceiling in the company is computed from these and the "
                             "ledger reconciles against them. About 1,200 rows a month"),
            "ledger": "actual money events, each with an evidence reference",
            "release certificates and pattern versions": "the product's provenance",
            "oauth_credentials": ("the company's only Etsy write credential, sealed. A "
                                  "horizon that reached it would log the company out of its "
                                  "own shop, and the only repair is the owner in a browser"),
        },
        "why_a_plan_exists": (
            "a deletion nobody can read before it happens is a deletion nobody can argue "
            "with afterwards"),
    }


def apply(db, *, now: datetime | None = None, dry_run: bool = False) -> dict:
    """Run the policy. Returns what it removed and everything it declined to remove.

    Refuses outright if the source names an audit action this module has no decision about:
    that means somebody added a reader and retention does not know whether pruning its rows
    changes its answer, which is exactly the state in which a retention run does damage.
    """
    from ..core import oauth_store
    from ..core.models import AuditLog, Job
    from ..finance import reservations

    now = now or datetime.now(timezone.utc)
    unknown = unknown_read_actions()
    if unknown:
        raise RetentionRefused(
            f"these audit actions are read by name in `src/` and this module has no "
            f"retention decision about them: {unknown}. Add each to "
            f"`KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned "
            f"table is a different claim from the one it says it is making, and that is the "
            f"mistake this refusal exists to prevent")

    audit = audit_plan(db, now=now)
    jobs = job_plan(db, now=now)
    dead = dead_letter_plan(db, now=now)
    swept = reservations.sweep(db, now=now)
    # Spent OAuth handshakes, under their own rule: a live one is never deleted at any age,
    # and a spent one is kept long enough that a replay is still answerable as a replay.
    # `oauth_credentials` is not in this function at all and must never be.
    handshakes = oauth_store.prune_handshakes(db, now=now, dry_run=bool(dry_run))

    removed = {"audit_log": 0, "jobs": 0, "dead_letters": 0,
               "oauth_handshakes": handshakes["deletable" if dry_run else "removed"]}
    if not dry_run:
        with db.session() as s:
            for row_id in audit["deletable_ids"]:
                row = s.get(AuditLog, row_id)
                if row is not None:
                    s.delete(row)
                    removed["audit_log"] += 1
            for row_id in list(jobs["deletable_ids"]) + list(dead["deletable_ids"]):
                row = s.get(Job, row_id)
                if row is not None:
                    s.delete(row)
                    removed["jobs" if row_id in set(jobs["deletable_ids"])
                            else "dead_letters"] += 1

    return {
        "at": now.isoformat(),
        "dry_run": bool(dry_run),
        "removed": removed,
        "reservations": swept,
        "oauth_handshakes": handshakes,
        "audit_log": {k: v for k, v in audit.items() if k != "deletable_ids"},
        "jobs": {k: v for k, v in jobs.items() if k != "deletable_ids"},
        "dead_letters": {k: v for k, v in dead.items() if k != "deletable_ids"},
    }


def _replay_memory_days() -> int:
    """Imported lazily: `core.oauth_store` imports the models and this module must stay cheap."""
    from ..core import oauth_store

    return oauth_store.REPLAY_MEMORY_DAYS


def state() -> dict:
    """The policy as a readable object, for the console and for a future session."""
    return {
        "audit_retention_days": AUDIT_RETENTION_DAYS,
        "keep_per_action": KEEP_PER_ACTION,
        "job_retention_days": JOB_RETENTION_DAYS,
        "keep_per_job_type": KEEP_PER_JOB_TYPE,
        "jobs_done_floor": JOBS_DONE_FLOOR,
        "dead_letter_retention_days": DEAD_LETTER_RETENTION_DAYS,
        "protected_actions": sorted(PROTECTED_ACTIONS),
        "known_read_actions": {a: {"read_as": how, "reader": why}
                               for a, (how, why) in sorted(KNOWN_READ_ACTIONS.items())},
        "never_pruned": ["cost_entries", "ledger", "pattern_versions",
                         "dead letters that are defects", *NEVER_PRUNED_TABLES],
        "oauth_handshake_replay_memory_days": _replay_memory_days(),
        "measured_growth_2026_09_24": {"audit_log_per_day": 4700, "jobs_per_day": 900,
                                       "dead_letters_per_day": 21},
        "why": ("at 4,700 audit rows a day nothing pruned anything, and the database is the "
                "main cost driver under the CA$20/month infrastructure ceiling. The horizon "
                "is the easy half; knowing which rows a gate counts over all time is the "
                "half that decides whether retention is safe"),
    }
