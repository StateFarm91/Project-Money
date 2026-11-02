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
* `freeze_pins(db, cir, pins)` verifies pins and returns a new CIR with the
  closed-vocabulary rule and four pin fields encoded in `primitives_used` as
  `learning_rule:<rule>:<id>:<version>:<rule_digest>:<evaluation_digest>`.
  It refuses missing provenance and refuses to replace existing frozen pins.
  `verify_cir_pins(db, cir)` verifies the encoded pins and their mapping to the
  approved rule; it raises if any reference is forged, stale or malformed.
* The current rule is `include_finishing_checklist` with no parameters. The
  pure `cir.writer.write_pattern(cir, result, ...)` reads the frozen CIR only
  and formats its own finishing actions as a list without changing their words.
  It does not read the database, library or benchmark material. For non-release
  callers, `write_with_verified_knowledge(db, cir, result, ...)` verifies first
  and logs and returns the byte-identical no-knowledge baseline on failure.

Secondary's A6 must freeze pins in CIR provenance and bump the CIR contract to
v3 with its pin tests. If v3 also stores structured pins, it must check that
those pins exactly match the encoded directives. The certificate, release and
quality paths must call `verify_cir_pins` before
accepting a result. The PDF hook must refuse a CIR with unverifiable pins;
otherwise the writer's safe baseline fallback could produce a different release
body than the one certified. CIRs without pins keep their current behavior.
Record a learning action only after a consumer actually changes its decision.

The evaluator compares either the empty incumbent or a verified active rule
with a proposed successor. A repeated rule yields `no_improvement`. Only one
rule can be active; multi-rule baselines and atomic approval of an improved
successor still need implementation. The frozen bench2
inputs are not in the image. A worker can read the pinned `product_truth.json`,
`bench2_manifest.json`, and `product_truth.py` from
`$BRAMBLELOOP_BENCHMARK_LIBRARY/benchmark-2-mini-star-stitch-cardigan/evaluation/`.
Each read uses the quarantined analyst path and current private-analysis
licence; all three files are checked against their frozen hashes. Only the
pinned builder function runs in memory; no benchmark pattern is rendered or
stored by evaluation. Missing, modified or unlicensed evidence blocks
evaluation and pin verification. Provisioning that private volume belongs to
Main's deployment process; no raw reference-derived material is added to the
image. This is not a deployment or production-readiness claim.
