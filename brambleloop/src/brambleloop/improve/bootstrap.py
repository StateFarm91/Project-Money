"""The league's incumbents, registered from the code that is actually running them.

Requirements 95, 96, 180. The configuration league had `register`, `compare`, `promote` and
`rollback`, and production held no ConfigVersion row at all: the nightly CHALLENGERS stage
read zero configurations every night and reported `did_not_run`, and the challenger role
found nothing to challenge because nothing was recorded as running. A league with no
incumbents is a scoreboard for a game nobody is playing.

The incumbents exist, in code: the model-routing task table in `gateway.routing.TASKS` says
which model answers which question, and `visual.provider_trial.INCUMBENT` names the image
generator every listing render goes through. This reads them and registers each as the
incumbent version of its configuration, with the reason it is running -- which, honestly, is
that it was first -- so the registry can say "what is running" tonight and "should it still
be" the day a trial says otherwise.

Two rules. **Registration is idempotent on content**: `league.register` refuses to create a
second version for an identical payload, so calling this every night costs nothing, and a
routing change in code produces a new version whose `why_changed` says the table moved.
**No challenger runs here.** A provider trial that already ran leaves its verdict in the
audit log; this copies the verdict onto the configuration rows it was about, as a measured
outcome, so `standings()` stops reporting an incumbent that has never been measured against
anything when in fact it has. Running a trial is a spending decision, and this spends nothing.
"""
from __future__ import annotations

import json

from . import league

ACTION = "improve.bootstrap"

ROUTING_KIND = "model"
ROUTING_KEY_PREFIX = "routing:"
IMAGE_KIND = "tool"
IMAGE_KEY = "image_provider"

# Which department answers for each model task. Named rather than inferred from the tier,
# because a regression in a routing decision is discovered by the department whose output
# moved, and `league.register` refuses a version that does not say which one that is.
TASK_DEPARTMENTS: dict[str, tuple[str, ...]] = {
    "listing_classify": ("market_radar",),
    "listing_mechanisms": ("market_radar",),
    "topic_filing": ("market_radar",),
    "seasonal_signal": ("market_radar",),
    "gallery_observation": ("market_radar", "creative_assets"),
    "construction_reading": ("market_radar", "product_creativity"),
    "asset_inspection": ("creative_assets",),
    "image_benchmark_judging": ("creative_assets",),
    "listing_copy": ("seo_search",),
    "creative_evaluation": ("product_creativity",),
    "concept_ideation": ("product_creativity",),
    "concept_generation": ("product_creativity",),
    "benchmark_challenge": ("product_creativity", "quality"),
}

# A task the table above has not heard of touches the routing itself, which is the runtime's.
DEFAULT_DEPARTMENTS: tuple[str, ...] = ("runtime",)


def _routing_payload(task, tier) -> str:
    return json.dumps({"task": task.key, "tier": task.tier, "model": tier.model,
                       "max_output_tokens": task.max_output_tokens,
                       "typical_input_tokens": task.typical_input_tokens,
                       "cacheable": task.cacheable}, sort_keys=True)


def register_routing_incumbents(db) -> dict:
    """One incumbent version per model task, read from the routing table that runs them."""
    from ..gateway import routing

    registered, unchanged = [], []
    for key, task in routing.TASKS.items():
        tier = routing.TIERS[task.tier]
        try:
            cost = routing.estimate_cad(key)
        except Exception:  # noqa: BLE001 - an unpriced tier is a finding, not a stop
            cost = 0.0
        out = league.register(
            db, kind=ROUTING_KIND, key=f"{ROUTING_KEY_PREFIX}{key}",
            payload=_routing_payload(task, tier),
            why_changed=(f"incumbent model routing recorded from gateway.routing.TASKS: "
                         f"{task.why}. It runs because the table says so, and the table was "
                         f"written before any challenger existed"),
            tests_declared=("tests/test_pods_routing.py",), cost_per_call_cad=cost,
            affected_departments=TASK_DEPARTMENTS.get(key, DEFAULT_DEPARTMENTS),
            incumbent=True)
        (unchanged if out.get("unchanged") else registered).append(
            {"key": key, "config_id": out["id"], "version": out["version"]})
        if out.get("unchanged"):
            _follow_code(db, out["id"], source="gateway.routing.TASKS")
    return {"registered": registered, "unchanged": unchanged}


