# Learning knowledge contract for A6

The consumer contract follows Main's `I-A6-FROZEN-KNOWLEDGE-CONTRACT`.

* `improve.design_knowledge.applicable(db, scope)` returns a list of verified
  records, each shaped as `{"pin": pin, "statement": statement, "scope": scope}`.
  The scope is `{"writer_section": "finishing"}` with an optional
  `construction_family` of `flat_rows`, `joined_rounds`, or `spiral_rounds`.
  A store failure logs an error and returns an empty list.
* A6 drafting and revision should call `applicable_to_cir(db, cir)`, then
  freeze the returned pins. This selects a rule for the CIR's actual family,
  or its global finishing rule. Never attach a family-scoped pin to a different
  family: both `freeze_pins` and `verify_cir_pins` refuse it.
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
* The registered rules are `include_finishing_checklist` and
  `include_checklist_and_end_check`, both with no parameters. The successor
  requires reviewed evidence from two distinct purchases and adds an original
  instruction to check the security of woven ends. The pure
  `cir.writer.write_pattern(cir, result, ...)` reads the frozen CIR only.
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

The evaluator compares either the empty incumbent or the prior independently
approved rule with a proposed successor against the current corpus. A repeated
rule yields `no_improvement`; an improved successor can replace its incumbent
atomically. One global finishing scope or multiple disjoint construction-family
finishing scopes can be active, but overlapping scopes are refused. A retired
internal guard reserves the legacy global slot while family scopes are active,
so an older single-slot binary cannot silently approve a conflicting global
rule during rollback. Scoped evaluation measures effects on matching held-out
cases and uses unmodified no-knowledge controls outside the scope; it does not
claim those controls reproduce other scopes' current output. A scope with no
matching held-out case is insufficient evidence. Once family scopes are
active, the ordinary daily analysis sweep proposes independently supported
successors for each active family; a repeated sweep does not duplicate them.
A damaged scope guard blocks proposals while reference intake and analysis
recovery continue. A corpus change
blocks production use of the old pin until a current evaluation is approved;
the evaluator can still use the authenticated historical incumbent privately
for comparison. Existing CIRs pinned to a retired version fail verification
and must be handled by Main's release process. The frozen bench2
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

The benchmark reference-image, ad-image and real-outcome comparison stages
remain `UNKNOWN`. The evaluator supports only the two registered finishing
rules; it must refuse any rule that changes construction or imagery until the
corresponding benchmark stages are measured and pass. UNKNOWN is not PASS.
The analyst's `construction.round_joining` cue is proposed reference evidence,
not an approved design rule or permission to change a CIR. It must not be used
as a production directive.

## Stale approval revalidation (pending independent review)

The daily evaluation sweep detects a stale active pin and queues a durable
revalidation. It authenticates the previous approval and its held-out report,
replays the current writer against that approval's original baseline, and
requires current results to preserve the prior approved metrics as well as
improve on the baseline. Source, licence, frozen cases and current corpus must
remain available. Unknown or regressed evidence cannot be reapproved.

Revalidation does not approve anything. An owner with step-up must call the
existing `design_knowledge.review_rule` action with decision `reapprove` and
the completed revalidation audit id. This records a new immutable approval
event; the unchanged rule retains its semantic rule version, while the new
evaluation digest makes its pin distinct. Existing CIR pins remain invalid.
`repin_revalidated_cir(db, cir, pins, new_version=...)` authenticates the old
and new approval, requires the same unchanged rule and a distinct unused release
version, and returns a copy. The caller must persist that as a new version and
run the ordinary certification, quality, release, PDF and visual gates. The
function does not modify or certify an existing release. A6 must not silently
replace pins on an existing release.
