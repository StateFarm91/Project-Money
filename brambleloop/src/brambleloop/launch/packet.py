"""The owner's Launch-0 launch packet (F-878), generated from state, never asserted.

One document the owner reads before deciding anything about launch: the candidate commit, the
recorded suite/closure evidence, the runtime phase, and for every Launch-0 product its
certification, listing set and disclosure, search / parity / policy state, price and economics
(with basis), physical-proof state, rollback path and the open gates -- each open owner gate
with its exact action, maximum cost, minutes and consequence of waiting, taken from the
launch-readiness owner queue.

Truthfulness rules, because a packet that reads green when nothing was checked is worse than
no packet:

* every verdict is read from the database or runtime state at generation time
  (`ops.publication_authority.evidence`, `launch.readiness.assess`, `core.phase.resolve`);
* a section that could not be read is UNKNOWN, and UNKNOWN is never shown as passing;
* the overall verdict is READY only when every product's gated sections PASS, readiness
  reports ready and the phase record agrees with the environment -- otherwise BLOCKED (a
  reading failed) or UNKNOWN (something was never read).

Nothing here writes to the database, renders, enqueues, contacts a provider or calls a model.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
READY = "READY"
BLOCKED = "BLOCKED"


def _guard(fn, default=None):
    try:
        return fn(), None
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, and says why
        return default, f"{type(exc).__name__}: {str(exc)[:300]}"


def launch0_releases() -> list[dict]:
    """Every Launch-0 product as published: candidate slug, variant CIR slug and version."""
    from ..products import launch0 as l0

    out = []
    for slug in l0.LAUNCH0_SLUGS:
        for v in l0.candidate(slug).variants:
            cir = l0.cir_for(v.build)
            out.append({"candidate": slug, "slug": cir.slug, "version": cir.version})
    return out


def _stored_release(db, slug: str, version: str) -> dict:
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = None if product is None else s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id, PatternVersion.version == version))
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version)
                           .order_by(Listing.id.desc()).limit(1))
        return {"stored": pv is not None, "certified": bool(pv and pv.certified),
                "release": (pv.release_hash or "") if pv is not None else "",
                "listing": (None if listing is None else
                            {"state": listing.state, "title": listing.title,
                             "price_cad": listing.price_cad,
                             "bound_to_release": bool(pv) and listing.release_hash == (
                                 pv.release_hash or ""),
                             "on_etsy": bool(listing.etsy_listing_id)})}


def _product(db, rel: dict) -> dict:
    from ..ops import publication_authority as pa

    stored = _stored_release(db, rel["slug"], rel["version"])
    ev, err = _guard(lambda: pa.evidence(db, rel["slug"], rel["version"], stored["release"]))
    if ev is None:
        ev = {k: {"state": UNKNOWN, "why": f"evidence unreadable: {err}"}
              for k in pa.GATED_SECTIONS + ("economics",)}
        ev["summary"] = {"all_gated_sections_pass": False,
                         "not_passing": list(pa.GATED_SECTIONS),
                         "unknown": list(pa.GATED_SECTIONS), "economics_basis": UNKNOWN}
    cert = ev.get("certification") or {}
    return {**rel, "release": stored["release"] or None,
            "certified": stored["certified"], "listing": stored["listing"],
            "sections": {k: ev[k] for k in pa.GATED_SECTIONS + ("economics",)},
            "display": pa.display(ev),
            "physical_proof": cert.get("physical_proof", UNKNOWN),
            "physical_proof_source": ("the release certificate's physical_test_required / "
                                      "physical_test_passed, bound to stored PhysicalTest rows "
                                      "at certification"),
            "open_gates": [{"section": k, "state": ev[k].get("state", UNKNOWN),
                            "why": ev[k].get("why", "")}
                           for k in pa.GATED_SECTIONS if ev[k].get("state") != PASS],
            "publishable_now": bool(ev["summary"]["all_gated_sections_pass"]),
            "not_passing": ev["summary"]["not_passing"],
            "unknown": ev["summary"]["unknown"]}


def _owner_queue(db, phase: str) -> tuple[dict, str | None]:
    from .readiness import assess

    r, err = _guard(lambda: assess(db, phase=phase))
    if r is None:
        return {"ready": False, "state": UNKNOWN, "owner_actions": [], "buildable": [],
                "outstanding": [], "unknowns": []}, err
    return {
        "ready": bool(r.ready), "state": PASS if r.ready else FAIL,
        "owner_actions": [{"key": o.key, "action": o.action, "why": o.reason,
                           "max_cost_cad": o.max_cost_cad, "minutes": o.minutes,
                           "consequence_of_delay": o.consequence_of_delay,
                           "blocks": o.blocks} for o in r.owner_requests()],
        "outstanding": [{"key": q.key, "description": q.description,
                         "blocked_by": q.blocked_by} for q in r.outstanding],
        "buildable": [q.key for q in r.buildable],
        "unknowns": list(r.unknowns)[:40],
    }, None


def _spend_limits(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import SpendLimit

    with db.session() as s:
        return [{"scope": r.scope, "daily_cap_cad": r.daily_cap_cad,
                 "lifetime_cap_cad": r.lifetime_cap_cad, "spent_today_cad": r.spent_today_cad,
                 "spent_lifetime_cad": r.spent_lifetime_cad, "paused": r.paused}
                for r in s.scalars(select(SpendLimit).order_by(SpendLimit.scope))]


def _recorded_suite(repo_root: Path | None) -> dict:
    """The newest recorded full-suite and closure evidence files, quoted, never re-judged."""
    if repo_root is None:
        return {"state": UNKNOWN, "why": "no repository root given; suite evidence not read"}
    base = repo_root / "research" / "final_build"
    runs = sorted(base.glob("RUN_*_full_suite.json"), key=lambda p: p.stat().st_mtime)
    out: dict = {"state": UNKNOWN, "suite_file": None, "closure_file": None}
    if runs:
        data, err = _guard(lambda: json.loads(runs[-1].read_text()))
        out["suite_file"] = str(runs[-1].relative_to(repo_root))
        if isinstance(data, dict):
            out["suite"] = {k: data.get(k) for k in ("commit", "sha", "passed", "failed",
                                                     "errors", "total", "verdict", "at")
                            if k in data}
        else:
            out["suite_error"] = err
    closure = base / "closure_matrix.json"
    if closure.exists():
        out["closure_file"] = str(closure.relative_to(repo_root))
        data, _err = _guard(lambda: json.loads(closure.read_text()))
        if isinstance(data, dict):
            out["closure"] = {k: data.get(k) for k in ("commit", "summary", "counts", "at")
                              if k in data}
    out["why"] = ("recorded evidence quoted as found; it was produced for the commit it names, "
                  "which may not be this candidate -- re-run the suite for this SHA")
    return out


ACTIVATION_STEPS = (
    "Resolve every open owner gate listed under each product and in the owner queue.",
    "Record the phase move one step at a time via POST /api/owner/phase/transition "
    "(owner credential; evidence refs 'readiness' and 'rollback'), and set BRAMBLELOOP_PHASE "
    "on the deployment to the same value -- a mismatch runs as the more restrictive phase.",
    "For each product: POST /api/owner/publication/preview, read its evidence, then "
    "POST /api/owner/publication/approve with the previewed digest (grant expires in 24 h; "
    "any change in the bound evidence voids it).",
    "store.publish creates the Etsy draft only after re-validating phase, grant, parity, "
    "gates, payload, PDFs and images at the pre-create boundary.",
    "Activation is a separate owner grant via /api/owner/activation; store.activate is the "
    "only path that makes a listing live and incurs the listing fee.",
)


def build(db, *, sha: str, repo_root: Path | None = None, env: dict | None = None,
          now: datetime | None = None) -> dict:
    """The packet as a dict. Reads only."""
    from ..core import phase as phase_mod
    from ..ops import publication_authority as pa

    now = now or datetime.now(timezone.utc)
    phase = phase_mod.resolve(db, env)
    releases, err = _guard(launch0_releases, [])
    products = [_product(db, r) for r in releases]
    queue, queue_err = _owner_queue(db, phase["phase"])
    limits, limits_err = _guard(lambda: _spend_limits(db), [])
    # The readiness owner queue is launch-wide (account, payout, samples, fees...): every
    # open owner action blocks every product, so each product names them by key.
    for pr in products:
        pr["launch_wide_owner_actions"] = [o["key"] for o in queue["owner_actions"]]
    unknown = [p["slug"] for p in products if p["unknown"]]
    blocked = [p["slug"] for p in products if not p["publishable_now"]]
    if err or not products:
        verdict = UNKNOWN
    elif (not blocked and queue["ready"] and phase["agree"]):
        verdict = READY
    elif unknown or queue["state"] == UNKNOWN:
        verdict = UNKNOWN
    else:
        verdict = BLOCKED
    return {
        "kind": "brambleloop.launch_packet", "scope": "Launch-0",
        "generated_at": now.isoformat(), "candidate_sha": sha,
        "verdict": verdict,
        "verdict_rule": ("READY only when every product's gated sections PASS, launch "
                         "readiness is ready and the recorded phase agrees with the "
                         "environment; UNKNOWN when anything was never read"),
        "phase": {k: phase[k] for k in ("phase", "env", "recorded_phase", "transition_id",
                                        "agree", "why")},
        "products": products,
        "products_error": err,
        "products_blocked": blocked, "products_with_unknowns": unknown,
        "owner_queue": queue, "owner_queue_error": queue_err,
        "spend_limits": limits, "spend_limits_error": limits_err,
        "recorded_suite": _recorded_suite(repo_root),
        "rollback_path": dict(pa.ROLLBACK_PATH),
        "activation_steps": list(ACTIVATION_STEPS),
    }


def _cell(state) -> str:
    return "PASS" if state == PASS else str(state or UNKNOWN)


def render_markdown(p: dict) -> str:
    L = ["# Launch-0 owner launch packet", "",
         f"- Candidate SHA: `{p['candidate_sha']}`",
         f"- Generated: {p['generated_at']}",
         f"- **Verdict: {p['verdict']}** -- {p['verdict_rule']}",
         f"- Phase: effective `{p['phase']['phase']}` (env `{p['phase']['env']}`, recorded "
         f"`{p['phase']['recorded_phase']}`, agree={p['phase']['agree']})", ""]
    L += ["## Products", "",
          "| Product | Version | Certified | " + " | ".join(
              ["Cert", "Parity", "Listing set", "Disclosure", "Policy", "Search", "Rollback",
               "Economics"]) + " | Physical proof |",
          "|" + "---|" * 12]
    for pr in p["products"]:
        s = pr["sections"]
        L.append(f"| {pr['slug']} | {pr['version']} | {pr['certified']} | " + " | ".join(
            _cell(s[k]["state"]) for k in ("certification", "parity", "listing_set",
                                           "disclosure", "policy", "search", "rollback",
                                           "economics")) + f" | {pr['physical_proof']} |")
    L.append("")
    for pr in p["products"]:
        L += [f"### {pr['slug']}@{pr['version']}", "",
              f"- Release: `{pr['release'] or 'none'}`; listing: "
              f"{'none drafted' if not pr['listing'] else pr['listing']['state']}",
              f"- Publishable now: {pr['publishable_now']}; not passing: "
              f"{', '.join(pr['not_passing']) or 'none'}"]
        par = pr["sections"]["parity"]
        if par.get("unjudged"):
            L.append(f"- Parity unjudged dimensions: {', '.join(par['unjudged'])}")
        eco = pr["sections"]["economics"]
        if eco.get("price_cad") is not None:
            L.append(f"- Price CA${eco['price_cad']} (basis {eco.get('price_basis')}); fees "
                     f"CA${eco.get('fees_cad')} and net CA${eco.get('net_per_sale_cad')} "
                     f"({eco.get('fees_basis')}); sales volume {eco.get('sales_volume_basis')}")
        else:
            L.append(f"- Economics: {eco['state']} -- {eco.get('why')}")
        L.append(f"- Physical proof: {pr['physical_proof']} (from "
                 f"{pr['physical_proof_source']})")
        L.append("- Evidence:")
        for row in pr["display"]:
            L.append(f"  - {row['section']}: {row['state']} -- {row['why']}")
        L.append("- Open gates: " + ("; ".join(f"{g['section']} ({g['state']})"
                                              for g in pr["open_gates"]) or "none"))
        if pr.get("launch_wide_owner_actions"):
            L.append("- Also blocked by launch-wide owner actions: "
                     + ", ".join(pr["launch_wide_owner_actions"]))
        L.append("")
    q = p["owner_queue"]
    L += ["## Open owner gates (from the launch-readiness owner queue)", "",
          f"Readiness: {q['state']}" + (f" (error: {p['owner_queue_error']})"
                                         if p.get("owner_queue_error") else ""), ""]
    if q["owner_actions"]:
        L += ["| Action | Why | Max cost CAD | Minutes | Consequence of waiting |",
              "|---|---|---|---|---|"]
        for o in q["owner_actions"]:
            L.append(f"| {o['action']} | {o['why']} | {o['max_cost_cad']} | {o['minutes']} | "
                     f"{o['consequence_of_delay']} |")
    else:
        L.append("No owner action is listed by the readiness queue.")
    L += ["", "## Spend limits", ""]
    L += ([f"- {x['scope']}: daily cap CA${x['daily_cap_cad']}, lifetime cap "
           f"CA${x['lifetime_cap_cad']}, spent CA${x['spent_lifetime_cad']}, paused={x['paused']}"
           for x in p["spend_limits"]] or ["- No spend limit rows are recorded (UNKNOWN)."])
    rs = p["recorded_suite"]
    L += ["", "## Recorded suite / closure evidence", "",
          f"- State: {rs.get('state')} -- {rs.get('why')}",
          f"- Suite file: {rs.get('suite_file')}; closure file: {rs.get('closure_file')}"]
    L += ["", "## Rollback path", ""] + [f"- **{k}**: {v}" for k, v in
                                          p["rollback_path"].items()]
    L += ["", "## Activation steps", ""] + [f"{i}. {s}" for i, s in
                                             enumerate(p["activation_steps"], 1)]
    return "\n".join(L) + "\n"


def write(packet: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(packet["generated_at"]).strftime("%Y%m%dT%H%M%SZ")
    stem = f"launch_packet_{str(packet['candidate_sha'])[:12]}_{stamp}"
    j, m = out_dir / f"{stem}.json", out_dir / f"{stem}.md"
    j.write_text(json.dumps(packet, indent=2, sort_keys=True, default=str) + "\n")
    m.write_text(render_markdown(packet))
    return j, m
