# G runtime independent review (read-only)

Source inspection: c93b136dee307158ec52d5ebd87bcec2b0a7a1c2. Tiny synthetic DB reproduction rerun at unchanged-before/after1ac185ea47485efd865b568e6e15f508cc35a9cc after coordinator advanced integration. gates/originality.py unchanged between those heads. No production calls, paid providers or source edits. Report fb1_G.json read completely; its own PARTIAL qualifications are accurate and must not disappear in closure counts.

## Proven defect G-R1: durable wording evidence omitted by certification consumer
Severity: high evidence-integrity defect (F-831/834/795/798). `originality.record_fingerprint(db,...)` persists BenchmarkFingerprintRecord. `similarity_review(cir,pattern_text,db=db)` reads those rows and correctly escalates known wording overlap. However certificate.certify -> originality.release_findings -> similarity_findings -> similarity_review passes NO db. Known durable evidence is therefore absent from the actual certificate decision. `runtime/pipeline.handle_certify` has ctx.db but cannot supply it through this interface. `store.publish -> _release_gates -> publish/release_gates.for_publish` recomputes staleness/search/standards/eligibility; no direct originality DB review is present there either.

Observed minimal adversarial result (synthetic, zero live effects):
- Build fixtures.good_mosaic_panel; compile and write its actual pattern text.
- In a temporary SQLite Database, create_all; originality.record_fingerprint(db,'synthetic-review-source',text=that_text).
- Dispose first connection; reopen same DB; stored fingerprint count1.
- similarity_review(cir,pattern_text=text,db=reopened): escalate=true, dimensions=['wording'].
- certify(cir): granted=true, SIMILARITY findings=[] against the SAME CIR.
This conclusively proves a false-PASS of the certificate originality subgate relative to evidence already available to its DB-aware instrument. It does not prove a real competitor copy exists or that any product can bypass ALL other publication gates. First attempt already reproduced this but had a Windows open-SQLite cleanup error; disposed-engine rerun exited0 and preserved identical head before/after.

Recommended minimal repair (narrow, objective): thread optional db and ledger inputs through certificate.certify -> originality.release_findings/provenance_findings/similarity_findings. Runtime handle_certify must supply ctx.db; use ledger_from_db for the current concept, fingerprints_from_db for current corpus. Publication execution must re-evaluate new benchmark evidence or require a current content+corpus-bound independent review; a certificate predating a new fingerprint cannot silently remain sufficient. Proof: above fixture must refuse at handle_certify, then add fingerprint AFTER prior certification and show protected publication refuses without network mutation. Keep unknown wording explicitly unknown; no blanket claim that keyword similarity establishes legal originality.

Disjoint first scope: gates/originality.py signatures/DB read and NEW tests/test_originality_runtime.py. Required coordinated minimal call-site edits: gates/certificate.py originality invocation and runtime/pipeline.py handle_certify; these overlap coordinator/C2 and must be integrator owned. Follow-on publication consumer in publish/release_gates.py is shared with A/B and needs coordinated ownership. No source edits made in this review.

## G-R2: real raw-geometry producer lacks provenance (proven source contract defect)
`pipeline.handle_draft` fallback builds Concept -> concept_to_cir -> enqueues cir.compile. concept_to_cir returns CIR without provenance. G's certify now correctly emits PROVENANCE_MISSING. This is fail-closed loss of runtime capability, not false PASS. G report explicitly notes it. Repair: producer stamp must be derived from actual approved concept/design inputs, not generic labels asserting independence. Test handler fallback through compile/certify with actual queued inputs; independently verify source/brief digest corresponds to produced design.

## G-R3: brief benchmark lineage drops (proven static mismatch; runtime exploit untested)
preengineering.benchmarks_consulted unions brief['benchmarks_consulted'] and Concept.provenance benchmark lineage; its durable ledger producer records that. prototype._provenance only carries the latter string. A benchmark known exclusively in brief is not carried to CIR and certificate can skip required ledger checks. No full worker exploit run, so classify runtime impact unproven pending focused adversarial path. Test: brief-only benchmark plus passing material ledger -> draft -> confirm CIRconsulted contains source; mutate/remove ledger before certify -> refusal. Avoid auto-stamping empty benchmarks on informed concepts.

## Explicit unknowns
Similarity thresholds remain heuristic. G report says keyword/magnitude material-change classification is defeatable, unregistered neutral-name competitor images are undetectable, no independent similarity job yet, and licence use/reader DB integration incomplete. Those are not proven fixed by28unit tests or by metadata existence. Paid/source PDF reads are not needed to fix the producer/consumer contracts. No requirement status changed; no claim of certification.
