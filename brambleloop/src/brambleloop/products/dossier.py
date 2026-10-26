"""F-671: the product digital dossier -- one record spanning every table that knows the product.

Instead of a hand-kept list that drifts as tables are added, the dossier walks the schema:
every table with a `product_slug` column contributes its rows for this product, and the
tables keyed on the product id (pattern versions, and anything else with `product_id`) are
joined through the `products` row. Each section carries its table name, count and the newest
rows (columns that are ids, states, versions, timestamps and short fields), so opportunity,
research, CIR, materials, imagery, PDFs, QA, safety, Etsy, marketing, customers, finance,
experiments and history are all read from where they actually live. A table that does not
mention the product is listed as absent rather than left out silently. Read-only.
"""
from __future__ import annotations

SHOW_ROWS = 5
_SHORT = (int, float, bool, str, type(None))


def _brief(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif hasattr(v, "value") and isinstance(getattr(v, "value"), str):
            out[k] = v.value
        elif isinstance(v, _SHORT) and not (isinstance(v, str) and len(v) > 160):
            out[k] = v
    return out


def dossier(db, slug: str) -> dict:
    from sqlalchemy import select

    from ..core.db import Base
    from ..core.models import Product

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pid = product.id if product is not None else None
        sections, absent = {}, []
        for name, table in sorted(Base.metadata.tables.items()):
            cols = table.c
            if "product_slug" in cols:
                cond = cols.product_slug == slug
            elif "product_id" in cols and pid is not None:
                cond = cols.product_id == pid
            else:
                continue
            order = next((cols[c] for c in ("at", "created_at", "id") if c in cols), None)
            q = select(table).where(cond)
            if order is not None:
                q = q.order_by(order.desc())
            rows = [dict(r._mapping) for r in s.execute(q).all()]
            if rows:
                sections[name] = {"count": len(rows),
                                  "newest": [_brief(r) for r in rows[:SHOW_ROWS]]}
            else:
                absent.append(name)
    return {"slug": slug, "known_product": product is not None,
            "product": _brief({c.name: getattr(product, c.name)
                               for c in product.__table__.columns}) if product else None,
            "sections": sections, "tables_without_this_product": absent,
            "covered_tables": len(sections)}
