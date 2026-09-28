# Learn launch engineering handoff

Base: c0a8f3950eaa09d89631faaafec60de7fd989f1b. Branch: codex/final-learn-01.
Scope: launch architecture subset of F-799,801,804,805,806,808,815,821,822,826,828. No requirement maturity/status promotion.

## Implemented path
Hourly learn_gap_scan -> dedicated zero-spend learn agent -> learn.scan handler -> existing PatternVersion CIR and SupportCase sources -> durable LearnNode/LearnEdge plus deduplicated LearnGap work queue -> authenticated queue/editor API -> canonical Lesson digest -> separate authenticated reviewer -> explicit human attestation for all seven quality dimensions -> current-revision approval checked again by public lesson read and contextual PDF-link consumer.
Graph carries exact CIR digest/version and support IDs without copying customer prose. Repeated scans/restarts retain gaps without duplicating them. No-source run WATCHes and generates nothing. Missing reviews, UNKNOWN visual truth, changed spec, stale requested revision and untrusted URL/slug refuse.
New tables registered through existing Database.create_all metadata/additive mechanism; no old schema/data rewrite.

## Integrator action
Mount router after app/db declarations in app/main.py:
`from ..learn.api import router as learn_router`
`app.include_router(learn_router(db))`
This shared file remains coordinator owned. Handler/cadence/agent/DB/PDF narrow wiring is in this branch already.
Use BOTH implementation commits after scope083d3ca: initial0bb3436 has PDF forwarding defect corrected by follow-on. Do not integrate initial slice alone.

## Operator-facing configuration (names only; no credentials created)
Existing BRAMBLELOOP_OPS_TOKEN authenticates queue/draft authoring. Server author identity is learn-operator-editor, not caller-selected.
Distinct BRAMBLELOOP_LEARN_REVIEW_TOKEN and BRAMBLELOOP_LEARN_REVIEWER_ID authenticate reviewer; missing config, same credential or same identity refuse. Review class must be human_attestation; result explicitly says automated_truth_proof=false.
Optional BRAMBLELOOP_LEARN_PUBLIC_ORIGIN must be an operator-owned HTTPS origin; without it PDFs receive no links. No deployed Learn site is asserted.

## Evidence
13 focused tests pass on follow-on source: production Worker dispatch, source graph/gap and restart/idempotence, WATCH, incorrect arithmetic/provenance refusal, UNKNOWN visual review refusal, self-review refusal, stale/direct-tampered canonical spec refusal, source PII exclusion, safe URLs, real PDF layout threading, and authenticated editor/reviewer/approved-reader flow with identity separation.
Fixtures simulate human review and are labelled test-only. They prove workflow refusal/enforcement, not lesson correctness or a real review.
One broad test_cert_wiring attempt finished 11/16 in181s; INVALID_SOURCE_CHANGED because new API/service files changed during the run (restored briefly afterward). This is not exact-head certification evidence. It did expose an actual PDF lesson_links NameError, now fixed and covered by the actual PDF test. Other observed failures included Windows file-lock continuity and socket-denied API harness. Coordinator schedules clean final integrated wiring/reachability and affected suites. No broad suite claimed PASS.

## Remaining limitations / honest status
All assigned Master rows remain engineering PARTIAL, not certified. F-801 core scanning/queue exists but no per-row complete claim. F-799 has first-class scheduled source gap work and durable state, not complete experiments/calendar/metrics/RUN-GROW-IMPROVE. F-804 canonical teaching spec exists, not every derivative format. F-805 count/terminology checks plus human attestation do not automatically validate all instruction semantics. F-806 visual correctness is required review evidence; no independent diagram pixel instrument or byte-fetch proof. F-808 app and PDF interfaces exist; app mount/integrated tests and deployed owned origin remain. F-815 graph covers available explicit CIR topics, patterns, lessons and support; broader video/query relations absent. F-821 rights/digests are declarations attested by reviewer, not external licence verification. F-822 is a real authenticated human review workflow, not an automated judge. F-826 rejects drafts without source-backed gaps and WATCHes empty sources; content value still needs review. F-828 technical/CX inputs reach Learn; Marketing/Finance integrations remain absent. Support grouping uses specialist labels, not inferred topic clustering. No lessons fabricated or published; no paid calls.

## Next actions
Integrate full branch into coordinator branch, mount router, run focused test_learn_launch plus affected PDF/runtime suites on final clean tree. Independent reviewer audit should particularly challenge reviewer credential/identity boundary, stale canonical mutations, and protected PDF consumption. Do not mark unbuilt curriculum/automatic QA complete.

## Follow-on PDF publish contract review
On3ba5359, assets.build passes pdf_help_links into renderer; publish-side re-render does not. With configured origin plus an approved lesson this reliably blocks at existing PDF_HASH_DRIFT. No incorrect document is uploaded, but valid publication cannot complete. AB worker owns narrow fix in _publish_and_read_back after coordinator integration.
Added tests/test_learn_publish_contract.py: explicit static two-call-site resolver assertion (fails before fix), real deterministic PDF bytes through check_pdf_hashes (passes), and omitted/current/stale revision public API semantics (passes). Local result2/3, sole expected failure is missing publish resolver. This test commit is adversarial evidence, not a repair candidate or green suite claim. Parent/AB worker reruns after merge. No runtime source modified in this follow-on.
