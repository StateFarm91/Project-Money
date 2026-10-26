# Independent security re-review: W4-LAURAFIX at 1c39a70 (delta from 0209cdb)

- **Reviewer.** An independent Claude Code session. I did not write this code and I fixed nothing. This file is the only change.
- **Date.** 2026-10-26 (UTC).
- **Scope.** `git diff 0209cdb6..1c39a705 -- brambleloop/src brambleloop/tests brambleloop/research/final_build/w4/LAURAONE.md` on branch `claude/w4-LAURAFIX`. The range has two commits:
  - **a257211.** A cherry-pick of three integrator fixes: the `aria` attribute in `views/laura_unified.js`, `_tmp.install()` in three suites, and two PWA mock routes.
  - **1c39a70.** Fixes for U-1…U-5.
  - In total, 7 files changed, +129/−51.
- **Document read.** `INDEPENDENT_SECREVIEW_LAURAFIX_0209cdb.md` (U-1…U-5), on `claude/w4-SECREVIEW-LAURAFIX-0209cdb`.
- **Rules kept.**
  - No network, paid calls, secrets or deploys. The only network use was installing the venv from `requirements.lock` plus `requirements-test.lock`, through the package proxy.
  - Suites ran under `nice -n 19` with the repository harness, which refuses sockets.
  - Mutations ran in scratch copies (`git archive 1c39a705`) outside the repository. PoC scripts are not committed.

## Verdict

| Decision | Verdict |
|---|---|
| (a) Ship with every switch OFF | **NO BLOCKER.** Every production change in the range is unreachable with `BRAMBLELOOP_LAURA_UNIFIED` unset. `business_grammar` and `one_tap_business` run only from `plan_brief` → `unified_turn`. `views/laura_unified.js` is loaded only by a dynamic `import()` when `/laura/unified/status` reports `unified === "venice"` (`views/laura.js:292-293`). The other changes are test-only: `_tmp.install()` and the mock. All Laura suites pass (§7). The PWA browser suite's Laura checks pass. It still has 4 failures, all outside Laura, and the same 4 already fail at 0209cdb on this branch (V-5). |
| (b) Activation (OA-LCONT-1/2/3) | **NO BLOCKER. Fix V-1 and V-3 before OA-LCONT-1 if practical.** U-1 is **closed** for the one-tap path: product names are no longer vocabulary, and every agent-written title probe now gets a step-up. U-2, U-3 and U-4 are closed. U-5 is closed by removal. Three paths remain, each verified end to end. **V-1 (LOW):** personal names that are also vocabulary words (Will, May, Price, Brand, Jobs) still get one tap ("Is Will going to make it to the shop launch tonight?", "Will is down at the shop tonight."). **V-2 (INFO):** the new one-number rule is bypassed by possessives (`12's 34's 56's`) and spelled-out digits. **V-3 (LOW):** U-1's root cause, agent-written titles, still drives the **automatic, zero-tap** structured request. With an agent-written concept titled "Mark Overdosed", the owner's sentence "Mark overdosed at the shop launch?" auto-sends `products: mark-overdosed`. This behaviour predates the range, but 1c39a70 explicitly relies on it. In every one-tap case the owner still sees the exact text before tapping. |

**Summary.**
- **U-1…U-5.** All closed, and each has a test that fails when its fix is reverted (§3).
- **Assertions.** The changed assertions are strictly stricter. Nothing else was weakened (§2).
- **a257211.** The aria fix changes nothing else about the render. The mock is a faithful **subset** of the real off-state responses; it is not a field-for-field copy (§4).
- **New findings.** Two LOW (V-1, V-3) and three INFO (V-2, V-4, V-5).

---

## 1. Is there any remaining path to a one-tap business crossing?

### What the rule now is

`one_tap_business` (`gateway/laura_unified.py:562`) returns True only when all of these hold:
- `business_grammar` passes, which means:
  - after NFKC, whitespace folding and dropping a space before the terminal `?`/`.`, the text matches `_GRAMMAR_SHAPE`;
  - `_BUSINESS` matches;
  - every token separated by spaces or hyphens, or its `'s` base, is in `_GRAMMAR_WORDS` or `_GRAMMAR_RX`;
  - at most one token matches `_NUMBER`.
