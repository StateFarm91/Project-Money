# V1 visual correctness continuation

Branch `codex/v1-visual-correctness` starts at Main's
`claude/w5-V1-visual-correctness` `f349c755a17d3792241249a49d0884262c8fd60b`.
The original branch is unchanged. The V1 base tests and `test_w4_visnext` passed
10/10 and 21/21 respectively before this delta; no paid provider was called.

The old `pattern_refs._ribbing` identified ribbing whenever front- and back-post
stitches appeared anywhere, including a real, compiled flat CIR with one front-post
row and one back-post row separated by 19 plain rows. This omitted the prompt's
`ribbing anywhere` prohibition even though there was no repeating rib pattern.
The continuation proves a post-stitch rib only from repeated alternating,
aligned front/back runs on nearby non-fold rows. Other post layouts are UNKNOWN,
not a claim that ribbing is absent. Unknown does not inject a false "no ribbing"
prompt, and the actual craft-fidelity check returns UNKNOWN and holds rather than
passing. Tests exercise real compiled CIRs, the prompt and fidelity comparison,
including isolated posts, separated blocks, shifted columns, fold rows, sparse
loop-only stitches and the existing genuinely ribbed scarf. Python 3.11: V1 15/15,
targeted fidelity UNKNOWN/FAIL checks, FLUX texture 9/9 and rim negative 2/2 passed.
The full fidelity suite was interrupted for a reviewer-requested fix; it has not
been claimed as passed. The reference version advances to
`pattern-refs/3.1.2` so changed references are identifiable. This conservative
reader does not prove other valid ribbing geometries; independent review is
required. No image or physical fidelity claim is established.

The parent V1 handoff already says its Cloudline experiment definition changed and
requires fresh owner authorization. This continuation does not authorize it.
Independent review, integration and production verification are still required.

Review follow-up: a ribbed design cannot PASS craft fidelity when ribbing is
reported absent (FAIL) or unclear (UNKNOWN). Component-level evidence is now
aggregated conservatively: mixed/unknown pieces remain UNKNOWN and cannot cause
a global "no ribbing" claim. Real-CIR small-ribbed-component and actual blind
reading tests pass. V1 focused suite: 17/17 on Python 3.11. Independent review
and the full fidelity regression remain open; this checkpoint is not accepted.

The expected-ribbing check also leaves an obscured/unclear fabric view UNKNOWN:
only a clear reading can establish that required ribbing is absent. Independent
scoped review confirmed this distinction; the V1 suite passed 17/17 afterwards.

## Multi-piece and impossible-repair follow-up: BLOCKED for integration

Independent review identified whole-product prompt claims incorrectly inferred
from the largest component. The continuation directs multi-piece shape, edge and
colour to each certified reference, suppresses global component-specific
prohibitions, and qualifies motif prohibitions to forbid only motifs absent from
the pattern. Real kneeler, garland, tea-cosy and ring-pillow CIRs are covered.
Structural reference failures now hold even with an unrelated routable failure
code; a durable SQLite fake-generator test shows only one lifestyle attempt.
No-structural routable repair coverage is retained. Existing scarf ribbed edges
are no longer forbidden. Reference and prompt builder versions advance to
`pattern-refs/3.1.3` and `flux3-prompt-builder/2.1.1`; do not repin or authorize
Cloudline's owner-controlled experiment without the owner.

The binary edge reader cannot distinguish Cloudline's legitimate end bands
from invented edging. This candidate returns UNKNOWN rather than a false
FAIL or PASS, with no publisher bypass. Consequently the unchanged existing
`test_positive_flat_lays_pass_under_photographic_perturbation` currently fails
for Cloudline: its former PASS assumption requires richer edge evidence. Do not
weaken that assertion. Per-piece edging is likewise held UNKNOWN when not proved.
V1 focused suite 23/23, texture 9/9, rim negative 2/2 and FLUX generator 9/9
passed in Python 3.11, all with fake providers. The full earlier fidelity suite
passed 22/22 on 85ff2b8 before this delta, not on this new candidate. Independent
review, per-edge evidence, full regression and integration are still required.

## Richer edge evidence (review required)

A single-component design with declared end bands can now pass craft fidelity
when a blind, image-only reading explicitly identifies ends-only treatment and
all expected band checks contain actual measured rows and pass. A synthetic
Cloudline anchor exercises that path; an added-border image remains non-PASS.
Missing/unclear readings, side/surrounding borders, mixed components and a
separately declared trim remain UNKNOWN. A clear absence of separately declared
edging fails; an obscured view remains UNKNOWN. These are synthetic/fake-judge
tests, not a physical observation or certification.

The legacy positive test still uses a fake reader without the new edge-placement
field and therefore remains UNKNOWN and fails its unchanged PASS assertion.
Updating its fixture to express independently observable evidence requires
review; the assertion was not removed or weakened. V1 focused suite 28/28 passes.
The blind-reading contract changes, so review provider output compatibility and
experiment authorization before integration. The branch remains DO NOT INTEGRATE.
