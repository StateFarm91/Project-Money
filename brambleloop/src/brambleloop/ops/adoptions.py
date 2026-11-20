"""F-417: what each adopted dependency, provider and service costs, and what it occupies.

`finance.unit_cost` measures running cost per artefact; nothing recorded, per adoption, what
taking on a technology cost and keeps costing. One row per adoption -- every direct
requirement, every called provider or data service, and hosting -- with:

* `recurring`: measured where this company records it (`CostEntry.provider` over the last
  30 days for metered providers), declared where it is only declared (hosting:
  `spend_policy.INFRA_MONTHLY_CAD`, basis `declared_not_observed`), zero for a free package;
* `footprint`: for a package, its installed size read from the installed distribution's file
  records; for a service, the host it is reached at; anything not read is `UNMEASURED`;
* `decision_ref` where a recorded decision explains the adoption, else `UNRECORDED`.

`check()` fails when a requirement or a called service has no adoption row, so the next
adoption is costed when it lands. Read-only; no network.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

UNMEASURED = "UNMEASURED"
UNRECORDED = "UNRECORDED"

# Direct requirements (requirements.txt) -> why adopted, decision ref.
PACKAGES: dict[str, tuple[str, str]] = {
    "sqlalchemy": ("database access for every durable row", UNRECORDED),
    "fastapi": ("HTTP API and dashboard", UNRECORDED),
    "uvicorn": ("ASGI server", UNRECORDED),
    "jinja2": ("server-rendered pages", UNRECORDED),
    "reportlab": ("pattern PDF rendering", "CLAUDE.md non-negotiables: patterns are releases"),
    "pillow": ("image composition and checks", UNRECORDED),
    "psycopg2-binary": ("PostgreSQL driver for production", UNRECORDED),
    "cryptography": ("OAuth token sealing and signing", UNRECORDED),
    "python-multipart": ("form/file uploads", UNRECORDED),
    "pypdf": ("PDF assembly and verification", UNRECORDED),
    "pypdfium2": ("PDF page rasterising for the contents frame", "requirements.txt W4-VISUAL2"),
    "numpy": ("yarn-level geometry", "requirements.txt (visual/yarn.py)"),
    "scipy": ("image analysis for render verification", "requirements.txt W4-PRODREADY"),
}

# Called services -> (metered provider key in CostEntry or None, host).
SERVICES: dict[str, tuple[str | None, str]] = {
    "anthropic": ("anthropic", "api.anthropic.com"),
    "bfl": ("bfl", "api.bfl.ai"),
    "openai": ("openai", "api.openai.com"),
    "google": ("google", "generativelanguage.googleapis.com"),
    "volcengine": ("volcengine", "volcengine API"),
    "wikimedia_pageviews": (None, "wikimedia.org"),
    "etsy_open_api": (None, "openapi.etsy.com"),
}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def direct_requirements() -> list[str]:
    from .licenses import ROOT

    text = (ROOT / "requirements.txt").read_text()
    return sorted({_norm(m.group(1)) for m in re.finditer(r"^([A-Za-z0-9_.\-]+)", text, re.M)})


def installed_mb(name: str):
    import importlib.metadata as md

    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        return UNMEASURED
    total = 0
    for f in dist.files or []:
        try:
            total += f.locate().stat().st_size
        except OSError:
            continue
    return round(total / 1e6, 2) if total else UNMEASURED


def _metered(db, now) -> dict[str, dict]:
    from sqlalchemy import func, select

    from ..core.models import CostEntry

    since = now - timedelta(days=30)
    with db.session() as s:
        rows = s.execute(select(CostEntry.provider, func.sum(CostEntry.amount_cad),
                                func.count()).where(CostEntry.at >= since)
                         .group_by(CostEntry.provider)).all()
    return {(p or ""): {"cad_30d": round(float(c or 0.0), 4), "rows": int(n)}
            for p, c, n in rows}


def report(db, *, now: datetime | None = None) -> dict:
    from ..finance import spend_policy

    now = now or datetime.now(timezone.utc)
    metered = _metered(db, now) if db is not None else {}
    rows = []
    for name, (why, ref) in sorted(PACKAGES.items()):
        rows.append({"adoption": name, "kind": "package", "why": why, "decision_ref": ref,
                     "one_off_cad": 0.0, "recurring": {"cad_30d": 0.0, "basis": "free licence"},
                     "footprint": {"installed_mb": installed_mb(name)}})
    for name, (key, host) in sorted(SERVICES.items()):
        m = metered.get(key or "")
        recurring = ({"cad_30d": m["cad_30d"], "rows": m["rows"],
                      "basis": "measured: cost_entries by provider, last 30 days"} if m else
                     {"cad_30d": 0.0, "basis": "measured: no cost rows in 30 days"} if key else
                     {"cad_30d": 0.0, "basis": "unmetered free API"})
        rows.append({"adoption": name, "kind": "service", "why": "called provider",
                     "decision_ref": UNRECORDED, "one_off_cad": 0.0, "recurring": recurring,
                     "footprint": {"host": host}})
    rows.append({"adoption": "hosting", "kind": "infrastructure", "why": "runs the company",
                 "decision_ref": UNRECORDED, "one_off_cad": 0.0,
                 "recurring": {"cad_month": spend_policy.INFRA_MONTHLY_CAD,
                               "basis": spend_policy.INFRA_BASIS},
                 "footprint": {"host": UNMEASURED}})
    return {"adoptions": rows, "problems": check(),
            "packages_installed_mb": round(sum(r["footprint"]["installed_mb"] for r in rows
                                               if isinstance(r["footprint"].get("installed_mb"),
                                                             float)), 2)}


def check() -> list[str]:
    from . import licenses

    problems = [f"requirement {p} has no adoption row" for p in direct_requirements()
                if p not in PACKAGES]
    problems += [f"service {s} has no adoption row" for s in licenses.called_services()
                 if s not in SERVICES]
    return problems
