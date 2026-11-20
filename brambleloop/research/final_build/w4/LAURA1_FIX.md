# W4-LAURA1 — Laura's CEO briefing: root cause, fix, evidence, owner action

Production SHA with the defect: `0417f35`. Branch: `claude/w4-LAURA1` (not production).
Canonical identity unchanged: `laura-r2-a42aeac7` (portrait/identity assets untouched).

## 1. What the owner saw

The owner asked (verbatim, now the regression fixture `OWNER_CEO_BRIEFING`):

> Laura, give me a complete but concise CEO briefing. Tell me what Brambleloop accomplished in
> the last 24 hours, what each department is working on, what is preventing our first Etsy sale,
> and the five most important things you need me to decide. Separate verified facts from
> unknowns, and tell me what you can handle without my involvement.

Laura answered with a long template list of owner decisions and
`Method: deterministic retrieval over durable state + fixed templates (no model call)`.

## 2. Root cause (what existed and why it failed)

What exists (Phase 1, `src/brambleloop/laura/agency/`):

- `talk.converse` → `talk.classify`: **one keyword intent per question**, first rule wins.
  `needs_me` is the first rule and contains "need me", so "...things you **need me** to decide"
  routed the whole six-part question to `needs_me`.
- `needs_me` reads only the owner queue (`evidence.owner_queue`) plus Laura's voice owner action
  and renders `"{n} item(s) need you: …"` — the template list the owner received. The other five
  parts (24 h, departments, first-sale blockers, verified vs unknown, autonomy) were dropped
  silently. There was no multi-part parsing at all.
- No model synthesis existed. The only model path is optional *rephrasing*
  (`phrasing.py` → `gateway/laura_phrase.py`, `laura.business_phrase@1`, cheap tier, ≤3
  sentences), off unless `BRAMBLELOOP_LAURA_PHRASING=1`, and billed to `orchestrator`, not Laura.
- Budget: registry agent `laura` is declared GREEN with `daily_cost_ceiling_cad=0.0`
  (`agents/registry.py`). Monthly ceiling CA$100 (`finance.spend_policy`).
- Durable conversation: `laura_cc_turns` (question, answer, facts, sources, unknowns, proposals,
  method, session id). Private register: separate encrypted `laura_private_*` tables behind
  step-up (`laura/private/`); business paths never import them (`test_w3_laura_cc_talk`).
- Authority: follow-ons only via `followon.proposal` (GREEN missions inside a charter, or
  protected work as an owner action after step-up).

Gateway finding (not changed here, flagged): `anthropic.agent_daily_ceiling` returns `None` for
a ceiling `<= 0`, so `failover.decide` and `check_budget_cad` do **not** refuse a zero-ceiling
agent before the call; `ModelGateway._record` refuses only **after** the provider has billed.
"CA$0 = refused" therefore holds only after one paid call. Laura's new path refuses *before*
any reservation (below). A general fix belongs to the spend lane.

## 3. What changed

| File | Change |
|---|---|
| `laura/agency/briefing.py` (new) | intent parser, evidence pack, deterministic composer, model-output validator, follow-ups |
| `gateway/laura_briefing.py` (new) | pinned prompt `laura.ceo_briefing@1`, budget-gated synthesis through the existing gateway, cost estimator |
| `gateway/routing.py` | declared task `laura.ceo_briefing`: existing STANDARD tier (`claude-sonnet-5`), 1800 output / 6000 typical input tokens, `stronger_fallback=False` (no new model, provider or tier) |
| `finance/economics.py` | purpose `laura.ceo_briefing` classed SUPPORT (same as the phrasing task) |
| `laura/agency/talk.py` | `classify` returns `briefing` for a multi-part/briefing question before any single intent; `converse` answers briefings and resolves follow-ups ("expand decision 2") against the stored turn; phrasing is not applied to briefings |
| `tests/test_w4_laura1_briefing.py` (new) | regression suite (9 tests) |

How it answers now:

