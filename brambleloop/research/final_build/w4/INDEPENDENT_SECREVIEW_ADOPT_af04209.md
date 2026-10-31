# Independent security & integrity review: `claude/w4-ADOPT` @ `af042099`

- **Base:** `origin/claude/w4-INTEG8-next` @ `b0133916`. **Subject:** `af042099`, 27 files, +1951/−35.
- **Reviewer:** an independent reviewer. I judged the code, not ADOPT.md. Date: 2026-10-31 (UTC).
- **Method:**
  - I read `publish/manual_adoption.py`, the `approvals.py` and `api.py` action route, `verify_checks.py`, the `main.api_catalogue` and `security.PUBLIC_PROJECTIONS` code, the census in `etsy_ops._expected_listings` and `_field_drift`, `etsy_verify.verify`, and every `published` literal reader under `src/`.
  - I ran the touched suite, then a suite of my own adversarial tests (Appendix A).
  - All runs were one at a time, using `PYTHONPATH=src:tests nice -n 19 python tests/<f>`.

## Verdict: **DO NOT SHIP** (as is)

The authorisation, the read-only transport and the duplicate-create guards all hold. One High finding blocks shipping:

- Accepting a baseline **narrows the census comparison** for the listing from the full certified payload to five copy fields.
- Later drift in `who_made`, `when_made`, `is_supply`, `type`, `quantity`, `materials` and `properties` is therefore silenced, permanently.
- Such drift that was already open in the halting `etsy.listing_drift:<id>` incident is resolved by the acceptance, and the owner was never shown it.

The fix is small (F-1). With F-1 fixed, and F-2 fixed or explicitly accepted, the branch is shippable.

## Test runs

| Suite | Result |
|---|---|
| `tests/test_w4_adopt_manual_listing.py` (branch) | **14/14 OK** |
| Adversarial suite (Appendix A, not committed) | 3 OK, **4 FAIL**. Each FAIL is a finding below |

The environment needed `pip install -r requirements.lock`, because fastapi was missing. No code was changed.

## Answers

### 1. Etsy writes: none found

- `manual_adoption` calls only `client.get_listing`, `get_listing_files` and `get_listing_images` (lines 210, 222 and 230). A grep finds no other `client.*(` call.
- The client is built with `build_client(..., owner_authorised=False)`.
- No other changed file introduces an Etsy call. The census changes only alter what it *compares*.
- The branch's `FakeEtsyTransport` returns 405 on any non-GET. `test_zero_etsy_write_calls_across_every_case` asserts `writes() == []` across every transport the suite builds, and that suite passed. My adversarial cases use the same transport class.

### 2. Authorisation: holds

- All three actions go through the existing `POST /api/cc/actions/{action}` route: owner session, CSRF and nonce (gate), then `require_stepup` when `ACTIONS[a][0]`.
- `adopt_manual` and `accept_baseline` are `True`. `baseline_preview` is `False`, which is acceptable: it is a read with no record.
- **Adversarial check** (`test_accept_baseline_refuses_bearer_and_replayed_nonce`, OK):
  - the operator bearer alone gets 401/403 on all three actions;
  - a replayed nonce on `accept_baseline` is refused, and no baseline is recorded.
- **Stale digest:** `accept_baseline` re-reads Etsy and refuses when `expected_digest` differs from the fresh snapshot digest ("preview changed"). The branch test covers this.
- The Product Truth checks run on that same fresh read, so nothing can change between the check and the acceptance.
- `adopt`/`accept_baseline` have no other caller in `src/`.

### 3. Duplicate publication

- **`store.publish`:** it refuses on `listing.etsy_listing_id`, which adoption sets. The unique (slug, version) `DraftIntent` row in state `ADOPTED_MANUAL` also makes `draft_intent.claim` refuse.
  - Both guards hold for an **UNVERIFIED** adoption too (`test_store_publish_and_claim_blocked_after_adoption`, OK).
- **One Etsy id, two releases:** possible under concurrency. See **F-3**.

### 4. Product Truth

