"""Store Foundation: the Etsy shop treated as a product (directive v1.1 section 10, F-926).

Every store-level surface -- identity, icon, banner, title, announcement, About, policies,
FAQ, support, sections, disclosures, trust signals, settings, search and support readiness --
held as one content model with a deterministic readiness check per surface, and an Owner
Store Preview that shows the whole shop the way a buyer would meet it, at phone and desktop
widths, before anything is live.

The content itself is mostly not written here. `brand.storefront`, `commerce.shop_package`,
`commerce.terms` and `gates.platform_policy` already own the shop's words, and a second copy
would be the drift requirement 40 forbids. This package *assembles* them, adds only what no
module owned (the PIPEDA-aware privacy addendum, the support/contact surface, the questions
the FAQ was missing, the trust-signal register, the settings checklist), and judges the lot.

Nothing here publishes, writes to Etsy, or contacts any network. The preview says
"Preview -- not live" on every render.

Modules:
    limits   -- per-field Etsy length limits, each with how well it is known
    lint     -- truthfulness and voice lint over every customer-facing string
    assets   -- deterministic SVG shop icon and banner in the brand palette
    content  -- the content model: every surface, plus the Launch-0 opening grid
    readiness-- per-surface checks and the roll-up
    preview  -- `summary(db)` for the Command Center and `render_preview(db, viewport)`
"""
