"""The server-side half of an OAuth authorization-code flow: state, verifier, credential.

Two jobs, kept in one module because they are two ends of one credential's life:

1. **Across the browser round trip.** A handshake is opened when the authorize URL is built
   and closed when the redirect comes back, minutes later, in a different request and quite
   possibly on a different container. What has to survive is the state (so the callback can
   tell its own flow from somebody else's) and the PKCE verifier (without which the code
   cannot be exchanged at all).
2. **After it.** The refresh token Etsy returns is stored sealed, and *rotated* by
   compare-and-set, because Etsy issues a new one on every refresh and spends the old one.

Everything here is written in terms of rejections rather than in terms of success, because
the callback route is the one endpoint in this system whose entire job is to decline things.
`Verdict` is the vocabulary: every refusal has its own name, the name reaches the operator's
browser, the audit row and the HTTP status, and no two refusals share one.

**What this module will not do.** It never returns a token or a verifier in a report, never
writes either to a log, never puts either in an audit detail, and never stores a state in a
form that could be replayed out of the database. It refuses to store anything at all when
`core.sealed` has no key, rather than storing it in the clear.
"""
from __future__ import annotations

import enum
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from . import sealed
from .models import OAuthCredential, OAuthHandshake, utcnow

# 32 bytes of CSPRNG output, URL-safe. `secrets`, never `random`: `random` is a Mersenne
# Twister seeded from the clock, and 624 outputs of it determine every output after, which
# is the precise property a CSRF token must not have.
STATE_BYTES = 32

# How long an unfinished flow stays usable. The owner opens a URL, signs in, reads a consent
# screen and approves; fifteen minutes is generous for that and short enough that an
# authorize URL left in a browser history overnight is dead. Etsy's authorization code
# "expires quickly" in its own words, so a longer window here would buy nothing.
HANDSHAKE_TTL_SECONDS = 900

# How long a *spent* handshake is remembered. This is not housekeeping: it is what makes the
# difference between "this state was already used" and "no such state" answerable. Prune it
# too soon and a replay starts reporting as an unknown state -- still refused, and refused
# for a vaguer reason than the true one.
REPLAY_MEMORY_DAYS = 30

# The sealing contexts. Authenticated with the ciphertext, so the two sealed values in this
# system cannot be swapped for one another.
VERIFIER_CONTEXT = "oauth.pkce_verifier"
REFRESH_TOKEN_CONTEXT = "oauth.refresh_token"


class Verdict(str, enum.Enum):
    """Every way a callback can end, each distinguishable from all the others."""

    OK = "ok"
    # No `state` parameter at all. A callback Etsy would not have sent, because Etsy echoes
    # back exactly what the authorization request carried and this system always sends one.
    STATE_MISSING = "state_missing"
    # A state that no handshake in this database has ever held: a forged or foreign value,
    # or one minted by a deployment whose database this is not.
    STATE_UNKNOWN = "state_unknown"
    # A handshake that exists, was never used, and is past its deadline.
    STATE_EXPIRED = "state_expired"
    # A handshake that exists and has already been consumed. The interesting one: it is the
    # signature of a replayed redirect URL, and it is counted.
    STATE_REPLAYED = "state_replayed"
    # The row is there and its verifier will not open -- the sealing key changed, or the
    # value is damaged. Distinct from every state failure because the fix is different: this
    # one is a deployment problem, not a caller problem.
    VERIFIER_UNREADABLE = "verifier_unreadable"


class CredentialConflict(RuntimeError):
    """A rotation tried to replace a token that is no longer the one stored."""


def state_hash(state: str) -> str:
    return hashlib.sha256((state or "").encode("utf-8")).hexdigest()


def _aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes and Postgres aware ones; comparing them raises."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Handshake:
    """What `begin` produced. The state is returned once and never read back out of storage."""

    state: str
    verifier: str
    fingerprint: str
    expires_at: datetime
    row_id: int


@dataclass(frozen=True)
class Consumed:
    """The result of a callback's attempt to close a handshake.

    `verifier` is populated only on `Verdict.OK`, and it is the one value in this module that
    a caller is allowed to hold -- for the length of one `etsy_oauth.exchange` call.
    """

    verdict: Verdict
    verifier: str = ""
    redirect_uri: str = ""
    scopes: str = ""
    fingerprint: str = "absent"
    row_id: int | None = None
    replays: int = 0

    @property
    def ok(self) -> bool:
        return self.verdict is Verdict.OK

    def redacted(self) -> dict:
        """Safe for an audit row, a log line and an HTTP response body. No verifier."""
        return {"verdict": self.verdict.value, "state_fingerprint": self.fingerprint,
                "handshake": self.row_id, "replays": self.replays,
                "scopes": self.scopes}


