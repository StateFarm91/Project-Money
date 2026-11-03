# Codex A4a continuation — review requested

Source: `opus2/a4a-research-to-concept` at `3dc3e68c490c74d947dd235fd2e39d0f32e7bd5c`. This is a stacked continuation for review, not an integration or deployment.

The A4A independent review found a supposedly square dishcloth whose computed dimensions were about 38 by 11 cm. This continuation gives the dishcloth its own draft geometry and adds an object-size check to certification and the live publication eligibility path. The shared text normalizer is taken byte-for-byte from A1/A2. The generated proposal's palette and stripes now agree with the actual draft. Hot pads are held: the existing acrylic construction has no heat-protection evidence. The computed size is not a physical test.

Evidence now excludes future-dated rows, requires the selected object to appear in at least three listings from at least two named shops, and binds crash-recovered proposals to the recorded census digest, which is also recorded in the source citation alongside the object-specific shop count. A proposal already attached when a worker is interrupted is reconciled to its gap and intake job. Conservative title matching considers compatibility Unicode, punctuation and simple plurals.

Remaining: A4A-3 still prevents a stopped/stalled or previously exhausted gap from opening a new research task when later evidence appears. The crash-after-proposal recovery does not reconstruct a missing `ideation.proposed` audit record. Exact causal auditing and concurrent recovery need independent review. A4a must be tested on a combined tree with A1/A2 and A6; `publish/eligibility.py` and `runtime/pipeline.py` have parallel Codex changes that must both be retained. Existing A4a does not satisfy the entire A4 contract; A4b still needs an authenticated research enrichment producer. No Main integration target was created or altered.

Tests: Python 3.11 locked environment, actual registered workers and file-backed SQLite: `test_w5_a4a_research_to_concept.py` passed 16/16, including certification, a refused legacy strip, obfuscated object names, listing-only claims, changed-evidence recovery, object-specific evidence, future dates and restart reconciliation. `test_w5_concept_intake`, `test_gates`, and retention guard run separately as regression checks; see PR for final exit status. No paid provider, production service, purchase, publication or deployment was used.

## Source-identity and heat-claim continuation

Future official marketplace scans attach the resolved positive shop ID to each listing,
including unchanged listings. The census requires that ID, counts canonical shop IDs, and
excludes duplicate, malformed or ambiguously attributed listing IDs. A catalogue with invalid
or mismatched identities does not prove that previously seen listings disappeared. Legacy
rows without a scan-time binding remain unknown until rescanned. The trust boundary is the
authorized marketplace reader and its shop-scoped catalogue; this is not independent
authentication of a compromised reader. Historical census data is still only an aggregate
and digest, not a reconstructable immutable source snapshot; independent evidence review
remains open.

The certificate and live listing truth check hold known hot-pad, potholder, trivet,
oven-mitt and heat-related claims until a reviewed, content-bound heat-evidence standard
exists. The finite vocabulary does not prove exhaustive detection of all possible claims.
No heat test or product safety approval has been invented.

Continuation verification: Python 3.11 file-backed SQLite runs passed `test_w5_a4a_research_to_concept.py` (29 tests), `test_intel.py` (41 tests), and `test_w4_intelrec_watchlist.py` (20 tests). The watchlist test now supplies its fixed test date to the existing summary clock; this avoids a calendar-dependent failure at the seven-day redecision boundary. These results do not resolve the historical evidence, source trust, heat vocabulary, or cross-branch integration limitations above. PostgreSQL concurrency has not been tested.
