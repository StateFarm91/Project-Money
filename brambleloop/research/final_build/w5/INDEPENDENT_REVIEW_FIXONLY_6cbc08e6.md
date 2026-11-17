# Independent review: W6 FIX-ONLY rebuild (6cbc08e6)

Branch `origin/claude/w6-fix-only-rebuild` at 6cbc08e6. Base `claude/w6-INTEG1` at c83d9516.
Diff: `brambleloop/src/brambleloop/runtime/release.py` (+70/-10) and
`brambleloop/tests/test_w6_fix_only_rebuild.py` (new, 5 tests).
Worktree: /home/user/bl-runs/wt-rev-fixonly. Python: /home/user/bl-runs/venv-integ4/bin/python.
Nothing was committed or pushed. The worktree is clean (mutants were reverted).

## Verdict: DO NOT SHIP 6cbc08e6

The bounded path works. A fix-only `assets.build` stops at `listing.seo`. It never enqueues
`launch.plan`, `marketing.schedule` or `store.publish`. It leaves a live `Listing` row alone,
and `launch.plan` refuses a fix-only input. An ordinary chain behaves exactly as it did before.

The change still adds a regression. `fix_only` is written into `assets.build`'s **outputs**, and
two ordinary re-drive paths copy those outputs as their inputs. After any fix-only build, the
next plan-drift re-price or targeted stale rebuild of that release silently becomes fix-only.
That run keeps the stale price and never relaunches, and the idempotency key is used up, so it
does not retry (F1). A fix-only run on a live listing also overwrites the listing's search
profile with the candidate copy. The live listing then reads as edited after certification
(F-294), and an open taxonomy-drift incident can be closed although nothing changed on Etsy (F2).
Both fixes are small. They are listed below.

## Tests run (one at a time, clean tree)

| Test | Result |
|---|---|
| tests/test_w6_fix_only_rebuild.py | 5/5 OK (4m10s) |
| tests/test_cert_rebuild_chain.py | 10/10 OK, "PASS: 0 failing" (3m30s) |

Repro scripts (run from `brambleloop/` with `PYTHONPATH=src:tests`):
- /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/repro_fixonly.py (F1, F3, F4)
- /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/repro_fixonly2.py (F2)

## Findings

### F1 — HIGH (regression): `fix_only` leaks into ordinary re-prices and targeted rebuilds through `assets.build` outputs
- **Where.** `runtime/release.py:608` puts `fix_only: True` into `payload`, which `handle_assets_build`
  returns, so it is stored as the job's **outputs**. Two paths look up "the latest DONE
  `assets.build` with `pdf_sha256`" and enqueue `{**built, ...}`:
  - `release.py:5197`, `_reprice_on_plan_drift`, which runs `pricing.position` to fix a price
    that has drifted from the plan.
  - `release.py:5396`, `_targeted_rebuild`, which handles stale `pricing`, `listing_copy` and
    marketing artefacts. Under `REBUILD_STAGE` all of these restart at `pricing.position`.

  `finance/launch_review.py:518-528` does the same with the latest build's **inputs**, which
  also carry `fix_only` after a fix-only build.
- **Effect.**
  - The plan-drift re-price becomes fix-only. It records no price point, `_persist_listing`
    keeps the drifted price (`release.py:2134`), and it stops before `launch.plan`. Its key
    is derived from the drift (`reprice:<old>-><new>`), so the repair is used up and never
    retries.
  - A targeted rebuild of a stale marketing asset never reaches `launch.plan` or
    `marketing.schedule`, so the stale artefact is never remade. Verify passes then find it
    still stale.
  - A launch-review batch enqueues a fix-only `assets.build`, so the reviewed release never
    goes on to launch.

  The direction of the leak is "ordinary becomes bounded", so it is fail-safe for the shop.
  It is still a silent loss of function, and nothing records it.
- **Repro (repro_fixonly.py, R1).** Run `_fix(...)` once. Then enqueue exactly what line 5196
  enqueues and set the draft price to 1.11:
  ```
  R1 latest assets.build OUTPUTS carry fix_only: True
  R1 ordinary re-price jobs: ['pricing.position', 'listing.seo']     # no launch.plan
  R1 price after a re-price meant to fix drift: 1.11                  # price not applied
  ```
- **Fix.**
  - Do not put `fix_only` into the returned payload. Pass it only on the `pricing.position`
    enqueue, for example `ctx.enqueue(..., {**payload, **fix})` with `return payload`
    unchanged.
  - Have the three consumers (5197, 5396, launch_review 522) drop `fix_only` from what they
    copy.
  - Add a test: after a fix-only build, `_reprice_on_plan_drift` applies the plan price and
    reaches `launch.plan`.

