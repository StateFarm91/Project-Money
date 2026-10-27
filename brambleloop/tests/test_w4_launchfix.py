"""W4-LAUNCHFIX: the engineering deadlocks on the path to the first Etsy listing.

Each defect has three kinds of test, named in the function:
  *_deadlock_*  the old behaviour, reproduced: it fails on the pre-fix code (b0133916);
  *_refuses_*   the gate still refuses without evidence (and on forged / stale / partial ones);
  *_passes_*    the gate passes only on genuine evidence, written the way production writes it.

D1  gates.first_customer.check_etsy_remote_state read a static gap list that never empties.
D2  launch.readiness `listing_fees` and `brand_clearance` were hard-coded ready=False.
E3  record_page_reading compared a person's first page reading with the repository excerpt.
E4  the category matcher on the shape of Etsy's real tree (names from production evidence).
CC  the Command Center policy-readings form (#/policy).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_launchfix.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import re
import socket
import sys
import tempfile
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="w4_launchfix_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'lf.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-LAUNCHFIX harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import approvals, auth  # noqa: E402
from brambleloop.app.command_center import policy_readings as PR  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Listing, PolicySnapshot  # noqa: E402
from brambleloop.gates import first_customer as FC  # noqa: E402
from brambleloop.gates import platform_policy as PP  # noqa: E402
from brambleloop.integrations import etsy_exercise as EX  # noqa: E402
from brambleloop.publish import listing_schema as LS  # noqa: E402

PASS = "owner passphrase for the launchfix harness"
OPS = "L" * 40
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()

RESULTS: list[str] = []


def ok(name: str) -> None:
    RESULTS.append(name)
    print(f"OK {name}")


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


# =============================================================================================
# D1 -- etsy_remote_state judges recorded round-trip evidence

LIVE = EX.LIVE_STATUS_PREFIX + ". The shop was read back and holds no test draft."
LOCAL = "RAN AGAINST A LOCAL MODEL OF ETSY, NOT ETSY."


def _blocking_claims() -> list[str]:
    return sorted({g["claim"] for g in LS.gaps() if g.get("blocks_launch") and g.get("claim")})


def _run(db, claims: dict[str, str], *, ok_=True, mode="full", status=LIVE, drafts=("901",),
         removed=True):
    """The rows `etsy_exercise.run` writes, in its order: draft created, removed (only when a
    read of Etsy confirmed it gone), finished with the per-claim states."""
    for lid in drafts:
        EX._audit(db, EX.DRAFT_CREATED, {"listing_id": lid, "title": "DO NOT BUY"})
        if removed:
            EX._audit(db, EX.DRAFT_REMOVED, {"listing_id": lid, "verified": True})
    EX._audit(db, EX.RUN_FINISHED, {
        "mode": mode, "ok": ok_, "status": status, "shop_is_clean": removed, "rotations": 3,
        "against_etsy": status.startswith(EX.LIVE_STATUS_PREFIX),
        "claims": [{"claim": c, "state_after": st} for c, st in claims.items()]})


def _all_verified() -> dict[str, str]:
    return {c: "VERIFIED_AGAINST_ETSY" for c in _blocking_claims()}


def test_d1_deadlock_the_static_gap_list_never_empties_yet_evidence_now_clears_it():
    # The deadlock's cause is unchanged and still true: the static list is not empty, and
    # nothing a run records can shorten it (it is code).
    assert LS.gaps(), "the static gap list is empty; this test would prove nothing"
    blocking = _blocking_claims()
    assert blocking, "no launch-blocking Etsy claim; nothing to verify"
    db = _db()
    _run(db, _all_verified())
    # Pre-fix: check_etsy_remote_state() took no evidence and returned UNVERIFIABLE whenever
    # gaps() was non-empty, so this was UNVERIFIABLE for ever (TypeError on the db argument).
    check = FC.check_etsy_remote_state(db)
    assert check.state == FC.PASS, check
    assert not check.blocks
    ok("D1 deadlock: gaps() is still non-empty, and a genuine live round trip now clears it")


def test_d1_refuses_without_evidence_or_on_anything_less_than_a_live_full_clean_run():
    assert FC.check_etsy_remote_state().state == FC.UNVERIFIABLE           # no database
    assert "authenticated" in FC.check_etsy_remote_state().detail
    db = _db()
    assert FC.check_etsy_remote_state(db).state == FC.UNVERIFIABLE         # nothing recorded
    cases = {
        "local model, even claiming verified": dict(status=LOCAL),
        "live but not ok": dict(ok_=False),
        "live rotation-only run": dict(mode="rotation"),
        "stranded draft": dict(removed=False),
    }
    for label, kw in cases.items():
        db = _db()
        _run(db, _all_verified(), **kw)
        st = FC.check_etsy_remote_state(db).state
        assert st == FC.UNVERIFIABLE, (label, st)
    # One launch-blocking claim missing from the live run.
    db = _db()
    partial = _all_verified()
    partial.pop(_blocking_claims()[0])
    _run(db, partial)
    c = FC.check_etsy_remote_state(db)
    assert c.state == FC.UNVERIFIABLE and _blocking_claims()[0] in c.detail, c
    # A live run recorded before this change carries no claims: it proves nothing per claim.
    db = _db()
    EX._audit(db, EX.DRAFT_CREATED, {"listing_id": "7"})
    EX._audit(db, EX.DRAFT_REMOVED, {"listing_id": "7"})
    EX._audit(db, EX.RUN_FINISHED, {"mode": "full", "ok": True, "status": LIVE})
    assert FC.check_etsy_remote_state(db).state == FC.UNVERIFIABLE
    ok("D1 refuses: no db, nothing, local model, not ok, rotation, stranded, partial, old row")


def test_d1_a_later_contradiction_fails_and_a_newer_live_run_is_what_counts():
    db = _db()
    _run(db, _all_verified())
    _run(db, {"array_encoding_tags": "CONTRADICTED"}, ok_=False, status="ATTEMPTED -- x")
    c = FC.check_etsy_remote_state(db)
    assert c.state == FC.FAIL and "array_encoding_tags" in c.detail, c
    # Only the newest live full ok run counts: an older complete run followed by a newer live
    # run that verified less does not pass.
    db = _db()
    _run(db, _all_verified())
    partial = _all_verified()
    partial.pop(_blocking_claims()[-1])
    _run(db, partial, drafts=("902",))
    assert FC.check_etsy_remote_state(db).state == FC.UNVERIFIABLE
    ok("D1 refuses: a later CONTRADICTED claim is a FAIL; only the newest live run counts")


def test_d1_passes_only_on_a_live_full_clean_run_verifying_every_blocking_claim():
    db = _db()
    _run(db, {**_all_verified(), "taxonomy_patterns_id": "IMPLEMENTED"})
    c = FC.check_etsy_remote_state(db)
    assert c.state == FC.PASS, c
    for claim in _blocking_claims():
        assert claim in c.detail
    # The evidence reader states exactly what it read.
    ev = EX.remote_state_evidence(db)
    assert ev["round_trip_clean"] and ev["live_run_id"] and not ev["contradicted_claims"]
    assert set(_blocking_claims()) <= set(ev["verified_claims"])
    ok("D1 passes: live full ok run, every blocking claim VERIFIED, every draft removed")


def test_d1_the_gate_is_wired_with_its_database_everywhere_it_runs():
    src = (ROOT / "src/brambleloop/gates/first_customer.py").read_text()
    assert src.count("check_etsy_remote_state(db)") == 2, "gate_product must pass its db"
    assert "check_etsy_remote_state()" not in src.split("def check_etsy_remote_state")[1]
    fs = (ROOT / "src/brambleloop/launch/first_sale.py").read_text()
    assert "_safe(_remote, owner=OWNER)" not in fs and fs.count("_remote(db)") >= 2
    ok("D1 wiring: gate_product and the first-sale view pass the database")


# ---- D1: draft vs public listing vs fee-bearing writes, each behind its own approval --------

class _Wire:
    """A transport that records and refuses: any call reaching it is a failure to gate."""

    def __init__(self):
        self.calls = []

    def request(self, method, url, **kw):
        self.calls.append((method, url))
        raise AssertionError(f"reached the wire: {method} {url}")


def _client(**kw):
    from brambleloop.integrations.etsy import Credentials, EtsyClient

    wire = _Wire()
    creds = Credentials(api_key="k" * 24, access_token="t" * 24, shop_id="1",
                        shared_secret="s" * 10)
    return EtsyClient(wire, credentials=creds, **kw), wire


def _payload():
    from brambleloop.integrations.etsy import ListingPayload

    return ListingPayload(title="A test", description="d", price=5.0, tags=["a"],
                          materials=["cotton"])


def test_d1_refuses_a_draft_activation_or_fee_bearing_write_without_its_own_approval():
    from brambleloop.integrations.etsy import EtsyNotPermitted

    # Phase and the owner flag both say "publish", and still: no draft without the owner's
    # verified publication grant (OwnerGrant), and nothing reaches Etsy.
    c, wire = _client(phase="limited_production", owner_authorised=True)
    for fn in (lambda: c.create_draft(_payload()),
               lambda: c.activate("55", launch_authorisation=""),
               lambda: c.activate("55", launch_authorisation="LAUNCH-0", grant=None),
               lambda: c.update_listing("55", {"title": "x"}),
               lambda: c.delete_listing("55")):
        try:
            fn()
        except EtsyNotPermitted:
            pass
        else:
            raise AssertionError("an ungated Etsy write was allowed")
    assert wire.calls == [], wire.calls
    # The draft-only lane (the CA$0 exercise) can never activate or set state=active.
    c, wire = _client(phase="shadow", shadow_writes_authorised=True)
    assert c.refusal_for(__import__("brambleloop.integrations.etsy", fromlist=["x"])
                         .Authority.ACTIVATE) is not None
    try:
        c.update_listing("55", {"state": "active"})
    except EtsyNotPermitted:
        pass
    else:
        raise AssertionError("state=active rode the draft lane")
    assert wire.calls == []
    # Renewal is fee-bearing: no create payload asks Etsy to auto-renew, and no source line
    # anywhere sets it true.
    assert "should_auto_renew" not in _payload().to_dict()
    hits = [str(p) for p in (ROOT / "src").rglob("*.py")
            if re.search(r"should_auto_renew\"?\s*[:=]\s*True", p.read_text())]
    assert hits == [], hits
    ok("D1 approvals: no draft, activation, update, delete or renewal without its own grant")


# =============================================================================================
# D2 -- listing_fees and brand_clearance read sealed owner decisions

from brambleloop.brand import clearance as CL  # noqa: E402
from brambleloop.ops import launch_decisions as LD  # noqa: E402


def _knockout(**over) -> dict:
    hit = {"hit": "BRAMBLE & LOOP (CA 1234567, cl. 26)", "relevance": "not_a_conflict",
           "why": "different goods and a different mark"}
    screens = {k: {"source": f"https://example.org/{k}", "queries": ["Brambleloop Studio"],
                   "hits": []} for k in CL.REQUIRED_SCREENS}
    screens["trademark_register_ca"]["hits"] = [hit]
    e = {"name": CL.SHOP_NAME, "searched_on": date.today().isoformat(),
         "searched_by": "company (test)", "screens": screens, "conflicts": [],
         "conclusion": "no conflicting mark found for crochet patterns"}
    e.update(over)
    return e


def _listings(db, n):
    with db.session() as s:
        for i in range(n):
            s.add(Listing(product_slug=f"p{i}", version="1.0.0", title="t", description="d",
                          tags=[], price_cad=5.0, state="draft"))


def _record(db, decision, choice=None, searches=None):
    content = LD.snapshot(db, decision, searches=searches)
    return LD.record(db, authorization=OPS, decision=decision, expected_digest=LD.digest(content),
                     reason="owner test decision", choice=choice, searches=searches)


def test_d2_deadlock_assess_could_never_make_either_row_ready():
    from brambleloop.launch import readiness

    db = _db()
    _listings(db, 3)
    _record(db, LD.LISTING_FEES)
    reqs = {r.key: r for r in readiness.assess(db, phase="shadow").requirements}
    # Pre-fix this was `ready=False` regardless of any record (and ops.launch_decisions did
    # not exist), so no phase transition could ever be recorded.
    assert reqs["listing_fees"].ready is True, reqs["listing_fees"].evidence
    assert reqs["listing_fees"].owner_request is None
    # brand_clearance: with no screening recorded it is company work, never ready.
    b = reqs["brand_clearance"]
    assert b.ready is False and b.blocked_by == readiness.BLOCKED_BUILD, b
    assert b.evidence["registration"]["required"] is False
    ok("D2 deadlock: listing_fees reads the sealed decision; brand_clearance has a path")


def test_d2_listing_fees_refuses_without_a_genuine_covering_decision():
    db = _db()
    _listings(db, 4)
    assert LD.listing_fees_state(db, 4)["ready"] is False                    # none
    # Forged: an unsealed row with the right action and principal.
    with db.session() as s:
        s.add(AuditLog(actor=LD.PRINCIPAL, action=LD.APPROVED, artifact=LD.LISTING_FEES,
                       detail={"decision": LD.LISTING_FEES, "content": {"listings": 99},
                               "seal": "0" * 64, "seq": 1, "prev_id": None, "prev_seal": ""}))
    assert LD.listing_fees_state(db, 4)["ready"] is False
    # A genuine approval for a smaller catalogue does not cover a larger one.
    db = _db()
    _listings(db, 2)
    _record(db, LD.LISTING_FEES)
    _listings(db, 3)
    st = LD.listing_fees_state(db, 5)
    assert st["ready"] is False and "re-approve" in st["why"], st
    # Revoked.
    db = _db()
    _listings(db, 2)
    rid = _record(db, LD.LISTING_FEES)["approval_id"]
    assert LD.listing_fees_state(db, 2)["ready"] is True
    LD.revoke(db, authorization=OPS, approval_id=rid)
    assert LD.listing_fees_state(db, 2)["ready"] is False
    # Credential rotated: the seal no longer verifies.
    db = _db()
    _listings(db, 1)
    _record(db, LD.LISTING_FEES)
    os.environ[opsauth.TOKEN_VAR] = "R" * 40
    try:
        assert LD.listing_fees_state(db, 1)["ready"] is False
    finally:
        os.environ[opsauth.TOKEN_VAR] = OPS
    # The preview binds: a stale digest is refused.
    db = _db()
    try:
        LD.record(db, authorization=OPS, decision=LD.LISTING_FEES, expected_digest="x" * 64,
                  reason="r")
    except ValueError as e:
        assert "preview changed" in str(e)
    else:
        raise AssertionError("an unbound decision was recorded")
    ok("D2 listing_fees refuses: none, forged, smaller catalogue, revoked, rotated, unbound")


def test_d2_brand_clearance_keeps_screening_risk_and_registration_apart():
    db = _db()
    good = (_knockout(),)
    # (a) missing / invalid screening: not ready and nothing can be decided on it.
    assert LD.brand_clearance_state(db, searches=())["ready"] is False
    bad = dict(_knockout())
    bad["screens"] = {k: v for k, v in bad["screens"].items() if k != "domain"}
    assert CL.latest(searches=(bad,))["state"] == "INVALID"
    assert any("domain" in p for p in CL.problems(bad))
    old = _knockout(searched_on=(date.today() - timedelta(days=CL.MAX_AGE_DAYS + 1)).isoformat())
    assert CL.latest(searches=(old,))["state"] == "INVALID"
    lying = _knockout(conflicts=[])
    lying["screens"]["marketplace"]["hits"] = [{"hit": "BramblelooP shop", "relevance": "conflict",
                                                "why": "same name, same goods"}]
    assert any("exactly the hits" in p for p in CL.problems(lying))
    try:
        LD.snapshot(db, LD.BRAND_RISK, searches=(bad,))
    except ValueError as e:
        assert "no valid knock-out" in str(e)
    else:
        raise AssertionError("a risk decision was offered on an invalid screening")
    # (a) valid, (b) not yet accepted: owner-blocked.
    st = LD.brand_clearance_state(db, searches=good)
    assert st["ready"] is False and st["knockout"] == "VALID" and not st["risk_accepted"]
    # (c) a registration decision alone does not clear it.
    _record(db, LD.REGISTRATION, "not_now", searches=good)
    assert LD.brand_clearance_state(db, searches=good)["ready"] is False
    # (b) accepted on a DIFFERENT screening does not clear the current one.
    other = (_knockout(conclusion="an earlier screening"),)
    _record(db, LD.BRAND_RISK, "accept", searches=other)
    assert LD.brand_clearance_state(db, searches=good)["ready"] is False
    ok("D2 brand_clearance refuses: no/invalid/old/inconsistent screening, no acceptance, "
       "registration alone, acceptance of another screening")


def test_d2_brand_clearance_passes_on_screening_plus_acceptance_without_registration():
    db = _db()
    good = (_knockout(),)
    _record(db, LD.BRAND_RISK, "accept", searches=good)
    st = LD.brand_clearance_state(db, searches=good)
    assert st["ready"] is True and st["risk_accepted"] is True, st
    assert st["registration"] == {**st["registration"], "required": False, "decision": None}
    _record(db, LD.REGISTRATION, "file", searches=good)
    st = LD.brand_clearance_state(db, searches=good)
    assert st["registration"]["decision"] == "file" and st["ready"] is True
    try:
        _record(db, LD.BRAND_RISK, "maybe", searches=good)
    except ValueError as e:
        assert "choice must be one of" in str(e)
    else:
        raise AssertionError("an unknown choice was sealed")
    ok("D2 brand_clearance passes on (a)+(b); (c) registration recorded separately, not required")


def test_d2_the_command_center_door_needs_step_up_and_seals_the_decision():
    assert approvals.ACTIONS["launch_decision.record"][0] is True
    assert approvals.ACTIONS["launch_decision.preview"][0] is False
    db = _db()
    _listings(db, 2)
    pv = approvals.execute(db, "launch_decision.preview", {"decision": "listing_fees"},
                           actor="owner:cc:t")["result"]
    try:
        approvals.execute(db, "launch_decision.record",
                          {"decision": "listing_fees", "expected_digest": pv["digest"]},
                          actor="owner:cc:t")
    except approvals.ActionRefused as e:
        assert "reason required" in str(e)
    else:
        raise AssertionError("recorded without a reason")
    out = approvals.execute(db, "launch_decision.record",
                            {"decision": "listing_fees", "expected_digest": pv["digest"],
                             "reason": "approved on my phone"}, actor="owner:cc:t")
    assert out["result"]["decision"] == "listing_fees" and out["audit_id"]
    assert LD.listing_fees_state(db, 2)["ready"] is True
    card = approvals._gate_card({"owner_action_id": 5, "requirement_key": "brand_clearance"})
    acts = {(a["action"], a["params"].get("decision")) for a in card["actions"]}
    assert ("launch_decision.record", "brand_risk_acceptance") in acts
    assert ("launch_decision.record", "trademark_registration") in acts
    ok("D2 CC door: preview reads, record needs reason + step-up + preview digest, seals")


# =============================================================================================
# E3 -- the first person reading is a baseline, a later different reading is a change

TEXT_A = "The seller policy as a person read it on the page. " * 8
TEXT_B = "The seller policy after Etsy changed a clause on the page. " * 8


def _seed(db, source="seller_policy"):
    PP.record_snapshot(db, source, text="repository excerpt seed of the policy", read_by="repo",
                       basis="excerpt", checked_on="2026-09-26")


def test_e3_deadlock_the_first_page_reading_was_a_material_change():
    db = _db()
    _seed(db)
    res = PP.record_page_reading(db, source="seller_policy", text=TEXT_A, read_by="owner")
    # Pre-fix: True -- the first reading differed from the excerpt seed and opened a P1.
    assert res["material_change"] is False and res["first_reading"] is True, res
    assert PP.unreviewed_changes(db) == []
    ok("E3 deadlock: a first person reading after the excerpt seed is the baseline")


def test_e3_a_later_different_reading_still_opens_the_review_and_blocks():
    db = _db()
    _seed(db)
    PP.record_page_reading(db, source="seller_policy", text=TEXT_A, read_by="owner")
    same = PP.record_page_reading(db, source="seller_policy", text=TEXT_A, read_by="owner")
    assert same["material_change"] is False
    changed = PP.record_page_reading(db, source="seller_policy", text=TEXT_B, read_by="owner")
    assert changed["material_change"] is True, changed
    pending = PP.unreviewed_changes(db)
    assert [c["source"] for c in pending] == ["seller_policy"]
    assert "publishing" in pending[0]["affects"]
    # Stale and empty readings stay refused or blocked.
    old = (date.today() - timedelta(days=PP.MAX_AGE_DAYS + 1)).isoformat()
    r = PP.record_page_reading(db, source="advertising_rules", text=TEXT_A, read_by="owner",
                               checked_on=old)
    assert r["current"] is False
    try:
        PP.record_page_reading(db, source="advertising_rules", text="  ", read_by="owner")
    except PP.PolicyRefused:
        pass
    else:
        raise AssertionError("an empty reading was recorded")
    ok("E3 refuses: a later different page reading is a material change; stale/empty blocked")


# =============================================================================================
# E4 -- the category matcher on the shape of Etsy's real tree (production evidence names)

def _real_shape_tree():
    """Etsy's own names as production's 2026-10-21 refresh recorded them
    (research/final_build/w4/evidence_FMBATCH1/prod_api_audit_taxonomy_refreshed_*.json).
    The ids are ILLUSTRATIVE: the evidence recorded names only, so no id here is Etsy's."""
    import fixtures_etsy_taxonomy as FX

    N = FX._node
    kids = ["Books & Magazines", "Craft Machine Files", "Critiques & Shop Tutorials", "Kits",
            "Patterns & Blueprints", "Recipes", "Tutorials"]
    return [
        N(1, "Art & Collectibles", 0, None, [N(2, "Fiber Arts", 1, 1, [N(3, "Crochet", 2, 2)])]),
        N(10, "Craft Supplies & Tools", 0, None, [
            N(11, "Patterns & How To", 1, 10, [N(20 + i, k, 2, 11) for i, k in enumerate(kids)]),
            N(40, "Tools & Equipment", 1, 10, [N(41, "Tools", 2, 40, [
                N(42, "Hooking", 3, 41, [N(43, "Crochet Hooks", 4, 42)])])])])]