# ---------------------------------------------------------------------------
# The browser round trip


def begin(db, *, provider: str = "etsy", verifier: str, redirect_uri: str,
          scopes: str = "", ttl_seconds: int = HANDSHAKE_TTL_SECONDS,
          started_by: str = "operator", env: dict[str, str] | None = None) -> Handshake:
    """Open a handshake: mint a state, seal the verifier, write the row.

    The verifier is generated by the caller (`etsy_oauth.new_verifier`) so that this module
    does not have to know Etsy's rules about verifier length; what it owns is the fact that
    the verifier is never written down unsealed and the state is never written down at all.

    Raises `sealed.SealUnavailable` when there is no sealing key. That refusal happens *here*,
    before the owner is sent to Etsy, which is deliberate: the alternative is discovering at
    the callback that the flow cannot be completed, after the authorization code has already
    been issued and spent.
    """
    state = secrets.token_urlsafe(STATE_BYTES)
    verifier_sealed = sealed.seal(verifier, context=VERIFIER_CONTEXT, env=env)
    now = utcnow()
    expires_at = now + timedelta(seconds=max(30, int(ttl_seconds)))
    row = OAuthHandshake(
        provider=provider,
        state_sha256=state_hash(state),
        state_fingerprint=sealed.fingerprint(state),
        verifier_sealed=verifier_sealed,
        redirect_uri=redirect_uri,
        scopes=scopes,
        created_at=now,
        expires_at=expires_at,
        outcome="open",
        started_by=started_by,
    )
    with db.session() as s:
        s.add(row)
        s.flush()
        row_id = row.id
    return Handshake(state=state, verifier=verifier,
                     fingerprint=sealed.fingerprint(state),
                     expires_at=expires_at, row_id=row_id)


def consume(db, *, provider: str = "etsy", state: str | None,
            now: datetime | None = None, env: dict[str, str] | None = None) -> Consumed:
    """Close a handshake exactly once, or say precisely why it cannot be closed.

    The claim is a single conditional UPDATE -- `consumed_at IS NULL AND expires_at > now` --
    so *the database* decides who wins. Two callbacks delivered simultaneously with the same
    valid state produce one `OK` and one `STATE_REPLAYED`; there is no window in which both
    read "unconsumed" and both proceed, which is the flaw in the obvious read-then-write
    version of this function.

    Only when that UPDATE changes nothing does this go looking for a reason, and the reasons
    are ordered most-specific-first: an already-consumed row is a replay even if it has since
    expired, because "somebody sent this twice" is the more useful thing to know.
    """
    if not (state or "").strip():
        return Consumed(verdict=Verdict.STATE_MISSING)

    now = now or utcnow()
    digest = state_hash(state)
    with db.session() as s:
        claimed = s.execute(
            update(OAuthHandshake)
            .where(OAuthHandshake.state_sha256 == digest,
                   OAuthHandshake.provider == provider,
                   OAuthHandshake.consumed_at.is_(None),
                   OAuthHandshake.expires_at > now)
            .values(consumed_at=now, outcome="claimed")
        ).rowcount
        row = s.scalar(select(OAuthHandshake).where(
            OAuthHandshake.state_sha256 == digest,
            OAuthHandshake.provider == provider))

        if row is None:
            # Nothing was claimed and nothing is there. Note that this is also the answer
            # for a state belonging to a different provider, which is correct: a handshake
            # opened for one API may not be closed by another's redirect.
            return Consumed(verdict=Verdict.STATE_UNKNOWN,
                            fingerprint=sealed.fingerprint(state))

        fingerprint = row.state_fingerprint or sealed.fingerprint(state)
        if not claimed:
            if row.consumed_at is not None:
                row.replays = int(row.replays or 0) + 1
                row.outcome = Verdict.STATE_REPLAYED.value
                return Consumed(verdict=Verdict.STATE_REPLAYED, fingerprint=fingerprint,
                                row_id=row.id, replays=row.replays)
            # Unconsumed and unclaimable means the deadline passed. Marked consumed on the
            # way out so that an expired handshake cannot be retried into existence by a
            # caller who waits for a clock skew to go their way.
            row.consumed_at = now
            row.outcome = Verdict.STATE_EXPIRED.value
            return Consumed(verdict=Verdict.STATE_EXPIRED, fingerprint=fingerprint,
                            row_id=row.id, replays=int(row.replays or 0))

        try:
            verifier = sealed.unseal(row.verifier_sealed, context=VERIFIER_CONTEXT, env=env)
        except (sealed.SealBroken, sealed.SealUnavailable):
            # The state was legitimate and the flow still cannot continue. The row stays
            # consumed: the state has been presented and must not be usable again, whatever
            # went wrong afterwards.
            row.outcome = Verdict.VERIFIER_UNREADABLE.value
            return Consumed(verdict=Verdict.VERIFIER_UNREADABLE, fingerprint=fingerprint,
                            row_id=row.id, replays=int(row.replays or 0))

        return Consumed(verdict=Verdict.OK, verifier=verifier,
                        redirect_uri=row.redirect_uri or "", scopes=row.scopes or "",
                        fingerprint=fingerprint, row_id=row.id,
                        replays=int(row.replays or 0))


