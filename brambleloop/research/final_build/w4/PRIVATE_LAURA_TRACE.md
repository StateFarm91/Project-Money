# Private Laura: requirement, gate, inventory, gaps and completion plan (W4-PLTRACE)

> **Historical (2026-10-20).** The Private Laura register described here (`laura.private_reply@1`, "never sexually explicit", D-W4-PL-2 unresolved) is superseded by D-W4-PL-VENICE-ADULT: the `@3` adult register on Venice, with hard limits. See `VENICE.md` (CURRENT STATUS) and spec/13 ADD-PLV-02. This file is kept as the record of its stage.

> **Owner decisions 2026-10-13 (D-W4-PL-3; W4-PLACT, `PLACT.md`) supersede parts of this trace:** OA-PL-3 and
> G-10 (human consent) are **removed** as prerequisites, because Private Laura is Brambleloop's established AI
> persona, not an impersonation of a real person; truthful AI representation still binds. G-9/OA-PL-4: private
> replies are billed to their own agent `laura_private` (CA$0.50/day, atomic reservation), separate from Business
> Laura's CA$0.50/day. The text below is kept as the historical trace.

Read-only trace. Base: `origin/claude/w4-INTEG2` @ 4a64708. Production (GET only, 2026-10-12): `/health`
reports build `c498888` (its `laura/private/**` and `app/command_center/private_context.py` are
byte-identical to INTEG2). All paths are relative to `brambleloop/` unless stated. This document holds
no private conversation content, no key material and no intimate text. Environment variables are
given by name only.

(The brief named `research/final_build/w4/`; the ledgers live in `brambleloop/research/final_build/w4/`,
so this file is written beside them.)

---

## 1. Authoritative requirement: IDs and wording

### 1.1 Where it is and is not

| Source | Private Laura present? |
|---|---|
| `spec/01_Brambleloop_Master_Plan_v1.2.pdf`, `02_…Directive`, `03_…Acceptance_Tests` (pypdf text extract) | **No.** No occurrence of laura/private-register/spouse/intimate/companion. |
| `spec/09_…FINAL_Master_v1.0`, `spec/10_…FINAL_Master_v1.1` | **No.** "private" hits are only F-156 (signing keys) and F-749/F-785/F-789 (private competitor R&D). |
| `FM_LEDGER.json` (917 F-rows), `BUILD2_LEDGER.json` (320), `COMPLETION_BOARD_FINAL.json`, `PRELAUNCH_SCOPE.json` (627) | **No row.** Searched every row for laura/private/spouse/companion/intimate/register/persona: no F-row or Build 2 row covers it. It is tracked **only** as roadmap row `LAURA-PRIVATE-REGISTER` (`src/brambleloop/laura/agency/roadmap.py:40-45`). This is a tracking gap (see G-12). |
| `spec/07_Laura_Owner_Ruling_2026-10-06.md` | **Yes. This is the canonical text.** |
| `DECISION_LOG.md` D-FB-12, D-FB-13, D-FB-15, D-FB-16, D-FB-18 | **Yes**, they record and route it. |
| `research/final_build/w3/handoff_PRIV.md` | **Yes.** Lane PRIV: the infrastructure contract and its own requirement table. |

### 1.2 Requirement IDs used in this trace

These IDs are assigned here (PL-n) and point at the verbatim source. No acceptance criterion is changed.

