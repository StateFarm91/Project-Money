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
# `BRAMBLELOOP_MODEL_ROUTES` names tasks (keys of `routing.TASKS`) one by one:
# "topic_filing=openai,listing_copy=openai". A task it does not name stays on the default vendor.
ROUTES_VAR = "BRAMBLELOOP_MODEL_ROUTES"
# Vendors that may only be reached through a per-task route, never the process-wide switch.
ROUTED_ONLY = frozenset({"openai"})
# The task the owner card names as its example route: culture classification's task
# (`culture.classify.TASK`), a real `routing.TASKS` key (verdict 6985175377 LOW).
EXAMPLE_ROUTE_TASK = "topic_filing"


def vendor(env=None) -> str:
    e = env if env is not None else os.environ
    return (str(e.get(VENDOR_VAR) or "").strip() or DEFAULT_VENDOR)


VENDOR_CARD_KEY = "model.vendor_switch_routed_only"


def vendor_switch_card(db, *, env=None) -> dict:
    """S2 review 6979817823 LOW: `BRAMBLELOOP_MODEL_VENDOR=openai` (any routed-only vendor)
    makes every task refuse, so all model work stops. That is an owner's setting, so it is
    raised loudly as an owner card naming the variable that does what was meant
    (`BRAMBLELOOP_MODEL_ROUTES`), and closed as satisfied once the switch no longer names one.
    Called from the health sweep; writes only the one owner-action row."""
    from ..ops import owner_queue

    name = vendor(env)
    with db.session() as s:
        if name in ROUTED_ONLY:
            from ..authority import standing_internal

            text = (f"Remove {VENDOR_VAR}={name} from the service variables and name the "
                    f"tasks that should use {name} in {ROUTES_VAR} instead (for example "
                    f"{ROUTES_VAR}={EXAMPLE_ROUTE_TASK}={name}).")
            if standing_internal.closure_in_force(s, VENDOR_CARD_KEY, text):
                return {"state": "covered", "vendor": name}
            owner_queue.ensure(
                s, VENDOR_CARD_KEY,
                action=text,
                reason=(f"{VENDOR_VAR}={name}: {name} may only be reached per task through "
                        f"{ROUTES_VAR}, never for the whole process, so every model task is "
                        f"refused while this is set (review 6957356475)."),
                max_cost_cad=0.0, minutes=5,
                consequence_of_delay="all model work stops: every task refuses its vendor",
                blocks="every model call (text and vision)")
            return {"state": "raised", "vendor": name}
        from sqlalchemy import select

        from ..core.models import OwnerAction

        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == VENDOR_CARD_KEY,
                                                 OwnerAction.done.is_(False)))
        if row is not None:
            owner_queue.close(row, owner_queue.SATISFIED,
                              f"{VENDOR_VAR} no longer names a routed-only vendor ({name})")
            return {"state": "closed", "vendor": name}
        from ..authority import standing_internal

        standing_internal.note_condition_cleared(s, VENDOR_CARD_KEY)
    return {"state": "clear", "vendor": name}


ROUTES_CARD_KEY = "model.routes_invalid"


def parse_routes(env=None) -> tuple[dict[str, str], list[dict]]:
    """The per-task vendor table and its invalid entries, parsed without guessing.

    Verdict 6998037105 (MEDIUM): an invalid entry is refused FOR ITS OWN TASK only. The table
    is read on every model call, so raising on the whole table let one typo refuse every task
    in the fleet. A malformed entry (`task` with no `=vendor`) and an entry naming a task the
    router does not know (`routing.TASKS`) are both returned in `invalid`, never in the table;
    `vendor_for` refuses the task an invalid entry names, and the health sweep's owner card
    names every invalid entry (`routes_card`)."""
    from . import routing

    e = env if env is not None else os.environ
    raw = str(e.get(ROUTES_VAR) or "").strip()
    table: dict[str, str] = {}
    invalid: list[dict] = []
    dup: set[str] = set()
    for part in filter(None, (x.strip() for x in raw.split(","))):
        task, sep, name = part.partition("=")
        task, name = task.strip(), name.strip()
        if not sep or not task or not name:
            invalid.append({"entry": part, "task": task or None,
                            "why": "is not task=vendor"})
        elif task not in routing.TASKS:
            # Verdict 6996033652 LOW: a typo would leave the meant task on the default vendor
            # while the owner believes it is routed; it is named, never silently ignored.
            invalid.append({"entry": part, "task": task,
                            "why": f"names task {task!r}, which is not a routing task "
                                   f"(routing.TASKS)"})
        elif name not in _VENDORS:
            # Verdict 6999967600 S2 LOW: `topic_filing=bogus` refused its task with no card.
            invalid.append({"entry": part, "task": task,
                            "why": f"names vendor {name!r}, which is not a registered model "
                                   f"vendor ({sorted(_VENDORS)})"})
        elif task in table or task in dup:
            # Verdict 6999967600 S2 LOW: a task named twice was last-wins, silently.
            dup.add(task)
            invalid.append({"entry": part, "task": task,
                            "why": f"routes task {task!r} a second time; refusing rather "
                                   f"than choosing one"})
        else:
            table[task] = name
    for task in dup:
        table.pop(task, None)
    return table, invalid


