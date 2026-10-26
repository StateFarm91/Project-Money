"""F-482: the contract-change barrier -- a shared contract cannot drift silently.

The CIR is the contract every product, compiler, reverse compiler, twin and listing is built
on; the Execution Directive makes it the one thing a lane must stop and declare rather than
change. `fingerprint()` hashes its shape -- every dataclass in `cir.model`, each field's name,
declared type and whether it has a default -- so any change to the contract changes the
fingerprint. `tests/test_w4_fmbatch1_contracts.py` holds the pinned value and fails until the
pin is updated **together with** a dated entry in `ops/CONTRACT_CHANGES.md` naming the
change and how dependants pin or migrate. The pin cannot be bumped without the declaration.

Pinned contracts (`fingerprints()`):
* `cir` -- every dataclass in `cir.model` (field name, declared type, has-default);
* `listing_payload` -- `integrations.etsy.ListingPayload`, the shape sent to Etsy;
* `api_routes` -- every HTTP route the app serves (path and methods). Response bodies are not
  hashed: they are documents with UNKNOWN-valued fields, and their keys are pinned by each
  route's own tests; what a dependant calls is the route.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json


def cir_shape() -> dict:
    from ..cir import model

    out = {}
    for name, obj in sorted(vars(model).items()):
        if inspect.isclass(obj) and dataclasses.is_dataclass(obj) \
                and obj.__module__ == model.__name__:
            out[name] = [
                [f.name, str(f.type),
                 f.default is not dataclasses.MISSING
                 or f.default_factory is not dataclasses.MISSING]  # type: ignore[misc]
                for f in dataclasses.fields(obj)]
    return out


def _fields(cls) -> list:
    return [[f.name, str(f.type),
             f.default is not dataclasses.MISSING
             or f.default_factory is not dataclasses.MISSING]  # type: ignore[misc]
            for f in dataclasses.fields(cls)]


def listing_payload_shape() -> dict:
    from ..integrations.etsy import ListingPayload

    return {"ListingPayload": _fields(ListingPayload)}


def api_routes_shape(app=None) -> list:
    if app is None:
        from ..app.main import app
    out = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = sorted(getattr(r, "methods", None) or [])
        if path and methods:
            out.add((path, ",".join(methods)))
    return sorted(out)


def _h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def fingerprint() -> str:
    """The CIR contract's fingerprint (kept for the original pin)."""
    return _h(cir_shape())


def fingerprints(app=None) -> dict:
    return {"cir": fingerprint(), "listing_payload": _h(listing_payload_shape()),
            "api_routes": _h(api_routes_shape(app))}
