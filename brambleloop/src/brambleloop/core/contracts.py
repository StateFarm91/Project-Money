"""Shared Truth Contracts (F-456) and the Contract Change Barrier (F-482) -- W4-AGENTS.

F-456: "Cross-department contracts -- CIR schemas, product IDs, listing schemas, evidence
formats, APIs and quality floors -- are versioned and authoritative. Agents do not silently
redefine shared contracts locally."
F-482: "A department changing a shared schema/API/CIR contract declares the change before
merge; dependent agents either pin the old version or explicitly migrate. Silent contract drift
is prohibited."

Each contract here has a VERSION and a deterministic FINGERPRINT of its shape (dataclass
fields, write-schema field sets, section lists). `contracts.json` pins both. `check()` fails:
* when a fingerprint moved but the version did not (silent drift), and
* when a version moved without a CHANGELOG entry for it (an undeclared change).
Consumers pin what they were built against with `require(name, version)`, which raises
`ContractDrift` at import when the contract has moved on -- so a dependent either migrates
(bumps its pin) or fails loudly. Regenerate the pins after declaring a change:

    python -m brambleloop.core.contracts --write
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

PINS = Path(__file__).resolve().with_name("contracts.json")


class ContractDrift(RuntimeError):
    """A consumer was built against a contract version that is no longer current."""


def _cir_shape():
    from ..cir import model as m

    out = {}
    for name in ("CIR", "Component", "Configuration", "Gauge", "Grading", "Hold", "Material",
                 "Op", "Provenance", "Repeat", "Row", "Seam"):
        cls = getattr(m, name)
        out[name] = [(f.name, str(f.type)) for f in dataclasses.fields(cls)]
    return out


def _etsy_write_shape():
    from ..integrations import etsy as e

    return {"ListingPayload": [f.name for f in dataclasses.fields(e.ListingPayload)],
            "UPDATE_WRITABLE": sorted(e.UPDATE_WRITABLE),
            "SHOP_UPDATE_SCHEMA": sorted(e.SHOP_UPDATE_SCHEMA),
            "SECTION_TITLE_MAX": e.SECTION_TITLE_MAX}


def _policy_shape():
    from ..commerce import shop_package

    return {"POLICY_SECTIONS": list(shop_package.POLICY_SECTIONS),
            "SHOP_TEXT_FIELDS": list(shop_package.SHOP_TEXT_FIELDS)}


def _storefront_proposal_shape():
    from ..store_foundation import director, live_state

    p = director._proposal(None, "announcement", {"operation": "noop"}, "contract", api=True)
    return {"proposal_keys": sorted(p), "agent_writable": sorted(live_state.AGENT_WRITABLE),
            "kind": director.PROPOSAL_KIND}


def _evidence_shape():
    from ..store_foundation import live_state

    return {"live_field_keys": [f.key for f in live_state.FIELDS],
            "statuses": sorted({live_state.MATCH, live_state.DRIFT, live_state.LIVE_MISSING,
                                live_state.STALE, live_state.UNKNOWN})}


#: name -> (current version, shape function, what it is)
CONTRACTS: dict[str, tuple[int, object, str]] = {
    "cir": (1, _cir_shape, "the CIR dataclasses every department builds, checks and renders"),
    "etsy_write_schemas": (1, _etsy_write_shape,
                           "what may be sent to Etsy (draft payload, updateListing, updateShop)"),
    "shop_policy_sections": (1, _policy_shape, "the shop's policy sections and text fields"),
    "storefront_proposal": (1, _storefront_proposal_shape,
                            "the Storefront Director's proposal record and writable fields"),
    "live_shop_evidence": (1, _evidence_shape, "live-shop field keys and drift statuses"),
}

#: name -> {version: "date: what changed and who migrated"}. A version without an entry is an
#: undeclared change and fails `check()`.
CHANGELOG: dict[str, dict[int, str]] = {
    "cir": {1: "2026-10-26: first pinned version (W4-AGENTS F-456)"},
    "etsy_write_schemas": {1: "2026-10-26: first pinned version, incl. updateShop + sections"},
    "shop_policy_sections": {1: "2026-10-26: first pinned version"},
    "storefront_proposal": {1: "2026-10-26: first pinned version"},
    "live_shop_evidence": {1: "2026-10-26: first pinned version"},
}


def fingerprint(name: str) -> str:
    _v, fn, _what = CONTRACTS[name]
    return hashlib.sha256(json.dumps(fn(), sort_keys=True, default=str).encode()).hexdigest()


def current() -> dict:
    return {n: {"version": v, "fingerprint": fingerprint(n), "what": what}
            for n, (v, _fn, what) in CONTRACTS.items()}


def pins() -> dict:
    try:
        return json.loads(PINS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def check() -> list[str]:
    """Every silent or undeclared contract change. Empty means the contracts hold."""
    problems = []
    pinned = pins()
    for name, now in current().items():
        p = pinned.get(name)
        if p is None:
            problems.append(f"{name}: not pinned in contracts.json")
            continue
        if now["fingerprint"] != p.get("fingerprint") and now["version"] == p.get("version"):
            problems.append(f"{name}: shape changed without a version bump (silent drift); "
                            f"bump CONTRACTS[{name!r}], add a CHANGELOG entry, migrate "
                            f"dependants, then regenerate the pins")
        if now["version"] not in CHANGELOG.get(name, {}):
            problems.append(f"{name}: version {now['version']} has no CHANGELOG entry "
                            f"(an undeclared change)")
        if now["version"] != p.get("version") and now["fingerprint"] == p.get("fingerprint"):
            problems.append(f"{name}: version bumped but contracts.json not regenerated")
    for name in pinned:
        if name not in CONTRACTS:
            problems.append(f"{name}: pinned but no longer declared")
    return problems


def require(name: str, version: int) -> None:
    """A consumer's pin: raise unless `name` is still at `version`."""
    have = CONTRACTS.get(name, (None,))[0]
    if have != version:
        raise ContractDrift(f"built against {name} v{version}, but the contract is now "
                            f"v{have}: migrate this consumer and bump its pin")


if __name__ == "__main__":  # pragma: no cover
    import sys

    if "--write" in sys.argv:
        PINS.write_text(json.dumps({n: {"version": c["version"],
                                        "fingerprint": c["fingerprint"]}
                                    for n, c in current().items()}, indent=1, sort_keys=True)
                        + "\n", encoding="utf-8")
        print(f"wrote {PINS}")
    else:
        print(json.dumps(current(), indent=1))
        print(check() or "contracts hold")
