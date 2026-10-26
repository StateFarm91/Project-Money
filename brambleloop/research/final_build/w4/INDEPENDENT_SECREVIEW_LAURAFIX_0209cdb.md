# Independent security re-review: W4-LAURAFIX at 0209cdb (delta from 3b9c4f5)

- **Reviewer.** An independent Claude Code session. I did not write this code and I fixed nothing. This file is the only change.
- **Date.** 2026-10-26 (UTC).
- **Scope.** `git diff 3b9c4f53..0209cdb6 -- brambleloop/src brambleloop/tests brambleloop/research/final_build/w4/LAURAONE.md` (branch `claude/w4-LAURAFIX`, one commit `0209cdb`, 3 files, +139/−18). The changed code is `gateway/laura_unified.py` (`_GRAMMAR_FIXED`, `_product_phrases`, `business_grammar`) and `tests/test_w4_laura_unified.py`.
- **Document read.** `INDEPENDENT_SECREVIEW_LAURAFIX_3b9c4f5.md` (T-1…T-5), on `claude/w4-SECREVIEW-LAURAFIX-3b9c4f5`.
- **Rules kept.**
  - No network, paid calls, secrets or deploys.
  - Suites ran offline under `nice -n 19` with the repository harness, which refuses sockets. The venv was built from `requirements.lock` plus `requirements-test.lock`.
  - Mutations ran in scratch copies (`git archive 0209cdb6`) outside the repository. PoC scripts are not committed.

## Verdict

| Decision | Verdict |
|---|---|
| (a) Ship with every switch OFF | **NO BLOCKER.** The delta changes only the pure function `business_grammar` and the grammar tables it uses, which are reached only through `one_tap_business` → `plan_brief` behind `BRAMBLELOOP_LAURA_UNIFIED`. No new I/O, no new switch, no change to the register or transport. All Laura suites pass (§6). |
| (b) Activation (OA-LCONT-1/2/3) | **NO BLOCKER, with one LOW to fix before OA-LCONT-1 if practical.** T-2 is closed: no open suffix is left. The reported T-1 sentences are closed. However, **U-1 (LOW)** remains: a *whole* product phrase is still turned into vocabulary, and product titles include agent-written `concept` rows. So a two-or-more-word title that reads as a person or an event ("Grandma Rose", "Thinking of You", or an adversarial "Mark Overdosed") still lets a personal sentence cross with one tap. I verified this end to end through `unified_turn` → `unified_crossing(approve=True)` with no credentials, and the sentence reached the business transport verbatim. The mitigation is unchanged: nothing crosses automatically, and the owner sees the exact text before the tap. T-5's number fix is partial (**U-2, INFO**). |

**Summary.**
- **Closed.** T-2, T-3 and T-4 are closed. T-1 is closed for every sentence the 3b9c4f5 report named, with U-1 left over. T-5 is closed for NBSP and the plain four-digit form, with U-2 left over.
- **Tests.** Every fix has a test that fails when the fix is reverted (§3). One test case is vacuous (U-4), and three properties of the phrase matcher are not pinned (U-5).
- **Weakening.** None (§4).
- **New findings.** One LOW (U-1) and four INFO (U-2…U-5).

---

## 1. T-1: can product-title or slug words still open the one-tap crossing?

### What the fix does

`_product_phrases` (`laura_unified.py:538-551`) builds one regex for each slug and each title that has **two or more** normalised words. Each regex matches the words in order, joined by `[ -]+`, bounded by non-alphanumerics, with an optional `'s`. The regexes are tried longest first. `business_grammar` (`:554-571`) replaces every match with the token `product`, which is a vocabulary word, then checks the remaining words without any title words.

The screen, `_PRIVATE`, `_FIRST_PERSON` and the per-clause business-word rule still run on the **raw** text (`one_tap_business`, `:574-586`). So title words still trigger those checks. The substitution only relaxes the grammar.

### Probes

