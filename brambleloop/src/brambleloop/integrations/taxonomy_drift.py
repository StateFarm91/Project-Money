"""F-010 Attribute Drift Monitor: a changed Etsy schema re-validates the listings it touches.

F-010: "Periodically re-check category/attribute schemas for platform changes."

`listing.taxonomy_refresh` already re-reads Etsy's seller taxonomy and the pattern nodes'
property schemas every day, and stores a new `EtsyTaxonomySnapshot` only when the content
hash changes. Before this module a changed hash was the end of it: the new snapshot sat in
the table while every listing's search profile stayed bound to the schema it was computed
on, so a node Etsy renamed, removed or re-required kept its certified category and property
payload as if nothing had happened.

What happens now, on every refresh that stored a new snapshot:

* **diff** the new snapshot against the previous one: nodes removed, added and moved or
  renamed (the ancestor path is compared, so a renamed parent changes every node under it),
  and per node the properties added, removed or changed (name, required flag, multivalued,
  allowed values, scales). A node whose schema is read for the first time is a change too.
* **affected listings** are judged per product from its newest `ListingSearchProfile`:
  - a profile CHOSEN on a node that changed, was removed, moved, or gained a child (a deeper
    truthful category may now exist) is **affected and was certified on a schema that no
    longer holds**: a halting P1 incident `taxonomy-drift:<slug>` is opened, so publication
    refuses the product until it is re-validated, and `listing.seo` is re-queued. When no
    `listing.seo` can be re-queued the P1 is opened non-halting and says so: Gate E halts
    `gate.certify` on a halting incident, and a halt nothing is queued to resolve would block
    the certification that rebuilds the profile (the deadlock W4-LISTREADY R2 describes);
  - a profile that is not CHOSEN (UNKNOWN or refused) is re-queued without an incident: it
    is already refused by its search certificate, and the new schema may now let the
    chooser decide;
  - a CHOSEN profile whose node, path and schema are unchanged is left alone.
* **re-queue** uses the inputs of the release's last completed `listing.seo` job with a
  rebuild token naming the snapshot (`tx<id>`), so it runs once per snapshot, never once per
  cadence. A profile with no completed `listing.seo` to re-run is reported as not re-queued
  with the reason, and its incident stays open: nothing re-validated it.
* **resolution**: `listing.seo` writes the profile on the newest snapshot
  (`runtime.release._persist_search_profile`), which resolves the product's drift incident
  when the profile is bound to the snapshot the incident names or a later one.

The first snapshot ever stored has nothing to drift from: profiles computed with no snapshot
are re-queued (they read UNKNOWN) and no incident is opened. Read-only towards Etsy: this
module never makes a network call; it reads two stored snapshots and the profile table.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SIGNATURE_PREFIX = "taxonomy-drift:"
ACTION = "etsy.taxonomy_drift"
CHOSEN = "CHOSEN"   # commerce.category.CHOSEN; not imported to keep this module light

# The property fields whose change alters what a listing may truthfully send.
_PROPERTY_FIELDS = ("name", "is_required", "is_multivalued", "max_values_allowed",
                    "supports_attributes")


def _norm_property(prop: dict) -> dict:
    values = sorted((str(v.get("value_id")), str(v.get("name") or ""))
                    for v in (prop.get("possible_values") or []) if isinstance(v, dict))
    scales = sorted(str(s.get("scale_id") if isinstance(s, dict) else s)
                    for s in (prop.get("scales") or []))
    out = {k: prop.get(k) for k in _PROPERTY_FIELDS}
    out["possible_values"] = values
    out["scales"] = scales
    return out


def _props_by_id(props: Any) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in props or []:
        if isinstance(p, dict) and p.get("property_id") is not None:
            out[str(p["property_id"])] = _norm_property(p)
    return out


def diff(old: dict | None, new: dict) -> dict:
    """What changed between two snapshots (`{"nodes": [...], "properties": {...}}`).

    `old` None means there was no earlier snapshot: everything is new and nothing drifted.
    `changed_ids` is every node id a listing filed there must be re-validated for.
    """
    new_nodes = {int(n["id"]): n for n in (new.get("nodes") or [])}
    if old is None:
        return {"first_snapshot": True, "removed": [], "added": sorted(new_nodes),
                "moved_or_renamed": [], "schema_changed": {}, "changed_ids": [],
                "gained_child": [], "material": False}
    old_nodes = {int(n["id"]): n for n in (old.get("nodes") or [])}
    removed = sorted(set(old_nodes) - set(new_nodes))
    added = sorted(set(new_nodes) - set(old_nodes))
    moved = sorted(i for i in set(old_nodes) & set(new_nodes)
                   if list(old_nodes[i].get("path_names") or []) !=
                   list(new_nodes[i].get("path_names") or [])
                   or list(old_nodes[i].get("path_ids") or []) !=
                   list(new_nodes[i].get("path_ids") or []))
    old_props = old.get("properties") or {}
    new_props = new.get("properties") or {}
    schema: dict[str, dict] = {}
    for key in sorted(set(old_props) | set(new_props), key=str):
        a, b = _props_by_id(old_props.get(key)), _props_by_id(new_props.get(key))
        change = {"added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)),
                  "changed": sorted(p for p in set(a) & set(b) if a[p] != b[p]),
                  "first_read": key not in old_props and key in new_props,
                  "no_longer_read": key in old_props and key not in new_props}
        if any(change.values()):
            schema[str(key)] = change
    # A node that gained a child: the deepest truthful category may now be deeper.
    gained_child = sorted({p for i in added for p in (new_nodes[i].get("path_ids") or [])[:-1]
                           if p in old_nodes})
    changed = set(removed) | set(moved) | {int(k) for k in schema} | set(gained_child)
    # A moved/renamed ancestor moves every node under it; path comparison already counts
    # those nodes, since each node carries its full path.
    return {"first_snapshot": False, "removed": removed, "added": added,
            "moved_or_renamed": moved, "schema_changed": schema,
            "gained_child": gained_child, "changed_ids": sorted(changed),
            "material": bool(changed or added)}


def _snapshot_dict(row) -> dict:
    return {"id": row.id, "nodes": row.nodes or [], "properties": row.properties or {},
            "sha256": row.sha256}


def _newest_profiles(session) -> list:
    """Each product's newest search profile (the release a re-validation would rebuild)."""
    from sqlalchemy import select

    from ..core.models import ListingSearchProfile

    newest: dict[str, Any] = {}
    for row in session.scalars(select(ListingSearchProfile).order_by(
            ListingSearchProfile.updated_at, ListingSearchProfile.id)):
        newest[row.product_slug] = row
    return [newest[k] for k in sorted(newest)]


