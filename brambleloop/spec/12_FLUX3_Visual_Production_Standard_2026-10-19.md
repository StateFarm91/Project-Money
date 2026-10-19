# Owner ruling 2026-10-19: Permanent FLUX 3 visual production standard (D-W4-LAURA-FLUX3)

Permanent and mandatory for every existing and future listing that features Laura (`laura-r2-a42aeac7`).
It supersedes weaker or conflicting visual-production instructions. Every Product Truth, identity,
security, disclosure and publication safeguard is preserved. The rules below are enforced in code by
tests, not by documentation alone.

1. **Three canonical Laura references are always mandatory.**
   - Every generation featuring Laura transmits all three originals as actual image inputs:
     - `neutral_portrait.jpg` (a42aeac7…): facial identity. Face, eyes, eyebrows, nose, lips,
       cheekbones, jawline, freckles, apparent age, hairline, and highlighted wavy hair.
     - `torso_fit_reference.png` (afe6191f…): torso and bust proportions. Bust fullness, chest
       projection, shoulders and waist. The bust is never flattened, reduced, exaggerated or
       redesigned, and clothing fits and drapes over the approved proportions.
     - `full_length_standing.png` (f32bac68…): full-body silhouette, waist-to-hip, legs.
   - The fingerprints are validated before use.
   - A reference that is missing, invalid or not transmitted causes a refusal. Generation never
     continues with reduced identity conditioning.
   - Generated lifestyle images may be added as supplementary references. They never replace the
     originals.
2. **The certified pattern becomes image references.** FLUX accepts images, not PDFs, so each product
   gets deterministic PNG references rendered from its exact certified version:
   - (4) complete product layout: shape, colour placement, proportions, component count, construction;
   - (5) stitch and construction detail;
   - (6) technical rules: dimensions, yarn, colours, row and stitch counts, restrictions, prohibited
     additions.
   - The references adapt to the category: multi-piece products show every component, and garments
     show fit, front and back, and sizing where the data supports it.
   - The written construction requirements also go in the prompt.
   - Only real provider image-input fields are used. Provider support is confirmed, never assumed from
     the dashboard.
3. **Six-reference minimum for a Laura product campaign:** face, torso, full body, layout, detail,
   rules.
   - All six are sent as provider image inputs where supported.
   - If the provider limit is lower, nothing is silently omitted. The limitation is reported and a
     tested alternative is used, for example a reference sheet that keeps the information legible.
   - Every transmitted image's fingerprint, the provider request metadata and the output are
     recorded.
   - Product-only images need no Laura references.
4. **One listing, one outfit (extends D-W4-LAURA-OUTFIT).**
   - A complete outfit is: top or dress; lower garment; shoes where visible; outerwear and accessories
     or jewellery where appropriate.
   - Every Laura image in a listing uses the same approved outfit.
   - Each new listing gets an entirely different complete outfit.
   - A persistent wardrobe registry keyed by listing records clothing, colours, accessories, approved
     reference, reservation status and usage history. It survives restarts, redeploys and model
     changes, and it is enforced before image approval.
   - A generated image that changes the outfit is flagged and repaired or regenerated within approved
     limits.
   - Product-only images need no outfit.
5. **Automatic fashion and scene direction.** Creative selects the outfit and photoshoot concept from
   product type, colours, materials, use, season, target customer, brand aesthetic, and the outfits and
   settings already used. The owner does not choose them. The result must be natural and believable,
   avoiding repetitive settings, generic poses, unnatural hands and over-staged composition.
6. **Seven-image campaign standard.**
   - Typical roles: lifestyle hero, product full view, Laura using or wearing it from another angle,
     verified texture or construction close-up, second lifestyle, size/scale/fit, product detail or
     customer information.
   - The roles adapt to the product, and there is no filler.
   - One outfit throughout wherever Laura appears.
   - The product version, colours, component count and construction stay the same across every image.
7. **Full prompt every time.** Each prompt is generated automatically from certified data and brand
   rules, then versioned, with its receipt kept. It covers:
   - identity and reference hierarchy;
   - face and body preservation;
   - product identity and version;
   - construction, colours, stitches and prohibited additions;
   - outfit, environment, pose and framing;
   - realism requirements and image role;
   - AI-disclosure status, publication restrictions and verification requirements.
8. **Autonomous execution:**
   1. certified pattern;
   2. reference PNGs;
   3. validate Laura's references;
   4. reserve the outfit;
   5. environment and shot plan;
   6. product-only image;
   7. fidelity check;
   8. seven-image gallery;
   9. identity and outfit check;
   10. product, anatomy, realism and disclosure checks;
   11. bounded repair;
   12. assembly;
   13. owner approval.

   It reuses the existing agents, queues, spend controls, Product Truth, conditioning and gallery
   certification, and stays bounded, resumable and auditable.
9. **Learning.**
   - Tracked: identity consistency, bust and body-proportion drift, outfit consistency, product
     fidelity, invented stitches or motifs, dimension or piece-count errors, realism, gallery
     completeness, cost per accepted image, latency.
   - Improvement goes through the existing controlled Learn process. Criteria are never weakened.
10. **Publication.**
    - Good-looking FLUX images do not prove construction, physical testing or Etsy compliance. All
      gates still apply.
    - Manual FLUX images are a temporary launch fallback.
    - Autonomy is not complete until a real unattended end-to-end production test passes.
11. **Required tests:**
    - the three canonical references are always supplied;
    - an invalid or missing reference is refused;
    - product references come from the correct pattern version;
    - every required reference reaches the provider;
    - bust and body proportions are checked against the canonical references;
    - one listing keeps one outfit across its Laura images;
    - different listings cannot reuse a complete outfit;
    - styling is selected automatically;
    - product-only images need no Laura references;
    - a failed Product Truth check cannot be bypassed;
    - nothing is published without the required approvals.

**Integrator note (not an owner ruling).**
- The owner supplied the three canonical files with this ruling. They are byte-identical to the
  committed originals (sha256 a42aeac7…, afe6191f…, f32bac68…).
- A "bust and body proportions checked" result needs an independent vision judgement. Until one is
  funded and run, that check reads UNKNOWN and blocks publication. It never reads PASS.