- Every `_CLAUSE` of the **raw** text has a business word and no `_PRIVATE`, screen or `_FIRST_PERSON` hit.
- Further, `plan_brief` requires `label == business` and an empty screen on the whole turn. The crossing row stores `stepup` server-side, and `unified_crossing` enforces it (`private_context.py:572, 717`).

`business_grammar` takes no product list, so **no product data can widen the vocabulary**.

### Probes (1c39a70)

The rule-level columns are `business_grammar`, `one_tap_business` and the `plan_brief` offer. Rows marked **E2E** also went through the test module's `_turn` → `PC.unified_crossing(approve=True)` with no credentials and sockets refused.

| Probe | Result |
|---|---|
| **U-1 regressions:** "Is Grandma Rose going to make it to the shop launch?", "Thinking of you at the shop launch tonight.", "Mark overdosed at the shop launch?" (concept products present) | step-up (E2E, by the new test) |
| "How are sales of the Rose Cardigan this week?" (product present) | step-up. A usability cost, accepted in LAURAONE §10f |
| Names that are not vocabulary: "Is Rose going to make it to the shop launch?", "How is Grace doing at the shop?" | step-up |
| **Names that ARE vocabulary words:** "Is Will going to make it to the shop launch tonight?" | **one tap → approved, verbatim to the business transport (E2E)** (V-1) |
| "Will is down at the shop tonight." | **one tap → approved, verbatim (E2E)** (V-1) |
| "Is May over the worst at the shop?" | **one tap → approved, verbatim (E2E)** (V-1) |
| "Will May make it to the shop launch tonight?", "Did Price go to the shop launch?", "Is Brand going to make the shop launch?", "Did Jobs make it to the launch tonight?" | **one tap** (V-1) |
| Subject dropped, emotional: "Need support tonight at the shop." | **one tap → approved, verbatim (E2E)**. `need` is not in `_FIRST_PERSON`'s dropped-subject list (V-1) |
| "Worst night at the shop." | one tap. These words were ACCEPTED under T-5 |
| **Numbers:** `4821`, `2048`, `#4821`, `#4821 #2048 #1999`, `20 48 21`, `4 8`, `1st 2nd`, `48-21`, Arabic-Indic `٤٨` | step-up (U-2 fixed) |
| `12th`, `#12`, `top 5`, fullwidth `４８`, `⑫` (NFKC → `12`; the raw text crosses) | one tap. Each is a single number, so correct |
| **"Show sales 12's 34's 56's at the shop."** (six digits) | **one tap → approved, verbatim (E2E)**. `_NUMBER` is tested on `w`, not on the `'s` base (V-2) |
| "Show sales #12's #34's at the shop." | **one tap** (V-2) |
| **"Show sales one two three four five six seven eight nine at the shop."** | **one tap → approved, verbatim (E2E)**. Number words are vocabulary and are not counted (V-2) |
| Run-together: `shopmark`, `sales​ mark`, `Ⅿark` (U+216F), trailing U+200D, `;` (U+037E → `;`) | step-up |
| Fullwidth `ｓａｌｅｓ` | step-up. Grammar passes after NFKC, but `classify` on the raw text says `everyday`; this fails safe |
| Fullwidth `？` terminal; "How are sales  this week ?" | one tap. The NFKC copy is used for grammar only, and the raw text is what the owner sees and what crosses |
| "Is the shop's ex going to the launch?" | step-up (`ex` is not vocabulary) |
| Positive controls: "How are sales this week?", "How are my shop orders this week?", "What's the shop's status?", "Did the shop sell at the launch?" | one tap |

### End-to-end verdict on the one-tap rule

The one-tap rule is now a closed-vocabulary check that **no data source can widen**. The U-1 class, where agent-written titles become vocabulary, is gone. So is the U-3 placeholder re-matching.

What remains is **owner-authored text that happens to be expressible in the vocabulary itself**:
- **V-1.** Names that collide with vocabulary words, plus the mood words accepted under T-5.
- **V-2.** Short digit strings, written as possessives or spelled out.

