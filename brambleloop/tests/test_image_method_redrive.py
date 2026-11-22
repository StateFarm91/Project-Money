"""ENG-IMAGE-METHOD-REDRIVE: a fidelity-blocked run made under an older generation method is
restarted exactly once under the current method, inside the existing call and spend caps.

The run and candidate rows are fixtures in the real `image_production_runs` and
`image_candidates` tables; `restartable`, `restart`, `_attempts` and the hourly sweep
(`redrive_capability_blocked`) are the real functions. Nothing generates and nothing is paid:
the restart only enqueues a job through `follow`, which records it.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_image_method_redrive.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import gallery_budget  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual.image_records import (ImageCandidate, ImageProductionRun,  # noqa: E402
                                              ensure_tables)

FIDELITY_REASON = "product fidelity FAIL after 3 attempts: {'product_truth': 'wrong bands'}"
OLD = {"prompt_builder": "flux3-prompt-builder/2.2.0", "pattern_refs": "pattern-refs/3.1.4",
       "pdf_page_refs": "none", "owner_method": "none",
       "version": "flux3-prompt-builder/2.2.0|pattern-refs/3.1.4|none|none"}


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='imr_')}/imr.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    ensure_tables(db)
    return db


def _blocked(db, slug, *, calls=3, spent=0.42, stamp=None, n=3, stage="fidelity_gate",
             reason=FIDELITY_REASON):
    """A run blocked at the fidelity gate with `n` FAILed product frames, each stamped with
    `stamp` (None = pre-method, as every candidate made before this change)."""
    key = IP.run_key(slug, "1.0.0", f"{slug}-release")
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=slug, version="1.0.0",
                                 release=f"{slug}-release", listing=slug, stage=stage,
                                 status="blocked", blocked_reason=reason, stages={},
                                 generation_calls=calls, spent_cad=spent,
                                 attempts_exhausted=True))
        for i in range(n):
            s.add(_cand(key, slug, i + 1, stamp))
    return key


def _cand(key, slug, attempt, stamp, status="FAIL"):
    checks = {"product_truth": {"status": status, "why": "bands disagree with the CIR"}}
    if stamp is not None:
        checks[IP.METHOD_KEY] = dict(stamp)
    return ImageCandidate(sha256=f"{attempt:064x}", run_key=key, method="autonomous",
                          provenance_kind="ai_generated_autonomous", slug=slug,
                          version="1.0.0", release=f"{slug}-release", listing=slug,
                          role=IP.ANCHOR_ROLE, stage="product_generation", attempt=attempt,
                          checks=checks, technical_status=status,
                          outcome="rejected" if status == "FAIL" else "accepted")


def _follow(calls):
    def follow(inputs, key, *, session=None):
        calls.append((inputs, key))
        return object()
    return follow


def _row(db, key):
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        return {"status": r.status, "calls": r.generation_calls, "spent": r.spent_cad,
                "reason": r.blocked_reason, "stage": r.stage, "stages": dict(r.stages or {})}


def _reblock(db, key, reason=FIDELITY_REASON):
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.status, r.blocked_reason, r.stage = "blocked", reason, "fidelity_gate"


def test_every_generated_candidate_is_stamped_with_stable_identifiers():
    from brambleloop.creative import flux_prompt, pattern_refs

    class Gen:
        accepts_owner_method = True

    m = IP.generation_method(Gen())
    assert m["prompt_builder"] == flux_prompt.BUILDER_VERSION
    assert m["pattern_refs"] == pattern_refs.VERSION
    assert m["pdf_page_refs"].startswith("pdf-page-refs/") and "pdfium" not in m["pdf_page_refs"]
    assert m["owner_method"] == IP.OWNER_METHOD and m["version"] == IP.current_method_version()
    assert m["generator_owner_method"] is True
    # what a generator declares is provenance, not the version: only code moves the version
    assert IP.generation_method(object())["generator_owner_method"] is False
    assert IP.generation_method(object())["version"] == m["version"]
    # recorded on the row by record_candidate, and an unstamped row reads as pre-method
    db = _db()
    verdict = {"sha256": "ab" * 32, "technical_status": "FAIL", "publishable": False,
               "checks": {"binding": {"status": "PASS"}, "quality": {}}}
    rec = IP.record_candidate(db, {"slug": "s", "role": IP.ANCHOR_ROLE, IP.METHOD_KEY: m},
                              verdict, method="autonomous", run="k")
    with db.session() as s:
        row = s.get(ImageCandidate, rec["candidate_id"])
        assert IP.candidate_method_version(row.checks) == m["version"], row.checks
    assert IP.candidate_method_version({}) == IP.PRE_METHOD
    assert IP.candidate_method_version(None) == IP.PRE_METHOD


def test_an_old_method_fidelity_block_restarts_once_under_the_new_method():
    db = _db()
    key = _blocked(db, "market-basket-small")
    assert IP._attempts(db, key, IP.ANCHOR_ROLE) == 3
    can = IP.restartable(db, key)
    assert can["restartable"] and can["resume_at"] == "product_generation", can
    assert can["reverify"] is False and can["method_redrive"]["eligible"], can
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert out["method_redrives"]["eligible"] == [key], out
    assert out["method_redrives"]["done"] == [key], out
    assert out["method_redrives"]["no_headroom"] == [], out
    assert len(calls) == 1 and calls[0][0]["stage"] == "product_generation", calls
    assert calls[0][1].endswith(":e1"), calls[0][1]
    row = _row(db, key)
    assert row["status"] != "blocked" and row["stage"] == "product_generation", row
    rec = row["stages"][IP.RESTART_KEY]
    assert rec["method_redrive"]["version"] == IP.current_method_version(), rec
    assert rec["history"][-1]["by"] == IP.METHOD_REDRIVE_BY
    assert rec["history"][-1]["method_version"] == IP.current_method_version()
    assert IP.get_run(db, key)["method_redrive"]["status"] == "done"
    # attempts now count only candidates made under the current method
    assert IP._attempts(db, key, IP.ANCHOR_ROLE) == 0
    with db.session() as s:
        s.add(_cand(key, "market-basket-small", 1, IP.generation_method()))
    assert IP._attempts(db, key, IP.ANCHOR_ROLE) == 1


def test_the_same_method_never_restarts_twice():
    db = _db()
    key = _blocked(db, "hexagon-coaster-set")
    calls = []
    IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert len(calls) == 1
    # Blocked at the fidelity gate again with only old-method failures on record: the one
    # restart for this method version is spent.
    _reblock(db, key)
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert len(calls) == 1 and out["method_redrives"]["done"] == [], out
    assert [r.get("code") for r in out["refused"]] == [IP.METHOD_REDRIVE_ALREADY], out
    can = IP.restartable(db, key)
    assert not can["restartable"] and can.get("code") == IP.METHOD_REDRIVE_ALREADY, can
    assert IP.restart(db, key, follow=_follow(calls), by="owner:test")["restarted"] is False
    assert len(calls) == 1


def test_caps_calls_and_spend_are_never_reset():
    db = _db()
    key = _blocked(db, "housewarming-key-basket", calls=5, spent=0.71)
    plan_before = IP._spend_plan(key, db)
    cap_before = gallery_budget.effective_cap(db)
    calls = []
    IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert len(calls) == 1
    row = _row(db, key)
    assert row["calls"] == 5 and abs(row["spent"] - 0.71) < 1e-9, row
    assert IP.MAX_GENERATION_CALLS == 12 and IP.MAX_SPEND_CAD_PER_GALLERY <= 2.50
    assert gallery_budget.effective_cap(db) == cap_before
    plan_after = IP._spend_plan(key, db)
    assert plan_after["call_count"] == plan_before["call_count"]
    assert plan_after["max_spend_cad"] == plan_before["max_spend_cad"]
    hist = row["stages"][IP.RESTART_KEY]["history"][-1]
    assert hist["generation_calls"] == 5 and abs(hist["spent_cad"] - 0.71) < 1e-9, hist


def test_no_headroom_stays_blocked_with_the_fixed_code():
    db = _db()
    no_calls = _blocked(db, "basket-calls", calls=IP.MAX_GENERATION_CALLS)
    no_money = _blocked(db, "basket-money", calls=2,
                        spent=gallery_budget.effective_cap(db) - 0.01)
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert calls == [], calls
    m = out["method_redrives"]
    assert sorted(m["eligible"]) == sorted([no_calls, no_money]), m
    assert sorted(m["no_headroom"]) == sorted([no_calls, no_money]) and m["done"] == [], m
    assert {r["code"] for r in out["refused"]} == {IP.METHOD_REDRIVE_NO_HEADROOM}, out
    for key in (no_calls, no_money):
        row = _row(db, key)
        assert row["status"] == "blocked" and row["reason"] == FIDELITY_REASON, row
        rb = IP.get_run(db, key)["method_redrive"]
        assert rb["status"] == "no_headroom" and rb["code"] == IP.METHOD_REDRIVE_NO_HEADROOM, rb
        assert rb["why"].startswith(IP.METHOD_REDRIVE_NO_HEADROOM), rb
        can = IP.restartable(db, key)
        assert not can["restartable"] and can["code"] == IP.METHOD_REDRIVE_NO_HEADROOM, can
        assert IP.restart(db, key, follow=_follow(calls), by="owner:test")["restarted"] is False
    assert calls == []
    assert _row(db, no_calls)["calls"] == IP.MAX_GENERATION_CALLS


def test_failures_made_under_the_current_method_never_restart():
    db = _db()
    current = _blocked(db, "basket-current", stamp=IP.generation_method())
    mixed = _blocked(db, "basket-mixed", n=2)
    with db.session() as s:
        s.add(_cand(mixed, "basket-mixed", 3, IP.generation_method()))
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert calls == [] and out["method_redrives"]["eligible"] == [], out
    assert {r["code"] for r in out["refused"]} == {IP.METHOD_REDRIVE_CURRENT}, out
    for key in (current, mixed):
        can = IP.restartable(db, key)
        assert not can["restartable"] and "FAIL on" in can["why"], can
        assert _row(db, key)["status"] == "blocked"


def test_an_older_stamped_method_is_also_redriven_and_other_blocks_are_not_considered():
    db = _db()
    stamped_old = _blocked(db, "basket-old-stamp", stamp=OLD)
    other = _blocked(db, "basket-lifestyle", stage="lifestyle_generation",
                     reason="lifestyle FAIL")
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert out["method_redrives"]["done"] == [stamped_old], out
    assert other not in str(out), out
    assert len(calls) == 1


def test_the_hourly_sweep_reports_fixed_vocabulary_counts():
    from brambleloop.runtime import chain_successors

    src = Path(chain_successors.__file__).read_text()
    assert "method_redrives" in src and "METHOD_REDRIVE_EVIDENCE" in src
    assert IP.METHOD_REDRIVE_EVIDENCE == ("eligible", "done", "no_headroom")


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
