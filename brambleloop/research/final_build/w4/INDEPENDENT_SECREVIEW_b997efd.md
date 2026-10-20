# Independent security review: release candidate b997efd

**VERDICT: NO BLOCKER.** The range reopens none of the earlier findings (B1, L1-L4, M1, I7, I8)
and adds no BLOCKER, HIGH or MEDIUM. Across the whole range `b931d17..b997efd`, taking the
three earlier reviews into account, no BLOCKER remains.

New findings: **I16-I19, all INFO**. Status: B1, L1-L4, M1, I7 and I8 stay FIXED. I9 and I10
are still OPEN, I11 is still PARTIAL, and I12-I15 are still OPEN. None of them changes in the
range.

Reviewer: W-SECREVIEW7. I am independent and wrote none of the code reviewed. Date: 2026-10-20
(UTC). The review was read-only. Nothing was deployed, no request went to production, nothing
was spent, and no credential was read or printed. The probes ran in-process with outbound
sockets disabled.

## Scope

- Production: `b931d17a738d6a5bcd96580f620069b669ca5f57`
- Earlier reviews: `INDEPENDENT_SECREVIEW_7f6dbe8.md` (B1 BLOCKER),
  `INDEPENDENT_SECREVIEW_17bc373.md` (NO BLOCKER; M1), `INDEPENDENT_SECREVIEW_6b25eb0.md`
  (NO BLOCKER; M1, I7 and I8 fixed).
- Candidate: `b997efda48e4c8a26176d2a3959430852300631f` (branch `claude/final-candidate-b997efd`).
- Diff: `git diff 6b25eb07 b997efda -- brambleloop/src brambleloop/tests ops
  brambleloop/requirements.lock brambleloop/Dockerfile` (13 files, +299/−25).
  `ops/`, `requirements.lock` and `Dockerfile` do not change in the range. No route, auth,
  `experiments/controlled.py` or `gateway/images.py` code changes, so the B1 byte route, the
  M1 resume settle and the I7/I8 code are byte-identical to `6b25eb07`.

Line numbers below refer to the candidate.

## (1) Earlier findings and new risk: **nothing reopened, no new BLOCKER/HIGH/MEDIUM**

| Change | Security/spend effect | Verdict |
|---|---|---|
| `runtime/release.py:407-419` storage audit | The `assets.storage_not_durable` audit now lists the ephemeral files (`chart`, `legend`, `pdf:<terminology>`) and adds `pdfs_kept_in_postgres`. The detail holds labels and a boolean only, with no digest or path. The row is now written whenever chart/legend are ephemeral, which is more often than before. No gate reads the row: `gates/first_customer.check_fulfilment_and_download` decides from `ArtifactStore.durable` and `deliverables.durable_state`. | SAFE |
| `intel/etsy_surfaces.py:2009-2016` F-588 re-audit | Adds `flux-3-image` to the reviewed image providers. Same vendor and role as `flux-2-pro`, and the buyer's deliverable is still the compiler-rendered PDF. The reasoning is recorded inline. This is a compliance judgement with no executable risk. | SAFE |
| `swarm/orchestrate.py:774-776` band | `visual.controlled_experiment` → `exploration`. A band sets queue priority only. `exploration` is an ordinary tier, not a protected one (`claim_tier`, `PROTECTED_KINDS`), so it cannot pre-empt customer-incident or truth-defect work. Spend stays bounded by the step-up authorization caps (7f6dbe8 §1b) and the M1 settle. | SAFE |
| `gateway/credentials.py:66-89, 209, 342` `model_for` | See (3). | SAFE, I18 |
| `visual/repair_routes.py:73-77` + shipped records | Experiment records are now read from `src/`, so `seed_experiments` now really runs in production on `visual.image_production`'s `retrieve_release` stage. See (2) and I17. | SAFE, I17 |

Regression runs on the candidate (focused files only):

| Test file | Result |
|---|---|
| `test_w4_integ4_secfixes.py` (B1 / L1-L4) | 12/12 |
| `test_w4_integ4_deliverable_routes.py` (B1 sweep) | 4/4 |
| `test_w4_credhealth.py` (I8, leak scan, URL pins) | 13/13 |
| `test_cert_spend_hosts.py` | PASS, 0 failing |
| `test_w3_k12_model_photography.py` (F-212) | 10/10 |
| `test_w4_integ4_shipped_records.py` | 2/2 |
| `test_w3_hq_independence.py` | 4 OK, exit 0 |
| `test_visual_inspection.py` | 24 OK, exit 0 |

## (2) Shipped `RECORD.json` files: **no secret, key, personal data or customer data**

Files: `src/brambleloop/visual/assets/owner_experiments/2026-10-19_chunky_ribbed_scarf/RECORD.json`
and `.../2026-10-19_reading_nook_cable_wrap/RECORD.json`. Both are byte-identical to the
`research/` originals (`cmp`), and the new test keeps them identical.

What the files contain:

