"""The route from a phone to the quarantine, and the four ways it could go wrong.

Intake exists so the owner types one thing — which pick this is — and so the files that
arrive are still there next week. Both of those are claims that can be false quietly, so
they are the ones tested hardest: a manifest filled from the catalogue, an upload that
reports honestly that it was not made durable, a zip that cannot write outside its folder,
and a promise audit that does not resolve its unknowns in the seller's favour or ours.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core import offsite  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing, BenchmarkProduct  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.teardown import intake, library  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _listing(db, ref="1234", *, pod="blankets", price=8.5, detail=None, title="Chunky throw",
             media=10) -> None:
    with db.session() as s:
        s.add(BenchmarkListing(
            benchmark_key=benchmarks.MJS_KEY, listing_ref=ref, title=title, pod=pod,
            product_type="pattern", price_cad=price, media_count=media,
            url=f"https://www.etsy.com/listing/{ref}", detail=detail or {}))


def _env(tmp: Path) -> dict:
    return {library.LIBRARY_ENV: str(tmp)}


def _zip(entries: list[tuple[str, bytes]], *, compress: bool = False) -> bytes:
    buf = io.BytesIO()
    mode = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(buf, "w", mode) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Names and what may be written at all


def test_a_filename_cannot_climb_out_of_the_purchase_folder() -> None:
    assert intake.safe_name("../../etc/passwd") == "passwd"
    assert intake.safe_name("C:\\Users\\me\\chart.pdf") == "chart.pdf"
    for bad in ("", "   ", "../", "..", "/"):
        try:
            intake.safe_name(bad)
        except intake.IntakeRefused:
            continue
        raise AssertionError(f"{bad!r} produced a usable filename")


def test_only_a_pattern_deliverable_is_accepted(tmp_path: Path = None) -> None:
    for good in ("pattern.pdf", "chart.PNG", "notes.txt", "tutorial.mp4"):
        intake._check_suffix(good)
    for bad in ("run.sh", "payload.py", "thing.exe", "noext"):
        try:
            intake._check_suffix(bad)
        except intake.IntakeRefused:
            continue
        raise AssertionError(f"{bad!r} was accepted onto a production filesystem")


def test_a_zip_entry_that_climbs_is_refused() -> None:
    blob = _zip([("../../escape.pdf", b"x")])
    try:
        intake.expand("bundle.zip", blob)
    except intake.IntakeRefused as exc:
        assert "climbs" in str(exc)
        return
    raise AssertionError("a zip entry wrote outside the quarantine")


def test_a_zip_is_expanded_and_its_rubbish_left_out() -> None:
    blob = _zip([("Chunky/pattern.pdf", b"PDF"), ("__MACOSX/._pattern.pdf", b"junk"),
                 ("Chunky/readme.nfo", b"no"), ("Chunky/chart.png", b"PNG")])
    out = intake.expand("bundle.zip", blob)
    assert sorted(n for n, _ in out) == ["chart.png", "pattern.pdf"]


def test_a_zip_bomb_is_refused() -> None:
    blob = _zip([("big.pdf", b"\0" * (4 * 1024 * 1024))], compress=True)
    try:
        intake.expand("bomb.zip", blob)
    except intake.IntakeRefused as exc:
        assert "not a pattern bundle" in str(exc)
        return
    raise AssertionError("a 4MB-from-nothing zip was expanded")


def test_a_file_that_is_not_a_zip_is_passed_through_untouched() -> None:
    assert intake.expand("pattern.pdf", b"PDF") == [("pattern.pdf", b"PDF")]


# ---------------------------------------------------------------------------
# The manifest fills itself


def test_intake_fills_the_manifest_from_the_catalogue(tmp_path: Path) -> None:
    db = _db()
    _listing(db, "1234", pod="blankets", price=9.25, title="Chunky throw")
    result = intake.receive(db, "1234", [("Chunky-pattern.pdf", b"PDF"),
                                         ("chart.png", b"PNG")],
                            env=_env(tmp_path), mirror_files=False)

    assert result["ref"] == "mjs-1234"
    assert result["file_count"] == 2
    assert result["department"] == "blankets"
    # The owner supplied a listing reference and two files. Everything else was looked up.
    assert result["paid_cad"] == 9.25
    assert "observed listing price" in result["paid_source"]
    assert result["needs_owner"] == []

    with db.session() as s:
        row = s.query(BenchmarkProduct).filter_by(ref="mjs-1234").one()
        assert row.seller == benchmarks.MJS_SHOP
        assert row.pod == "blankets"
        assert row.listing_ref == "1234"
        assert row.teardown_state == intake.AWAITING_ANALYST
        assert {f["role"] for f in row.files} == {"pattern_pdf", "chart"}
        # Filenames, sizes and hashes -- never contents.
        assert all(set(f) == {"name", "role", "bytes", "sha256"} for f in row.files)


def test_a_pick_outside_the_observed_catalogue_is_refused(tmp_path: Path) -> None:
    db = _db()
    try:
        intake.receive(db, "9999", [("p.pdf", b"x")], env=_env(tmp_path), mirror_files=False)
    except intake.IntakeRefused as exc:
        assert "not in the observed MJs catalogue" in str(exc)
        return
    raise AssertionError("a manifest was registered against a listing nobody observed")


def test_the_manifest_holds_no_competitor_text(tmp_path: Path) -> None:
    db = _db()
    _listing(db, "1234")
    intake.receive(db, "1234", [("pattern.pdf", b"Row 1: ch 3, dc in each")],
                   env=_env(tmp_path), mirror_files=False)
    with db.session() as s:
        row = s.query(BenchmarkProduct).filter_by(ref="mjs-1234").one()
    blob = repr(row.files) + repr(row.listing_promises) + (row.why_selected or "")
    assert "ch 3" not in blob and "dc in each" not in blob


# ---------------------------------------------------------------------------
# Promise against delivery


def test_an_unobserved_promise_is_unverifiable_not_kept() -> None:
    audit = intake.deliverable_audit({}, {"pattern_pdfs": 1})
    # Not "consistent": nothing was actually compared. A verdict computed from the absence
    # of failures passes an audit that did not happen.
    assert audit["verdict"] == "unaudited"
    assert {c["claim"] for c in audit["unverifiable"]} == {
        "has_video", "has_chart", "has_print_edition"}
    assert audit["kept"] == []


def test_a_promised_chart_that_did_not_arrive_is_a_gap() -> None:
    audit = intake.deliverable_audit({"has_chart": True}, {"has_chart": False,
                                                           "pattern_pdfs": 1})
    assert audit["verdict"] == "gap"
    assert audit["missing"][0]["claim"] == "has_chart"
    assert "analyst confirms" in audit["missing"][0]["why"]


def test_no_pattern_document_at_all_is_a_gap() -> None:
    audit = intake.deliverable_audit({"has_chart": True}, {"has_chart": True,
                                                           "pattern_pdfs": 0})
    assert audit["verdict"] == "gap"
    assert any(m["claim"] == "pattern_document" for m in audit["missing"])


def test_promises_are_read_from_the_listing_and_absence_stays_unknown() -> None:
    promises = intake.promises_from_listing({"detail": {"has_video": True}, "price_cad": 8.0})
    assert promises["has_video"] is True
    assert promises["has_chart"] is None       # never observed -- not "no chart"
    assert promises["observed_price_cad"] == 8.0


# ---------------------------------------------------------------------------
# Durability, which is the claim most worth not overstating


def test_an_unmirrored_upload_reports_that_it_is_not_durable(tmp_path: Path) -> None:
    db = _db()
    _listing(db, "1234")
    result = intake.receive(db, "1234", [("pattern.pdf", b"PDF")], env=_env(tmp_path))
    assert result["durable"] is False
    assert "replaces on every deploy" in result["offsite"]["why"]


def test_a_mirrored_upload_writes_every_file_and_says_so(tmp_path: Path) -> None:
    db = _db()
    _listing(db, "1234")
    env = {**_env(tmp_path),
           offsite.ENDPOINT_VAR: "https://s3.example.com", offsite.BUCKET_VAR: "bl",
           offsite.KEY_ID_VAR: "k", offsite.SECRET_VAR: "s",
           offsite.ENCRYPTION_KEY_VAR: "a passphrase long enough to stretch"}
    written: dict[str, bytes] = {}

    original = offsite._call
    offsite._call = lambda dest, method, key, payload=b"", **kw: (
        written.__setitem__(key, payload) or b"")
    try:
        result = intake.receive(db, "1234", [("pattern.pdf", b"PDF"), ("chart.png", b"PNG")],
                                env=env)
    finally:
        offsite._call = original

    assert result["durable"] is True
    assert result["offsite"]["mirrored"] == 2
    assert len(written) == 2
    # Sealed, not plain: a competitor's purchased file reaching a third-party bucket in the
    # clear is a different decision from backing it up.
    assert all(blob.startswith(offsite.ENCRYPTION_HEADER) for blob in written.values())
    assert all(b"PDF" not in blob and b"PNG" not in blob for blob in written.values())
    assert all(key.startswith("benchmark/mjs-1234/") for key in written)


def test_a_mirror_failure_does_not_report_a_durable_upload(tmp_path: Path) -> None:
    db = _db()
    _listing(db, "1234")
    env = {**_env(tmp_path),
           offsite.ENDPOINT_VAR: "https://s3.example.com", offsite.BUCKET_VAR: "bl",
           offsite.KEY_ID_VAR: "k", offsite.SECRET_VAR: "s",
           offsite.ENCRYPTION_KEY_VAR: "a passphrase long enough to stretch"}

    def _boom(*a, **kw):
        raise offsite.TransientError("the store said 503")

    original = offsite._call
    offsite._call = _boom
    try:
        result = intake.receive(db, "1234", [("pattern.pdf", b"PDF")], env=env)
    finally:
        offsite._call = original

    # The files are still filed; the claim that they will survive is not made.
    assert result["file_count"] == 1
    assert result["durable"] is False
    assert result["offsite"]["failed"] == 1


def test_benchmark_mirrors_are_not_aged_out_by_the_continuity_retention(tmp_path: Path) -> None:
    """`prune` works from continuity's own audit rows. A purchase is not a snapshot."""
    db = _db()
    _listing(db, "1234")
    env = {**_env(tmp_path),
           offsite.ENDPOINT_VAR: "https://s3.example.com", offsite.BUCKET_VAR: "bl",
           offsite.KEY_ID_VAR: "k", offsite.SECRET_VAR: "s",
           offsite.ENCRYPTION_KEY_VAR: "a passphrase long enough to stretch"}
    deleted: list[str] = []

    original = offsite._call
    offsite._call = lambda dest, method, key, payload=b"", **kw: (
        deleted.append(key) if method == "DELETE" else None) or b""
    try:
        intake.receive(db, "1234", [("pattern.pdf", b"PDF")], env=env)
        offsite.prune(db, env=env, keep=0)
    finally:
        offsite._call = original

    assert not any(k.startswith("benchmark/") for k in deleted)