def routes(env=None) -> dict[str, str]:
    """The valid per-task vendor routes (invalid entries are in `parse_routes`)."""
    return parse_routes(env)[0]


def routes_card(db, *, env=None) -> dict:
    """Verdict 6998037105: an invalid `BRAMBLELOOP_MODEL_ROUTES` entry is an owner's setting
    that silently refuses its task, so it is raised as one owner card naming every invalid
    entry, and closed as satisfied once the table has none. Called from the health sweep."""
    from sqlalchemy import select

    from ..core.models import OwnerAction
    from ..ops import owner_queue

    _table, invalid = parse_routes(env)
    with db.session() as s:
        if invalid:
            from ..authority import standing_internal

            named = "; ".join(f"{b['entry']!r} {b['why']}" for b in invalid)
            text = (f"Correct {ROUTES_VAR} in the service variables: {named}. Each entry "
                    f"is task=vendor with a task from routing.TASKS (for example "
                    f"{EXAMPLE_ROUTE_TASK}=openai).")
            if standing_internal.closure_in_force(s, ROUTES_CARD_KEY, text):
                return {"state": "covered", "invalid": invalid}
            owner_queue.ensure(
                s, ROUTES_CARD_KEY,
                action=text,
                reason=(f"{ROUTES_VAR} has {len(invalid)} invalid entr"
                        f"{'y' if len(invalid) == 1 else 'ies'}; the task each one names is "
                        f"refused its model calls until it is corrected (verdict 6998037105)."),
                max_cost_cad=0.0, minutes=5,
                consequence_of_delay="the named tasks make no model calls",
                blocks="model calls for the tasks the invalid entries name")
            return {"state": "raised", "invalid": invalid}
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == ROUTES_CARD_KEY,
                                                 OwnerAction.done.is_(False)))
        if row is not None:
            owner_queue.close(row, owner_queue.SATISFIED, f"{ROUTES_VAR} has no invalid entry")
            return {"state": "closed", "invalid": []}
        from ..authority import standing_internal

        standing_internal.note_condition_cleared(s, ROUTES_CARD_KEY)
    return {"state": "clear", "invalid": []}


def vendor_for(task_key: str, env=None) -> str:
    """The one router: the vendor `task_key` runs on. Raises `NoProviderAvailable` for an
    unregistered vendor, or a routed-only vendor named by the process-wide switch."""
    table, invalid = parse_routes(env)
    mine = [b for b in invalid if b["task"] == task_key]
    if mine:
        raise NoProviderAvailable(
            f"{ROUTES_VAR} entry {mine[0]['entry']!r} {mine[0]['why']}; task {task_key!r} is "
            f"refused rather than guessed (the other tasks are unaffected)")
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


# ---- the one call-size estimate (S2 review 6979817823 MEDIUM) ----------------------------------
# A call's reservation (made by its caller through `check_budget`) and the paid-provider gate's
# own estimate (made by the vendor adapter just before the request) must be computed the same
# way: when they differed, classify reserved the user text only while the OpenAI gate counted
# system + user, and every OpenAI classify call was refused `reservation_underfunded`.

def image_tokens(model: str) -> int:
    """Input tokens one image costs on `model`: the vendor's own per-image figure."""
    from . import openai_chat

    if model in openai_chat.PRICES_USD_PER_MTOK:
        return int(openai_chat.image_tokens(model))
    from . import anthropic

    return int(anthropic.IMAGE_TOKENS_ESTIMATE)


def input_tokens(model: str, *, system: str = "", user: str = "", images: int = 0) -> int:
    """The input-token estimate for one call: system and user text at 4 characters a token,
    plus `images` at the model's per-image figure. Callers reserve with it; the OpenAI gate
    checks with it; so a reservation is never smaller than the gate's own figure."""
    return ((len(system or "") + len(user or "")) // 4
            + image_tokens(model) * max(0, int(images)))


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
                     "USD_TO_CAD",
                     # The spend-ledger lock (pg advisory / BEGIN IMMEDIATE) every
                     # check-and-write of a ceiling row takes; a lock on the ledger, not a
                     # model call (toy_board, owner_directives).
                     "budget_lock", "budget_lock_held"})


def __getattr__(name: str):
    if name in NEUTRAL:
        from . import anthropic

        return getattr(anthropic, name)
    raise AttributeError(name)
