# V1 visual anchor binding continuation — review required

`codex/v1-anchor-binding` continues `codex/v1-visual-correctness` at
`d125a3ba356fbe360bdc99a05287b06cc29ff360`. The source branch is unchanged.

The lifestyle anchor lookup previously allowed two distinct full release hashes
to match on only their first 12 characters. Its fallback lookup could also select
an anchor for a different product or version sharing the listing. A lifestyle
verdict could therefore be bound to an image from a different design. The lookup
now requires matching full SHA-256 release IDs, matching slug and version, and
checks that the retrieved bytes hash to the recorded anchor ID. Direct lifestyle
verification also rejects abbreviated or unequal release IDs. Existing shortened
anchor IDs are held pending recovery of the full identity; this is an intentional
availability consequence and requires integration review.

These checks do not authenticate a stored PASS verdict, independently prove
physical fidelity or protect evidence against concurrent modification. Selection
filters product, version and release before ranking so mismatched candidates do
not hide an otherwise eligible anchor. A matching candidate with missing or
corrupt bytes can still hide another usable candidate (a conservative hold).
Generation and re-verification propagate the actual run key and selection no
longer falls back to a different controlled run. Unscoped owner-submitted
anchors remain eligible only for the ordinary production run. These are database
identity checks, not cryptographic authentication of a run, method or verdict.
Existing
Cloudline experiment approval must not be repinned or activated. Inherited V1
uncertainty and independent-review requirements remain. DO NOT INTEGRATE.

No provider was called, no deployment was performed and no physical evidence was
created. Detailed regression status and limitations are recorded in the PR.

Python 3.11 offline focused V1 and binding tests passed 35/35. A broader run
before the final change to reject abbreviated digests had 71 passed, four
failed: the previously documented W4 fidelity lifestyle PASS expectation and
three W4 VISNEXT expectations. Those three VISNEXT cases were rerun individually
on the unchanged `d125a3b` base and also failed there. Their assumptions about
the vision/fidelity handoff require separate review. No assertions were weakened.
`test_w4_visnext2.py` on the earlier working tree had 8 passes and 3 failures
because the owner-controlled Cloudline experiment remains frozen to older prompt
and reference versions. Its drift-refusal case was reproduced on the unchanged
`d125a3b` base. This work does not modify or reauthorize that experiment.

The run-scope follow-up passed 72/72 Python 3.11 tests across anchor binding,
V1 correctness and owner images. A separate reviewer reran the five anchor
tests and confirmed the owner fallback's intended scope. A caller-supplied run
key defaults to the production run when omitted and, like the stored method and
PASS status, is mutable metadata; these checks do not authenticate its origin.