def record_outcome(db, row_id: int | None, outcome: str) -> None:
    """Write what became of a consumed handshake. Never the reason in Etsy's own words.

    An Etsy error body can echo back whatever was sent to it, so only this system's own
    vocabulary is stored: `exchanged`, `exchange_failed`, `exchange_refused`.
    """
    if row_id is None:
        return
    with db.session() as s:
        row = s.get(OAuthHandshake, row_id)
        if row is not None:
            row.outcome = str(outcome)[:40]


def live_handshakes(db, *, provider: str = "etsy", now: datetime | None = None) -> int:
    """How many flows are open right now. Evidence, and never a list of states."""
    now = now or utcnow()
    with db.session() as s:
        rows = list(s.scalars(select(OAuthHandshake).where(
            OAuthHandshake.provider == provider,
            OAuthHandshake.consumed_at.is_(None))))
    return sum(1 for r in rows if (_aware(r.expires_at) or now) > now)


# ---------------------------------------------------------------------------
# The credential that outlives the flow


def save_refresh_token(db, token: str, *, provider: str = "etsy", scopes: str = "",
                       source: str = "", expected_fingerprint: str | None = None,
                       new_grant: bool = False, env: dict[str, str] | None = None) -> dict:
    """Store or rotate the sealed refresh token. Returns fingerprints, never a value.

    `expected_fingerprint` makes this a compare-and-set: the write succeeds only if the row
    still holds the token the caller thinks it is replacing. If another worker rotated first
    this raises `CredentialConflict` rather than writing, because the token this caller is
    holding has already been spent by Etsy and storing it would log the company out. Passing
    `None` is an unconditional write and is correct in exactly two cases -- a fresh grant,
    and a process adopting a row it did not load.

    `new_grant` is a separate flag rather than something inferred from the absence of a
    fingerprint, because the two unconditional cases differ in what they mean for the
    *chain*: a browser authorization starts a new 90-day chain and resets `rotations`, while
    a process adopting the row is joining a chain already in progress and must not.
    """
    if not (token or "").strip():
        raise ValueError("refusing to store an empty refresh token: an empty credential is "
                         "an absent one, and storing it would hide that")
    sealed_value = sealed.seal(token, context=REFRESH_TOKEN_CONTEXT, env=env)
    finger = sealed.fingerprint(token)
    key_finger = sealed.key_health(env)["key_fingerprint"]
    now = utcnow()

    with db.session() as s:
        row = s.get(OAuthCredential, provider)
        if row is None:
            if expected_fingerprint:
                raise CredentialConflict(
                    f"a rotation named the token it was replacing (***{expected_fingerprint}) "
                    f"and no {provider} credential is stored. Nothing was written: the "
                    f"company has to authorise again in a browser.")
            row = OAuthCredential(provider=provider, obtained_at=now, rotations=0)
            s.add(row)
        elif expected_fingerprint and row.token_fingerprint != expected_fingerprint:
            raise CredentialConflict(
                f"refusing to rotate the {provider} credential: this caller is replacing "
                f"***{expected_fingerprint} and the stored token is ***"
                f"{row.token_fingerprint or 'absent'}. Another worker rotated first, so the "
                f"token this one holds has already been spent by Etsy and writing it would "
                f"replace a live credential with a dead one.")
        elif expected_fingerprint:
            row.rotations = int(row.rotations or 0) + 1
        elif new_grant:
            # The owner has just approved the app in a browser: a new 90-day chain, so the
            # rotation count starts over. Keeping the old count would make the age of the
            # *chain* unreadable, which is the one thing the count is for.
            row.rotations = 0
            row.obtained_at = now
        else:
            row.rotations = int(row.rotations or 0) + 1

        row.refresh_token_sealed = sealed_value
        row.token_fingerprint = finger
        row.key_fingerprint = key_finger
        row.scopes = scopes or row.scopes or ""
        row.updated_at = now
        row.source = (source or row.source or "")[:80]
        rotations = int(row.rotations or 0)

    return {"provider": provider, "token_fingerprint": f"***{finger}",
            "key_fingerprint": f"***{key_finger}", "rotations": rotations,
            "stored": "sealed in oauth_credentials", "scopes": scopes}


