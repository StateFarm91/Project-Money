# Independent security and integrity review: W4-LAUNCHFIX `8c14dbf2`

- **Subject:** the delta `git diff 0f0306dd 8c14dbf2` (commits `209ad3af`, `323f302b`, `8c14dbf2`; 20 files, +685/−118).
- **Prior review:** `INDEPENDENT_SECREVIEW_LAUNCHFIX_0f0306d.md` (DO NOT SHIP; F-1 High).
- **Reviewer:** independent. The code was judged, not `LAUNCHFIX.md`.
- **Date:** 2026-10-31 (UTC).

## Verdict: **SHIP**

The High finding (F-1) is closed: the ops-token regression is reverted to the base behaviour. The Medium findings F-2, F-3, F-6 and F-7 are closed as each one's required fix specified. F-4, F-5, F-8 and F-9 are closed. The owner clarification (209ad3af) is implemented correctly:
- the sample photo now refuses at activation only;
- all three activation gate checks pass `stage="activation"`;
- a private draft still needs every other gate and its sealed owner grant.

The `_status` restoration is byte-identical to `0f0306dd`.

The probes found new issues, but none is High and none gives the ops token or an outsider a way to create, activate or publish a listing. Every one either needs direct database write access, fails closed, or predates this branch. They are listed below as follow-ups. N-1 and N-2 should be fixed before the photo gate or the policy gate is described as owner-grade evidence.

## Test runs

Each suite ran solo: `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python3 tests/<f>.py`, on a checkout of `8c14dbf2`. The container lacked the dependencies, so `pip install -r requirements.txt` was run first.

| Suite | Result |
|---|---|
| `test_w4_launchfix` | 32 passed, 0 failed |
| `test_etsy_exercise` | 32 passed, 0 failed |
| `test_search_hero_publish` | 4/4 passing |
| `test_first_customer_gate` | 12 passing, 0 failing |
| `test_etsy_readback_observe` | 37 passed, 0 failed |
| `test_cert_commerce` | 14/14 passed |
| `test_launch` | exit 0, no FAIL |
| `test_cost_governance_wave2` | exit 0, no FAIL |
| adversarial probes (below) | 5 holes reproduced (N-1 x2, N-2, N-3, N-4) and 1 pre-existing sibling (N-5); 3 probes held (p4, p5a, p6) |

The probe file was `tests/adv_secreview_launchfix_8c14dbf.py`. It imports the fixtures from `test_w4_launchfix`. It is not pushed, because only this report is pushed. The essential code of each probe is quoted below.

---

## Prior findings

