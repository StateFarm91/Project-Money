# Handoff — v1.1 lane G (SEO / keywords / taxonomy / search intelligence)

Branch `claude/v11-G`, base `claude/visual-investigation` @ 0694fb7. Phase stays SHADOW; no
network calls, no Etsy writes, no spend. Audit: `SEO_AUDIT.md` (same directory).

## Requirements

| ID | Status | Notes |
|---|---|---|
| Directive §11 (continuous SEO loop) | PARTIAL | `seo.jobs.run_cycle` implements observe → decide → propose → measure → re-evaluate, idempotently. It is not scheduled until the WIRING REQUEST below is applied. Learning from measured data is coded but has no real input yet (no live shop) |
| F-002/F-020 evidence with provenance | COMPLETE | `seo_keyword_evidence`: every row has a source, source_ref, basis, use and fingerprint. Real state: 42 phrases, all `modelled` |
| F-005/F-006 deepest truthful category, readiness | GATED (etsy_api) | `seo.taxonomy.readiness`: 5/5 Launch-0 variants read `GATED(etsy_api)`. CONFIRMED needs an Etsy-read snapshot (`source=etsy_open_api_v3` and `confirmed_at`, which only `etsy_taxonomy.refresh` sets). 2112/2114/2115 are fixture ids and are never reported as a product's category |
| F-007/F-008 attributes | COMPLETE (proposal level) | Proposed from twin facts; `attribute_truth` plus `check_attributes` give 0 problems on all 5 variants. Etsy property payload still needs the snapshot (GATED) |
| F-011/F-021/F-023/F-245 13 tags, no stuffing, readable titles | COMPLETE | All 5 proposals: 13 tags, each ≤20 chars, titles 92–107 chars (≤140). Limits are cited from `commerce/seo.py`, `commerce/search.py` and `publish/listing_schema.py` |
| F-918 anti-gaming SEO KPIs | COMPLETE | `seo.truth.validate_listing` blocks untraceable, stuffed, competitor-name, third-party-brand, protected-IP and misleading terms. Evidence never overrides truth (tested: an "earning" competitor term is rejected). Each KPI in `summary()` carries a basis, and `guardrails` are listed |
| F-929 no hallucinated action | COMPLETE | Proposals only (`writes_to_etsy: False`, and the package imports no Etsy client, which a test checks). An unconfirmed category stays GATED. UNKNOWN is never shown as 0 |
| #237 keyword outcome measurement | COMPLETE (code) / UNKNOWN (data) | `seo.measure.attribution`: Stats-export term → ATTRIBUTED (estimated, sole live carrier) / UNATTRIBUTABLE / SHOP_LEVEL_ONLY. Confidence is capped at `moderate`. Listing outcomes are never split across tags. No real data exists yet |
| Provider `brambleloop.seo.status.summary(db)` | COMPLETE | Contract keys plus `reason`, `kpis`, `guardrails`, `taxonomy`. Never raises. Returns UNKNOWN on an empty or unmigrated DB, and DEGRADED/modelled after a cycle (categories gated) |
| `brambleloop.seo.status.next_work(db) -> list[dict]` | COMPLETE | Item keys: key, department, title, kind (internal/owner/gated), action, priority, gated_by, why, external_effect (always False), sources. Documented in the `seo/status.py` docstring |

`db` is the repo's `core.db.Database`, which is what every existing provider takes. A bare
SQLAlchemy `Session` is also accepted (tested). With a bare Session the caller owns the
transaction: the code flushes but never commits it.

## Files
Created (all new):
- `src/brambleloop/seo/`: `__init__.py`, `_db.py`, `models.py`, `facts.py`, `evidence.py`, `truth.py`, `proposals.py`, `taxonomy.py`, `measure.py`, `jobs.py`, `status.py`, `handler.py`, `_testkit.py`
- `tests/test_v11_seo_truth.py`, `tests/test_v11_seo_proposals.py`, `tests/test_v11_seo_taxonomy.py`, `tests/test_v11_seo_cycle.py`
- `research/final_build/v1_1/SEO_AUDIT.md`, `research/final_build/v1_1/handoff_G.md`, `research/final_build/v1_1/evidence/G_seo_cycle_proof.json`

Modified: none. No existing module was edited.

