# Independent security and integrity review: W4-LAUNCHFIX `0f0306dd`

- **Subject:** `claude/w4-LAUNCHFIX` at `0f0306dd`, against base `origin/claude/w4-INTEG8-next` `b0133916` (`git diff b0133916...0f0306dd`, 26 files, +2638/−50).
- **Reviewer:** independent. The code was judged, not `LAUNCHFIX.md`.
- **Date:** 2026-10-27 (UTC).

## Verdict: **DO NOT SHIP**

There is one High finding (F-1, E3). The ops token alone can now create a policy-page "baseline" that clears the `rendered_pages` freshness gate with no owner review. Before this change, the same request opened a material-change card. That card needed the owner's CC `policy.review` under step-up. This is an authority loosening on a gate that protects publishing. The D1, D2 and IMG gates are fail-closed today, and no Etsy write gained a new path. Their Medium findings should be fixed in the same pass.

## Test runs

Each suite ran solo at `nice -n 19` with `PYTHONPATH=src:tests` from `brambleloop/`, on a worktree of `0f0306dd`.

| Suite | Result |
|---|---|
| `test_w4_launchfix` | 22 passed, 0 failed |
| `test_etsy_exercise` | 32 passed, 0 failed |
| `test_first_customer_gate` | 12 passing, 0 failing |
| `test_launch` | exit 0, no FAIL |
| `test_cost_governance_wave2` | exit 0, no FAIL |
| `test_search_hero_publish` | 4/4 passing |
| adversarial probes (below) | 7 holes reproduced; 1 probe (nonce replay) confirmed the gate holds |

The adversarial probe file was `tests/adv_secreview_launchfix.py`. It imports the fixtures from `test_w4_launchfix`, and each probe asserts the hole. It is not pushed, because only this report is pushed. Each probe's essential code is quoted in its finding below.

---

## Findings

### F-1 (High): E3 lets the ops token alone set an unreviewed policy baseline and clear `rendered_pages`

**Code.**
- `gates/platform_policy.py:record_page_reading` now passes `compare_basis=PAGE_BASIS`.
- That function is also behind the legacy `POST /api/policy/snapshot` (`app/main.py:1880ff`). That endpoint accepts the **ops token alone**: there is no owner session, no step-up and no attestation, and `read_by` is taken **from the body**.
- With this change, the first `page` reading of a source is `material_change=False`, whatever text it carries. `unreviewed_changes` stays empty, and `policy_access` freshness counts the source as read by a named person.

**Before:** the same request was a material change against the excerpt seed. It raised a `policy:<source>` card that only the owner could clear (CC `policy.review`, which needs step-up).

**Reproduction (probe `adv_e3_ops_token_alone_sets_an_unreviewed_baseline`):**
```python
_seed(db, "shilling_and_reviews")
r = client.post("/api/policy/snapshot", headers={"Authorization": f"Bearer {OPS}"},
                json={"source": "shilling_and_reviews",
                      "text": "anything at all, not the page " * 3, "read_by": "Owner Name"})
assert r.json()["material_change"] is False and r.json()["first_reading"] is True
assert "shilling_and_reviews" not in {x["source"] for x in PP.unreviewed_changes(db)}
```

**Second consequence (all paths).** A real Etsy change made between the repository excerpt and the first person reading is no longer flagged by code. On the CC form, the owner reads the page and answers the questions, which partly mitigates this. On the ops-token path nothing mitigates it.

**Answer to brief question 4:** a baseline is **not** only ever a first *person* reading. Any ops-token holder, or a bug in any caller of `record_page_reading`, can create it with any text and any claimed reader.

**Required fix (any one of these):**
- (a) Apply `compare_basis=PAGE_BASIS` only on the CC path (`policy_readings.record`, owner session, step-up, verbatim attestation). Leave `POST /api/policy/snapshot` with its old comparison, so an ops-token first reading still opens the owner review card.
- (b) Have `freshness` / `rendered_pages` count a page reading only when it has a matching `policy.page_reading_attested` row.
- (c) Retire the ops-token intake.

Add a regression test that an ops-token first reading is not silently a baseline.

### F-2 (Medium): D1 evidence is unsealed audit rows; any DB writer can forge a PASS

**Code.** `integrations/etsy_exercise.remote_state_evidence` trusts any `AuditLog` row with action `etsy.exercise_finished`, `etsy.exercise_draft_created` or `etsy.exercise_draft_removed`:
- it does not check the actor;
- the rows carry no seal and no chain;
- `DRAFT_REMOVED` is accepted without `confirmed_by`.