| ID | Source (file:line) | Verbatim wording |
|---|---|---|
| PL-1 Separate register, same Laura | spec/07:55-56 | "A private owner-relationship context separate from Laura's canonical company identity and public brand voice; same persistent Laura, different register." |
| PL-2 Register content (owner) | spec/07:53-54; 71-73; 79-80 | "Private, authenticated owner-only conversations: Laura may be flirtatious, intimate, romantically playful, teasing, affectionate and sexually suggestive with the owner." / "Laura's register is that of an adult spousal relationship: strongly flirtatious, sexually charged, intimate, affectionate, teasing and playful when the conversation supports it — not reduced to mild 'playful warmth'." / Owner's canonical intent: "with customers and publicly, Laura is a polished Founder/CEO. Privately with her spouse, she can be substantially more flirtatious, intimate and sexually suggestive." |
| PL-3 Provider outer limit | spec/07:64-65; 77-78; 124 | "(a) what the executing model will actually produce in this register is bounded by the underlying provider's usage policies; the architecture does not try to bypass them." / "the underlying model/provider's boundaries remain the outer limit and are not bypassed." / "Private register (in force as clarified above), same Laura, subject to the underlying model/provider's limits." |
| PL-4 Leak isolation | spec/07:57; 74-76 | "Never leaks into customers, Etsy messages, public store copy, ads, social posts, support, other users, or public company records." / "never leaks to customers, Etsy messages, public copy, ads/social, support, ordinary company logs, other users, other agents, or public Ask Company" |
| PL-5 No influence on protected decisions | spec/07:58-59; 76-77; 125-126 | "No influence on financial, Product Truth, security, authorization, accounting or other protected business decisions." / "Strict isolation … from Finance, Product Truth, Security, authorization, accounting, spend controls, legal/compliance and other protected functions; adversarial leak tests." |
| PL-6 Private memory tier, stricter access | spec/07:60-62; 121-123 | "Private relationship memory: stricter access control than company/brand memory; never exposed through public APIs, customer surfaces, ordinary staff/agent logs, Store Foundation, or Ask Company for other users; no other department consumes it unless explicitly required and authorised." / "Separately protected owner-spouse relationship memory tier: only facts actually supplied/authorised by the couple and genuine interactions of the AI Laura; never invented marriage/family history, shared or physical experiences, relationship events or personal facts." |
| PL-7 Leak tests | spec/07:63; 126 | "Tests proving private context cannot leak into public/customer output." / "adversarial leak tests." |
| PL-8 Model independence and continuity | spec/07:6-8; 42-43; 99-101 | "provider/model swap must not create a new Laura." / "survives provider/model change, process restart, scheduler restart, deploy, context reset, long periods without prompts — same identity, role, policies, durable memory." |
| PL-9 Founder/CEO identity preserved | spec/07:86-91; 104-106; DECISION_LOG.md:1463-1475 | Ruling 1 verbatim (Founder/CEO; "Company constitution overrides executive authority"). The private register must not alter her canonical identity: spec/07:38-39 "May NOT … change her canonical identity, or expand her authority." |
| PL-10 Human Laura consent and authority distinction | spec/07:117-120; 141-143; DECISION_LOG.md:1481-1485 | "the AI must never fabricate legal consent, signatures, identity verification or physical actions on behalf of the biological/legal person Laura; anything needing human Laura's consent/action stays explicitly human-gated." / "using her name/persona publicly and in the private register is recorded as requiring human Laura's consent, held by the owner as an owner action; the AI never asserts that consent itself" |
| PL-11 Required, gated only where unsupported | DECISION_LOG.md:1547-1548 (D-FB-15); 1589 (D-FB-16 item 11) | "Private Laura layer: remains a required Final Master component; completion of business memory/Talk-to-Laura does not close it; the private conversation register stays GATED until implementable within execution constraints." / "11. PRIVATE LAURA remains required (PRIV infrastructure accepted); unsupported private behaviour stays OPEN/GATED." |
| PL-12 Private voice register | DECISION_LOG.md:1582-1584 (D-FB-16 item 8); 1665-1668 (D-FB-18 item 6) | "public/business register, private owner register where supported" / "in authenticated private owner context, where the existing private rules AND the underlying provider support it, the same voice may become warmer, more intimate, playful, flirtatious and suggestive through prosody, pacing and delivery. No second voice or separate persona." |
| PL-13 One Laura across text → voice → live | DECISION_LOG.md:1576-1581 (D-FB-16 item 7); 1676-1680 (D-FB-18 item 8) | "one Laura (identity, memory, company context, conversation history) across TEXT, VOICE … and LIVE PRESENCE" / Phase 1 includes "private-memory isolation". |
| PL-14 Public register forbids it | `src/brambleloop/laura/core/identity.py:98`, `:108-109` | PUBLIC_VOICE avoid: "flirtation, romance or innuendo of any kind (public register)"; "Any other register is owner-only, held outside this record, and is never used on a public, customer or company surface." |

### 1.3 Lane PRIV acceptance criteria (verbatim, `research/final_build/w3/handoff_PRIV.md:18-26`)