- **No credentials.** There is no key, token, request id, seed or account identifier. A scan
  for `sk-ant-`, `bfl-sk-` and `api_key=`-shaped values found nothing. `operator` is the
  string `"owner, manual, dashboard.bfl.ai"`.
- **No personal data.** No name, email, address or payment detail appears. "Laura" is the
  company's AI persona (DECISION_LOG D-FB-12), not a real person. The three
  `canonical ...` reference hashes are the digests of the Laura reference-pack images, and
  those images already ship under `visual/assets/canonical/laura-r2-a42aeac7/`.
- **No customer data.** There are no buyer, order or Etsy identifiers. The products are two
  uncertified, not-customer-ready patterns.
- **Commercial content:** a $0.048 cost receipt, an outfit description, failure codes and
  lessons. Only owner-session routes expose it after seeding (ImageCandidate and outfit rows).
- **Only the JSON ships.** The research folder's `dashboard_receipt_screenshot.jpg`,
  `output_image.png` and `ref4-6*.png` stay under `research/`, which the Dockerfile does not
  copy (it copies `src`, `release` and `tests`).
- **Digests (I19).** The cable-wrap record holds a 16-hex prefix of an uncertified PDF digest
  and the full sha256 of the experiment output. Since 17bc373 the byte route serves only
  reference-pack/tournament images that pass a magic-number check, whatever digests are known
  (B1 fix, re-verified by the sweep above). Knowing these digests gives no access.

## (3) `gateway/credentials.py` in `test_cert_spend_hosts`: **justified; the check cannot bill**

- The file has addressed `api.bfl.ai` and `api.anthropic.com` since W4-CREDHEALTH (17bc373),
  and that review found it free and bounded. The undeclared file was one of the 9 failing
  suites on 6b25eb0. Declaring it records a decision that was already reviewed. It does not
  widen spend.
- **Only two URLs exist in the file**, both module constants: `BFL_CREDITS_URL`
  (`https://api.bfl.ai/v1/credits`, GET) and `ANTHROPIC_COUNT_URL`
  (`https://api.anthropic.com/v1/messages/count_tokens`, POST) at `:52-53`.
  `test_w4_credhealth.py:93,110-111` pins the method and URL of each check.
- **`model_for` changes only the `model` field of the count_tokens body.** It cannot change the
  host, path or method. `model_for("anthropic")` → `routing.route("asset_inspection")[1].model`
  → `claude-sonnet-5`. That is the STANDARD tier's model, it is in the billing table, and it is
  the model `visual/inspect.py`, `photoreal.py` and `model_registry.py` use. Token counting is
  free for every model, so any model `route()` could return (`claude-haiku-4-5`,
  `claude-sonnet-5`, `claude-opus-5`) is still a free call. `route()` raises `TaskRefused`
  rather than inventing a model. A raise happens before `http(...)` and `check_all` turns it
  into `UNKNOWN` (`:276-279`). `model_for("bfl")` returns the fixed string `flux-3-image`, and
  the BFL check never sends a model.
- Probe: `check_anthropic` with a recording transport made exactly one call,
  `POST https://api.anthropic.com/v1/messages/count_tokens`, and no other request.
- Residual: the declaration covers the whole file, so a future billable call added to
  `credentials.py` would pass this scanner (**I16**). `test_w4_credhealth`'s URL pins would
  still catch a changed endpoint in the two existing checks.

## (4) Test edits: **no security or spend assertion weakened; F-212 is still proven**

- **`test_w3_k12_model_photography.py:173-188` (receipt).** The earlier premise "BFL carries
  only the first reference" is out of date since W4-FLUXAPI. The test now asserts that both
  references are proven in a BFL body. It **keeps** the negative property using a body built
  from one reference: `proven` false, `transmitted == 1`, `[True, False]`. The receipt still
  measures the bytes in the request. I also checked the real BFL builder: 12 references are
  refused at build ("takes at most 8 ... Refused rather than silently dropping 4"), so no
  dialect drops references silently.