1. **Intent** (`briefing.parse`): components in the order asked — `last_window` (24 h; "last N
   hours/days" parsed), `departments`, `blockers`, `decisions` (N parsed: "five" → 5),
   `facts_unknowns`, `autonomous`; "complete but concise" noted. A question is a briefing if it
   says briefing/brief me/sitrep… or asks for ≥3 components. Single-intent questions keep their
   old routes.
2. **Evidence pack** (`briefing.evidence_pack`): existing readers only — jobs window + missions +
   timeline, autonomy department status, queued missions/open jobs, Laura's executive priorities,
   products/certification/Etsy state, phase, store surfaces (non-READY), open P0/P1 or
   publication-halting incidents, accounting (revenue/profit/spend), month spend vs ceiling,
   Laura's own daily permission, and the approvals inbox. Every item: id `E#`, source,
   ISO timestamp, status `VERIFIED` / `ESTIMATE` / `UNKNOWN` (UNKNOWN is never shown as 0).
   Items whose source names a private register or spouse context are dropped.
3. **Decisions**: the owner queue's own ranking (`build2.executor.approval_inbox` card `rank`,
   then Laura's voice-selection action), top N, never re-ranked by the model.
4. **Model synthesis** (`gateway.laura_briefing.synthesize`), agent `laura`, in order:
   Laura's daily permission (CA$0.00 → refused before any reservation, audited as
   `spend.refused` / `agent_daily_ceiling_unset`) → provider configured → `failover.gateway_for`
   (month + agent day per model, else PARK) → `complete_json` → `check_budget_cad`
   (month + provider + agent day + reservation, atomic) → billing via `_record`.
5. **Validation** (`briefing.validate`, deterministic): each model item must cite ≥1 id that
   exists in the pack (E#) or proposal list (P#); may not contain a number absent from the cited
   evidence; may not present UNKNOWN evidence as known; may not claim to be human; decision
   items must cite exactly one ranked decision; autonomy items must cite a GREEN proposal or
   work in progress and may not claim publish/spend/price/ads/customer contact. Rejected items
   are stripped and counted in the answer ("N unsupported claim(s) were removed"). The decision
   ranking, the VERIFIED/UNKNOWN listing and the authority boundary are always code-rendered.
6. **Fallback** (`briefing.compose`): same six sections from the same pack, top-5 decisions
   ranked, each line with `[E#]`, ≤4,500 chars, plus a first line such as
   *"Model synthesis unavailable: laura has no authorised daily model budget (daily ceiling
   CA$0.00); authorising one is an owner decision. This is my deterministic fallback briefing,
   built only from the evidence records cited below."* This is what production shows until the
   owner authorises a Laura budget.
7. **Follow-ups**: "expand decision 2", "tell me more about step 1", "explain blocker 1" resolve
   against the last briefing turn **in the same owner session** (durable `laura_cc_turns`), re-read
   the live inbox card for detail, and are deterministic (no model call).
8. **Delegation**: "what I can handle without you" lists only `followon.proposal` results —
   GREEN missions inside the department charter (confirm → queued through the existing
   follow-on route) and running missions; protected work (e.g. `store.publish`) is shown as
   "Not mine to do … stays your decision". Nothing is enqueued by the briefing itself.

## 4. Test evidence

Interpreter `brambleloop/.venv/bin/python`, `PYTHONPATH=src:tests`, one process at a time,
private `TMPDIR` removed afterwards. No network, no key, stub transports only.

`tests/test_w4_laura1_briefing.py` — **9/9 passed**:

- owner question (and the earlier reconstruction) → `briefing`, six components in order, 24 h,
  5 decisions; single intents unchanged;
- fallback at CA$0.00: zero provider calls, zero `CostEntry`, audited refusal, all six sections
  populated with `[E#]`, exactly five ranked decisions matching the queue ranking, every fact
  with id/source/ISO timestamp/status, revenue shown `UNKNOWN` never `CA$0`, ≤4,500 chars and ≤60
  lines, no private sentinel or spouse text, zero SQL touching `laura_private_*`;