- **Dropping a disclosure or contradicting the CIR:** refused. `truth_problems` runs:
  - `disclosure_on_remote` on the live title and description;
  - the `ai_assisted_design` sentence verbatim, plus any AI sentence the certified copy had;
  - the title, assembly and motif promises against the certified CIR. An exception counts as a refusal.
  - The branch test covers these. I found no bypass.
- **Silencing later drift:** **yes. See F-1 (High).**

### 5. Safety signals

- **Shadow `/api/verify` `nothing_published`:** it correctly **fails** while an adopted listing exists. It fails on `listings_with_etsy_id` and on `draft_create_intents`. The new `listings_published_manually` count is evidence only. The branch test covers this.
- **Live phases:** `everything_published_is_certified_granted_and_read_back` is **weakened** for manual listings. See **F-2 (Medium)**.
- **Literal `"published"` migration:** complete on a full grep of `src/` for `'published'`/`"published"`. Every listing-state reader now uses `LIVE_ON_ETSY` or `is_live_on_etsy`, or an explicit tuple containing `published_manually`:
  - `kpis.py:132`
  - `sustainability.LIVE_STATES`
  - `mission_runtime.py:2116`
  - `orchestrate._CLOSED_LISTINGS`
  - `benchmark_matrix.py:140`
- **Static guard:** narrow. See **F-4 (Info)**.

### 6. Data leaks: none

- `SecurityHeaders`/`PUBLIC_PROJECTIONS` limits `/api/catalogue` to `{"published": ...}` for anonymous callers.
- After an adoption, an anonymous `GET /api/catalogue` returns exactly `{"published": true}` (`test_anonymous_catalogue_sees_only_published`, OK).
- The new `why` string lists `slug@version`, which authenticated callers already see per listing. No Etsy id is added to the catalogue.
- The adoption evidence (audit rows, `DraftIntent.detail`, review incidents) is reachable only through authenticated views.
- Flipping `published` to `true` tells the public only that a listing is live, and the Etsy shop is public anyway.

## Findings

### F-1: HIGH. An accepted baseline silences drift on non-copy listing fields, and resolves such drift unseen

**Where:**
- `runtime/etsy_ops._field_drift`: `if known.get("accepted_baseline"): return baseline_drift(...)`.
- `manual_adoption.BASELINE_FIELDS = ("title","description","tags","price","taxonomy_id")`.
- `accept_baseline`, which resolves `etsy.listing_drift:<lid>`.

**What happens:**
- Without a baseline, `_field_drift` compares every field in `sent_fields(certified_payload)`: `who_made`, `when_made`, `is_supply`, `type`, `quantity`, `materials` and `properties`, plus the five copy fields.
- With a baseline it compares only the five copy fields. Nothing else compares the other fields for that listing ever again.
- `who_made` (`i_did` versus `someone_else`), `type` (`download` versus `physical`) and `is_supply` are buyer-trust and Etsy-policy fields.
- The preview (`compare()` and `differences_from_certified`) does not show any of them either.
  - If the halting P1 incident was open *because of* a `who_made` mismatch, `accept_baseline` marks it resolved.
  - The owner never saw that mismatch, and the census will not raise it again.

**Reproduction:** `test_baseline_narrows_the_fields_the_census_compares` (deterministic, with `certified_payload` patched).
- Without a baseline: `["who_made: certified 'i_did', Etsy holds 'someone_else'", "is_supply: certified True, Etsy holds False", "type: certified 'download', Etsy holds 'physical'", "properties: not returned"]`.
- With a baseline: `[]`.
- The end-to-end variant through `handle_listing_census` also reports no drift: `test_after_acceptance_policy_fields_still_drift`.
  - In the branch fixture the certified payload is missing ("taxonomy UNKNOWN"). The certified path therefore reports only "no certified payload", so the unit test is the decisive one.

**Fix:**
- In `_field_drift`, keep the certified-payload comparison for every field **not** in `BASELINE_FIELDS`, and use the baseline only for the five copy fields.
- Or add the non-copy fields to the snapshot **and** require them to equal the certified values for the acceptance to pass.
- In `accept_baseline`, resolve `etsy.listing_drift:<lid>` only when its recorded drift is entirely within the accepted fields.

### F-2: MEDIUM. In live phases a VERIFIED adoption counts as "read back verified" even when the live listing differs from the certificate

