"""F-091: the provider abstraction boundary -- the one place business code gets a model.

Business modules ask for a provider *by task* (`for_task`) and spend through the
vendor-neutral ledger calls (`check_budget`, `release_reservation`); they never import a
vendor module. The vendor is chosen here, from `BRAMBLELOOP_MODEL_VENDOR` (default
`anthropic`, the only vendor implemented today), through a registry a second vendor joins
with `register_vendor` -- so a swap touches this file's registry, not the callers.

A vendor name nobody registered raises `NoProviderAvailable`; it never falls back silently.
A provider returned for a task whose tier needs vision satisfies `VisionProvider` (`see`).

`tests/test_w4_fmbatch1_provider_boundary.py` scans every module outside `gateway/` and fails
on any new direct import of a vendor module. The callers that still import
`gateway.anthropic` directly are listed there by name with the reason they are pending.
"""
from __future__ import annotations

import os
from typing import Callable, Protocol

from .model_gateway import ModelResponse, NoProviderAvailable

VENDOR_VAR = "BRAMBLELOOP_MODEL_VENDOR"
DEFAULT_VENDOR = "anthropic"


class TextProvider(Protocol):
    name: str
    model: str
    cost_per_1k_input_cad: float
    cost_per_1k_output_cad: float

    def complete(self, system: str, user: str, *, max_tokens: int) -> ModelResponse: ...


class VisionProvider(TextProvider, Protocol):
    def see(self, system: str, prompt: str, image_urls: list[str], *,
            max_tokens: int) -> ModelResponse: ...


def _anthropic(task_key: str, **kw):
    from . import anthropic

    return anthropic.provider_for(task_key, **kw)


def _openai(task_key: str, **kw):
    from . import openai_chat

    return openai_chat.provider_for(task_key, **kw)


_VENDORS: dict[str, Callable[..., TextProvider]] = {"anthropic": _anthropic,
                                                    "openai": _openai}


def register_vendor(name: str, factory: Callable[..., TextProvider]) -> None:
    _VENDORS[name] = factory


def unregister_vendor(name: str) -> None:
    if name != DEFAULT_VENDOR:
        _VENDORS.pop(name, None)


# S2 review 6957356475 (HIGH): the vendor is chosen PER TASK, by one router every builder
# asks (`for_task`, `failover.decide`/`gateway_for`/`job_gateway`). A process-wide switch to a
# second vendor sent every caller -- vision judges, culture, serp -- to a provider the rest of
# the gateway could not price or route, so no call happened and every Anthropic path stopped.
# `BRAMBLELOOP_MODEL_ROUTES` names tasks one by one: "culture_classify=openai,serp_x=openai".
# A task it does not name stays on the default vendor.
ROUTES_VAR = "BRAMBLELOOP_MODEL_ROUTES"
# Vendors that may only be reached through a per-task route, never the process-wide switch.
ROUTED_ONLY = frozenset({"openai"})


def vendor(env=None) -> str:
    e = env if env is not None else os.environ
    return (str(e.get(VENDOR_VAR) or "").strip() or DEFAULT_VENDOR)


def routes(env=None) -> dict[str, str]:
    """The per-task vendor table, parsed strictly: a malformed entry is refused, not skipped."""
    e = env if env is not None else os.environ
    raw = str(e.get(ROUTES_VAR) or "").strip()
    out: dict[str, str] = {}
    for part in filter(None, (x.strip() for x in raw.split(","))):
        task, sep, name = part.partition("=")
        task, name = task.strip(), name.strip()
        if not sep or not task or not name:
            raise NoProviderAvailable(f"{ROUTES_VAR} entry {part!r} is not task=vendor; "
                                      f"refusing rather than guessing a route")
        out[task] = name
    return out


def vendor_for(task_key: str, env=None) -> str:
    """The one router: the vendor `task_key` runs on. Raises `NoProviderAvailable` for an
    unregistered vendor, or a routed-only vendor named by the process-wide switch."""
    table = routes(env)
    if task_key in table:
        name = table[task_key]
    else:
        name = vendor(env)
        if name in ROUTED_ONLY:
            raise NoProviderAvailable(
                f"{VENDOR_VAR}={name!r}: {name} is enabled per task through {ROUTES_VAR}, "
                f"never for the whole process (review 6957356475)")
    if name not in _VENDORS:
        raise NoProviderAvailable(
            f"task {task_key!r} routes to {name!r}, which names no registered model vendor "
            f"(registered: {sorted(_VENDORS)}); refusing rather than falling back")
    return name


def for_task(task_key: str, *, env=None, **kw) -> TextProvider:
    name = vendor_for(task_key, env)
    factory = _VENDORS.get(name)
    if factory is None:
        raise NoProviderAvailable(
            f"{VENDOR_VAR}={name!r} names no registered model vendor "
            f"(registered: {sorted(_VENDORS)}); refusing rather than falling back")
    return factory(task_key, **kw)


# The name every pre-facade caller used; same factory, chosen by vendor.
provider_for = for_task


def check_budget(db, *, purpose: str, **kw) -> dict:
    """The pre-call reservation against every ceiling; vendor-neutral (it prices by model).
    `purpose` is required here: a reservation always names the question it pays for."""
    from . import anthropic

    return anthropic.check_budget(db, purpose=purpose, **kw)


def release_reservation(db, reservation_id, **kw):
    from . import anthropic

    return anthropic.release_reservation(db, reservation_id, **kw)


def classify_failure(exc: BaseException) -> str:
    """Vendor-neutral: whether a failed model call's billing is DECLINED or UNCERTAIN (the split
    `ModelGateway._billing` bills on). Business modules ask here, never the vendor module
    (F-091 boundary; W5-INTEG1, for culture.classify's OPUS2I C-4 fallback)."""
    from . import anthropic

    return anthropic._classify_failure(exc)


# Vendor-neutral names that still live in the Anthropic module (the ceiling ledger, its
# refusals and its estimators). Callers read them from here so migrating a caller is an
# import change; moving the ledger itself out of the vendor module is the follow-up.
NEUTRAL = frozenset({"BudgetExceeded", "AgentCeilingExceeded", "IMAGE_TOKENS_ESTIMATE",
                     "MAX_IMAGES_PER_CALL", "VISION_TIMEOUT_SECONDS", "estimate_cad",
                     "vision_usable", "monthly_ceiling_cad", "check_budget_cad",
                     # The probe record (has a real call succeeded?), the month's spend, an
                     # agent's daily ceiling and the assumed USD->CAD rate: ledger and probe
                     # readings, not a model call (F-091 rest, FMBATCH2).
                     "usable", "last_probe", "spent_this_month_cad", "agent_daily_ceiling",
                     "USD_TO_CAD"})


def __getattr__(name: str):
    if name in NEUTRAL:
        from . import anthropic

        return getattr(anthropic, name)
    raise AttributeError(name)