| ID | Sev | Status | Evidence |
|---|---|---|---|
| F-1 | High | **Closed** (regression reverted; a residual pre-existing gap is N-1) | `record_page_reading(..., owner_attested=False)` defaults to `compare_basis=None`, the base `b0133916` comparison. Only `policy_readings.record` passes `owner_attested=True`, and it sits behind the CC owner session, CSRF, nonce, step-up and the verbatim confirmation. `owner_attested is True` is an identity test, so a truthy body value cannot reach it, and `main.py` never passes it (grep). Test `test_review_f1_*` shows an ops-token first reading over a seed is a material change with a `policy:<source>` owner card. |
| F-2 | Med | **Closed** | `remote_state_evidence` now reads only `etsy.exercise_evidence` rows. Each must have `actor == system:etsy_exercise` and pass `EVIDENCE.refusal()`, a `GrantLedger` HMAC check under the operator credential with a hash chain. Hand-inserted rows, rows with a wrong seal, and rows by other actors are all rejected (test plus code read). `_run_drafts` counts a removal only with `confirmed_by`. **A DB writer without the credential cannot forge a PASS.** Whoever holds the credential *value* can: this is the same trust root as every owner-grant family, so it is accepted. Residual: N-3. |
| F-3 | Med | **Closed** | `recorded_at` lies inside the sealed body. An age above 90 days, a negative age or an unparseable value sets `stale`, and the result is UNVERIFIABLE. Test: a correctly sealed row dated 2020 is UNVERIFIABLE. |
| F-4 | Low | **Closed** | The drafts are those with audit id greater than `start_id`, taken before `RUN_STARTED` inside `single_flight`. They are sealed into the evidence row. The gate also checks `outstanding_drafts()`. PASS now always requires `live_run_id` and `round_trip_clean`, even when `needed == []`, which closes the related sub-note. |
| F-5 | Low | **Closed** | `against_etsy` parses the URL and requires exactly `https` on `openapi.etsy.com`. The gate requires `transport_is_urllib` (`type(t) is UrllibTransport`, exact). Production `run()` defaults `transport` to `UrllibTransport()` before sealing (line 678), so a real run qualifies. |
| F-6 | Med | **Closed** | Every key of `_fee_terms()` is compared with the sealed `content`, and any difference is unready (`changed_terms`). Test covers the rate, the period, the reading and the CAD fee. |
| F-7 | Med | **Closed** for the questions asked (residual: N-2) | (a) A SHA in `ArtefactProvenance` with a provider or model, in a non-photo `ListingAsset`, or in `disclosed_shas` disqualifies the file. (b) The first certified frame must be `medium == PHYSICAL_PRODUCT_PHOTO`. (c) A photo qualifies only with `detail.owner_attestation.by` starting `owner:cc:` and a matching SHA. That attestation is written only by `attest_unedited`, which needs the verbatim confirmation, an `owner:cc:` actor and the CC action `physical_photo.attest_unedited` (step-up `True`). **The ops-token intake cannot set it**: `intake()` builds `detail` itself and has no `detail` parameter (probe p4 HOLDS). **A recorded render or AI image cannot qualify, and neither can an ops-token attestation.** |
| F-8 | Low | **Closed** | `TRADEMARK_SCREEN.action`, the requirement description, the owner-queue decision and the code comment now name the sealed `brand_risk_acceptance` as required and filing as optional. |
| F-9 | Low | **Closed** | The replay test now sends a *different* body under the reused nonce and asserts `code == "REPLAY"` (`test_w4_launchfix.py:979-982`). |

## Owner clarification (209ad3af)

**Can a private draft be created without its sealed owner grant?** No. `stage` changes only one line: `sample_photo.requirement`'s reasons join `reasons` only at `STAGE_ACTIVATION`. Every other gate still applies at the draft stage: staleness, window, listing set, search, standards, withholding, scope, originality and copy truth. `EtsyClient._authorise_write` and the sealed publication grant are untouched by the delta. An unknown stage raises `ValueError` (probe p6 HOLDS), and `_release_gates` turns that into a closed gate.

**Can activation or public publication occur without the bound sample photo and every other gate?** No. The only `client.activate` call is in `handle_store_activate` (`pipeline.py:2374`). All three gate reads there (initial, after read-back and after the budget reservation) pass `stage="activation"`. `EtsyClient.activate` still re-resolves the sealed ACTIVATE grant. `update_listing` still refuses `state`. Creation is always `createDraftListing`. The default `stage="draft"` is used only by `handle_store_publish` and by the read-only inventory report.

**Does any draft path make a false claim about a photo?**
- The generated photo sentence (`disclosure_copy(True)`) is refused at both stages when there is no qualifying photo (probe p5a HOLDS).
- The no-photo disclosure is the default copy.
- `copy_problems` matches the generated sentence exactly, so a *paraphrased* claim is not caught. See N-4. On a draft this is private, and at activation the photo gate refuses anyway, so it cannot reach a buyer as a false claim.

## `_status` restoration

`diff` of the `_status` function body between `0f0306dd` and `8c14dbf2`: **identical**. The only hunks in `etsy_exercise.py` across the delta are:
- `start_id` in `run()`;
- the `_seal_evidence` call;
- the new evidence helpers and ledger;
- the rewritten `remote_state_evidence`.

