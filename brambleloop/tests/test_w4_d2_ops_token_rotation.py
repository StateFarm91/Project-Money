"""F-160 (W4-D2): BRAMBLELOOP_OPS_TOKEN is in the credential rotation register with its
exposure history (console, PSReadLine history, screenshot; rotation unconfirmed), raised as an
owner card with the exact rotation action, and its value is never held or printed."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.ops import credential_register as C  # noqa: E402

NAME = "BRAMBLELOOP_OPS_TOKEN"


def test_the_ops_token_is_registered_with_its_exposure_history():
    e = {x.name: x for x in C.REGISTER}[NAME]
    assert e.exposed_at == "2026-09-25" and e.status == C.ROTATION_REQUIRED
    for channel in ("PowerShell command line", "PSReadLine", "screenshot", "unconfirmed"):
        assert channel in e.exposure, channel
    assert "Railway" in e.held_in and "nowhere in this repository" in e.held_in
    assert C.validate() == []
    assert NAME in C.report()["rotation_required"]


def test_the_owner_card_states_exactly_what_to_do():
    card = {r.key: r for r in C.owner_requests()}[C.KEY_PREFIX + NAME]
    for step in ("Read-Host", "Railway", "GET /status", "refused with the old one",
                 "publication grant", "PSReadLine", "screenshot", "never the value"):
        assert step in card.action, step
    assert card.max_cost_cad == 0.0 and card.minutes > 0 and card.consequence_of_delay
    # Rotation with evidence retires it; age alone never does.
    import dataclasses
    e = {x.name: x for x in C.REGISTER}[NAME]
    done = dataclasses.replace(e, rotated_at="2026-10-28",
                               rotation_evidence="operator call accepted with the new value")
    assert C.owner_requests((done,)) == [] and C.validate((done,)) == []


def test_the_value_is_never_printed():
    probe = "opsprobe-" + "Z" * 30                       # a stand-in value, set only here
    env = dict(os.environ, **{NAME: probe})
    r = subprocess.run([sys.executable, "-m", "brambleloop.ops.credential_register"],
                       cwd=str(ROOT / "src"), env=env, capture_output=True, text=True)
    out = r.stdout + r.stderr
    assert NAME in out and probe not in out
    assert probe not in json.dumps([c.__dict__ for c in C.owner_requests()])


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
