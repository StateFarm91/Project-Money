# W4-COPY: customer claims, verified

Date: 2026-10-11 (UTC). Branch `claude/w4-COPY`, from `origin/claude/w4-INTEG2` 68224ac.
Store copy is now **copy_v3**. The single content source is
`store_foundation/copy_v2.py` (the module name is unchanged so every reader keeps working).
`export()` now carries the `claim_register` for the STOREFRONT lane.

## What changed in the copy

**Rewritten for a professional crochet-pattern brand.** The About, announcement, Laura intro,
returns, support, sale message, FAQ answers and trust line now cover: original design work,
clear instructions in US and UK terms, practical projects, free corrections and support. The
rejected v1 About ("the way software gets made … a compiler") had survived as
`brand.storefront.ABOUT`, and the owner's Info & appearance paste step pointed at it. It now
*is* the store copy.

**AI disclosure.** The disclosure that Etsy's rule requires is now one plain sentence,
carried verbatim in every listing description, the FAQ and the shop disclosure:
"This design was created with AI assistance, and every row's stitch count is checked before
release." It replaces "…directed and edited by the designer". That wording read as a human
designer, and there is none. The policy text this rests on is in
`gates/policy_knowledge.py`, creativity_standards, read 2026-09-26:
- "Sellers must disclose within their listing description if an item is created with the use
  of AI."
- "Designed by a seller: original designs by a seller or seller-prompted AI art offered as a
  digital download …"

**Laura.** She is "Brambleloop's AI founder and the face of this shop … an AI, not a person".
She is never the seller. The human account holder is named as responsible for every order.

**Listing description template** (`commerce.seo.build_description`):
- "automated pattern compiler" is gone; the disclosure sentence is used instead;
- "a colour chart generated from the same data" is now "a chart drawn from the same pattern …
  so the two always agree";
- the PDF disclosure and the pipeline's fallback draft were changed the same way.

**Terms** (`commerce.terms`). Two new options were added and chosen; the old options are kept
for history:
- the redistribution term now says "its images", not "its photographs", because the shop has
  none;
- the version term now says "corrections are free: a corrected pattern replaces the old file,
  and anyone who bought an earlier version can ask for the corrected one at any time". The
  old "free forever, and buyers are told when the version they own changes" promised a notice
  no channel can send.

The terms are still `legal_review=None`, and every surface says so.

## Claim table

