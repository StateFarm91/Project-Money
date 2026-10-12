"""W3-E: Laura's memory is pure database state -- it survives restarts and model swaps.

A fresh interpreter (a real process restart) with a different model/provider configuration
reads back exactly what the first process wrote, including every revision, and continues
the revision chain. Nothing in the memory path consults a model, provider or context window.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_memory_persistence.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from w3_laura_memory_harness import ROOT, check, finish, fresh_db, owner_session

from brambleloop.laura import memory as lm

CHILD = r"""
import json, sys
from brambleloop.core.db import Database
from brambleloop.laura import memory as lm
db = Database(sys.argv[1])
laura = lm.Principal.laura()
snap = {t: sorted((e["key"], json.dumps(e["value"], sort_keys=True), e["revision"],
                   tuple(e["sources"])) for e in lm.read(db, t, None, laura,
                                                         include_projections=False))
        for t in lm.TIERS}
hist = [h["revision"] for h in lm.history(db, "brand", "voice", laura)]
nxt = lm.write(db, "operational", "continuity/after-restart", "resumed",
               "laura_memory:brand:voice", laura)["revision"]
print(json.dumps({"snap": snap, "hist": hist, "next": nxt, "seed": lm.ensure_canonical_seed(db)}))
"""


def _snapshot(db):
    laura = lm.Principal.laura()
    return {t: sorted([e["key"], json.dumps(e["value"], sort_keys=True), e["revision"],
                       list(e["sources"])] for e in lm.read(db, t, None, laura,
                                                            include_projections=False))
            for t in lm.TIERS}


def _populate(db):
    owner = lm.Principal.owner(owner_session(db))
    laura = lm.Principal.laura()
    lm.ensure_canonical_seed(db)
    lm.write(db, "brand", "voice", "warm, concise", "decision:D-FB-12", laura)
    lm.write(db, "brand", "voice", "warm, concise, tasteful", "decision:D-FB-13", laura)
    lm.write(db, "operational", "priority/now", "finish the storefront", "decision:D-FB-13",
             lm.Principal.department("store_commerce"))
    lm.write(db, "experience", "lesson/banner", "lead with crochet, not mechanics",
             "doc:spec/07_Laura_Owner_Ruling_2026-10-06.md", laura)
    lm.write(db, "relationship", "policy/spend", "no consequential spend without approval",
             "owner_statement:CLAUDE.md non-negotiable", owner)


def test_survives_a_process_restart_and_a_model_swap():
    with tempfile.TemporaryDirectory(prefix="w3e-persist-") as td:
        url = f"sqlite:///{td}/persist.sqlite"
        db = fresh_db(f"{td}/persist.sqlite")
        _populate(db)
        before = _snapshot(db)
        assert sum(len(v) for v in before.values()) == 10
        db.engine.dispose()
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"),
                   BRAMBLELOOP_LLM_PROVIDER="some-other-provider",
                   BRAMBLELOOP_MODEL="a-different-model", ANTHROPIC_MODEL="swapped",
                   OPENAI_MODEL="swapped")
        r = subprocess.run([sys.executable, "-c", CHILD, url], env=env, cwd=str(ROOT),
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-2000:]
        child = json.loads(r.stdout.strip().splitlines()[-1])
        assert child["snap"] == before, (child["snap"], before)
        assert child["hist"] == [1, 2] and child["next"] == 1 and child["seed"] == []
        db2 = fresh_db(f"{td}/persist.sqlite")
        got = lm.read(db2, "operational", "continuity/after-restart", lm.Principal.laura())
        assert got and got[0]["value"] == "resumed"
        db2.engine.dispose()


def test_memory_path_never_imports_a_model_client():
    src = Path(lm.__file__).parent
    files = sorted(src.glob("*.py"))
    assert len(files) >= 5
    for f in files:
        text = f.read_text(encoding="utf-8")
        for banned in ("anthropic", "openai", "llm", "requests", "httpx", "urllib"):
            assert f"import {banned}" not in text and f"from {banned}" not in text, (f, banned)


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)
finish()
