# W3 lane F handoff: Talk to Laura + Owner Command Center integration

Branch `claude/w3-F`. Resumed from WIP checkpoint 680c8ba, then merged `claude/visual-investigation`
@ 88993c5 (lanes D, H2, K12, PRIV, A3, D-FB-17) with no conflicts; the merge commit was re-signed with
the lane trailers (83eaee9). After the lane work was committed (c528d58), the integrator had moved on, so
I merged it again @ 06271ff (K1 + K4) as c10822e; `app/security.py` auto-merged. With that merge,
`visibility` and `search_evidence` are live providers on this branch. Phase stays shadow. No deploy, no Etsy writes, no spend, no paid or model API
calls, no customer messages.

## Rows
| # | Requirement | Status | Where / proof |
|---|---|---|---|
| 1 | Talk to Laura Phase 1 (D-FB-16 items 7, 9, 10): polished owner-only text conversation, evidence-based answers from durable state | COMPLETE | `laura/agency/talk.py`. Sources are the CC providers, `laura.executive` (D) and `laura.memory` business tiers (E). Each fact carries a source and an in-app link. UNKNOWN is shown with its reason and is never CA$0.00. Runtime transcript below. |
| 1a | Visible canonical Laura (laura-r2-a42aeac7), honest display state | COMPLETE | `identity_view.visible_identity` / `frame_bytes`. The view shows only the r2 owner-approved reference pack (face, v6 torso, v6 full-length), each verified by sha256 against `visual.canonical` and labelled "Internal — owner-approved canonical reference, not publication-approved". It states that 0 frames are publication-approved. Routes `GET /api/cc/laura/presence` and `GET /api/cc/laura/frame/{frame}` are allow-listed: historical, superseded and concept images return 404. |
| 1b | Authorised delegation with confirmation ("have Design make three more banners") | COMPLETE | `laura/agency/delegation.py` + `talk._delegation_answer`. "I don't like that banner. Have Design make three more." is parsed with the antecedent resolved to "make three more banners" (count 3). Product & Design receives a proposal with a brief containing D-FB-17 constraints and a GATED note: new imagery needs paid generation (owner spend authority). After the owner confirms (`confirm: true` is required), it becomes one audited `autonomy.department_review` job through the COO enqueue boundary, with the brief in `inputs.brief`. The job is idempotent. Protected requests (publish, activate, live listing edits, pricing, ads, customer messages) require step-up and become an owner action, never a job. Spending, changing Laura's identity, and replacing the canonical logo or banner are refused, nothing is queued, and the answer names the owning decision. An owner block is respected. |
| 1c | Phases 2–3 (voice in/out over phone mic / Galaxy Buds; real-time live presence) as interfaces/contracts with live+voice → voice → text degradation | GATED (contract COMPLETE) | `laura/agency/presence.py` defines the `SpeechToText`, `TextToSpeech` and `LivePresenceRenderer` protocols, `capabilities()`, `negotiate()` and `respond()`. Every mode calls the same `talk.converse` (same identity, memory, authority and `laura_cc_turns`). Local deterministic test adapters prove a spoken turn equals a typed turn: same identity, sources and proposals. Low-confidence audio gets CLARIFY and records no turn. An unqualified voice is never used. `POST /api/cc/laura/voice` returns 503 VOICE_GATED with the exact needs. No provider is called. |
| 2 | Canonical Laura Voice spec + qualification | COMPLETE (spec v1; accent and apparent age PROPOSED pending owner confirmation) | `laura/agency/voice_spec.py`. Covers character, accent/dialect, apparent age, pitch, warmth, pace, energy, rhythm, pronunciation lexicon, the business register (ACTIVE) and the private register (GATED). Pinned sha `08f98c00…`. `qualify()` passes only MEASURED, sufficiently sampled, in-range readings plus the full lexicon. It fails estimates, drift, a real-person clone without consent, and any claim to the private register. `promotion_requirements` is never automatic. |
| 3 | PRIV contract: private context only through `app/command_center/private_context` | COMPLETE (infra); private reply register GATED | `private_context.py` is the only CC module importing the private API or calling `.reveal()`. Routes are `/api/cc/private/{status,open,close,view,remember,turn,forget}`. Every content route is POST with `no-store`. Opening requires a fresh step-up. The grant id stays server-side. Logout and revoke call `revoke_session_contexts`. Refusals are logged as `private_context` security events carrying the class name only. With no key the routes return 503. `owner_turn` stores the owner's words and returns `reply_status: GATED`; no reply is generated. `reject_private` guards `talk.converse` and `followon.create`. An SQL watch shows business paths (talk, overview, presence, tabs, every provider, CC GETs) issue 0 `laura_private` statements and echo no sentinels while a context is open. |
| 4a | Lane D: `provider_module` resolution; drop harness re-pin | COMPLETE | `providers._import` uses `autonomy.generators.provider_module`, with importlib as fallback. The harness re-pin is removed and lane D's own `ensure()` verifies (CURRENT_SHA256 20697b7c…). The fail-closed test now patches `ensure`. |
| 4b | Lane K4 `visibility` provider | COMPLETE (tolerant) | The `PROVIDERS` entry exists. K4 is unmerged here, so it reads UNKNOWN "not built"; this is tested with a forced ImportError. Store tab section added. |
| 4c | Lane K1 `search_evidence` (optional) | COMPLETE (tolerant) | Same pattern as 4b; Store tab section added. |
| 4d | K8 W1: estate_api router and `/api/cx/workspace` in CUSTOMER_DATA_ROUTES | COMPLETE | `app/main.py`. `test_customer_data_auth` 9/9 shows the route refuses anonymous requests, and the operator can read it. |
| 4e | `laura_phrase.phrase` for Laura's voice; one prompt registration | COMPLETE | `phrasing.py` now routes production phrasing through `gateway.laura_phrase.phrase` (lane SPEND task, allocation, cache, validation), then applies its own number/UNKNOWN check. Defect fixed: the two modules registered different texts as `laura.business_phrase@1`, so importing both raised `PromptIsImmutable`. There is now one prompt. Phrasing is off by default and there is no provider key, so answers stay deterministic. |
| 4f | `visual.rnd.status` summary sections | COMPLETE | `tabs.visual_rnd_section` (per class) and the new `tabs.visual_rnd_governance`: identity_review queue, paid_plans_incomplete, commercial heroes, evolution verdicts. A missing part reads UNKNOWN with a reason. Both are in the Learn view. |
| 4g | Launch verdict provider | COMPLETE | `tabs.launch_verdict` reads the newest `launch.assessed` row: PASS/FAIL plus ours / owner / integration blockers. A missing row gives UNKNOWN, and a synthetic fixture is never used as the verdict. Shown on the Store tab. |
| 5 | Mutating routes behind owner auth, esc/CSP, mobile-first | COMPLETE | All new routes are under `/api/cc/` (`auth.gate`: owner session, CSRF, nonce, timestamp, same-origin). Protected and private-open routes also require step-up. The PWA builds DOM with `h()` (text nodes, no innerHTML) and uses no inline handlers, so CSP is unchanged. `pwa_static` is 79/79. New Laura cards: presence (modes, gated needs, internal-labelled frames) and Private (open with step-up, store, forget, close). The service-worker shell was bumped to v3. |

