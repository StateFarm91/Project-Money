"""W4-B2GATE2: the gated Build 2 rows re-read against production, and three fixes it found.

1. #140 / `lead_lag_series`. Production (GET /api/culture at 0417f35, 2026-10-11) served
   lead_lag "measurable" for four signals, and the gate would have opened on it. Every one was
   an artefact: each marketplace series holds 1.0 on 2026-09-13..19 (the single-pass catalogue
   baseline), so max() returned the day observation began. `radar.lead_lag` now refuses a
   plateau by name. The production series are vendored in
   research/final_build/w4/evidence_B2GATE2 and re-run here through the gate's own function.
2. #35 / #39. `gates.policy_access` records, per etsy.com/legal source, what software may read
   (robots.txt; Etsy Help Center articles that link the page, as change signals) and why the
   page itself needs a person. It never requests a legal page and never opens the gate. The
   recurring reading is a PROPOSAL to the owner, not a duty imposed.
3. #11 / #12. The transactions_r card names the second half of its gate: the Etsy credential
   must read (production's etsy.probe has been refused since 2026-10-07).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_b2gate2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
EV = ROOT / "research/final_build/w4/evidence_B2GATE2"
_TMP = tempfile.mkdtemp()


def ok(msg: str) -> None:
    print(f"  ok  {msg}")


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/d{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _gate(db, key):
    from brambleloop.build2 import executor as E

    return E.GATE_BY_KEY[key].open(db, {})


# ---- 1. #140: a plateau is not a peak ------------------------------------------------------


def test_lead_lag_refuses_a_plateau_and_names_it():
    from brambleloop.culture import radar as R

    db = _db()
    for i, v in enumerate((0.2, 0.9, 0.4)):
        R.observe(db, "t", channel="reference", interest=v, observed_on=f"2026-09-1{i}")
    for d in ("2026-09-01", "2026-09-02", "2026-09-03"):
        R.observe(db, "t", channel="etsy", interest=1.0, observed_on=d)
    R.observe(db, "t", channel="etsy", interest=0.2, observed_on="2026-09-04")
    out = R.lead_lag(db, "t")
    assert out["measurable"] is False, out
    assert out["plateau"] == {"series": "demand", "value": 1.0, "dates": 3,
                              "from": "2026-09-01", "to": "2026-09-03"}, out
    assert "plateau has no peak date" in out["reason"]
    assert not _gate(db, "lead_lag_series")
    ok("a maximum held on 3 dates is refused by name and keeps the gate closed")


def test_a_distinct_peak_is_still_measured_and_two_tied_dates_are_not_a_plateau():
    from brambleloop.culture import radar as R

    db = _db()
    for d, v in (("2026-08-01", 0.3), ("2026-08-10", 0.9), ("2026-08-20", 0.5)):
        R.observe(db, "s", channel="reference", interest=v, observed_on=d)
    for d, v in (("2026-09-01", 0.6), ("2026-09-02", 0.6), ("2026-09-15", 1.0)):
        R.observe(db, "s", channel="etsy", interest=v, observed_on=d)
    out = R.lead_lag(db, "s")
    assert out["measurable"] is True and out["lead_days"] == 36, out
    assert _gate(db, "lead_lag_series")
    db2 = _db()
    for d in ("2026-09-01", "2026-09-08"):
        R.observe(db2, "u", channel="reference", interest=1.0, observed_on=d)
    for d, v in (("2026-09-01", 0.5), ("2026-09-15", 1.0)):
        R.observe(db2, "u", channel="etsy", interest=v, observed_on=d)
    assert R.lead_lag(db2, "u")["measurable"] is True
    ok("a distinct peak is measured (36 days); a 2-date tie is not a plateau")


def test_productions_own_series_measure_nothing_once_the_plateau_is_refused():
    from brambleloop.culture import radar as R

    culture = json.loads((EV / "prod_culture_2026-10-11.json").read_text())
    db = _db()
    served = {}
    for f in culture["findings"]["findings"]:
        served[f["signal"]] = (f.get("lead_lag") or {}).get("measurable")
        for p in f["momentum"].get("series") or []:
            R.observe(db, f["signal"], channel=p["channel"], interest=float(p["interest"]),
                      observed_on=p["on"])
    assert sorted(s for s, m in served.items() if m) == [
        "crochet", "crochet_hook", "granny_square", "halloween"], served
    now = {s: R.lead_lag(db, s) for s in served}
    assert not [s for s, v in now.items() if v["measurable"]], now
    for s in ("crochet", "crochet_hook", "granny_square", "halloween"):
        assert now[s].get("plateau"), now[s]
        # The marketplace half of every one is the baseline plateau: 1.0 from 2026-09-13.
        demand = [p for p in R._series(db, s) if p["channel"] == "etsy"]
        top = sorted({p["on"] for p in demand if p["interest"] == 1.0})
        assert len(top) >= R.PLATEAU_MIN_DATES and top[0] == "2026-09-13", (s, top)
    assert not _gate(db, "lead_lag_series")
    derived = json.loads((EV / "derived_data_gates_2026-10-11.json").read_text())
    assert derived["gates"]["lead_lag_series"]["open"] is False
    ok("production's 4 'measurable' lead-lags were plateau artefacts; the gate stays closed")


# ---- 2. #35 / #39: what software may read, and what needs a person -------------------------

ROBOTS = """User-agent: Googlebot
Disallow: /legal/

