"""WS5 E7 (audit WS5_WS6_etsy_sales_audit): the four small Etsy items.

1. `REQUIRED_SCOPES` includes `transactions_r` (orders are read with it).
2. Etsy's cumulative `views` is reported as views, never as Stats "visits".
3. The public reader accepts `ETSY_KEYSTRING` as well as `ETSY_API_KEY`.
4. `getListingsByShop` is paged past 100.

All credential values here are inert fixture strings.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws5_e7_small_etsy_fixes.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.integrations.etsy import Credentials, EtsyClient  # noqa: E402
from brambleloop.integrations.http import UrllibTransport  # noqa: E402
from brambleloop.intel import etsy_public as EP  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402
from fake_etsy import FakeEtsy  # noqa: E402


def test_transactions_r_is_a_required_scope():
    assert "transactions_r" in etsy_ops.REQUIRED_SCOPES
    assert set(etsy_ops.REQUIRED_SCOPES) >= {"listings_r", "listings_w", "listings_d",
                                             "shops_r", "shops_w"}


def test_the_public_reader_accepts_either_keystring_name():
    alt = {"ETSY_KEYSTRING": "fixturekey", "ETSY_SHARED_SECRET": "fixturesecret"}
    cred = EP.ReadCredential.from_env(alt)
    assert cred is not None and cred.complete and cred.keystring == "fixturekey"
    assert EP.health(alt)["usable"] is True
    both = {**alt, "ETSY_API_KEY": "primarykey"}
    assert EP.ReadCredential.from_env(both).keystring == "primarykey"
    assert EP.credential_shape(both)["etsy_keystring_differs"] is True
    assert EP.ReadCredential.from_env({"ETSY_SHARED_SECRET": "x"}) is None
    assert EP.health({})["usable"] is False


def _client(fake):
    return EtsyClient(UrllibTransport(), phase="shadow", base=fake.base,
                      credentials=Credentials(api_key=fake.keystring,
                                              shared_secret=fake.shared_secret,
                                              access_token="111.live-token",
                                              shop_id=fake.shop_id))


def test_shop_listings_are_read_past_the_first_page():
    with FakeEtsy() as fake:
        for i in range(1, 251):
            fake.listings[str(i)] = {"listing_id": i, "state": "active", "title": f"t{i}"}
        fake.listings["999"] = {"listing_id": 999, "state": "draft", "title": "d"}
        got = _client(fake).get_shop_listings(state="active")
        calls = [r for r in fake.requests if r["operation"] == "getListingsByShop"]
    assert len(got) == 250 and len({g["listing_id"] for g in got}) == 250
    assert len(calls) == 3, len(calls)
    with FakeEtsy() as fake:
        for i in range(1, 6):
            fake.listings[str(i)] = {"listing_id": i, "state": "draft", "title": "d"}
        got = _client(fake).get_shop_listings(state="draft")
        calls = [r for r in fake.requests if r["operation"] == "getListingsByShop"]
    assert len(got) == 5 and len(calls) == 1


def test_paging_is_bounded():
    with FakeEtsy() as fake:
        for i in range(1, 501):
            fake.listings[str(i)] = {"listing_id": i, "state": "active", "title": "t"}
        got = _client(fake).get_shop_listings(state="active", max_pages=2)
    assert len(got) == 200


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
