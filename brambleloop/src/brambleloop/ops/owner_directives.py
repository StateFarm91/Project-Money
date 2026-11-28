"""Owner directives applied by the system, never by a person's session (D-OWNER-APPROVE-ALL).

On 2026-11-20 (~13:20 UTC) the owner told the integrating session, in their own words:
"I approve every single one. Approve them all, whatever it takes. Once it's at 0, I will take
over approval moving forward."

The paid-provider gate (`gateway.paid_provider_gate`) normally accepts an activation only with
owner step-up evidence: passphrase + TOTP, `step_up.session_public_id`. This module records the
owner's directive as a second, explicit kind of evidence:

* Only the (directive, provider, scope) triples in `ACTIVATIONS` are recognised. The gate checks
  membership in this table, so nothing else can claim directive authority.
* Each activation is written ONCE per triple. An expired or revoked directive activation is
  never renewed by the system. The directive was "approve what is pending now"; renewing it
  later is the owner's own decision through the normal step-up path.
* Ceilings are conservative and sit inside the company's monthly ceiling. Every call is still
  reserved, capped (daily, monthly, per gallery, per run) and audited by the gate exactly as
  for a step-up activation.
* The step-up evidence on the row says plainly that no step-up happened
  (`session_public_id: None`, `owner_directive: ...`). Nothing is presented as a login.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

DIRECTIVE_ID = "D-OWNER-APPROVE-ALL"
DIRECTIVE_AT = "2026-11-20T13:20:00Z"
ACTOR = f"owner-directive:{DIRECTIVE_ID}"
ACTION = "owner_directive.applied"
EXPIRY = timedelta(days=30)
# B19-SEC S1: the directive was "approve what is pending now". It mints authority only inside
# its own window: from when it was given until EXPIRY later. After that a fresh or reset store
# (new environment, restore from an older backup, recreated table) is never given a new one.
GIVEN_AT = datetime(2026, 11, 20, 13, 20, tzinfo=timezone.utc)
SUNSET = GIVEN_AT + EXPIRY
_SLACK = timedelta(seconds=1)

# (provider, scope) -> ceilings. Image generation for the 7-photo galleries, and the second,
# independent vision judge. Nothing else: no ads, no text-model widening, no company ceiling.
ACTIVATIONS: dict[tuple[str, str], dict] = {
    # D-OWNER-PHOTO-BUDGET (2026-11-28): daily CA$5.00 -> CA$10.00, per gallery CA$2.50 ->
    # CA$6.00 (= image_production.MAX_SPEND_CAD_PER_GALLERY, so the activation never cuts the
    # owner's plan short). Monthly unchanged at CA$40; the company's CA$100/month is unchanged.
    ("flux-3-image", "generation"): {"daily_ceiling_cad": 10.0, "monthly_ceiling_cad": 40.0,
                                     "per_gallery_cad": 6.0},
    ("openai-vision", "vision"): {"daily_ceiling_cad": 2.0, "monthly_ceiling_cad": 10.0,
                                  "per_gallery_cad": 1.0},
    # D-OWNER-PHOTO-VISION (2026-11-28T16:50Z): the second, independent vision vendor, so Laura
    # identity can get two readings from different vendors (two OpenAI readings count as one).
    # The owner, in their own words in the integrating session: "Im on my phone. You do it. I
    # approve" -- answering the exact request for anthropic-vision at CA$2/day, CA$10/month,
    # CA$1 per gallery. It carries its OWN directive id, window and actor (`DIRECTIVES`).
    ("anthropic-vision", "vision"): {"daily_ceiling_cad": 2.0, "monthly_ceiling_cad": 10.0,
                                     "per_gallery_cad": 1.0},
}

# Which directive authorises which triple. A triple not listed here belongs to the original
# D-OWNER-APPROVE-ALL. Each later directive has its own id, given-at time, 30-day window and
# actor, so its authority is never back-dated into another directive's window.
PHOTO_VISION_ID = "D-OWNER-PHOTO-VISION"
PHOTO_VISION_AT = "2026-11-28T16:50:00Z"
PHOTO_VISION_GIVEN_AT = datetime(2026, 11, 28, 16, 50, tzinfo=timezone.utc)
DIRECTIVES: dict[str, dict] = {
    DIRECTIVE_ID: {"at": DIRECTIVE_AT, "given_at": GIVEN_AT, "sunset": SUNSET,
                   "actor": ACTOR},
    PHOTO_VISION_ID: {"at": PHOTO_VISION_AT, "given_at": PHOTO_VISION_GIVEN_AT,
                      "sunset": PHOTO_VISION_GIVEN_AT + EXPIRY,
                      "actor": f"owner-directive:{PHOTO_VISION_ID}"},
}
TRIPLE_DIRECTIVE: dict[tuple[str, str], str] = {
    ("anthropic-vision", "vision"): PHOTO_VISION_ID,
}


def directive_for(provider: str, scope: str) -> tuple[str, dict]:
    """The (directive id, spec) that authorises a triple in `ACTIVATIONS`."""
    did = TRIPLE_DIRECTIVE.get((str(provider), str(scope)), DIRECTIVE_ID)
    return did, DIRECTIVES[did]

# Owner decisions that RAISE a directive activation's ceilings after it was written. `apply`
# writes each activation once and never renews it; an amendment only lifts a live row's
# daily and per-gallery ceilings up to `ACTIVATIONS` (never its monthly ceiling, its expiry or
# its call ceilings), once, audited as AMEND_ACTION. Adding one is a reviewed code change.
AMEND_ACTION = "owner_directive.amended"
AMENDMENTS: dict[tuple[str, str], dict] = {
    ("flux-3-image", "generation"): {
        "decision": "D-OWNER-PHOTO-BUDGET",
        "decided_at": datetime(2026, 11, 28, 0, 0, tzinfo=timezone.utc),
        "fields": ("daily_ceiling_cad", "per_gallery_cad"),
        "owner_words": "up the photo budget i dont care. Get it right.",
    },
}


# AUDIT F-07 / D-OWNER-AUDIT-APPROVALS (owner, 2026-11-22 ~06:10Z: "I approve my stuff. Fix
# the rest. Get p0 done."): a publication-gate waiver used to be authorised by a heading in the
# shipped decision index, so any commit adding a heading waived a gate. A waiver now needs an
# entry in this fixed table AND the heading. Each entry names the owner's decision, when it was
# given, and the directive that grants it standing. It is recorded as
# `owner_directed_without_attestation`: no step-up or signature happened, and nothing here
# claims one. Adding a waiver is a code change to this table, reviewed like `ACTIVATIONS`.
AUDIT_APPROVALS_ID = "D-OWNER-AUDIT-APPROVALS"
AUDIT_APPROVALS_AT = datetime(2026, 11, 22, 6, 10, tzinfo=timezone.utc)
WAIVERS: dict[str, dict] = {
    "D-OWNER-PUBLISH-WITH-RENDERS": {
        "gate": "SAMPLE_PHOTO_REQUIRED",
        "decided_at": datetime(2026, 11, 21, 10, 50, tzinfo=timezone.utc),
        "granted_under": AUDIT_APPROVALS_ID,
        "evidence": "owner_directed_without_attestation",
    },
}


def waiver_granted(decision_id: str, gate: str, *, now: datetime | None = None) -> bool:
    """Whether `decision_id` is a standing owner waiver of exactly `gate` (fail closed)."""
    try:
        w = WAIVERS.get(str(decision_id))
        if not w or w["gate"] != str(gate):
            return False
        now = _aware(now) or datetime.now(timezone.utc)
        return now >= w["decided_at"]
    except Exception:  # noqa: BLE001 - an unreadable table waives nothing
        return False


def recognised(step_up: dict | None, provider: str, scope: str) -> bool:
    """Whether a row's evidence is this directive, for exactly a triple it covers."""
    su = step_up or {}
    if (str(provider), str(scope)) not in ACTIVATIONS:
        return False
    did, _spec = directive_for(provider, scope)
    return su.get("owner_directive") == did


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)