## Files
- **New:** `laura/agency/{delegation,voice_spec,presence}.py`, `app/command_center/private_context.py`, `research/final_build/w3/F_runtime_proof.py`, `research/final_build/w3/evidence/F_talk_to_laura_transcript.json`.
- **New tests:** `test_w3_laura_cc_{delegation,private,providers}.py`, `test_w3_laura_{presence,voice_spec}.py`.
- **Modified:** `app/main.py` (K8 W1), `app/command_center/{api,providers,tabs}.py`, `static/js/{api.js,views/laura.js,views/learn.js,views/store.js}`, `static/sw.js`, `static/css/app.css`, `laura/agency/{talk,followon,phrasing,identity_view}.py`, `tests/w3_laura_cc_harness.py` (re-pin removed), `tests/test_w3_laura_cc_integration.py` (patch `ensure`), `tests/test_w3_laura_cc_talk.py` (allows only the stdlib firewall import; still forbids the private store).

## Tests
Interpreter: `/home/user/Project-Money/brambleloop/.venv/bin/python`, `PYTHONPATH=src`, run from
`brambleloop/`. Every test below was re-run after the K1/K4 merge, on the final source. The counts are
`OK` lines.

- **Lane F (57/57, 0 FAIL).**
  - New suites: delegation 5, private 7, providers 7, presence 4, voice_spec 6.
  - Existing suites: talk 9, followon 4, access 5, integration 5, wiring 5.
