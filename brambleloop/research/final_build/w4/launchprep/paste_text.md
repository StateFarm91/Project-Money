# Prepared text to paste (only for the items still outstanding)

Generated 2026-10-21 from the repository's own copy: `store_foundation/copy_v2.py`
(VERSION `copy_v3`, written 2026-10-11), which `commerce.shop_package.policies()` also reads.
Nothing here was written fresh; every sentence is the copy that the claim register
(`store_foundation.claims`) and the FORBIDDEN fence already test. Do not edit while pasting:
the same words appear in listings and in the PDFs.

Do not paste anything over a field you already set on 2026-10-11 (banner, logo, About, Laura's
bio, cancellation policy, privacy policy). The live shop is authoritative for those.

---

## 1. FAQ (only if Shop Manager > Settings > Policy settings > FAQs is empty)

Paste the questions in this order. One question and one answer per FAQ entry.

**Can I sell what I make from this pattern?**
Yes: finished items may be sold by individual makers and small businesses, not manufactured at scale. You do not owe us a percentage and you do not need to ask. What you may not do is pass on the pattern itself: the pattern file, its charts and its images may not be shared, resold, uploaded or included in another publication.

**Am I buying a finished piece or a pattern?**
A pattern. You receive the instructions and chart as PDFs and make the piece yourself, in your own yarn. Nothing is shipped.

**Where is my file?**
In your Etsy account under Purchases and downloads, as soon as your payment clears. Etsy also emails you a link. If neither works, message us and we will get it to you.

**Can I print it?**
Yes, as often as you like. The pattern is for the buyer's own use, and to teach from in a class where each participant has their own copy.

**Can I teach a class from it?**
Yes, on one condition from our terms: the pattern is for the buyer's own use, and to teach from in a class where each participant has their own copy. Each participant needs their own copy.

**US or UK crochet terms?**
Both. Every pattern comes as two complete PDFs, one written throughout in US terms and one in UK terms, each with its own stitch key, so you never have to translate in your head.

**What if I find a mistake?**
Tell us the pattern and the row. Questions are answered through the shop the pattern was bought from, against the exact version that was bought. If the pattern is wrong we fix the pattern itself. Corrections are free: a corrected pattern replaces the old file, and anyone who bought an earlier version can ask for the corrected one at any time.

**Can I get a refund?**
Digital patterns cannot be returned, and Etsy does not allow a seller to accept a return on a digital listing. If something is wrong (a file that will not open, an error in the pattern, a listing that misled you), message us and we will put it right.

**Was this designed with AI?**
This is a digital pattern. No physical item is shipped.
This design was created with AI assistance, and every row's stitch count is checked before release.
Charts and previews are rendered directly from the pattern file, so they show exactly what is in the document.

**Do you ship internationally?**
There is nothing to ship. A digital pattern is the same file everywhere, and any tax due is handled by Etsy at checkout.

**What skill level do I need?**
Each listing states a difficulty and names every stitch the pattern uses, with the hook size and gauge, so you can judge before you buy. If you are unsure, message us and we will tell you honestly.

**Are the pictures photographs?**
About the images: each listing image is a digital rendering of the pattern's finished design, not a photograph. Every stitch in it is drawn from the pattern itself at the stated gauge, with a centimetre scale; no sample has been photographed, and your finished piece will vary with yarn and tension.

**Has this pattern been made up in yarn?**
Not yet by us. Every row's stitch count is checked and the finished sizes are calculated from the stated gauge, but we have not yet worked a physical sample of these designs. Your finished size will vary with yarn, hook and tension, so make a gauge swatch first.

**Who is Laura?**
Laura is Brambleloop's AI founder and the face of the studio. She is an AI, not a human: she has not crocheted these pieces, and her portrait is a generated image, not a photograph. The shop is sold on Etsy by its human account holder, who is responsible for every order and every promise made here.

**How do I reach you?**
Questions go through Etsy Messages: use the message button on this shop page or on your order. Tell us the pattern name, which file you are using (US or UK terms) and the row or round number, and we will answer against the exact version you bought. If the problem is in the pattern, we correct the pattern itself and send you the corrected file.

> When a tester's sample of a product is recorded and binds (Task A), the "Has this pattern
> been made up in yarn?" answer becomes untrue for that product only. The company updates
> `copy_v2.faq_extra()` first; then the owner re-pastes that one answer. Until then it stays
> exactly as above.

---

## 2. Delivery text (only if Policy settings shows an editable delivery/shipping text box for digital items)

The 2026-10-06 checklist (Etsy Help 115014372467) found only a fixed, non-editable "Instant
downloads" policy for digital items. If that is still what you see, paste nothing and report it
(it is the reading that fixes our check, E2). If a free-text box exists, paste:

Every pattern here is a digital file, so there is no processing time and nothing is posted. As soon as your payment clears, your PDFs are waiting in your Etsy account under Purchases and downloads, and Etsy emails you a link as well. They read comfortably on a phone or tablet and print cleanly on paper. If a download will not start or a file will not open, message us and we will get it to you.

---

## 3. Not to paste

- **Additional policies (`policy_additional`).** Etsy already holds a non-blank value for this
  shop (getShop, 2026-10-20). Leave it as it is. Our check that demanded it blank is wrong (E3).
- **Announcement.** Already set (getShop `announcement` non-blank, 2026-10-20).
- **Message to buyers for digital items.** Already set (getShop `digital_sale_message`
  non-blank, 2026-10-20).
- **Returns/cancellation and privacy.** Already set by you on 2026-10-11 (getShop non-blank).
  The wording differs from the repository draft; the live wording is authoritative and the
  company's consistency check found no contradiction with our terms.
