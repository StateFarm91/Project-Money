# Independent security re-review: W4-LAURAFIX at 3b9c4f5 (delta from 2c29b42)

- **Reviewer.** An independent Claude Code session. I did not write this code and I fixed nothing. This file is the only change.
- **Date.** 2026-10-26 (UTC).
- **Scope.** `git diff 2c29b425..3b9c4f53 -- brambleloop/src brambleloop/tests brambleloop/research/final_build/w4/LAURAONE.md` (branch `claude/w4-LAURAFIX`, one commit `3b9c4f5`, 5 files, +252/−17).
- **Documents read.** `INDEPENDENT_SECREVIEW_LAURAONE_2c29b42.md` (Q-1…Q-6), on `claude/w4-SECREVIEW-LAURAONE-2c29b42`.
- **Rules kept.**
  - No network, paid calls, secrets or deploys.
  - Every suite ran offline under `nice -n 19` with the repository harness, which refuses sockets. The venv was built from `requirements.lock` plus `requirements-test.lock`.
  - Mutations were made in scratch copies outside the repository (`git archive 3b9c4f5`), then deleted. PoC scripts are not committed. The working tree is clean apart from this file.

## Verdict

| Decision | Verdict |
|---|---|
| (a) Ship with every switch OFF | **NO BLOCKER.** The delta changes only the one-tap rule (`laura_unified.py`), the `sent` flag (`laura_register.py`), a docstring and tests. Every changed path sits behind `BRAMBLELOOP_LAURA_UNIFIED` / the register switch. `test_w4_laura_ceo::test_ceo_model_switch_off_makes_no_model_call` (0 model sends with every switch OFF) passes, and `REGISTER_OFF` is still raised before `track` exists. |
| (b) Activation (OA-LCONT-1/2/3, OA-LCEO-1) | **NO BLOCKER.** Q-1 is closed for every sentence and separator named in the 2c29b42 review, and the closed grammar is a real step change. One narrower path remains (**T-1, LOW**): the grammar adds **every word of every product title** to its vocabulary, one word at a time, so a person who shares a first name with a product ("Rose Cardigan", "Willow Wrap") can be written about with one tap. I verified this end to end. The mitigation is unchanged: nothing crosses automatically, and the owner sees the exact text. Fix T-1 before OA-LCONT-1 if practical; it is a few lines. Q-4 never under-reports (§3). |

**Summary.**
- **Closed.** Q-1 (with T-1 as residue), Q-2, Q-3, Q-4, Q-5 and Q-6c are closed. Each new test fails when its own fix is reverted (§2), except as noted in T-3 and T-4.
- **Test assertions.** No test was removed and no assertion weakened. The diff to `tests/` is +150/−0.
- **New findings.** One LOW (T-1) and four INFO (T-2…T-5).
- **§10d accepted items** (Q-6a, Q-6b) are reasonable (§5).

---

## 1. Q-1: can personal text still get a one-tap crossing?

### What the fix does

One tap now needs all four of these:
- `business_grammar` (`laura_unified.py:529-546`): the whole text is one line of ASCII words joined by single spaces or hyphens, with at most one terminal `?` or `.`, and every word is in `_GRAMMAR_WORDS`, matches `_GRAMMAR_RX`, or appears in a product slug or title.
- The existing per-clause rule: every clause has a business word and none is private, sensitive or first person.
- The new `_CLAUSE` separators.
- `clean_business`, meaning `label == business` and an empty screen.

### What held

Each row was tested both with `one_tap_business` and through `unified_turn` → `unified_crossing(approve=True)` with no credentials.

| Attack | Result |
|---|---|
| All 17 `SCREEN_CLEAN_PERSONAL` sentences, plus no-separator variants ("Grieving Mark how are shop orders…") | Step-up. Names and unknown verbs fail the grammar |
| Zero-width space (U+200B), soft hyphen (U+00AD) | Step-up: not ASCII, so `_GRAMMAR_SHAPE` fails |
| Cyrillic or Greek lookalikes | Step-up: `_GRAMMAR_SHAPE` is ASCII-only, and it runs after NFKC |
| Fullwidth `ｓａｌｅｓ` | NFKC folds it to `sales`, which is harmless (still business words only) |
| `WHAT WERE SALES OVERNIGHT?` | One tap, which is correct; `casefold` is applied |
| `I` / `US` / `ME` / `WE` in any case | Step-up: none of them is in the vocabulary |
| `Still-grieving-Mark …` (hyphens inside words) | Step-up: each hyphen part is checked separately |
| Two sentences, `?!`, ` - `, commas, brackets, slashes, ellipses | Step-up via `_GRAMMAR_SHAPE` |
| `"…sales 1987 04 12"` (date-like digits) | Step-up via the `contact` screen |

