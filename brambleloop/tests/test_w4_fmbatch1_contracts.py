"""F-482: the CIR contract is pinned; a silent change fails here until the pin and a
declaration in ops/CONTRACT_CHANGES.md move together."""
import dataclasses
import os
import sys
import tempfile
from pathlib import Path

_T = tempfile.mkdtemp(prefix="fmb1ct_")
os.environ.setdefault("BRAMBLELOOP_DATABASE_URL", f"sqlite:///{_T}/c.db")
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_T, "a"))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core import contract_pins as C  # noqa: E402

PINNED_CIR = "8265022276e81c44"
PINNED = {"cir": PINNED_CIR, "listing_payload": "655954b9510590d0",
          "api_routes": "97cc8307a76bcea7"}
CHANGES = ROOT.parent / "ops" / "CONTRACT_CHANGES.md"


def test_the_cir_contract_matches_its_pin():
    got = C.fingerprint()
    assert got == PINNED_CIR, (
        f"the CIR contract changed ({PINNED_CIR} -> {got}). Declare it: add a dated row to "
        f"ops/CONTRACT_CHANGES.md naming the change and how dependants pin or migrate, then "
        f"update PINNED_CIR in this file in the same commit")


def test_the_pin_is_declared():
    assert f"| {PINNED_CIR} |" in CHANGES.read_text(), "the pinned fingerprint has no declaration"


def test_any_field_change_moves_the_fingerprint():
    from brambleloop.cir import model

    base = C.fingerprint()
    orig = model.Gauge

    @dataclasses.dataclass
    class Gauge(orig):          # one extra field on one contract class
        extra_field_for_test: int = 0

    Gauge.__module__ = model.__name__
    model.Gauge = Gauge
    try:
        assert C.fingerprint() != base
    finally:
        model.Gauge = orig
    assert C.fingerprint() == base
    assert {"CIR", "Row", "Op", "Gauge", "Component"} <= set(C.cir_shape())


def test_listing_payload_and_api_routes_match_their_pins():
    got = C.fingerprints()
    changed = {k: (PINNED[k], got[k]) for k in PINNED if PINNED[k] != got[k]}
    assert not changed, (
        f"contract(s) changed: {changed}. Declare each in ops/CONTRACT_CHANGES.md (what changed, "
        f"how dependants pin or migrate) and update PINNED in this file in the same commit")
    text = CHANGES.read_text()
    for k, v in PINNED.items():
        assert f"| {v} |" in text, f"{k} pin {v} has no declaration"


def test_a_new_route_moves_the_api_fingerprint():
    from fastapi import FastAPI

    a = FastAPI()
    a.get("/x")(lambda: {})
    before = C.fingerprints(a)["api_routes"]
    a.post("/y")(lambda: {})
    assert C.fingerprints(a)["api_routes"] != before


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