- model path (stub provider, Laura's test-DB ceiling CA$1.00): one call on `claude-sonnet-5`,
  billed once to agent `laura`, grounded text used, decisions kept in queue order;
- unsupported claims (invented CA$1,250, no evidence id, unknown id E999, "I will publish …"):
  all four rejected with reasons, none rendered, answer states 4 removed;
- ceiling reached (CA$0.10 spent of CA$0.10): parked before the call, no new spend, fallback
  states "parked by the spend controls … agent 'laura' …";
- no key / provider error: transparent fallback, nothing billed;
- follow-ups resolve against the previous briefing (and not across sessions);
- cost estimate uses the gateway price table.

Existing suites run (all pass): `test_w3_laura_cc_talk` 9/9, `_private` 7/7, `_followon` 4/4,
`_delegation` 5/5, `_integration` 5/5, `_providers` 7/7, `_wiring` 5/5, `_access` 5/5,
`test_w3_laura_presence` 4/4, `test_w3_laura_core_executive`, `test_w3_k11_authority`,
`test_w3_spend_laura_phrase`, `test_gateway`, `test_spend_policy`, `test_model_access`,
`test_w4_spend_paid_discipline`, `test_model_spend_paths`, `test_v11_reliability_gateway`,
`test_rc1_spend`, `test_cost_governance_wave2`, `test_improve_director`, `test_v11_cc_auth`
16/16, `test_rc1_auth` 11/11; CLAUDE.md core three (`test_compiler`, `test_reverse`,
`test_twin`) pass. No test was weakened (one first-run failure in
`test_no_private_register_in_business_conversation` was fixed in the new code, not the test).

## 5. Cost estimate (existing policy, gateway price table; nothing set)

Model: the task's declared STANDARD tier, `claude-sonnet-5`, priced by
`gateway.anthropic.PRICES_USD_PER_MTOK` at USD 3 / 15 per MTok, converted at the assumed
0.715 USD/CAD (×1.3986). Token counts use the gateway's own accounting (`chars // 4` of system +
rendered prompt; `laura_briefing.estimate`). Reservation = padded ×1.25 with the full output
allowance. **Revised for the round-2 contract (prompt `@2`)**: the model now returns only
selected ids plus short notes, so the output allowance is 600 tokens (expected ~200).

| Case | Input tok | Output tok | Expected billed | Pre-call reservation |
|---|---|---|---|---|
| Seeded test DB (44 evidence items) | 3,319 | ~200 expected (600 max) | **CA$0.018** | CA$0.033 |
| Production-sized (all pack caps, 68 items, avg ~120-char statements) | ~5,000 | ~200 | **CA$0.025** | ~CA$0.042 |
| Production worst case (68 items × 400-char statements) | ~10,450 | 600 | CA$0.056 | CA$0.071 |
| Briefing + 2 follow-ups | follow-ups are deterministic (no model call) | — | **CA$0.025** typical (≤CA$0.056) | as above |

**Proposed Laura daily budget: CA$0.50/day** (not set). Covers ≥7 briefings even at the
worst-case reservation, ~12-20 typical briefings a day; expected use (≈3 briefings/day) ≈
CA$0.08/day, ≈CA$2.30/month; hard maximum exposure CA$15/month = 15% of the CA$100 monthly
ceiling, which stays authoritative.

Hard enforcement once set: (1) Laura's per-agent daily ceiling and (2) the monthly ceiling, both
checked before the call (`failover.decide` pre-filter, then `anthropic.check_budget_cad` under the
budget lock with a written reservation, padded estimate); every refusal writes a `spend.refused`
audit row; billing is the gateway's single `_record` path to `cost_entries` (agent `laura`,
purpose `laura.ceo_briefing@2`). At CA$0.00 (today) no call is attempted at all.

When the ceiling is reached Laura does **not** degrade to a weaker model or skip parts: the call
parks before it is made, nothing is billed, and the full deterministic briefing is shown with the
first line *"Model synthesis unavailable: parked by the spend controls: no available model fits
the money: … agent 'laura' CA$x of CA$0.50 today. Parked rather than routed to a weaker model.
This is my deterministic fallback briefing, built only from the evidence records cited below."*
Proven by `test_ceiling_reached_parks_before_the_call_and_falls_back_with_no_new_spend`.

## 6. OWNER ACTION REQUIRED (to enable model synthesis in production)

