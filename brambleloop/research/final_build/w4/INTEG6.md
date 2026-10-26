# INTEG6 / Batch 2 (2026-10-26): Unified Laura on the listings release, certified

Integrator: W-INTEG5. **No deploy was made.** Production is 051dbee2, the listings release, re-read
by `ops/deployed_sha.py` at about 16:20Z. Every Laura switch is OFF by default in code.

## Certified candidate

| | |
|---|---|
| Suite SHA | **`413a29cfe05830b49d95d284e6fd416ad568c58f`** (`claude/w4-INTEG6b`; frozen as `claude/final-candidate-413a29c`) |
| Deploy head | **`62770fbe`** = 413a29c, then release record 068450b6, then the DEPLOYED_HISTORY commit. Records only; the tree digest is unchanged. |
| Contents | listings 09acd42 + deploy head 051dbee2 (records); LAURAONE 2c29b42 + LAURAFIX 3b9c4f5 (Q-1..Q-6), reviewed NO BLOCKER; INTEG harness fix (Venice refused under `enabled(None)`; state restored before the S-5 raise); the INTEG6b fixes (below) |
| Full suite | run `20261026T134040Z-24420`: 684 suites, 9612 s. **9204 passing, 0 failing, release_eligible true** |
| deploy_guard record | `RELEASE_413a29cf….json`, tree_sha256 `46ac33c9c0dc…` |
| `DRY_RUN=1 sh ops/deploy.sh --deployed 051dbee2…` | forward **ALLOW**; built-in rollback rehearsal **ALLOW** (`evidence_INTEG6/dryrun_413a29c.txt`) |
| Rollback rehearsal | to 051dbee2: **ALLOW**; to 15800536: **ALLOW** (`rollback_413a29c.txt`) |
| Migration (PostgreSQL 16, full lazy surface; `pg_batch2.txt`) | from 051dbee2 (145 tables), +2: `laura_cost_events` and `laura_boundary_crossings`. No existing column changed. The second boot is a no-op. 051dbee2 boots the upgraded schema cleanly. |
| DEPLOYED_HISTORY | adds 051dbee2 with the operator's deploy evidence. The 15800536 entry is reconciled with INTEG4's 1eaf0f44 evidence: still one entry per SHA, no duplicate. |

## Defects fixed at integration

| Commit | Defect |
|---|---|
| 1e44bd7 | test_vacuity: LAURAFIX's new Q-1 loop had no non-emptiness assertion. One was added; the test is stricter. |
| 10cfefe | **Product bug.** `views/laura_unified.js` passed `"aria-label"` to `h()`. `dom.js` refuses that attribute, so the unified view threw on any thread with an owner turn. Fixed with `aria: {label}`. |
| 10cfefe | Three Laura test files were missing the `_tmp` sandbox (test_w3_tmp_hygiene). |
| 10cfefe | The CC browser mock lacked `/laura/converse` and `/laura/unified/status`. It now answers exactly as the real routes do with every switch OFF. No check was changed. |

## Owner note: production behaviour with every switch OFF, 051dbee2 → Batch 2

**1. The CEO briefing (the one deliberate difference).**

| | Production 051dbee2 today | Batch 2 with every switch OFF |
|---|---|---|
| **Model call** | **Yes.** `talk.converse` → `briefing.answer` → `gateway.laura_briefing.synthesize` calls Laura's model (routing task, Anthropic) whenever an API key and Laura's daily permission exist. | **No.** `laura_briefing.synthesize` returns `unavailable` ("Business Laura's model is switched off", `BRAMBLELOOP_LAURA_CEO_MODEL`), and the deterministic sectioned briefing is shown. |
| **Routes it reaches** | the briefing intents of `POST /api/cc/laura/ask` (the CC Ask form) and `presence.respond` (`POST /api/cc/laura/presence…`, the text/voice presence turn) | the same two |
| **CC Ask form posts to** | `/api/cc/laura/ask` | `/api/cc/laura/converse`. With the switch OFF it returns the same deterministic `talk.converse` turn, plus `model.source: "not_called"`. |
| **Cost** | the synthesis is billed to Laura's daily budget | CA$0 for the briefing |

**2. Other differences visible to users with every switch OFF.**
- **Non-briefing answers are unchanged.** The phrasing call (`laura_phrase`) still runs as in production.
- **Private Laura (the owner-private register).** The reply now requires `BRAMBLELOOP_PRIVATE_PROVIDER=venice` and a Venice key; `@3` runs only on Venice (`REGISTER_NEEDS_VENICE`).
  - If production today has the private reply enabled on the Anthropic transport (`BRAMBLELOOP_PRIVATE_REPLY`-style register switch, plus a daily figure), **those replies stop after this deploy**. They report `PROVIDER_NOT_SELECTED` (no provider set) or `REGISTER_NEEDS_VENICE` (provider set to Anthropic) until Venice is configured.
  - W-INTEG5 cannot read production's switches (they sit behind owner auth). **The owner should confirm.**
- **The Laura view** also reads the unified status on every open; with the switch OFF the view is unchanged. The CC shell cache version moves to `cc-shell-v25`, so phones fetch the new shell once.

**3. The owner's options.**
- **(a) Ship as is.** The CEO briefing becomes deterministic, with no model synthesis, until `BRAMBLELOOP_LAURA_CEO_MODEL=1` is set. This matches the label "switch OFF = no Business Laura model calls" (review R-2).
- **(b) Keep today's model-synthesised briefing.** That means calling the model while the switch reads OFF, which is exactly the R-2 finding. It is honest only if the switch is re-scoped and relabelled, for example "`BRAMBLELOOP_LAURA_CEO_MODEL` governs the conversation model only; the briefing synthesis keeps its own existing gate (API key + Laura's daily permission)". That would be a code and label change, followed by a re-review and a re-certification.
- Alternatively, keep (a) and have the owner set `BRAMBLELOOP_LAURA_CEO_MODEL=1` at deploy, which restores the synthesis together with the model conversation.
