"""#41 and #42 through the runtime: the listing draft, the support desk and the order path.

The proof audit (2026-09-26) found `disclosure_check`, `confusion_rate` and `VersionMap` tested
as a library and called by nothing. These run the `listing.draft`, `support.triage` and
`support.reply` handlers through the worker, and write the order-to-version map the way the
order path will. Every buyer and order here is a test fixture; none is a customer.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.commerce import buyer_trust as bt  # noqa: E402
from brambleloop.commerce import cohorts  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Job, JobStatus, Listing, OrderVersion, PatternVersion, Product, SupportCase,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

GOOD_TITLE = "Fir Blanket | Crochet Pattern PDF | Written Instructions and Chart | US and UK Terms"
GOOD_DESCRIPTION = (
    "Fir Blanket — a crochet pattern, not a finished item. You receive an instant digital "
    "download.\n\nWHAT YOU GET\n- Two PDFs, one in US terms and one in UK terms\n"
    "THE DETAILS\n- Difficulty: Intermediate\n- Yarn: about 900-1000 m\n"
    "If anything does not add up, tell us.")


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/trust.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, agent: str, job_type: str, inputs: dict) -> dict:
    job = JobQueue(db).enqueue(agent, job_type, inputs, priority=0,
                               idempotency_key=f"t:{job_type}:{datetime.now().timestamp()}")
    assert Worker(db, "trust-test").run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        return dict(row.outputs or {})


def _product(db, slug: str, versions: dict[str, str]) -> None:
    with db.session() as s:
        product = Product(slug=slug, title=slug, status="certified")
        s.add(product)
        s.flush()
        for version, release_hash in versions.items():
            s.add(PatternVersion(product_id=product.id, version=version, cir_json={},
                                 release_hash=release_hash, certified=True))


# ---- #41: the draft ---------------------------------------------------------


def test_a_draft_missing_an_owed_disclosure_gets_a_finding():
    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug="fir", version="1.0.0", title="Cosy Fir Throw Blanket",
                      description="A lovely throw for winter evenings."))
    out = _run(db, "listing", "listing.draft", {"slug": "fir", "version": "1.0.0"})
    finding = out["disclosures"]
    assert finding["checked"] is True and finding["finding"] is True
    missing = {m["disclosure"] for m in finding["missing"]}
    assert {"digital_not_finished", "terminology", "delivery", "skill_level"} <= missing
    with db.session() as s:
        audited = [a for a in s.scalars(select(AuditLog)) if a.artifact == "fir@1.0.0"
                   and a.action.startswith("listing.disclosure")]
        assert audited and audited[0].detail["missing"], "the finding was not recorded"


def test_a_complete_draft_has_no_finding_and_an_unwritten_one_is_unmeasured():
    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug="fir", version="1.0.0", title=GOOD_TITLE,
                      description=GOOD_DESCRIPTION))
    out = _run(db, "listing", "listing.draft", {"slug": "fir", "version": "1.0.0"})
    assert out["disclosures"]["complete"] is True and out["disclosures"]["finding"] is False

    none = _run(db, "listing", "listing.draft", {"slug": "moss", "version": "1.0.0"})
    assert none["disclosures"]["checked"] is False
    assert none["disclosures"]["reading"] == "UNMEASURED"


def test_the_digital_disclosure_belongs_in_the_title():
    present = bt.disclosures_from_copy(title="Fir Throw Blanket", description=GOOD_DESCRIPTION)
    result = bt.disclosure_check(present)
    assert [m["disclosure"] for m in result["misplaced"]] == ["digital_not_finished"]


# ---- #41: support readings -------------------------------------------------


def test_support_readings_carry_confusion_and_an_unknown_case_window():
    db = _db()
    with db.session() as s:
        s.add(SupportCase(customer_ref="fixture-1", question="is this not a finished blanket?",
                          resolved=False))
    out = _run(db, "support", "support.triage", {})
    readings = out["readings"]
    assert readings["confusion"]["measurable"] is False       # no orders
    assert readings["confusion"]["confusion_contacts"] == 1
    window = readings["case_window"]
    assert window["known"] is False and window["days"] is None
    assert window["deadline"] == "UNKNOWN"
    assert readings["deadlines"] == [{"case": 1, "resolve_before": "UNKNOWN"}]


def test_no_recorded_policy_reading_states_a_case_window_in_days():
    """If a reading ever records one, the window is read from it -- never assumed."""
    assert bt.case_window()["known"] is False


# ---- #42: the order-to-version map -----------------------------------------


def test_the_order_path_writes_the_version_and_support_answers_from_it():
    db = _db()
    _product(db, "fir", {"1.0.0": "a" * 64})
    cohorts.record_customer(db, "fixture-buyer", first_product_slug="fir")
    order = cohorts.record_order(db, "fixture-buyer", "order-1", product_slug="fir",
                                 version="1.0.0", price_cad=12.0, contribution_cad=9.0)
    # The order path itself writes the version at sale time (#42); nobody has to remember to.
    written = order["version_recorded"]
    assert written["created"] and written["release_hash"] == "a" * 64
    assert bt.record_sale_version(db, order_ref="order-1", product_slug="fir",
                                  version="1.0.0")["created"] is False
    assert bt.record_sale_version(db, order_ref="order-1", product_slug="fir",
                                  version="9.9.9")["created"] is False

    reply = _run(db, "support", "support.reply",
                 {"slug": "fir", "question": "Which version did I buy?",
                  "customer_ref": "fixture-buyer"})
    assert reply["specialist"] == "version" and reply["escalated"] is False
    assert reply["cited_version"] == "fir@1.0.0"
    assert "order-1" in reply["body"] and "current version" in reply["body"]
    assert reply["sent"] is False

    # A correction is certified: the same buyer is now told they hold an older build.
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == "fir"))
        s.add(PatternVersion(product_id=product.id, version="1.1.0", cir_json={},
                             release_hash="b" * 64, certified=True))
    again = _run(db, "support", "support.reply",
                 {"slug": "fir", "question": "which version do I have now?",
                  "customer_ref": "fixture-buyer"})
    assert "1.1.0" in again["body"] and again["cited_version"] == "fir@1.0.0"


def test_an_unrecorded_buyer_is_handed_off_not_guessed_at():
    db = _db()
    reply = _run(db, "support", "support.reply",
                 {"slug": "fir", "question": "what version is my pattern?",
                  "customer_ref": "fixture-nobody"})
    assert reply["escalated"] is True and reply["cited_version"] is None


def test_the_correction_notice_reads_affected_buyers_from_the_table():
    db = _db()
    _product(db, "fir", {"1.0.0": "a" * 64, "1.1.0": "b" * 64})
    sold = datetime(2026, 9, 1, tzinfo=timezone.utc)
    bt.record_sale_version(db, order_ref="o-old", product_slug="fir", version="1.0.0",
                           sold_at=sold)
    bt.record_sale_version(db, order_ref="o-new", product_slug="fir", version="1.1.0")
    notice = bt.correction_notice(
        db=db, product_slug="fir", from_versions=("1.0.0",), to_version="1.1.0",
        what_changed="Row 12 read 84 stitches and should read 86 stitches.")
    assert notice["affected_orders"] == ["o-old"] and notice["sent"] is False
    with db.session() as s:
        row = s.scalar(select(OrderVersion).where(OrderVersion.order_ref == "o-old"))
        assert row.correction_notice_sent_at is None, "shadow mode sent nothing"
        assert row.current_safe_version == "1.1.0"
    assert bt.purchased_versions(db, order_ref="o-old")[0]["superseded"] is True


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