# ---------------------------------------------------------------------------
# What the phone sees


def test_the_plan_marks_what_has_already_arrived(tmp_path: Path) -> None:
    db = _db()
    for i, pod in enumerate(("blankets", "amigurumi", "wearables")):
        _listing(db, str(1000 + i), pod=pod, price=6.0 + i, title=f"Thing {i}")
    before = intake.plan(db)
    assert before["received"] == 0
    assert len(before["picks"]) >= 1
    first = before["picks"][0]["listing_ref"]

    intake.receive(db, first, [("pattern.pdf", b"PDF")], env=_env(tmp_path),
                   mirror_files=False)
    after = intake.plan(db)
    assert after["received"] == 1
    assert first not in after["outstanding"]
    assert next(p for p in after["picks"] if p["listing_ref"] == first)["files"] == 1


def test_the_plan_warns_while_nothing_is_durable(tmp_path: Path) -> None:
    db = _db()
    _listing(db, "1234")
    state = intake.plan(db, env={})["durable"]
    assert state["configured"] is False
    assert "replaces on every deploy" in state["warning"]


def test_the_approved_set_size_and_budget_are_in_code(tmp_path: Path) -> None:
    assert intake.SET_SIZE == 13
    assert intake.SET_BUDGET_CAD == 300.0


def _run() -> int:
    import inspect

    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        kwargs = {}
        tmp = None
        if "tmp_path" in inspect.signature(fn).parameters:
            tmp = tempfile.mkdtemp(prefix="intake-test-")
            kwargs["tmp_path"] = Path(tmp)
        try:
            fn(**kwargs)
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
        finally:
            if tmp:
                import shutil

                shutil.rmtree(tmp, ignore_errors=True)
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
