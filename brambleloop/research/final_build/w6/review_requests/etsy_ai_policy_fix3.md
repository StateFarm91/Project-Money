# ENG-ETSY-AI-FIX3: review request (delta review of ENG-ETSY-AI-FIX was DO NOT SHIP)

- Branch: `eng/etsy-ai-policy` (on top of `2e32855`, which already contains the INTEG2 merge).
- The final SHA is given in the issue #28 comment.
- Not deployed. Not merged. Nothing touches Railway, production, secrets, Etsy, spend,
  `BRAMBLELOOP_PHASE` or `STAGE_A_ENABLED`. No human authorship or owner attestation is
  claimed anywhere. No gate is weakened. UNKNOWN is never PASS.
- Kept from FIX/FIX2: the 12 original bypasses, the Unicode tricks, H2a/b/c, the earlier
  mutants.

## H1: listing copy is a composition, not a bigger blacklist

New module: `src/brambleloop/publish/listing_composition.py`. `etsy_ai_policy.authorship_claim_problems`
now delegates to it, so all three existing callers use it: `gates.policy.check_listing`
(listing.seo and every package), `integrations.etsy.build_payload`, and
`manual_adoption.truth_problems`.

Every line of the title and description must be one of three things.

1. **An honest statement.** An exact sentence from the closed allowlist
   (`etsy_ai_policy.honest_statements`). This is the only source of any authorship,
   making, testing or provenance statement, and of the AI disclosure. Two concept-stage
   generator sentences joined the allowlist: `CONCEPT_AI_SENTENCE` and
   `CERTIFIED_CONCEPT_AI_SENTENCE`. `runtime.pipeline` and `creative.certification` now
   import them, so each sentence has one source.
2. **A template.** One line from the closed set in `listing_composition.templates()`. It
   covers every line `commerce.seo.build_description` emits:
   - the lead line and the value proposition
   - the key-phrase opening
   - the contents: rows, chart, US/UK editions, pages
   - the facts: size, skill, yarn and weight, fibre, gauge and hook, stitches, colours,
     yardage estimate
   - the season block, the support line, and the headings
   - the `commerce.terms` lines, as rendered
   - every `intel.childrens` statement, with its `{placeholders}` turned into slots

   Only the template's fixed words may mention making. Each slot value, such as the
   product title, a tag phrase, the difficulty or a yarn name, is checked by the
   constrained-field validator.
3. **Constrained free text.** This covers LLM-drafted prose, a concept premise and tag
   phrases. `constrained_problems` refuses a sentence on either of two independent rules:
   - **the lexical backstop** (`etsy_ai_policy.claims`). It is extended to the whole
     delta-review corpus:
     - AI denial
     - attribution to a named person ("Pattern by Emily Smith")
     - self-designed and independently designed, "I'm the designer", "the designer behind"
     - my hook or my studio, "my original", "original design"
     - artisan and handspun
     - photographed sample, real photo
     - "verified by", "goes through testing"
     - "Ive" as a subject; conceived and dreamed
     - misspellings one edit away (OSA distance 1) from designed, handmade, created and
       similar words, for example desgined, designd, hanmade and Handmaid
   - **the topic rule** (`listing_composition.topics`). Any mention of design, creation,
     making, testing, photos, samples, AI or humans is refused, whether or not it is a
     claim and whether or not it is true. It reads the same normalised forms, so the
     Unicode, spacing and leet tricks get the same answer here.

   Each refusal names the sentence and the reason, and listing.seo turns it into the
   hold card (`etsy_ai_policy.hold_card`).

Known fail-closed refusals of benign text, kept on purpose:

- "Designed for confident beginners", "Make a gauge swatch to test your tension" and
  "Includes a photo tutorial" are refused as free text.
- **L-c:** "Ideal handmade gift" and "Make a handmade gift" are refused, and the card says
  "mentions making ('handmade')".
- The one narrowing is that bare "craft"/"crafts" (the hobby noun, a real tag: "yarn craft
  project") is not a topic. "crafted", "crafting", "crafter" and "handcraft" still are.

## M-A: the owner's path out of UNKNOWN

The UNKNOWN status is lifted in these steps:

- `etsy_ai_policy.record_reading` is the only writer of an `etsy_ai_policy.reading` row.
  Only the Command Center action `etsy_ai_policy.record_reading` calls it. That action is
  `ACTIONS[...][0] is True`, so it requires a fresh step-up, together with owner session,
  CSRF and nonce. Preview is `etsy_ai_policy.reading_preview`.
- The record needs:
  - status PERMITTED or PROHIBITED
  - `policy_urls`: https etsy.com page(s)
  - `read_on`: not in the future, on or after the rules' last edit (2026-11-11), and at
    most `READING_MAX_AGE_DAYS = 30` old
  - `checked`: what was checked
  - the confirmation "I reviewed Etsy's current AI and creativity policy", verbatim
  - the preview digest
- `publication_status` accepts only a row that has all of these:
  - actor `owner…`
  - `attested_via == "command_center.step_up"`
  - URLs and `checked`
  - a fresh date

  An older reading goes **stale**, and the status is UNKNOWN again. The attestation is
  never inferred.
- One consolidated owner card is raised while the status is UNKNOWN:
  - `release_gates.for_publish` calls `ensure_owner_card`, with key `etsy_ai_policy.reading`.
  - `approvals.inbox` shows one card, `etsy_ai_policy:reading`, and folds the owner-queue
    row into it.
  - The card is computed on every read, so it returns the day a reading goes stale.
  - Only the owner's record closes it, as SATISFIED. Nothing auto-closes it.

## L-a

`tests/test_w6_etsy_ai_fix3_seo.py` uses the real certify → assets.build → listing.seo chain
(test_search_hero_publish fixture).

- A drafted "Handmade with love…" line raises `authorship_copy_hold:<slug>@<ver>`, and the
  card states its reason.
- A clean draft raises no card.
- The real drafted listing is checked unit by unit: every unit is a template, an honest
  statement or validated free text.

## Tests and mutants

Results pending: the broad regression run (172 suites) is in progress; this section is filled in by the next commit.