def load_refresh_token(db, *, provider: str = "etsy",
                       env: dict[str, str] | None = None) -> str | None:
    """Open the stored credential, or return None. Raises nothing a caller must catch.

    A row that will not unseal returns None rather than raising: to every caller the answer
    is the same -- there is no usable credential and the owner has to authorise again -- and
    an exception here would turn a scheduled job into a dead letter instead of a refusal.
    """
    with db.session() as s:
        row = s.get(OAuthCredential, provider)
        stored = row.refresh_token_sealed if row is not None else ""
    if not stored:
        return None
    try:
        return sealed.unseal(stored, context=REFRESH_TOKEN_CONTEXT, env=env)
    except (sealed.SealBroken, sealed.SealUnavailable):
        return None


def credential_health(db, *, provider: str = "etsy",
                      env: dict[str, str] | None = None) -> dict:
    """Everything an operator needs to know about the credential except the credential."""
    with db.session() as s:
        row = s.get(OAuthCredential, provider)
        stored = bool(row and row.refresh_token_sealed)
        detail = {
            "provider": provider,
            "stored": stored,
            "token_fingerprint": f"***{row.token_fingerprint}" if stored else "absent",
            "sealed_under_key": f"***{row.key_fingerprint}" if stored else "absent",
            "rotations": int(row.rotations or 0) if row else 0,
            "scopes": (row.scopes or "") if row else "",
            "obtained_at": (_aware(row.obtained_at).isoformat()
                            if row is not None and row.obtained_at else None),
            "updated_at": (_aware(row.updated_at).isoformat()
                           if row is not None and row.updated_at else None),
            "source": (row.source or "") if row else "",
        }
    key = sealed.key_health(env)
    detail["sealing_key"] = {k: v for k, v in key.items() if k != "key_fingerprint"}
    detail["sealing_key"]["fingerprint"] = f"***{key['key_fingerprint']}"
    # The check that matters and that nothing else can make: a stored credential sealed under
    # a key the deployment no longer has is a credential that is gone, and it looks present
    # in every other report.
    detail["openable"] = bool(
        stored and key["usable"] and detail["sealed_under_key"] == f"***{key['key_fingerprint']}")
    return detail


def prune_handshakes(db, *, now: datetime | None = None, dry_run: bool = False,
                     days: int = REPLAY_MEMORY_DAYS) -> dict:
    """Forget spent handshakes once a replay of them is no longer worth distinguishing.

    Two rules, and the first is the one with teeth: **a live handshake is never deleted at
    any age**, because deleting one turns a legitimate callback into `state_unknown` and
    strands the owner mid-flow. The second is the replay window -- see `REPLAY_MEMORY_DAYS`.
    """
    now = now or utcnow()
    cutoff = now - timedelta(days=max(1, int(days)))
    removed = 0
    kept = {"live": 0, "inside_replay_window": 0}
    with db.session() as s:
        for row in list(s.scalars(select(OAuthHandshake))):
            if row.consumed_at is None and (_aware(row.expires_at) or now) > now:
                kept["live"] += 1
                continue
            when = _aware(row.consumed_at) or _aware(row.expires_at) or now
            if when >= cutoff:
                kept["inside_replay_window"] += 1
                continue
            if not dry_run:
                s.delete(row)
            removed += 1
    return {"table": "oauth_handshakes", "dry_run": bool(dry_run),
            "deletable" if dry_run else "removed": removed, "kept": kept,
            "replay_memory_days": int(days), "cutoff": cutoff.isoformat(),
            "why": ("a spent handshake is what lets a replayed callback be answered with "
                    "'this state was already used' instead of 'no such state'. A live one is "
                    "never deleted at any age: deleting it strands the owner mid-flow")}
