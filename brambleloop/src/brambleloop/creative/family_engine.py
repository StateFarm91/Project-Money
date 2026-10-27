"""Product Family Engine over the CERTIFIED catalogue (W4-AGENTS product-engine batch).

`creative.family.family_test` (#111) answers, before engineering, whether one concept *can*
seed a family. Nothing answered the catalogue-level questions the requirements ask once
products exist:

* Master Plan s33: "at least one bundle-ready family" in the launch portfolio;
* F-359 / #111: families "where genuine customer value exists, while preventing low-value
  catalogue duplication" -- a member that differs from a sibling only by colour is a recolour
  with a collection name on it (F-791: "merely changing colour ... is not sufficient");
* Master Plan s5 Winner Amplification: "turns proven demand into matching products, bundles,
  sizes, colourways" -- from PROVEN demand, so it waits on real orders and says UNMEASURED.

`family_report(db)` is deterministic and reads only our own rows (certified pattern versions,
the radar pool's declared families, orders). It writes nothing; the job stores one reading.
It never creates a product: a next member is a radar-pool seed that still has to pass the
ordinary funnel (radar.score -> preengineering -> cir.draft -> compile -> certify).
"""
from __future__ import annotations

import hashlib
import json

UNMEASURED = "UNMEASURED"
# Winner Amplification needs proven demand. Five orders for a family is this module's own
# floor (no requirement states a number); below it amplification is UNMEASURED, never "no".
AMPLIFY_MIN_ORDERS = 5


def structure_fingerprint(cir_json: dict) -> str:
    """The design's structure with colour removed: two members with the same fingerprint are
    the same pattern in different colours (a recolour, not a sibling)."""
    comps = []
    for c in cir_json.get("components") or []:
        rows = [{k: v for k, v in (r or {}).items() if k not in ("color", "colour")}
                for r in c.get("rows") or []]
        comps.append({k: v for k, v in c.items() if k not in ("rows", "name")} | {"rows": rows})
    body = {"construction": cir_json.get("construction"), "components": comps}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()
                          ).hexdigest()[:16]


def family_of(slug: str) -> tuple[str | None, str]:
    """(family key, source) for a certified CIR slug, from the radar pool's declared family."""
    from ..products import launch0
    from ..radar.opportunity import POOL

    by = {p.slug: p for p in POOL}
    concept = launch0.radar_concept_for(slug) or slug
    seed = by.get(concept) or by.get(slug)
    if seed is not None and seed.family:
        return seed.family, f"radar.opportunity.POOL[{seed.slug}].family"
    return None, "no declared family"