- **Required suites, 0 FAIL:**

  | Suite | OK |
  |---|---|
  | `test_route_auth_default_deny` | 7 |
  | `test_rc1_auth` | 11 |
  | `test_vacuity` | 7 |
  | `test_secret_scan` | 7 |
  | `test_reachability` | 11 |
  | `test_w3_priv_store` | 8 |
  | `test_w3_priv_access` | 7 |
  | `test_w3_priv_provenance` | 7 |
  | `test_w3_priv_firewall` | 7 |
  | `test_w3_priv_continuity` | 3 |
  | `test_w3_priv_leak` | 7 |
  | `test_w3_laura_core_constitution` | 7 |
  | `test_w3_laura_core_continuity` | 2 |
  | `test_w3_laura_core_executive` | 7 |
  | `test_w3_laura_core_identity` | 11 |
  | `test_w3_laura_core_wiring` | 6 |
  | `test_w3_laura_memory_canonical` | 6 |
  | `test_w3_laura_memory_isolation` | 5 |
  | `test_w3_laura_memory_permissions` | 9 |
  | `test_w3_laura_memory_persistence` | 2 |
  | `test_w3_laura_memory_provenance` | 6 |

- **Existing suites for modules I touched, 0 FAIL:**

  | Suite | OK |
  |---|---|
  | `test_v11_cc_actions` | 7 |
  | `test_v11_cc_auth` | 16 |
  | `test_v11_cc_views` | 13 |
  | `test_v11_wiring_cc` | 5 |
  | `test_v11_pwa_static` | 79 |
  | `test_r2_finance_money` | 12 |
  | `test_r2_finance_views` | 4 |
  | `test_r2_security_department_block` | 2 |
  | `test_w3_spend_laura_phrase` | 6 |
  | `test_k8_shop_cx` | 17 |
  | `test_customer_data_auth` | 9 |
  | `test_w3_k4_launch_verdict` | 16 |
  | `test_w3_k1_search` | 20 |

- **Fixed along the way:**
  - `test_route_auth_default_deny` requires every customer-data route to be in `security.OPERATOR_GET_ROUTES`. I added `/api/cx/workspace` and `/api/etsy/policy-violations` there.
  - `test_v11_cc_views` caught two problems:
    - Its provider stubs are installed through `sys.modules`. `_import` now defers to importlib whenever a module is already in `sys.modules`.
    - It also flagged the word "fixture" in `tabs.py`. I removed the synthetic-row clause; anything other than `ready is True` is FAIL.
- **Pre-existing failure, not caused by this lane:** `test_w3_reachability_dynamic::test_without_the_rule_the_provider_modules_were_invisible` (2 OK / 1 FAIL). It fails the same way on the integrator @ 9977f0a: lane D's static `provider_module` imports already make the provider modules reachable without the dotted-literal rule, so the "gained" set is empty. The test's premise is stale; the owner is lane D / K15.
- I did not run the full suite.

## Runtime proof
`research/final_build/w3/F_runtime_proof.py` produced `evidence/F_talk_to_laura_transcript.json` (80 KB, 13 turns). Setup:
- the real FastAPI app on temp SQLite, through TestClient;
- phase shadow, with sockets closed;
- no model or provider credentials;
- an ephemeral private key.

**Before the conversation, the company did real work.** Laura's executive tick and the COO orchestrator tick ran, then the shadow worker ran for a bounded window of 90 s. That gave 7 jobs completed and a 12-job pending queue. This is not a soak.

**What the transcript shows:**
- **Access:** anonymous requests to `/api/cc/laura`, `/api/cc/laura/ask` and `/api/cc/private/view` all returned 401.
- **Identity:** "Who are you?" gave a truthful AI-founder answer, with the verified identity record.
- **The seven executive questions:** all answered from rows, with sources, and with proposals:
  - overnight: 7 jobs completed, by agent;
  - working on: Laura's executive priorities;
  - store: Store Foundation surface counts;
  - money: revenue UNMEASURED and profit UNKNOWN, never shown as CA$0.00;
  - discoveries and learned: Learn loops and Visual R&D DEGRADED with reasons;
  - launch next: store, products and owner queue.