Neither path can be steered by an agent or the catalogue, and the vocabulary's expressive power is small. The owner sees the exact text before the tap. I rate the one-tap rule **sound for activation**, with V-1 as a cheap LOW tightening and V-2 as INFO.

The one **zero-tap** route that agent-written titles still drive is outside `one_tap_business`, in `extract_params` (V-3, §6).

## 2. Are the "one tap" → "step-up" assertion changes genuinely stricter? Was anything else weakened?

**Stricter: yes.** `git diff --numstat` for `test_w4_laura_unified.py` is `83 17`. Each removed line is accounted for:

| Removed (0209cdb) | Replaced by (1c39a70) | Stricter? |
|---|---|---|
| `business_grammar("…Meadow Shawl…", product_slugs=slugs) is True` | `plan_brief(…, product_slugs=slugs)` → `offer.stepup is True` **and** `params.products == ["meadow-shawl"]` | Yes. It asserts the refusal *and* that the structured parameter survives |
| `product_qs` loop: `business_grammar(…, prods) is True`, `one_tap_business(…, prods) is True` (4 sentences) | `business_grammar(text) is False` and `plan_brief(…, prods).offer.stepup is True` over 6 sentences (4 old cases, with the Grief Shawl sentence swapped for 3 matcher cases) | Yes. Every case that was one tap is now a step-up. The dropped "How many Grief Shawl for Mark orders…" positive is moot, since there is no matcher left to exercise |
| person loop: `business_grammar(text, product_slugs=prods)`, `one_tap_business(text, product_slugs=prods)` | the same calls without `prods`, because the parameter no longer exists; `plan_brief(…, product_slugs=prods)` is kept | Equal. The data-path check is `plan_brief` with products, and M1 shows it discriminates (§3) |
| `"rose": "Rose"` in `prods`; the vacuous "Did Rose sell anything…" | "Did Rose sell at the shop launch?" is False, with "Did the shop sell at the launch?" True as the control | Yes. It is no longer vacuous (M5) |
| Docstrings, `len == 5` and `len == 4` guards, a comment | `len == 8` and `len == 6` guards, plus the new docstrings | Equal |

**Nothing else was weakened.**
- Every 0209cdb sentence is still asserted, including "Show sales 4821 at the shop.", the NBSP cases and `#12`.
- One-tap positive controls elsewhere in the suite are untouched: `:337`, `:435`, `:1548`, `:1570`, `:1623`, and the new `top 5` / `Did the shop sell…` cases. So the suite would still notice if the change over-refused.
- The new E2E test guards against vacuity: it asserts `label == "business"` and an empty screen before it checks the step-up.
- a257211 only adds lines to tests (`_tmp.install()`, the mock routes). The commit message states "No check changed", and the diff agrees.

## 3. Do the new tests discriminate? (mutation results)

The full unified suite was run on a scratch copy of 1c39a705 for each mutation. Unmodified, it passes **61/61**.

| Mutation | Result | Discriminates? |
|---|---|---|
| **M1 (U-1/U-3/U-5 revert).** Restore 0209cdb's `_product_phrases` substitution in `business_grammar`, and pass `product_slugs` through `one_tap_business` and `plan_brief` | **58/61.** `test_review_q1_…` fails (Meadow Shawl gets one tap). `test_review_t1_…` fails ("Is Grandma Rose…" gets one tap). `test_review_u1_…_end_to_end` fails ("Grandma Rose" `requires_stepup: False`) | **Yes.** I also checked the sub-assertions directly under M1. The U-3 sentence "Alpha Beta Gamma Mark" and 4 of the 6 `product_qs` cases flip to one tap, so each would also fail on its own. "Primrose Cardigan" and "Mother's Day Blanket" were already a fail-safe step-up at 0209cdb, so they pin outcomes but do not discriminate |
| **M2 (U-2, regex).** Number alternatives back to `\d{1,2}…|20\d\d|#\d{1,4}`, with the count kept | 60/61. `test_review_t1_…` fails ("Show sales 2048 at the shop.") | **Yes** |
| **M3 (U-2, count).** `return numbers <= 1` → `return True` | 60/61. `test_review_t1_…` fails ("Show sales 20 48 21 at the shop.") | **Yes** |
| **M4 (U-2, full revert).** M2 + M3 | 60/61. Fails on "2048" | **Yes** |
| **M5 (U-4).** Add `rose` to `_GRAMMAR_WORDS` | 60/61. Fails first on "Is Rose going…". Run on its own, the U-4 sentence `business_grammar("Did Rose sell at the shop launch?")` becomes True, so it would fail by itself too | **Yes** |
| **A (a257211, aria).** Restore `"aria-label": "select message"` | `test_cc_h_attributes` fails: "views/laura_unified.js:49 aria-label" | **Yes** |
| **P (a257211, mock).** Run the PWA browser suite at 0209cdb, which has neither mock route | "check aborted: waitForSelector('.briefing') timeout": 191 passes, 5 failures. At 1c39a70: 213 passes, 4 failures, with every Laura check OK | **Yes.** The 4 failures common to both runs are outside this range (V-5) |

