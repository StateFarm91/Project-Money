# W4-L0PACKET: Launch-0 product readiness packet (8 products, CAP-1)

Branch `claude/w4-L0PACKET` from `origin/claude/w4-INTEG2` (85ec5d0). It generates the packet
from code and writes nothing to the database. No Etsy write, publication or spend.

## What it is

`brambleloop/src/brambleloop/launch/product_readiness.py` builds the packet as `build(db)` and
renders it with `render_markdown`. It covers every Launch-0 product (8 under CAP-1) and every
release of each (10 releases, because the baskets come in S/M/L).

For each release it records a state for seven gates. Each state is read from the code that
enforces that gate:

| gate | read from |
|---|---|
| certification | `publication_authority` certification section |
| product_truth | `launch0.product_truth`, computed when the packet is built |
| image_truth | `publication_authority` listing set, plus presentation parity as a separate owner note |
| listing_readiness | a draft listing bound to the release, plus `dashboard_truth` launch clearance |
| price_plan | `release_gates.launch_price_check` |
| seo | `publication_authority` search certificate |
| disclosure | `publication_authority` disclosure section |

Every gate that is not PASS records what remains to be done and who owns it: **company**,
**owner** or **external**. A gate that could not be read is UNKNOWN, and UNKNOWN never counts as
PASS. The four CAP-1 additions are labelled "catalogue configuration approved, the product
itself not approved". The packet grants nothing. Publication still needs policy, rollback,
parity and a sealed owner grant for each release.

The runner is `research/final_build/w4/l0_readiness_run.py <sqlite> <out-dir>`. It writes JSON
and Markdown, with the network closed.

## Evidence

**Tests.** `tests/test_w4_l0_product_readiness.py`: 8 of 8 pass, run through `testslot`.

- The packet covers all 8 products and 10 releases, with all 7 gates for each release.
- On an empty database, nothing is ready, and every gap names an owner.
- Product Truth passes for all 8 products, and the twin is never reported as calibrated.
- CAP-1 additions are labelled as not-approved products.
- An off-plan placemat listing (CA$9.50) fails `price_plan`, owned by the company; a listing at
  the CA$5.00 plan passes.
- Listing readiness needs a listing bound to the release **and** launch clearance.
- A missing taxonomy produces an owner item (the Etsy app keystring).
- UNKNOWN never counts as PASS: an unrecognised state reads as UNKNOWN, and the worst state
  across releases wins.

`test_vacuity` also passes.

**Generated packet.** `evidence_L0PACKET/empty_db/` is the packet run on an **empty** scratch
database. It is the baseline before any release chain has run:

- Product Truth: PASS for all 8.
- Certification and listing readiness: FAIL, owned by the company.
- Every other gate: UNKNOWN.

**Pending run on a populated database.** The packet still has to be generated on a populated
release-chain database (`pipe_chain_run.py` on the 10 releases, then
`l0_readiness_run.py`). That chain renders images, which the rationed test slots forbid until
`slots/N` ≥ 3, so it is deferred. The expected result follows from the scratch chains of
2026-10-11 (`evidence_PRODUCT`, `evidence_CAP1`):

- certification, Product Truth, image truth and disclosure: PASS
- seo: FAIL, owned by the owner (Etsy taxonomy credential)
- price_plan: PASS
- listing readiness: PASS once the release is launch-cleared

**Board rows.** This deliverable serves the owner's queue item (1). No final-master row is
closed by it. It supports F-878 (Launch Packet; the integrator owns that row) by giving that
packet a per-product, per-gate source.