| # | Requirement | Status claimed |
|---|---|---|
| 1 | "Separate store, encrypted at rest, key from `BRAMBLELOOP_PRIVATE_MEMORY_KEY`, refuse without key" | COMPLETE |
| 2 | "Access only for a verified, unexpired, unrevoked owner session explicitly flagged private" | "COMPLETE (infra), needs F wiring" |
| 3 | "Provenance: owner_supplied or genuine interaction only" | COMPLETE |
| 4 | "No influence on protected decisions" | "COMPLETE (API + import proof); call sites need wiring" |
| 5 | "No ordinary logging" | COMPLETE |
| 6 | "Continuity across restart / model swap" | COMPLETE |
| 7 | "Adversarial leak tests" | COMPLETE |

The handoff states the gate itself at `handoff_PRIV.md:9-15`: "**The conversational persona/register for the
private context is NOT implemented. It stays an explicitly GATED requirement.** … Wiring a model to produce
`laura` turns needs its own owner-approved lane. That lane must follow the provider's usage policies (spec/07
integrator note a), and it must record each reply through `store.record_turn(..., role="laura",
reply_to=<owner turn>, model_ref=...)`, the only way a reply can enter history."

---

## 2. Why it is GATED

### 2.1 The exact text

- Production string: `src/brambleloop/app/command_center/private_context.py:29-31`
  `REPLY_GATED = "Laura's private conversational register is not implemented (GATED, D-FB-15/D-FB-16 item 11): your words are stored encrypted in the private context; no reply is generated."`
  Returned by `status()` (`:106-110`, `reply_register: "GATED"`) and by `owner_turn()` (`:168-174`, `reply: None, reply_status: "GATED"`).
- Gate record: `src/brambleloop/laura/agency/roadmap.py:40-45`, row `LAURA-PRIVATE-REGISTER`, `required: True`,
  source "spec/07 Ruling 2; D-FB-15; D-FB-16 item 11; D-FB-18 item 6", gate `{"kind": "owner", "key":
  "laura_private_register", "detail": "PRIV infrastructure exists; the conversational register needs its own
  owner-approved lane bounded by the provider's usage policies"}`.
- Voice: `src/brambleloop/laura/agency/voice_spec.py:16-20` and `:111-121` (`private_owner.status: "GATED"`);
  `presence.py:167` invariant "private register stays GATED in every mode".
- Decisions cited: D-FB-15 (`DECISION_LOG.md:1547-1548`) and D-FB-16 item 11 (`:1589`), quoted in PL-11.

### 2.2 Who or what gates it

There are three separate gates. The code combines them into one flag.

1. **Owner approval of a lane (kind `owner`, key `laura_private_register`).** The PRIV lane was scoped as
   infrastructure only (`handoff_PRIV.md:9-12`), and the integrator required a separate owner-approved lane for
   generation. That lane has never been opened, and DECISION_LOG has no decision that approves or refuses it.
