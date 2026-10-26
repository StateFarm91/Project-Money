"""F-415: every locked package, bundled font and called provider has a licence/terms row;
unread provider terms are UNVERIFIED and queued for review, never shown as permitted."""
import importlib.metadata as md
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.ops import licenses as L  # noqa: E402


def test_register_is_complete():
    assert L.check() == [], L.check()
    req = {L._norm(m.group(1)) for m in re.finditer(
        r"^([A-Za-z0-9_.\-]+)", (ROOT / "requirements.txt").read_text(), re.M)}
    assert req and req <= set(L.PACKAGES), req - set(L.PACKAGES)


def test_a_new_dependency_without_a_row_fails():
    real = L.locked_packages
    L.locked_packages = lambda: real() + ["leftpad"]
    try:
        assert L.check() == ["package leftpad is locked with no licence row"]
    finally:
        L.locked_packages = real


def test_package_rows_agree_with_installed_metadata_where_it_states_an_spdx_expression():
    checked = 0
    for name, row in L.PACKAGES.items():
        try:
            expr = md.metadata(name).get("License-Expression") or ""
        except md.PackageNotFoundError:
            continue
        for ident in re.findall(r"[A-Za-z0-9.\-]+", expr):
            if ident in ("AND", "OR", "WITH"):
                continue
            assert ident in row["licence"], (name, expr, row["licence"])
            checked += 1
    assert checked >= 20, checked


def test_unread_terms_are_unverified_and_queued():
    q = {r["name"] for r in L.review_queue()}
    assert set(L.SERVICES) <= q
    for k, v in L.SERVICES.items():
        assert v["commercial_use"] == L.UNVERIFIED and v["verified"] is False, k
        # F-441: reversibility recorded from the code; maintenance not read, so UNVERIFIED.
        assert v["reversibility"].strip() and v["maintenance"] == L.UNVERIFIED, k
    assert all(v["verified"] for v in {**L.PACKAGES, **L.FONTS_REGISTER}.values())


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