- **"What genuinely needs me?":** 10 owner items.
- **Banner delegation:**
  - Asking produced one mission proposal for Product & Design: make three more banners, count 3, with the GATED paid-generation note.
  - Without confirm, the request returned 400 CONFIRMATION_REQUIRED.
  - Confirmed, it returned 200 and created `jobs:12` (`autonomy.department_review`, agent coo), with `inputs.brief`. The constitution check returned allow, and the result was recorded in operational memory.
- **"Have Store publish …":** an `owner_action` proposal for `store.publish`, requiring step-up.
- **"Ask finance to spend …":** refused, and nothing was queued.
- **Modes:** "overnight" asked with modes live/voice/text was delivered as text, `degraded: true`, with the skipped reasons.
- **`POST /laura/voice`:** 503 VOICE_GATED.
- **Presence:**
  - available modes: `["text"]`;
  - visible identity: 3 verified internal frames, 0 publication-approved;
  - voice spec `laura-voice-v1` (sha `08f98c00…`), owner confirmation PENDING.
- **Private context (statuses only; no content in the file):**
  - configured: true;
  - step-up 200, open 200, owner turn 200 with `reply_status: GATED`;
  - view 200, with 1 owner message and 0 Laura turns;
  - close 200; view after close 403.

**Earlier browser evidence:** `evidence_F/laura_{phone,desktop}.jpg` is from the previous session and does not show the new presence or private cards. I did not re-run Playwright this session; the PWA static suite (79) covers the shell.

## WIRING REQUESTS (for other owners)
1. **Lane D (autonomy/charters):** if delegated briefs should produce more than a department self-review, add a GREEN `<dept>.brief` job type (handler reads `inputs.brief`) to the relevant charters' `generatable` and `SAFE_GENERATED`. Today a delegation runs `autonomy.department_review` with the brief attached. The answer and the brief say so honestly.
2. **Lane D (optional, still open):** record CC follow-ons and delegations as `laura_decisions`.
3. **Integrator:** when merging K4 and K1, the `visibility` and `search_evidence` entries go live with no further change. Optionally add their modules to `generators.provider_module`'s static list for reachability.
4. **PRIV / owner:** a private reply register needs its own owner-approved lane, bounded by provider policies. Its only entry point must be `store.record_turn(role="laura", reply_to=..., model_ref=...)` through `private_context`.

## Honest gaps / not verified
- **Voice and live presence:** GATED. No STT, TTS or avatar provider is configured, contracted or paid. The needs are listed per phase in `presence.PHASE_NEEDS`, with max cost UNKNOWN until a provider is chosen. Voice spec accent and apparent age await owner confirmation. Voicing the human Laura needs her recorded consent.
- **Laura imagery:** no frame is publication-approved; the owner view is internal only.
- **Banner delegation:** no free banner producer exists, and generating new imagery waits on owner spend authority (Visual paid path). The delegated job is a department review carrying the brief.
- **Private register:** not implemented (GATED). Only owner-supplied text is stored and shown.
- **Delegation parser:** regex-based. Unusual phrasings fall back to the business intents or Ask Company. Naive pluralisation, e.g. "heros".
- **Database:** SQLite only; Postgres not exercised.


## Follow-up: D-FB-18 items 6–8 (Laura Voice decided; Phase 1 approved)
I merged `claude/visual-investigation` again (d2c92e2), which brought in D-FB-18. The merge had no conflicts.