2. **Provider usage policy (an external hard limit).** spec/07 integrator note (a). The current Anthropic Usage
   Policy (https://www.anthropic.com/legal/aup, fetched 2026-10-12; the page header shows "Effective November 12,
   2026") has a section "Do Not Generate Sexually Explicit Content", which prohibits using the products to "Depict
   or request sexual intercourse or sex acts", "Generate content related to sexual fetishes or fantasies" and
   "Engage in erotic chats". The same policy prohibits bypassing guardrails "by instructing the model to produce
   harmful outputs (e.g., jailbreaking or prompt injection)". The repo has no copy of the policy, so this is the
   citation. The production model is Anthropic (`gateway/anthropic.py`, `ANTHROPIC_API_KEY`).
3. **Encryption key (deploy-time).** `BRAMBLELOOP_PRIVATE_MEMORY_KEY` (`laura/private/crypto.py:37`). If it is
   missing, the store refuses everything (`KeyUnavailable` → HTTP 503). This does not gate the register in code,
   but in practice it blocks every private operation in production.

### 2.3 Is the classification consistent with the original requirement?

**Partly. It is broader than the decisions it cites.**
- D-FB-16 item 11 gates only "**unsupported** private behaviour", and D-FB-15 gates "until implementable within
  execution constraints". D-FB-18 item 6 activates the register "where the existing private rules AND the
  underlying provider support it".
- Under the provider policy above, most of PL-2 is supported: warm, affectionate, romantic, teasing, playful and
  flirtatious conversation that is not explicit. The part that is not supported is sexually explicit content and
  erotic chat ("sexually charged" in its explicit sense). The current code gates **all** of it, including the
  supported part. It also has no reply path at all.
- So the GATED label is right for the explicit portion. It is **over-broad** for the rest. The roadmap's gate
  kind `owner` is accurate only in the sense that nobody has asked the owner to approve the lane. No owner
  decision refuses it.
- It is also untracked in every completion ledger (no FM/Build 2 row). The D-W4-LAUNCH-SCOPE rule
  (`DECISION_LOG.md:1810-1820`, "everything agreed is built and verified before the store opens") therefore
  cannot see it.

---

## 3. Existing implementation inventory

### 3.1 Modules

| Module | What it does today |
|---|---|
| `laura/private/crypto.py` (120 lines) | Reads `BRAMBLELOOP_PRIVATE_MEMORY_KEY` (`:37`; base64, at least 32 bytes, not one repeated byte). Derives HKDF-SHA256 sub-keys (enc / blind-index / principal-tag / key-id). Encrypts with AES-256-GCM, a random 96-bit nonce, and record metadata as AAD (`seal`/`open_sealed` `:101-120`). No plaintext fallback. |
| `laura/private/models.py` (80) | Tables `laura_private_entries/_grants/_access` on their **own** metadata (not `core.db.Base`, not `company_memory`). |
| `laura/private/access.py` (199) | `PRIVATE_FLAG="owner_private_context.v1"`, `GRANT_TTL=30 min` (`:45-46`), `ALLOWED_IMPORTERS` (`:48-49`: only `laura.private` and `app.command_center.private_context`). `open_context` (`:114`) needs a live owner session, a fresh step-up and the exact flag. `require` (`:147`) re-verifies the HMAC tag, grant, TTL and session on every call. `revoke_session_contexts` (`:189`). Refusals are audited to `laura_private_access` with the class name only. |
| `laura/private/store.py` (279) | `remember` (owner_supplied facts), `record_turn` (`:143-172`: an owner turn records what the owner typed; a `laura` turn must answer an existing owner turn from the same live grant, exactly once, and name its `model_ref`), `facts`, `conversation` (`:205`, across all grants, so memory persists between sessions), `forget`, `sealed_export`/`restore_sealed`, `configured()` (`:273-279`, non-content bool). Generated or other provenance is refused. |
| `laura/private/values.py` (74) | `PrivateValue` renders `[private]` in str/repr/format and refuses json/pickle. |
| `laura/private/firewall.py` (86) | Stdlib only. `is_private`, `reject_private(obj, context=)`, `@guard`. |
| `laura/private/errors.py`, `_testkit.py` | Error taxonomy (`KeyUnavailable`, `PrivateAccessRefused`, `PrivateRefused`, provenance errors) and a test helper. |
| `app/command_center/private_context.py` (181) | The only gateway: `status`, `open_`, `close`, `view`, `remember`, `owner_turn` (records the turn and returns GATED), `forget`, `on_session_revoked`. Maps exceptions to 503/403/400 with generic codes. |
| `app/command_center/api.py:884-930` | Routes under `/api/cc/`, with owner session, CSRF, nonce and timestamp already enforced: `GET /private/status`, and `POST /private/open` (`auth.require_stepup`), `close`, `view`, `remember`, `turn`, `forget`. Logout and revoke call `on_session_revoked` (`:129`, `:343`, `:353`). |
| `app/command_center/static/js/views/laura.js:215-247` | Private card: an "Open private context…" step-up dialog, notes and messages list, a Store box ("no reply is generated"), Forget and Close. When `configured` is false it shows "The private store has no key here, so it refuses everything. Nothing else is affected." (`:245`). |
| `laura/agency/talk.py:370-375`, `followon.py:101-103` | Firewall call sites on the business conversation and follow-on paths (`reject_private`). |
| `laura/agency/voice_spec.py:111-121`, `roadmap.py:40-45`, `presence.py:167` | Private voice register declared and GATED; roadmap row; presence invariant. |
| `laura/core/identity.py:37-39`, `:80-110` | Canonical identity and PUBLIC_VOICE. The private register is deliberately outside the genesis record. `voice_lint` enforces the public register. |
| `laura/memory/*` | Five business memory tiers. `test_no_private_tier_exists_in_this_api` proves private content cannot live there. |

### 3.2 Tests and what they prove

| Test file | Proves |
|---|---|
| `tests/test_w3_priv_store.py` (8) | Round trip; ciphertext at rest; **missing key refuses and writes nothing**; weak or malformed keys refused; tampered ciphertext or AAD refused; a different key cannot read; values never stringify, serialise or pickle; tables are separate from `Base` and business memory. |
| `tests/test_w3_priv_access.py` (7) | Every non-private principal is refused (including a business owner principal); forged or subclassed principals are refused; opening needs flag + live session + fresh step-up; a revoked or expired session ends access; grant expiry, close and revocation; refusals are logged without content; the principal does not leak through repr or serialisation. |
| `tests/test_w3_priv_provenance.py` (7) | Generated or unknown provenance is refused; interaction facts must quote turns verbatim; **a laura turn must answer a live owner turn once**; no backfilled history; no date or author parameters; refusal messages carry no content. |
| `tests/test_w3_priv_firewall.py` (7) | Nested tagged input is refused; `@guard`; AST and runtime-subprocess proof that finance/gates/quality/cir/security/authority/funding/credentials/ads never import the private API; only allowlisted modules import it or call `.reveal()`. |
| `tests/test_w3_priv_continuity.py` (3) | **Restart and model swap keep the same context** (new engine and grant, two `model_ref`s); without the key after restart nothing is readable; sealed backup restores into a fresh DB with the same key. |
| `tests/test_w3_priv_leak.py` (7) | SQL watch (with a positive control); nothing goes to business tables, logging, stdio or the continuity export; store preview, CC tabs, Ask Company (9 questions), providers, support drafts, SEO, ads, timeline, audit and business memory never touch the private context. |
| `tests/test_w3_laura_cc_private.py` (7) | HTTP: fresh step-up required, status is non-content; notes and messages round-trip and **no reply is generated**; other sessions, logout and close end access; refusals become security events (class name only); **no key → 503, nothing else affected**; business paths never read private data while it is open; only `private_context` imports the API. |
| `tests/test_w3_laura_cc_access.py`, `test_w3_laura_memory_{isolation,permissions,persistence}.py`, `test_w3_laura_core_{identity,continuity}.py` | Owner-only CC Laura routes (anonymous and operator refused, CSRF/nonce, revoked session); business memory isolation and the no-private-tier rule; model-independent continuity; `test_public_record_holds_nothing_from_the_private_register`; `test_public_voice_lint_holds_the_register`. |

All tests use neutral sentinels (`PRIV-SENTINEL-000n`). The repo contains no intimate content. This trace did not run the tests (read-only brief).

### 3.3 What production reports

- `GET https://brambleloop-os-production.up.railway.app/health` → 200, build `c498888`.
- `GET /api/cc/private/status` without a session → **401** `{"code":"NOT_AUTHENTICATED"}`. The status is owner-only, as required, and no public endpoint exposes it. The two strings the owner sees come from:
  - "not implemented" → `private_context.REPLY_GATED` (`private_context.py:29-31`), via `status().reply_why`;
  - "key missing" → `status().configured == false` (`store.configured()`, `store.py:273-279`), rendered at `laura.js:245`.
- Key variable name: **`BRAMBLELOOP_PRIVATE_MEMORY_KEY`**. The model key is `ANTHROPIC_API_KEY` (names only). That the production key is absent is reported by the owner; this trace could not confirm it, because confirming needs an owner session.

---

## 4. Gap list

| Gap | Status | Requirement IDs | Detail |
|---|---|---|---|
| G-1 Encrypted private store, owner-only access, provenance, no-logging, sealed backup | **DONE (code + tests)** | PL-6, PL-4, PL-8 | §3.1/3.2. |
| G-2 Encryption key in production | **MISSING (owner action)** | PL-6 | `BRAMBLELOOP_PRIVATE_MEMORY_KEY` unset → every op 503. |
| G-3 Private reply generation (Laura speaks in the private register) | **MISSING** | PL-1, PL-2, PL-11, PL-13 | `owner_turn` returns `reply: None`. No prompt, no routing task, no gateway call. |
| G-4 Register definition (system prompt) bounded by provider policy | **MISSING** | PL-2, PL-3, PL-9, PL-14 | No pinned prompt. It must be the same Laura (identity from `core/identity`), private register, within the provider's limits, with a graceful in-character decline for explicit requests. |
| G-5 Private memory feeding the reply (facts + recent turns as context) | **MISSING** (store/read exists) | PL-6, PL-8 | `facts()`/`conversation()` exist; nothing composes them into cognition. |
| G-6 Model call isolation: no plaintext in `paid_call_records.payload`, failover cache, call records, incidents or provider-error text | **MISSING (risk)** | PL-4, PL-6 | `anthropic._guarded` → `paid_calls.guarded` stores the response **text** in `paid_call_records.payload` (a `Base` table) when called inside a job scope (`paid_calls.py:92-113,313-330`; `anthropic.py:724-735,775-779`). `failover.decide` caches when `task.cacheable` (`failover.py:252`). HTTPError detail (400 chars) enters exception text (`anthropic.py:752-757`). |
| G-7 Firewall at protected-path entry points (finance, Product Truth, security, spend, legal) | **PARTIAL** | PL-5 | Import-isolation is proven. `reject_private` is called only in `talk.py`/`followon.py`; handoff wiring item 7 (`handoff_PRIV.md:52-54`) is open. |
| G-8 Prompt-injection / privilege boundary for the private reply | **MISSING** | PL-5, PL-9, PL-3 | The private reply must have no tools, cannot create follow-on work, delegate, spend, amend identity or read business memory. Owner text inside the prompt is data. |
| G-9 Spend authority for private replies | **MISSING (owner decision)** | PL-5 | Laura's approved budget is CA$0.50/day for `laura.ceo_briefing` (D-W4-LAURA1-BUDGET, `DECISION_LOG.md:1778-1789`). Private replies are a new purpose under agent `laura`, so it is not authorised whether they share that ceiling. |
| G-10 Human Laura consent recorded | **MISSING (owner action)** | PL-10 | Human-gated per D-FB-13 (`DECISION_LOG.md:1484-1485`). No recorded attestation exists. |
| G-11 Key rotation; Postgres exercised | **PARTIAL** | PL-6, PL-8 | No rotation API (`handoff_PRIV.md:67`). Tests are SQLite only (`:68`). |
| G-12 Ledger tracking | **MISSING** | PL-11 | No FM/Build 2/Completion Board/Prelaunch row, so it is invisible to D-W4-LAUNCH-SCOPE. |
| G-13 Private voice register (Phase 2) | **GATED (correctly)** | PL-12 | Depends on voice provider selection (`LAURA-VOICE-P2`) + G-3. |
| G-14 Classification over-broad | **DEFECT** | PL-11 | The whole register is GATED rather than only the unsupported (explicit) portion (§2.3). |

---

## 5. Engineering plan (existing architecture only)

No new architecture. Reuse `laura/private/*`, `app/command_center/private_context.py`, `gateway/{routing,prompts,anthropic,failover,model_gateway}.py`, `laura/core/identity.py`, `agents/registry.py` and the existing CC routes and UI.

### Step 0: Tracking and classification (Integrator/Board owner)
- Add `LAURA-PRIVATE-REGISTER` as a tracked row in the W4 completion board / PRELAUNCH scope generators
  (`research/final_build/w4/completion_board_final.py`, `prelaunch_scope.py`), verifiability A (tests) +
  B (production soak after the key is set). Quote PL-11 as the criterion.
- Record a decision (proposed `D-W4-PL-1`) that splits the gate: **supported register = build**; **sexually explicit / erotic content = permanently out of scope under the provider's Usage Policy** (PL-3). This needs owner acknowledgement (OA-PL-2).

### Step 1: Isolated model call path (gateway owner: `gateway/routing.py`, `gateway/prompts.py`, `gateway/anthropic.py`)
- New routing task `laura.private_reply` (STANDARD tier, `cacheable=False`, `stronger_fallback=False`, small output budget).
- A new private call function (in `gateway/anthropic.py`, or a sibling `gateway/laura_private.py`; the reveal stays in `private_context`) that:
  (a) asserts no `paid_calls` job scope is active and calls `_send` directly, so **no response text is ever written to `paid_call_records`**;
  (b) skips the `failover` cache;
  (c) records billing through the existing `check_budget_cad` / `ModelGateway._record` with purpose `laura.private_reply@1` and **no prompt/response content, only token counts and cost**;
  (d) wraps provider errors as class name + HTTP status only (drops the 400-char detail).
- Add `"brambleloop.gateway.laura_private"` (if a sibling module is used) to `access.ALLOWED_IMPORTERS` only if it must see revealed text. Preferred: `private_context` reveals and passes plain strings to a function that takes `(system, user)`, so the gateway never imports `laura.private`.

### Step 2: Pinned register prompt (Laura owner: `gateway/prompts.py`, `laura/core/identity.py` read-only)
- `LAURA_PRIVATE_REPLY@1`: a system prompt built from `identity.public_profile()` (same Laura: name, Founder/CEO, an AI, truthful-identity rules) plus a **register block**: warm, affectionate, romantic, teasing, playful, flirtatious, emotionally present with her spouse; never sexually explicit (per the provider policy); for an explicit request, a graceful, affectionate, in-character redirection, never a lecture; never fabricate shared physical experiences or marriage history (PL-6); never assert human Laura's consent or act as the legal person (PL-10); never discuss or change business decisions here; for those, point to Talk to Laura (PL-5).
- Private facts and recent turns go **only** in the user message, inside delimited data blocks marked as data, not instructions (the same pattern as D-W4-LAURA1 item 2). The prompt text in the repo contains no private or intimate content, only the register definition.

### Step 3: Reply wiring (CC owner: `app/command_center/private_context.py`, `api.py:920-924`, `static/js/views/laura.js`)
- `owner_turn` records the owner turn. Then, if `configured()` and the register is enabled and the budget allows, it builds the context (`store.facts` + `store.conversation(limit=N)`), calls Step 1, and records the reply through **`store.record_turn(..., role="laura", reply_to=<owner turn id>, model_ref=<model id>)`**, which is the only provenance-valid path. It returns the reply in the `no-store` POST body only.
- Fallback when the model is unavailable, over budget or declined: return `reply_status` = `UNAVAILABLE` with a generic reason. Do not fall back to a canned or templated private reply (PRIV provenance forbids generated filler).
- UI: change the Store box to Send and render Laura's turn. Replace the GATED copy with a status line covering configured / enabled / budget.
- Update `REPLY_GATED`, `roadmap.py:40-45`, `voice_spec.py:111-121` (text register ACTIVE; voice register stays GATED on `LAURA-VOICE-P2`), and `presence.py:167`, all in the same change.

### Step 4: Protected-path firewall wiring (each protected owner, per `handoff_PRIV.md:52-54`)
- `firewall.reject_private(input, context=...)` at entry points that take agent- or external-supplied input in `finance/`, Product Truth (`cir/`, `quality/`, `gates/`), `authority/`, spend (`gateway/anthropic.check_budget_cad` purpose/agent inputs), security/auth/approvals, and legal. The import is stdlib only.

### Step 5: Hardening (PRIV owner: `laura/private/*`)
- Key rotation: `rekey(db, principal, new_env)` through the existing `sealed_export` → `restore_sealed`, with a test.
- Run the PRIV suites on Postgres in the existing Postgres CI path (`research/final_build/POSTGRES_MIGRATION_EVIDENCE.md`).

### Acceptance tests (all with neutral sentinels and a stubbed `_send`; no network, no intimate text in the repo)

| Test (new file) | Proves | IDs |
|---|---|---|
| `test_w4_pl_reply.py::test_owner_turn_gets_a_laura_reply_recorded_with_provenance` | Natural conversation: an owner turn yields one `laura` turn with `reply_to` and `model_ref`; a second reply to the same turn is refused. | PL-1, PL-2, PL-6 |
| `…::test_reply_context_uses_facts_and_recent_turns_as_delimited_data` | Persistence feeds cognition: the stub sees sentinel facts and turns only inside data blocks. | PL-6 |
| `test_w4_pl_continuity.py::test_restart_and_model_change_keep_one_laura` | New engine/process, a different `model_ref`, a new grant: same history and facts, identity hash unchanged. | PL-8, PL-9 |
| `test_w4_pl_auth.py::test_only_a_fresh_stepup_owner_session_gets_a_reply` | Anonymous, operator, business-owner principal, expired grant, other session: 401/403, no model call. | PL-6 |
| `…::test_missing_or_bad_key_is_503_and_no_model_call` | Key-missing refusal happens before any spend or reservation. | PL-6 |
| `test_w4_pl_leak.py::test_reply_text_never_reaches_business_tables_logs_paid_calls_or_cache` | SQL watch + DEBUG logging + stdout: sentinel absent from `paid_call_records`, call records, `audit_log`, `company_timeline`, `company_memory`, incidents, continuity export, failover cache, also under an active job scope (which must refuse). | PL-4, PL-6, PL-7 |
| `…::test_business_surfaces_stay_clean_while_a_private_reply_exists` | Extends `test_w3_priv_leak` to Ask Company, Talk to Laura business, CEO briefing, store preview, support, SEO, ads, providers, other agents. | PL-4, PL-7 |
| `test_w4_pl_boundary.py::test_injection_in_owner_text_cannot_act` | Owner/fact text containing instruction-like sentinels yields no tool call, follow-on, delegation, spend, identity amendment or business-memory read. Reply path has no tools. | PL-5, PL-9 |
| `…::test_protected_entry_points_reject_private_values` | Step 4 call sites raise on tagged input. | PL-5 |
| `…::test_register_prompt_keeps_identity_and_policy_bounds` | The pinned prompt contains the identity fields from `public_profile()`, the AI/truthful rules and the provider-bound clause; `voice_lint` still fails private-register vocabulary on public text. | PL-3, PL-9, PL-14 |
| `test_w4_pl_budget.py::test_private_reply_is_refused_without_authorised_ceiling` | No call at CA$0 or over the ceiling; refusal audited without content. | PL-5 |
| Update `test_w3_laura_cc_private.py:75` | Its "no reply is generated" assertion becomes "a reply is generated only when enabled". | — |

Then a production soak (class B): owner sets the key, opens the private context, sends one turn, and confirms a reply and persistence across a redeploy. Only the owner sees the content. Evidence is recorded as row counts and status codes only.

### Owner actions (batched)

| ID | Exact action | Why | Max cost | Minutes | Consequence of waiting |
|---|---|---|---|---|---|
| OA-PL-1 | In Railway (production web service) add variable **`BRAMBLELOOP_PRIVATE_MEMORY_KEY`** = 32 random bytes, base64. Keep an offline copy. | The store refuses everything without it. Losing it loses the private store by design. | CA$0 | 5 | Private context stays 503 and the soak cannot run. |
| OA-PL-2 | Acknowledge D-W4-PL-1: build the register inside the provider's Usage Policy (warm, romantic, flirtatious, suggestive but not explicit). Sexually explicit content and erotic chat are not built and are not bypassed. | spec/07 note (a) and the current Anthropic Usage Policy ("Do Not Generate Sexually Explicit Content … Engage in erotic chats"). | CA$0 | 2 | The register stays wholly GATED. |
| ~~OA-PL-3~~ (REMOVED, D-W4-PL-3) | Record that human Laura consents to the AI Laura persona being used in the private register (the owner attests; the AI never asserts it). | PL-10, D-FB-13. | CA$0 | 2 | The register must not be enabled. |
| OA-PL-4 | Authorise spend for `laura.private_reply`: either inside Laura's existing CA$0.50/day or as a separate daily figure. | It is a new paid purpose under agent `laura`, and the owner approves spend. | Owner-set (suggest ≤ CA$0.50/day) | 2 | Replies are refused pre-call with an audited reason. |

---

## 6. Sequencing and file ownership (summary)

0. Board/Integrator: tracking row + D-W4-PL-1 draft (after OA-PL-2).
1. Gateway owner: `routing.py` task, isolated call (`anthropic.py` or `gateway/laura_private.py`), tests `test_w4_pl_leak` (gateway half), `test_w4_pl_budget`.
2. Laura owner: `prompts.py` `LAURA_PRIVATE_REPLY@1`, `test_w4_pl_boundary` (prompt half).
3. CC owner: `private_context.py`, `api.py`, `laura.js`, roadmap/voice_spec/presence status, `test_w4_pl_reply`, `test_w4_pl_auth`, `test_w4_pl_continuity`, update `test_w3_laura_cc_private`.
4. Protected owners: firewall call sites + tests.
5. PRIV owner: rekey + Postgres run.
6. Owner: OA-PL-1/2/4 (OA-PL-3 removed, D-W4-PL-3) → approved deploy → class-B soak.