def _last_seo_inputs(session, slug: str, version: str) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import Job, JobStatus

    for job in session.scalars(select(Job).where(
            Job.job_type == "listing.seo", Job.status == JobStatus.DONE)
            .order_by(desc(Job.id))):
        i = job.inputs or {}
        if i.get("slug") == slug and i.get("version") == version:
            return dict(i)
    return None


def judge(profiles: list[dict], d: dict, *, new_id: int) -> list[dict]:
    """Per product: affected or not, whether it halts, and why. Pure; no database."""
    changed = set(d.get("changed_ids") or [])
    out = []
    for p in profiles:
        if p.get("snapshot_id") == new_id:
            continue                                   # already built on the new schema
        chosen = p.get("category_status") == CHOSEN and p.get("taxonomy_id") is not None
        if chosen:
            tid = int(p["taxonomy_id"])
            if tid not in changed:
                continue
            why = []
            if tid in (d.get("removed") or []):
                why.append(f"node {tid} no longer exists in Etsy's taxonomy")
            if tid in (d.get("moved_or_renamed") or []):
                why.append(f"node {tid} moved or was renamed")
            if str(tid) in (d.get("schema_changed") or {}):
                why.append(f"node {tid}'s property schema changed: "
                           f"{d['schema_changed'][str(tid)]}")
            if tid in (d.get("gained_child") or []):
                why.append(f"node {tid} gained a child: a deeper truthful category may exist")
            out.append({**p, "halts": True, "why": "; ".join(why)[:600]})
        else:
            out.append({**p, "halts": False,
                        "why": (f"category {p.get('category_status')}: re-chosen on the new "
                                "snapshot, which may now decide it")})
    return out


