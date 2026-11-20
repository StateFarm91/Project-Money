"""R2 security, audit ddf9c6e M3: the command center's department block refuses the
never-pause departments (executive, finance, platform, product_truth) exactly as emergency
pause does -- one shared rule -- and the orchestrator keeps running them.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_security_department_block.py
"""
from __future__ import annotations

from r2_security_harness import DB, client, fresh, login, run  # noqa: I001

from brambleloop.app.command_center import emergency
from brambleloop.autonomy import memory, orchestrator

NEVER = ("executive", "finance", "platform", "product_truth")


def test_block_and_pause_refuse_the_same_departments():
    assert set(NEVER) == set(emergency.NEVER_PAUSED)
    c = client()
    csrf = login(c)
    for d in NEVER:
        p = c.post("/api/cc/emergency/pause", headers=fresh(csrf),
                   json={"scope": "department", "department": d, "reason": "try pause"})
        b = c.post(f"/api/cc/departments/{d}/block", headers=fresh(csrf), json={"reason": "x"})
        assert p.status_code == 409 and p.json()["code"] == "REFUSED_BY_AUTHORITY", p.text
        assert b.status_code == 409 and b.json()["code"] == "REFUSED_BY_AUTHORITY", b.text
        assert b.json()["error"] == p.json()["error"], (b.text, p.text)
        assert memory.active_block(DB, d) is None, d
    # A pausable department can still be blocked (the control itself is not removed).
    r = c.post("/api/cc/departments/growth/block", headers=fresh(csrf), json={"reason": "x"})
    assert r.status_code == 200, r.text
    assert memory.active_block(DB, "growth") is not None
    memory.unblock_department(DB, "growth")


def test_orchestrator_keeps_running_never_pause_departments_even_with_a_block_row():
    # A block row written by any other path (or left over from before the fix) is not obeyed.
    for d in NEVER:
        memory.block_department(DB, d, reason="legacy block")
    try:
        rep = orchestrator.tick(DB)
        states = {d: rep["departments"][d].get("state") for d in NEVER}
        assert all(v != "BLOCKED" for v in states.values()), states
        assert all(rep["departments"][d].get("ignored_block") for d in NEVER), rep
    finally:
        for d in NEVER:
            memory.unblock_department(DB, d)


if __name__ == "__main__":
    run(globals())