### F2 — MEDIUM-HIGH: on a live listing, a fix-only run still rewrites the search profile, so the live listing fails F-294 and drift incidents can close falsely
- **Where.** `release.py:1317` calls `_persist_search_profile` before `_persist_listing` and
  ignores `fix_only`. It overwrites `ListingSearchProfile` with the **candidate** copy's
  fingerprint, taxonomy, properties, attributes and certificate (`release.py:1504-1528`). The
  live branch in `_persist_listing` (`release.py:2116-2132`) protects only the `Listing` row.
- **Effect.**
  1. `release_gates.search_gate` (`publish/release_gates.py:338-343`) compares the profile
     fingerprint with the row. The live listing now reports "the listing's title, description,
     tags, taxonomy or properties changed after certification; re-run listing.seo". Re-running
     `listing.seo` cannot clear it, because the row stays frozen. This reaches
     `publication_authority`, `commerce/search.py:949` and `ranking_readiness`.
  2. `_persist_search_profile` calls `taxonomy_drift.resolve_if_current`
     (`release.py:1533`). A fix-only run on a newer snapshot resolves the product's
     `taxonomy-drift:` incident as "rebuilt", but the live Etsy listing is still on the old
     taxonomy. This sidesteps the hold that FMBATCH1 F-1 put on owner approval. I found this
     by reading the code; the fixture has no snapshot (`snapshot_id` is None), so I could not
     exercise it.
  3. `seo/packages.record_from_release` (around line 1395) and `_support_knowledge` (FAQ
     built from `copy.description`) are also built from the candidate, not from what buyers
     see.
- **Repro (repro_fixonly2.py).** The live row is `published`, has an Etsy id, and its profile
  was certified on its live copy.
  ```
  before: F-294 on live listing: False
  after:  F-294 on live listing: True
  live row title: LIVE TITLE ON ETSY
  ```
- **Fix.**
  - Decide liveness before `_persist_search_profile`.
  - For a live row, store the candidate profile separately, for example in the
    `listing.fix_candidate` audit or a candidate table, and do not call
    `resolve_if_current`.
  - Leave the package and FAQ alone for a live row, or mark them as candidate.

### F3 — MEDIUM: a `withdrawn` listing with no Etsy id comes back as `draft`
- **Where.** `release.py:2092` and `2143`. `LIVE_STATES` does not cover `withdrawn`, so a
  fix-only run sets `row.state = "draft"`. Rows are withdrawn because certification was
  refused (`pipeline.py:1577-1582`) or because the lane release was refused
  (`release.py:8293-8296`). A remediation should never undo either. `autonomy/generators.py:225`
  and the readiness readers then count the row as a draft again. (An ordinary chain did this
  before as well. The brief asks for fix-only to be bounded, and this is not.)
- **Repro (repro_fixonly.py, R3).** Set `state="withdrawn"` and `etsy_listing_id=""`, then run
  `_fix`:
  ```
  R3 withdrawn -> state: draft
  ```
- **Fix.** Under `fix_only`, keep a non-draft state that is not live (at least `withdrawn`). Do
  not touch the row and audit it the way the live case is audited, or keep `row.state`.

### F4 — MEDIUM: the owner card cannot be acted on for the description
- **Where.** `release.py:2117-2132`. The card says "Review the rebuilt listing copy … (audit
  listing.fix_candidate) and … update the live Etsy listing by hand". The audit holds only
  `title`, `tags` and `description_chars`, a length (`release.py:2120`). The candidate
  description is not stored anywhere the card points to. It survives only in the
  `listing.seo` job outputs, and the card does not name them. The candidate taxonomy and
  properties are left only in the profile overwritten by F2.
  - "Exact action" is not met. The card does not say which fields differ from the live
    listing or where to find the text.
  - Once the owner applies the copy by hand, nothing updates the local row, so the row stays
    stale.
  - The rest of the card is well-formed: cost 0.0, 10 minutes, a consequence and a reason. It
    is deduped by key through `owner_queue.ensure`, an open row is restated, and a new card
    is raised after `done`.
- **Repro (repro_fixonly.py, R4).**
  `R4 candidate keys: ['description_chars', 'tags', 'title'] has description text: False`
- **Fix.**
  - Store the candidate description, or a pointer to the job id, in the audit.
  - Name the changed fields in `action`.
  - Name the follow-up (`listing.adopt_manual` or the equivalent) that re-syncs the row after
    the owner edits the listing.