## Tests
`cd brambleloop && SUITES="test_v11_seo_truth test_v11_seo_proposals test_v11_seo_taxonomy test_v11_seo_cycle" PY=python3 bash run_tests.sh`
gives **TOTAL PASSING: 29 ; suites failing: 0** (truth 9, proposals 8, taxonomy 4, cycle 8).

Existing tests run for regression (unchanged modules that this package reuses):
- `tests/test_search_truth.py`: 32 passing, 0 failing.
- `tests/test_vacuity.py` and `tests/test_secret_scan.py` each have one failing test, and both failures are in files this lane does not own:
  - vacuity flags `test_launch0_listing_truth.py:272`, `test_pattern_truth.py:125` and `test_web_security.py:272`;
  - secret scan flags `tests/test_rc1_ord2.py:169`.
  Neither test flags any lane-G file.

## Runtime proof
`evidence/G_seo_cycle_proof.json` comes from a fresh hermetic SQLite database (`create_all`, no network). What it shows:
- **Before the first cycle:** `summary` returned UNKNOWN ("seo tables not created"), and `next_work` returned `seo.run_cycle`, `seo.taxonomy_confirm` (gated by etsy_api) and `seo.stats_export` (gated by live_listings).
- **Cycle 1:** `changed: True`, 104 evidence rows, 5 proposals written.
- **Cycle 2:** `changed: False`, nothing written, same fingerprint.
- **After the cycles:**
  - `summary` returned DEGRADED with basis modelled and reason "proposals ready; taxonomy not confirmed (GATED(etsy_api))".
  - All 5 proposals are `ok`.
  - `next_work` now lists only the two gated items.

## WIRING REQUESTS (integrator applies; lane G does not own these files)
1. `src/brambleloop/core/db.py`, in `Database.create_all`, after the `search_visibility` import:
   ```python
   from ..seo import models as seo_models  # noqa: F401; v1.1 lane G SEO tables
   ```
   Until this is applied, `run_cycle` creates its tables itself via `seo.models.ensure_tables`.
2. `src/brambleloop/runtime/pipeline.py` (or `app/runner.py` next to `from ..runtime import pipeline`): register the handler:
   ```python
   from ..seo import handler as _seo_handler  # noqa: F401  -- registers seo.cycle
   ```
3. `src/brambleloop/runtime/worker.py` `CADENCES`, next to `("etsy_taxonomy", ...)`:
   ```python
   # v1.1 §11: continuous SEO; idempotent, no external effect.
   ("seo_cycle", "listing", "seo.cycle", 6 * 60 * 60),
   ```
4. `src/brambleloop/agents/registry.py`, `listing` agent `allowed_job_types`: add `"seo.cycle"`.
5. `src/brambleloop/swarm/orchestrate.py` `JOB_BANDS`: add `"seo.cycle": "housekeeping",` (or the band the integrator prefers for read-and-propose work).
6. Lane A orchestrator: consume `brambleloop.seo.status.next_work(db)`. Run only `kind == "internal"` items. Never run `gated` items.
7. Lane C: `brambleloop.seo.status.summary(db)`.

No change to `runtime/release.py` is required. The release chain keeps drafting listings as it does today. A proposal that differs from the current draft appears in `next_work` as `seo.adopt:<slug>`. Adopting it into the release chain (for example, `listing.seo` reading the newest PROPOSED `seo_proposals` row) is a later decision for the integrator. It is not wired here.

## Open defects / limits
- `facts.DELIVERABLE_WORDS` treats "written + chart, US and UK terms, PDF" as true of every Launch-0 release. That follows `runtime.release` (`assets.build` renders the US and UK PDFs). It was not re-verified per product here.
- The vocabulary is broad by design: it includes CIR-title words, identity qualifiers and category shelf phrases. Traceability proves that a term names a fact; it does not judge whether the term is commercially wise.
- The third-party brand list in `truth.THIRD_PARTY_BRANDS` is a tripwire, not a register. The traceability rule is the real backstop.
- With a bare Session, a failed audit-row insert leaves that Session needing a rollback (the Database path is isolated).

## Could not verify
- Real Etsy taxonomy ids and property schemas (the `etsy_api` gate is closed).
- Any measured search demand or outcome: no Insights entries, Stats export, SERP reads or live listings exist.
- Scheduled execution under the real worker (not wired; the handler was tested by direct call).
