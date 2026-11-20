# CONDPACK: F-733 provider conditioning packages for Laura's canonical identity

Branch `claude/w4-CONDPACK`, based on `origin/claude/w4-INTEG2` 85ec5d0. Local and
deterministic: no provider call and no spend. Laura's files are only read.

## What changed

- `visual/conditioning.py` derives, for every image provider that can hold an identity lock
  (flux-2-pro, gpt-image-2, nano-banana-2, seedream-v5-lite), the exact conditioning package
  an identity-locked render is built from:
  - the canonical revision `laura-r2-a42aeac7` (D-FB-14);
  - its frames in order, face first: `neutral_portrait`, then `torso_fit_reference`, then
    `full_length_standing`;
  - each frame's approved sha256 and size (hash-verified through `canonical.reference_file`);
  - how many references the dialect actually transmits. BFL carries only the first, so its
    package states this as a `limitation`; gpt-image-2 carries all three;
  - a `package_sha256`.
- A forbidden hash, a missing reference or a reference whose bytes are not the approved bytes
  refuses the package (`ConditioningRefused`).
- The packages are stored at
  `src/brambleloop/visual/assets/conditioning/laura-r2-a42aeac7/<provider>.json`.
  - `verify_stored` re-derives each package and compares it field by field.
  - `registry()` is the canonical asset registry's provider view.
- Nothing is approved for publication by this. Laura's customer-facing gates are unchanged.

## Acceptance evidence

- `tests/test_w4_condpack.py` (new) covers:
  - every package verifies;
  - face first, with transmission stated honestly per dialect;
  - an edited package fails verification;
  - a missing or altered reference refuses the package;
  - a forbidden hash refuses the package;
  - Laura's bytes are unchanged and `canonical.verify()` is ok.
- `test_canon_manifest` and `test_secret_scan` also run. Results are in the commit message.

## Board row F-733: what remains, and who clears it

- **Provider conditioning packages: done (this branch).**
- **Approved pack fingerprint from the production `model.frozen` row: BLOCKED (owner/external).**
  - It is readable only from the production database. Production reads and POSTs are not
    allowed from workers.
  - Clearing path: owner action OA-CANON-1 (read-only SQL in Railway, about 10 minutes, no
    cost). Then record the value in `freeze.APPROVED["approved_pack_fingerprint"]`.
- **Deploy of hash-verified `reference_paths`: integrator deploy step.** The code is on
  INTEG2.

## Test results (testslot, 2026-10-12)

| Test file | Result |
|---|---|
| test_w4_condpack | 0 fail |
| test_canon_manifest | 0 fail |
| test_secret_scan | 0 fail |
