# Learning knowledge contract for A6

The consumer contract follows Main's `I-A6-FROZEN-KNOWLEDGE-CONTRACT`.

* `improve.design_knowledge.applicable(db, scope)` returns a list of verified
  records, each shaped as `{"pin": pin, "statement": statement, "scope": scope}`.
  The currently supported scope is `{"writer_section": "finishing"}`. A store
  failure logs an error and returns an empty list.
* A `pin` contains exactly `rule_id`, `rule_version`, `rule_digest` and
  `evaluation_digest`. The two digests are lowercase SHA-256 strings.
* `improve.design_knowledge.verify_pins(db, pins)` returns the same verified
  record shape, or raises `DesignKnowledgeRefused` for an invalid, stale,
  revoked, unreviewed or unevaluated pin. An unavailable database may raise
  its underlying error. The empty list returns an empty list.
* The currently implemented statement is the closed vocabulary
  `{"rule": "include_finishing_checklist", "parameters": {}}`. It formats
  the original writer's finishing actions as a list without changing their
  words. `cir.writer.write_pattern(..., knowledge_pins=pins, db=db)` applies
  it only after `verify_pins`. On a verification failure the standalone writer
  logs and returns its byte-identical baseline.

Secondary's A6 must freeze pins in CIR provenance, bump the CIR contract to v3
with its pin tests, and pass those pins and the database into the writer. The
certificate, release and quality paths must verify the frozen pins before
accepting a result. The PDF hook must refuse a CIR with unverifiable pins;
otherwise the writer's safe baseline fallback could produce a different release
body than the one certified. CIRs without pins keep their current behavior.
Record a learning action only after a consumer actually changes its decision.

The first evaluator compares the empty incumbent with a single candidate. It
refuses a new evaluation while an approved rule is active; multi-rule and
successor-version comparisons still need implementation. The current frozen
bench2 research inputs are not in the image, so deployed evaluation and pin
verification fail closed until a safe, licensed availability mechanism exists.
No raw reference-derived research content should be added to the image. The
current implementation is not a deployment or production-readiness claim.
