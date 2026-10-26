"""F-482: the contract-change barrier -- a shared contract cannot drift silently.

The CIR is the contract every product, compiler, reverse compiler, twin and listing is built
on; the Execution Directive makes it the one thing a lane must stop and declare rather than
change. `fingerprint()` hashes its shape -- every dataclass in `cir.model`, each field's name,
declared type and whether it has a default -- so any change to the contract changes the
fingerprint. `tests/test_w4_fmbatch1_contracts.py` holds the pinned value and fails until the
pin is updated **together with** a dated entry in `ops/CONTRACT_CHANGES.md` naming the
change and how dependants pin or migrate. The pin cannot be bumped without the declaration.

Scope today: the CIR. Listing payload keys and public API schemas are named as the next
contracts to pin (F-482 partial), because their churn needs a migration story first.
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


def fingerprint() -> str:
    return hashlib.sha256(json.dumps(cir_shape(), sort_keys=True).encode()).hexdigest()[:16]
