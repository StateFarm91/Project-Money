"""The access approval protocol, and the rule that stops a missing capability being faked.

Requirements 223 and 224. The owner has said they will approve reasonable access for the
mandatory benchmark observation and for 24/7 autonomy, and wrote the limit into the same
sentence: *"this is not blanket authorization for unbounded spending or credentials."*

Those two halves are what this module is. A capability the system does not have becomes a
**structured approval request** the owner can answer in one reading -- exact purpose, the
capability it unlocks, what it costs at most, what it can see, what happens if they decline
and what continues regardless. And until that request is answered, the capability stays
**unavailable and says so**, because the tempting failure here is not asking for too much: it
is quietly substituting search snippets for the mandated observation and reporting the mandate
as met.

Three properties, each against a specific way this goes wrong:

**A request names a ceiling, and the ceiling is enforced in code.** "Approve model access" with
no number is a blank cheque, and an approval the owner cannot bound is one they should refuse.
Every request carries `max_cost_cad` and, for anything recurring, a monthly ceiling that
`SpendLimit` enforces after approval rather than a promise to be careful.

**Willingness is not approval.** Nothing here grants itself. A capability is available only
when its credential is actually present in the environment, and `available()` asks the
environment, never the request.

**A degraded substitute is never evidence.** #224: if anti-bot controls, authentication or
tooling prevent the mandated depth, report the exact limitation and keep the requirement
unmet. `accept_evidence` refuses to let a search snippet, a manual screenshot or a seeded
fixture count as benchmark observation -- it is allowed to exist, clearly labelled, and it is
never allowed to close the requirement.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .readiness import OwnerRequest

# ---------------------------------------------------------------------------
# Evidence grades (#224)
#
# The distinction that matters is not "good data / bad data". It is whether a piece of
# evidence is capable of satisfying the mandate at all. A screenshot can be true, useful and
# worth keeping, and still not be continuous cloud observation.

MANDATED = "mandated"        # produced by the capability the spec requires
SUPPORTING = "supporting"    # true and useful, cannot close the requirement
INADMISSIBLE = "inadmissible"  # must not be recorded as benchmark evidence at all

EVIDENCE_GRADES: dict[str, str] = {
    # What #221/#222 actually ask for.
    "browser_traversal": MANDATED,
    "gallery_image_observation": MANDATED,
    "listing_metadata_capture": MANDATED,
    "official_api_read": MANDATED,
    # Real, and explicitly named in #221 as things that must not silently replace the above.
    "search_snippet": SUPPORTING,
    "manual_screenshot": SUPPORTING,
    "seeded_fixture": SUPPORTING,
    "text_only_search": SUPPORTING,
    "stale_cache": SUPPORTING,
    # Never. Copying a competitor's photograph is out of bounds whatever it would prove.
    "copied_competitor_asset": INADMISSIBLE,
}


class EvidenceRefused(Exception):
    """Evidence that may not be recorded, or may not count for what it was offered for."""


@dataclass(frozen=True)
class Acceptance:
    """What a piece of evidence is allowed to do."""

    kind: str
    grade: str
    satisfies_mandate: bool
    note: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "grade": self.grade,
                "satisfies_mandate": self.satisfies_mandate, "note": self.note}


def accept_evidence(kind: str, *, capability_available: bool) -> Acceptance:
    """Grade a piece of benchmark evidence. Never upgrades it.

    The one judgement call is deliberate: mandated-kind evidence produced while the capability
    is unavailable is downgraded to supporting. Otherwise a fixture labelled
    `browser_traversal` would satisfy the mandate by naming itself after it, which is the
    silent downgrade #224 exists to prevent, wearing the right hat.
    """
    grade = EVIDENCE_GRADES.get(kind)
    if grade is None:
        raise EvidenceRefused(
            f"unknown evidence kind {kind!r}: grade it in EVIDENCE_GRADES before recording it, "
            f"because an ungraded kind defaults to whatever the caller hoped for")
    if grade == INADMISSIBLE:
        raise EvidenceRefused(
            f"{kind!r} may never be recorded as benchmark evidence (competitor assets are "
            f"studied, never reproduced)")
    if grade == MANDATED and not capability_available:
        return Acceptance(kind, SUPPORTING, False,
                          "labelled as mandated observation but produced without the "
                          "capability, so it is recorded as supporting evidence only")
    return Acceptance(kind, grade, grade == MANDATED,
                      "" if grade == MANDATED else
                      "real evidence, and cannot close a requirement that asks for "
                      "continuous cloud observation")


# ---------------------------------------------------------------------------
# Access requests (#223)


@dataclass(frozen=True)
class AccessRequest:
    """One thing only the owner can grant, in the shape the Execution Directive requires.

    Carries more than an `OwnerRequest` because #223 asks for more: the capability unlocked,
    the security scope of what is being handed over, and what the company keeps doing if the
    answer is no. `as_owner_request()` renders it into the consolidated owner queue rather
    than starting a second queue beside it -- section 14 is explicit that there is one.
    """

    key: str
    capability: str
    action: str
    purpose: str
    unlocks: str
    security_scope: str
    max_cost_cad: float
    monthly_ceiling_cad: float
    minutes: int
    consequence_of_declining: str
    continues_without: str
    requirement_ids: tuple[int, ...] = ()
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # A request the owner cannot bound is one they should refuse, so it is not allowed to
        # exist. Recurring cost with no monthly ceiling is the blank cheque #223 forbids.
        if self.monthly_ceiling_cad < 0 or self.max_cost_cad < 0:
            raise ValueError(f"{self.key}: a negative ceiling is not a ceiling")
        if self.max_cost_cad > 0 and self.monthly_ceiling_cad == 0 and "one-off" not in self.action:
            raise ValueError(
                f"{self.key}: a recurring cost needs a monthly ceiling, or the action must "
                f"say it is one-off")

    def as_owner_request(self) -> OwnerRequest:
        reason = (f"{self.purpose} Unlocks: {self.unlocks} "
                  f"Security scope: {self.security_scope} "
                  f"If declined: {self.consequence_of_declining} "
                  f"Continues regardless: {self.continues_without}")
        return OwnerRequest(
            key=self.key, action=self.action, reason=reason,
            max_cost_cad=self.max_cost_cad, minutes=self.minutes,
            consequence_of_delay=self.consequence_of_declining,
            blocks=self.capability)

    def to_dict(self) -> dict:
        return {
            "key": self.key, "capability": self.capability, "action": self.action,
            "purpose": self.purpose, "unlocks": self.unlocks,
            "security_scope": self.security_scope,
            "max_cost_cad": self.max_cost_cad,
            "monthly_ceiling_cad": self.monthly_ceiling_cad,
            "minutes": self.minutes,
            "consequence_of_declining": self.consequence_of_declining,
            "continues_without": self.continues_without,
            "requirement_ids": list(self.requirement_ids),
            "options": list(self.options),
        }


# ---------------------------------------------------------------------------
# Capabilities
#
# Each capability asks the environment whether it exists. None of them can grant itself, and
# an absent credential is absent -- the same discipline as `opsauth`, for the same reason.


@dataclass(frozen=True)
class Capability:
    key: str
    name: str
    env_vars: tuple[str, ...]
    request: AccessRequest
    requirement_ids: tuple[int, ...] = field(default_factory=tuple)

    def available(self, env: dict[str, str] | None = None) -> bool:
        e = env if env is not None else os.environ
        return all((e.get(v) or "").strip() for v in self.env_vars)

    def status(self, env: dict[str, str] | None = None) -> dict:
        ok = self.available(env)
        return {
            "key": self.key, "name": self.name, "available": ok,
            "requires": list(self.env_vars),
            "requirement_ids": list(self.requirement_ids),
            # Deliberately not "pending" or "in progress". A capability nobody has granted is
            # unavailable, and the report says the word.
            "state": "available" if ok else "unavailable — awaiting owner approval",
            "request": None if ok else self.request.to_dict(),
        }


BENCHMARK_OBSERVATION = AccessRequest(
    key="benchmark_observation",
    capability="mandatory MJsOffTheHookDesigns benchmark observation (#221, #222)",
    action=("Register a free Etsy developer app, then set TWO Railway variables on the "
            "brambleloop-os service: ETSY_API_KEY = the app's keystring, and "
            "ETSY_SHARED_SECRET = the app's shared secret. Etsy v3 sends them joined as "
            "'keystring:shared_secret' in one header, which the code does — paste each value "
            "whole, do not join them by hand. Read-only public data: not a shop, not a payout "
            "account, no OAuth. One-off, no cost."),
    purpose=("The v1.4.3 master makes observation of MJsOffTheHookDesigns a non-negotiable "
             "top priority, from cloud infrastructure, with your devices off."),
    unlocks=("Resolving the canonical shop, enumerating the catalogue, reading listing text, "
             "price, tags and gallery image URLs on a schedule, and routing every observation "
             "into the category pods. Image-level understanding additionally needs the model "
             "credential below."),
    security_scope=("The keystring reads public marketplace data only. It cannot see your "
                    "account, cannot list, cannot spend and cannot message anyone. It is set "
                    "in the hosting environment and never in the repository."),
    max_cost_cad=0.0,
    monthly_ceiling_cad=0.0,
    minutes=15,
    consequence_of_declining=("The named benchmark mandate stays formally unmet and is "
                              "reported as unmet rather than approximated. No competitive "
                              "evidence about the benchmark shop enters the pods."),
    continues_without=("Every other Build-2 requirement: the pods, the gap queue, the "
                       "lead-time engine, the pattern engine, the catalogue and the "
                       "acceptance gates all build and run without it. Only the observation "
                       "itself is blocked."),
    requirement_ids=(206, 221, 222, 301, 319),
    options=(
        "Etsy Open API v3 — free, read-only, the platform's own sanctioned route. Verified "
        "against Etsy's published OpenAPI specification: the nine endpoints this mission "
        "uses are all served by the API key alone, with no OAuth scope. Nothing here claims "
        "a call has been made; the credential does not exist yet.",
        "A managed cloud browser (roughly CA$40-70 per month) for the rendered page only — "
        "badges, sale banners as presented, thumbnail crop in search. NOT currently "
        "requested: the API covers the mandate's substance, and this is presentation detail "
        "recorded as an unmet fraction rather than claimed.",
        "Neither, and the requirement is reported unmet. This is a real option and the "
        "system will not degrade into search snippets to avoid it (#224).",
    ),
)

MODEL_CREDENTIAL = AccessRequest(
    key="model_provider",
    capability="language and vision model access for the agent swarm (#221 image "
               "understanding, #177-194 continuous learning)",
    action=("Set ONE Railway variable on the brambleloop-os service: ANTHROPIC_API_KEY = an "
            "Anthropic API key. The CA$25 monthly ceiling is already enforced in code — "
            "gateway/routing.py refuses a call before making it once the month's ledgered "
            "spend would cross it, and there is no override."),
    purpose=("No provider is configured today, so every agent runs on deterministic code and "
             "templates. That is why the catalogue is engineered rather than written, and why "
             "no image can be described."),
    unlocks=("Image-level observation of benchmark galleries, listing copy that is written "
             "rather than assembled, the critique and improvement loops, and the continuous "
             "learning architecture."),
    security_scope=("An API key for the model vendor only. It reaches no Etsy account, no "
                    "bank, no customer and no repository. Spend is metered per agent against "
                    "ceilings that already exist and already halt work when breached."),
    max_cost_cad=25.0,
    monthly_ceiling_cad=25.0,
    minutes=10,
    consequence_of_declining=("The company stays deterministic: correct, cheap, and unable to "
                              "look at a photograph or write in a voice."),
    continues_without=("The whole deterministic spine — CIR, compiler, twin, reverse "
                       "compiler, gates, pricing, scheduling — which is the part that must "
                       "never depend on a model anyway."),
    requirement_ids=(221, 222, 177, 178),
)

CAPABILITIES: tuple[Capability, ...] = (
    Capability(key="benchmark_observation",
               name="MJs benchmark observation (read-only marketplace data)",
               env_vars=("ETSY_API_KEY", "ETSY_SHARED_SECRET"),
               request=BENCHMARK_OBSERVATION,
               requirement_ids=(206, 221, 222, 301, 319)),
    Capability(key="model_provider", name="language and vision model access",
               env_vars=("BRAMBLELOOP_MODEL_KEY_PRESENT",), request=MODEL_CREDENTIAL,
               requirement_ids=(221, 177, 178)),
)


def _model_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """A provider key under any of its real names satisfies the model capability.

    The capability is declared against one sentinel rather than listing every vendor variable
    in `env_vars`, because `available()` requires all of them and requiring both vendors'
    keys would be wrong.
    """
    e = dict(env if env is not None else os.environ)
    present = any((e.get(v) or "").strip()
                  for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BRAMBLELOOP_MODEL_KEY"))
    e["BRAMBLELOOP_MODEL_KEY_PRESENT"] = "1" if present else ""
    return e


def statuses(env: dict[str, str] | None = None) -> list[dict]:
    e = _model_env(env)
    return [c.status(e) for c in CAPABILITIES]


def available(key: str, env: dict[str, str] | None = None) -> bool:
    e = _model_env(env)
    for c in CAPABILITIES:
        if c.key == key:
            return c.available(e)
    raise KeyError(f"unknown capability {key!r}")


def pending_requests(env: dict[str, str] | None = None) -> list[AccessRequest]:
    """The access batch, in the order the owner should read it: free and unblocking first."""
    e = _model_env(env)
    out = [c.request for c in CAPABILITIES if not c.available(e)]
    return sorted(out, key=lambda r: (r.max_cost_cad, r.minutes))


def owner_requests(env: dict[str, str] | None = None) -> list[OwnerRequest]:
    return [r.as_owner_request() for r in pending_requests(env)]


def unmet_report(env: dict[str, str] | None = None) -> dict:
    """#224, as a report rather than a promise.

    Names the capability, the exact limitation, and the requirements that stay unmet because
    of it. Nothing in this report is softened by what the system did instead.
    """
    e = _model_env(env)
    unmet = [c for c in CAPABILITIES if not c.available(e)]
    blocked: list[int] = sorted({i for c in unmet for i in c.requirement_ids})
    return {
        "capabilities": statuses(e),
        "unmet_capabilities": [c.key for c in unmet],
        "requirements_unmet_for_want_of_access": blocked,
        "substituted": False,
        "statement": ("No mandated observation has been performed. Nothing in this system "
                      "reports benchmark coverage from search snippets, screenshots or seeded "
                      "fixtures, and evidence of those kinds is graded as supporting and "
                      "cannot close a requirement (#224).") if unmet else
                     "Every declared capability is available.",
    }