def _follow_code(db, config_id: int, *, source: str) -> bool:
    """Make the version the code runs the incumbent, when it already exists as a challenger.

    `league.register` returns an existing row for an identical payload without touching its
    incumbent flag. So when the code is changed to what a league challenger proposed -- the
    only way a code-mirrored configuration can be promoted -- the registry would keep naming
    the old version as running. The registry follows the code, never the other way round.
    """
    from ..core.models import ConfigVersion

    with db.session() as s:
        row = s.get(ConfigVersion, config_id)
        if row is None or row.incumbent:
            return False
    league.promote(db, config_id, evidence_ref=f"code:{source}",
                   outcome={"why": f"the running code ({source}) now uses this version",
                            "promoted_by": "code"})
    return True


# ---- challengers (#95, #180) ------------------------------------------------------------

# The cheaper tier a task could be answered by. A cost optimiser's challenger is the same task
# one tier down: the only challenger that can be written without inventing a prompt, and the
# one #188's marginal-value question most needs answered.
CHEAPER_TIER: dict[str, str] = {"deep": "standard", "standard": "cheap"}


def register_routing_challengers(db) -> dict:
    """One challenger per model task that is not already on the cheapest tier.

    Registered, never run: `league.cycle` compares it only on recorded runs, and producing a
    run is a model call. Idempotent on content, so the nightly and league sweeps add nothing
    once each challenger exists, and a routing change in code produces a new challenger for
    the new incumbent rather than leaving the old one pointing at a tier nothing runs.
    """
    from ..gateway import routing

    registered, unchanged, skipped = [], [], []
    for key, task in routing.TASKS.items():
        cheaper = CHEAPER_TIER.get(task.tier)
        if cheaper is None or cheaper not in routing.TIERS:
            skipped.append({"key": key, "why": f"{task.tier} is already the cheapest tier"})
            continue
        tier = routing.TIERS[cheaper]
        payload = json.dumps({"task": task.key, "tier": cheaper, "model": tier.model,
                              "max_output_tokens": task.max_output_tokens,
                              "typical_input_tokens": task.typical_input_tokens,
                              "cacheable": task.cacheable}, sort_keys=True)
        try:
            cost = tier.cost_cad(task.typical_input_tokens, task.max_output_tokens)
        except Exception:  # noqa: BLE001 - an unpriced tier is a finding, not a stop
            cost = 0.0
        out = league.register(
            db, kind=ROUTING_KIND, key=f"{ROUTING_KEY_PREFIX}{key}", payload=payload,
            why_changed=(f"cost optimiser challenger for {key}: the same task routed one tier "
                         f"cheaper, to {cheaper} ({tier.model}). It is compared with the "
                         f"incumbent on the incumbent's shared task set and a holdout before "
                         f"anything switches, and it switches only by a change to "
                         f"gateway.routing.TASKS the owner approves"),
            tests_declared=("tests/test_pods_routing.py",), cost_per_call_cad=cost,
            affected_departments=TASK_DEPARTMENTS.get(key, DEFAULT_DEPARTMENTS),
            incumbent=False)
        (unchanged if out.get("unchanged") else registered).append(
            {"key": key, "config_id": out["id"], "version": out["version"],
             "tier": cheaper})
    return {"registered": len(registered), "unchanged": len(unchanged),
            "skipped": len(skipped), "new": registered}


def _provider_payload(provider) -> str:
    return json.dumps({"provider": provider.key, "model": provider.model,
                       "endpoint": provider.endpoint, "dialect": provider.dialect,
                       "usd_per_image": provider.usd_per_image,
                       "reference_images": provider.reference_images}, sort_keys=True)


def register_image_incumbent(db) -> dict:
    """The image generator every listing render goes through, as the incumbent tool."""
    from ..gateway import images, routing
    from ..visual import provider_trial

    provider = images.BY_KEY.get(provider_trial.INCUMBENT)
    if provider is None:
        return {"registered": False,
                "why": (f"{provider_trial.INCUMBENT!r} is not in the image provider table, "
                        f"so there is nothing to register as running")}
    out = league.register(
        db, kind=IMAGE_KIND, key=IMAGE_KEY, payload=_provider_payload(provider),
        why_changed=(f"incumbent image generator recorded from visual.provider_trial: "
                     f"{provider.what}. {provider.note}"),
        tests_declared=("tests/test_provider_trial.py",),
        cost_per_call_cad=round(provider.usd_per_image / routing.USD_PER_CAD, 6),
        affected_departments=("creative_assets",), incumbent=True)
    if out.get("unchanged"):
        _follow_code(db, out["id"], source="visual.provider_trial.INCUMBENT")
    return {"registered": not out.get("unchanged"), "config_id": out["id"],
            "version": out["version"], "provider": provider.key}