def authorises(row) -> bool:
    """B19-SEC S2: whether a stored row carries this directive's authority. Only a row written
    inside the directive's window, with ceilings no wider than `ACTIVATIONS` and the gate's
    default call ceilings, and a lifetime no longer than EXPIRY. Any other row bearing the
    directive's name authorises nothing (fail closed)."""
    from ..gateway import paid_provider_gate as G

    try:
        if not recognised(row.step_up, row.provider, row.scope):
            return False
        _did, spec = directive_for(row.provider, row.scope)
        if str(row.activated_by or "") != spec["actor"]:
            return False
        if (row.step_up or {}).get("session_public_id"):
            return False                       # a directive row never claims a login
        ceil = ACTIVATIONS[(str(row.provider), str(row.scope))]
        for k in ("daily_ceiling_cad", "monthly_ceiling_cad", "per_gallery_cad"):
            v = float(getattr(row, k))
            if not (v == v) or v <= 0 or v > ceil[k] + 1e-9:
                return False
        if not 1 <= int(row.max_attempts_per_request or 0) <= G.DEFAULT_MAX_ATTEMPTS:
            return False
        if not 1 <= int(row.max_calls_per_run or 0) <= G.DEFAULT_MAX_CALLS_PER_RUN:
            return False
        at, exp = _aware(row.activated_at), _aware(row.expires_at)
        if (at is None or exp is None or at < spec["given_at"] - _SLACK
                or at > spec["sunset"]):
            return False
        return exp - at <= EXPIRY + _SLACK
    except Exception:  # noqa: BLE001 - unreadable evidence authorises nothing
        return False