**Where:** `app/verify_checks._published_rows_proven`, the `published_manually` branch.

**What happens:**
- For an automated listing, "read back" means `etsy_ops.read_back(...)["verified"]`, which requires the fields, the files and the images to match.
- For a manual listing, the substitute is `adoption.verification == VERIFIED`. That means only "exists, and its `shop_id` is ours".
- The listing can carry a different title, drop the AI disclosure, or have files of the wrong size, and the check `everything_published_is_certified_granted_and_read_back` still passes.
- The differences are recorded and do raise a non-halting P2 review, and the census raises a P1 drift. But `/api/verify` itself reports green.

**Reproduction:** `test_live_phase_verify_does_not_prove_a_mismatched_manual_listing`.
- Adopt listing 7201 with title "Anything At All" and the AI-disclosure sentence removed. The result is `verification=VERIFIED`, with differences in title, description and disclosures.
- Then `_published_rows_proven(DB)["unproven"]` contains nothing for 7201.

**Fix:**
- Also add a reason when the adoption's recorded `differences` are non-empty and no accepted baseline covers them.
- Add a reason when the open review incident `listing.adoption_review:<slug>@<version>` or the drift incident `etsy.listing_drift:<id>` is unresolved.
- Or rename the evidence so it does not claim read-back verification.

### F-3: LOW. One Etsy listing id can be linked to two releases by concurrent adoptions

**Where:** `adopt()`.
- The "already linked to another release" check (`other = ... Listing.etsy_listing_id == lid ...`) runs in its own session, **before** the Etsy read.
- The write transaction does not re-check it.
- `Listing.etsy_listing_id` is indexed but **not unique**, and the unique `DraftIntent` key is per (slug, version), not per remote id.

**Reproduction:** `test_one_etsy_id_cannot_be_linked_to_two_releases_concurrently`.
- A second adoption for `hexagon-coaster-twin@1.0.0` runs while the first is inside `read_listing`.
- Result: `Etsy listing 7301 linked to two releases: ['hexagon-coaster-set@1.2.0', 'hexagon-coaster-twin@1.0.0']`.

**Impact:**
- Orders, stats and census attribution become ambiguous: `_expected_listings` keeps whichever row comes last.
- One release stays falsely "live".
- Severity is Low because it needs two concurrent owner step-up requests.

**Fix:** re-check, inside the write transaction, that no other `Listing` or `DraftIntent` carries `lid`. A partial unique index on non-empty `Listing.etsy_listing_id` would also work.

### F-4: INFO. The static guard is narrower than its claim

`test_no_reader_compares_listing_state_to_published_literally` matches only these patterns:

- `state ==/!= "published"`
- `by.get("published")`
- `"published" in states`

It does not catch the following:

- `.in_(["published", ...])` or `in ("published", ...)` tuples, the form five readers now use;
- `"published" == x.state`;
- a variable not named `state`.

The tree is complete today (see §5), but the guard would not catch a new reader written in those forms. Consider making it flag any `"published"` literal next to `Listing.state` or `.state`, outside `listing_state.py`.

### Notes (no action)

- An UNVERIFIED adoption can link any numeric id without any Etsy read. This is by design, so the duplicate guard holds offline. It is surfaced as UNVERIFIED in the review item and in live-phase `/api/verify`.
- On a VERIFIED adoption where Etsy returns no `shop_id`, the result is UNVERIFIED, never VERIFIED. That is correct.
- `baseline_preview` needs no step-up but does read Etsy with the owner's credential. It is acceptable as a read with an owner session, CSRF and nonce.

## Appendix A: adversarial suite (run from `brambleloop/`, alongside the branch's tests)

Not committed to any code branch. Saved here verbatim for reproduction as `tests/test_w4_secreview_adopt_adversarial.py`.

