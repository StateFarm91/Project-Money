"""W4-OWNERHOME: the owner's six-block overview for the Command Center Home.

The owner directive: the owner must not scroll hundreds of records. Home leads with six
compact blocks, each a one-line headline, at most five rows, and an expandable evidence list:

1. ``working``     -- capabilities verified live (executor gates that are open) and the last
                      production self-check (`verify.completed` audit row), with their times.
2. ``blocked``     -- root causes: the finish-line board's (W4-BOARD, rows held per cause)
                      first, then closed gates ranked by how many requirements wait on each,
                      plus department blockers grouped by gate.
3. ``decisions``   -- the existing ranked owner queue. The server only counts it; the client
                      ranks it with `_decisions.js` (one ranking, not two).
4. ``accomplished``-- the last 24 h of finished jobs that did useful work, by kind, each with
                      its latest result text. Jobs that did no work are counted, not shown.
5. ``ready``       -- products: certified release, pattern PDF provenance, listing images and
                      the publication gate verdict, read from rows that already exist.
6. ``money``       -- revenue / profit / recorded spend exactly as the Money tab reads them
                      (UNKNOWN stays UNKNOWN, never CA$0.00), and agent activity measured as
                      useful outcomes in 24 h.

Every block is read independently under `guard`: one unreadable source makes that block
UNKNOWN with the reason, never the page. Nothing here writes, and nothing is fabricated: a
value this module cannot read is ``None`` with a reason.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .providers import envelope, now_iso, unknown

TOP = 5
EVIDENCE_MAX = 30


def _iso(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return str(v)


def _block(key: str, title: str, env: dict, headline: str, *, href: str,
           evidence: list | None = None, **extra) -> dict:
    out = dict(env)
    out.update({"key": key, "title": title, "headline": headline, "href": href,
                "items": list(env.get("items") or [])[:TOP],
                "evidence": list(evidence if evidence is not None else
                                 env.get("items") or [])[:EVIDENCE_MAX]})
    out.update(extra)
    return out


def _unknown_block(key: str, title: str, href: str, why: str, sources: list) -> dict:
    env = unknown(why, f"overview.{key}", sources)
    return _block(key, title, env, f"Unknown: {why}", href=href, evidence=[])


# ---- 1 + 2: gates ---------------------------------------------------------------------------

def _gates(db) -> dict:
    from ...build2 import executor

    return executor.gate_states(db, dict(os.environ))


def _last_verify(db) -> dict | None:
    from ...core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "verify.completed")
                       .order_by(AuditLog.id.desc()).limit(1))
        if row is None:
            return None
        d = row.detail or {}
        return {"at": _iso(row.at), "ok": d.get("ok"), "failing": list(d.get("failing") or []),
                "commit": d.get("commit"), "source": f"audit_log:{row.id}"}


def working(db, gates: dict | None = None) -> dict:
    title, href = "What's working", "#/company"

    def read():
        gs = gates if gates is not None else _gates(db)
        checked_at = now_iso()
        rows = [{"title": g["what"], "detail": g["how_it_is_checked"], "verified_at": checked_at,
                 "verified_basis": "checked live when this page was read",
                 "status": "OK", "source": f"build2.executor.gate:{k}"}
                for k, g in sorted(gs.items()) if g.get("open")]
        last = _last_verify(db)
        evidence = list(rows)
        if last is not None:
            evidence.insert(0, {
                "title": "Production self-check (/api/verify)",
                "detail": ("all checks passed" if last["ok"] else
                           "failing: " + ", ".join(last["failing"]) if last["failing"]
                           else "result not recorded"),
                "verified_at": last["at"], "verified_basis": "last recorded run",
                "status": "OK" if last["ok"] else "DEGRADED", "source": last["source"]})
        if not evidence:
            return _block("working", title, envelope(
                "UNKNOWN", [], ["build2.executor.gate_states", "audit_log:verify.completed"],
                basis="unknown", provider="overview.working",
                reason="no capability gate is open and no self-check is recorded"),
                "Unknown: nothing is verified yet", href=href, evidence=[])
        head = f"{len(rows)} of {len(gs)} capabilities verified live"
        if last is not None:
            head += (f"; last self-check {'passed' if last['ok'] else 'had failures'}")
        env = envelope("OK" if rows else "DEGRADED", evidence,
                       ["build2.executor.gate_states", "audit_log:verify.completed"],
                       provider="overview.working", as_of=checked_at,
                       counts={"verified": len(rows), "capabilities": len(gs)},
                       last_self_check=last)
        return _block("working", title, env, head, href=href, evidence=evidence)

    return _safe("working", title, href, read, ["build2.executor.gate_states"])


def _safe(key, title, href, fn, sources) -> dict:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - one unreadable block is UNKNOWN, never the page
        return _unknown_block(key, title, href,
                              f"could not be read: {type(exc).__name__}: {str(exc)[:160]}",
                              sources)


def _board():
    from .company import finish_line

    return finish_line()


def blocked(db, gates: dict | None = None, departments: dict | None = None,
            board_reader=_board) -> dict:
    title, href = "What's blocked", "#/company"

    def read():
        gs = gates if gates is not None else _gates(db)
        causes = []
        for k, g in gs.items():
            if g.get("open"):
                continue
            waiting = len(g.get("requirement_ids") or [])
            causes.append({"title": g["what"], "gate": k, "count": waiting,
                           "detail": f"{waiting} requirement(s) wait on this; checked by: "
                                     f"{g['how_it_is_checked']}",
                           "status": "BLOCKED", "source": f"build2.executor.gate:{k}"})
        # Department blockers, grouped by the gate (or kind) that names them.
        dept_counts: dict[str, dict] = {}
        for d in (departments or {}).get("items") or []:
            for b in d.get("blockers") or []:
                key = str(b.get("gate") or b.get("kind") or "unnamed")
                row = dept_counts.setdefault(key, {
                    "title": f"Departments blocked by {key}", "gate": key, "count": 0,
                    "departments": [], "status": "BLOCKED",
                    "source": "autonomy.status.summary"})
                row["count"] += 1
                row["departments"].append(d.get("name") or d.get("department"))
        for row in dept_counts.values():
            row["detail"] = "departments: " + ", ".join(sorted(set(map(str, row["departments"]))))
        gate_ranked = sorted(causes + list(dept_counts.values()),
                             key=lambda r: (-int(r["count"]), r["title"]))
        for r in gate_ranked:
            r["unit"] = "requirements" if r in causes else "departments"
        waiting_total = sum(c["count"] for c in causes)
        # W4-BOARD: the finish-line board's root causes (rows of Build 2 + Final Master each
        # cause holds) lead when the board is readable; the live gates follow. Two units, so
        # two ranked lists, never one list that compares rows with requirements.
        try:
            board = board_reader() if board_reader is not None else None
        except Exception as exc:  # noqa: BLE001 - the gates still answer
            board = {"status": "UNKNOWN", "reason": f"board unreadable: {type(exc).__name__}"}
        board_rows = []
        if isinstance(board, dict) and board.get("status") != "UNKNOWN":
            for r in board.get("items") or []:
                n = r.get("rows")
                board_rows.append({
                    "title": r.get("title") or "unnamed root cause",
                    "count": n if isinstance(n, int) else None, "unit": "rows",
                    "detail": "; ".join(x for x in (
                        f"launch-critical: {r['fm_launch_critical']}"
                        if r.get("fm_launch_critical") is not None else None,
                        f"Build 2: {r['build2']}" if r.get("build2") is not None else None,
                        f"owner action: {r['owner_action']}" if r.get("owner_action") else None)
                        if x) or None,
                    "at": board.get("as_of"), "status": "BLOCKED", "source": r.get("source")})
            board_rows.sort(key=lambda r: (-(r["count"] if isinstance(r["count"], int) else -1),
                                           r["title"]))
        ranked = board_rows + gate_ranked
        env = envelope("BLOCKED" if ranked else "OK", ranked,
                       ["company.finish_line (COMPLETION_BOARD_FINAL)",
                        "build2.executor.gate_states", "autonomy.status.summary"],
                       provider="overview.blocked", as_of=now_iso(),
                       counts={"root_causes": len(ranked), "board_root_causes": len(board_rows),
                               "closed_gates": len(causes),
                               "requirements_waiting": waiting_total},
                       board=({"status": board.get("status"), "as_of": board.get("as_of"),
                               "production_commit": board.get("production_commit")}
                              if board_rows else
                              {"status": "UNKNOWN", "why": (board or {}).get("reason")
                               or "finish-line board not readable; gates only"}))
        gates_head = f"{len(causes)} closed gate(s) hold {waiting_total} requirement(s)"
        if board_rows:
            top = board_rows[0]
            head = (f"Top root cause: {top['title']} ({top['count'] if top['count'] is not None else 'Unknown'} "
                    f"rows); {gates_head}")
        else:
            head = gates_head if ranked else "No closed gate and no blocked department"
        return _block("blocked", title, env, head, href=href, evidence=ranked)

    return _safe("blocked", title, href, read,
                 ["build2.executor.gate_states", "autonomy.status.summary"])


# ---- 3: decisions (counted here, ranked by the client) ------------------------------------

def decisions(box: dict) -> dict:
    title, href = "Decisions for you", "#/approvals"
    if not isinstance(box, dict) or box.get("status") == "UNKNOWN":
        return _unknown_block("decisions", title, href,
                              (box or {}).get("reason") or "owner queue unreadable",
                              ["build2.executor.approval_inbox"])
    n = box.get("open") if isinstance(box.get("open"), int) else None
    env = envelope(box.get("status") or "OK", [], ["build2.executor.approval_inbox"],
                   provider="overview.decisions", as_of=now_iso(), open=n,
                   note="ranked on the device by _decisions.rankDecisions (same as Approvals)")
    head = ("Unknown: open decisions not counted" if n is None else
            f"{n} decision(s) open" if n else "No decision is waiting on you")
    return _block("decisions", title, env, head, href=href, evidence=[])


# ---- 4: accomplished --------------------------------------------------------------------

def _result_text(outputs) -> str | None:
    from .company import _result_text as rt

    return rt(outputs)


def _done_24h(db, now: datetime):
    from ...core.models import Job, JobStatus

    since = now - timedelta(hours=24)
    with db.session() as s:
        return list(s.execute(select(Job.id, Job.agent, Job.job_type, Job.outputs,
                                     Job.finished_at)
                              .where(Job.status == JobStatus.DONE, Job.finished_at >= since)
                              .order_by(Job.finished_at.desc(), Job.id.desc())
                              .limit(2000)).all())


def accomplished(db, done=None, *, now: datetime | None = None) -> dict:
    title, href = "What the company accomplished (24 h)", "#/timeline"

    def read():
        from ...autonomy.kpis import did_no_work

        t = now or datetime.now(timezone.utc)
        rows = done if done is not None else _done_24h(db, t)
        kinds: dict[str, dict] = {}
        idle = 0
        for r in rows:
            if did_no_work(r.outputs, r.job_type):
                idle += 1
                continue
            k = kinds.setdefault(r.job_type, {"title": r.job_type, "count": 0, "agents": set(),
                                              "detail": None, "at": None, "source": None})
            k["count"] += 1
            k["agents"].add(r.agent)
            if k["at"] is None:  # rows are newest first
                k["detail"] = _result_text(r.outputs)
                k["at"] = _iso(r.finished_at)
                k["source"] = f"jobs:{r.id}"
        items = sorted(({**v, "agents": sorted(v["agents"]), "status": "OK"}
                        for v in kinds.values()), key=lambda v: (-v["count"], v["title"]))
        useful = sum(i["count"] for i in items)
        env = envelope("OK", items, ["jobs (done, last 24 h)", "autonomy.kpis.did_no_work"],
                       provider="overview.accomplished", as_of=_iso(t),
                       counts={"useful": useful, "kinds": len(items), "no_work": idle,
                               "finished": len(rows)},
                       truncated_at=2000 if len(rows) >= 2000 else None)
        head = (f"{useful} useful outcome(s) across {len(items)} kind(s) of work; "
                f"{idle} finished job(s) did no work" if rows else
                "No job finished in the last 24 h")
        return _block("accomplished", title, env, head, href=href, evidence=items)

    return _safe("accomplished", title, href, read, ["jobs"])


# ---- 5: ready to sell ---------------------------------------------------------------------

def _pdf_and_images(db, slugs: list[str]) -> dict:
    from ...core.models import ArtefactProvenance

    out: dict[str, dict] = {s: {} for s in slugs}
    if not slugs:
        return out
    with db.session() as s:
        for row in s.scalars(select(ArtefactProvenance)
                             .where(ArtefactProvenance.product_slug.in_(slugs),
                                    ArtefactProvenance.artefact_class.in_(
                                        ("pdf", "visual_truth")))
                             .order_by(ArtefactProvenance.id.desc())):
            slot = out[row.product_slug].setdefault(row.artefact_class, {
                "built_at": _iso(row.built_at), "key": row.artefact_key,
                "source": f"artefact_provenance:{row.id}"})
            del slot  # first (newest) row per class wins
    return out


def _section_state(card: dict, label: str) -> str | None:
    for e in card.get("evidence") or []:
        if str(e.get("label") or e.get("section") or "") == label:
            return str(e.get("state") or "UNKNOWN")
    return None


def ready(db, box: dict | None = None, products: dict | None = None) -> dict:
    title, href = "Ready to sell", "#/store"

    def read():
        from . import readers

        prods = products if products is not None else readers.products(db)
        if prods.get("status") != "OK":
            return _unknown_block("ready", title, href,
                                  prods.get("reason") or "products unreadable",
                                  prods.get("sources") or ["products"])
        items = prods.get("items") or []
        art = _pdf_and_images(db, [p["slug"] for p in items])
        cards = {}
        for c in (box or {}).get("cards") or []:
            if c.get("kind") == "PUBLICATION":
                slug = str(c.get("card_id", "")).split(":", 1)[-1].split("@", 1)[0]
                cards.setdefault(slug, c)
        rows = []
        for p in items:
            a = art.get(p["slug"]) or {}
            card = cards.get(p["slug"])
            images = _section_state(card, "listing_set") if card else None
            sellable = bool(card and card.get("executable"))
            rows.append({
                "title": p.get("title") or p["slug"], "slug": p["slug"],
                "certified": bool(p.get("certified")), "version": p.get("version"),
                "pdf": ({"state": "BUILT", **a["pdf"]} if "pdf" in a else
                        {"state": "UNKNOWN", "why": "no pdf provenance row for this product"}),
                "images": ({"state": images, "basis": "publication gate listing_set"}
                           if images else
                           {"state": "RECORDED", "basis": "visual_truth provenance",
                            **a["visual_truth"]} if "visual_truth" in a else
                           {"state": "UNKNOWN", "why": "no listing-set verdict or imagery "
                                                       "provenance for this product"}),
                "listing_state": p.get("listing_state"), "on_etsy": bool(p.get("on_etsy")),
                "publication": (("READY" if sellable else "NOT READY") if card else
                                "NO CANDIDATE"),
                "why": (card.get("recommendation") if card else
                        "no certified release with a stored listing" if not p.get("certified")
                        else "certified, but no stored listing for this release"),
                "status": "OK" if sellable else "BLOCKED",
                "source": ", ".join(p.get("sources") or [])})
        rows.sort(key=lambda r: (r["status"] != "OK", not r["certified"],
                                 r["pdf"]["state"] != "BUILT", r["title"]))
        n_ready = sum(1 for r in rows if r["status"] == "OK")
        n_cert = sum(1 for r in rows if r["certified"])
        env = envelope("OK" if n_ready else "BLOCKED", rows,
                       ["products", "pattern_versions", "listings", "artefact_provenance",
                        "ops.publication_authority.evidence"],
                       provider="overview.ready", as_of=now_iso(),
                       counts={"products": len(rows), "certified": n_cert, "ready": n_ready,
                               "on_etsy": sum(1 for r in rows if r["on_etsy"])},
                       note="the Store tab owns the full catalogue; this is the summary")
        head = (f"{n_ready} of {len(rows)} product(s) ready to sell; {n_cert} certified; "
                f"{env['counts']['on_etsy']} on Etsy")
        return _block("ready", title, env, head, href=href, evidence=rows)

    return _safe("ready", title, href, read, ["products"])


# ---- 6: money + agent activity -------------------------------------------------------------

def _spend_24h(db, now: datetime) -> dict:
    from ...core.models import CostEntry
    from ...finance.listing_costs import cost_basis

    since = now - timedelta(hours=24)
    total, by_basis, n = 0.0, {}, 0
    with db.session() as s:
        for c in s.scalars(select(CostEntry).where(CostEntry.at >= since)):
            amt = float(c.amount_cad or 0.0)
            total += amt
            n += 1
            b = cost_basis(c) or "unknown"
            by_basis[b] = round(by_basis.get(b, 0.0) + amt, 6)
    # Zero rows is a measured zero of *recorded* spend: the rows are this system's own ledger.
    return {"value_cad": round(total, 4), "state": "RECORDED", "rows": n,
            "by_basis_cad": by_basis,
            "display": f"CA${total:,.2f} (recorded, {n} row(s))",
            "why": "cost rows this system wrote in the last 24 h; not a provider invoice"}


def money(db, m: dict | None = None, done=None, *, now: datetime | None = None) -> dict:
    title, href = "Money and agent activity", "#/money"

    def read():
        from ...autonomy.kpis import did_no_work
        from . import tabs

        t = now or datetime.now(timezone.utc)
        ms = m if m is not None else tabs.money_section(db)

        def line(name, v):
            v = v if isinstance(v, dict) else {}
            val = v.get("value_cad")
            return {"title": name, "value_cad": val if isinstance(val, (int, float)) else None,
                    "state": v.get("state") or "UNKNOWN",
                    "display": v.get("display") or (v.get("state") or "UNKNOWN"),
                    "detail": v.get("why") or None,
                    "status": "OK" if isinstance(val, (int, float)) else "UNKNOWN"}

        lines = [line("Revenue", ms.get("revenue")), line("Profit", ms.get("profit")),
                 line("Recorded spend (all time)", ms.get("recorded_spend"))]
        try:
            lines.append(line("Recorded spend (24 h)", _spend_24h(db, t)))
        except Exception as exc:  # noqa: BLE001
            lines.append(line("Recorded spend (24 h)", {
                "state": "UNKNOWN", "why": f"unreadable: {type(exc).__name__}"}))
        rows = done if done is not None else _done_24h(db, t)
        per: dict[str, dict] = {}
        for r in rows:
            a = per.setdefault(r.agent, {"title": r.agent, "useful_24h": 0, "no_work_24h": 0,
                                         "last_result": None, "at": None, "source": None})
            if did_no_work(r.outputs, r.job_type):
                a["no_work_24h"] += 1
            else:
                a["useful_24h"] += 1
                if a["at"] is None:
                    a["last_result"] = _result_text(r.outputs)
                    a["at"] = _iso(r.finished_at)
                    a["source"] = f"jobs:{r.id}"
        agents = sorted(per.values(), key=lambda a: (-a["useful_24h"], a["title"]))
        for a in agents:
            a["detail"] = (f"{a['useful_24h']} useful, {a['no_work_24h']} with no work"
                           + (f"; latest: {a['last_result']}" if a["last_result"] else ""))
            a["status"] = "OK" if a["useful_24h"] else "DEGRADED"
        unknown_lines = [ln["title"] for ln in lines if ln["status"] == "UNKNOWN"]
        rev = lines[0]
        env = envelope("UNKNOWN" if rev["status"] == "UNKNOWN" else "OK", lines,
                       ["finance.accounting.dashboard", "ledger", "cost_entries", "jobs"],
                       basis="unknown" if unknown_lines else "measured",
                       provider="overview.money", as_of=_iso(t),
                       reason=(", ".join(unknown_lines) + " UNKNOWN: "
                               + str(rev.get("detail") or ms.get("reason") or "not measured")
                               if unknown_lines else None),
                       agents=agents[:EVIDENCE_MAX],
                       agents_counts={"active_24h": sum(1 for a in agents if a["useful_24h"]),
                                      "ran_24h": len(agents)})
        head = (f"Revenue {rev['display']}; spend 24 h {lines[3]['display']}; "
                f"{env['agents_counts']['active_24h']} agent(s) produced useful results")
        return _block("money", title, env, head, href=href, evidence=lines + agents)

    return _safe("money", title, href, read,
                 ["finance.accounting.dashboard", "cost_entries", "jobs"])


# ---- the six together -----------------------------------------------------------------------

ORDER = ("working", "blocked", "decisions", "accomplished", "ready", "money")


def overview(db, *, box: dict | None = None, m: dict | None = None,
             products: dict | None = None, departments: dict | None = None,
             now: datetime | None = None) -> dict:
    """All six blocks. Inputs already read by `tabs.home` are passed in, not re-read."""
    t = now or datetime.now(timezone.utc)
    try:
        gates = _gates(db)
    except Exception:  # noqa: BLE001 - each gate block reports its own UNKNOWN
        gates = None
    try:
        done = _done_24h(db, t)
    except Exception:  # noqa: BLE001
        done = None
    blocks = {
        "working": working(db, gates) if gates is not None else _unknown_block(
            "working", "What's working", "#/company", "capability gates unreadable",
            ["build2.executor.gate_states"]),
        "blocked": blocked(db, gates, departments) if gates is not None else _unknown_block(
            "blocked", "What's blocked", "#/company", "capability gates unreadable",
            ["build2.executor.gate_states"]),
        "decisions": decisions(box if box is not None else {}),
        "accomplished": accomplished(db, done, now=t) if done is not None else _unknown_block(
            "accomplished", "What the company accomplished (24 h)", "#/timeline",
            "jobs unreadable", ["jobs"]),
        "ready": ready(db, box, products),
        "money": money(db, m, done, now=t) if done is not None else _unknown_block(
            "money", "Money and agent activity", "#/money", "jobs unreadable",
            ["cost_entries", "jobs"]),
    }
    return {"status": "OK", "as_of": _iso(t), "basis": "measured", "items": [],
            "sources": ["overview"], "provider": "command_center.overview",
            "order": list(ORDER), "blocks": blocks}
