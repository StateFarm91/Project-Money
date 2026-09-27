"""gates.policy_knowledge: Etsy commerce knowledge as dated, sourced, digested readings, and the
policy watch seeding them for a source nobody has read (#35, #39, Build 2 commerce closeout).

The failure this guards against is the opposite of the one #39 guards against: a watch that
says "never read" forever because the only reader it knows is a fetcher the platform refuses.
A reading with its basis declared is a reading; one with its basis hidden would be a lie."""
import os, sys, tempfile
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from brambleloop.core.db import Database
from brambleloop.gates import platform_policy as PP, policy_knowledge as PK

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

check("every watched surface has a reading", set(PK.READINGS) == set(PP.POLICY_SOURCES), str(set(PP.POLICY_SOURCES) ^ set(PK.READINGS)))
check("every reading declares its basis, date, official URLs, conclusions and verbatim excerpts", all(r.basis in (PK.BASIS_EXCERPT, PK.BASIS_PAGE) and r.read_on and r.urls and r.conclusions and r.excerpts for r in PK.all_readings().values()))
check("every excerpt names an etsy.com or help.etsy.com URL", all(("etsy.com" in e.url) for r in PK.all_readings().values() for e in r.excerpts))
check("the retrieval block is stated, not hidden", "403" in PK.RETRIEVAL_BLOCK and "excerpt" in PK.BASIS_EXCERPT)
check("digests are stable across calls", all(r.digest() == r.digest() and r.digest() == type(r)(**{f: getattr(r, f) for f in r.__dataclass_fields__}).digest() for r in PK.all_readings().values()))
check("digests differ between readings", len({r.digest() for r in PK.all_readings().values()}) == len(PK.all_readings()))
check("the reading of the children policy says patterns and instructions are in scope", any("instructions" in c["text"] for c in PK.READINGS["children_and_baby"].conclusions))
check("the AI disclosure rule is recorded on the seller policy and the creativity standards", any(c["rule"] == "ai_disclosure_required" for c in PK.READINGS["seller_policy"].conclusions) and any("disclosure" in c["rule"] for c in PK.READINGS["creativity_standards"].conclusions))
check("fee facts agree with the code's constants (US$0.20 listing, 6.5% transaction)", any("0.20" in c["amount"] for c in PK.TOPICS["fees"].conclusions) and any("6.5%" in c["amount"] for c in PK.TOPICS["fees"].conclusions))
from brambleloop.commerce import pricing; from brambleloop.scale import target
check("the code's transaction and listing fee constants match the recorded policy", pricing.TRANSACTION_FEE == 0.065 == target.TRANSACTION_FEE_RATE and target.LISTING_FEE_USD == 0.20)
check("an unknown fee stays UNKNOWN rather than invented (Canadian regulatory operating fee)", any(c["fee"] == "regulatory_operating" and "UNKNOWN" in c["amount"] for c in PK.TOPICS["fees"].conclusions))

with tempfile.TemporaryDirectory() as d:
    db = Database(f"sqlite:///{d}/t.db"); db.create_all()
    today = date(2026, 9, 27)
    before = PP.freshness(db, today=today)
    check("before seeding every surface is never-checked", set(before["never_checked"]) == set(PP.POLICY_SOURCES))
    res = PK.seed_snapshots(db, today=today)
    check("seeding records one snapshot per never-read surface with the reading's own date and basis", len(res["seeded"]) == len(PP.POLICY_SOURCES) and all(s["read_on"] == PK.READ_ON and s["basis"] == PK.BASIS_EXCERPT for s in res["seeded"]))
    after = PP.freshness(db, today=today)
    check("after seeding the watch reports every surface current (read 1 day ago)", after["all_fresh"] and not after["never_checked"], str(after))
    check("seeding again records nothing (never over an existing snapshot)", PK.seed_snapshots(db, today=today)["seeded"] == [])
    late = PP.freshness(db, today=date(2026, 11, 15))
    check("a repository reading goes stale on the same 30-day rule as any snapshot", len(late["stale"]) == len(PP.POLICY_SOURCES) and not late["all_fresh"])
    check("a page reading recorded by the owner supersedes the excerpt reading", PP.record_snapshot(db, "seller_policy", text="page text read by hand", version="2026-11-15:page", checked_on="2026-11-15")["material_change"] is True and PP.freshness(db, today=date(2026, 11, 15))["stale"].__len__() == len(PP.POLICY_SOURCES) - 1)
    stamp = PP.policy_stamp(db, today=today)
    check("a certificate stamp names the seeded versions with their basis", all(":search_engine_excerpt_of_official_page" in v for k, v in stamp["sources"].items() if k != "seller_policy"))
# the watch handler seeds, then resolves the incidents it opened
with tempfile.TemporaryDirectory() as d:
    db = Database(f"sqlite:///{d}/t.db"); db.create_all()
    from brambleloop.core.models import Incident
    from brambleloop.runtime import release as RL
    class Ctx:
        def __init__(self, db): self.db = db; self.audits = []
        def audit(self, kind, detail=None, **kw): self.audits.append((kind, detail))
    with db.session() as s:
        for src in PP.POLICY_SOURCES:
            s.add(Incident(severity="P2", signature=f"policy_stale:{src}", summary=f"Etsy {src} has never been read.", halts_publication=False, detail={"source": src}))
    out = RL.handle_policy_watch(Ctx(db))
    with db.session() as s:
        from sqlalchemy import select
        open_ = [i.signature for i in s.scalars(select(Incident).where(Incident.resolved == False))]  # noqa: E712
        resolved = [i for i in s.scalars(select(Incident).where(Incident.resolved == True))]  # noqa: E712
    check("the watch seeds the readings and resolves each policy incident with the snapshot named", out["all_fresh"] and not open_ and len(resolved) == len(PP.POLICY_SOURCES) and all("read on" in r.detail.get("resolution", "") for r in resolved), str((out, open_)))
    check("the watch's own note names the retrieval block rather than claiming a fetch", "bot" in out["note"] and "seeds" in out["note"])
print(f"\n  {PASSED} passing, {FAILED} failing"); sys.exit(1 if FAILED else 0)
