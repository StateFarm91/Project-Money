# Independent security and integrity review: W4-LISTREADY (with FIRSTSALE2)

- **Reviewed:** `origin/claude/w4-LISTREADY` @ d45e033, against `origin/claude/final-candidate-b997efd`.
  This includes `origin/claude/w4-FIRSTSALE2` @ ade23d2, merged in at c2e60b6.
- **Diff reviewed:** `brambleloop/src` and `brambleloop/tests`: 13 files, about +1330/−59.
  I also read `research/final_build/w4/LISTREADY.md` and `FIRSTSALE2.md`.
- **Reviewer:** an independent reviewer that did not write this code. Review only: nothing was
  fixed, deployed, posted or paid for, and no secrets were used.
- **Date:** 2026-10-21 (UTC).
- **Local test runs (nice 19):**

  | suite | result |
  |---|---|
  | `test_w4_listready` | 11/11 |
  | `test_w4_firstsale2_surfaces` | 7/7 |
  | `test_w4_etsysurf` | 8/8 |
  | `test_etsy_surfaces` | 53/53 |

  `test_product_run` and `test_cert_wiring` were not run, as instructed.
- **Reproductions:** both findings below were confirmed with a script built on the branch's own
  test helpers. The script is in the appendix.

## Verdict: **BLOCKER**

One change classes a genuinely stale artefact of the product's **current** state as
`superseded`. It then raises no halt, closes the existing halt, and never queues the rebuild.
That is finding F1: unversioned marketing assets are matched by fingerprint to an older release.

A second defect, F2 (HIGH), lets publication treat a non-newest release as the newest. R3 makes
this path reachable.

The other fixes hold up:

- **R1** for versioned artefacts is sound.
- **R3, R4, R5, the `superseded_release` guard and the `chain.rebuild` comparison fix** do not
  weaken any gate.
- **FIRSTSALE2:** I found no way to forge an observation without owner authentication, and no
  path that turns UNKNOWN or STALE into FRESH.
- **The refused `gate.certify` relaxation is absent.** `runtime/pipeline.py`, `gates/`,
  `ops/incident_lifecycle.py`, `ops/rebuild_graph.py` and `core/` are untouched by the diff.
  `handle_certify` still halts on `publication_halted`
  (`runtime/pipeline.py` `handle_certify`, Gate E).

