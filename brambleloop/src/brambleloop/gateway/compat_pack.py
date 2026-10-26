"""F-096: the provider compatibility pack -- golden tasks a provider must pass before it can
replace (or keep serving after a change) the current one.

Five task families, each scored by deterministic code against a known answer, never by
another model:

* extraction            -- pull gauge, hook and yardage out of pattern prose exactly;
* vision_gallery        -- read a gallery (needs a provider with `see`); a text-only
                           provider scores UNSUPPORTED, which is never a pass;
* creative_jury         -- rank candidates under a rubric with one hard-rule violator, which
                           must be flagged and must not win;
* benchmark_comparison  -- pick the winner per metric from two metric sets;
* improvement_analysis  -- direction and significance of a before/after change at a stated
                           threshold.

`run(provider)` sends each task through `provider.complete` (or `provider.see`), so any
object satisfying the gateway `Provider` protocol can be tested. Verdict `compatible` only
when every task PASSes; FAIL, ERROR and UNSUPPORTED all block. `compare(current, candidate)`
says whether a swap would lose a task the current provider passes.

`record(db, report)` writes the result as a `gateway.compat_pack` audit row; the provider
watch (F-099) asks for a fresh pack whenever a provider snapshot changes. Tests run this
against scripted `EchoProvider`s only; a live run is an operator drill and is a paid call.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

PASS, FAIL, ERROR, UNSUPPORTED = "PASS", "FAIL", "ERROR", "UNSUPPORTED"
AUDIT_ACTION = "gateway.compat_pack"
SYSTEM = ("You are a careful assistant. Answer with one JSON object only, no prose, exactly "
          "in the shape asked for.")


@dataclass(frozen=True)
class Task:
    key: str
    family: str
    prompt: str
    check: Callable[[dict], list[str]]
    vision: bool = False
    image_urls: tuple[str, ...] = ()


def _parse(text: str) -> dict:
    t = (text or "").strip()
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        raise ValueError("no JSON object in the reply")
    out = json.loads(m.group(0))
    if not isinstance(out, dict):
        raise ValueError("reply is not a JSON object")
    return out


# ---- golden tasks --------------------------------------------------------------------------

EXTRACT_TEXT = ("Gauge: 18 sts and 20 rows = 10 cm in single crochet with a 4.5 mm hook. "
                "You will need 3 balls of Aran cotton (each 85 m), about 255 m in total.")


def _extract(out: dict) -> list[str]:
    want = {"stitches_per_10cm": 18, "rows_per_10cm": 20, "hook_mm": 4.5, "total_metres": 255}
    return [f"{k}: expected {v!r}, got {out.get(k)!r}" for k, v in want.items()
            if not isinstance(out.get(k), (int, float)) or float(out[k]) != float(v)]


def _jury(out: dict) -> list[str]:
    problems = []
    ranking = out.get("ranking")
    if not isinstance(ranking, list) or sorted(map(str, ranking)) != ["A", "B", "C"]:
        return [f"ranking must order exactly A, B, C; got {ranking!r}"]
    if ranking[0] == "B":
        problems.append("the hard-rule violator B was ranked first")
    if [str(x) for x in (out.get("violations") or [])] != ["B"]:
        problems.append(f"violations must be exactly ['B']; got {out.get('violations')!r}")
    return problems


def _bench(out: dict) -> list[str]:
    want = {"conversion": "X", "return_rate": "Y", "cost_per_sale": "X"}
    got = out.get("winners") if isinstance(out.get("winners"), dict) else {}
    return [f"{k}: expected {v}, got {got.get(k)!r}" for k, v in want.items()
            if got.get(k) != v]


def _improve(out: dict) -> list[str]:
    problems = []
    if out.get("direction") != "worse":
        problems.append(f"direction: expected 'worse', got {out.get('direction')!r}")
    if out.get("significant") is not True:
        problems.append(f"significant: expected true, got {out.get('significant')!r}")
    d = out.get("relative_change")
    if not isinstance(d, (int, float)) or abs(float(d) - (-0.25)) > 0.005:
        problems.append(f"relative_change: expected -0.25, got {d!r}")
    return problems


def _gallery(out: dict) -> list[str]:
    n = out.get("listing_count")
    return [] if n == 4 else [f"listing_count: expected 4, got {n!r}"]


TASKS: tuple[Task, ...] = (
    Task("extract.gauge_yardage", "extraction",
         f"From this text: {EXTRACT_TEXT!r} return {{\"stitches_per_10cm\": int, "
         f"\"rows_per_10cm\": int, \"hook_mm\": number, \"total_metres\": int}}.", _extract),
    Task("vision.gallery_count", "vision_gallery",
         "How many distinct product listings are visible in this gallery screenshot? "
         "Return {\"listing_count\": int}.", _gallery, vision=True,
         image_urls=("fixture://compat/gallery_4_listings.png",)),
    Task("jury.hard_rule", "creative_jury",
         "Rank candidate titles A, B, C for a crochet hat listing. Hard rule: no title may "
         "claim a size. A: 'Cozy Ribbed Beanie Pattern'. B: 'Fits All Adults Beanie'. "
         "C: 'Textured Winter Hat Pattern'. Return {\"ranking\": [ids best first], "
         "\"violations\": [ids that break the hard rule]}.", _jury),
    Task("bench.per_metric", "benchmark_comparison",
         "Shop X: conversion 3.1%, return_rate 2.0%, cost_per_sale CA$1.10. Shop Y: "
         "conversion 2.4%, return_rate 1.2%, cost_per_sale CA$1.60. Higher conversion is "
         "better; lower return_rate and cost_per_sale are better. Return {\"winners\": "
         "{\"conversion\": \"X\"|\"Y\", \"return_rate\": ..., \"cost_per_sale\": ...}}.", _bench),
    Task("improve.direction", "improvement_analysis",
         "Conversion was 4.0% before a change and 3.0% after. A relative change beyond 10% "
         "is significant. Return {\"direction\": \"better\"|\"worse\"|\"same\", "
         "\"relative_change\": number (after/before - 1), \"significant\": bool}.", _improve),
)
FAMILIES = tuple(sorted({t.family for t in TASKS}))


def run(provider, *, db=None, agent: str = "orchestrator",
        tasks: tuple[Task, ...] = TASKS, max_tokens: int = 400) -> dict:
    """Every task through `provider`. With `db` (a live drill), each call is reserved against
    the ceilings first and released with its cost after, like every other model-spend path;
    without `db` only a stub provider may be passed (tests)."""
    from . import providers as gw

    if db is None and getattr(provider, "cost_per_1k_input_cad", 0) and not getattr(
            provider, "scripted", None):
        raise ValueError("a billed provider is only run with `db`, so its spend is reserved")
    results = []
    for t in tasks:
        reservation = None
        try:
            if db is not None:
                reservation = gw.check_budget(
                    db, model=provider.model, input_tokens=len(t.prompt) // 4,
                    max_tokens=max_tokens, agent=agent, purpose="compat_pack")["reservation_id"]
            if t.vision:
                see = getattr(provider, "see", None)
                if not callable(see):
                    results.append({"task": t.key, "family": t.family, "status": UNSUPPORTED,
                                    "problems": ["provider has no vision method"]})
                    continue
                resp = see(SYSTEM, t.prompt, list(t.image_urls), max_tokens=max_tokens)
            else:
                resp = provider.complete(SYSTEM, t.prompt, max_tokens=max_tokens)
            if db is not None:
                cost = (resp.input_tokens * provider.cost_per_1k_input_cad
                        + resp.output_tokens * provider.cost_per_1k_output_cad) / 1000
                gw.release_reservation(db, reservation, actual_cad=round(cost, 8))
                reservation = None
            out = _parse(getattr(resp, "text", resp))
        except Exception as exc:  # noqa: BLE001 - an error is a result, never a pass
            if db is not None and reservation is not None:
                gw.release_reservation(db, reservation)
            results.append({"task": t.key, "family": t.family, "status": ERROR,
                            "problems": [f"{type(exc).__name__}: {exc}"[:200]]})
            continue
        problems = t.check(out)
        results.append({"task": t.key, "family": t.family,
                        "status": FAIL if problems else PASS, "problems": problems})
    counts = {s: sum(1 for r in results if r["status"] == s)
              for s in (PASS, FAIL, ERROR, UNSUPPORTED)}
    return {"provider": getattr(provider, "name", "?"), "model": getattr(provider, "model", "?"),
            "results": results, "counts": counts,
            "compatible": counts[PASS] == len(results) and bool(results)}


def compare(current: dict, candidate: dict) -> dict:
    cur = {r["task"]: r["status"] for r in current["results"]}
    cand = {r["task"]: r["status"] for r in candidate["results"]}
    lost = sorted(k for k, s in cur.items() if s == PASS and cand.get(k) != PASS)
    gained = sorted(k for k, s in cand.items() if s == PASS and cur.get(k) != PASS)
    return {"swap_safe": not lost and candidate["compatible"], "lost": lost, "gained": gained}


def record(db, report: dict) -> None:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=AUDIT_ACTION, artifact=(
            f"{report.get('provider')}:{report.get('model')}")[:200], detail=report))


def latest(db) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == AUDIT_ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        return ({"at": row.at.isoformat(), **dict(row.detail or {})} if row else None)
