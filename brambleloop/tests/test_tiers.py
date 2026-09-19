"""How fast the company may change itself, and the four ways that speed becomes a rewrite.

v1.4.3 requirement 178, whose own sentence is the specification: never equate "continuous"
with "unsupervised rewriting of the company". Learning may happen as fast as evidence
arrives; promotion may not, and the gap between those two is the requirement.

What is tested is mostly the classifier, because it is the load-bearing part: a change is
graded by what it touches, never by what it is called, and the description is the part
somebody chooses.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import tiers as T  # noqa: E402

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/tiers.sqlite")
    db.create_all()
    return db


def _promote(db, tier: str, *, hours_ago: float) -> None:
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="improvement", action="improve.promoted", artifact=tier,
                       at=NOW - timedelta(hours=hours_ago),
                       detail={"tier": tier, "summary": "an earlier change"}))


# ---- classification is by surface, never by description -------------------


def test_a_change_is_graded_by_its_riskiest_surface():
    assert T.classify(("weights",)).key == "scoring"
    assert T.classify(("weights", "prompt")).key == "prompt"
    assert T.classify(("weights", "spend_limit")).key == "gate"


def test_a_spend_change_described_as_a_scoring_tweak_is_still_a_spend_change():
    """The description is the part somebody chooses, so the check does not read it."""
    try:
        T.check_promotion(_db(), touches=("spend_limit",),
                          evidence=(T.BASELINE, T.SANDBOX_RESULT),
                          declared_tier="scoring", now=NOW)
    except T.TierRefused as e:
        assert "never by what it is called" in str(e)
    else:
        raise AssertionError("a spend change was promoted through the scoring lane")


def test_an_unknown_surface_is_graded_upward_rather_than_downward():
    """Defaulting to the cheapest tier would make 'touch something the classifier has not
    heard of' the fast path, which is the first thing anybody would find."""
    assert T.classify(("some_surface_nobody_listed",)).key == "code"


def test_a_change_that_will_not_say_what_it_touches_cannot_be_graded():
    try:
        T.classify(())
    except T.TierRefused as e:
        assert "whichever lane its author felt like" in str(e)
    else:
        raise AssertionError("an ungraded change was classified")


def test_declaring_a_higher_tier_than_required_is_allowed():
    """Somebody being cautious is not somebody cheating."""
    state = T.check_promotion(_db(), touches=("weights",),
                              evidence=(T.BASELINE, T.SANDBOX_RESULT, T.ROLLBACK,
                                        T.REGRESSION_TEST),
                              declared_tier="tooling", now=NOW)
    assert state["tier"] == "scoring"


# ---- evidence -------------------------------------------------------------


def test_each_tier_requires_the_evidence_its_failure_mode_needs():
    db = _db()
    try:
        T.check_promotion(db, touches=("compiler",),
                          evidence=(T.BASELINE, T.SANDBOX_RESULT, T.ROLLBACK), now=NOW)
    except T.TierRefused as e:
        assert T.ADVERSARIAL_TEST in str(e)
        assert "keeps producing plausible output while being wrong" in str(e)
    else:
        raise AssertionError("a code change was promoted with no adversarial test")


def test_we_tested_it_is_not_a_kind_of_evidence():
    try:
        T.check_promotion(_db(), touches=("weights",),
                          evidence=(T.BASELINE, "we tested it"), now=NOW)
    except T.TierRefused as e:
        assert "not a recognised kind" in str(e)
    else:
        raise AssertionError("free-text evidence was accepted")


def test_the_gate_tier_never_promotes_without_a_person():
    db = _db()
    full = (T.BASELINE, T.SANDBOX_RESULT, T.ROLLBACK, T.REGRESSION_TEST, T.ADVERSARIAL_TEST)
    try:
        T.check_promotion(db, touches=("policy",), evidence=full, now=NOW)
    except T.TierRefused as e:
        assert T.OWNER_APPROVAL in str(e)
        assert "not recoverable by reverting" in str(e)
    else:
        raise AssertionError("a policy change promoted itself")

    allowed = T.check_promotion(db, touches=("policy",),
                                evidence=full + (T.OWNER_APPROVAL,), now=NOW)
    assert allowed["needs_owner"] is True
    assert "does not promote without a person" in allowed["note"]