- **Action:** authorise a daily model budget for agent `laura` of **CA$0.50** (or another amount
  you choose). Implementation is one declared value: `daily_cost_ceiling_cad=0.0` → `0.50` in the
  `laura` entry of `DEFAULT_AGENTS` (`src/brambleloop/agents/registry.py`), deployed (the registry
  reconciles declared ceilings on boot). Also confirm the production `ANTHROPIC_API_KEY` is
  present and funded; without it the briefing states "no model provider is configured".
- **Why:** Laura has no authorised model budget; consequential spend needs owner approval.
- **Maximum cost:** CA$0.50/day (≤CA$15/month), inside the existing CA$100 monthly ceiling.
- **Minutes:** ~2 to approve.
- **If it waits:** briefings stay the deterministic fallback above — complete and grounded, but
  written by code rather than synthesised; nothing else is blocked.

## 7. Review fixes (independent review FIX-FIRST, origin/claude/w4-LAURAREV f64c8f9)

All findings addressed; each attack is a regression test in `tests/test_w4_laura1_briefing.py`
(now 13/13).

- **HIGH-1 validator** (`briefing.claim_problem`): per claim, every value -- digits *and*
  number words ("five hundred", "a dozen", "nothing") -- must occur in a cited record's
  *statement* (timestamps and window/N grant nothing; only the literal "last {window} hours"
  phrase is ignored); a claim citing an UNKNOWN record must say unknown and may state no value
  at all; sale/revenue, live/on-Etsy, refund, review, launch, customer and certification
  claims must cite a record stating that event type with the same polarity ("0 are on Etsy"
  cannot ground "now on Etsy"); publish/price/spend/buy/ads/outreach is refused in **every**
  section in the first person, and in any form unless a cited record names the act (no
  bare-word negation escape); broader human/physical-claim check; decision lines are the owner
  card's text verbatim in queue order, the model may only add one validated "Why it matters"
  line. All 11 reviewer attacks plus 4 paraphrases are rejected; faithful controls pass.
- **MEDIUM-1**: delegation is classified before briefing; a delegation that also asks for a
  brief says so instead of dropping it.
