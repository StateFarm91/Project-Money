# INTEG7 / Batch 3 (2026-10-26): Final Master (FMBATCH1) and Agents (AGENTS) on top of Batch 2

Integrator: W-INTEG5. Branch `claude/w4-INTEG7`, worktree `.claude/worktrees/W4-INTEG7`, built from
Batch 2 (`claude/w4-INTEG6b` 413a29c, plus its deploy head 62770fbe, which carries records only).
No deploy and no production write. Every safety default stays OFF in code (§5).

## 1. Merges

| # | Branch @ head | Merge | Conflicts |
|---|---|---|---|
| 1 | w4-FMBATCH1 @ 62fcf5e (base b997efd) | 351f3e1 | DECISION_LOG and BUILD_STATE: append-only, both sides kept, 0 lines removed. The autonomy map and decision index were regenerated with their tools (43 ids). |
| 2 | w4-AGENTS @ fb68131 | c08eb54 | DECISION_LOG: both sides kept. Map and index regenerated. There were no textual code conflicts; the semantic reconciliation is §2. |
| 3 | Batch 2 deploy head 62770fbe | 9cab1b6 | Records only, so Batch 3 fast-forwards from Batch 2. |
| - | **CLOSE6 @ ff788bd** | **not merged; left for Batch 4** | A trial merge (`git merge-tree`) conflicts in code as well as in generated files: `commerce/shop_observations.py`, `launch/readiness.py`, `static/sw.js` and **`ops/deploy.sh`**. That is not a clean merge, so the `job_links` lazy-table risk does not arise here. |

## 2. Research Agent reconciled with FMBATCH1's rules (DEPARTMENTS.md breakpoints 1-5), a587022

The rules stay in `intel/research.py` (FMBATCH1). The agent, `intel/research_agent.py`, now calls them.

1. **The F-419/F-444 fields are required.** `R.open_question` gets `evidence_needed`, `stop_condition` and `if_unresolved` in two places:
   - `stale_domains_to_research`;
   - the `research.investigate` request path, where a requester may name them and otherwise the method ladder supplies the smallest action (`smallest_action(domain)`).
2. **Unresolved research stops.** The unresolved branch of `investigate` calls **`R.stop`**, which carries the escalation, instead of `R.answer(outcome, confidence)`.
3. **One stop path.** `_stop` is `R.stop`. The agent's F-420 no-change stop is kept and carries the escalation.
4. **`research.sweep` keeps only the agent's own work:** stale triggers, due investigations, and the `R.escalations` and `R.metrics` readings. `detect_unknowns`, `expire_due` and `stop_overdue` stay in `learn.scan`.
5. **`official_docs` availability follows the fetch switch.** It is available iff `research_fetch.fetch_enabled()` (`BRAMBLELOOP_RESEARCH_FETCH`, default OFF).

Which implementation survives each rule:
- **F-405:** `R.search_internal_report`, plus the agent's two extra corpora (listing memory and earlier research).
- **F-432:** open-time reuse. The agent's `prior_answer` and `STOPPED_DUPLICATE` are dropped.
- **F-444 / F-449:** `R.escalations` and `R.metrics`, with the agent's counters reported beside them.

**Found at integration:** a stale-domain episode whose research stopped would have been re-opened, and re-stopped, by every daily sweep. A STOPPED task for that trigger now covers its domain's freshness window.

**Tests** (adapted per the reconciliation note):
- `test_w4_research_agent` passes: the F-432 agent test is dropped (FMBATCH1 covers it), and the F-405, F-420, F-444/F-449, F-404 and no-evidence tests now assert the rules' outputs.
- `test_w4_fmbatch1_research` passes 13/13 and `_research_run` 11/11.

## 3. Contracts (FMBATCH1 §27)

- **The pins already match the merged tree.** `core.contract_pins.fingerprints()` on the merged tree equals `PINNED` (cir `8265022276e81c44`, listing_payload `655954b9510590d0`, api_routes `556ba71935bfe4c4`), so no `ops/CONTRACT_CHANGES.md` row or pin update is due.
- **Observation for the reviewer:** `api_routes` hashes `app.routes` only. The Command Center sub-router's routes are not in it, which is why LISTREADY's `/api/cc/launch-review*` and LAURAONE's `/api/cc/laura/*` did not move the pin.
- **AGENTS' `core/contracts.py` and FMBATCH1's `core/contract_pins.py` are both kept**, and both suites pass (`test_w4_contracts`, `test_w4_fmbatch1_contracts`).

## 4. Retention: union, and the stricter classification wins (1455592)

