# Codex proof lane scope
Base: c0a8f3950eaa09d89631faaafec60de7fd989f1b. Branch codex/final-proof-01.
Requirements: bounded support for F-831..840, F-843, F-867. No closure awards.
Own only src/brambleloop/build2/final_proof.py, tests/test_final_proof.py, codex/master_review/.
Forbidden: existing closure/maturity/reachability/aggregate, registry/matrix/statuses, runtime and shared models, Visual, production.
Existing machinery: closure.proof_of derives static module/test/reachability; aggregate caps using static mapping and filename patterns. Neither establishes a run-bound complete producer/consumer chain. New additive validation is a candidate evidence contract, not duplicate closure authority.
Acceptance: exact qualified UID and head binding; hash-checked local artifacts; complete linked runtime chain; fixture/proxy/stale/consumer deletion refusal; execution-time authorization and independent review; explicit REVIEWABLE rather than certified PASS. Focused zero-cost tests only. No network/API runtime calls.
Handoff: tested small commit and report with remaining runtime integration gap.
