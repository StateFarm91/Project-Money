"""The hard-coded protected invariants no self-improvement proposal may touch (directive §4).

`improve.governance` reads a hypothesis's *words* and refuses one that would weaken a gate.
That is the right net for prose and the wrong one for a parameter change: a policy loop
proposes `{"min_shared": 3}`, not a sentence. So this is the structural half, applied to the
parameter a proposal would change:

1. **A named protected invariant is refused outright.** Product Truth, customer truth and
   safety, accounting truth, authorization, security, spend controls and evidence
   requirements are listed here by name and by the vocabulary their thresholds are spelled
   in. The list is hard-coded on purpose: a list the loop could edit is a list the loop
   would eventually edit.
2. **Every protected constant the governance scan finds is refused too** (UPPERCASE
   constants of the gates, cir, publish, quality, visual, learn and improve packages) -- including
   this engine's own evidence floors, so the loop cannot lower the sample size it is judged
   on.
3. **Anything not declared tunable by a loop is refused.** An unknown parameter is treated
   as protected, never as free: defaulting to "allowed" would make "name something the
   guard has not heard of" the fast path.
4. **A tunable value outside its hard bounds is refused**, as is a value that is not a
   finite number.

A refusal is a verdict, never an exception swallowed: the caller records it durably
(`learn_proposals`, state REFUSED) and audits it, so a refused proposal is as visible as a
promoted one.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from . import governance


@dataclass(frozen=True)
class Invariant:
    key: str
    protects: str
    # Substrings of a normalised parameter name that place it on this invariant.
    vocabulary: tuple[str, ...]


PROTECTED_INVARIANTS: tuple[Invariant, ...] = (
    Invariant("product_truth",
              "the certified CIR is the only source of what a pattern says; compiler, "
              "reverse compiler, twin and certification thresholds are not tunable",
              ("truth", "cir", "compil", "reverse", "stitch_count", "certif", "gauge_tol",
               "twin", "validat", "originality", "benchmark_quarantine")),
    # W3-B2 wiring 2 (W3-WIRE4): the owner's canonical brand assets (D-FB-17). Which bytes
    # are the brand, which roles they fill and which owner decisions authorise a change are
    # the owner's; a proposal naming them is refused, never ranked against them.
    Invariant("brand_canonical_assets",
              "the owner's canonical brand assets (brand.canonical_assets), the owner "
              "decisions that authorise a brand change (AUTHORISED_BRAND_CHANGES) and the "
              "canonical brand roles (brand_role)",
              ("canonical_asset", "authorised_brand_change", "authorized_brand_change",
               "brand_change", "brand_role", "canonical_brand")),
    Invariant("customer_safety",
              "customer truth and safety: disclosures, child-safety statements, escalation, "
              "consent and CASL rules",
              ("safety", "child", "choking", "age_grade", "allergen", "disclos", "casl",
               "consent", "escalat", "complaint", "unsubscribe", "claim")),
    Invariant("accounting_truth",
              "accounting derives from reconciled records; nothing tunes a ledger, tax or "
              "reconciliation tolerance",
              ("ledger", "reconcil", "tax", "revenue", "accrual", "payout", "bookkeep",
               "accounting", "deposit")),
    Invariant("authorization",
              "owner authority, approvals, phase, roles and credentials",
              ("auth", "token", "owner", "approv", "permission", "role", "grant", "phase",
               "credential", "shadow_mode", "publish")),
    Invariant("security",
              "security controls: CSP, secrets, CSRF, escaping, encryption",
              ("csp", "secret", "csrf", "encrypt", "sanitiz", "escape", "signature", "hmac")),
    Invariant("spend_controls",
              "budget ceilings and spend limits enforced in code",
              ("spend", "budget", "ceiling", "cap_cad", "limit_cad", "cost_ceiling",
               "max_cost", "daily_cost", "ads_", "bid")),
    Invariant("evidence_requirements",
              "sample floors, holdouts, baselines, margins and confidence the loop is judged by",
              ("evidence", "min_sample", "sample_size", "min_rows", "holdout", "baseline",
               "margin", "significan", "confidence", "min_decisions", "min_matched",
               "min_fresh", "regression", "tolerance", "observation_days")),
    Invariant("protected_gates",
              "every protected gate in improve.governance, and any refusal or block threshold",
              tuple(governance.PROTECTED_GATES) + ("gate", "refus", "block_threshold",
                                                   "pass_threshold", "policy")),
)

BY_KEY: dict[str, Invariant] = {i.key: i for i in PROTECTED_INVARIANTS}


@dataclass(frozen=True)
class Verdict:
    ok: bool
    param: str
    invariant: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "param": self.param, "invariant": self.invariant,
                "reason": self.reason}


def canonical_key(name) -> str:
    """One spelling for a parameter name (J-product P-6), used by the guard AND the readers.

    NFKC (fullwidth/compatibility forms fold to ASCII), format characters such as zero-width
    spaces stripped, lower-cased, and every run of non-alphanumerics (hyphen, space, dot)
    collapsed to one underscore. "Min-Shared", "min_shared<ZWSP>" and "ｍｉｎ_shared" are all
    `min_shared` -- so an alias can neither slip past a protected-word match nor reach a
    reader that looks the key up by its declared name.
    """
    text = unicodedata.normalize("NFKC", str(name or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


_norm = canonical_key


def canonical_payload(params: dict) -> tuple[dict, list[str]]:
    """The payload with canonical keys, and the canonical keys more than one key spelled."""
    out: dict = {}
    twins: list[str] = []
    for k, v in (params or {}).items():
        ck = canonical_key(k)
        if ck in out:
            twins.append(ck)
        out[ck] = v
    return out, sorted(set(twins))


def protected_invariant(param: str) -> Invariant | None:
    """The protected invariant a parameter name lands on, or None."""
    key = _norm(param)
    if not key:
        return BY_KEY["evidence_requirements"]
    for invariant in PROTECTED_INVARIANTS:
        if any(word in key for word in invariant.vocabulary):
            return invariant
    # Protected constants of protected packages, discovered from source by governance.
    upper = (param or "").strip()
    if upper in governance.protected_constants() or key.upper() in \
            governance.protected_constants():
        return BY_KEY["protected_gates"]
    return None


def check(param: str, value, *, tunable: dict | None = None) -> Verdict:
    """May a self-improvement proposal set `param` to `value`?

    `tunable` is the loop's declaration: {"param": name, "lo": .., "hi": .., "integer": ..}.
    The order is the order of seriousness: a protected invariant is reported as that even
    when the parameter is also undeclared.
    """
    hit = protected_invariant(param)
    if hit is not None:
        return Verdict(False, param, hit.key,
                       f"{param!r} is on the protected invariant {hit.key!r} ({hit.protects}). "
                       f"Self-improvement may never change it, in either direction, without "
                       f"the owner changing the code")
    if not tunable or _norm(param) != _norm(tunable.get("param", "")):
        return Verdict(False, param, "undeclared_surface",
                       f"{param!r} is not a parameter any policy loop declares tunable. An "
                       f"undeclared surface is treated as protected, never as free")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or \
            not math.isfinite(float(value)):
        return Verdict(False, param, "malformed_value",
                       f"{value!r} is not a finite number")
    if tunable.get("integer") and float(value) != int(value):
        return Verdict(False, param, "malformed_value", f"{param} takes whole numbers")
    lo, hi = float(tunable["lo"]), float(tunable["hi"])
    if not lo <= float(value) <= hi:
        return Verdict(False, param, "hard_bounds",
                       f"{value} is outside the hard bounds [{lo}, {hi}] declared for {param}")
    return Verdict(True, param)


def check_payload(params: dict, *, tunable: dict) -> list[Verdict]:
    """Every key of a proposed payload, checked; the refusals only."""
    if not isinstance(params, dict) or not params:
        return [Verdict(False, "", "malformed_value", "a proposal names what it changes")]
    out = [v for v in (check(k, val, tunable=tunable) for k, val in params.items())
           if not v.ok]
    _canon, twins = canonical_payload(params)
    for ck in twins:
        out.append(Verdict(False, ck, "malformed_value",
                           f"{ck!r} is spelled by more than one key in one payload; an "
                           f"ambiguous proposal is refused rather than resolved by key order"))
    return out


def describe() -> dict:
    return {"invariants": [{"key": i.key, "protects": i.protects,
                            "vocabulary": list(i.vocabulary)} for i in PROTECTED_INVARIANTS],
            "also_protected": ("every UPPERCASE constant of the gates, cir, publish, quality, learn, "
                               "visual and improve packages (improve.governance scan), and "
                               "every parameter no policy loop declares tunable"),
            "enforced_at": ["proposal (submit/cycle)", "cross-agent challenge",
                            "execution (before the registry incumbent changes)",
                            "read (a registry value outside bounds falls back to the code "
                            "default and is reported)"]}