```python
"""Independent security review of claude/w4-ADOPT @ af042099: adversarial cases.

Each test asserts the SAFE behaviour. A failing test is a finding (see
research/final_build/w4/INDEPENDENT_SECREVIEW_ADOPT_af04209.md).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_secreview_adopt_adversarial.py
"""
from __future__ import annotations

import os
import traceback
import uuid
from unittest.mock import patch

import test_w4_adopt_manual_listing as T  # sets up env, sockets refused, shared DB
from fastapi.testclient import TestClient
from sqlalchemy import select

from brambleloop.app import main, verify_checks
from brambleloop.core.models import Listing
from brambleloop.publish import manual_adoption as MA

DB = T.DB
BODY = {"slug": "hexagon-coaster-set", "version": "1.2.0"}


def _adopt_and_accept(lid, live, t):
    release = T.seed(DB)
    T.adopt(DB, t, lid, release)
    with patch.dict(os.environ, T.ETSY_ENV), patch.object(MA, "_transport", lambda: t):
        shown = MA.baseline_preview(DB, etsy_listing_id=lid, **BODY)
        assert shown["acceptable"], shown["refusals"]
        MA.accept_baseline(DB, etsy_listing_id=lid, expected_digest=shown["digest"],
                           actor="owner:review", reason="review", **BODY)
    return release


def test_after_acceptance_policy_fields_still_drift():
    """Q4: accepting a baseline must not silence later drift the certified census caught."""
    lid = "7101"
    base = T.remote_listing(lid, description=T.EDITED, who_made="i_did",
                            when_made="made_to_order", is_supply=True, type="download",
                            quantity=999, materials=[])
    live = {lid: dict(base)}
    t = T.transport(live)
    _adopt_and_accept(lid, live, t)
    assert lid not in T.run_census(t)["field_drift"]
    # The owner (or anyone with Shop Manager access) changes who-made and the listing type.
    live[lid] = {**base, "who_made": "someone_else", "type": "physical", "quantity": 1,
                 "is_supply": False}
    found = lid in T.run_census(t)["field_drift"]
    assert found, ("who_made/type/quantity/is_supply changed after the baseline was accepted "
                   "and the census reported no drift")


def test_baseline_narrows_the_fields_the_census_compares():
    """Q4 (unit, deterministic): with a certified payload the census compares who_made,
    when_made, is_supply, type, quantity and materials; once a baseline exists it compares
    only title/description/tags/price/taxonomy."""
    from brambleloop.integrations.etsy import ListingPayload
    from brambleloop.runtime import etsy_ops

    lid = "7111"
    payload = ListingPayload(title=T.TITLE, description=T.EDITED, price=4.0, tags=list(T.TAGS),
                             materials=["yarn"], taxonomy_id=2856)
    good = T.remote_listing(lid, description=T.EDITED, materials=["yarn"], quantity=999,
                            who_made="i_did", when_made="made_to_order", is_supply=True,
                            type="download")
    bad = {**good, "who_made": "someone_else", "type": "physical", "is_supply": False}
    known = {"slug": "hexagon-coaster-set", "version": "1.2.0"}
    baseline = {"snapshot": MA.snapshot(good), "digest": MA.digest_of(MA.snapshot(good))}
    with patch.object(etsy_ops, "certified_payload", lambda db, s, v: payload):
        certified = etsy_ops._field_drift(DB, known, bad)
        with_base = etsy_ops._field_drift(DB, {**known, "accepted_baseline": baseline}, bad)
    assert any("who_made" in d for d in certified), certified   # control: caught without one
    assert any("who_made" in d for d in with_base), (
        f"who_made/type/is_supply drift silenced by the accepted baseline; certified census "
        f"reports {certified}, baseline census reports {with_base}")


def test_live_phase_verify_does_not_prove_a_mismatched_manual_listing():
    """Q5: in live phases a VERIFIED adoption counts as 'read back verified' even when the
    live copy differs from the certified copy and drops the AI disclosure."""
    lid = "7201"
    stripped = T.DESCRIPTION.split(" How this pattern was made")[0]
    t = T.transport({lid: T.remote_listing(lid, description=stripped,
                                           title="Anything At All")})
    release = T.seed(DB)
    res = T.adopt(DB, t, lid, release)
    assert res["verification"] == MA.VERIFIED and res["differences"]
    proven = verify_checks._published_rows_proven(DB)
    mine = [u for u in proven["unproven"] if u["etsy_listing_id"] == lid]
    assert mine, ("everything_published_is_certified_granted_and_read_back passes for an "
                  f"adopted listing whose copy differs from the certificate: {res['differences']}")


def test_one_etsy_id_cannot_be_linked_to_two_releases_concurrently():
    """Q3: the 'already linked elsewhere' check runs before the Etsy read, outside the write
    transaction, and Listing.etsy_listing_id has no unique constraint."""
    lid = "7301"
    t = T.transport({lid: T.remote_listing(lid)})
    rel_a = T.seed(DB)
    rel_b = T.seed(DB, slug="hexagon-coaster-twin", version="1.0.0")
    real_read = MA.read_listing
    fired = []

    def racing_read(db, listing_id, *, transport=None):
        if not fired:
            fired.append(1)  # a second owner tab adopts the same id for the other release
            T.adopt(DB, t, lid, rel_b, slug="hexagon-coaster-twin", version="1.0.0")
        return real_read(db, listing_id, transport=transport)

    try:
        with patch.object(MA, "read_listing", racing_read):
            T.adopt(DB, t, lid, rel_a)
    except MA.AdoptionRefused:
        pass
    with DB.session() as s:
        linked = [f"{r.product_slug}@{r.version}" for r in s.scalars(
            select(Listing).where(Listing.etsy_listing_id == lid))]
    assert len(linked) <= 1, f"Etsy listing {lid} linked to two releases: {linked}"


def test_store_publish_and_claim_blocked_after_adoption():
    """Q3: both duplicate guards hold for an UNVERIFIED adoption too."""
    from brambleloop.publish import draft_intent

    lid = "7401"
    release = T.seed(DB)
    t = T.transport({}, fail=503)
    assert T.adopt(DB, t, lid, release)["verification"] == MA.UNVERIFIED
    with DB.session() as s:
        intent = s.get(draft_intent.DraftIntent,
                       draft_intent.key_for("hexagon-coaster-set", "1.2.0"))
        assert intent.state == MA.INTENT_STATE and intent.remote_id == lid
    assert T.listing_row(DB)["etsy_listing_id"] == lid


def test_anonymous_catalogue_sees_only_published():
    """Q6."""
    lid = "7501"
    release = T.seed(DB)
    T.adopt(DB, T.transport({lid: T.remote_listing(lid)}), lid, release)
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = anon.get("/api/catalogue")
    assert r.status_code == 200 and r.json() == {"published": True}, r.text


def test_accept_baseline_refuses_bearer_and_replayed_nonce():
    """Q2."""
    lid = "7601"
    t = T.transport({lid: T.remote_listing(lid, description=T.EDITED)})
    release = T.seed(DB)
    T.adopt(DB, t, lid, release)
    with patch.dict(os.environ, T.ETSY_ENV), patch.object(MA, "_transport", lambda: t):
        digest = MA.baseline_preview(DB, etsy_listing_id=lid, **BODY)["digest"]
        body = {**BODY, "etsy_listing_id": lid, "expected_digest": digest, "reason": "x"}
        anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
        for action in ("listing.accept_baseline", "listing.baseline_preview",
                       "listing.adopt_manual"):
            r = anon.post(f"/api/cc/actions/{action}", json={**body, "release": release},
                          headers={"Authorization": f"Bearer {T.OPS}"})
            assert r.status_code in (401, 403), (action, r.status_code, r.text)
        c, csrf = T.session()
        h = T.fresh(csrf)
        r1 = c.post("/api/cc/actions/listing.baseline_preview", json=body, headers=h)
        assert r1.status_code == 200, r1.text
        r2 = c.post("/api/cc/actions/listing.accept_baseline", json=body, headers=h)
        assert r2.status_code in (401, 403, 409), ("replayed nonce accepted", r2.text)
    assert T.baseline_of(lid) is None


if __name__ == "__main__":
    failed = 0
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            try:
                fn()
                print("OK  ", n)
            except AssertionError as e:
                failed += 1
                print("FAIL", n, "--", str(e)[:400])
            except Exception:  # noqa: BLE001
                failed += 1
                print("ERR ", n)
                traceback.print_exc()
    print("failed:", failed)
```