def _challenger_version(db, provider_key: str, *, trial_ref: str) -> int | None:
    """The challenger's own row, so its verdict has somewhere to live. Never the incumbent."""
    from ..gateway import images, routing

    provider = images.BY_KEY.get(provider_key)
    if provider is None:
        return None
    out = league.register(
        db, kind=IMAGE_KIND, key=IMAGE_KEY, payload=_provider_payload(provider),
        why_changed=(f"challenger image generator put to a provider trial ({trial_ref}): "
                     f"{provider.what}. Registered so the trial's verdict is recorded "
                     f"against the configuration it judged; it is not the incumbent"),
        tests_declared=("tests/test_provider_trial.py",),
        cost_per_call_cad=round(provider.usd_per_image / routing.USD_PER_CAD, 6),
        affected_departments=("creative_assets",), incumbent=False)
    return out["id"]


def record_trial_outcomes(db) -> dict:
    """Copy every completed provider trial's verdict onto the configurations it judged."""
    from sqlalchemy import select

    from ..core.models import AuditLog, ConfigVersion
    from ..visual import provider_trial

    with db.session() as s:
        trials = [(a.id, dict(a.detail or {})) for a in s.scalars(
            select(AuditLog).where(AuditLog.action == provider_trial.ACTION)
            .order_by(AuditLog.id))]
        incumbent = s.scalar(select(ConfigVersion).where(
            ConfigVersion.kind == IMAGE_KIND, ConfigVersion.key == IMAGE_KEY,
            ConfigVersion.incumbent == True))  # noqa: E712
        incumbent_id = incumbent.id if incumbent is not None else None

    recorded, skipped = [], []
    for audit_id, detail in trials:
        if not detail.get("ran"):
            skipped.append({"audit_id": audit_id, "why": "the trial did not run"})
            continue
        ref = f"audit:{audit_id}"
        verdict = dict(detail.get("verdict") or {})
        by_provider = dict(detail.get("by_provider") or {})
        challenger = detail.get("challenger") or ""
        outcome_common = {"trial": provider_trial.ACTION, "challenger": challenger,
                          "recommendation": verdict.get("recommendation"),
                          "why": (verdict.get("why") or "")[:300],
                          "spent_cad": detail.get("spent_cad")}
        if incumbent_id is not None:
            out = league.record_measured_outcome(
                db, incumbent_id, evidence_ref=ref,
                outcome={**outcome_common, "role": "incumbent",
                         "summary": by_provider.get(detail.get("incumbent") or "", {})})
            if out["recorded"]:
                recorded.append({"config_id": incumbent_id, "role": "incumbent",
                                 "evidence_ref": ref})
        challenger_id = _challenger_version(db, challenger, trial_ref=ref) if challenger \
            else None
        if challenger_id is not None:
            out = league.record_measured_outcome(
                db, challenger_id, evidence_ref=ref,
                outcome={**outcome_common, "role": "challenger",
                         "summary": by_provider.get(challenger, {})})
            if out["recorded"]:
                recorded.append({"config_id": challenger_id, "role": "challenger",
                                 "evidence_ref": ref})
    return {"trials_read": len(trials), "recorded": recorded, "skipped": skipped}


# ---- #96: every material prompt, tool and decision policy, versioned from the running code --

PROMPT_KIND = "prompt"
TOOL_KIND = "tool"
POLICY_KIND = "policy"

# The deterministic tools every release passes through, by the module that is the tool. Their
# version is the digest of the running source, so a change to the compiler is a new version
# with the reason recorded -- the registry follows the code.
TOOLS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    # key: (module path relative to the package, tests that exercise it, departments)
    "tool:cir_compiler": ("cir/compiler.py", ("tests/test_compiler.py",),
                          ("pattern_engineering", "quality")),
    "tool:digital_twin": ("cir/twin.py", ("tests/test_twin.py",),
                          ("pattern_engineering", "creative_assets")),
    "tool:reverse_compiler": ("cir/reverse.py", ("tests/test_reverse.py",),
                              ("pattern_engineering", "quality")),
    "tool:regression_suite": ("gates/regression.py", ("tests/test_defects.py",),
                              ("quality",)),
    "tool:pdf_writer": ("publish/pdf.py", ("tests/test_layout_qa.py",),
                        ("creative_assets", "customer_experience")),
}


def _source_digest(relative: str) -> str:
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / relative
    try:
        return league.digest_of(path.read_text(encoding="utf-8"))
    except OSError:
        return ""


