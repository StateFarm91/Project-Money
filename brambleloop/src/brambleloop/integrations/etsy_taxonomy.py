"""Etsy's seller taxonomy, read into a durable snapshot (F-005, F-006, F-007, F-009).

Every listing this company drafted was sent with one integer, `TAXONOMY_PATTERNS = 66`, that
nobody had ever read back from Etsy. A wrong taxonomy id is not an error -- Etsy answers 201
and files the listing where no crochet shopper looks -- so the only thing that can confirm a
category is Etsy's own tree, and the only thing that can say which attributes a category
takes is that node's property schema. This module reads both and stores them.

**The gate is real and is checked before anything else.** The reads need a working Etsy
credential, and the `etsy_api` gate's condition is a recorded successful `etsy.probe`
(`intel.etsy_public.usable`). When that gate is closed the run records `UNMEASURED` with the
reason and makes **no network call** -- the client is not even constructed. That is an honest
no-op: the category chooser then reads UNKNOWN for every product and search certification
refuses, which is the truthful state of a company that has never looked at the tree.

**What is stored.** The flattened tree (id, name, level, parent_id, the ancestor path) and the
property lists of every node in the crochet-pattern subtree, exactly as Etsy returned them.
Properties are read only for that subtree, because a pattern shop has no business with the
schema of "Jewelry > Rings", and Etsy's tree has thousands of nodes; `MAX_PROPERTY_READS`
bounds the run even if the subtree turns out larger than expected.

Nothing here decides a category. `commerce.category` reads the snapshot and decides.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable

NODES_OPERATION = "getSellerTaxonomyNodes"
PROPERTIES_OPERATION = "getPropertiesByTaxonomyId"
SOURCE = "etsy_open_api_v3"
REFRESHED_ACTION = "etsy.taxonomy_refreshed"
JOB_TYPE = "listing.taxonomy_refresh"

# Bound on property reads per run. The crochet-pattern subtree is expected to be a handful of
# nodes; a tree that yields more than this is recorded as truncated rather than read forever.
MAX_PROPERTY_READS = 40

# Injection point for the client, like `orders_ingest.reader_factory`. None in production:
# the client is built from the environment's Etsy credential, and only after the gate is open.
# Tests set this to a fake that answers with recorded responses; the gate is still checked
# first, so a test cannot read a tree the gate refuses.
client_factory: Callable[[Any], Any] | None = None


class TaxonomyReadFailed(RuntimeError):
    """Etsy answered, but not with a tree this module can read."""


# ---------------------------------------------------------------------------
# The gate


# ---------------------------------------------------------------------------
# The API-key-only read path (wave 3, lane G wiring request 2)
#
# Etsy's Open API v3 document gives getSellerTaxonomyNodes and getPropertiesByTaxonomyId an
# `api_key` security requirement and no OAuth scope (`seo.constraints`
# `seller_taxonomy_read_needs_api_key_only`, VERIFIED 2026-10-06). The taxonomy therefore does
# not have to wait for the shop's OAuth grant: the app keystring alone may read it. This
# client can do nothing else -- GET only, `/seller-taxonomy/` paths only, no Authorization
# header -- so opening the gate on it cannot reach a shop, a listing or a write.

TAXONOMY_PATH_PREFIX = "/seller-taxonomy/"
# Injection point for the transport, so tests answer with recorded responses and make no
# network call. None in production: `integrations.http.UrllibTransport`.
api_key_transport_factory: Callable[[], Any] | None = None


class ApiKeyTaxonomyClient:
    """A read-only seller-taxonomy client authenticated by the app keystring alone."""

    BASE = "https://openapi.etsy.com/v3/application"

    def __init__(self, transport, *, api_key: str, shared_secret: str = ""):
        if not api_key:
            raise ValueError("an API-key client needs a keystring")
        self.transport = transport
        self._header = f"{api_key}:{shared_secret}" if shared_secret else api_key
        self.calls: list[dict] = []

    def _call(self, method: str, path: str, *, operation: str, authority: Any = None,
              **_unused):
        from .etsy import EtsyRejected, TransientError, classify_http

        if method != "GET" or not path.startswith(TAXONOMY_PATH_PREFIX):
            raise PermissionError(f"the API-key taxonomy client reads {TAXONOMY_PATH_PREFIX} "
                                  f"with GET only; refused {method} {path} ({operation})")
        response = self.transport.request("GET", f"{self.BASE}{path}",
                                          headers={"x-api-key": self._header})
        self.calls.append({"operation": operation, "method": "GET", "path": path,
                           "status": response.status, "auth": "api_key_only"})
        if response.status >= 400:
            kind = classify_http(response.status)
            message = (f"Etsy returned {response.status} for GET {path} ({operation}) on the "
                       f"API-key-only path")
            if kind is TransientError:
                raise TransientError(message)
            raise EtsyRejected(message)
        return response

    def __repr__(self) -> str:  # pragma: no cover - keeps the keystring out of logs
        return f"ApiKeyTaxonomyClient(calls={len(self.calls)}, api_key=***)"


def _api_key(env: dict | None = None) -> tuple[str, str]:
    import os

    e = env if env is not None else os.environ
    return ((e.get("ETSY_KEYSTRING") or e.get("ETSY_API_KEY") or "").strip(),
            (e.get("ETSY_SHARED_SECRET") or "").strip())


def api_key_client(env: dict | None = None):
    """The read-only API-key client, or None when no keystring is in the environment."""
    key, secret = _api_key(env)
    if not key:
        return None
    if api_key_transport_factory is not None:
        transport = api_key_transport_factory()
    else:
        from .http import UrllibTransport

        transport = UrllibTransport()
    return ApiKeyTaxonomyClient(transport, api_key=key, shared_secret=secret)


def gate(db, *, env: dict | None = None) -> dict:
    """Whether the taxonomy may be read now, how, and what is missing if not.

    Open by either path: a recorded successful `etsy.probe` (the shop credential), or -- since
    these two reads need only the app keystring -- a keystring in the environment, read
    through `ApiKeyTaxonomyClient`. `via` says which.
    """
    from ..intel import etsy_public

    missing: list[str] = []
    via = None
    if etsy_public.usable(db):
        via = "shop_credential"
    elif _api_key(env)[0]:
        via = "api_key_only"
    else:
        missing.append("etsy_api: no recorded successful etsy.probe, so no working Etsy "
                       "credential has been demonstrated; and no ETSY_KEYSTRING/ETSY_API_KEY "
                       "is set for the API-key-only taxonomy read")
    return {"open": not missing, "missing": missing, "via": via,
            "operations": [NODES_OPERATION, PROPERTIES_OPERATION]}


# ---------------------------------------------------------------------------
# Reading


def _production_client(db):
    from ..integrations.etsy import Credentials, EtsyClient
    from ..integrations.http import UrllibTransport

    transport = UrllibTransport()
    creds = Credentials.from_env(transport=transport, db=db)
    if creds is None:
        return None
    return EtsyClient(transport, credentials=creds)


def read_tree(client) -> list[dict]:
    """The raw `results` of getSellerTaxonomyNodes, through the client's own transport.

    `EtsyClient` walks this tree in `get_taxonomy_node` and `find_taxonomy_nodes` but has no
    public method returning it whole, and `integrations/etsy.py` belongs to another cluster.
    `_call` is used deliberately rather than a second HTTP path: it is the one place that
    applies the credential, the operation's scope check and the error classification.
    """
    from ..integrations.etsy import Authority

    body = client._call("GET", "/seller-taxonomy/nodes", operation=NODES_OPERATION,
                        authority=Authority.READ).body
    results = body.get("results") if isinstance(body, dict) else None
    if not isinstance(results, list):
        raise TaxonomyReadFailed(f"{NODES_OPERATION} returned no `results` list")
    return results


def flatten(results: list[dict]) -> list[dict]:
    """Every node once, with its parent and its ancestor path, in tree order.

    Etsy documents `parent_id` and `full_path_taxonomy_ids` on each node; both are recomputed
    from the nesting here rather than trusted, so a response that omits them still yields a
    usable path, and one whose fields disagree with its own nesting is caught by the nesting.
    """
    out: list[dict] = []

    def walk(nodes: Any, parent: dict | None) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict) or node.get("id") is None:
                continue
            nid = int(node["id"])
            path_ids = (parent["path_ids"] if parent else []) + [nid]
            path_names = (parent["path_names"] if parent else []) + [str(node.get("name") or "")]
            row = {"id": nid, "name": str(node.get("name") or ""),
                   "level": node.get("level", len(path_ids) - 1),
                   "parent_id": parent["id"] if parent else None,
                   "path_ids": path_ids, "path_names": path_names,
                   "child_ids": [int(c["id"]) for c in (node.get("children") or [])
                                 if isinstance(c, dict) and c.get("id") is not None]}
            out.append(row)
            walk(node.get("children"), row)

    walk(results, None)
    return out


def pattern_subtree(nodes: list[dict]) -> list[dict]:
    """The nodes a crochet pattern could truthfully be filed under.

    A node is in the subtree when some ancestor-or-self is named like a pattern node and some
    ancestor-or-self is named like crochet. Decided from names, because the ids are exactly
    what nobody here has verified.
    """
    out = []
    for n in nodes:
        names = [p.lower() for p in n["path_names"]]
        if any("pattern" in p for p in names) and any("crochet" in p for p in names):
            out.append(n)
    return out


def fingerprint(nodes: list[dict], properties: dict) -> str:
    blob = json.dumps({"nodes": nodes, "properties": properties}, sort_keys=True,
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def refresh(db, *, now: datetime | None = None) -> dict:
    """Read the tree and the subtree's properties into a snapshot, or say why not.

    Returns `ran`, `reading` (`measured` or `UNMEASURED`), `network_calls`, and the snapshot
    id when one was written or confirmed.
    """
    from sqlalchemy import desc, select

    from ..core.models import EtsyTaxonomySnapshot

    now = now or datetime.now(timezone.utc)
    g = gate(db)
    if not g["open"]:
        return {"ran": False, "reading": "UNMEASURED", "network_calls": 0, "gate": g,
                "why": ("the etsy_api gate is closed, so the taxonomy was not read and no "
                        "client was constructed; every category reads UNKNOWN until it is")}
    if client_factory is not None:
        client = client_factory(db)
    elif g.get("via") == "api_key_only":
        client = api_key_client()
    else:
        client = _production_client(db)
    if client is None:
        return {"ran": False, "reading": "UNMEASURED", "network_calls": 0, "gate": g,
                "why": "the etsy_api gate is open but no Etsy credential is in this "
                       "environment, so no client could be built"}

    calls = 0
    results = read_tree(client)
    calls += 1
    nodes = flatten(results)
    subtree = pattern_subtree(nodes)
    properties: dict[str, list] = {}
    truncated = False
    for n in subtree:
        if calls - 1 >= MAX_PROPERTY_READS:
            truncated = True
            break
        body = client._call("GET", f"/seller-taxonomy/nodes/{n['id']}/properties",
                            operation=PROPERTIES_OPERATION,
                            authority=_read_authority()).body
        calls += 1
        got = body.get("results") if isinstance(body, dict) else None
        properties[str(n["id"])] = list(got) if isinstance(got, list) else []

    sha = fingerprint(nodes, properties)
    with db.session() as s:
        latest = s.scalar(select(EtsyTaxonomySnapshot)
                          .order_by(desc(EtsyTaxonomySnapshot.id)).limit(1))
        if latest is not None and latest.sha256 == sha:
            latest.confirmed_at = now
            sid, written = latest.id, False
        else:
            row = EtsyTaxonomySnapshot(
                fetched_at=now, confirmed_at=now, source=SOURCE, sha256=sha,
                node_count=len(nodes), nodes=nodes, properties=properties,
                detail={"pattern_subtree": [n["id"] for n in subtree],
                        "properties_read": len(properties), "truncated": truncated})
            s.add(row)
            s.flush()
            sid, written = row.id, True
    return {"ran": True, "reading": "measured", "network_calls": calls, "gate": g,
            "snapshot_id": sid, "new_snapshot": written, "nodes": len(nodes),
            "pattern_subtree": len(subtree), "properties_read": len(properties),
            "truncated": truncated,
            "why": ("read Etsy's taxonomy and the crochet-pattern subtree's property schemas"
                    if subtree else
                    "read Etsy's taxonomy; no node is named both pattern and crochet, so "
                    "every category stays UNKNOWN")}


def _read_authority():
    from ..integrations.etsy import Authority

    return Authority.READ


def latest(db) -> dict | None:
    """The newest snapshot as a plain dict, or None when the tree has never been read."""
    from sqlalchemy import desc, select

    from ..core.models import EtsyTaxonomySnapshot

    with db.session() as s:
        row = s.scalar(select(EtsyTaxonomySnapshot)
                       .order_by(desc(EtsyTaxonomySnapshot.id)).limit(1))
        if row is None:
            return None
        return {"id": row.id, "fetched_at": row.fetched_at.isoformat() if row.fetched_at
                else None,
                "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
                "sha256": row.sha256, "source": row.source, "nodes": list(row.nodes or []),
                "properties": dict(row.properties or {}), "detail": dict(row.detail or {})}