def _certified(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    latest: dict[str, dict] = {}
    with db.session() as s:
        for slug, version, cir_json in s.execute(
                select(Product.slug, PatternVersion.version, PatternVersion.cir_json)
                .join(PatternVersion, PatternVersion.product_id == Product.id)
                .where(PatternVersion.certified == True)  # noqa: E712
                .order_by(PatternVersion.id)).all():
            latest[slug] = {"slug": slug, "version": version, "cir": cir_json or {}}
    return list(latest.values())


def _orders_by_slug(db) -> dict[str, int]:
    from sqlalchemy import func, select

    from ..core.models import Order

    with db.session() as s:
        return {slug: int(n) for slug, n in s.execute(
            select(Order.product_slug, func.count()).group_by(Order.product_slug)).all()}


def family_report(db) -> dict:
    from ..radar.opportunity import POOL

    certified = _certified(db)
    orders = _orders_by_slug(db)
    fams: dict[str, dict] = {}
    singles: list[str] = []
    for r in certified:
        fam, source = family_of(r["slug"])
        if fam is None:
            singles.append(r["slug"])
            continue
        f = fams.setdefault(fam, {"family": fam, "source": source, "members": [],
                                  "structures": {}})
        fp = structure_fingerprint(r["cir"])
        f["members"].append({"slug": r["slug"], "version": r["version"], "structure": fp,
                             "orders": orders.get(r["slug"], 0)})
        f["structures"].setdefault(fp, []).append(r["slug"])
    certified_slugs = {r["slug"] for r in certified}
    out = []
    for key, f in sorted(fams.items()):
        recolours = [sorted(v) for v in f["structures"].values() if len(v) > 1]
        distinct = len(f["structures"])
        n_orders = sum(m["orders"] for m in f["members"])
        next_members = sorted(
            ({"seed": p.slug, "category": p.category, "whitespace": p.whitespace,
              "route": "radar.score -> preengineering -> cir.draft (the ordinary funnel)"}
             for p in POOL if p.family == key and not p.is_bundle
             and p.slug not in certified_slugs),
            key=lambda x: -x["whitespace"])
        out.append({
            "family": key, "source": f["source"], "members": f["members"],
            "distinct_designs": distinct,
            # A bundle is derived, never asserted: two distinct certified designs (#111).
            "bundle_ready": distinct >= 2,
            "recolour_duplicates": recolours,
            "next_members": next_members[:5],
            "orders": n_orders,
            "amplification": (UNMEASURED if n_orders < AMPLIFY_MIN_ORDERS else {
                "proposal": "amplify the family through the funnel (matching member, bundle, "
                            "size or colourway), proven by its orders",
                "orders": n_orders}),
        })
    return {"families": out, "single_products": sorted(singles),
            "certified": len(certified),
            "portfolio_has_bundle_ready_family": any(f["bundle_ready"] for f in out),
            "recolour_duplicates": [d for f in out for d in f["recolour_duplicates"]],
            "amplify_min_orders": AMPLIFY_MIN_ORDERS, "writes": 0}


# ---- W4-INTELREC G5: Winner Amplification delegated, and its follow-ons measured -----------

AMPLIFY_PREFIX = "creative:amplify:"
AMPLIFY_MAX_ATTEMPTS = 2
# Review 720b291 N-2: a promoted member is not re-scored while its engineering outcome is
# pending; one that has not certified within this window counts as a failed attempt.
AMPLIFY_PROMOTION_DAYS = 30
# N-2/N-3: a repeat measurement or a needs-original-design decision is parked this long.
AMPLIFY_PARK_DAYS = 7


def _amp_state(db, family: str) -> dict:
    from ..autonomy import memory

    rec = memory.get(db, AMPLIFY_PREFIX + family)
    return dict((rec or {}).get("body") or {})


def amplify(db, rep: dict, *, enqueue, today=None) -> dict:
    """For every family whose orders prove demand: delegate one original follow-on through
    the ordinary funnel, and measure the follow-ons' orders against the members at decision.

    * a declared next member exists -> `radar.score` for it (steering, evidence discount,
      lessons, the pre-engineering gate, then cir.draft) -- never a recolour: the funnel's
      novelty floor refuses one;
    * none -> recorded `needs_original_design` and surfaced; no job. An original design is
      paid creative work and this handler is CA$0 delegable work (review M-2, G14);
    * one open attempt per family. An attempt is judged by what radar.score produced
      (`watchlist.score_outcome`): promoted -> progressed; scored and not promoted -> a
      failed attempt; refused/dead -> not an attempt (review L-5). After AMPLIFY_MAX_ATTEMPTS
      failed attempts the family is held (no endless repetition). A promoted member is not
      re-scored while it waits for certification (N-2); an identical re-score is a repeat
      measurement, not a second attempt (N-3);
    * the follow-on must be an adjacent experiment (`commerce.replication.check_proposal`,
      enforced by `adjacency`): a clone of the winner, or one holding none of the #22
      study's candidate causes, is parked, not queued (review N-8). `amplify_holds` still
      travels with the radar.score job for the record;
    * follow-on orders are orders of members certified AFTER the decision -- measured, never
      inferred. Nothing here prices, publishes or spends.
    """
    from datetime import date, datetime, timedelta, timezone

    from ..intel.watchlist import score_outcome

    today = today or datetime.now(timezone.utc).date()
    decided = []
    for f in rep.get("families") or []:
        amp = f.get("amplification")
        st = _amp_state(db, f["family"])
        members_now = {m["slug"]: m["orders"] for m in f["members"]}
        if st.get("members_at_decision") is not None:
            follow = {s: n for s, n in members_now.items()
                      if s not in st["members_at_decision"]}
            st["follow_on"] = {"members": sorted(follow), "orders": sum(follow.values()),
                               "measured_on": today.isoformat()}
        if not isinstance(amp, dict):
            continue                                  # UNMEASURED: below the order floor
        job_id = st.get("job_id")
        if job_id:
            res = score_outcome(db, [job_id], now=datetime.now(timezone.utc),
                                settle=timedelta(0))
            if res["outcome"] == "wait":
                _save_amp(db, f["family"], st)
                continue
            st["last_outcome"] = res["outcome"]
            sig = res.get("signature")
            if res["outcome"] == "progressed":
                st["promoted"] = {"seed": res["promoted"][0]["slug"], "on": today.isoformat()}
            elif res["outcome"] == "failed" and not (st.get("follow_on") or {}).get("members"):
                if sig is not None and sig == st.get("last_signature"):
                    st["last_outcome"] = "repeat_measurement"
                    st["parked_until"] = (today + timedelta(days=AMPLIFY_PARK_DAYS)).isoformat()
                else:
                    st["failed_attempts"] = int(st.get("failed_attempts") or 0) + 1
                    st["last_signature"] = sig
            st["job_id"] = None
        pr = st.get("promoted")
        if pr:
            if pr.get("seed") in members_now:
                st["promoted"] = None                     # certified: measured as a follow-on
            elif today - date.fromisoformat(pr["on"]) >= timedelta(days=AMPLIFY_PROMOTION_DAYS):
                st["failed_attempts"] = int(st.get("failed_attempts") or 0) + 1
                st["promoted"] = None
                st["last_outcome"] = (f"promoted {pr.get('seed')} did not certify within "
                                      f"{AMPLIFY_PROMOTION_DAYS} days")
            else:
                _save_amp(db, f["family"], st)            # engineering outcome pending
                continue
        if st.get("parked_until") and today < date.fromisoformat(st["parked_until"]):
            _save_amp(db, f["family"], st)
            continue
        if int(st.get("failed_attempts") or 0) >= AMPLIFY_MAX_ATTEMPTS:
            st["held"] = (f"{st['failed_attempts']} follow-on attempts added no certified "
                          f"member; held until new evidence")
            _save_amp(db, f["family"], st)
            continue
        attempt = int(st.get("attempts") or 0) + 1
        # #22: before more capacity goes to the family, ask WHY its best seller sells.
        # N-8: the study's window starts once per family and is kept, never reset per attempt.
        st.setdefault("study_starts", today.isoformat())
        st["investigation"] = investigate(db, f, today=date.fromisoformat(st["study_starts"]))
        nxt = (f.get("next_members") or [None])[0]
        adj = adjacency({**st["investigation"], "winner": st["investigation"].get("winner")
                         or (sorted(f["members"], key=lambda m: -m["orders"]) or [{}])[0]
                         .get("slug")}, nxt["seed"]) if nxt is not None else None
        st["adjacency"] = adj
        if adj is not None and adj.get("adjacent") is False:
            st.update(not_adjacent=today.isoformat(),
                      parked_until=(today + timedelta(days=AMPLIFY_PARK_DAYS)).isoformat(),
                      how=f"{nxt['seed']} is not an adjacent experiment: "
                          f"{'; '.join(adj['reasons'])[:300]}")
            _save_amp(db, f["family"], st)
            decided.append({"family": f["family"], "job_id": None,
                            "decision": "not_adjacent", "reasons": adj["reasons"]})
            continue
        if nxt is not None:
            job = enqueue("market_radar", "radar.score",
                          {"slug": nxt["seed"], "amplify_family": f["family"],
                           "amplify_holds": _holds(st["investigation"])},
                          idempotency_key=f"amplify:{f['family']}:{nxt['seed']}:{attempt}")
            how = f"next declared member {nxt['seed']} through the ordinary funnel"
        else:
            st.update(needs_original_design=today.isoformat(),
                      parked_until=(today + timedelta(days=AMPLIFY_PARK_DAYS)).isoformat(),
                      how=("no declared member left: an original follow-on design is paid "
                           "creative work outside this CA$0 handler (G14, proposed)"))
            _save_amp(db, f["family"], st)
            decided.append({"family": f["family"], "job_id": None,
                            "decision": "needs_original_design"})
            continue
        if job is None:
            _save_amp(db, f["family"], st)
            continue
        st.update(attempts=attempt, job_id=job.id, job_type=job.job_type, how=how,
                  decided_on=today.isoformat(), orders_at_decision=f["orders"],
                  members_at_decision=sorted(members_now))
        _save_amp(db, f["family"], st)
        decided.append({"family": f["family"], "job_id": job.id, "how": how})
    return {"decisions": decided}


def _holds(investigation: dict) -> list[str]:
    """The candidate causes a follow-on should hold (and change the rest), or none."""
    return [r["dimension"] for r in (investigation.get("explanations") or [])][:3]


def _skus(db, today) -> list:
    """Every certified product as a `commerce.replication.Sku`, from rows and the pool."""
    from datetime import datetime, timezone

    from sqlalchemy import func, select

    from ..commerce.replication import Sku
    from ..radar.opportunity import POOL

    from ..core.models import PatternVersion, Product

    by = {p.slug: p for p in POOL}
    orders = _orders_by_slug(db)
    # Review 720b291 N-8: weeks are counted from when the product was first certified (the
    # earliest it could be on sale), not from its first order -- counting from the first
    # order made every product look newer than it is, and a product that sold late look
    # like a fast seller. Measured against `today`, which this function now honours.
    with db.session() as s:
        since = {slug: at for slug, at in s.execute(
            select(Product.slug, func.min(PatternVersion.created_at))
            .join(PatternVersion, PatternVersion.product_id == Product.id)
            .where(PatternVersion.certified == True)  # noqa: E712
            .group_by(Product.slug))}
    now = (datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
           if today is not None else datetime.now(timezone.utc))
    out = []
    for r in _certified(db):
        at = since.get(r["slug"])
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        weeks = (max(0, (now - at).days // 7) if at else 0)
        out.append(Sku(slug=r["slug"], orders=orders.get(r["slug"], 0), weeks_live=weeks,
                       traits=seed_traits(by.get(r["slug"]))))
    return out


def seed_traits(seed) -> dict:
    """The replication dimensions a radar seed states (the rest are not recorded)."""
    if seed is None:
        return {}
    return {"theme": seed.family or seed.slug, "category": seed.category,
            "season": seed.season or "evergreen",
            "price": ("under_8" if seed.price_cad < 8 else
                      "8_to_14" if seed.price_cad <= 14 else "over_14"),
            "bundle": "bundle" if seed.is_bundle else "single"}


def adjacency(investigation: dict, next_seed: str) -> dict:
    """Review 720b291 N-8: `commerce.replication.check_proposal` enforced on the follow-on.

    The follow-on holds the winner's traits it shares and changes the ones it does not, over
    the dimensions both record. With a credible study it must also hold at least one of the
    study's candidate causes, or it learns nothing about why the winner sells. A proposal the
    check calls a clone (palette only, nothing held or nothing changed) is not queued."""
    from ..commerce import replication
    from ..radar.opportunity import POOL

    by = {p.slug: p for p in POOL}
    win = seed_traits(by.get(investigation.get("winner") or ""))
    nxt = seed_traits(by.get(next_seed))
    shared = [d for d in replication.DIMENSIONS if d in win and d in nxt]
    if not shared:
        return {"adjacent": None, "why": "neither the winner nor the follow-on records a "
                                         "comparable trait; adjacency UNKNOWN, not passed"}
    holds = tuple(d for d in shared if win[d] == nxt[d])
    changes = tuple(d for d in shared if win[d] != nxt[d])
    verdict = replication.check_proposal(
        replication.Proposal(slug=next_seed, holds=holds, changes=changes),
        replication.Sku(slug=investigation.get("winner") or "", orders=0, weeks_live=0,
                        traits=win))
    causes = [e["dimension"] for e in investigation.get("explanations") or []]
    if verdict["adjacent"] and investigation.get("credible") and causes \
            and not set(causes) & set(holds):
        verdict = {**verdict, "adjacent": False, "reasons": [
            f"holds none of the study's candidate causes {causes[:3]}, so it cannot test "
            f"why the winner sells"]}
    return verdict


def investigate(db, family: dict, *, today) -> dict:
    """#22 `commerce.replication.study` for the family's best seller: a credible winner gets
    a bounded study (ranked, testable explanations); anything less is recorded with the
    replication module's own reasons -- never a guessed cause."""
    from ..commerce import replication

    members = sorted(family.get("members") or [], key=lambda m: -m["orders"])
    if not members:
        return {"credible": False, "reasons": ["no member"]}
    catalogue = _skus(db, today)
    winner = next((s for s in catalogue if s.slug == members[0]["slug"]), None)
    if winner is None:
        return {"credible": False, "reasons": ["best seller is not certified"]}
    try:
        st = replication.study(winner, catalogue, capacity_share=0.2, starts=today)
    except replication.ReplicationRefused as exc:
        return {"credible": False, "winner": winner.slug, "reasons": [str(exc)[:300]],
                "explanations": []}
    return {"credible": True, "winner": st["winner"], "ends": st["ends"],
            "explanations": [{"dimension": e["dimension"], "contrast": e["contrast"]}
                             for e in st["explanations"]],
            "confounded": st["confounded"], "attributable": st["attributable"]}


def _save_amp(db, family: str, body: dict) -> None:
    from ..autonomy import memory

    memory.remember(db, AMPLIFY_PREFIX + family, kind="creative.amplification",
                    department="product_design", subject=f"amplify {family}",
                    state="held" if body.get("held") else "open", body=body,
                    sources=["orders", "pattern_versions"])