- **MEDIUM-2**: two or more asked-for parts are answered part by part (e.g. "What should I
  approve today and why is the shop not selling?" → decisions + blockers).
- **LOW-1**: "rundown of the store" / "status report on revenue" route to the topical intent.
- **LOW-2**: audit noise (refusals, session/security rows) never appears as an accomplishment.
- **LOW-3**: follow-ups are anchored to short "expand decision N"-style messages.
- **INFO**: DECISION_LOG entry D-W4-LAURA1 records the routing choice.

Fallback, spend checks, privacy and identity are unchanged.

## 8. Round-2 review (5dcb6c0): the model's contract changed — select and order, never assert

The round-2 review showed keyword validation of free prose keeps losing to rephrasing (7 of 19
new attacks passed). The prose validator is removed. Prompt `laura.ceo_briefing@2`: per
section the model may only **select and order evidence ids** allowed for that section (E#, or
P# GREEN missions for the autonomy section) and add **one note** of ≤20 words drawn from a
closed vocabulary (`briefing.NOTE_VOCABULARY`: connective/framing words only — no numbers, no
event words, no action verbs). Code renders every factual line from the selected record's own
statement text; decisions stay the owner queue's cards verbatim in queue order; the
VERIFIED/UNKNOWN listing and the authority boundary are always code-rendered. Any deviation in a
section (unknown/foreign/duplicate id, a field other than component/evidence/note, a word outside
the vocabulary, a digit) → that whole section falls back to the deterministic text, and the
answer says how many sections fell back.

Regression: all 30 reviewer attacks (11 round-1 + 19 round-2) are tests; each is rejected both
as a note and as free prose, and end to end none reaches the owner. New test: "Give me a CEO
briefing on the store and the decisions you need" keeps both parts (store → first-sale blockers
section + decisions); "What did you do overnight and what needs me?" keeps both parts. Suite
14/14. Output allowance fell 1,800 → 600 tokens, so cost estimates in §5 dropped.

## 9. Round-3 review (bd65fc2) fixes

- **HIGH-R3-1 mandatory records** (`briefing.mandatory`): code always renders, first and in code
  order, regardless of model selection — blockers: open P0/P1 or publication-halting incidents,
  the "N are on Etsy" product summary, UNKNOWN store/product reads, phase SHADOW, UNKNOWN revenue;
  last 24 h: the jobs completed/failed summary and any UNKNOWN read; departments: BLOCKED/DEGRADED
  departments and UNKNOWN reads. Decisions (top N) and the VERIFIED/UNKNOWN listing were already
  wholly code-rendered. The model may only add and order optional records. The fallback uses the
  same mandatory set.
- **MEDIUM-R3-2 note vocabulary**: now neutral connectives only (no not/verified/unknown/open/
  all/priority/worth/attention/most/key/first/top…); `decisions` and `facts_unknowns` take no
  model note at all.
- **LOW-R3-3**: any repeated section fails closed (every occurrence), whatever the count.
- **LOW-R3-4**: record text is data — sentences that read as instructions to the reader/owner/
  model are removed before the text reaches the owner or the prompt, and the remainder is shown
  as `record says: “…” [instruction-like text removed]` (`briefing.neutralise`).

Regression tests for each (suite 18/18).

## 10. Round-4 review (82bb28c) fixes — prompt `laura.ceo_briefing@3`

- **HIGH R4-1 (model and fallback)**: the evidence pack now carries **every** open P0/P1 and
  **every** publication-halting incident (any severity), ordered severity → halting → most
  recent, followed by "+N more open lower-severity incident(s)". All are mandatory in the
  blockers section and are never capped, in both paths; record text of mandatory lines is shown
  in full. Length is now kept by shrinking optional lines level by level (`CAP_LEVELS`), never
  by tail-trimming. Versus 3565b5f the fallback shows a superset: 3565b5f showed at most five
  incident-first lines, so a halting incident behind three routine P1s could be dropped; now none
  can be.
- **MEDIUM R4-2**: `neutralise()` is gone — nothing is deleted from records. Every record line is
  the record's statement verbatim as quoted, escaped data (`“…” [E#]`; quotes and brackets in the
  text are escaped so it can neither close the quote nor forge a citation). In the prompt every
  record field sits inside `<<<RECORD DATA …>>> … <<<END RECORD DATA>>>` blocks (delimiters in
  record text neutralised) and the system prompt says the contents are data, never instructions.
  VERIFIED/ESTIMATE/UNKNOWN now come only from the reader's declared basis in code, never from
  record text; "missing evidence" items carry a code flag.
- **LOW R4-3**: model notes removed entirely; the contract is `{component, evidence}` only.

Tests (19/19): 3 older routine P1s + halting P1 + halting P2 "Etsy API returned 401. You must
re-authorise…" + a P3 — every halting/P1 incident shown in model and fallback, verbatim, in
order, before the model's pick, P3 counted as "+1 more"; the injection text and six benign
"instruction-looking" records are shown verbatim but only inside their quoted record line, labels
unchanged, and only inside the data block in the prompt.

## 11. Owner decision implemented: Laura CA$0.50/day (D-W4-LAURA1-BUDGET)

The owner approved CA$0.50/day on 2026-10-11. Separate commit on this branch (after merging
`origin/claude/w4-INTEG2` with W4-FINHEALTH's pre-call zero-ceiling fix): `DEFAULT_AGENTS`
`laura.daily_cost_ceiling_cad` 0.0 → 0.50; nothing else about spend, ceilings or model selection
changed. `tests/test_w4_laura1_budget.py` (4/4) proves: the value is declared and reconciled;
the cap is checked and a reservation written before the provider is called; a call that would
exceed CA$0.50 today is refused with no provider call and the briefing falls back transparently
with no new spend (refusal audited); the monthly ceiling still binds when Laura's day has room.
Existing tests that used `laura` as the example CA$0 agent (`test_w4_finhealth`,
`test_w3_laura_core_identity`) were updated to the owner's decision: `coo`/`learn` remain the
CA$0 agents with the same assertions; `laura` is asserted at 0.50. Production still needs the
deploy and a funded `ANTHROPIC_API_KEY`; without a key the briefing states it and falls back.