def test_e4_on_the_real_names_crochet_is_never_a_node_and_needs_etsys_own_property():
    import fixtures_etsy_taxonomy as FX
    from brambleloop.commerce import category as C
    from brambleloop.integrations import etsy_taxonomy as T

    nodes = T.flatten(_real_shape_tree())
    assert T.pattern_subtree(nodes) == [], "no real node names both pattern and crochet"
    blueprints = next(n for n in nodes if n["name"] == "Patterns & Blueprints")
    # Without Etsy's stored schema for that node, every category stays UNKNOWN (fail safe).
    bare = {"id": 1, "nodes": nodes, "properties": {}}
    for cat in T.REPORTED_CATEGORIES:
        assert C.choose(bare, cat).status == C.UNKNOWN, cat
    # A schema WITHOUT a Crochet value: still UNKNOWN. Nothing is invented.
    knit = FX.prop(9001, "Craft type", ("Knitting", "Sewing"))
    no = {"id": 1, "nodes": nodes, "properties": {str(blueprints["id"]): [knit]}}
    for cat in T.REPORTED_CATEGORIES:
        assert C.choose(no, cat).status == C.UNKNOWN, cat
    # Only if Etsy's own schema for that exact node offers "Crochet" is the node chosen, and
    # it is "Patterns & Blueprints" -- never Fiber Arts > Crochet or Crochet Hooks.
    craft = FX.prop(9001, "Craft type", ("Crochet", "Knitting"))
    yes = {"id": 1, "nodes": nodes, "properties": {str(blueprints["id"]): [craft]}}
    chosen = {cat: C.choose(yes, cat) for cat in T.REPORTED_CATEGORIES}
    for cat, ch in chosen.items():
        if ch.status == C.CHOSEN:
            assert ch.taxonomy_id == blueprints["id"], (cat, ch)
            assert ch.crochet_basis.get("via") == "property", ch
        assert ch.taxonomy_id not in (3, 43), (cat, ch)
    assert any(ch.status == C.CHOSEN for ch in chosen.values()), chosen
    ok("E4: on Etsy's real names the node is Patterns & Blueprints, only with a Crochet value")