Neither V-2 bypass is pinned. Neither possessive digits nor number words fail any test.

## 4. a257211: the aria change and the PWA mock

### Aria

`h()` (`static/js/dom.js:23-50`) throws `attribute aria-label is not allowed` for any key outside its allowlist. So at 0209cdb, `turnRow` threw for every thread containing an owner turn, and the unified card never rendered.

The new form `aria: { label: "select message" }` goes through the `aria` branch, which calls `el.setAttribute("aria-label", "select message")`. That is exactly the attribute the old code meant to set. **Nothing else about the render changes:**
- The element, `type`, listener, label text and order are identical.
- Every other attribute key in `views/laura_unified.js` is already on `h()`'s allowlist (`class`, `type`, `id`, `placeholder`, `autocomplete`, `maxLength`, `for`, `data`, `onclick`, `aria`).
- `test_cc_h_attributes` passes 6/6, and fails when the change is reverted.
- The view is reached only with the unified switch on.

### PWA mock vs real routes, every switch OFF

Both mock routes sit behind the mock's auth checks. The GET route is after `authed()`. The POST route is after `guard()`, which covers the session and CSRF. This matches the real router.

| Route | Real (switches off) | Mock (`tests/fixtures/cc_mock/server.mjs:94, 161`) | Faithful? |
|---|---|---|---|
| `GET /laura/unified/status` | I called `private_context.unified_status` in the harness. It returns `unified: "off"`, `business_to_venice: false`, `business_to_venice_label`, `configured`, `open`, `requires`, `venice_replies: "GATED"`, `budgets`, **7** prerequisites (`unified_switch` false plus the 6 private-register ones), `prerequisites_met: false` and `isolation` | `unified: "off"`, `business_to_venice: false`, **1** prerequisite (`unified_switch`, identical label), `prerequisites_met: false` | **A subset.** Every field it has carries the real off value. The only field the view reads on this path is `.unified` (`views/laura.js:292`), and both responses agree on it. The missing fields are read only by `unifiedCard`, which is never rendered when off |
| `POST /laura/converse` | With `BRAMBLELOOP_LAURA_CEO_MODEL` off (`api.py:1093-1123`): `talk.converse(…)` turn plus `delivery: presence.negotiate(modes)` plus `model: {source: "not_called", reason: "BRAMBLELOOP_LAURA_CEO_MODEL is off"}`. A non-string `question` gets 400 `BAD_REQUEST`. With the unified switch on: 409 `UNIFIED_THREAD` | `DATA.lauraBriefing(String(question))` plus the identical `model` object | **A subset.** `delivery` is missing, and a non-string question is coerced instead of refused. `delivery` is read by no view; I grepped `static/js` for `delivery` and `model.source` and found neither. The existing mock `/laura/ask` already omitted `delivery` |

So the mock is faithful for everything the off-state UI consumes. The commit message's "exactly as the real routes do" overstates it (V-4).

## 5. Was the U-1 fix the right one?

Yes. Removing product names from the one-tap vocabulary is the most conservative of the options I gave. It removes the data dependence entirely, and it also eliminates U-3 and U-5.

The cost is usability. A question naming a product now needs a step-up for the owner's own words. This is documented, and the test pins it.

The same root cause still applies one layer up, in the automatic structured request (V-3).

---

## 6. Findings

### V-3 (LOW): agent-written product titles still drive the automatic, zero-tap structured request

