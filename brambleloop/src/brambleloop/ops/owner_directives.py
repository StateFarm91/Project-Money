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

# (provider, scope) -> ceilings. Image generation for the 7-photo galleries, and the second,
# independent vision judge. Nothing else: no ads, no text-model widening, no company ceiling.
ACTIVATIONS: dict[tuple[str, str], dict] = {
    ("flux-3-image", "generation"): {"daily_ceiling_cad": 5.0, "monthly_ceiling_cad": 40.0,
                                     "per_gallery_cad": 2.5},
    ("openai-vision", "vision"): {"daily_ceiling_cad": 2.0, "monthly_ceiling_cad": 10.0,
                                  "per_gallery_cad": 1.0},
}


def recognised(step_up: dict | None, provider: str, scope: str) -> bool:
    """Whether a row's evidence is this directive, for exactly a triple it covers."""
    su = step_up or {}
    return (su.get("owner_directive") == DIRECTIVE_ID
            and (str(provider), str(scope)) in ACTIVATIONS)


def apply(db, *, now: datetime | None = None) -> dict:
    """Write each directive activation once. Idempotent; never renews; never raises."""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from ..gateway import anthropic as gw
    from ..gateway import paid_provider_gate as G

    now = now or datetime.now(timezone.utc)
    out = {"directive": DIRECTIVE_ID, "activated": [], "already": [], "refused": []}
    try:
        G.ensure_tables(db)
        company = gw.monthly_ceiling_cad()
    except Exception as exc:  # noqa: BLE001 - an unreadable store activates nothing
        out["refused"].append({"why": f"store unreadable: {type(exc).__name__}"})
        return out
    for (provider, scope), ceil in ACTIVATIONS.items():
        try:
            with db.session() as s:
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
                    expires_at=now + EXPIRY,
                    note=f"owner directive {DIRECTIVE_ID} ({DIRECTIVE_AT}); no step-up")
                s.add(row)
                s.flush()
                s.add(AuditLog(at=now, actor=ACTOR[:64], action=ACTION,
                               artifact=f"{provider}:{scope}",
                               detail={"directive": DIRECTIVE_ID, "activation_id": row.id,
                                       **ceil, "expires_at": (now + EXPIRY).isoformat()}))
                out["activated"].append(f"{provider}:{scope}")
        except Exception as exc:  # noqa: BLE001 - one failure never blocks the other
            out["refused"].append({"activation": f"{provider}:{scope}",
                                   "why": f"{type(exc).__name__}: {str(exc)[:120]}"})
    return out
