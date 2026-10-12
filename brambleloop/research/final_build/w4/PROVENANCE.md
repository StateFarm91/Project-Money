# W4-PROVENANCE: approval record into the repository (F-718/F-733), F-849 evidence, F-834/F-846 status

Branch `claude/w4-PROVENANCE`, based on `origin/claude/w4-INTEG2` 85ec5d0. Production was only
read, with one public GET (`/api/audit?action=model.frozen`). Nothing was deployed or written.

## F-718 / F-733: the owner's canonical-model approval no longer lives only in one database row

- **`src/brambleloop/visual/approval_record.json`** is the production `model.frozen` row 5693
  (2026-09-22T03:52:53Z), exported read-only. It ships in the image. Pinned fields:
  - `key` brambleloop-canonical, `version` 1
  - `approved_at`
  - `pack_version` v15-…
  - `candidate_fingerprint` 914ee7da716baef7

  The identity description fields are not copied. The pack itself is the durable description;
  this file pins which pack the owner approved.
- **`visual/approval_record.py::compare(db)`** checks the repository record against the
  database's own `model.frozen` row. States:

  | state | meaning |
  |---|---|
  | MATCH | the row agrees on every pinned field |
  | MISMATCH | the row disagrees; the differing fields are named |
  | NO_ROW | the database holds no freeze row; this is never a pass |
  | UNREADABLE | the repository record could not be read |

  `GET /api/model-identity` now serves this as `approval_record`.
- **`freeze.OWNER_APPROVAL["approved_pack_fingerprint"]` is still `None`.** Two existing tests
  pin that (`test_cert_identity`, `test_model_freeze`), and this lane edits no test assertion.
  The fingerprint is held by the new record instead.
- **Tests:** `tests/test_w4_provenance.py` passes 6/6 (run through the test slot). It covers MATCH, MISMATCH naming the field, NO_ROW never
  a match, no identity description copied, the record agreeing with the code approval's
  `approved_pack_version`, and the route serving the comparison.
- **Rows:** F-718 is advanced. Its stated next action ("export the production approval record
  and pack fingerprint into the repository manifest; test the manifest matches the DB row") is
  done. It closes on a production readback of `/api/model-identity` `approval_record.state ==
  MATCH` after a deploy. F-733 is advanced for the fingerprint only. Its other parts (provider
  conditioning packages, deploying hash-verified `reference_paths`) belong to the image/visual
  domain and are not taken here.

## F-849 Claude/Chat independence: the "buildable now" half is done; the soak remains

- `tests/test_cert_claude_independence.py` passed 4/4 on the frozen candidate 5ad94dd, clean
  tree, run 20261012T020255Z-6086, 502 s. The record and log are copied verbatim, read-only,
  into `evidence_PROVENANCE/`. Their sha256 hashes:
  - json: 91beabae…
  - log: dbf96028…

  It was not re-run.
- **What remains** is the F-849 data gate `production_window`: the 24h off-device proof on a
  deployed release. Production on 0417f35 is still unmet on dead letters. The fixes for those
  are on INTEG2 and not yet deployed.

## F-846: no code change; integrator acceptance needed

The audit-repair loop ran end to end on 7421ef6 → 5dfd1ac/0417f35 (see `FM_GATE_REPORT.md`). The
row needs only the integrator to accept the structural TESTED target in
`OVERRIDES_PROPOSED_FMGATE.json`, whose dry run computes COMPLETE. A worker cannot accept it
(F-867).

## F-834: blocked by the adjudicator's own design (recorded, not worked around)

`build2/final_proof.py::_validate` applies one run identity to every receipt: `receipt()` needs
`item.head == packet.head` and `item.run_id == packet.run_id` for the chain stages, the
`suite`, the `production_producer`, the `failure_test` and the `independent_review`.

A full suite, a shadow rehearsal and an independent review are by nature three separate runs.
Each has its own run id, and the suite's head is the record SHA (5dfd1ac), not the record-only
commit (0417f35). So a packet can only pass by relabelling one run's receipts with another run's
id, which would be fabrication.

**Unblocking action (integrator/owner decision on an adjudicator rule; no worker may weaken
it):** let `final_proof` bind the suite by the deploy guard's tree rule, and give the review its
own run id bound by artifact digest.

Until then, extending `emit_runtime_packets.py` cannot produce a REVIEWABLE packet honestly, so
this lane did not.
