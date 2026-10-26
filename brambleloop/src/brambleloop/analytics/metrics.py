"""F-618: one canonical definition per KPI, shared by every department that reports it.

Each KPI below is a function of named inputs with the rule for UNKNOWN written once: any
missing input, or a zero denominator, is None (UNMEASURED) -- never 0. Callers may round for
display; the definition itself is unrounded. `REGISTRY` documents each KPI's formula, unit
and the module that supplies its inputs, and `tests/test_w4_fmbatch1_metrics.py` holds the
callers (scale.runrate, growth.loops, finance.books) to these definitions.
"""
from __future__ import annotations


def _ratio(num, den):
    if num is None or den is None or not den:
        return None
    return num / den


def conversion(orders, visits):
    """Orders per visit."""
    return _ratio(orders, visits)


def ctr(visits, impressions):
    """Visits per impression (search click-through)."""
    return _ratio(visits, impressions)


def aov(revenue_cad, orders):
    """Average order value, CAD."""
    return _ratio(revenue_cad, orders)


def revenue_per_visitor(revenue_cad, visits):
    return _ratio(revenue_cad, visits)


def contribution_per_visitor(contribution_cad, visits):
    return _ratio(contribution_cad, visits)


def refund_rate(refunded_orders, orders):
    """Refunded (voided, not countable) orders per order booked in the window."""
    return _ratio(refunded_orders, orders)


def cac(ad_spend_cad, new_customers):
    """Paid customer acquisition cost: ad spend per new customer from ads."""
    return _ratio(ad_spend_cad, new_customers)


def roas(attributed_revenue_cad, ad_spend_cad):
    """Return on ad spend: attributed revenue per ad dollar."""
    return _ratio(attributed_revenue_cad, ad_spend_cad)


def contribution_margin(net_sales_cad, platform_fees_cad, ads_cad):
    """P&L contribution margin: net sales less the costs that vary with selling."""
    if None in (net_sales_cad, platform_fees_cad, ads_cad):
        return None
    return net_sales_cad - platform_fees_cad - ads_cad


REGISTRY: dict[str, dict] = {
    "conversion": {"formula": "orders / visits", "unit": "ratio",
                   "inputs_from": "listing_outcomes (visits), orders (booked, countable)"},
    "ctr": {"formula": "visits / impressions", "unit": "ratio",
            "inputs_from": "listing_outcomes"},
    "aov": {"formula": "revenue_cad / orders", "unit": "CAD", "inputs_from": "orders"},
    "revenue_per_visitor": {"formula": "revenue_cad / visits", "unit": "CAD",
                            "inputs_from": "orders, listing_outcomes"},
    "contribution_per_visitor": {"formula": "contribution_cad / visits", "unit": "CAD",
                                 "inputs_from": "orders.contribution_cad, listing_outcomes"},
    "refund_rate": {"formula": "refunded (voided) orders / orders booked", "unit": "ratio",
                    "inputs_from": "commerce.orders_ingest (countable)"},
    "cac": {"formula": "ad spend / new customers from ads", "unit": "CAD",
            "inputs_from": "cost_entries kind=ads, orders acquisition_source"},
    "roas": {"formula": "attributed revenue / ad spend", "unit": "ratio",
             "inputs_from": "orders acquisition_source, cost_entries kind=ads"},
    "contribution_margin": {"formula": "net sales - platform fees - ads", "unit": "CAD",
                            "inputs_from": "finance.books"},
}
UNKNOWN_RULE = "a missing input or a zero denominator is None (UNMEASURED), never 0"