The rule-level columns are `business_grammar`, `one_tap_business` and the `plan_brief` offer. Rows marked **E2E** also went through `unified_turn` → `unified_crossing(approve=True)`.

| Probe | Products | Result |
|---|---|---|
| Partial title: "Is Rose going to make it to the launch?" | Rose Cardigan, plus a one-word "Rose" | **step-up** (fixed; E2E control) |
| "Did Willow go to the shop launch?" / "Is Mother going to make it to the launch?" | Willow Wrap / Mother's Day Blanket | step-up (fixed) |
| Title inside a personal frame, but a partial phrase: "How is Mark doing with the grief shawl launch?" | Grief Shawl for Mark | step-up (fixed) |
| Slug with hyphen: "How are rose-cardigan orders this week?", "rose cardigan-orders", "Rose-Cardigan's" | Rose Cardigan | one tap. Correct: it is a product reference |
| Overlap / chained (see U-3): "How are Alpha Beta Gamma Mark sales this week?" | Alpha Beta Gamma, **Product Mark** | **one tap**, though no product is titled "Alpha Beta Gamma Mark" |
| Overlap, longest first: "Alpha Beta Mark Relapsed" | Alpha Beta, Product Mark Relapsed | step-up (the longer phrase is tried first and does not match) |
| Title with a personal word that a screen catches: "My mom is dying at the shop launch?" | My Mom Is Dying | step-up (`personal`, `relationship`) |
| Title containing `my`: "My Mom Blanket" | — | step-up (`_FIRST_PERSON`: `my` before a non-business noun) |
| Apostrophe title: "How are sales of the Mother's Day Blanket this week?" | Mother's Day Blanket | **step-up.** `normalise` makes the title `mother s day blanket`, and the regex needs `[ -]` between `mother` and `s`. This fails safe and affects usability only (U-5) |
| **Person-like two-word title**: "Is Grandma Rose going to make it to the shop launch?" | Grandma Rose (`status="concept"`) | **one tap → approved without credentials, verbatim in the business transport (E2E)** |
| "Is Little Hazel going to the launch at the shop?", "Did Auntie Clara like the new shop designs?" | Little Hazel / Auntie Clara | **one tap** |
| **Emotionally loaded title**: "Thinking of you at the shop launch tonight." | Thinking of You (`concept`) | **one tap → approved, verbatim (E2E)** |
| "Is the shop going to get well soon?", "Are hard times over for the shop?" | Get Well Soon / Hard Times | one tap (ambiguous at most) |
| **Adversarial title**: "Mark overdosed at the shop launch?" | Mark Overdosed (`concept`) | **one tap → approved, verbatim (E2E)** |
| "Sarah left Tom at the shop launch?", "Mark relapsed again at the shop launch." | Sarah Left Tom / Mark Relapsed Again | **one tap** |
| "Baby Ivy" title | Baby Ivy | step-up (`baby` is in `_PRIVATE`) |
| "Laura is leaving Jacob after the shop launch?" | Laura Is Leaving Jacob | step-up (`after` is not vocabulary) |

### Is the placeholder substitution itself abusable?

Yes, in a narrow way (U-3). The placeholder `product` is a word that a *later* phrase regex can match. Phrases are applied one after another, so a title that begins with `Product …` can absorb words that follow any other product phrase. Example: with titles "Alpha Beta Gamma" and "Product Mark", the text "Alpha Beta Gamma Mark" becomes `product Mark`, then `product`, and gets one tap. It needs an agent-written title starting with "Product", and it adds little beyond U-1, but it means the check no longer matches its own docstring ("only as its WHOLE slug or title").

The possessive and boundary handling held: `Rose Cardigan'smark` → `product'smark` (refused), `Rose-Cardigan-Mark` → `product-Mark` (refused), and `Rose Cardigans` does not match. Removing the boundaries entirely (M10) still fails safe in every probe I tried, because the token left behind is not vocabulary.

### Cost

`_product_phrases` compiles one regex per phrase on every call. With 5,000 synthetic products, one `business_grammar` call took 2.8 s. The catalogue is far smaller today, so this is a note, not a finding.