| ID | Topic | Before | Verdict | Evidence | Wording now | Open review |
|---|---|---|---|---|---|---|
| C-01 | AI involvement / designer | Parts of this design were developed with AI assistance, directed and edited by the designer. | REMOVED | 'the designer' reads as a human designer; Brambleloop has none (Laura is an AI, D-FB-13). Etsy: 'Sellers must disclose within their listing description if an item is created with the use of AI' and 'Designed by a seller: original designs by a seller or seller-prompted AI art offered as a digital download' (gates.policy_knowledge creativity_standards, read 2026-09-26). | This design was created with AI assistance, and every row's stitch count is checked before release. (gates.platform_policy.DISCLOSURES['ai_assisted_design'], carried verbatim in every listing description, the FAQ and the shop disclosure.) |  |
| C-02 | originality | Brambleloop Studio designs crochet patterns (original designs). | QUALIFIED | Each CIR carries an originality record (products/originality, policy_knowledge creativity_standards 'originality'); competitor research is demand intelligence only (CLAUDE.md). 'Original' as a legal non-infringement assurance has not been reviewed. | 'Brambleloop Studio designs crochet patterns' -- the word 'original' is not used as a guarantee in customer copy. | **legal**: Is an originality/non-infringement statement wanted, and on what clearance? |
| C-03 | testing / physical samples | (no claim of test-making or physical samples anywhere) | SUPPORTED | No PhysicalTest is complete (executor gate physical_proof closed in production 2026-10-11); copy says 'We have not yet worked physical samples' and the FAQ says 'we have not yet worked a physical sample'. | 'We have not yet worked physical samples, so make a gauge swatch first.' FORBIDDEN refuses tested-by / test-made / sample-made claims. |  |
| C-04 | stitch-count / chart accuracy | every row's stitch count is checked; a chart that matches the words | SUPPORTED | cir/compiler.py verifies every row's count and repeat division; cir/reverse.py reads the finished document back against the design; gates/certificate.py refuses release on a mismatch. Charts render from the same pattern (publish/charts.py, cir/twin.py). Listings exist only for certified releases. | 'every row's stitch count adds up, every repeat divides evenly, and the written pattern is read back against the chart'; listing: 'A chart drawn from the same pattern as the written instructions, so the two always agree'. |  |
| C-05 | US/UK terminology | two complete PDFs, one in US terms and one in UK terms | SUPPORTED | publish/pdf.py TERMINOLOGIES; assets.build renders both and store.publish attaches both (commerce/seo.py build_description note). | unchanged |  |
| C-06 | digital delivery | instant download; no processing time; nothing is posted | SUPPORTED | Etsy help 115013328108 'How to Download a Digital Item' (read 2026-10-11 through the Help Center API): files are on the Purchases page once payment clears. | unchanged |  |
| C-07 | commercial use of finished items | finished items may be sold by individual makers and small businesses, not manufactured at scale | QUALIFIED | commerce.terms FINISHED_ITEM_SALE (decided by the build); terms.enforceable is False and every surface says 'not yet been through legal review'. | unchanged sentence, rendered from commerce.terms with its review caveat | **legal**: Are these licence terms enforceable as written (Canada, US, EU buyers)? |
| C-08 | corrections / version updates | corrections and revisions are free forever, and buyers are told when the version they own changes; 'we send the corrected file to everyone who bought it' | QUALIFIED | No Etsy Messages API exists ('conversation' 1 occurrence in Etsy's OpenAPI, intel.etsy_surfaces), so a notice to every past buyer would be a person typing each message. Etsy help 115015628347 says nothing about past buyers receiving replaced files. 'Forever' was a perpetual promise nobody reviewed. | 'corrections are free: a corrected pattern replaces the old file, and anyone who bought an earlier version can ask for the corrected one at any time'; 'we correct the pattern itself and send you the corrected file'. | **owner**: Do you want to commit to proactively messaging past buyers on a correction (manual Etsy Messages)? Until you do, the copy promises only on request. |
| C-09 | redistribution limits | the pattern file, its charts and its photographs may not be shared... | QUALIFIED | The shop has no photographs (every image is a rendering; store_foundation.readiness LICENCE_MENTIONS_PHOTOGRAPHS). | 'the pattern file, its charts and its images may not be shared, resold, uploaded or included in another publication' | **legal**: Enforceability of the redistribution term (same review as C-07). |
| C-10 | refunds / cancellations | Etsy does not allow a seller to accept a return on a digital listing | QUALIFIED | Etsy help 115013328108: 'digital listings are not able to be returned or canceled. If there's a problem with your digital order, like it's not as described in the listing or the seller never delivers the file, you may be covered under Etsy's Purchase Protection.' A seller can still refund an order. | 'Digital patterns cannot be returned or cancelled: Etsy does not allow returns on digital listings ... A digital item that is not as described, or never arrives, may also be covered by Etsy's Purchase Protection.' No refund is refused in words; 'we will put it right'. | **legal**: Consumer-law rights for digital content (EU withdrawal waiver, Quebec/provincial law) -- does the returns text need a statutory-rights sentence? |
| C-11 | AI imagery / listing images | the pictures are digital renderings of each finished design, not photographs | QUALIFIED | True and disclosed (platform_policy.DISCLOSURES disclosed_render). But Etsy's listing image rule as held: 'Your own photographs or video content--not stock photos, artistic renderings, or photos used by other sellers or sites are required for listings' (policy_knowledge listing_image_rules). | disclosure unchanged; no copy calls a rendering a photo (FORBIDDEN) | **owner**: Policy review: does a rendered finished-object image satisfy Etsy's image rule for a digital pattern listing, or must the first image be the pattern document / chart itself until a real sample is photographed? |
| C-12 | support commitments | questions answered through Etsy Messages against the exact version bought | QUALIFIED | Etsy Messages has no API, so every reply is sent by the human account holder; no response time is promised anywhere (FORBIDDEN refuses 'within N hours'). | unchanged channel; no response-time promise | **owner**: Confirm you will answer Etsy Messages (the only support channel). |
| C-13 | Laura | Laura is Brambleloop's AI founder and the face of the shop | SUPPORTED | D-FB-11..13 (spec/07): AI, never human, never the legal owner or seller; lint TRUTH_LAURA_HUMAN_CLAIM. | 'She is an AI, not a person, and we will always say so.' |  |
| C-14 | seller identity | sold on Etsy by the human holder of this shop account | SUPPORTED | Etsy's account holder is the legal seller (etsy_constraints, Owner role). | unchanged |  |
| C-15 | machinery talk | 'automated pattern compiler', 'the way software gets made', 'machine-readable' | REMOVED | Owner rejected v1 store copy 2026-10-06; owner directive 2026-10-11 'no unnecessary AI-infrastructure talk'. brand.storefront.ABOUT still held the v1 text and the Info & appearance owner action pointed at it. | plain checks language; brand.storefront.ABOUT now is store copy v3 |  |
| C-16 | legal clearance | (none claimed) | SUPPORTED | No trademark, licence or safety clearance exists (owner decision brand_clearance open); FORBIDDEN refuses 'trademark registered', 'legally reviewed', 'certified'. | the terms say 'have not yet been through legal review' |  |

## The fence (`store_foundation.claims.FORBIDDEN`)

`claims.audit()` scans 96 customer surfaces:
- every copy string, the FAQ and the policies;
- `brand.storefront.ABOUT`;
- the terms in their pdf, listing and FAQ renderings;
- every platform disclosure;
- the PDF AI disclosure;
- a listing description from the real template.

`tests/test_w4_copy.py` checks that the audit is clean and that each pattern catches the old
wording it replaced.

| Forbidden wording (regex) | Why |
|---|---|
| `\b(edited/directed/designed/created/written) by (the/our/a/my) designer\b` | invents a human designer (C-01) |
| `\bour designer\b/\bthe designer'?s\b` | invents a human designer (C-01) |
| `\b(i/we) (designed/crocheted/made/tested) (this/these/it/each/every)\b` | first-person making or testing that did not happen (C-03) |
| `\btest(ed)?[- ](made/crocheted/knit/worked)\b/\bpattern testers?\b/\btested by\b/\btester[- ]approved\b/\btested and (proven/approved)\b` | physical testing that has not happened (C-03) |
| `\bsample (was/has been) (made/worked/crocheted)\b/\bphotographed sample\b/\bour (finished )?samples?\b` | a physical sample that does not exist (C-03) |
| `\bphoto(graph)?s? of (the/our/my) (finished/actual/real)\b/\breal photos?\b` | calls a rendering a photograph (C-11) |
| `\bto everyone who bought\b/\bevery(one/ buyer) who (has )?bought\b.{0,40}\b(send/sent/email/message/notif)` | a proactive notice no channel can deliver (C-08) |
| `\bfree forever\b/\bforever free\b` | an unreviewed perpetual promise (C-08) |
| `\bbuyers are told when\b` | a proactive notice no channel can deliver (C-08) |
| `\bwithin \d+ (minutes?/hours?/days?)\b/\b24/7\b/\bsame[- ]day (reply/response)\b` | a response-time promise nobody committed to (C-12) |
| `\b(legally (reviewed/cleared/approved)/trademark(ed)? registered/registered trademark/lawyer[- ]approved)\b` | legal clearance nobody gave (C-16) |
| `\blaura (is/was) (a )?(real/human/person/woman)\b/\blaura (crochet/knit/made/tested)` | presents Laura as human or as a maker (C-13) |
| `\bcompiler\b/\bthe way software gets made\b/\bmachine[- ]readable\b` | rejected machinery talk (C-15) |
| `\bits photographs\b` | the shop has no photographs (C-09) |

## Owner / legal review items (not resolved here)

- **C-02 (legal)** Is an originality/non-infringement statement wanted, and on what clearance?
- **C-07 (legal)** Are these licence terms enforceable as written (Canada, US, EU buyers)?
- **C-08 (owner)** Do you want to commit to proactively messaging past buyers on a correction (manual Etsy Messages)? Until you do, the copy promises only on request.
- **C-09 (legal)** Enforceability of the redistribution term (same review as C-07).
- **C-10 (legal)** Consumer-law rights for digital content (EU withdrawal waiver, Quebec/provincial law) -- does the returns text need a statutory-rights sentence?
- **C-11 (owner)** Policy review: does a rendered finished-object image satisfy Etsy's image rule for a digital pattern listing, or must the first image be the pattern document / chart itself until a real sample is photographed?
- **C-12 (owner)** Confirm you will answer Etsy Messages (the only support channel).

CASL: the privacy addendum's email sentence is unchanged ("only to people who have expressly
agreed … unsubscribe that works"). No email list exists, so nothing is sent. Whether that
sentence is complete under CASL is an open **legal** item, alongside C-07 and C-10.