**Reproduction (`adv_d1_unsealed_rows_by_any_actor_pass`):** three hand-inserted rows with `actor="anyone"` give `check_etsy_remote_state(db).state == PASS`.

**Impact.** `etsy_remote_state` is one release gate. A real draft still needs the sealed publication grant, and activation still needs the sealed activation grant (see question 2), so a forgery removes a gate but grants nothing. Still, the brief's standard ("can it PASS without a genuine run?") is not met. The doc's claim of "the same trust level as `launch.readiness`" is accurate, but that level is weaker than every other gate input that now relies on it.

**Required fix:**
- Seal the `RUN_FINISHED` row, including its `claims`, `drafts_created` and the live run's draft ids, with the server credential, in a `sealed_chain` family. Alternatively, have `remote_state_evidence` require the row's actor to be `orchestrator`, plus an HMAC.
- Require `DRAFT_REMOVED.confirmed_by`.

### F-3 (Medium): D1 has no age bound; a years-old run passes for ever

**Reproduction (`adv_d1_a_years_old_live_run_still_passes`):** a live run whose rows are dated 2020-01-01 still gives `PASS`.

**Why it matters.** The claims (form-encoded create, multipart upload, tag array encoding, the OAuth token endpoint) describe Etsy's API contract, which drifts. Every other evidence source in this repo has a freshness window: policies, knock-out screening, taxonomy.

**Required fix:** add a maximum age (for example 90 days, the same as the policy readings) to `live_run_at` in `check_etsy_remote_state`. When the run is older, the result is UNVERIFIABLE.

### F-4 (Low): D1 `round_trip_clean` is not scoped to the live run

**Code.** `created`/`removed` are collected across **all** runs. A live full ok run that recorded no draft passes on an older run's removed draft.

**Reproduction (`adv_d1_clean_round_trip_not_scoped_to_the_live_run`):** a local run with draft 5 created and removed, then a live run with `drafts=()`, gives `PASS`.

**Mitigation.** In the real `run()`, `ok` requires `exercise.verified`, which needs a created and deleted draft. Only forged or partial rows reach this path.

**Required fix:** require at least one `DRAFT_CREATED` between the live run's `RUN_STARTED` and its `RUN_FINISHED`, and require each of those drafts to be removed.

**Related (Low).** When every blocking claim is static-verified (`needed == []`), PASS requires no round trip and no draft-removal evidence at all. Today this is not reachable, because four claims are needed.

### F-5 (Low/Info): `against_etsy` is a URL-prefix test, not a transport fact

`etsy_probe.against_etsy` returns `str(client.BASE).startswith("https://openapi.etsy.com")`:
- Any injected transport with the default `BASE` reports `True` (`adv_d1_against_etsy_is_the_url_prefix_not_the_transport`).
- There is no trailing `/`, so `https://openapi.etsy.com.attacker.test` would match.

Production `POST /api/etsy/exercise` passes no transport, so `UrllibTransport` with TLS is used. This finding is only reachable from code. **Fix:** compare the parsed host exactly, and record the transport class in the finished row. `remote_state_evidence` should accept only `UrllibTransport`.

### F-6 (Medium): `listing_fees` can be satisfied by an approval of different fee terms

**Code.** `ops/launch_decisions.listing_fees_state` compares only `fee_per_listing_usd` and the listing count. The owner previewed and sealed `transaction_rate`, `listing_period_months` and `fee_reading`, and none of them is compared. The requirement's own text is "approved Etsy's listing **and transaction** fees".

**Reproduction (`adv_d2_listing_fees_ignores_transaction_rate_change`):** with `transaction_rate` changed to 0.25 and `listing_period_months` changed to 1, it stays `ready: True`.

**Count:**
- An approval for N listings covers any N or fewer listings.
- A different catalogue *count* above N is refused (good).
- A different fee per listing is refused (good).

**Required fix:** compare every field of `_fee_terms()` with the sealed `content`, or bind and compare `digest(_fee_terms())`. Any difference is unready.

### F-7 (Medium): the sample-photo gate accepts bytes the system itself recorded as an AI render

**Code.** `publish/sample_photo.qualifying_photos` trusts:
- the intake row (`physical_upgrade.intake`, reached by `POST /api/physical-photo` with the **ops token**);
- the boolean `unedited: true`, which comes from the job body;
- free-text `taken_by`.