# =============================================================================================
# CC -- the policy-readings form (#/policy)

def _session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def _fresh(csrf):
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


def _body(source="children_and_baby", text=TEXT_A, **over):
    b = {"source": source, "text": text, "version": "updated 2026-08-11",
         "summary": "my own answers to the questions", "confirm": PR.CONFIRMATIONS[PR.PASTE]}
    b.update(over)
    return b


def test_cc_policy_form_needs_a_session_csrf_and_step_up():
    from brambleloop.app.command_center.models import OwnerSession

    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert anon.get("/api/cc/policy/readings").status_code == 401
    assert anon.post("/api/cc/policy/readings", json=_body()).status_code == 401
    # The ops token is not a way in.
    assert anon.post("/api/cc/policy/readings", json=_body(),
                     headers={"Authorization": f"Bearer {OPS}"}).status_code == 401
    c, csrf = _session()
    r = c.post("/api/cc/policy/readings", json=_body(),
               headers={"X-CC-Nonce": uuid.uuid4().hex, "X-CC-Timestamp": str(int(time.time()))})
    assert r.status_code == 403, r.text                                     # no CSRF
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with main.db.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))
    r = c.post("/api/cc/policy/readings", json=_body(), headers=_fresh(csrf))
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    # A replayed nonce is refused by the gate.
    c2, csrf2 = _session()
    h = _fresh(csrf2)
    first = c2.post("/api/cc/policy/readings", json=_body(source="advertising_rules"), headers=h)
    assert first.status_code == 200, first.text
    again = c2.post("/api/cc/policy/readings", json=_body(source="advertising_rules"), headers=h)
    assert again.status_code in (401, 403, 409), again.text
    ok("CC: session, CSRF, step-up and a fresh nonce are all required; the ops token is not")