## 2. T-2 / T-5: is the vocabulary now closed?

**T-2: closed.** Every `_GRAMMAR_FIXED` alternative is an explicit list of inflections, and `_GRAMMAR_RX` wraps all of them in one `^(?:…)$` group. The following were all refused at the grammar level:
- The four run-together tokens in the test.
- `shopmarkdied`, `salesmark` and `deploymentsmark`.
- The `\w*` forms that remain in `_BUSINESS` / `_BIZ_NOUN`. They no longer matter, because the grammar must also accept every token.

`mock-?ups?` cannot match a hyphenated word after the `[ -]` split, so "mock-up" needs a step-up. That fails safe.

**T-5 numbers: partial (U-2).** Plain `4821` is now refused. But the replacement forms still let digits cross with one tap, and I approved one end to end:
- `#4821` is accepted, through the priority-id form `#\d{1,4}`.
- `2048` is accepted, through the year form `20\d\d` (2000–2099).
- `48th` / `21st` are accepted.
- `20 48 21` is accepted (six digits). It is 8 characters, just under the `contact` screen's 9.
- `Show sales #4821 #2048 #1999 at the shop.` (12 digits) was **approved E2E, verbatim**, because `#` breaks the `contact` screen's digit run.

**Space before `?`: sound.** `re.sub(r" ([?.])$", …)` runs after NFKC and whitespace folding, so NBSP, U+2009 and U+3000 before `?` are accepted. That is correct.
- It replaces only the final terminator. "Mark relapsed . What were sales ?" and "What were sales ? ?" are still refused by `_GRAMMAR_SHAPE`.
- U+200B is not whitespace, so it is still refused.
- `"What were sales  ."` is accepted, which is harmless.
- The rewrite affects only the grammar copy. The text that crosses is the raw `business_text`.

## 3. Do the new tests discriminate?

The unified suite was run in full on a scratch copy of 0209cdb6 for each mutation. Unmodified, it passes 60/60.