def _policy_payloads() -> dict[str, tuple[str, tuple[str, ...], str]]:
    """Each gate-tier decision policy as the running code states it."""
    from ..finance import spend_policy
    from ..gates import policy as gate_policy
    from ..improve import tiers

    return {
        "policy:release_gate": (json.dumps({"POLICY_VERSION": gate_policy.POLICY_VERSION}),
                                ("quality", "seo_search"),
                                "the release Policy Gate's version, as gates.policy states it"),
        "policy:spend_ceilings": (json.dumps({
            "CEILING_CAD": spend_policy.CEILING_CAD,
            "ESCALATE_AT_SHARE": spend_policy.ESCALATE_AT_SHARE,
            "INFRA_CEILING_CAD": spend_policy.INFRA_CEILING_CAD,
            "BENCHMARK_BUDGET_CAD": spend_policy.BENCHMARK_BUDGET_CAD}, sort_keys=True),
            ("finance", "runtime"), "the monthly and infrastructure spend ceilings in code"),
        "policy:promotion_tiers": (json.dumps({t.key: [t.cooldown_hours, t.weekly_ceiling,
                                                       list(t.requires)] for t in tiers.TIERS},
                                              sort_keys=True),
                                   ("runtime", "quality"),
                                   "the improvement tiers' cooldowns, ceilings and evidence"),
    }


def register_code_versions(db) -> dict:
    """Register every prompt, deterministic tool and decision policy the code runs (#96)."""
    from ..gateway import prompts

    registered, unchanged = [], []

    def one(kind, key, payload, why, tests, departments, cost=0.0):
        prior = league.incumbent_payload(db, kind=kind, key=key)
        reason = (f"{why}; first recorded from the running code" if prior is None else
                  f"{why}; the running code moved from version {prior['version']}")
        out = league.register(db, kind=kind, key=key, payload=payload, why_changed=reason,
                              tests_declared=tests, cost_per_call_cad=cost,
                              affected_departments=departments, incumbent=True)
        (unchanged if out.get("unchanged") else registered).append(
            {"kind": kind, "key": key, "version": out["version"]})
        if out.get("unchanged"):
            _follow_code(db, out["id"], source=key)

    for prompt in prompts.all_prompts():
        one(PROMPT_KIND, f"prompt:{prompt.name}",
            json.dumps({"ref": prompt.ref, "sha256": prompt.sha256,
                        "output_schema": list(prompt.output_schema),
                        "max_output_tokens": prompt.max_output_tokens}, sort_keys=True),
            f"prompt {prompt.ref} as registered in gateway.prompts",
            ("tests/test_gateway.py",), ("product_creativity", "seo_search"))
    for key, (relative, tests, departments) in TOOLS.items():
        digest = _source_digest(relative)
        if not digest:
            continue
        one(TOOL_KIND, key, json.dumps({"module": relative, "source_sha256": digest}),
            f"deterministic tool {relative}, versioned by its source digest", tests,
            departments)
    for key, (payload, departments, why) in _policy_payloads().items():
        one(POLICY_KIND, key, payload, why, ("tests/test_gates.py", "tests/test_tiers.py"),
            departments)
    return {"registered": registered, "unchanged": len(unchanged)}


def ensure(db) -> dict:
    """Register the incumbents and record any trial verdicts. Cheap, idempotent, spends nothing."""
    routing = register_routing_incumbents(db)
    image = register_image_incumbent(db)
    trials = record_trial_outcomes(db)
    code = register_code_versions(db)
    return {
        "routing": {"registered": len(routing["registered"]),
                    "unchanged": len(routing["unchanged"])},
        "code_versions": {"registered": len(code["registered"]),
                          "unchanged": code["unchanged"]},
        "image_provider": image,
        "trials": {"read": trials["trials_read"], "recorded": len(trials["recorded"])},
        "challengers_run": 0,
        "note": ("incumbents are registered from the code that runs them and trial verdicts "
                 "are copied onto the rows they judged. Nothing here runs a challenger; that "
                 "is a spending decision and this spends nothing"),
    }


def state() -> dict:
    return {
        "action": ACTION,
        "registers": {
            f"{ROUTING_KIND}/{ROUTING_KEY_PREFIX}<task>": "one incumbent per gateway.routing task",
            f"{IMAGE_KIND}/{IMAGE_KEY}": "the image generator visual.provider_trial names",
        },
        "records": "provider trial verdicts as measured outcomes on both arms",
        "never": "runs a challenger",
    }
