"""F-581 (third-party app evaluation) and F-582 (no redundant tool spend).

A software subscription is the one recurring spend that can duplicate what the company
already does. Before any `software:` spend scope may get a limit, a vendor evaluation must be
recorded naming:

* `capability_gap` -- what the company cannot do today without it;
* `overlap` -- the existing modules or tools checked for the same capability, each with why it
  does not cover the gap (an empty list is refused: nobody looked);
* `expected_roi` -- the monthly value expected against `monthly_cost_cad`, with its basis;
* `data_quality`, `permissions` (OAuth scopes / data it would see), `vendor_risk`, and
  `build_vs_buy` (why buying beats building here).

`SpendGuard.set_limit` refuses a `software:` scope without the id of a recorded evaluation for
that tool whose expected value exceeds its cost. The evaluation is an audit row
(`finance.tool_evaluation`), so it is evidence, not prose. Recording one spends nothing and
grants nothing: the owner still approves the spend itself.
"""
from __future__ import annotations

ACTION = "finance.tool_evaluation"
SOFTWARE_PREFIX = "software:"
FIELDS = ("capability_gap", "overlap", "expected_roi", "data_quality", "permissions",
          "vendor_risk", "build_vs_buy")


class ToolSpendRefused(ValueError):
    pass


def record_evaluation(db, *, tool: str, monthly_cost_cad: float, evaluation: dict,
                      evaluated_by: str) -> int:
    from ..core.models import AuditLog

    tool = (tool or "").strip().lower()
    if not tool:
        raise ToolSpendRefused("an evaluation names the tool")
    missing = [f for f in FIELDS if not evaluation.get(f)]
    if missing:
        raise ToolSpendRefused(f"a tool evaluation states {missing} (F-581)")
    overlap = evaluation["overlap"]
    if not isinstance(overlap, list) or not all(
            isinstance(o, dict) and o.get("existing") and o.get("why_not_enough")
            for o in overlap):
        raise ToolSpendRefused("overlap lists each existing capability checked and why it "
                               "does not cover the gap (F-582)")
    roi = evaluation["expected_roi"]
    if not isinstance(roi, dict) or not isinstance(roi.get("value_cad_month"), (int, float)) \
            or not str(roi.get("basis") or "").strip():
        raise ToolSpendRefused("expected_roi is {value_cad_month, basis} (F-582)")
    with db.session() as s:
        row = AuditLog(actor=evaluated_by or "unknown", action=ACTION, artifact=tool,
                       detail={"tool": tool, "monthly_cost_cad": float(monthly_cost_cad),
                               **{f: evaluation[f] for f in FIELDS}})
        s.add(row)
        s.flush()
        return int(row.id)


def check_scope(db, scope: str, decision_ref: int | None) -> dict | None:
    """None for a non-software scope; the evaluation for a software scope; raises otherwise."""
    from ..core.models import AuditLog

    if not scope.startswith(SOFTWARE_PREFIX):
        return None
    tool = scope[len(SOFTWARE_PREFIX):].strip().lower()
    # F-579: an accounting integration is connected only if the recorded evaluation of
    # QuickBooks Online / Xero against our own books recommends it.
    from .accounting.integration_decision import connection_allowed

    allowed, why = connection_allowed(tool)
    if not allowed:
        raise ToolSpendRefused(f"{scope}: {why}")
    if decision_ref is None:
        raise ToolSpendRefused(f"{scope}: a software spend limit needs a recorded tool "
                               f"evaluation (decision_ref) naming the capability gap and ROI")
    with db.session() as s:
        row = s.get(AuditLog, int(decision_ref))
        d = dict(row.detail or {}) if row is not None and row.action == ACTION else None
        artifact = row.artifact if row is not None else None
    if d is None or artifact != tool:
        raise ToolSpendRefused(f"{scope}: decision_ref {decision_ref} is not an evaluation of "
                               f"{tool!r}")
    if float(d["expected_roi"]["value_cad_month"]) <= float(d["monthly_cost_cad"]):
        raise ToolSpendRefused(f"{scope}: expected value does not exceed the cost (F-582)")
    return d