Nothing after `remote_state_evidence` was lost. The WIP checkpoint `323f302b` had grown the file to 969 lines. It ended inside the new `remote_state_evidence`, and the final commit carries that function complete. `test_etsy_exercise` passes 32/32.

---

## New findings

### N-1 (Low, pre-existing): ops-token first reading on a never-seeded source is a silent baseline

Before the first `policy.watch` job runs `policy_knowledge.seed_snapshots`, a source has no row. In that state, `POST /api/policy/snapshot` with the ops token alone records `first_reading=True, material_change=False`. With any text and any `read_by`, it opens `page_readings_status` for that source.

```python
r = ops_post("creativity_standards", "not the page at all " * 10)   # no seed row
# -> 200, first_reading True, material_change False; page_readings_status(...)["open"] is True
```

A related case: once any reading exists, the ops token can re-post identical text under any `read_by` (not material). That renews freshness with no person reading the page (probe p2).

Both behaviours are the base `b0133916` behaviour (the ops intake was the designed W4-B2CLOSE remedy), so neither is a regression. They do mean the answer to "can anything except the owner's form set a baseline?" is "yes, the ops token, on an unseeded source".

**Fix:** the prior review's option (b). `page_readings_status` should count a page reading only when it has a matching `policy.page_reading_attested` row, or treat a first reading with no prior row as material.

### N-2 (Medium): the owner photo attestation is unsealed JSON; a DB writer can forge it

`qualifying_photos` trusts `PhysicalPhoto.detail.owner_attestation` (`by` starting `owner:cc:` and a matching SHA). It carries no seal and is not cross-checked against the CC action's audit row.

```python
p.detail = {**p.detail, "owner_attestation": {"by": "owner:cc:forged", "sha256": sha}}
SP.requirement(db, slug, version)["satisfied"]   # True
```

This is the same class as F-2, which this delta fixed for D1 with a sealed chain. Impact is bounded: activation still needs the owner's sealed ACTIVATE grant bound to the listing id, so a forgery removes a gate but grants nothing.

**Fix:** seal the attestation, for example a `GrantLedger` family bound to `photo_id` and `sha256`, or require the matching `cc.action physical_photo.attest_unedited` audit row and verify its seal.

### N-3 (Low, fail-closed availability): one junk evidence row denies D1 with no rebase path

A single hand-inserted `etsy.exercise_evidence` row breaks the chain. After that, every sealed row is rejected, including a genuine run made afterwards (probe p7: UNVERIFIABLE after a fresh valid run). `EVIDENCE.rebase` is not called anywhere (grep), so recovery needs code. `remote_state_evidence` also calls `EVIDENCE.refusal` once per row. On a broken chain, that call writes a tamper incident, so the function described as "reads only" writes. Both behaviours fail closed.

**Fix:** expose an owner rebase for the family (a CC action under step-up), and call `chain()` once per read.

### N-4 (Low): copy truth matches only the generated sentence

```python
SP.copy_problems("The first image is an unedited photo of our finished sample, made from this pattern.",
                 photographed_sample=False)   # [] -- not flagged
```

This is reachable only on a private draft (activation refuses without the photo). Any LLM-assisted description path could still write such a claim into a draft.

**Fix:** add a conservative phrase check (photo, photograph or picture near sample, made or finished) when `photographed_sample` is False.

### N-5 (Info, pre-existing): `launch.readiness.etsy_integration` still reads unsealed breadcrumbs

`_etsy_exercise_evidence` still accepts hand-inserted rows (`round_trip_proven` True, probe p8). D1 is UNVERIFIABLE on the same rows, and both are required, so this grants nothing. For consistency, it should read `remote_state_evidence`.

## Required before SHIP

Nothing blocking. Recommended next: N-2, then N-1 (b), then N-3.