FMBATCH1's read-actions guard failed on the merged tree, for two reasons:
- `runtime/release_recovery.py::halted_releases` (LISTREADY) was unresolved;
- its partner actions `gate.halted` and `gate.version_conflict` were unclassified.

FMBATCH1 adds its classes with `setdefault`, so LISTREADY's literal `gate.certified: windowed` won over FMBATCH1's `lifetime_total`, which six readers need (finance.governor, finance.unit_cost, improve.presale, ops.backfill, runtime.pipeline, runtime.release).

**Fix:**
- `gate.certified`, `gate.halted` and `gate.version_conflict` are all `lifetime_total`.
- `halted_releases` is registered as a resolved read site.
- AGENTS' entries are literal, and none is weakened.

Result: `test_w4_fmbatch1_retention_guard`, `test_w4_firstsale_retention` 6/6 and `test_w4_listready` pass.

**Production note:** production 051dbee2, and Batch 2, carry the `windowed` class. The daily sweep keeps 90 days and production's audit history began 2026-10-06, so no `gate.certified` row is old enough to prune before about 2027-01-04. Batch 3 closes this.

## 5. Other cross-branch fixes (2f97964, a442b06)

| Suite | Cause | Fix |
|---|---|---|
| test_cert_spend_hosts | FMBATCH1's `ops/adoptions.py` names provider hosts as data in the F-417 register | declared as data-only; a new test pins that it imports no HTTP client |
| test_w4_fmbatch1_provider_boundary | LISTREADY's `finance/launch_review.py` imported `gateway.anthropic` | uses the neutral `gateway.providers` names (F-091) |
| test_w4_fmbatch1_departments | AGENTS' generatable job types were missing from FMBATCH1's closed WORK_CLASS | classified: family_engine and storefront.review GROW; photo_principles and research.sweep IMPROVE; gate.quality RUN |
| test_vacuity | an FMBATCH1 loop over `OWNER_KEYS + (...)` | non-emptiness assertion added |
| test_w3_tmp_hygiene | six FMBATCH1 test files lacked the `_tmp` sandbox; `ops/integrate.py` had no cleanup path for its temp directory | sandbox installed; `shutil.rmtree` in `finally` |

## 6. Edits to existing tests (from merge base to each branch)

| File | Branch | Verdict |
|---|---|---|
| test_cert_dashboard, test_customer_data_auth | FMBATCH1 | stricter: card and owner-inbox text now render only for the operator (coordinator decision 2026-10-26). The public view is asserted in `test_w4_fmbatch1_route_audit`. |
| test_deploy | FMBATCH1 | equivalent: the same three strings, each asserted with a diagnostic |
| test_w4_research | FMBATCH1 | adapted to the stricter `R.answer` (effect and conclusion required) |
| test_roles | AGENTS | stricter: job types moved off the not-yet-handled list once their handlers existed |
| test_route_auth_default_deny | AGENTS | the new owner storefront-grant router is added to the owner-auth prefixes |
| test_w4_finhealth | AGENTS | `research_agent` and `storefront_director` join the CA$0-by-declaration agents |
| test_w4_store_live_state | AGENTS | "no `update_shop` method" becomes "no **ungated** shop write". This follows the owner directive of 2026-10-21. The test now proves nothing is sent in shadow, without a grant, or for owner-configured or EU-only fields, and that no banner or icon write exists. |
| test_w4_close5_rows, test_w4_listready | AGENTS | additions only |

## 7. Safety defaults (all OFF in code)

| Default | Switch | Off unless |
|---|---|---|
| Auto-rollback | `ops/deploy.sh` `AUTO_ROLLBACK` | set; a standing `AUTO_ROLLBACK_REASON` is refused (`test_w4_fmbatch1_rollback`) |
| Taxonomy requeue | `BRAMBLELOOP_TAXONOMY_DRIFT_REQUEUE` | it is "1" |
| Research fetch | `BRAMBLELOOP_RESEARCH_FETCH` | it is "1" |
| Storefront writes | `BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED` | it is set, and an owner grant also applies |
| Laura | `BRAMBLELOOP_LAURA_UNIFIED`, `_CEO_MODEL`, `_BUSINESS_TO_VENICE`, `_PRIVATE_REGISTER` | each is set (unchanged from Batch 2) |

## 8. Focused suites

122 suite files ran:
- every test that FMBATCH1 and AGENTS added or changed (104);
- the required set;
- research, retention, contracts, spend, PWA, tmp hygiene and cert_wiring;
- the Laura and listings suites.

First pass: 116/122. The 6 failures were fixed as in §4-5 and rerun; all pass.

## 9. Full suite and gates

(pending)