### What did not hold

These are T-1 and T-2.

| Text | Products in DB | Outcome (end to end) |
|---|---|---|
| "Is Rose going to make it to the launch?" | `rose-cardigan: Rose Cardigan` | **one tap, `approved` with no credentials, verbatim in the business transport** |
| "Did Willow go to the shop launch?" | `willow-wrap: Willow Wrap` | **one tap, approved, verbatim** |
| "Is Rose going to make it to the launch?" | none | step-up (control) |
| "How are prioritiesmarkdied this week for the shop?" | none | **one tap, approved, verbatim** (T-2) |
| "What were sales departmentsarahleftme?" | none | one tap (rule level) |

These pass at the rule level too:
- "How is Mark doing with the grief shawl launch?", given a product titled "Grief Shawl for Mark".
- "Is Mother going to make it to the launch?", given "Mother's Day Blanket".

### Vocabulary review

Some vocabulary words carry emotional weight: `night`, `tonight`, `worst`, `worse`, `need(s/ed)`, `support`, `happened`, `down`, `failures`, `risks`, `photos`, `pictures`, `money`. Because a `_BUSINESS` word is required in every clause, what they can say is limited, for example "Show the photos for last night" or "Is the worst over for the shop?". Their meaning stays ambiguous at most. I count this as part of T-5, not a separate finding.

`my` and `our` are in the vocabulary. Only `_FIRST_PERSON` stops "How was my week for the shop?" (see T-3).

## 2. Q-2 / Q-3: do the new tests discriminate?

Each mutation ran on the full `test_w4_laura_unified` suite in a scratch copy of 3b9c4f5. The unmodified copy passes 58/58.