- **`:202-238` (F-212 refusal before request or reservation).** Since no real dialect drops a
  reference any more, the test simulates the drop by wrapping `I._request_for` so the second
  reference is omitted. `generate` looks up `_request_for` as a module global
  (`gateway/images.py:1064`), so the wrapper is on the real path, and the real
  `conditioning_receipt` and refusal at `:1069-1075` run before `reserve_render` (`:1082`)
  and before any post. The test still asserts the three things that matter:
  `ImagesRefused` containing "F-212", `post.bodies == []`, and exactly **one**
  `SpendReservation` (the first render's). The wrapper is restored in `finally`.
  Mutation probe:
  - Baseline: PASS.
  - Guard disabled (receipt forced `proven`): the test **fails** with "unprovable conditioning
    was not refused".
  - Control: the same two references with the real builder are accepted (proven, 1 post).
    So the refusal in the test is caused by the dropped reference and nothing else.
- **`test_cert_spend_hosts.py:36-41`.** One declaration added, see (3). The scanner,
  `test_the_scan_would_see_a_new_one` and the d_judge refusal tests are unchanged.
- **cc_mock fixtures.** These **add** an assertion: the provider-keys card shows status and
  fingerprint, and `page.content()` contains no `bfl-sk-`/`sk-ant-`. The other two edits
  update UI counts (11 More items) and exclude the first-sale card's rows from the lane count.
  Neither touches a security assertion.
- **`test_w4_integ4_shipped_records.py`.** New. It checks that the shipped records are
  byte-identical to `research/` (and the scan is non-empty), and that the runtime reads only
  inside `src/`.

## Findings

No BLOCKER, HIGH, MEDIUM or LOW.

- **I16 (INFO): the spend-host declaration covers the whole file.**
  `tests/test_cert_spend_hosts.py:40`. Declaring `gateway/credentials.py` exempts any future
  paid-host URL in that file from the scanner. *Fix:* add a test in `test_cert_spend_hosts`
  that the set of paid-host URLs in `credentials.py` is exactly `{BFL_CREDITS_URL,
  ANTHROPIC_COUNT_URL}` and that `/v1/messages"` (generation) never appears. That pins the
  free-only claim next to the declaration, as the d_judge entry is pinned.
- **I17 (INFO): the experiment seed now runs in production and writes owner-attributed
  approvals.** `visual/repair_routes.py:149` (via `image_production.py:598-603`). The first
  `visual.image_production` run will register `owner-manual-reading-nook-cable-wrap` and
  `owner-manual-chunky-ribbed-scarf` as `approval_state="approved"`,
  `approved_by="owner:manual-experiment"`, each reserved for its own listing. `outfits` then
  offers them as that listing's outfit (`reserved_for`, `:315-345`). The scarf record says it
  was written "from the owner's description relayed by the coordinator", not from an owner
  action in the system. The effect is bounded:
  - neither product is certified, so image production stops at `awaiting_certified_pattern`;
  - the seeded ImageCandidate is `publishable=False`, `technical_status="FAIL"`;
  - there is no spend.
  *Fix (optional):* record these as history (for example `approved_by="owner-reported"` plus a
  flag that excludes them from `reserved_for`), or confirm the owner intends them as the
  listings' outfits.
- **I18 (INFO): `owner_action` calls `model_for` with no guard.** `gateway/credentials.py:342`
  (called from `:321` and `:365`). If `asset_inspection` were ever removed from
  `routing.TASKS`, `route()` would raise inside the credentials card and notification builder
  (outside `check_all`'s try), and the card would fail with an error. It would not show a
  misleading state, and no request is sent. *Fix:* wrap the call and fall back to `"the
  routed vision model"`.
- **I19 (INFO): shipped record carries artifact digests.** `owner_experiments/
  2026-10-19_reading_nook_cable_wrap/RECORD.json:17` (16-hex PDF prefix) and the
  `output.sha256`. Harmless after the B1 fix (see (2)). *Fix:* none needed. Keep it in mind if
  a public route ever serves bytes by digest again.

## Status of earlier findings

| ID | Status on b997efd | Evidence |
|---|---|---|
| B1 | FIXED (holds) | byte route and `tournament_image_refusal` untouched in range; `test_w4_integ4_deliverable_routes` 4/4, `test_w4_integ4_secfixes` 12/12 |
| L1-L4 | FIXED (holds) | `test_w4_integ4_secfixes` 12/12 |
| M1 | FIXED (holds) | `experiments/controlled.py` untouched in range |
| I7 | FIXED (holds; residuals I14) | audit shortening code untouched |
| I8 | FIXED (holds) | `FINGERPRINT_DOMAIN` untouched; `test_w4_credhealth` 13/13; cc_mock adds a no-key-in-page check |
| I9 | OPEN (unchanged) | public `/api/audit` still shows `provider.credential_health` rows |
| I10 | OPEN (unchanged) | |
| I11 | PARTIAL (unchanged) | |
| I12-I15 | OPEN (unchanged) | not touched in range |
| I1-I3, I5, I6 | OPEN (unchanged) | not touched in range |
| I4 | BY DESIGN | |

## Method

1. Read the three earlier reviews and their status tables.
2. Read the full diff, then the code each change reaches:
   - `routing.route`/`TIERS`/`TASKS`;
   - `credentials.check_all`/`owner_action`;
   - `images.generate` (`:1040-1090`);
   - `repair_routes.seed_*` and its caller;
   - `outfits` selection;
   - `orchestrate.band_for`/`claim_tier`;
   - `first_customer.check_fulfilment_and_download`;
   - the Dockerfile `COPY` lines.
3. Probes, in-process with `socket.connect` disabled and nothing committed:
   - `model_for` for both providers;
   - `check_anthropic` with a recording transport;
   - the F-212 test's baseline, its guard-off mutant and a real-builder control;
   - the real BFL builder with 12 references;
   - `cmp` of shipped against research records.
4. Ran the focused test files listed in (1). I did not run the full suite.

## Verdict

**NO BLOCKER.** `b997efd` can ship as far as security and spend are concerned. I16-I19 are
INFO and can follow.
