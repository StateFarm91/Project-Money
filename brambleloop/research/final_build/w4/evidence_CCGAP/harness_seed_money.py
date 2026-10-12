"""Seed realistic recorded model spend (TEST data, CCVERIFY): 22 token-priced calls this month,
under-estimated by ~60% (expect estimate drift DEGRADED), plus 3 calls last month."""
import env  # noqa
from datetime import datetime, timezone, timedelta
from brambleloop.core.db import Database
from brambleloop.core.models import CostEntry
from brambleloop.gateway import routing
db = Database()
now = datetime.now(timezone.utc)
with db.session() as s:
    for i in range(22):
        s.add(CostEntry(at=now - timedelta(hours=1 + i), agent="seo_strategist", kind=routing.COST_KIND,
                        amount_cad=0.016, tokens_in=1200, tokens_out=400, provider="anthropic",
                        model="claude-test", purpose="ccverify.listing_seo", estimated_cad=0.010,
                        product_slug="hexagon-coaster-set", department="growth",
                        detail={"ok": True, "billing": "billed", "price_basis": "assumed", "ccverify_seed": True}))
    for i in range(3):
        s.add(CostEntry(at=datetime(2026, 9, 15, 12, i, tzinfo=timezone.utc), agent="crochet_engineer",
                        kind=routing.COST_KIND, amount_cad=0.25, tokens_in=8000, tokens_out=2000,
                        provider="anthropic", model="claude-test", purpose="ccverify.cir_review",
                        estimated_cad=0.24, product_slug="nordic-star-ornaments", department="product_design",
                        detail={"ok": True, "billing": "billed", "price_basis": "assumed", "ccverify_seed": True}))
print("COST_KIND", routing.COST_KIND, "month total", round(22*0.016, 3), "last month", 0.75)