def test_cc_policy_form_records_a_digest_baseline_then_a_reviewable_change():
    c, csrf = _session()
    st = c.get("/api/cc/policy/readings").json()
    srcs = {s["source"]: s for s in st["sources"]}
    assert set(srcs) == set(PP.POLICY_SOURCES) and len(srcs) == 7
    sp = srcs["seller_policy"]
    assert sp["url"] == PP.POLICY_SOURCES["seller_policy"][0] and sp["questions"]
    assert sp["state"] in (PR.NEVER_READ, PR.STALE) and sp["way_in"] == PR.PASTE
    # Never pre-filled: the server sends questions, not answers.
    assert "summary" not in sp and "answers" not in sp
    _seed(main.db, "seller_policy")
    r = c.post("/api/cc/policy/readings", json=_body(source="seller_policy"), headers=_fresh(csrf))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "baseline" and out["material_change"] is False, out
    assert TEXT_A not in r.text
    with main.db.session() as s:
        snap = s.get(PolicySnapshot, out["id"])
        assert snap.digest == PP.digest_of(TEXT_A)
        assert (snap.detail or {}).get("read_by", "").startswith("owner:cc:")
        assert TEXT_A[:40] not in str(snap.detail) and TEXT_A[:40] not in (snap.summary or "")
        rows = {a.action: a for a in s.scalars(select(AuditLog).where(
            AuditLog.action.in_([PP.PAGE_READING_AUDIT, PR.ATTESTED_AUDIT])))
            if (a.detail or {}).get("id", (a.detail or {}).get("snapshot_id")) == out["id"]}
    assert set(rows) == {PP.PAGE_READING_AUDIT, PR.ATTESTED_AUDIT}, rows
    # The intake row is the same shape POST /api/policy/snapshot writes.
    assert set(rows[PP.PAGE_READING_AUDIT].detail) == {
        "id", "source", "digest", "material_change", "checked_on", "current",
        "incidents_resolved", "basis"}
    assert rows[PR.ATTESTED_AUDIT].detail["confirmed"] == PR.CONFIRMATIONS[PR.PASTE]
    assert TEXT_A[:40] not in str(rows[PR.ATTESTED_AUDIT].detail)
    # Duplicate: same text, same day, same owner -> 409, nothing added.
    dup = c.post("/api/cc/policy/readings", json=_body(source="seller_policy"),
                 headers=_fresh(csrf))
    assert dup.status_code == 409 and dup.json()["code"] == "DUPLICATE", dup.text
    # A genuine later change opens the review card; the form offers no way around it.
    r = c.post("/api/cc/policy/readings", json=_body(source="seller_policy", text=TEXT_B),
               headers=_fresh(csrf))
    assert r.status_code == 200 and r.json()["kind"] == "change", r.text
    st = {s["source"]: s for s in c.get("/api/cc/policy/readings").json()["sources"]}
    assert st["seller_policy"]["state"] == PR.CHANGED
    assert [h["kind"] for h in st["seller_policy"]["history"]] == ["change", "baseline"]
    cards = [x["card_id"] for x in approvals.inbox(main.db)["cards"]]
    assert "policy:seller_policy" in cards
    ok("CC: digest only, same intake row + attestation, baseline then change, duplicate refused")