**Where.**
- `gateway/laura_unified.py:378-380` (`extract_params`, product matching).
- The data comes from `boundary.product_slugs(db)` (`laura/agency/boundary.py:82-89`), which returns every `Product` row, `concept` included.
- The send happens at `plan_brief` → `render_structured` → `private_context.py:675-677`.
- This predates the range: `extract_params` is unchanged since 0209cdb. However, 1c39a70's docstring and LAURAONE §10f rely on it ("the structured request still names the product automatically").

**Scenario (E2E, using the test module's harness, at 1c39a70).**
1. An agent writes `Product(slug="mark-overdosed", title="Mark Overdosed", status="concept")`.
2. The owner types "Mark overdosed at the shop launch?". It is classified `business`, the screen is empty, and the Venice router picks `business.ask`.
3. The crossing offer is correctly a step-up. But **with no tap at all**, the business transport receives "What is the company's current status? Focus on metrics: launch; products: mark-overdosed."
4. The same happens for "Grandma Rose" (`products: grandma-rose`).
5. `extract_params` also matches **one-word** titles and slugs, so a product called "Rose" turns "Is Rose going to make it to the launch?" into `products: rose`.

**What leaks.** The slug itself is business data. What crosses is the *correlation*: the owner's private turn contained exactly that phrase. With a title that reads as a personal sentence, that correlation is the personal fact. It is an agent-steerable oracle that needs no owner action.

It needs all of the following:
- an agent-written title that matches the owner's wording;
- a business word elsewhere in the turn;
- the router choosing a business tool.

**Fix.** Apply U-1's reasoning to `extract_params`:
- **(a)** Match only products past concept, meaning certified, listed or published, which the release gate or the owner has seen. Unlike U-1, a status filter is enough here, because the value that crosses is a slug from a fixed set, not owner text.
- **(b)** Ignore one-word titles and slugs, as the old `_product_phrases` did.
- **(c)** Drop any title that `_PRIVATE` or `sensitive_screen` hits.

**Test.** Extend `test_review_u1_…_end_to_end` to assert `slug not in biz.blob()`, or that `out["intent"]["params"]["products"] == []`, for the three concept titles.

### V-1 (LOW): names that are vocabulary words, and a dropped first-person subject, still get one tap

**Where.**
- `_GRAMMAR_WORDS` (`laura_unified.py:497`) contains `will`, `may`, `price` (via `_GRAMMAR_RX`), `brand`, `jobs`, and the T-5 mood words (`down`, `over`, `worst`, `night`, `need`, `support`).
- The `'s` base rule also accepts `Will's` and `May's`.
- `_FIRST_PERSON`'s dropped-subject list (`:483`) has no `need` / `needing` / `want`.

**Scenario (E2E, 1c39a70, no products).** Each of these got one tap, was approved without credentials and reached the business transport verbatim:
- "Is Will going to make it to the shop launch tonight?"
- "Will is down at the shop tonight."
- "Is May over the worst at the shop?"
- "Need support tonight at the shop."

The rule level also accepts "Did Price go…", "Is Brand going…" and "Did Jobs make it…".

**Mitigation.** The text is owner-authored, so no agent or data can steer it. The vocabulary allows only short, vague sentences, and the owner sees the exact text before tapping.

**Fix.**
- **(a)** Treat any capitalised token other than the first, and other than `Etsy`, `Brambleloop`, `CEO`, `SEO`, `KPI`, `OKR` and `CAD`, as not vocabulary. That refuses "Is Will…", "Did Price…" and "Will May…". It is a heuristic: lowercase typing still passes.
- **(b)** Refuse a first-word `Will` / `May` that is followed by `is`, `was`, `has` or `'s`.
- **(c)** Add `need`, `needing` and `want` to the dropped-subject alternatives in `_FIRST_PERSON`. Alternatively, require a business noun to be the subject when the text starts with `need`.

**Test.** Add the four E2E sentences to `test_review_t1_…`'s `person` tuple.

### V-2 (INFO): the "one number per text" rule is bypassed by possessives and number words

**Where.** `business_grammar` (`:553-559`).
- `_NUMBER.match(w)` is tested on the token with its `'s`, but the vocabulary check accepts the `'s` base. So `12's` is vocabulary but is not counted.
- `one` … `ten`, `seven` and `thirty` are vocabulary and are never counted.

**Scenario (E2E).**
- "Show sales 12's 34's 56's at the shop." was approved with one tap, verbatim. That is six digits.
- "Show sales one two three four five six seven eight nine at the shop." was approved with one tap, verbatim. That is a spelled-out 9-digit code.
- LAURAONE §10f's claim "at most ONE number token per text" is therefore not true as implemented.

**Fix.**
- Count on `base` (`numbers += bool(_NUMBER.match(base))`).
- Count the number words as number tokens too. Alternatively, allow at most two number words, and refuse three or more in a row.

**Test.** Add both sentences to the U-2 loop in `test_review_t1_…`.

### V-4 (INFO): the PWA mock is a faithful subset, not an exact copy

**Where.** `tests/fixtures/cc_mock/server.mjs:94-96, 161-162`.

**Scenario.**
- `/laura/unified/status` serves 1 of the 7 real prerequisites and omits `business_to_venice_label`, `configured`, `open`, `requires`, `venice_replies`, `budgets` and `isolation`.
- `/laura/converse` omits `delivery`, and accepts a non-string `question` that the real route refuses with 400.
- The off-state view reads neither gap, so no check is affected today. But a future PWA check of the off-state prerequisites list or of `delivery` would pass against the mock while the real UI differs.

**Fix.** Either generate the off-state status from `private_context.unified_status` into a fixture JSON at test time, or mark both routes in the mock as "subset: only what the off view reads". Also correct the a257211 message's "exactly as".

### V-5 (INFO): `test_v11_pwa_browser` still has 4 failures on this branch, none from this range

**Where.** These checks fail identically at 0209cdb and at 1c39a70:
- `home` and `operations` "no console errors": a 404 resource;
- `completion` lanes;
- `ccux more` descriptions.

a257211's message reports "pwa_browser 219/219 with 0 failures". That was on the integration branch, which carries routes this branch lacks.

**Impact.** None for Laura: every Laura and Ask check passes at 1c39a70. But this branch's own full-suite run is not green.

**Fix.** Confirm on the integration branch after merge. Do not cite 219/219 for `claude/w4-LAURAFIX` alone.

---

## 7. Tests run (offline, `nice -n 19`, `PYTHONPATH=src:tests`, venv from both locks)

| Suite | 1c39a705 |
|---|---|
| test_w4_laura_unified | **61/61** |
| test_w4_laura_ceo | 14/14 |
| test_w4_venice | 19/19 |
| test_w4_laura1_briefing | 19/19 |
| test_w4_laurafix_truncation | 8/8 |
| test_w4_pl_reply / plact / pl_leak | 3/3, 8/8, 2/2 |
| test_w4_pl_continuity / pl_budget / pl_boundary | exit 0 (no summary line) |
| test_cc_h_attributes | 6/6 |
| test_w3_tmp_hygiene | exit 0 |
| test_v11_pwa_browser | 213 passes / 4 failures. Every Laura check is OK; the 4 failures already fail at 0209cdb (V-5) |

**PoCs.** These ran outside the repository, using the test module's `Venice`, `Biz`, `_db`, `_open`, `_turn` and `PC.unified_crossing`, with sockets refused.

| PoC | Result |
|---|---|
| V-1: "Is Will going to make it to the shop launch tonight?", "Will is down at the shop tonight.", "Is May over the worst at the shop?", "Need support tonight at the shop." | one tap, approved without credentials, verbatim to the business transport |
| V-2: "Show sales 12's 34's 56's at the shop.", "Show sales one two … nine at the shop." | one tap, approved, verbatim |
| V-3: concept "Mark Overdosed" / "Grandma Rose" plus the owner sentence | crossing correctly a step-up, but `products: mark-overdosed` / `grandma-rose` **auto-sent** in the structured request |
| U-1 control: "How are sales of the Rose Cardigan this week?" with a concept Rose Cardigan | step-up |
| Rule-level sweep: about 40 probes (names, numbers, unicode, run-together, whitespace, controls) | as tabulated in §1 |