def apply(db, *, now: datetime | None = None) -> dict:
    """Write each directive activation once. Idempotent; never renews; never raises."""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from ..gateway import providers as gw
    from ..gateway import paid_provider_gate as G

    now = _aware(now) or datetime.now(timezone.utc)
    out = {"directive": DIRECTIVE_ID, "activated": [], "already": [], "refused": []}
    try:
        G.ensure_tables(db)
        company = gw.monthly_ceiling_cad()
    except Exception as exc:  # noqa: BLE001 - an unreadable store activates nothing
        out["refused"].append({"why": f"store unreadable: {type(exc).__name__}"})
        return out
    for (provider, scope), ceil in ACTIVATIONS.items():
        did, spec = directive_for(provider, scope)
        actor = spec["actor"]
        if not spec["given_at"] <= now <= spec["sunset"]:
            out["refused"].append({"activation": f"{provider}:{scope}",
                                   "why": f"outside {did}'s window "
                                          f"{spec['given_at'].isoformat()}.."
                                          f"{spec['sunset'].isoformat()}; never renewed by "
                                          "the system"})
            continue
        expires = min(now + EXPIRY, spec["sunset"])
        try:
            # B19-SEC S3: check-and-write under the spend lock (pg advisory / BEGIN IMMEDIATE)
            # so a booting web process and the hourly job cannot both write the triple.
            with gw.budget_lock(db) as s:
                prior = s.scalar(select(G.PaidProviderActivation).where(
                    G.PaidProviderActivation.provider == provider,
                    G.PaidProviderActivation.scope == scope,
                    G.PaidProviderActivation.activated_by == actor).limit(1))
                if prior is not None:
                    out["already"].append(f"{provider}:{scope}")
                    amended = _amend(s, prior, provider, scope, ceil, now)
                    if amended:
                        out.setdefault("amended", []).append(amended)
                    continue
                if ceil["monthly_ceiling_cad"] > company:
                    out["refused"].append({"activation": f"{provider}:{scope}",
                                           "why": "exceeds the company monthly ceiling"})
                    continue
                row = G.PaidProviderActivation(
                    provider=provider, scope=scope, activated_by=actor, activated_at=now,
                    step_up={"owner_directive": did, "directive_at": spec["at"],
                             "session_public_id": None, "step_up_performed": False},
                    daily_ceiling_cad=ceil["daily_ceiling_cad"],
                    monthly_ceiling_cad=ceil["monthly_ceiling_cad"],
                    per_gallery_cad=ceil["per_gallery_cad"],
                    max_attempts_per_request=G.DEFAULT_MAX_ATTEMPTS,
                    max_calls_per_run=G.DEFAULT_MAX_CALLS_PER_RUN,
                    expires_at=expires,
                    note=f"owner directive {did} ({spec['at']}); no step-up")
                s.add(row)
                s.flush()
                s.add(AuditLog(at=now, actor=actor[:64], action=ACTION,
                               artifact=f"{provider}:{scope}",
                               detail={"directive": did, "activation_id": row.id,
                                       **ceil, "expires_at": expires.isoformat()}))
                out["activated"].append(f"{provider}:{scope}")
        except Exception as exc:  # noqa: BLE001 - one failure never blocks the other
            # B19-SEC: the exception's type only; its text (SQL, DSN fragments) stays out of
            # the job summary and the audit row it lands in.
            out["refused"].append({"activation": f"{provider}:{scope}",
                                   "why": type(exc).__name__})
    return out


def _amend(s, row, provider: str, scope: str, ceil: dict, now: datetime) -> dict | None:
    """Raise a live directive row's amended ceilings to `ACTIVATIONS` (AMENDMENTS). Only up,
    only the named fields, only a row that still authorises and is neither revoked nor
    expired. Returns what changed, or None."""
    from ..core.models import AuditLog

    am = AMENDMENTS.get((provider, scope))
    if not am or now < am["decided_at"]:
        return None
    if row.revoked_at is not None:
        return None
    exp = _aware(row.expires_at)
    if exp is None or exp <= now or not authorises(row):
        return None
    changed = {}
    for k in am["fields"]:
        old, new = float(getattr(row, k)), float(ceil[k])
        if new > old + 1e-9:
            setattr(row, k, new)
            changed[k] = {"from": old, "to": new}
    if not changed:
        return None
    s.add(AuditLog(at=now, actor=ACTOR[:64], action=AMEND_ACTION,
                   artifact=f"{provider}:{scope}",
                   detail={"decision": am["decision"], "activation_id": row.id,
                           "changed": changed,
                           "monthly_ceiling_cad": float(row.monthly_ceiling_cad)}))
    return {"activation": f"{provider}:{scope}", "decision": am["decision"], **changed}
