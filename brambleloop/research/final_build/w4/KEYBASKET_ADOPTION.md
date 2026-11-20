# Housewarming Key Basket: adoption packet for the owner's decision (W4-KEYBASKET)

Branch `claude/w4-KEYBASKET`, from `origin/claude/w4-INTEG2` (85ec5d0).

**The decision is yours and has not been made.** In code, `moment_candidates.ADOPTED_RELEASE`
is empty.

Under CAP-1 the Key Basket is inside the Launch-0 scope. That approval covered the catalogue
configuration only: it did not adopt the Key Basket as a product.

## What "adopting 0.1.0 → 1.0.0" means

The Key Basket comes from `products.moment_candidates`. That module's rule is that every
version stays `0.x` until the candidate clears three things:

| condition | status |
|---|---|
| Product Truth | **cleared** |
| taste gate | **not cleared.** It survives only as `needs_taste`: structurally clean, not judged by eyes. This is true of every Launch-0 product. |
| owner-governed adoption | **this decision** |

If you adopt it:

1. One entry is set: `ADOPTED_RELEASE["housewarming-key-basket"] = "1.0.0"`. It is already
   prepared as `PROPOSED_ADOPTION`. The builder's default version then becomes 1.0.0.
2. **The pattern does not change.** The tests show the CIR is identical to 0.1.0 except for its
   version.
3. **The release identity does change:**
   - fingerprint `c63743691cf8` (0.1.0) becomes `d028fc06d787` (1.0.0);
   - certification grants a **new release hash** (tested).
4. The release chain then re-certifies it through the normal path. `chain.rebuild` redrafts a
   stored design the code no longer produces, and that is followed by the PDFs, disclosed
   frames, listing set, price and listing draft.
5. The 0.1.0 scratch release is superseded. It was never stored in production.

Adoption does **not**:

- change any gate;
- create an Etsy draft;
- publish anything;
- spend anything.

Each of those remains its own decision. The sealed publication grant (D-FB-10) is still
required for each release.

## Evidence

All of the following comes from a scratch shadow chain run on 2026-10-11 (W4-CAP1,
`evidence_CAP1/key_basket_chain.json`):

| check | result |
|---|---|
| release | `housewarming-key-basket@0.1.0`, release hash `142b52f0f9c6…` (reproduced) |
| compile | 0 errors, 0 warnings |
| certification | granted |
| Product Truth | 5 of 5 gates pass |
| final PDF (US and UK) | PASS |
| terminology, counts, listing claims, imagery, licence and safety | PASS |
| listing set, disclosure | PASS |
| listing draft | 13 tags, CA$5.50. This is the SOURCED CA$4–12 cluster plan, and the price is inside its band. |
| creative jury | `needs_taste`; the brief is validated (moment-first housewarming brief) |

**Still blocked.** It shares these blockers with the other seven products, and each is an owner
or external item:

- search taxonomy
- gauge and size claims (UNRESOLVED; this is a class-B basket, so wall stiffness is unclaimed
  until a sample exists)
- Etsy remote state
- non-durable fulfilment storage
- parity and policy

**Demand: UNKNOWN.** The Key Basket has no radar opportunity. It is a moment-first creative
candidate (W4-PIPE2), and `launch0.NO_RADAR_CONCEPT` records that origin.

What *is* observed is demand for the basket category, which is what put the nesting baskets
into Launch-0. That is not demand for this specific product, and it is not presented as such.

## The decision

| option | effect |
|---|---|
| **Adopt as 1.0.0** | It becomes a catalogue product. It is re-certified as 1.0.0 and goes through every gate like the other seven. It opens labelled "demand UNKNOWN". |
| **Keep at 0.1.0** | It stays a pre-release candidate inside the Launch-0 scope. It is not offered as a catalogue product, and the 8-product floor would then rest on a candidate. |
| **Replace** | A different evergreen product with radar demand fills the eighth slot. Candidates that were tried and dropped are listed in `products.launch0` (most failed a gate). |

**Recommendation:** adopt, with "demand UNKNOWN" stated. Its engineering and certification
evidence matches the other seven. Its price is at the low end of a sourced band. It completes
the housewarming set alongside the coaster set and the placemat pair.

**Cost and time of adopting:** CA$0 and about 2 minutes to decide. The re-certification is
company work.

**Cost of waiting:** the eighth Launch-0 product stays a pre-release candidate.

## Tests

`tests/test_w4_keybasket_adoption.py` covers:

- no adoption has been made, and 1.0.0 is proposed;
- adoption changes the release identity and nothing in the pattern;
- the adopted release certifies under a new release hash;
- the product's own demand is UNKNOWN, with its origin recorded.

Board rows: none closed by this deliverable. It is queue item (3), an owner decision packet.