def test_cc_policy_form_refuses_incomplete_unconfirmed_or_bad_input():
    c, csrf = _session()
    for bad, code in ((_body(summary=""), 400), (_body(confirm="yes"), 400),
                      (_body(text=""), 400), (_body(source="nope"), 400),
                      (_body(version="v" * 121), 400),
                      (_body(checked_on=(date.today() + timedelta(days=2)).isoformat()), 400),
                      (_body(source="search_guidance", text="", fetch_article=True,
                             confirm=PR.CONFIRMATIONS[PR.PASTE]), 400)):
        r = c.post("/api/cc/policy/readings", json=bad, headers=_fresh(csrf))
        assert r.status_code == code, (bad, r.status_code, r.text)
    ok("CC refuses: no answers, wrong confirmation, empty text, unknown source, long version, "
       "future date, wrong confirmation for a fetched article")


def test_cc_help_center_article_is_fetched_by_the_server_not_pasted():
    from brambleloop.gates import policy_reader

    article_id = policy_reader.help_center_sources()["search_guidance"]
    body = "<p>" + ("Tags help buyers find you. Use all 13 tags. " * 10) + "</p>"
    seen = []

    def fake(url):
        seen.append(url)
        return {"article": {"id": int(article_id), "body": body, "draft": False,
                            "title": "How to Use Tags", "edited_at": "2026-04-21T15:22:37Z"}}

    PR.fetcher = fake
    try:
        c, csrf = _session()
        r = c.post("/api/cc/policy/readings", headers=_fresh(csrf), json={
            "source": "search_guidance", "fetch_article": True, "summary": "answers",
            "confirm": PR.CONFIRMATIONS[PR.FETCHED]})
        assert r.status_code == 200, r.text
        assert r.json()["text_source"] == PR.FETCHED and r.json()["kind"] == "baseline"
        assert seen and article_id in seen[0]
        r = c.post("/api/cc/policy/readings", headers=_fresh(csrf), json={
            "source": "seller_policy", "fetch_article": True, "summary": "answers",
            "confirm": PR.CONFIRMATIONS[PR.FETCHED]})
        assert r.status_code == 400 and "paste" in r.text, r.text   # legal pages: a person
    finally:
        PR.fetcher = None
    ok("CC: Help Center text fetched from Etsy's article API; legal pages must be pasted")


def test_cc_policy_view_is_in_the_spa_shell_and_linked():
    static = ROOT / "src/brambleloop/app/command_center/static"
    assert '"js/views/policy.js"' in (static / "sw.js").read_text()
    assert 'id: "policy"' in (static / "js/routes.js").read_text()
    view = (static / "js/views/policy.js").read_text()
    assert "export async function render" in view and "requiresStepUp: true" in view
    assert "https://" not in view, "no hard-coded external URL: links come from the server"
    for v in ("approvals.js", "completion.js"):
        assert 'href: "#/policy"' in (static / "js/views" / v).read_text(), v
    ok("CC: #/policy view is in the offline shell, routed, and linked from Approvals/Completion")


if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                print(f"FAIL {name}")
                fails += 1
    print(f"\n{len(RESULTS)} passed, {fails} failed")
    raise SystemExit(1 if fails else 0)
