"""D-OWNER-APPROVE-ALL-3: the owner's standing directive approves every owner card the system can
act on, recorded `owner_directed_without_attestation` (never a step-up, a login or an attestation).

* every press bucket is approved through the press's own code (`execute_items(directive=...)`);
* child-family cards and cards needing a ruling are approved as the owner's ruling;
* physical-attestation cards are WITHDRAWN without attestation, never `satisfied`, and the copy
  guard still refuses a made-sample claim;
* spend stays inside the CA$100/month cap; ceiling raises and unstated amounts stay listed;
* outside acts (OAuth, payout, KYC-class) stay listed: code cannot do them;
* idempotent, window-bounded, and nobody else can claim the directive.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_approve_all_3.py
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_approve_all_v2 as V  # noqa: E402 - the same sandbox and seed helpers

from brambleloop.app.command_center import approve_everything as AE  # noqa: E402
from brambleloop.ops import approve_all_directive as AD  # noqa: E402
from brambleloop.ops import owner_queue  # noqa: E402
from brambleloop.publish import sample_photo  # noqa: E402
from brambleloop.visual import laura_approval  # noqa: E402

DB = V.DB
NOW = AD.GIVEN_AT + timedelta(hours=1)
STAYS = (AE.OUTSIDE, AE.SPEND_OVER_CAP, AE.SPEND_NO_AMOUNT, AE.SPEND_CEILING_RAISE,
         AE.PUBLISHING_COVERED)


def _run():
    ids = V.seed()
    mark = V.mark()
    with V.World():
        out = AD.apply(DB, now=NOW)
    return ids, mark, out


def test_every_card_the_system_can_act_on_is_approved():
    ids, _mark, out = _run()
    assert out["ran"] and out["error"] is None, out
    st = V.states()
    for key, (bucket, _c, _b) in V.ROWS.items():
        rid = ids[key]
        if bucket in STAYS:
            assert st[rid] == owner_queue.OPEN, (key, st[rid])
        elif bucket == AE.NEVER_PHYSICAL:
            assert st[rid] == owner_queue.WITHDRAWN, (key, st[rid])
        else:
            assert st[rid] in owner_queue.CLOSED_STATES, (key, st[rid])
    # child-family and ruling cards: approved as the owner's ruling.
    for key in ("childrens-decision:baby-rattle", "portfolio.rework:baby-safety-rattle",
                "decision.api_vision_equivalence", "phase", "correction_notice:moss-throw"):
        assert st[ids[key]] == owner_queue.SATISFIED, key
    # what stays is listed with a reason.
    listed = {i.get("requirement_key") for i in out["still_listed"] if "id" in i}
    for key, (bucket, _c, _b) in V.ROWS.items():
        if bucket in (AE.OUTSIDE, AE.SPEND_OVER_CAP, AE.SPEND_NO_AMOUNT,
                      AE.SPEND_CEILING_RAISE):
            assert key in listed, (key, listed)


def test_nothing_is_recorded_as_a_step_up_or_an_attestation():
    _ids, mark, _out = _run()
    rows = (V.audits(AE.ROW_AUDIT_ACTION, mark) + V.audits(AD.ROW_ACTION, mark)
            + V.audits(AE.GRANT_AUDIT_ACTION, mark))
    assert rows
    for actor, _art, d in rows:
        assert actor == AD.ACTOR[:64], actor
        assert d.get("step_up") is False, d
        assert d.get("directive") == AD.DIRECTIVE_ID, d
        # the sample cards keep naming the directive that resolves them (renders, no sample).
        assert d.get("owner_directive") in (AD.DIRECTIVE_ID, AE.DIRECTIVE_RENDERS), d
        assert d.get("owner_approved_via_step_up") in (None, False), d
        assert d.get("attested") in (None, False), d
    # Etsy grants are signed only inside the owner's own request: the directive signs none
    # and lists them for the owner's press.
    assert V.audits(AE.GRANT_AUDIT_ACTION, mark) == []
    with V.World():
        out = AD.apply(DB, now=NOW + timedelta(minutes=1))
    cards = {i.get("card") for i in out["still_listed"] if i.get("bucket") ==
             "owner_grant_signature"}
    assert cards == {"publication:moss-throw@1", "activation:hex-coaster@2"}, out


def test_physical_cards_are_withdrawn_without_attestation_and_copy_guard_holds():
    ids, mark, _out = _run()
    rid = ids["physical_size_conflict:moss-throw@1"]
    rows = [d for _a, art, d in V.audits(AD.ROW_ACTION, mark) if art == f"owner_action:{rid}"]
    assert rows and rows[0]["to"] == owner_queue.WITHDRAWN
    assert rows[0]["attested"] is False and rows[0]["sample_exists"] is False
    # Approving the card never lets copy claim a made sample.
    assert sample_photo.copy_problems("I made this blanket and tested every row.",
                                      photographed_sample=False)


def test_spend_stays_inside_the_cap():
    ids, mark, _out = _run()
    st = V.states()
    assert st[ids["benchmark_refresh:granny-square"]] == owner_queue.SATISFIED
    assert st[ids["knowledge_gap:amigurumi-eyes"]] == owner_queue.SATISFIED
    assert st[ids["benchmark_challenge"]] == owner_queue.OPEN           # CA$300 > headroom
    assert st[ids["spend.ceiling.model_monthly"]] == owner_queue.OPEN   # no ceiling raise
    approved = sum(d["amount_cad"] for _a, _r, d in V.audits(AE.SPEND_AUDIT_ACTION, mark))
    assert approved <= 100.0 - V.SPENT_CAD + 1e-9, approved


def test_idempotent_and_window_bounded():
    _run()
    before = V.states()
    with V.World():
        again = AD.apply(DB, now=NOW + timedelta(minutes=5))
    assert again["approved"] == 0 and again["closed_kept"] == 0, again
    assert V.states() == before
    with V.World():
        late = AD.apply(DB, now=AD.SUNSET + timedelta(seconds=5))
    assert not late["ran"] and late["error"], late


def test_nobody_else_can_claim_the_directive():
    V.seed()
    with V.World():
        try:
            AE.execute_items(DB, actor="owner-directive:D-OWNER-APPROVE-ALL-3", items=["x"],
                             confirm=True, directive="D-SOMETHING-ELSE")
        except AE.Refused:
            pass
        else:
            raise AssertionError("a forged directive id was accepted")
        try:
            AE.execute_items(DB, actor="system", items=["x"], confirm=True,
                             directive=AD.DIRECTIVE_ID)
        except AE.Refused:
            pass
        else:
            raise AssertionError("a forged directive actor was accepted")
    try:
        laura_approval._decide_in(None, DB, None, decision=laura_approval.APPROVED,
                                  actor="system", step_up=False, via="x", now=NOW,
                                  owner_directive=AD.DIRECTIVE_ID)
    except laura_approval.Refused:
        pass
    else:
        raise AssertionError("a Laura decision with a forged directive actor was accepted")


def test_visibility_is_counts_only():
    _run()
    v = AD.visibility(DB)
    last = v["last_run"]
    assert last["ran"] is True and isinstance(last["approved"], int)
    for k in last["still_listed_by_bucket"]:
        assert k in AE.KEPT + AE.ACTED + ("other", "owner_grant_signature"), k


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