| # | severity | area | one line |
|---|---|---|---|
| F1 | **BLOCKER** | R1 | Stale live marketing copy of the current product is classed `superseded`: no halt, the old halt is closed, and no rebuild is ever queued |
| F2 | HIGH | R1 + R3 | "Newest" is the highest PatternVersion **id**, not the highest version. An out-of-order certification (an R3 retry of an older halted version) makes the real newest release "superseded" and lets the older one publish |
| F3 | MEDIUM | R3 | `retry_halted` re-certifies an old halted CIR as recorded, with no check that it is still the design the code defines for that slug@version, or that no newer release exists |
| F4 | LOW | R4 | When the marketing rebuild exception applies, all `for_marketing` reasons are cleared, including the unreviewed-platform-policy block (#39). This was already true; R4 makes it apply more often |
| F5 | LOW | R3 | A retry and a normal `certify:` job for the same slug@version can both run (different keys), giving a duplicate re-certification |
| F6 | LOW | tests | The `chain.rebuild` comparison fix has no test of its own. One edited assertion now greps source code instead of checking behaviour |
| F7 | LOW | FIRSTSALE2 | An owner observation's `recorded_by="owner"` is asserted, not proven: anyone holding the operator credential can attest `identity_verified: true`. There is no nonce, although a replay cannot refresh a reading |
| F8 | INFO | R1 | Versioned artefacts of an older release are correctly `superseded`. Their safety depends entirely on every publication path calling `for_publish` |

---

## F1: BLOCKER: stale live marketing copy is classed `superseded` through fingerprint matching

**Where:**
- `brambleloop/src/brambleloop/ops/artefacts.py:547-553` (`built_from_version`, the
  unversioned branch);
- `ops/artefacts.py:591-600` (`check`: superseded, then `continue`);
- `ops/artefacts.py:838-845` (`sweep` closes the incident);
- test `brambleloop/tests/test_w4_listready.py:123`.

**What is wrong.** Marketing assets are `ContentPiece` rows. They are keyed
`marketing_key(slug, channel, title)` = `slug:channel:<sha16(title)>` (`ops/artefacts.py:383`).
That key has no version: one live row exists per product, channel and title, and that row is
the product's current marketing copy, whatever release it was written from.

`built_from_version` matches such a row to "the release it was built from" by its recorded
`cir:` and `release:` fingerprints. Every certified release has a distinct `cir_json`, so
marketing copy written for 1.0.0 always matches 1.0.0 exactly. When 1.1.0 is certified, the
1.0.0 copy is classed `SUPERSEDED`, and then:

1. No stale-artefact incident is raised, so the product is not halted.
2. Any existing `stale-artefact:marketing_asset:…` incident is **closed** with the resolution
   "superseded, not stale".
3. `rebuild_graph.publication_gate` only counts `STALE` verdicts (`rebuild_graph.py:319`), so
   the copy never appears in `outstanding`. `marketing.schedule` is therefore never asked to
   rebuild it. R4's rebuild exception never fires for it either.
4. `superseded_release` only checks the **release version being published** (1.1.0, the
   newest), so it passes.

The copy is not an artefact of a superseded release. It is the product's live marketing, and
it describes a design the product has moved past. This is the exact staleness the sentinel
exists to catch: for example, a pin or email stating 1.0.0's yardage, size or colours next to
the 1.1.0 listing. The old logic flagged it. The new logic hides it permanently.

The branch's own test `test_an_unversioned_marketing_asset_is_matched_to_the_release_it_was_built_from`
asserts this misclassification as intended behaviour. Its "still judged stale" case uses a
fabricated fingerprint (`{"rows": 99}`) that matches no release. A real stale piece always
matches its own old release, so the test never exercises the realistic case.

**Concrete scenario (reproduced, appendix part A).**
1. `hex@1.0.0` is certified, and marketing copy is written from it.
2. `hex@1.1.0` is certified.
3. With the b931d17 logic the result is `stale 1`, `publication_blocked ['hex']`.
4. With the LISTREADY logic:
   - the verdict is `superseded`;
   - `publication_blocked [ ]`;
   - `publication_halted('hex')` is False;
   - `rebuild_graph.publication_gate` gives `may_publish True` with `outstanding []`;
   - `staleness(hex).blocks` is False;
   - `superseded_release(hex, 1.1.0)` is False.

   So `for_publish(hex, 1.1.0)` has no staleness reason left. The 1.0.0 copy stays drafted
   for the product and is never rebuilt.

**Effect on the P0 threshold.** `incident_lifecycle.systemic_evidence` is unchanged, so the
threshold is the same. But this class of genuine staleness no longer produces incidents, so it
can no longer contribute to tripping the P0. The test that the P0 "trips at the same threshold
for genuine staleness" only covers versioned PDF and certificate artefacts.

**Today's exposure.** I found no code path that posts `ContentPiece` rows externally on its
own: they are drafts, readiness counts and dashboard content. The defect is still a BLOCKER for
two reasons:
- it removes a publication-halting condition on the product's listing (a gate weakening);
- it makes stale copy permanently invisible to the rebuild graph, which is the mechanism that
  would ever correct it before a channel posts it.

**Recommended fix (narrow).**
1. Allow `SUPERSEDED` only for **versioned** keys (`slug@version…`). Remove the fingerprint
   match for unversioned keys in `built_from_version`, so it returns None for them, and judge
   them against the newest release as before. A marketing piece written from an older release
   is then STALE again.
2. R4 already makes that staleness rebuildable: the sentinel's own marketing rows no longer
   block the marketing rebuild. So restoring STALE does not bring back the deadlock. The
   rebuild re-records the piece from the newest release, and the incident clears as FRESH.
3. Replace the test at `test_w4_listready.py:123` with this assertion: marketing copy written
   from 1.0.0 is STALE and halting after 1.1.0, and `marketing.schedule(rebuild=True)` clears
   it.

## F2: HIGH: "newest release" is the highest PatternVersion id, and R3 makes that reorderable

**Where:**
- `ops/artefacts.py:922` (`current_from_db`: `version.id > latest.id`);
- `ops/artefacts.py:935`;
- `publish/release_gates.py:1374` (`superseded_release`: `max(rows, key=id)`);
- `runtime/release_recovery.py:70-93` (`retry_halted`).

**What is wrong.** Both the sentinel's `latest_version` and the new publication guard define
"newest" as the release whose PatternVersion row was **inserted last**. They do not compare
version numbers. `gate.certify` has no check that a version being certified is at or above the
product's newest certified version (`_version_conflict` only checks the same version).

`retry_halted` re-enqueues every release whose latest certify attempt was halted. It never asks
whether a newer version of that slug has been certified since: `halted_releases` ends an
episode only on an outcome for the **same** `slug@version`. If 1.5.0 was halted and 1.6.0 later
certified, the retry certifies 1.5.0 after it. `_persist_release` then inserts a row with a
higher id, and:

- every artefact of 1.6.0 (the real current release) is classed `SUPERSEDED`: no halt, and
  its open incidents are closed;
- `superseded_release` refuses to publish 1.6.0 and **allows 1.5.0**.

**Concrete scenario (reproduced, appendix part B).**
- Rows are inserted in the order 1.1.0, then 1.0.0.
- The 1.1.0 PDF reads `superseded`.
- `superseded_release(hex, 1.1.0)` gives `superseded True, newest '1.0.0'`.
- `superseded_release(hex, 1.0.0)` gives `superseded False`.

This answers the review question "Can publication ever pick a superseded or non-newest
release?": yes.

**How it is reached.**
- On first deployment, `retry_halted` scans the **whole** audit history of `gate.halted` (for
  example, winter-village-graphghan@1.3.0 halted on 10-12).
- Within one `chain.rebuild`, redrafts of a newer version and retries of an older one are
  queued together and run in any order.
- Any older version halted while a newer one certifies afterwards will reorder.

**Recommended fix.**
1. Define "newest" in `current_from_db`, `_superseded_lookup` and `superseded_release` by
   parsed version (semantic-version order), using the id only to break ties. Or refuse in
   `gate.certify` any version below the product's newest certified version.
2. In `retry_halted`, skip a halted release when the slug has a certified version above it.
   Record it as `superseded_by_newer` rather than retrying.

## F3: MEDIUM: R3 certifies the halted CIR as it was recorded, without re-deriving it

**Where:** `runtime/release_recovery.py:77-91`.

`retry_halted` takes `cir` from the halted job's inputs (the job id in the `gate.halted`
audit). That matches the recorded CIR exactly, which answers "certify with a CIR that differs
from the recorded one?": no. But it is the CIR as it stood when the halt happened, which may
have been days earlier.

