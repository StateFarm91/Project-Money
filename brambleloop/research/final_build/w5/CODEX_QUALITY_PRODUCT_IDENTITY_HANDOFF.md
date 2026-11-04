# Product identity in quality re-verification

Stacked on PR #91 (`codex/quality-asset-truth-tags`, `d272e8f`). Existing listing production and first-customer gates use `product_type_findings` and `colourwork_findings` to compare title and tags with the CIR and twin. The real `gate.asset_truth` re-verification worker omitted both, so synthetic wrong-product title, wrong-product tag and unsupported tapestry tag each passed and did not create a quality hold.

The worker now reuses those checks on stored title and tags, alongside the existing shape/technique checks. The existing durable quality hold blocks publication on a finding and the same check clears its own hold after corrected copy passes. These are finite heuristics; they can conservatively hold contextual mentions, and they do not authenticate evidence, cover all descriptions or fence concurrent listing mutations. Product Truth, A6/A9 authority, PostgreSQL and integration review remain open.

Synthetic real Worker tests exercise all three cases and corrected-copy recovery. No physical evidence, owner approval, purchase, publication or deployment was created.

Python 3.11 tmpfs SQLite quality, withholding and real Worker regression passed 30/30; independent reviewer reran the final three Worker cases 3/3.