### F5 — LOW: `LIVE_STATES` duplicates `core/listing_state.LIVE_ON_ETSY`
- **Where.** `release.py:2092`. `core/listing_state.py` says that every "live on Etsy" reader
  must ask that module, "so a new live state cannot be added in one reader and missed in
  another". The new tuple adds `active`, which `LIVE_ON_ETSY` lacks. It misses `live` (used in
  `autonomy/kpis.py:132`) and `incomplete_on_etsy` (`pipeline.py:2385`). In practice
  `incomplete_on_etsy` is covered because the Etsy id is always set with it.
- **Fix.** Use `LIVE_ON_ETSY + ("active", "incomplete_on_etsy")`, or add `active` to the
  canonical tuple.

### F6 — LOW: a draft's pricing provenance is refreshed while its old price is kept
- **Where.** `release.py:2134-2169`. On a fix-only draft the kept price is written next to the
  new `release_hash` (line 2145), and `record_lineage(artefact_class="pricing", ...)` binds that
  price to the current design. The stale-artefact sentinel then reads the kept price as current
  for the new release, which hides a price that should be re-derived. A kept `0.0` also stays
  `0.0`.
- **Fix.** Under `fix_only`, skip the `pricing` lineage and leave `release_hash` as it was.

### F7 — LOW: `fix_only` is not part of the idempotency key
- **Where.** `chain_key("price"|"seo", slug, version, release, token)` at lines 621, 815, 891.
  `JobQueue.enqueue` deduplicates against every existing key, whatever the job's status.
  - A fix-only chain that reuses a rebuild token is swallowed without running the fix. This
    includes the empty token of the original chain.
  - An ordinary chain that later reuses a token first used by a fix-only chain is swallowed
    too.
- **Fix.** Add a `:fix` suffix to the token when `fix_only` is set, or refuse `fix_only` with
  an empty `rebuild`.

### F8 — INFO: no production caller sets `fix_only` yet, so the original findings stay open
`grep fix_only src` finds only release.py. The autonomous asset remediation in
`runtime/pipeline.py:3486` (parity escalation, `deterministic_representation`) still enqueues a
plain `assets.build`. It re-drives through `launch.plan`, `marketing.schedule` and
`store.publish`, which is the PORTFOLIO and STOREFRONT pattern. BUILD_STATE must not mark those
review findings closed until callers pass `fix_only`.

A related point: a fix-only `assets.build` still calls `image_production.trigger`
(`release.py:630`). This is keyed per release and gated, so it is not an Etsy write.

## Attack checklist results

- **Can `fix_only` be lost?** On the bounded path, no:
  - `assets.build` carries it to `pricing.position`, which passes `i` on (815 and 891).
  - `listing.seo` stops.
  - The `chain_successors` dead-end records keep it (they drop only `rebuild`) and re-drive
    with it.
  - `launch.plan`'s own `listing.seo` re-enqueue (2219) sits behind the backstop.
  - `chain.rebuild` and the `REBUILD_STAGE` graph never set it.

  The leak goes the other way: F1.
- **Can a fix-only chain reach `marketing.schedule`, `store.publish` or an Etsy write?** Not
  found. `marketing.schedule` and `store.publish` are enqueued only from `launch.plan`
  (2304, 2307), which refuses `fix_only`. `listing.seo` makes no Etsy writes.
- **Is LIVE_STATES complete?** It is functionally complete for live rows, because the Etsy id
  is an alternative test. `withdrawn` is not protected (F3), and the tuple duplicates the
  canonical one (F5).
- **Does a draft lose anything it should keep?** The price is kept. The state is reset
  (F3), and provenance and `release_hash` are advanced (F6).
- **Is the owner card well-formed and deduped?** Deduped, yes. The exact action and the
  candidate text are missing (F4).
- **Do the audits leak anything?** No. They hold the title, tags, Etsy id, state and a
  description length. No secrets and no PII.
- **Is an ordinary chain unchanged?** Yes, by code and by test. With `fix_only` absent, every
  new branch reduces to the old expression. The exception is when an ordinary chain inherits
  the flag from outputs (F1).
- **Do the tests protect every guard?** Not all. My own mutants:

  | Mutant | Result |
  |---|---|
  | M-a: drop `"active"` from `LIVE_STATES` | SURVIVES; no test uses `active` |
  | M-b: remove the `fix_only` skip in the non-Launch-0 `handle_pricing_position` (804) | SURVIVES; the fixture product `cloudline-baby-blanket` is Launch-0, so that branch is never run |
  | M-c: remove the `fix_only` skip in `_price_launch0` (876) | KILLED by test_a |

  M-a and M-b were applied together and all 5 tests still passed, so each survives on its own.

  Not covered by any test: F1 (outputs leak), F2 (profile overwrite and incident
  resolution), F3 (withdrawn), F4 (card content), `listing.seo` called directly with
  `fix_only` (the taxonomy_drift entry point), and the `chain_successors` re-drive keeping the
  flag.