| Mutation | Result | Discriminates? |
|---|---|---|
| M1. Restore 3b9c4f5's loose title words (`extra`) | `test_review_t1_…` fails (Rose) | **Yes** |
| M2. Accept one-word titles (`len(w) >= 1`) | `test_review_t1_…` fails, but on the **Rose** sentence, not on the case written for it | Yes. The one-word case itself is vacuous (U-4) |
| M3a–d. Restore `priorit\w*`, `department\w*`, `launch\w*` or `deploy\w*`, one at a time | `test_review_q1_…` fails on each one's own token | **Yes**, each one separately |
| M4. Numbers back to `\d{1,4}` | `test_review_t1_…` fails ("Show sales 4821") | **Yes** |
| M5. Drop the NBSP / space-before-`?` rewrite | `test_review_t1_…` fails | **Yes** |
| M6 (T-3). Remove `_FIRST_PERSON` from `one_tap_business` | `test_review_n1_…` fails ("How was my week for the shop?") | **Yes** |
| M7 (T-4). Flip `track["sent"]` after `_send` returns (the 3b9c4f5 report's mutation H) | `test_review_t4_…` fails (no audit row) | **Yes** |
| M8. Remove longest-first ordering | 60/60 | No. It fails safe (a shorter match leaves a non-vocabulary word), so it is usability only (U-5) |
| M9. Remove the optional possessive `'s` | 60/60 | No. A trailing `'s` is stripped by the base-word rule anyway, so the group is redundant |
| M10. Remove the word-boundary look-arounds | 60/60 | No. It fails safe in the probes, but it is not pinned (U-5) |

## 4. Was any test weakened or removed?

**No.**
- `git diff --numstat` for `tests/` is `90 5`. The 5 removed lines are two loop headers. They were rewritten to loop over supersets: `SCREEN_CLEAN_PERSONAL + FIRST_PERSON_CLEAN`, and `cases` = the old three sentences plus four T-2 tokens.
- Every earlier sentence, assertion and positive control is still present, including the Meadow Shawl assertions and `one_tap_business("How are my shop orders this week?") is True`.
- Non-emptiness guards were added before both loops.

## 5. Overall verdict on the one-tap rule at 0209cdb6

**Requirements for one tap.** All of these must hold:
- `label == business` and the negative screen is empty.
- Every clause has a business word, and no clause has a `_PRIVATE`, screen or first-person hit.
- The whole text is one line of closed-vocabulary words, apart from whole product phrases.

**What the rule now resists.** Names, unknown verbs, run-together tokens, unicode tricks, punctuation joins, second sentences and partial product titles all get a step-up.

**The one remaining way in.** The rule's only remaining opening is the product catalogue, which is data that agents write. For text with any personal content to reach one tap, that personal content has to sit **entirely inside** a product title phrase of two or more words. The rest of the sentence must be vocabulary. Every one of the title's words must also pass `_PRIVATE`, the screen and `_FIRST_PERSON`.

**How likely that is.**
- **Accidental collisions.** These need a title such as "Grandma Rose" or "Thinking of You" plus an owner sentence about a real person with exactly that phrase. That is uncommon, but plausible for a crochet catalogue.
- **Deliberate collisions.** These need an agent to write a concept titled like a personal sentence and also predict the owner's wording. That is contrived.

**Mitigation.** In both cases the owner sees the exact text and taps. Nothing crosses without that tap.

I rate this LOW, not a blocker, and recommend the U-1 fix before OA-LCONT-1.

---

## 6. Findings

### U-1 (LOW): a whole product phrase is still vocabulary, and agent-written concept titles count, so a person-like or adversarial title opens one tap

**Where.**
- `gateway/laura_unified.py:538-551` (`_product_phrases`) and `:563-564` (the substitution).
- The source is `boundary.product_slugs(db)` (`laura/agency/boundary.py:82-89`): every `Product` row, including `status="concept"`.

**Scenario (E2E, using the test module's own harness).**
1. A `Product(slug="grandma-rose", title="Grandma Rose", status="concept")` exists.
2. The owner types "Is Grandma Rose going to make it to the shop launch?".
3. The result is `requires_stepup: False`, `kind: business`, and one tap approves it with no credentials. The sentence reaches the business transport verbatim.
4. The same happens for "Thinking of You" / "Thinking of you at the shop launch tonight." and for "Mark Overdosed" / "Mark overdosed at the shop launch?".
5. Without the product, each of these sentences gets a step-up.

**Fix.** Do (a) and (b); (c) is optional.
- **(a)** Count only titles of products past concept: `certified`, listed or published, so the owner or the release gate has seen them. Concepts and drafts are exactly the rows agents write without review.
- **(b)** Require the phrase to end in a closed craft-object noun (`cardigan`, `shawl`, `wrap`, `blanket`, `cowl`, `hat`, `kit`, `pattern`…). That still allows "Rose Cardigan", but refuses "Grandma Rose", "Thinking of You" and "Mark Overdosed".
- **(c)** Optionally, run `_PRIVATE` / `sensitive_screen` over each title when the phrase list is built, and drop any title that hits.

**Test.** Add the three E2E sentences above to `test_review_t1_…`, with the products seeded as `concept`.

### U-2 (INFO): the T-5 number forms still let 4- to 12-digit strings cross with one tap

**Where.** `_GRAMMAR_FIXED`, last entry: `\d{1,2}|\d{1,2}(?:st|nd|rd|th)|20\d\d|#\d{1,4}`.

**Scenario.**
- "Show sales #4821 #2048 #1999 at the shop." was approved E2E and arrived verbatim.
- "Show sales 2048 at the shop." and "Show sales 20 48 21 at the shop." get one tap.
- The `contact` screen's digit run stops at `#`, and `20 48 21` is one character under its minimum of 9.
- The owner sees the text first, so this is a code fragment or PIN leak only through the owner's own carelessness.

**Fix.**
- Allow at most one number token per text.
- Accept `#n` only when it is an existing priority id. It is already a structured parameter, so it can be checked.
- Accept a year only when the next or previous word is a date word, or drop the year form from the grammar and let `extract_params` handle it.

### U-3 (INFO): the placeholder can be matched again by a later phrase, so chained titles cover words that are not in any title

**Where.** `business_grammar` (`:563-564`): phrases are applied one after another to the same string, and the replacement `product` is plain text that later phrases can match.

**Scenario.** With titles "Alpha Beta Gamma" and "Product Mark", "How are Alpha Beta Gamma Mark sales this week?" gets one tap.

**Fix.** Substitute in one pass with a single alternation regex built from all phrases, longest first. Alternatively, substitute a sentinel such as `\x00` that no phrase can match and that the word loop accepts explicitly. Also drop any title whose words include `product` / `products`.

### U-4 (INFO, test): the one-word-title case in `test_review_t1_…` is vacuous

**Where.** `tests/test_w4_laura_unified.py`: "Did Rose sell anything at the shop launch?" (commented "one-word title 'Rose'").

**Check.** `anything` is not vocabulary, so the sentence is refused whatever the one-word rule does. With one-word titles re-enabled (M2), `business_grammar` is still `False` for it, while "Did Rose sell at the shop launch?" becomes `True`. M2 is caught only by the first Rose sentence, because the `"rose": "Rose"` product happens to be in the same dict.

**Fix.** Replace `anything` with vocabulary, for example "Did Rose sell at the shop launch?", and assert the case with `{"rose": "Rose"}` alone.

### U-5 (INFO): minor items

- **Unpinned matcher properties.** No test pins the longest-first order (M8), the word-boundary look-arounds (M10) or the possessive group (M9, which is redundant with the base-word rule). All of them fail safe today. Add "Rose Cardigan Kit" with both "Rose Cardigan" and "Rose Cardigan Kit", plus "Primrose Cardigan" with "Rose Cardigan", if they are meant to stay.
- **Apostrophe titles never match.** "Mother's Day Blanket" normalises to `mother s day blanket`, so the regex needs `mother[ -]+s` and "the Mother's Day Blanket" in text gets a step-up. Only "Mothers Day Blanket" matches. This fails safe. Build the regex from the title's own tokens with `['’]?` between letters, or normalise the text the same way before matching.
- **Cost.** `_product_phrases` compiles regexes on every call: 2.8 s for 5,000 products. Cache the compiled patterns per `product_slugs` snapshot if the catalogue grows.
- **Doc.** LAURAONE §10e says the T-1 test covers "a one-word title". In practice that case is vacuous (U-4).

---

## 7. Tests run (offline, `nice -n 19`, `PYTHONPATH=src:tests`, venv from both locks)

| Suite | 0209cdb6 |
|---|---|
| test_w4_laura_unified | **60/60** |
| test_w4_laura_ceo | 14/14 |
| test_w4_venice | 19/19 |
| test_w4_laura1_briefing | 19/19 |
| test_w4_laurafix_truncation | 8/8 |
| test_w4_pl_reply / plact / pl_leak | 3/3, 8/8, 2/2 |
| test_w4_pl_continuity / pl_budget / pl_boundary | exit 0 (no summary line) |

**PoCs.** These ran outside the repository, using the test module's `Venice`, `Biz`, `_db`, `_open` and `_turn`, with sockets refused.

| PoC | Result |
|---|---|
| U-1: Grandma Rose / Thinking of You / Mark Overdosed (concept products) | one tap, approved without credentials, verbatim to the business transport |
| U-1 control: "Is Rose going to make it to the launch?" with Rose Cardigan | step-up |
| U-2: "Show sales #4821 #2048 #1999 at the shop." | one tap, approved, verbatim |
| Rule-level sweep: about 50 probes (title, slug, overlap, run-together, numbers, whitespace) | as tabulated in §1–§2 |
