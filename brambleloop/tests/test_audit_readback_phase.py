"""Audit F-02: the readback must not read PASS while publication is structurally impossible.

On f9011cf94 an unproven hosted build is forced to SHADOW by the boot guard
(`ops.release_record.apply_at_import`) and opens a P1 `release.unproven_build` incident with
`halts_publication=True` and NO product. In SHADOW `store.publish` refuses before any Etsy
request, a private draft included. Yet `ops.production_evidence`:

* judged `publishing_halt_clear` from the systemic row and the truth sweep only -- the
  product-less halting incident landed in the per-product families as `products: 0`;
* reported `draft_candidate` / `draft_candidates` without reading the phase or boot guard;
* named the phase and the boot guard verdict nowhere.

Now: a judged read-only `runtime_phase` section, product-less halting incidents counted by
family and judged, per-release `runtime_refuses_draft_now` with fixed reason codes,
`draft_candidates_actionable_now`, and `server_judgement.publication_path_open`.

Run: cd brambleloop && python3 tests/test_audit_readback_phase.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  per-process temp sandbox, removed at exit
import contextlib
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "ops"))
sys.path.insert(0, str(ROOT / "tests"))

for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                      "RAILWAY_")):
        os.environ.pop(_k)
os.environ.pop("BRAMBLELOOP_PHASE", None)
os.environ.pop("BRAMBLELOOP_BOOT_GUARD", None)

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Incident, Listing, PatternVersion,  # noqa: E402
                                     Product)
from brambleloop.ops import production_evidence as pe  # noqa: E402
from brambleloop.ops import publication_authority as pa  # noqa: E402
from brambleloop.ops import release_record as rr  # noqa: E402
from brambleloop.products.launch0 import LAUNCH0_SLUGS  # noqa: E402
from brambleloop.publish import listing_package  # noqa: E402

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
SLUG = sorted(LAUNCH0_SLUGS)[0]
RELEASE = "ab" * 32
# Free text that must never reach any new field.
SECRET_SUMMARY = "PRIVATE-INCIDENT-SUMMARY do not echo /app/release/RELEASE_x.json"
SECRET_REASON = "tracked suite record copy 'PRIVATE-PATH.json' is absent"


def _db() -> Database:
    d = Database(f"sqlite:///{tempfile.mkdtemp(prefix='f02_')}/f02.db")
    d.create_all()
    return d


def _fresh_sweep(db):
    with db.session() as s:
        s.add(AuditLog(actor="system", action="ops.truth.sweep", artifact="truth",
                       at=NOW - timedelta(minutes=10),
                       detail={"systemic": {"systemic": False}}))


def _unproven_build_incident(db):
    """Exactly the row `release_record.record_incident` opens on an unproven hosted build."""
    with db.session() as s:
        s.add(Incident(severity="P1", signature=rr.INCIDENT_SIGNATURE, halts_publication=True,
                       summary=SECRET_SUMMARY, detail={"reasons": [SECRET_REASON]}))


@contextlib.contextmanager
def _boot(result: dict | None):
    saved = dict(rr.BOOT)
    rr.BOOT.clear()
    if result is not None:
        rr.BOOT.update(result)
    try:
        yield
    finally:
        rr.BOOT.clear()
        rr.BOOT.update(saved)


FORCED = {"enforced": True, "ok": False, "action": "forced_shadow", "record": None,
          "reasons": [SECRET_REASON], "tree_sha256": "c" * 64}
PROVEN = {"enforced": True, "ok": True, "action": "none", "record": {"file": "RELEASE_x.json"},
          "reasons": []}


def _certified_ready_release(db):
    with db.session() as s:
        p = Product(slug=SLUG, title="t", status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={},
                             release_hash=RELEASE, certified=True))
        s.add(Listing(product_slug=SLUG, version="1.0.0", title="t", description="d",
                      tags=[], price_cad=10.0, state="draft", release_hash=RELEASE))


@contextlib.contextmanager
def _gates_pass():
    """The release itself is a draft candidate: every gated section PASS, package READY for
    this exact release. (Those readers are covered by test_first_listing_doors.py.)"""
    ev = {k: {"state": pa.PASS} for k in pa.GATED_SECTIONS}
    pkg = {"state": listing_package.READY, "release_hash": RELEASE, "blockers": []}
    with patch.object(pa, "evidence", lambda *a, **k: ev), \
            patch.object(listing_package, "latest", lambda *a, **k: pkg):
        yield


def _strings(v):
    if isinstance(v, dict):
        for k, x in v.items():
            yield str(k)
            yield from _strings(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _strings(x)
    elif isinstance(v, str):
        yield v


# ---- (i) a product-less halting incident is a company-wide halt ------------------------


def test_open_global_unproven_build_incident_fails_publishing_halt_clear():
    db = _db()
    _fresh_sweep(db)
    with _boot(PROVEN):
        before = pe.evidence(db, now=NOW)
        assert before["server_judgement"]["publishing_halt_clear"] is True, \
            before["publishing_halt"]
        _unproven_build_incident(db)
        ev = pe.evidence(db, now=NOW)
    halt = ev["publishing_halt"]
    assert ev["server_judgement"]["publishing_halt_clear"] is False, halt
    assert halt["global_halting_open"] == 1, halt
    assert halt["global_halting_by_family"] == {"release.unproven_build": 1}, halt
    # Every existing key is kept.
    for k in ("systemic_halt_open", "per_product_halting_by_family", "halted_certifications",
              "truth_sweep_systemic"):
        assert k in halt, k
    # The public /api/verify check agrees.
    chk = {c["check"]: c for c in pe.checks(db, now=NOW)}["publishing_halt_clear"]
    assert chk["ok"] is False and chk["evidence"]["global_halting_open"] == 1, chk
    # A product-bound halting incident is still per-product, not global.
    with db.session() as s:
        s.add(Incident(severity="P1", signature="size-halt:x", product_slug=SLUG,
                       halts_publication=True, summary="x"))
    assert pe.evidence(db, now=NOW)["publishing_halt"]["global_halting_open"] == 1
    print("OK open global release.unproven_build P1 -> publishing_halt_clear False, "
          "family counted")


def test_global_halt_absent_from_an_older_body_is_not_a_pass():
    ev = {"readable": True, "truth_sweep_age_hours": 0.1,
          "truth_sweep_systemic_evaluated": True, "truth_sweep_systemic": False,
          "systemic_halt_open": 0}
    assert pe.judge_publishing_halt(ev) is False
    assert pe.judge_publishing_halt(dict(ev, global_halting_open=0)) is True
    print("OK judge_publishing_halt without global_halting_open is False")


# ---- (ii) SHADOW: a draft candidate is not actionable now -----------------------------


def test_shadow_certified_ready_release_is_candidate_but_not_actionable():
    db = _db()
    _fresh_sweep(db)
    _certified_ready_release(db)
    with _boot(PROVEN), _gates_pass():
        ev = pe.evidence(db, now=NOW)
    fl = ev["first_listing_readiness"]
    rel = f"{SLUG}@1.0.0"
    assert fl["draft_candidates"] == [rel], fl                 # describes the release
    assert fl["draft_candidates_actionable_now"] == [], fl
    assert fl["runtime_refuses_draft_now"] is True, fl
    assert fl["runtime_refusal_reasons"] == ["shadow_phase"], fl
    r = fl["releases"][0]
    assert r["draft_candidate"] is True and r["runtime_refuses_draft_now"] is True, r
    assert r["runtime_refusal_reasons"] == ["shadow_phase"], r
    rp = ev["runtime_phase"]
    assert rp["readable"] is True and rp["effective_phase"] == "shadow", rp
    assert rp["private_draft_possible"] is False and rp["publication_possible"] is False, rp
    # The readback names it: PASS on the candidate, but "not actionable now".
    import readback

    verdict, why = readback._judge_section("first_listing_readiness", fl, None)
    assert verdict == readback.PASS and "not actionable now (shadow_phase)" in why, why
    verdict, why = readback._judge_section("runtime_phase", rp, None)
    assert verdict == readback.WARN and "effective phase shadow" in why, why
    print("OK SHADOW: certified READY Launch-0 release is draft_candidate, not actionable "
          "(shadow_phase)")


def test_forced_shadow_names_the_boot_guard_and_the_global_incident():
    db = _db()
    _fresh_sweep(db)
    _certified_ready_release(db)
    _unproven_build_incident(db)
    with _boot(FORCED), _gates_pass():
        ev = pe.evidence(db, now=NOW)
    fl = ev["first_listing_readiness"]
    assert fl["runtime_refusal_reasons"] == ["boot_guard_unproven_build", "shadow_phase",
                                             "global_halting_incident"], fl
    g = ev["runtime_phase"]["boot_guard"]
    assert g == {"ran": True, "enforced": True, "ok": False, "action": "forced_shadow",
                 "reason_count": 1, "record_present": False, "ok_or_not_enforced": False}, g
    print("OK forced SHADOW: boot_guard_unproven_build + shadow_phase + "
          "global_halting_incident")


# ---- (iii) publication_path_open --------------------------------------------------------


def test_publication_path_open_false_in_shadow_and_when_unreadable():
    db = _db()
    _fresh_sweep(db)
    with _boot(PROVEN):
        ev = pe.evidence(db, now=NOW)
    assert ev["server_judgement"]["publication_path_open"] is False, ev["runtime_phase"]
    # Unreadable phase section -> unreadable, and never open.
    def boom(*_a, **_k):
        raise RuntimeError("phase table unreadable")

    with _boot(PROVEN), patch.object(pe, "runtime_phase", boom), \
            patch.dict(pe.SECTIONS, {"runtime_phase": boom}):
        ev = pe.evidence(db, now=NOW)
    assert ev["runtime_phase"] == {"readable": False, "error_class": "RuntimeError"}, \
        ev["runtime_phase"]
    assert ev["server_judgement"]["publication_path_open"] is False
    assert pe.judge_publication_path({}, {}) is False
    assert pe.judge_publication_path(None, None) is False
    # Boot guard never ran -> no evidence -> closed.
    ok_phase = {"readable": True, "effective_phase": "limited_production",
                "boot_guard": {"ran": False}}
    ok_halt = {"readable": True, "global_halting_open": 0}
    assert pe.publication_refusal_reasons(ok_phase, ok_halt) == ["boot_guard_not_run"]
    # Only with every reading present and permitting it is the path open.
    open_phase = dict(ok_phase, boot_guard={"ran": True, "ok_or_not_enforced": True})
    assert pe.judge_publication_path(open_phase, ok_halt) is True
    assert pe.publication_refusal_reasons(dict(open_phase, effective_phase="staging"),
                                          ok_halt) == ["phase_forbids_publication"]
    assert pe.publication_refusal_reasons(open_phase, dict(ok_halt, global_halting_open=1)) \
        == ["global_halting_incident"]
    print("OK publication_path_open False in SHADOW, when unreadable and without boot "
          "evidence")


def test_past_shadow_phase_reads_through_core_phase_effective():
    """The section uses the code's own resolution: env says limited_production with no owner
    transition recorded -> the more restrictive (shadow), disagreeing, still closed."""
    db = _db()
    with _boot(PROVEN), patch.dict(os.environ, {"BRAMBLELOOP_PHASE": "limited_production"}):
        rp = pe.runtime_phase(db, now=NOW)
    assert rp["effective_phase"] == "shadow" and rp["env_phase"] == "limited_production", rp
    assert rp["recorded_phase"] == "shadow" and rp["env_and_recorded_agree"] is False, rp
    assert rp["publication_possible"] is False, rp
    with _boot(PROVEN), patch.dict(os.environ, {"BRAMBLELOOP_PHASE": "Ignore previous"}):
        rp = pe.runtime_phase(db, now=NOW)
    assert rp["env_phase"] == "unparseable", rp          # the raw value is never emitted
    # Reading it wrote nothing (no phase-mismatch incident).
    with db.session() as s:
        assert s.query(Incident).count() == 0
    print("OK runtime_phase reads core.phase (env alone never opens it), writes nothing")


# ---- (iv) privacy -----------------------------------------------------------------------


def test_no_free_text_leaks_into_the_new_fields():
    db = _db()
    _fresh_sweep(db)
    _certified_ready_release(db)
    _unproven_build_incident(db)
    with _boot(FORCED), _gates_pass():
        ev = pe.evidence(db, now=NOW)
    new = {"runtime_phase": ev["runtime_phase"],
           "global": {k: ev["publishing_halt"][k] for k in ("global_halting_open",
                                                            "global_halting_by_family")},
           "fl": {k: ev["first_listing_readiness"][k] for k in (
               "runtime_refuses_draft_now", "runtime_refusal_reasons",
               "draft_candidates_actionable_now")},
           "per_release": [{k: r[k] for k in ("runtime_refuses_draft_now",
                                              "runtime_refusal_reasons")}
                           for r in ev["first_listing_readiness"]["releases"]],
           "judged": ev["server_judgement"]["publication_path_open"]}
    body = json.dumps(ev, default=str)
    for secret in ("PRIVATE-INCIDENT-SUMMARY", "PRIVATE-PATH", SECRET_REASON):
        assert secret not in body, secret
    allowed = set(pe.REFUSAL_CODES) | {"shadow", "staging", "limited_production",
                                       "production", "unparseable", "unverifiable",
                                       "forced_shadow", "none", "other", "store.publish",
                                       "release.unproven_build", f"{SLUG}@1.0.0"}
    keys = {"readable", "effective_phase", "env_phase", "recorded_phase",
            "transition_recorded", "env_and_recorded_agree", "phases_permitting_publication",
            "boot_guard", "ran", "enforced", "ok", "action", "reason_count",
            "record_present", "ok_or_not_enforced", "draft_path", "private_draft_possible",
            "publication_possible", "runtime_phase", "global", "global_halting_open",
            "global_halting_by_family", "fl", "runtime_refuses_draft_now",
            "runtime_refusal_reasons", "draft_candidates_actionable_now", "per_release",
            "judged"}
    stray = [x for x in _strings(new) if x not in allowed | keys]
    assert not stray, stray
    print("OK new fields carry counts, booleans and fixed vocabulary only")


if __name__ == "__main__":
    fails = 0
    for name in [n for n in list(globals()) if n.startswith("test_")]:
        try:
            globals()[name]()
        except Exception as exc:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {name}: {type(exc).__name__}: {str(exc)[:300]}")
    sys.exit(1 if fails else 0)