# ---- cooldown and ceiling -------------------------------------------------


def test_a_second_promotion_inside_the_cooldown_is_refused():
    """Six changes to one surface in an afternoon cannot be attributed to anything, and the
    attribution is what makes the next change an improvement rather than a guess."""
    db = _db()
    _promote(db, "scoring", hours_ago=1)
    try:
        T.check_promotion(db, touches=("weights",),
                          evidence=(T.BASELINE, T.SANDBOX_RESULT), now=NOW)
    except T.TierRefused as e:
        assert "cooldown" in str(e)
    else:
        raise AssertionError("a promotion landed inside its own cooldown")


def test_the_cooldown_expires():
    db = _db()
    _promote(db, "scoring", hours_ago=T.TIER_BY_KEY["scoring"].cooldown_hours + 1)
    state = T.check_promotion(db, touches=("weights",),
                              evidence=(T.BASELINE, T.SANDBOX_RESULT), now=NOW)
    assert state["promotions_this_week"] == 1


def test_the_weekly_ceiling_stops_a_company_rewriting_itself_faster_than_it_can_look():
    db = _db()
    scoring = T.TIER_BY_KEY["scoring"]
    for i in range(scoring.weekly_ceiling):
        _promote(db, "scoring", hours_ago=scoring.cooldown_hours + 1 + i * 2)

    try:
        T.check_promotion(db, touches=("weights",),
                          evidence=(T.BASELINE, T.SANDBOX_RESULT), now=NOW)
    except T.TierRefused as e:
        assert "faster than it can observe" in str(e)
    else:
        raise AssertionError("the weekly ceiling did not hold")


def test_promotions_older_than_a_week_do_not_count_against_the_ceiling():
    db = _db()
    for i in range(T.TIER_BY_KEY["scoring"].weekly_ceiling + 3):
        _promote(db, "scoring", hours_ago=24 * 9 + i)

    state = T.check_promotion(db, touches=("weights",),
                              evidence=(T.BASELINE, T.SANDBOX_RESULT), now=NOW)
    assert state["promotions_this_week"] == 0


def test_one_tier_spending_its_week_does_not_block_another():
    db = _db()
    scoring = T.TIER_BY_KEY["scoring"]
    for i in range(scoring.weekly_ceiling):
        _promote(db, "scoring", hours_ago=scoring.cooldown_hours + 1 + i * 2)

    state = T.check_promotion(db, touches=("prompt",),
                              evidence=(T.BASELINE, T.SANDBOX_RESULT, T.ROLLBACK), now=NOW)
    assert state["tier"] == "prompt"


def test_the_ceilings_get_tighter_as_the_surface_gets_riskier():
    ranks = sorted(T.TIERS, key=lambda t: t.rank)
    for lower, higher in zip(ranks, ranks[1:]):
        assert higher.weekly_ceiling <= lower.weekly_ceiling, (lower.key, higher.key)
        assert higher.cooldown_hours >= lower.cooldown_hours, (lower.key, higher.key)
        assert set(lower.requires) <= set(higher.requires), (lower.key, higher.key)


def test_the_state_report_counts_rows_rather_than_intentions():
    db = _db()
    _promote(db, "prompt", hours_ago=30)
    rows = {r["tier"]: r for r in T.state(db, now=NOW)["tiers"]}

    assert rows["prompt"]["promotions_this_week"] == 1
    assert rows["prompt"]["hours_since"] == 30.0
    assert rows["code"]["promotions_this_week"] == 0
    assert rows["gate"]["needs_owner"] is True


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
