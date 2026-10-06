"""W3 lane F x lanes D/E: Talk to Laura consumes Laura's identity, executive and memory.

* identity comes from lane D's verified durable record (`laura.identity`), not a copy;
* "What are you working on?" cites Laura's own executive priorities/decisions
  (`laura_priorities:*`, `laura_decisions:*`) after her executive tick has run;
* answers cite lane E memory entries by their `laura_memory:<tier>:<key>` ref, read as the
  verified owner session; a follow-on is remembered in her operational memory;
* the company constitution (Finance / Product Truth / Security) can block a follow-on Laura
  would otherwise create, and only the challenger (or the owner) can clear it.

Each check skips itself only when the peer lane is genuinely absent (never silently passes).
Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_cc_integration.py
"""
from __future__ import annotations

import importlib.util

import w3_laura_cc_harness as H  # noqa: E402


from brambleloop.core.models import Job  # noqa: E402

DB = H.DB
H.seed_company()
HAVE_D = importlib.util.find_spec("brambleloop.laura.executive") is not None
HAVE_E = importlib.util.find_spec("brambleloop.laura.memory") is not None


def _ask(c, csrf, q):
    r = H.post(c, csrf, "/api/cc/laura/ask", {"question": q})
    assert r.status_code == 200, r.text
    return r.json()


def test_identity_is_lane_d_verified_record():
    if not HAVE_D:
        print("SKIP lane D not merged")
        return
    c, csrf = H.session()
    ov = c.get("/api/cc/laura").json()
    idn = ov["identity"]
    assert idn["source"] == "brambleloop.laura.identity", idn
    assert idn["identity_id"] == "laura-v15-a42aeac7" and not idn.get("identity_disagreement")
    assert idn["verified"]["status"] == "OK" and idn["verified"]["identity_version"], idn
    t = _ask(c, csrf, "Who are you?")
    assert any(s.startswith("laura_identity_versions:") for s in t["sources"]), t["sources"]
    assert "spend money" in " ".join(idn["authority"]["may_not"]), idn["authority"]


def test_working_on_cites_laura_executive_priorities():
    if not HAVE_D:
        print("SKIP lane D not merged")
        return
    from brambleloop.laura import executive

    executive.tick(DB)
    pr = [p for p in executive.priorities(DB) if p["status"] != "closed"]
    hist = executive.history(DB, limit=5)
    assert pr or hist, "Laura's executive tick recorded nothing on a seeded company"
    c, csrf = H.session()
    t = _ask(c, csrf, "What are you working on?")
    assert t["status"] in ("ANSWERED", "PARTIAL"), t
    cited = [s for s in t["sources"] if s.startswith(("laura_priorities:", "laura_decisions:"))]
    assert cited, t["sources"]
    assert "My executive priorities" in t["answer"], t["answer"]


def test_memory_is_cited_and_follow_ons_are_remembered():
    if not HAVE_E:
        print("SKIP lane E not merged")
        return
    from brambleloop.laura import memory as lm

    written = lm.ensure_canonical_seed(DB)
    assert written or lm.read(DB, "canonical", "identity/*", lm.Principal.laura())
    c, csrf = H.session()
    t = _ask(c, csrf, "Who are you?")
    mem = [s for s in t["sources"] if s.startswith("laura_memory:canonical:identity/")]
    assert mem, t["sources"]
    t = _ask(c, csrf, "What's making money / losing money?")
    prop = next(p for p in t["proposals"] if p["job_type"] == "finance.accounting.cycle")
    r = H.post(c, csrf, "/api/cc/laura/follow-on",
               {"turn_id": t["turn_id"], "proposal_key": prop["key"], "confirm": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert str(out.get("memory_ref", "")).startswith("laura_memory:operational:cc/followon/"), out
    assert out["constitution"] in ("allow", "not available"), out
    entries = lm.read(DB, "operational", "cc/followon/*", lm.Principal.laura())
    assert any(e["value"].get("result") == out["result_ref"] for e in entries), entries
    # A public surface still reads nothing of it (lane E's boundary).
    try:
        lm.read(DB, "operational", None, lm.Principal.public("storefront"))
        raise AssertionError("public principal read Laura's operational memory")
    except lm.PermissionRefused:
        pass


def test_constitution_can_block_laura_follow_on():
    if not HAVE_D:
        print("SKIP lane D not merged")
        return
    from brambleloop.laura.core import constitution

    cid = constitution.challenge(DB, raised_by="finance",
                                 reason="books are being re-closed; hold finance jobs",
                                 scope={"department": "finance"})
    try:
        c, csrf = H.session()
        t = _ask(c, csrf, "How much money did we make?")
        prop = next(p for p in t["proposals"] if p["department"] == "finance")
        with DB.session() as s:
            before = s.query(Job).filter(Job.job_type == prop["job_type"]).count()
        r = H.post(c, csrf, "/api/cc/laura/follow-on",
                   {"turn_id": t["turn_id"], "proposal_key": prop["key"], "confirm": True})
        assert r.status_code == 409 and "constitution" in r.json()["error"], r.text
        assert "finance" in r.json()["error"]
        with DB.session() as s:
            assert s.query(Job).filter(Job.job_type == prop["job_type"]).count() == before
        try:
            constitution.resolve_challenge(DB, cid, resolved_by="laura", resolution="no")
            raise AssertionError("Laura cleared her own block")
        except constitution.ChallengeRefused:
            pass
    finally:
        constitution.resolve_challenge(DB, cid, resolved_by="finance", resolution="done")


if __name__ == "__main__":
    H.run(globals())
