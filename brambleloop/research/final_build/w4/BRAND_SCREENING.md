# Trademark knock-out SCREENING: "Brambleloop" / "Brambleloop Studio" (W-BRANDSCREEN)

**This is a free knock-out screening by the company, not legal advice and not a clearance
opinion.** A knock-out finds obvious conflicts cheaply. It cannot rule out unregistered
(common-law) rights, pending applications not yet published, foreign rights, or a confusion
finding by an examiner or a court. Formal clearance, if wanted, goes to a trademark agent
(Master Plan v1.2 §29: "escalate formal legal clearance to the owner/professional if needed").

- **Date:** 2026-10-27 (UTC).
- **Branch:** `claude/w4-BRANDSCREEN`, from LAUNCHFIX `0f0306dd`.
- **Machine-readable draft:** `evidence_BRANDSCREEN/knockout_draft.json`.

## Status: INCOMPLETE. Not recorded as a knock-out search.

`brand.clearance.KNOCKOUT_SEARCHES` stays **empty**. Two reasons:
- The three trademark registers and the marketplace and social checks block or do not permit automated querying, and the company does not evade that. They need a person.
- Search-engine coverage of a register is not a register search, and recording it as one would make `brand_clearance` read cleared on evidence that is not there.

`tests/test_w4_brandscreen.py` pins the gap. The draft fails `clearance.problems()` exactly on the person-only screens, and the domain screen passes on its own.

## What was checked automatically, and what it found

| Screen | Source (automated, compliant) | Result |
|---|---|---|
| Domains | RDAP, the registries' public machine protocol: Verisign `.com` and CIRA `.ca` (via rdap.org), 2026-10-27 17:31Z. Control: `etsy.com` → 200. | `brambleloop.com`, `brambleloopstudio.com`, `bramble-loop.com`, `brambleloop.ca` and `brambleloopstudio.ca` are all **unregistered** (404). Raw CIRA replies are in `evidence_BRANDSCREEN/`. |
| Web (identical name) | Web search for `"Brambleloop"` | No business trading as Brambleloop in crafts. Two hits: a hobbyist's miniature figure named "Brambleloop" (CoolMiniOrNot), and **brambleloophq.space**, "Brambleloop HQ", a small games studio (a social-casino game, "Crazy Monkey"). That domain **did not resolve** on 2026-10-27 and is recorded from the search snippet only. |
| CIPO (indexed records only) | Web search `BRAMBLE site:ised-isde.canada.ca/cipo/trademark-search`. One public record page fetched; `robots.txt` does not disallow `/cipo/`. | **BRAMBLE BERRY**: TMA928596, application 1614556, registered 2016-02-10, expires 2031-02-10. Owner Bramble Berry, Inc. (Bellingham WA). Nice 35/40/41: retail and online retail of soap-making supplies; "education services, namely, providing on-line tutorials in the field of soap making". Also OTION (same owner), expunged. No BRAMBLELOOP or BRAMBLE LOOP record surfaced. |
| USPTO (indexed only) | Web search | No BRAMBLELOOP record surfaced. The nearest are BRAMBLE & MOPS (serial 50009390, filed 2026-07-23, plush toys, live application) and the BRAMBLE BERRY marks (soap making). |
| Marketplace (indexed only) | Web search | No shop named Brambleloop. Same-field "Bramble" names: Etsy shop **BramblesAndHart** (crochet hats, scarves, jumpers), Bramble & Fleece (UK yarn), many patterns titled "Bramble", and "bramble stitch", a standard knit and crochet stitch name. |

## Similarity assessment (screening view, by Nice class)

The relevant classes are:
- **16:** printed matter, including printed patterns;
- **9:** downloadable patterns and PDFs;
- **41:** education and tutorials;
- **35:** retail and online retail of patterns or craft supplies;
- **23 / 26:** yarn and haberdashery, only if the company ever sells physical supplies.

- **Identical or near-identical marks (BRAMBLELOOP, BRAMBLE LOOP):** none found in any class by the automated screens.
- **BRAMBLE BERRY (CA, 35/40/41).** The nearest registered mark in the jurisdiction. It shares only BRAMBLE, a common botanical word. The fields differ (soap making vs crochet patterns), and BRAMBLELOOP reads as one coined word whose distinctive part is the whole. Screening view: **not a conflict**, but it is the closest class-41 craft-education registration, so it is listed under residual risk.
- **BramblesAndHart (Etsy, crochet goods).** This is the same field. The composite is different (BRAMBLES AND HART), and no registration was seen. Screening view: **not a conflict**, but it is the nearest marketplace neighbour.
- **"Bramble" in the craft field generally.** "Bramble stitch" is a standard stitch name, so BRAMBLE alone is weak and descriptive here. That cuts both ways: others cannot easily monopolise it, and neither can we. Our protectable element is the coined whole, BRAMBLELOOP.
- **Brambleloop HQ (games).** The identical first word in an unrelated field (Nice 9/41 entertainment), and apparently inactive. It is not a conflict for craft patterns. It is the one identical-name user found, and it would matter for a filing in class 9 or 41 broadly drafted.