If the code's design for that `slug@version` changed during the halt, the retry certifies the
**outdated** design under that version. The version is then immutable (PT-03), so the normal
chain's later certify of the current design is refused as `release.version_immutable`, a P2.
That fixes a wrong design under a version number and needs a manual version bump to recover.

The retry also carries the halted job's `DOC_VERSION`, so the certificate can be one document
version behind. `chain.rebuild` then redrafts it, which is wasted work but not unsafe.

**Recommended fix.** Retry by re-entering the chain rather than by replaying certify:
- enqueue `cir.draft` or `cir.compile` with the current engineered CIR for the slug;
- or retry only when the recorded CIR's fingerprint equals the code's current CIR for that
  `slug@version`, and record `design_moved` otherwise.

**Other R3 properties checked (all OK):**
- **No retry while halted.** It checks `IncidentTracker.publication_halted`, the same
  predicate Gate E uses, and `gate.certify` re-checks it anyway.
- **One retry per episode.** The key is
  `certify-after-halt:<slug>:<version>:<halt audit id>`, and the audit id is unique.
- **No storm.** Each further retry needs a new halt and that halt clearing.
- **No key collisions.** The prefix differs from the `certify:` keys.
- **No guessed input.** With no CIR on record it records "no_cir_on_record" rather than
  guessing.

## F4: LOW: the marketing rebuild exception also clears the platform-policy block

**Where:**
- `runtime/release.py:2236-2241`, which sets `reasons: []` when `only_own_marketing_stale`;
- `publish/release_gates.py:1268-1273`.

`outstanding_only_marketing` does not consider `policy_changes_unreviewed`. When the flag is
true, `marketing.schedule` sets `blocks False` and drops **every** reason, including
"platform policy changed (#39)".

This was already the case before R4. R4 makes the flag true in more states: it is now true
while the sentinel's own marketing rows are halting, which was previously impossible.

Otherwise R4 is correctly narrow:
- `own_marketing` contains only the `stale-artefact:marketing_asset:<key>` signatures of
  exactly the outstanding marketing nodes;