It never checks that the photo's SHA-256 is absent from the system's own records of generated or rendered images (`ArtefactProvenance.sha256` with a provider or model, `ListingAsset` with a non-photo `asset_class`). The certificate's first frame is matched by SHA only. `PHOTO_CLASS = "PHYSICAL_PRODUCT_PHOTO"` is defined and never used, so the frame's class or role is not checked either.

**Reproduction (`adv_img_a_recorded_ai_render_passes_as_the_sample_photo`):**
1. Take the passing fixture.
2. Add `ArtefactProvenance(provider="replicate", model="flux-pro", sha256=sha)` and `ListingAsset(asset_class="DISCLOSED_RENDER", sha256=sha)`.
3. `requirement(...)["satisfied"]` is still `True`.

**What holds** (tests and code read):
- a photo of another release (version mismatch) is refused;
- a sample of another release (the test's slug or version is not this one) is refused;
- an unbound make is refused;
- not attested unedited, or marked edited or AI-processed, is refused;
- a photo that is not first is refused;
- a swatch is refused: the binding requires `FULL_PHYSICAL_MAKE`.

**Disclosure.** The disclosure is truthful relative to the gate. The "photographed" copy is emitted only when `requirement` is satisfied, an exception is treated as not photographed, and `for_publish` refuses either sentence when it contradicts the gallery. It is only as truthful as the `unedited` attestation (above).

This gate is a net **tightening** relative to the base, so F-7 does not regress anything.

**Required fix:**
- Refuse a photo whose SHA appears in `ArtefactProvenance` with a provider or model, or in any `ListingAsset`/certificate frame whose class is not a photo.
- Require the certified first frame's `asset_class == PHOTO_CLASS`.
- Record the `unedited` attestation through the owner's CC session, not the ops-token body.

### F-8 (Low): `brand_clearance` owner request text does not match the code

**Code.** `brand_clearance_state` requires (a) a valid knock-out screening **and** (b) the sealed `brand_risk_acceptance` bound to `digest(entry)`. Registration (c) is reported and **not** required. That matches the code and the brief.

**What does not match:**
- `launch/readiness.TRADEMARK_SCREEN.action` still asks the owner only to "Decide whether to file a Canadian trademark".
- The requirement's description says "and the owner has decided whether to file".
- The comment in `readiness.py` says "the owner's sealed decision on filing bound to that exact search".

An owner who follows the card can record `trademark_registration: not_now` and still be blocked. This fails closed, but the owner queue misstates what is needed.

**Required fix:** rewrite the request, the description and the comment to name the risk acceptance as the required decision, and filing as optional.

**Spec check (question 3c).** Master Plan v1.2 §29 says, verbatim: "perform marketplace/domain/social-handle screening and appropriate trademark clearance; escalate formal legal clearance to the owner/professional if needed". The plan's owner-only list says "final brand/trademark decision", and spec 08 #54 says "brand/name clearance checkpoint". None of them requires a filing, so "registration not required" is faithful. The screening validation is real code (`brand/clearance.problems`):
- all four screens;
- an https source;
- a query containing the name;
- an explicit hits list, with relevance and a reason for each hit;
- `conflicts` must equal exactly the hits marked conflict;
- a maximum age of 365 days, evaluated at read time.

The acceptance is bound to that screening's digest.

**Info.** The validator accepts any https source string. It cannot check that `trademark_register_ca` actually points at CIPO, so it relies on code review of the `KNOCKOUT_SEARCHES` entry.

### F-9 (Low): the nonce-replay assertion in `test_w4_launchfix` is ambiguous

In `test_cc_policy_form_needs_a_session_csrf_and_step_up`, the replay of the same request with the same nonce asserts `status in (401, 403, 409)`. The **duplicate-reading** refusal is also 409 (`DUPLICATE`), so the test would still pass with no nonce check at all.

The probe `adv_cc_nonce_replay_with_a_different_body` (same nonce, *different* text) shows the gate does refuse: `409 {"code":"REPLAY"}`. The control works, but the test does not prove it.

**Fix:** send a different body under the replayed nonce, and assert `code == "REPLAY"`.

### F-10 (Info): owner authority via the ops token at module level

`launch_decisions.record(authorization=<ops token>)` seals a decision without step-up when it is called in-process. The test suite does exactly this. Over HTTP, the only path is the CC `POST /api/cc/actions/launch_decision.record`, which enforces session, CSRF, nonce and step-up (`ACTIONS[...][0] is True`, `api.py:852`), and refuses the bearer token (the `/api/cc/` owner-session gate). This is the same model as every other `GrantLedger` family, so it predates this diff and is unchanged by it.

### F-11 (Info): the exercise test-draft lane (pre-existing, now load-bearing)

The D1 evidence comes from `POST /api/etsy/exercise`. That endpoint uses the ops token, not a sealed owner grant, and creates and deletes a real Etsy draft through `shadow_writes_authorised`:
- it is only allowed outside the publishing phases;
- `refusal_for(ACTIVATE)` is asserted non-None before the run.

`LAUNCHFIX.md` §1 itself says draft fees are "UNVERIFIED by a quoted Etsy source" and are to be treated as potentially fee-bearing. Yet this lane has no fee reservation and no ceiling. This diff does not change the lane. The owner should know that the D1 gate now depends on it.

---

## Answers to the brief, point by point

**1. D1.** It cannot PASS on:
- a run against the fake (`_status` is never the live prefix);
- a run that was not ok;
- a rotation-only run;
- a partial claim set;
- old rows with no claims;
- a stranded draft;
- the newest live run verifying less than an older one;
- a later CONTRADICTED claim (that is a FAIL).

It **can** PASS on:
- forged unsealed rows (F-2);
- an arbitrarily old run (F-3);
- a round trip borrowed from another run (F-4).

**2. No unauthorised Etsy action.** `store.publish` still runs `release_gates.for_publish` and still requires the sealed publication grant (`EtsyClient._authorise_write`). Activation needs the separate sealed activation grant bound to the listing id. `update_listing` refuses `state`. No create payload sets `should_auto_renew`. This diff adds no new Etsy write path, and the D1 test's stub transport fails on any byte. The kill-switch and the fee ceiling on activation are unchanged. The test-draft lane (F-11) predates this diff.

**3. D2.** The decisions are:
- HMAC-sealed under the server credential;
- chained (`GrantLedger`);
- revocable;
- bound to the preview digest;
- recorded through CC only with step-up, refusing the bearer token over HTTP.

Stale approvals:
- `listing_fees` refuses a larger catalogue count and a different per-listing fee, but **accepts changed transaction and period terms** (F-6).
- `brand_clearance` is correct in logic. Its owner-facing text is wrong (F-8).

**4. E3.** Yes, see F-1.

**5. The `#/policy` form.** What holds:
- owner session (401 anonymous; bearer token refused);
- CSRF (403);
- step-up (403 `STEP_UP_REQUIRED`);
- nonce (409 `REPLAY`, probe);
- duplicate (409 `DUPLICATE`);
- `read_by` comes from the session, not the body;
- only the SHA-256 of the text is stored (the owner's answers go to `summary`);
- the legal pages are never fetched: `_fetch_article` refuses any non-Help-Center source;
- the Help Center fetch uses a fixed host (`https://help.etsy.com/api/v2/...`), with the article id taken from the code constant `POLICY_SOURCES` by regex `\d+`, so there is no SSRF.

Minor points:
- `urllib` follows redirects;
- the fetch ignores `BRAMBLELOOP_POLICY_READER` and the 3-second spacing (one owner-triggered GET).

**6. The sample-photo gate.** A photo of another release or of another sample is refused, and an edited or AI-flagged photo is refused. A render or AI image **is** accepted if the ops-token intake attests it unedited, and nothing cross-checks the system's own render records (F-7). The disclosure follows the gate's fact.

**7. Test integrity.**
- **`test_launch`:** `brand_clearance` is added to the expected company-side items and excluded from the blocked-by subset check. This matches the new BLOCKED_BUILD attribution and asserts `ready is False`. It is not a weakening.
- **`test_cost_governance_wave2`:** the test file is **unchanged**. Only `ops/retention.py` gained `lifetime_total` entries for the new sealed-chain and attestation actions. That is correct for a sealed chain, and not a weakening.
- **`test_search_hero_publish`:** it stubs `sample_photo.requirement` to `{"satisfied": False, "reasons": []}`, in the same pattern as the existing scope-gate stub. Its assertions are unchanged, so it is not a weakening of that test. As a result, **no test exercises the photo gate on the real `store.publish` path**: `test_img_*` calls `requirement()` directly, plus a source-text check that `for_publish` calls it.
- **New tests:** the D1, D2 and IMG tests are substantive (each refusal case is asserted separately). F-9 is the one ambiguous assertion.

## Required before SHIP

1. F-1 (High): an ops-token page reading must not become an unreviewed baseline.
2. F-2 and F-3: seal the D1 evidence and bound its age.
3. F-6: bind all of the fee terms.
4. F-7: cross-check the photo SHA against render and generation records, and require `PHOTO_CLASS` on the first frame.

F-4, F-5, F-8 and F-9 are recommended in the same pass.