User-agent: *
Disallow: /api/
Disallow: /*handmade/
Disallow: /*?order=*
Allow: /legal/
"""


def _article(aid, links, edited="2026-07-01T00:00:00Z", extra=""):
    body = " ".join(f'<a href="https://www.etsy.com{p}">x</a>' for p in links)
    return {"article": {"id": int(aid), "title": f"article {aid}", "edited_at": edited,
                        "draft": False, "body": f"<p>{'policy words ' * 30}{extra}</p>{body}"}}


def _fetchers(articles, robots=ROBOTS):
    seen: list[str] = []

    def fetch_json(url):
        seen.append(url)
        aid = url.rsplit("/", 1)[1].split(".")[0]
        return articles[aid]

    def fetch_text(url):
        seen.append(url)
        return robots
    return seen, fetch_json, fetch_text


def _articles(**override):
    from brambleloop.gates import policy_access as PA

    base = {}
    for source, comps in PA.COMPANIONS.items():
        for aid, frags in comps:
            base.setdefault(aid, set()).add(frags[0])
    out = {aid: _article(aid, sorted(fr)) for aid, fr in base.items()}
    out.update(override)
    return out


def test_robots_verdicts_follow_the_star_group_with_wildcards_and_literal_question_marks():
    from brambleloop.gates import policy_access as PA

    v = lambda u: PA.robots_verdict(ROBOTS, u)["robots"]  # noqa: E731
    assert v("https://www.etsy.com/legal/handmade/") == "disallowed"
    assert PA.robots_verdict(ROBOTS, "https://www.etsy.com/legal/handmade/")["rule"] == \
        "Disallow: /*handmade/"
    assert v("https://www.etsy.com/legal/sellers/") == "allowed"  # Googlebot group ignored
    assert v("https://www.etsy.com/api/v3") == "disallowed"
    assert v("https://www.etsy.com/c/x?order=1") == "disallowed"
    assert v("https://www.etsy.com/c/xorder=1") == "allowed"  # '?' is literal in robots
    ok("robots.txt: `*` group, longest match, wildcards, literal '?'")


def test_assess_never_requests_a_legal_page_and_records_signals_per_source():
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog
    from brambleloop.gates import platform_policy as PP
    from brambleloop.gates import policy_access as PA

    db = _db()
    seen, fj, ft = _fetchers(_articles())
    rep = PA.assess(db, fetch_json=fj, fetch_text=ft, sleep=lambda s: None)
    assert seen[0] == PA.ROBOTS_URL
    assert all(u == PA.ROBOTS_URL or u.startswith("https://help.etsy.com/api/v2/help_center/")
               for u in seen), seen
    assert not [u for u in seen if "/legal/" in u]
    assert sorted(rep["sources"]) == ["advertising_rules", "children_and_baby",
                                      "creativity_standards", "seller_policy",
                                      "shilling_and_reviews"]
    for s, v in rep["sources"].items():
        assert v["needs_person"] is True and "DataDome" in v["direct_fetch"]
    assert rep["sources"]["children_and_baby"]["machine_signal"] == "none"
    assert "no machine change signal" in rep["sources"]["children_and_baby"]["why_person"]
    assert rep["sources"]["seller_policy"]["machine_signal"] == "help_center_companion"
    cs = rep["sources"]["creativity_standards"]
    assert [r["robots"] for r in cs["robots"]] == ["disallowed", "allowed"]
    assert "robots.txt also disallows" in cs["why_person"]
    with db.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == PA.AUDIT_ACTION)) is not None
    # Evidence of the company's half opens nothing: the gate is the person's reading.
    assert PP.page_readings_status(db)["open"] is False
    assert not _gate(db, "rendered_pages")
    ok("assess: robots + Help Center only, never a legal page; the gate stays closed")


def test_a_companion_that_stops_linking_or_changes_is_said_so():
    from brambleloop.gates import policy_access as PA

    db = _db()
    _s, fj, ft = _fetchers(_articles())
    PA.assess(db, fetch_json=fj, fetch_text=ft, sleep=lambda s: None)
    changed = _articles(**{"360033701174": _article("360033701174", ["/legal/advertising"],
                                                    edited="2026-10-10T00:00:00Z",
                                                    extra="new rule"),
                           "360000338367": _article("360000338367", ["/legal/fees"])})
    _s, fj, ft = _fetchers(changed)
    rep = PA.assess(db, fetch_json=fj, fetch_text=ft, sleep=lambda s: None)
    comps = {c["article_id"]: c for c in rep["sources"]["advertising_rules"]["companions"]}
    assert comps["360033701174"]["changed_since_last_run"] is True
    assert comps["360000338367"]["links_policy_page"] is False
    assert rep["changed_companions"] == ["advertising_rules"]
    st = PA.status(db)
    assert st["sources"]["advertising_rules"]["reread_suggested"] is True
    assert st["sources"]["seller_policy"]["reread_suggested"] is False
    assert st["gate_open"] is False
    ok("an edited companion suggests a re-read; an unlinked one is not a companion")


def test_reread_is_suggested_when_etsy_edits_after_the_persons_reading():
    from brambleloop.core.models import AuditLog
    from brambleloop.gates import platform_policy as PP
    from brambleloop.gates import policy_access as PA

    db = _db()
    res = PP.record_page_reading(db, source="seller_policy", text="the seller policy " * 20,
                                 read_by="owner", checked_on="2026-10-01")
    with db.session() as s:
        s.add(AuditLog(actor="owner", action=PP.PAGE_READING_AUDIT, detail={"id": res["id"]}))
    arts = _articles(**{"115015808588": _article("115015808588", ["/legal/sellers",
                                                                  "/legal/policy/shilling"],
                                                 edited="2026-10-05T00:00:00Z")})
    _s, fj, ft = _fetchers(arts)
    PA.assess(db, fetch_json=fj, fetch_text=ft, sleep=lambda s: None)
    st = PA.status(db)
    sp = st["sources"]["seller_policy"]
    assert sp["person_reading"]["ok"] is True
    assert sp["reread_suggested"] is True and "115015808588" in sp["why"], sp
    assert st["gate_open"] is False  # four sources still unread
    ok("Etsy edited a linking article after the owner's reading: re-read suggested")


def test_the_recurring_reading_is_a_proposal_not_an_imposed_duty():
    from brambleloop.build2 import closure as C
    from brambleloop.ops import owner_queue as Q

    d = Q.DECISION_BY_GATE["rendered_pages"]
    assert d["id"] == "policy_page_reading"
    assert d["decision"].startswith("PROPOSAL for your approval (not yet accepted)")
    assert "Accept, decline" in d["decision"]
    assert d["max_cost_cad"] == 0.0 and d["minutes"] == 15
    assert "PROPOSAL" in C.PERSON_OPENED_GATES["rendered_pages"]
    assert "policy_access" in C.PERSON_OPENED_GATES["rendered_pages"]
    ok("policy_page_reading is a CA$0 proposal the owner may accept or decline")


def test_the_transactions_card_names_the_etsy_credential_half_of_its_gate():
    from brambleloop.commerce import orders_ingest
    from brambleloop.ops import owner_queue as Q

    d = Q.DECISION_BY_GATE["transactions_r"]
    assert "etsy.probe" in d["decision"] and "ETSY_SHARED_SECRET" in d["decision"]
    db = _db()
    missing = orders_ingest.gate(db)["missing"]
    assert any(m.startswith("etsy_api") for m in missing), missing
    ok("transactions_r: re-authorising alone cannot open it while etsy.probe is refused")


def test_policy_watch_and_api_reach_policy_access():
    from brambleloop.build2 import reachability

    v = reachability.reached("gates/policy_access.py")
    assert v["reached"], v
    src = (ROOT / "src/brambleloop/runtime/release.py").read_text()
    assert "policy_access.assess(ctx.db)" in src
    ok("gates/policy_access.py is reached from the running system")


def test_the_ledger_names_a_derived_reading_by_its_own_source():
    from brambleloop.build2 import closure as C

    led = C.ledger(gate_open={"lead_lag_series": False}, gate_source="prod /api/build",
                   gate_sources={"lead_lag_series": "derived from GET /api/culture"})
    row = next(r for r in led["rows"] if r["id"] == 140)
    assert row["state"] == "DATA-GATED"
    assert row["gate"]["state"] == "closed"
    assert row["gate"]["state_source"] == "derived from GET /api/culture"
    ok("a derived gate reading carries its own source in the ledger")


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {t.__name__}: {exc}")
        print(f"     ({time.time() - t0:.1f}s)")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
