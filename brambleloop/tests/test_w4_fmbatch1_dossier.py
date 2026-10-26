"""F-671: the product dossier spans every table that holds the product (by slug or id),
lists the ones that do not, and is operator-only."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1do_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/d.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.db import Base  # noqa: E402
from brambleloop.core.models import (Listing, PatternVersion, PhysicalTest, Product,  # noqa: E402
                                     SupportCase)
from brambleloop.products import dossier as D  # noqa: E402

main.db.create_all()
Registry(main.db).seed_defaults()


def _seed():
    with main.db.session() as s:
        p = Product(slug="hex-coaster", title="Hex", status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={}, certified=True))
        s.add(Listing(product_slug="hex-coaster", version="1.0.0", title="t", description="d"))
        s.add(PhysicalTest(product_slug="hex-coaster", version="1.0.0", tester_ref="t1"))
        s.add(SupportCase(customer_ref="c", product_slug="hex-coaster", question="row 3?"))
        s.add(Listing(product_slug="other", version="1", title="o", description="d"))


def test_dossier_spans_every_table_that_holds_the_product():
    _seed()
    d = D.dossier(main.db, "hex-coaster")
    assert d["known_product"] and d["product"]["slug"] == "hex-coaster"
    for t in ("pattern_versions", "listings", "physical_tests", "support_cases"):
        assert t in d["sections"], t
    assert d["sections"]["listings"]["count"] == 1                    # not "other"
    keyed = {n for n, t in Base.metadata.tables.items()
             if "product_slug" in t.c or "product_id" in t.c}
    assert keyed == set(d["sections"]) | set(d["tables_without_this_product"])


def test_unknown_product_is_said_and_route_is_operator_only():
    d = D.dossier(main.db, "zz-nothing")
    assert d["known_product"] is False and d["sections"] == {}
    c = TestClient(main.app)
    token = "d" * 40
    os.environ[opsauth.TOKEN_VAR] = token
    try:
        assert c.get("/api/product/hex-coaster/dossier").status_code == 401
        r = c.get("/api/product/hex-coaster/dossier",
                  headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and "listings" in r.json()["sections"]
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
