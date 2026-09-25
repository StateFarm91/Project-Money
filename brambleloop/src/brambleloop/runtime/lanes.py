"""Disjoint execution lanes over the existing durable queue, not another scheduler.

Only deterministic, no-model maintenance is separated initially. Paid/model work stays
serialized until reservation-to-ledger reconciliation and external-effect recovery have
been proven under parallel workers. Logical department count is not a worker count.
"""

OPERATIONS = frozenset({"ops.heartbeat", "ops.queue_check", "ops.health"})
MARKETING = frozenset({"marketing.ads_readiness"})
FINANCE = frozenset({"finance.reconcile"})


def partitions(known, mode="serial"):
    known = set(known)
    if mode == "serial":
        return {"company": None}
    if mode != "departments":
        raise ValueError("BRAMBLELOOP_WORKER_LANES must be serial or departments")
    dedicated = {"operations": OPERATIONS, "marketing": MARKETING, "finance": FINANCE}
    assigned = set().union(*dedicated.values())
    return {**{name: sorted(types & known) for name, types in dedicated.items()},
            "production": sorted(known - assigned)}
