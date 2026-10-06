"""Continuous SEO / keywords / taxonomy / search intelligence (directive v1.1 section 11).

The listing chain (`runtime.release` `listing.seo`, built on `commerce.seo`, `commerce.search`,
`commerce.category`, `commerce.intent`) drafts one listing per release and certifies it. That
is a one-shot decision taken at release time. This package is the loop around it:

    observe evidence -> keyword/taxonomy decisions -> title/tag/attribute proposals
                     -> measure -> learn (re-evaluate when evidence changes)

Modules:

- `models`    durable tables (keyword evidence, proposals, cycles) and `ensure_tables`.
- `evidence`  the keyword evidence store: every row carries provenance (`source`,
              `source_ref`) and a basis (`measured` | `observed` | `modelled` | `unknown`).
              The company has no live Etsy search analytics, so most rows are `modelled`.
- `facts`     verified product facts for Launch-0 variants, from the CIR, its twin and the
              product's own listing identity -- the vocabulary a truthful tag may use.
- `truth`     the truthful-tag validator (F-918 anti-gaming, F-008, F-021, PT-01): every term
              traceable to a fact; no stuffing, competitor names, protected IP or misleading claims.
- `proposals` title / tag / attribute proposals for Launch-0 drafts. Proposals only: nothing in
              this package can write to Etsy (it imports no Etsy client).
- `taxonomy`  which Launch-0 products have a confirmed vs an assumed Etsy category.
- `measure`   per-keyword outcome attribution when listing stats exist; UNKNOWN otherwise.
- `jobs`      `run_cycle(db)`, idempotent: re-evaluates proposals only when inputs change.
- `status`    `summary(db)` and `next_work(db)` -- the provider contract for lanes A and C.

`db` everywhere is the repo's `core.db.Database` (the object every provider in this codebase
takes); a raw SQLAlchemy `Session` is also accepted (see `_db`).
"""
