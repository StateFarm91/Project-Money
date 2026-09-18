"""The access approval protocol, and the rule that a missing capability stays missing.

Requirements 223 and 224. The owner said they would approve reasonable access and, in the
same sentence, that this is not blanket authorization. Both halves are testable, and the half
that is easy to lose is the second one: the failure mode here is not asking for too much, it
is quietly substituting something cheaper for a capability nobody granted and reporting the
mandate as met.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import OwnerAction  # noqa: E402
from brambleloop.launch import access  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402


def test_a_capability_nobody_granted_is_unavailable_and_says_the_word():
    """Willingness is not approval, and 'pending' is not a state a capability gets to sit in.

    The owner's stated willingness to approve access is what makes the request reasonable to
    make. It is not the grant. `available()` asks the environment and nothing else, so no
    amount of intent in a conversation can turn a capability on.
    """
    empty: dict[str, str] = {}
    assert access.available("benchmark_observation", empty) is False
    assert access.available("model_provider", empty) is False

    for status in access.statuses(empty):
        assert status["available"] is False
        assert "unavailable" in status["state"]
        assert status["request"] is not None

    # And a credential that is actually present turns exactly one of them on.
    with_key = {"ETSY_API_KEY": "a-read-only-keystring"}
    assert access.available("benchmark_observation", with_key) is True
    assert access.available("model_provider", with_key) is False

    # Any of the provider variables satisfies the model capability; requiring all of them
    # would mean the company needed two vendors before it could describe one photograph.
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BRAMBLELOOP_MODEL_KEY"):
        assert access.available("model_provider", {var: "k"}) is True


def test_a_search_snippet_cannot_close_a_requirement_that_asks_for_observation():
    """#224, which is the requirement that stops #221 being satisfied by wishful labelling.

    Supporting evidence is real and worth keeping. What it may never do is satisfy a mandate
    that asks for continuous cloud observation, because a company that believes it is watching
    its benchmark and is not has a worse problem than one that knows it is blind.
    """
    for kind in ("search_snippet", "manual_screenshot", "seeded_fixture",
                 "text_only_search", "stale_cache"):
        a = access.accept_evidence(kind, capability_available=True)
        assert a.satisfies_mandate is False, kind
        assert a.grade == access.SUPPORTING, kind


def test_evidence_labelled_as_observation_is_downgraded_when_nothing_observed_it():
    """The silent downgrade wearing the right hat.

    A fixture named `browser_traversal` is the exact shape this goes wrong in: the label says
    mandated, the capability was never granted, and nothing in the record would show it. So
    the grade is decided by whether the capability existed, not by what the caller called it.
    """
    granted = access.accept_evidence("browser_traversal", capability_available=True)
    assert granted.satisfies_mandate is True
    assert granted.grade == access.MANDATED

    ungranted = access.accept_evidence("browser_traversal", capability_available=False)
    assert ungranted.satisfies_mandate is False
    assert ungranted.grade == access.SUPPORTING
    assert "without the capability" in ungranted.note


def test_a_competitor_photograph_is_refused_outright_and_an_unknown_kind_is_not_guessed():
    """Two refusals for two different reasons.

    Copying a competitor's photography is out of bounds whatever it would prove (#305, and a
    standing constraint), so it is not gradeable -- it is refused. An unknown kind is refused
    because a default would be whatever the caller hoped for, and the whole point of grading
    is that the grade does not come from the caller.
    """
    for kind in ("copied_competitor_asset", "a_kind_nobody_graded"):
        try:
            access.accept_evidence(kind, capability_available=True)
        except access.EvidenceRefused:
            pass
        else:
            raise AssertionError(f"{kind!r} was accepted")


def test_every_request_is_bounded_and_carries_the_directive_format():
    """An approval the owner cannot bound is one they should refuse.

    The Execution Directive says every owner action states the exact action, why it is
    required, the maximum cost, the minutes and the consequence of waiting; #223 adds the
    capability unlocked and the security scope. Missing any of them turns a decision into a
    conversation, which is what batching them exists to avoid.
    """
    requests = access.pending_requests({})
    assert requests, "the access batch is empty, which can only be right once everything is granted"

    for r in requests:
        for field_name in ("action", "purpose", "unlocks", "security_scope",
                           "consequence_of_declining", "continues_without", "capability"):
            value = getattr(r, field_name)
            assert value and len(value) > 20, f"{r.key}.{field_name} is not an answer"
        assert r.minutes > 0, r.key
        assert r.max_cost_cad >= 0 and r.monthly_ceiling_cad >= 0
        # The blank-cheque guard: a recurring cost with no ceiling.
        if r.max_cost_cad > 0:
            assert r.monthly_ceiling_cad > 0 or "one-off" in r.action, r.key
        assert r.requirement_ids, f"{r.key} does not say which requirements it unblocks"

    # Declining has to be a real option that is described, not a formality.
    assert any("unmet" in r.consequence_of_declining for r in requests)


def test_a_request_that_recurs_without_a_ceiling_cannot_be_constructed():
    """The guard is in the type, not in a review.

    "Approve model access" with no number is the request #223 forbids, and a rule that lives
    in a docstring is one a future session writes around at 3am.
    """
    kwargs = dict(
        key="unbounded", capability="c" * 30, action="Approve something recurring",
        purpose="p" * 30, unlocks="u" * 30, security_scope="s" * 30,
        max_cost_cad=40.0, monthly_ceiling_cad=0.0, minutes=5,
        consequence_of_declining="d" * 30, continues_without="w" * 30,
        requirement_ids=(1,))
    try:
        access.AccessRequest(**kwargs)
    except ValueError as e:
        assert "ceiling" in str(e)
    else:
        raise AssertionError("an unbounded recurring request was constructed")

    # The same request, declared one-off, is fine -- the ceiling exists to bound repetition.
    access.AccessRequest(**{**kwargs, "action": "Pay a one-off registration fee"})


def test_the_unmet_report_never_claims_a_substitute_was_used():
    """What a report about a missing capability is for.

    #224 asks for the exact limitation and the requirement preserved as unmet. A report that
    led with what the system did instead would be the downgrade, written down.
    """
    report = access.unmet_report({})
    assert report["unmet_capabilities"] == ["benchmark_observation", "model_provider"]
    assert report["substituted"] is False
    assert 221 in report["requirements_unmet_for_want_of_access"]
    assert 222 in report["requirements_unmet_for_want_of_access"]
    assert "No mandated observation has been performed" in report["statement"]

    everything = {"ETSY_API_KEY": "k", "ANTHROPIC_API_KEY": "k"}
    granted = access.unmet_report(everything)
    assert granted["unmet_capabilities"] == []
    assert granted["requirements_unmet_for_want_of_access"] == []


def test_access_requests_join_the_one_owner_queue_and_do_not_duplicate_on_re_run():
    """Section 14 says one consolidated owner queue, and the reason is arithmetic.

    Two queues means the owner reads whichever they remember. So the capability requests go
    through the same `launch.readiness` job, with the same requirement-key identity that
    stopped the fee approval appearing twice -- which means running the job again must change
    nothing.
    """
    from sqlalchemy import select

    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime.worker import Worker

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/access.sqlite")
    db.create_all()
    Registry(db).seed_defaults()

    def run(key: str) -> None:
        JobQueue(db).enqueue("orchestrator", "launch.readiness", {}, idempotency_key=key)
        worker = Worker(db, "access-worker")
        for _ in range(200):
            if not worker.run_once():
                break

    run("access-1")
    with db.session() as s:
        first = {a.requirement_key for a in s.scalars(select(OwnerAction))}
    assert "benchmark_observation" in first, sorted(first)
    assert "model_provider" in first, sorted(first)

    run("access-2")
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction)))
    keys = [a.requirement_key for a in rows]
    assert len(keys) == len(set(keys)), sorted(keys)
    assert set(keys) == first

    # The queued row must still be readable on its own: an owner reading the queue sees the
    # capability, the cost and the consequence without opening an API.
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "model_provider"))
        assert "Unlocks:" in row.reason and "Security scope:" in row.reason
        assert row.max_cost_cad == 25.0
        assert row.minutes > 0


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