## What needs a person (exact steps; about 25 minutes, CA$0)

Each of these blocks automated access or has no compliant machine route, so they were not queried. Search each term **exactly**, with every status (live, pending and dead), and note each hit's mark, number, owner, classes and status.

1. **CIPO, Canadian Trademarks Database:** https://ised-isde.canada.ca/cipo/trademark-search/srch
   - Field "Trademark": `brambleloop`, `bramble loop`, `bramble*` (wildcard), `bramblelope`, `brambleloops`.
   - Also `bramble*` with a Nice class filter of 16, 9, 41, 35 or 23.
2. **USPTO Trademark Search:** https://tmsearch.uspto.gov/search/search-information
   - Wordmark searches for `brambleloop`, `bramble loop` and `bramble*`.
   - Then `bramble*` limited to International Classes 016, 009, 041, 035 and 023.
3. **WIPO Global Brand Database:** https://branddb.wipo.int/en/quicksearch
   - Brand name `brambleloop` and `bramble loop`, all offices, then filter Nice 16/9/41.
4. **Etsy:** shop search https://www.etsy.com/search/shops?search_query=brambleloop, and the same for `bramble loop` and `bramble`. Also a listing search for `brambleloop`.
5. **Social handles.** Check whether each is taken: https://www.instagram.com/brambleloop/, https://www.pinterest.com/brambleloop/, https://www.youtube.com/@brambleloop, and a Ravelry designer search for "Brambleloop".

When those results exist, the company fills `knockout_draft.json` from them: an https source, the queries, and every hit with relevance and why. `conflicts` lists exactly the hits marked conflict. The completed entry is then added to `brand.clearance.KNOCKOUT_SEARCHES` through review. `brand_clearance` then becomes owner-decidable: the owner previews and accepts the residual risk (sealed, step-up). Registration stays optional.

## What the owner would be accepting as residual risk (once the person screens are done)

If the person-checked registers also show no BRAMBLELOOP-like mark, accepting the risk means accepting all of the following:
1. **Unregistered prior users** in Canada or the US (common-law rights) that no register shows, including the dormant "Brambleloop HQ" games name and any small craft seller using a similar name.
2. **Applications filed but not yet published or searchable**, which typically lag weeks to months.
3. **Similarity calls made by a screener, not an examiner:**
   - BRAMBLE BERRY (CA, class 41 craft tutorials, soap);
   - the Etsy shop BramblesAndHart (crochet);
   - a generally crowded "Bramble" field in yarn crafts.

   A third party or examiner could weigh these differently, most plausibly against a future application of ours in class 41 or 16.
4. **No registration of our own (if not filing).** Nothing stops a later filer of a similar mark, and enforcing the name later rests on proof of use. Filing (CA$458.05, first class) is a separate decision and is **not** required for launch.
5. **Foreign rights** (EU, UK, AU and others) are not screened beyond whatever WIPO shows.
6. **Exposure grows with use:** low at zero sales, and higher as the name appears on more listings, PDFs and images.

## Sources (all read 2026-10-27)

- CIPO record BRAMBLE BERRY: https://ised-isde.canada.ca/cipo/trademark-search/1614556
- CIPO `robots.txt`: https://ised-isde.canada.ca/robots.txt (no `/cipo/` disallow)
- RDAP: https://rdap.verisign.com/com/v1/domain/ (`.com`); https://rdap.org/domain/ → CIRA (`.ca`)
- Web searches: `"Brambleloop"`; `"Bramble Loop" OR "Brambleloop" trademark`; `"Bramble Loop" yarn OR crochet OR knitting OR pattern`; `BRAMBLE site:ised-isde.canada.ca/cipo/trademark-search`; `"BRAMBLE" trademark registered knitting OR crochet OR yarn ...`; `"Brambleloop" OR "Bramble Loop" Etsy shop OR instagram OR ravelry`; `"Bramble" Etsy shop crochet patterns ...`
- Hits referenced:
  - https://www.coolminiornot.com/438025
  - https://brambleloophq.space/ (did not resolve)
  - https://www.etsy.com/shop/BramblesAndHart (not fetched; bot protection)
  - https://trademarkregistration.app/Trademark/Details/50009390
  - https://knitwithme.co.uk/collections/bramble-fleece
  - https://texturedknits.blogspot.com/2014/09/bramble-stitch.html
