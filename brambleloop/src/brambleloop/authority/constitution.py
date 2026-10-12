"""The Brambleloop Constitution (F-700) as one check.

The thirteen clauses were enforced piecemeal across the codebase. This module states them in
one place, names the code that enforces each (a test imports every enforcer, so a clause can
never point at nothing), and gives the company one `evaluate(db, action)` that every work item
the coordinator dispatches (`authority.dag`) and every Laura priority/delegation
(`laura.core.constitution.review`) passes through.

`evaluate` judges the clauses that are decidable from one proposed action; the others are
structural (they hold because of how a subsystem is built) and are reported with their
enforcer rather than re-judged. It never raises: anything it cannot read blocks (fail closed).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Clause:
    key: str
    text: str
    enforcers: tuple[str, ...]      # "module:attribute", imported by the test
    per_action: bool                 # judged by evaluate() for each action


CLAUSES: tuple[Clause, ...] = (
    Clause("sell_truthfully", "sell truthfully",
           ("brambleloop.publish.release_gates:for_publish",
            "brambleloop.publish.release_gates:claims_of"), True),
    Clause("product_truth_over_speed", "Product Truth over speed",
           ("brambleloop.gates.certificate", "brambleloop.improve.governance:check"), True),
    Clause("never_manufacture_evidence", "never manufacture evidence",
           ("brambleloop.improve.governance:check",), True),
    Clause("unknown_is_valid", "UNKNOWN is valid",
           ("brambleloop.autonomy.kpis:did_no_work",), True),
    Clause("customer_harm_outranks_revenue", "customer harm outranks revenue",
           ("brambleloop.laura.core.constitution:review",), True),
    Clause("no_silent_authority_expansion", "no silent authority expansion",
           ("brambleloop.authority.policy:check_dispatch",
            "brambleloop.agents.registry:Registry"), True),
    Clause("every_dollar_has_provenance", "every dollar has provenance",
           ("brambleloop.agents.registry:Registry", "brambleloop.finance.spend_report:attribution"),
           True),
    Clause("consequential_decisions_auditable", "consequential decisions are auditable",
           ("brambleloop.agents.registry:Registry",), True),
    Clause("experiments_falsifiable", "experiments are falsifiable",
           ("brambleloop.growth.experiments:register",), True),
    Clause("failures_remain_knowledge", "failures remain knowledge",
           ("brambleloop.improve.mine:mine",), False),
    Clause("never_repeat_known_failures", "never unknowingly repeat known failures",
           ("brambleloop.autonomy.orchestrator:_suppressed",
            "brambleloop.authority.dag:known_failure"), True),
    Clause("improve_without_preventing_shipping",
           "improve continuously without preventing shipping",
           ("brambleloop.improve.tiers:check_promotion",), False),
    Clause("idle_opportunity_not_acceptable",
           "idle compute is acceptable, idle opportunity is not",
           ("brambleloop.autonomy.orchestrator:idle_wake",
            "brambleloop.autonomy.orchestrator:tick"), False),
)
BY_KEY = {c.key: c for c in CLAUSES}

_PRODUCT_TRUTH_TYPES = frozenset({"cir.draft", "cir.revise", "gate.certify", "store.publish",
                                  "store.activate", "store.update"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def evaluate(db, action: dict, *, now: datetime | None = None,
             record_audit: bool = True) -> dict:
    """Judge one proposed action against the per-action clauses.

    action keys (all optional): actor, agent, job_type, department, kind, description,
    cost_cad, provenance, claims [{text, evidence}], metrics {name: {value, basis}},
    customer_harm, expected_revenue_cad, hypothesis, success_metric, falsified_if,
    fingerprint, addresses_failure, skip_validation, audit_ref.
    """
    now = now or _now()
    violations: list[dict] = []

    def v(key: str, why: str) -> None:
        violations.append({"clause": key, "text": BY_KEY[key].text, "why": why[:400]})

    try:
        a = dict(action or {})
        jt = str(a.get("job_type") or "")
        desc = " ".join(str(a.get(k) or "") for k in ("title", "description", "hypothesis"))

        # sell truthfully: every claim carries its evidence
        for c in a.get("claims") or []:
            if not (isinstance(c, dict) and c.get("evidence")):
                v("sell_truthfully", f"claim without evidence: {str(c)[:120]}")

        # Product Truth over speed
        if a.get("skip_validation") and (jt in _PRODUCT_TRUTH_TYPES or a.get("product")):
            v("product_truth_over_speed", f"{jt or 'product work'} may not skip validation")
        from ..improve import governance

        if governance._describes_product_truth(desc):
            v("product_truth_over_speed", "replaces the certified chart with an image/model")

        # never manufacture evidence
        fab = governance._mentions(desc, governance._FABRICATION)
        if fab:
            v("never_manufacture_evidence", f"proposes {fab!r}")

        # UNKNOWN is valid: an unknown reading is never reported as a number
        for name, m in (a.get("metrics") or {}).items():
            if isinstance(m, dict) and str(m.get("basis") or "").lower() == "unknown" \
                    and m.get("value") not in (None, "UNKNOWN"):
                v("unknown_is_valid", f"{name} has basis unknown but value {m.get('value')!r}")

        # customer harm outranks revenue
        if a.get("customer_harm"):
            v("customer_harm_outranks_revenue",
              f"declared customer-harm risk ({str(a.get('customer_harm'))[:120]}) blocks the "
              f"action whatever its expected revenue "
              f"(CA${float(a.get('expected_revenue_cad') or 0):.2f})")

        # no silent authority expansion
        agent = a.get("agent")
        if agent and jt:
            from ..agents.registry import Registry
            from .policy import check_dispatch

            try:
                row = Registry(db).get(agent)
            except Exception:  # noqa: BLE001
                row = None
            if row is None:
                v("no_silent_authority_expansion", f"unknown agent {agent!r}")
            else:
                if jt not in (row.allowed_job_types or []):
                    v("no_silent_authority_expansion", f"{agent} does not hold {jt}")
                why = check_dispatch(db, row, jt)
                if why:
                    v("no_silent_authority_expansion", why)

        # every dollar has provenance
        try:
            cost = float(a.get("cost_cad") or 0)
        except (TypeError, ValueError):
            cost = float("inf")
        if cost > 0 and not a.get("provenance"):
            v("every_dollar_has_provenance", f"CA${cost:.2f} with no provenance")

        # consequential decisions are auditable: written here, so it cannot be skipped
        from .classes import is_gated

        if record_audit and jt and is_gated(jt) and not violations:
            from ..agents.registry import Registry

            Registry(db).audit(str(a.get("actor") or "system"), "constitution.consequential",
                               artifact=jt, detail={"department": a.get("department"),
                                                    "key": a.get("key"), "cost_cad": cost})

        # experiments are falsifiable
        if str(a.get("kind") or "") == "experiment":
            missing = [k for k in ("hypothesis", "success_metric", "falsified_if")
                       if not a.get(k)]
            if missing:
                v("experiments_falsifiable", f"experiment missing {missing}")

        # never unknowingly repeat a known failure
        fp = a.get("fingerprint")
        if fp and not a.get("addresses_failure"):
            from .dag import known_failure

            failed = known_failure(db, str(fp))
            if failed:
                v("never_repeat_known_failures",
                  f"{failed} already failed with this fingerprint; resubmit with "
                  "addresses_failure and what changed")
    except Exception as exc:  # noqa: BLE001 - fail closed
        violations.append({"clause": "constitution", "text": "constitution check",
                           "why": f"unreadable ({type(exc).__name__}: {exc})"[:300]})
    return {"allowed": not violations, "violations": violations,
            "checked": [c.key for c in CLAUSES if c.per_action],
            "structural": [{"clause": c.key, "enforcers": list(c.enforcers)}
                           for c in CLAUSES if not c.per_action],
            "at": now.isoformat()}


def describe() -> dict:
    return {"clauses": [{"key": c.key, "text": c.text, "enforcers": list(c.enforcers),
                         "per_action": c.per_action} for c in CLAUSES],
            "evaluate": "brambleloop.authority.constitution.evaluate",
            "consumers": ["brambleloop.authority.dag.dispatch",
                          "brambleloop.laura.core.constitution.review"]}
