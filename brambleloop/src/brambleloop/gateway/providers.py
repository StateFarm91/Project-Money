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


_VENDORS: dict[str, Callable[..., TextProvider]] = {"anthropic": _anthropic}


def register_vendor(name: str, factory: Callable[..., TextProvider]) -> None:
    _VENDORS[name] = factory


def unregister_vendor(name: str) -> None:
    if name != DEFAULT_VENDOR:
        _VENDORS.pop(name, None)


def vendor(env=None) -> str:
    e = env if env is not None else os.environ
    return (str(e.get(VENDOR_VAR) or "").strip() or DEFAULT_VENDOR)


def for_task(task_key: str, *, env=None, **kw) -> TextProvider:
    name = vendor(env)
    factory = _VENDORS.get(name)
    if factory is None:
        raise NoProviderAvailable(
            f"{VENDOR_VAR}={name!r} names no registered model vendor "
            f"(registered: {sorted(_VENDORS)}); refusing rather than falling back")
    return factory(task_key, **kw)


def check_budget(db, **kw) -> dict:
    """The pre-call reservation against every ceiling; vendor-neutral (it prices by model)."""
    from . import anthropic

    return anthropic.check_budget(db, **kw)


def release_reservation(db, reservation_id, **kw):
    from . import anthropic

    return anthropic.release_reservation(db, reservation_id, **kw)


# Vendor-neutral names that still live in the Anthropic module (the ceiling ledger, its
# refusals and its estimators). Callers read them from here so migrating a caller is an
# import change; moving the ledger itself out of the vendor module is the follow-up.
NEUTRAL = frozenset({"BudgetExceeded", "AgentCeilingExceeded", "IMAGE_TOKENS_ESTIMATE",
                     "MAX_IMAGES_PER_CALL", "VISION_TIMEOUT_SECONDS", "estimate_cad",
                     "vision_usable", "monthly_ceiling_cad", "check_budget_cad"})


def __getattr__(name: str):
    if name in NEUTRAL:
        from . import anthropic

        return getattr(anthropic, name)
    raise AttributeError(name)