| Item | Status | Where / proof |
|---|---|---|
| Voice spec v1 → v2 (decision D-FB-18), pinned | COMPLETE | **Spec content.** `voice_spec.py` is now `laura-voice-v2`, sha `4c5ab12b…`. v1 (`08f98c00…`) is kept pinned in `SUPERSEDED`. Apparent age is 30–34, centred on 32. Accent is subtle en-CA or neutral North American. The spec carries the full positive character list and both exclusion lists (performance and cadence), plus the natural conversational prosody list. **One canonical voice.** It has two registers: business (polished, ACTIVE) and private_owner. The private_owner register is the same voice made warmer, more intimate, playful and flirtatious through prosody only. It requires PRIV, provider support and the unbuilt private register, so it stays GATED exactly as before. **Qualification.** `qualify()` is unchanged except that it now checks against the v2 ranges. |
| Candidate scorecard + selection rule + durable voice identity | COMPLETE (no voice selected) | **Scorecard.** `voice_selection.py` scores all 14 D-FB-18 criteria (plus "exclusions absent"). The 10 perceptual criteria are judgements by the owner or a named human listener, and each must name the samples heard. An automatic, model, metric or provider score reads UNKNOWN. Attractiveness, natural sensuality, match to appearance and same-voice are owner-only. **Technical criteria** need recorded measurements or evidence. Cost reads UNKNOWN until a price exists. **Selection.** `select()` requires all of: a PASS qualification on the current spec sha, a scorecard PASS, an owner listening decision id that is recorded in DECISION_LOG, and judgements made on the exact reference samples. It then writes a hash-chained `laura_voice_identity` row with provider-independent descriptors and the reference-sample digest. The provider is recorded as a replaceable instrument. **Replacement.** A replacement must requalify and be judged by the owner to be the same voice as the reference. A tampered chain is reported. No provider is called. |
| Owner action "listen to shortlisted Laura voice candidates" | COMPLETE (catalogue; see wiring request 5) | `voice_selection.OWNER_ACTION`. It needs provider access and paid-trial approval; max cost is UNKNOWN until a provider is chosen. It is shown in the Laura presence card and in "What genuinely needs me?". I did **not** insert it into the consolidated `owner_actions` table, because `max_cost_cad` is a non-null float. Storing it there would show CA$0.00 and the executor would treat it as free. |
| Voice (P2) and Live Presence (P3, Zoom-like) registered as REQUIRED open rows; voice as a permanent improvement domain | COMPLETE (registry in code); fold-in is wiring request 6 | `laura/agency/roadmap.py` holds rows LAURA-TEXT-P1 (COMPLETE), LAURA-VOICE-P2, LAURA-LIVE-P3, LAURA-PRIVATE-REGISTER and LAURA-VOICE-IMPROVE. Each GATED row is `required`, `cancelled: false`, and carries a `gate {kind, key, detail}` in the closure v1.1 row shape. Status is recomputed from the configured adapters and is never declared. `IMPROVEMENT_DOMAIN` covers realism, latency, prosody, expressiveness and conversation quality. Its invariant is the locked identity: every challenger must be judged the same voice. Its metrics are UNKNOWN. The new provider `laura_roadmap` is shown in the CC Learn tab (DEGRADED, with reason) and in `/api/cc/laura/presence`. |

**Tests for this follow-up** (re-run on the final source; counts are OK lines; 0 FAIL in every suite):
- New `test_w3_laura_voice_selection`: 4.
- `test_w3_laura_voice_spec`: 7 (v2 pin plus the D-FB-18 content).

| Suite | OK |
|---|---|
| `test_w3_laura_cc_access` | 5 |
| `test_w3_laura_cc_delegation` | 5 |
| `test_w3_laura_cc_followon` | 4 |
| `test_w3_laura_cc_integration` | 5 |
| `test_w3_laura_cc_private` | 7 |
| `test_w3_laura_cc_providers` | 7 |
| `test_w3_laura_cc_talk` | 9 |
| `test_w3_laura_cc_wiring` | 5 |
| `test_w3_laura_presence` | 4 |
| `test_w3_priv_leak` | 7 |
| `test_w3_priv_firewall` | 7 |
| `test_vacuity` | 7 |
| `test_secret_scan` | 7 |
| `test_reachability` | 11 |
| `test_v11_cc_views` | 13 |
| `test_v11_pwa_static` | 79 |
| `test_route_auth_default_deny` | 7 |
| `test_w3_laura_core_identity` | 11 |

**WIRING REQUESTS added by the follow-up:**

5. **core/models owner (lane D / integrator):** give `OwnerAction` an explicit unknown max-cost (for example nullable `max_cost_cad` plus a `max_cost_basis`) and teach `build2.executor` not to treat UNKNOWN as free. Then seed `voice_selection.OWNER_ACTION` into the consolidated queue, keyed by `laura.voice.listen_shortlist`.
6. **Lane K / integrator (closure):** fold `roadmap.ROWS` into the W3 closure's v1.1 overlay as owner-ruling rows. They must stay REQUIRED/GATED and must never be marked N/A or cancelled.
7. **Learn/improve owner:** register a `laura_voice` loop in `improve.policy_loops` (or the department loop registry) once a voice is selected. Use `roadmap.IMPROVEMENT_DOMAIN`. The proposer is Brand/Laura, the challenger is an independent listener, the metric is owner A/B listening preference, and the guardrails are latency and same-voice. A loop with no measurable data today would be a fake loop, so I did not register one.