- any other halting incident, including the company-wide `systemic-halt:*` row that
  `open_incidents(slug)` returns, refuses the rebuild;
- `halted`, `reasons` and `blocks`, the fields `for_publish` reads, are unchanged.

So publication reads exactly what it read before, and no product with a non-marketing halt can
rebuild or publish through R4.

**Recommended fix.** Add `and not policy` to `only_marketing`.

## F5: LOW: possible duplicate certification of one slug@version

The R3 retry key and the normal chain key `certify:<slug>:<version>:<fp>:d<DOC>` differ. If a
redraft re-enqueues the normal path for the same version while a retry is pending, both run.
`_version_conflict` allows identical content, so the result is two `gate.certified` and a
`gate.recertified` audit. It does not produce wrong content.

**Recommended fix.** Skip the retry when an unfinished `gate.certify` job exists for the same
`slug@version`.

## F6: LOW: test coverage and an edited assertion

**Missing test for the `chain.rebuild` fix.** No test covers the comparison fix at
`runtime/release.py:4409`. I reasoned about it instead:
- `cir_json` is written through SQLAlchemy's JSON column, so it holds only JSON-native values;
- `json.loads(json.dumps(..., default=str))` only normalises tuples to lists and int keys to
  str keys;
- any real value change still differs, so real design changes are still detected.

Add a test: an unchanged design is not redrafted, and a one-row change is.

**Edited test assertions.**

- `tests/test_etsy_surfaces.py:534-550` was edited.
  - **Before:** it checked the owner action's behaviour (`transactions_r` in the action text,
    "browser" in `why_software_cannot`).
  - **After:** the orders surface has no standing action, and that part is a behaviour check
    (`owner_queue` excludes the key).
  - **Weaker part:** "only the owner, in a browser" is now checked by grepping
    `inspect.getsource(orders_ingest.gate)`, a source-text check rather than a behaviour check.
  - **Verdict:** the change reflects a real behaviour change and not a removed guarantee.
    Prefer asserting on `gate()` output with `transactions_r` missing.
- `tests/test_w4_etsysurf.py:59-78` was edited. It still asserts `ready is False`, and that
  every unread surface is `NO_EVIDENCE`. Not weakened.
- No other existing test file was edited.

## F7: LOW: owner attestation for FIRSTSALE2 observations

**Where:** `commerce/estate_api.py` `shop_observation` (unchanged) and
`commerce/shop_observations.py` `record` and `SATISFIED`.

**Authentication: OK.** `POST /api/etsy/shop-observation` requires the operator credential
through `opsauth.check`. With no token configured it returns 503; with a wrong or missing
token it returns 401. It cannot be posted without that credential.

**Validation: OK.**
- `observed_at` is required and cannot be in the future.
- `complete` must be a bool.
- A statement is required.
- `messages` needs `notifications_inbox` to be text and `reply_window_hours` to be a number
  above 0. A bool is rejected, and NaN fails the `> 0` check.
- `legal_and_tax` needs `identity_verified is True`, plus `tax_position` and `decided_on` as
  text. `decided_on` is parsed as ISO when present.

**Replay.** A replayed body re-records the same `observed_at`, so its age does not reset and a
replay cannot make a reading fresh. A forged reading needs the credential.

**Remaining gaps.**
- The credential is a shared operator token, so `recorded_by="owner"` is a claim. Any
  automation holding the token could attest `identity_verified: true` and close
  `legal_and_tax_setup`, which concerns KYC and tax.
- `decided_on` may be a future date.

**Recommended fix.**
- Bind these two pages to an owner-only credential or a signed owner session, distinct from the
  heartbeat's token.
- Reject a future `decided_on`.

**Freshness: OK.** UNKNOWN or STALE is never treated as FRESH:
- **`evidence_state`:** no record or no `observed_at` gives NO_EVIDENCE; an age below 0 or
  above the maximum gives STALE; `satisfied False` gives FAILING; only otherwise FRESH.
- **Readiness:** requires every row to be FRESH.
- **Collectors** return None when they have nothing:
  - orders: no ingest that ran;
  - taxonomy: no snapshot;
  - digital files: every release UNKNOWN;
  - observations: no observation.
- **Unknown inside a reading is a gap.** Digital-file UNKNOWN releases are gaps, so
  `satisfied` is False.
- **Unreadable is no evidence.** `readings()` turns any exception into None.
- **`orders.observed_at`** is the time of the last ingest that ran, not the current time, with
  `max_age_days=1`.