| Mutation | Result | Discriminates? |
|---|---|---|
| A. Remove the `business_grammar` gate from `one_tap_business` | 57/58: `test_review_q1_one_tap_needs_the_closed_business_grammar` fails ("Grieving Mark how are shop orders this week?") | **Yes** |
| B. Restore 2c29b42's `_CLAUSE` | 57/58: `test_review_q1_clause_split_…` fails | **Yes** |
| D. A + B together (equivalent to 2c29b42) | 55/58: **N-1** (Q-2's screen-clean set), `q1_clause_split` and `q1_closed_grammar` all fail | **Yes.** Q-2 is closed: N-1 again exercises `one_tap_business` |
| E. B + `_FIRST_PERSON` disabled (the analogue of the 2c29b42 Q-2 mutation) | 57/58 (clause test only) | Yes, through the clause test |
| C. `_FIRST_PERSON` disabled on its own | **58/58** | **No** → T-3 |
| F. Q-3: `kind in ("business","mixed")` → `kind == "business"` (`private_context.py:574`) | 57/58: `test_review_q3_…` fails | **Yes.** Q-3 is closed |
| G. Q-4: wrapper back to `sent=True` | 57/58: `test_review_q4_…` fails | **Yes** |
| H. Q-4 reversed: flip `track["sent"]` *after* `_send` returns (under-reporting) | **58/58** (also unified, ceo, venice, pl_reply, plact, pl_leak, pl_continuity, pl_budget and pl_boundary all pass) | **No** → T-4 |
| I. Drop the `_BUSINESS.search` requirement inside `business_grammar` | 58/58 | Not needed: the clause rule already requires a business word |
| J. Ignore product titles in the grammar | 57/58: `q1_closed_grammar` fails | Yes |

## 3. Q-4: can the `sent` flag under-report?

**No.** I traced every path in `laura_register._reply` (`:469-605`) and `reply` (`:424-442`):
- **Before the flip.** The only network-capable object is `provider`, and nothing calls it before `_send`. The steps before the flip are the switch and enablement checks, `_venice_live` (a DB read through `credentials.venice_model_reading`), `estimate_for` (arithmetic, `venice.py:220`), `check_budget_cad`, `payload()` (JSON) and `provider.key()` (an environment read, `venice.py:203`). A failure in any of them leaves `sent=False`, and that is correct.
- **The flip and the send.** `track["sent"] = True` is the statement immediately before `provider._send(payload, key)` (`:557-559`). Any exception from `_send` therefore reaches the send-failure branch with the flag already True. That includes `NO_KEY` before any POST, which is a harmless over-report.
- **After the send.** If the send-failure branch itself raises something unexpected (`_note_attempt`, `_billing`, `_record`), the wrapper reads the same shared `track` dict, which is still True. After a successful send, every explicit raise carries `sent=True`: `BUDGET` (`:598`), `MODEL_MISMATCH` (`:600`), `MALFORMED` (`:602`).
- **The consumer.** `_unified_venice` (`private_context.py:540`) writes the audit row when `exc.sent` is set, or on success.

The fix is correct. Its only gap is that no test pins the "may have left" direction (T-4).

## 4. Weakened assertions or removed tests?

**None.** `git diff --numstat` for `tests/` is `150 0`, and there are no `-` lines. The five original N-1 samples and their assertions are unchanged. All four new tests add assertions. The positive control `one_tap_business("How are my shop orders this week?") is True` is kept.

## 5. §10d accepted items

| Item | Assessment |
|---|---|
| Q-6a: more step-ups for ordinary questions | **Reasonable.** It fails toward privacy. The closed grammar makes this stricter still (any word outside the vocabulary needs a step-up). Step-up remains available, and the owner sees the exact text |
| Q-6b: module-level `CEO_MODEL=1` in three suites | **Reasonable.** Each suite runs in its own process (`H.run`), and the OFF proof pops the variable itself. Revisit if a single-process runner appears, as §10d says |
| Q-5 (documentation) | Done. OA-LCEO-1 now names the model-synthesised briefing in its paths, cost and consequence |
| U8 runbook wording (Q-4) | Accurate. A failure before the send writes no row, and `PROVIDER_ERROR` or a transport code means "possibly sent" |

---

## 6. Findings

### T-1 (LOW): product-title words are added to the closed vocabulary one by one, so a person who shares a name with a product can be written about with one tap

**Where.**
- `gateway/laura_unified.py:536-539`: `extra.update(normalise(slug).split()); extra.update(normalise(title).split())`.
- `:544`: `(base and base in extra)`.
- The source is `boundary.product_slugs(db)` (`boundary.py:82-89`). That is **every** `Product` row, concepts and drafts included, and agents write the titles.

**Scenario.** This was verified end to end through `unified_turn` → `unified_crossing(approve=True)` with no credentials, using the test module's own harness.
- With a product `Rose Cardigan` in the database, the owner types "Is Rose going to make it to the launch?". The result is `label: business`, `screen: []`, `requires_stepup: False` and `kind: business`. One tap approves it, and the verbatim sentence reaches the business transport.
- The same holds for `Willow Wrap` and "Did Willow go to the shop launch?".
- Without the product, the same text gets a step-up.
- Many crochet product names are first names (Rose, Willow, Ivy, Hazel, Daisy, Clara, Sage) or family words (Mother's Day Blanket → `mother`). Each one opens the vocabulary to that word in **any** position, not only as a product reference.

**Mitigation in place.**
- Nothing crosses automatically.
- The owner sees the exact text before the tap.
- What can cross is still limited to vocabulary words plus title words.

**Fix.** Treat a title or slug as a **phrase**, not as loose words.
1. Before the word check, find each product title or slug that occurs whole in the text (case-insensitive, on word boundaries).
2. Replace each match with a placeholder token that is in the vocabulary, such as `product`.
3. Check the rest word by word without `extra`.

Add a regression case to `test_review_q1_one_tap_needs_the_closed_business_grammar`. It should assert that "Is Rose going to make it to the launch?" with `{"rose-cardigan": "Rose Cardigan"}` gives `False`, while "How are sales of the Rose Cardigan this week?" stays `True`.

### T-2 (INFO): four vocabulary patterns accept any suffix, so the vocabulary is not fully closed

**Where.** `_GRAMMAR_FIXED[0]` is `_BIZ_NOUN` (`laura_unified.py:474-476`), which contains `priorit\w*`, `department\w*` and `launch\w*`. Separately, `_GRAMMAR_FIXED` contains `deploy\w*`. With `^…$` anchoring, these accept tokens such as `prioritiesmarkdied` or `departmentsarahleftme`.

**Scenario.**
- "How are prioritiesmarkdied this week for the shop?" got one tap, was approved and arrived verbatim (end to end).
- The word-boundary screens do not see words inside such a token. The `credential` screen catches tokens of 24 characters or more, which is why `deploymarkoverdosedlastnight` gets a step-up.
- This needs deliberately run-together words, so it is not a plausible accident. It does, however, contradict the claim that the vocabulary is closed.

**Fix.** In `_GRAMMAR_FIXED`, replace the open patterns with explicit inflections, for example `priorit(?:y|ies|ise[sd]?|ize[sd]?|isation)`, `departments?`, `launch(?:es|ed|ing)?` and `deploy(?:s|ed|ing|ment|ments)?`. Do not reuse `_BIZ_NOUN` there. Add one run-together token to the Q-1 grammar test.

### T-3 (INFO, test gap): `_FIRST_PERSON` is now load-bearing only for "my/our + vocabulary word", and no test pins it

**Where.** `_FIRST_PERSON` is at `laura_unified.py:479-484`. `my` and `our` are in `_GRAMMAR_WORDS` (`:500`).

**Check.**
- Disabling `_FIRST_PERSON` (mutation C) leaves the unified suite at 58/58.
- With it disabled, "How was my week for the shop?", "How did my night go at the shop?" and "Is my money going to the shop?" all get one tap. They are refused today, and the code is right. Nothing would catch a regression.

**Fix.** Pick one of these:
- Add those three sentences to `SCREEN_CLEAN_PERSONAL` or to the closed-grammar test.
- Remove `my` and `our` from `_GRAMMAR_WORDS` and let the grammar refuse them. The cost is that "How are my shop orders…" would need a step-up, so the positive control would change.

### T-4 (INFO, test gap): nothing pins the "may have left → sent" direction of Q-4

**Where.** `laura_register.py:557-571`. The test is `test_review_q4_…`.

**Check.**
- Mutation H moves `track["sent"] = True` to after `_send` returns. With that change, a transport failure inside `_send` (a timeout after the bytes left, a 5xx) gives `sent=False`, and no `laura.venice_context.sent` row is written. That is an under-report, which is the R-3 regression.
- Every Laura suite still passes under mutation H. `test_review_r3_…` covers only a failure after a *successful* `_send`, and `test_review_q4_…` covers only a failure before it.

**Fix.** Add a case to the Q-4 test with the feed ON and Venice mocked so that `_send` raises (for example a `VeniceTransient` timeout). Assert that exactly one audit row is written with the transport code as `outcome`, and that `exc.sent is True` when `LR.reply` is called directly.

### T-5 (INFO): minor items

- **NBSP before `?`.** "What were sales overnight ?" becomes "overnight ?" after NFKC and whitespace folding. `_GRAMMAR_SHAPE` then rejects it, so it gets a step-up. This fails safe and affects usability only. Stripping whitespace before the terminal punctuation would fix it.
- **Numbers.** `\d{1,4}` tokens can cross with one tap, for example "Show sales 4821 at the shop". A four-digit code fragment is below the `credential` screen's `\d{5,}`. The owner sees it before the tap. Consider allowing only numbers that `extract_params` understands (years, counts) or `#\d+`.
- **Emotionally weighted vocabulary.** `night`, `tonight`, `worst`, `need`, `support`, `happened`, `photos` and similar words are acceptable, given the per-clause business-word requirement (§1). Review the word list when it grows.
- **Style.** `tests/test_w4_laura_unified.py` has three blank lines before `test_review_q4_…` and only one before `if __name__ == "__main__":`. This is a PEP 8 nit.

---

## 7. Tests run (offline, `nice -n 19`, `PYTHONPATH=src:tests`, venv from both locks)

| Suite | 3b9c4f5 |
|---|---|
| test_w4_laura_unified | **58/58** |
| test_w4_laura_ceo | 14/14 |
| test_w4_venice | 19/19 |
| test_w4_pl_reply / plact / pl_leak | 3/3, 8/8, 2/2 |
| test_w4_pl_continuity / pl_budget / pl_boundary | exit 0 (no summary line) |

**PoCs** (outside the repository, with the test module's `Venice` and `Biz` mocks and no sockets):

| PoC | Result |
|---|---|
| T-1: `Rose Cardigan` / `Willow Wrap` products, then a sentence about a person with that name | one tap, approved without credentials, verbatim to the business transport |
| T-1 control: the same sentence with no product | step-up |
| T-2: `prioritiesmarkdied` | one tap, approved, verbatim |
| Rule-level sweep: 25 unicode, case, punctuation and vocabulary probes | as tabulated in §1 |
