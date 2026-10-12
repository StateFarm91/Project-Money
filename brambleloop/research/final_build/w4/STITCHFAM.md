# STITCHFAM: F-759 distinctive-stitch benchmark registry

Status: **PARTIAL**. Branch `claude/w4-STITCHFAM`, based on INTEG2 083c9fc.

## Done

`visual/stitch_families.py` is written but **not wired and not tested**. It contains:
- a family registry: star, cluster, cable, post_relief;
- the star benchmark set: 2 positive fixtures and 5 negative fixtures, run through the
  existing `stitch_identity.diagnose` with its BARS unchanged;
- `support(family)`: supported only when every fixture behaves;
- `families_in(cir)`;
- `refusal(cir)`.

I checked the catalogue's compiled stitches: sc, inc, dc and slst only, so no Launch-0 product
uses a distinctive family.

## Open: next executable steps

1. Call `stitch_families.refusal(cir)` in `disclosed_render.render`, and raise `RenderRefused`
   when it returns a reason.
2. Add `tests/test_w4_stitchfam.py`, covering:
   - star is supported;
   - cluster, cable and post_relief are unsupported;
   - a CIR using a cable stitch is refused;
   - a Launch-0 render is unaffected.
3. Run test_disclosed_render and the required set.