- **`digital_files.observed_at`** is the current time, but each call re-hashes the PDFs from
  durable storage, so that reading is genuinely current.

## F8: INFO: R1 for versioned artefacts is sound; it depends on `for_publish`

For keys like `slug@version…`, `built_from_version` returns that version only when it exists
for the slug. The `[^#]+` version group means that `slug@1.0.0:pdf` yields `1.0.0:pdf`, which
is not a known version, so the answer is None and the artefact is judged against the newest
release, as before.

| question | finding |
|---|---|
| **Spoofing:** a key naming a newer version than the artefact was built from | its recorded inputs differ from that version's own, so it reads STALE |
| **Spoofing:** a key naming an older version | it reads superseded, but publication refuses that version |
| **Missing link** (no `cir:` input, or ambiguous: more than one matching version) | None, so it is judged against the newest release |
| **Same release** | `own == current` for the newest release, so the comparison is unchanged |
| **Re-certification** of the current release with a new `release_hash` | still STALE (tested) |

The `superseded_release` guard is wired into `for_publish`. It treats an unreadable state as
"superseded" (a refusal), which is correct. `for_publish` is reached from
`runtime/pipeline._release_gates` (`listing.export`) and `products/inventory.py`.

I did not verify that every Etsy write path reaches `for_publish` (for example, listing renewal,
or keeping a live listing of an older release active). Superseded artefacts of a live
older-release listing no longer raise any halt, so any such path is now unguarded by the
sentinel. That needs checking before LIMITED PRODUCTION.

**R5: OK.**
- `seed_launch0` only enqueues `cir.draft` `{slug}` with the key
  `launch0-seed:<slug>:<version>:<fingerprint>:d<DOC>`, one per run.
- The draft goes through the normal `handle_cir_draft`, then `cir.compile` (deterministic
  `compile_cir`), then `gate.certify` (Gate E and the full certificate).
- It certifies, lists and publishes nothing itself.
- A refused design keeps its key and is not retried until its fingerprint or `DOC_VERSION`
  changes. The next pending release is seeded instead, so there is no storm.

---

## Appendix: reproduction (run from `brambleloop/` with `PYTHONPATH=src:tests`)

```python
import test_w4_listready as T
from brambleloop.ops import artefacts as P, rebuild_graph
from brambleloop.publish import release_gates as RG
from brambleloop.gates.incidents import IncidentTracker

# A) F1: marketing copy written for 1.0.0 is the live copy; the product moves to 1.1.0
db = T._db()
T._pv(db, "hex", "1.0.0", {"rows": 12, "yards": 100}, "a" * 64)
T._record_from(db, "hex", "1.0.0", cls="marketing_asset",
               key=P.marketing_key("hex", "pin", "Hex: 100 yards"))
T._pv(db, "hex", "1.1.0", {"rows": 14, "yards": 140}, "b" * 64)
new = T._sentinel(db)                                   # old_logic=True gives stale 1, blocked ['hex']
# -> [('hex:pin:43d36b484a4e94bf', 'superseded')], publication_blocked []
IncidentTracker(db).publication_halted("hex")           # False
with db.session() as s: rebuild_graph.publication_gate(s, slug="hex")  # may_publish True, outstanding []
RG.staleness(db, slug="hex")["blocks"]                  # False

# B) F2: 1.1.0 certified first, then an older 1.0.0 certifies (e.g. an R3 retry)
db3 = T._db()
T._pv(db3, "hex", "1.1.0", {"rows": 14}, "b" * 64); T._record_from(db3, "hex", "1.1.0")
T._pv(db3, "hex", "1.0.0", {"rows": 12}, "a" * 64)
T._sentinel(db3)                                        # hex@1.1.0#pdf-us -> superseded
RG.superseded_release(db3, slug="hex", version="1.1.0") # superseded True, newest '1.0.0'
RG.superseded_release(db3, slug="hex", version="1.0.0") # superseded False
```

Observed output on d45e033:

```
A old logic: 1 ['hex']
A new logic: [('hex:pin:43d36b484a4e94bf', 'superseded')] []
A halted: False
A rebuild graph: True []
A staleness blocks: False superseded_release(1.1.0): False
B verdicts: [('hex@1.1.0#pdf-us', 'superseded')]
B 1.1.0 superseded? {'superseded': True, 'newest': '1.0.0', ...}
B 1.0.0 superseded? False
```