def after_refresh(ctx, *, snapshot_id: int, now: datetime | None = None) -> dict:
    """Diff the stored snapshot against its predecessor and act on the listings it touches."""
    from sqlalchemy import desc, select

    from ..core.models import EtsyTaxonomySnapshot
    from ..ops import incident_lifecycle as lifecycle
    from ..runtime.release import chain_key

    now = now or datetime.now(timezone.utc)
    with ctx.db.session() as s:
        new_row = s.get(EtsyTaxonomySnapshot, snapshot_id)
        if new_row is None:
            return {"state": "UNKNOWN", "why": f"snapshot {snapshot_id} is not stored"}
        prev_row = s.scalar(select(EtsyTaxonomySnapshot)
                            .where(EtsyTaxonomySnapshot.id < snapshot_id)
                            .order_by(desc(EtsyTaxonomySnapshot.id)).limit(1))
        d = diff(_snapshot_dict(prev_row) if prev_row is not None else None,
                 _snapshot_dict(new_row))
        profiles = [{"slug": r.product_slug, "version": r.version,
                     "snapshot_id": r.snapshot_id, "category_status": r.category_status,
                     "taxonomy_id": r.taxonomy_id} for r in _newest_profiles(s)]
        verdicts = judge(profiles, d, new_id=snapshot_id)
        token = f"tx{snapshot_id}"
        requeued, not_requeued, opened = [], [], []
        for v in verdicts:
            inputs = _last_seo_inputs(s, v["slug"], v["version"])
            if inputs is None:
                not_requeued.append({"slug": v["slug"], "version": v["version"],
                                     "why": "no completed listing.seo job for this release "
                                            "to re-run; the profile stays on the old "
                                            "snapshot until the next certification "
                                            "rebuilds it"})
            else:
                v["inputs"] = inputs
            if v["halts"] and not d["first_snapshot"]:
                # Halting only where a re-validation is queued: Gate E halts gate.certify
                # for the product while the incident is open, so a halt with nothing queued
                # to resolve it would block the very certification that rebuilds the
                # profile. Without one the incident is a P1 that names the gap instead.
                halts = inputs is not None
                _row, new = lifecycle.open_or_restate(
                    s, signature=f"{SIGNATURE_PREFIX}{v['slug']}", severity="P1",
                    product_slug=v["slug"], halts_publication=halts,
                    summary=(f"{v['slug']}@{v['version']} was certified on Etsy taxonomy "
                             f"snapshot {v['snapshot_id']}, and snapshot {snapshot_id} "
                             f"changed its category: {v['why']}"
                             + ("" if halts else "; no listing.seo could be re-queued, so "
                                "the next certification of this product must rebuild it"))
                    [:900],
                    detail={"snapshot_id": snapshot_id, "previous_snapshot_id":
                            prev_row.id if prev_row is not None else None,
                            "version": v["version"], "taxonomy_id": v["taxonomy_id"],
                            "why": v["why"], "requeued": halts}, now=now)
                v["halts"] = halts
                if new:
                    opened.append(v["slug"])
        prev_id = prev_row.id if prev_row is not None else None
    # Enqueued after the incidents are committed, each in the queue's own transaction.
    for v in verdicts:
        inputs = v.pop("inputs", None)
        if inputs is None:
            continue
        ctx.enqueue("listing", "listing.seo", {**inputs, "rebuild": token},
                    idempotency_key=chain_key("seo", v["slug"], v["version"],
                                              inputs.get("release", ""), token))
        requeued.append(f"{v['slug']}@{v['version']}")
    report = {"state": "measured", "snapshot_id": snapshot_id,
              "previous_snapshot_id": prev_id,
              "first_snapshot": d["first_snapshot"],
              "removed": d["removed"][:50], "added": d["added"][:50],
              "moved_or_renamed": d["moved_or_renamed"][:50],
              "schema_changed": dict(list(d["schema_changed"].items())[:20]),
              "gained_child": d["gained_child"][:50],
              "affected": [{k: v[k] for k in ("slug", "version", "taxonomy_id", "halts", "why")}
                           for v in verdicts],
              "incidents_opened": opened, "requeued": requeued,
              "not_requeued": not_requeued}
    ctx.audit(ACTION, detail=report)
    return report


def resolve_if_current(session, slug: str, snapshot_id: int | None) -> list[str]:
    """Called where a search profile is written: a profile rebuilt on the snapshot the drift
    incident names (or a later one) resolves that product's incident."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..ops import incident_lifecycle as lifecycle

    if snapshot_id is None:
        return []
    sig = f"{SIGNATURE_PREFIX}{slug}"
    row = session.scalar(select(Incident).where(Incident.signature == sig,
                                                Incident.resolved == False))  # noqa: E712
    if row is None:
        return []
    named = (row.detail or {}).get("snapshot_id")
    if named is None or int(snapshot_id) < int(named):
        return []
    return lifecycle.resolve_signatures(
        session, [sig], resolution=(f"listing.seo rebuilt the search profile on taxonomy "
                                    f"snapshot {snapshot_id}"))
