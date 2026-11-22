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
    ("flux-3-image", "generation"): {"daily_ceiling_cad": 5.0, "monthly_ceiling_cad": 40.0,
                                     "per_gallery_cad": 2.5},
    ("openai-vision", "vision"): {"daily_ceiling_cad": 2.0, "monthly_ceiling_cad": 10.0,
                                  "per_gallery_cad": 1.0},
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
    return (su.get("owner_directive") == DIRECTIVE_ID
            and (str(provider), str(scope)) in ACTIVATIONS)


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
        if str(row.activated_by or "") != ACTOR:
            return False
        if not recognised(row.step_up, row.provider, row.scope):
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
        if at is None or exp is None or at < GIVEN_AT - _SLACK or at > SUNSET:
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
    if not GIVEN_AT <= now <= SUNSET:
        out["refused"].append({"why": f"outside the directive's window {GIVEN_AT.isoformat()}"
                                      f"..{SUNSET.isoformat()}; never renewed by the system"})
        return out
    expires = min(now + EXPIRY, SUNSET)
    try:
        G.ensure_tables(db)
        company = gw.monthly_ceiling_cad()
    except Exception as exc:  # noqa: BLE001 - an unreadable store activates nothing
        out["refused"].append({"why": f"store unreadable: {type(exc).__name__}"})
        return out
    for (provider, scope), ceil in ACTIVATIONS.items():
        try:
            # B19-SEC S3: check-and-write under the spend lock (pg advisory / BEGIN IMMEDIATE)
            # so a booting web process and the hourly job cannot both write the triple.
            with gw.budget_lock(db) as s:
                prior = s.scalar(select(G.PaidProviderActivation).where(
                    G.PaidProviderActivation.provider == provider,
                    G.PaidProviderActivation.scope == scope,
                    G.PaidProviderActivation.activated_by == ACTOR).limit(1))
                if prior is not None:
                    out["already"].append(f"{provider}:{scope}")
                    continue
                if ceil["monthly_ceiling_cad"] > company:
                    out["refused"].append({"activation": f"{provider}:{scope}",
                                           "why": "exceeds the company monthly ceiling"})
                    continue
                row = G.PaidProviderActivation(
                    provider=provider, scope=scope, activated_by=ACTOR, activated_at=now,
                    step_up={"owner_directive": DIRECTIVE_ID, "directive_at": DIRECTIVE_AT,
                             "session_public_id": None, "step_up_performed": False},
                    daily_ceiling_cad=ceil["daily_ceiling_cad"],
                    monthly_ceiling_cad=ceil["monthly_ceiling_cad"],
                    per_gallery_cad=ceil["per_gallery_cad"],
                    max_attempts_per_request=G.DEFAULT_MAX_ATTEMPTS,
                    max_calls_per_run=G.DEFAULT_MAX_CALLS_PER_RUN,
                    expires_at=expires,
                    note=f"owner directive {DIRECTIVE_ID} ({DIRECTIVE_AT}); no step-up")
                s.add(row)
                s.flush()
                s.add(AuditLog(at=now, actor=ACTOR[:64], action=ACTION,
                               artifact=f"{provider}:{scope}",
                               detail={"directive": DIRECTIVE_ID, "activation_id": row.id,
                                       **ceil, "expires_at": expires.isoformat()}))
                out["activated"].append(f"{provider}:{scope}")
        except Exception as exc:  # noqa: BLE001 - one failure never blocks the other
            # B19-SEC: the exception's type only; its text (SQL, DSN fragments) stays out of
            # the job summary and the audit row it lands in.
            out["refused"].append({"activation": f"{provider}:{scope}",
                                   "why": type(exc).__name__})
    return out
