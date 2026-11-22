"""BFL-KEY-SHAPE: the readback describes a credential's shape without any character of it.

BFL answered 403 not_authenticated to every render and to the free credits check while the
owner reported a funded account and a freshly updated key. The owner needs to know whether the
value on Railway carries quotes, a header name or whitespace, without anyone reading it.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_bfl_key_shape.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.gateway import credentials as C  # noqa: E402

FAKE = "fixturekeyABCDEF0123456789zzzz"   # TEST FIXTURE, not a credential


def test_shape_fields_are_booleans_and_a_bucket():
    sh = C.key_shape(FAKE)
    assert sh == {"present": True, "length_bucket": "20-60", "surrounding_quotes": False,
                  "starts_with_header_name": False, "internal_whitespace_or_newline": False,
                  "outer_whitespace_trimmed": False, "looks_like_uuid": False}, sh


def test_shapes_detect_common_paste_mistakes():
    assert C.key_shape(f'"{FAKE}"')["surrounding_quotes"]
    assert C.key_shape(f"'{FAKE}'")["surrounding_quotes"]
    assert C.key_shape(f"x-key: {FAKE}")["starts_with_header_name"]
    assert C.key_shape(f"Bearer {FAKE}")["starts_with_header_name"]
    assert C.key_shape(f"{FAKE[:10]}\n{FAKE[10:]}")["internal_whitespace_or_newline"]
    assert C.key_shape(f"  {FAKE}\n")["outer_whitespace_trimmed"]
    assert C.key_shape("12345678-1234-1234-1234-123456789abc")["looks_like_uuid"]
    assert C.key_shape("")["length_bucket"] == "none" and not C.key_shape("")["present"]
    assert C.key_shape("short")["length_bucket"] == "<20"
    assert C.key_shape("k" * 80)["length_bucket"] == ">60"


def test_the_readback_carries_the_shape_beside_credential_health():
    from brambleloop.ops import production_evidence as PE

    shapes = PE._credential_key_shape()
    assert set(shapes) == set(C.PROVIDERS), shapes
    assert "bfl" in shapes and "length_bucket" in shapes["bfl"], shapes


def test_no_character_of_the_key_is_ever_emitted():
    secret = "zq9VERYsecretVALUEthatMUSTnotLEAK77"
    env = {"BRAMBLELOOP_IMAGE_KEY_BFL": f'"{secret}"'}
    shapes = C.key_shapes(env)
    text = json.dumps(shapes)
    assert len(secret) > 4 and shapes, shapes
    for i in range(0, len(secret) - 3):
        assert secret[i:i + 4] not in text, secret[i:i + 4]
    assert shapes["bfl"]["surrounding_quotes"] is True
    for prov, sh in shapes.items():
        assert sh, prov
        for k, v in sh.items():
            assert isinstance(v, bool) or v in ("none", "<20", "20-60", ">60", "unreadable"), \
                (prov, k, v)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
