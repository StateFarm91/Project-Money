"""W4-CLOSE5 batch 3: F-542 Remote Write Readback.

  F-542  "Every Etsy mutation that can affect customers must be followed by authoritative remote
          readback where the API permits. A 2xx response is insufficient proof that the intended
          business field changed."

The mapping said the production publish path performs no remote read-back. It does on the
deployed tree: `runtime/pipeline._publish_and_read_back` reads the draft, its files, images and
alt text back (`etsy_ops.read_back`); `handle_store_activate` reads the listing state after the
activation; `commerce/listing_rollback.execute` reads the restored fields back. These tests pin
that as a rule over every mutation call site in src/, and add the two refusal paths the existing
tests did not assert: an activation Etsy accepted but did not apply, and a rollback whose
read-back still differs.

Stub Etsy only (tests/fake_etsy.py); no network.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close5_rows3.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import ast
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "brambleloop"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

from tests import test_etsy_readback_observe as rb  # noqa: E402  (its fake Etsy and fixtures)

# Every EtsyClient method that writes to Etsy.
MUTATIONS = {"publish", "create_draft", "set_listing_property", "attach_file", "upload_image",
             "update_listing", "delete_listing", "activate"}
READBACK = ("get_listing(", "read_back(", "listing_exists(", "etsy_verify.", "verify(")
# Mutation sites that cannot affect a customer, and why. Drafts are not visible on Etsy; a
# delete is constrained to a listing Etsy itself reports as a draft (delete_listing reads the
# listing first and refuses any other state).
DRAFT_ONLY = {
    "integrations/etsy_exercise.py::create_draft": "creates an unpublished draft in the "
    "owner-authorised exercise; run_exercise reads it back (etsy_probe.run_exercise)",
    "integrations/etsy_probe.py::sweep": "deletes stale DRAFTS only (expect_states=('draft',)); "
    "delete_listing reads the listing first and refuses any other state",
    "integrations/etsy_probe.py::run_exercise#delete_listing": "deletes the exercise's own "
    "draft (expect_states=('draft',)) and then verifies it is gone with listing_exists",
}


def _sites():
    out = []
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(SRC).as_posix()
        if rel == "integrations/etsy.py":
            continue                       # the client itself
        text = p.read_text()
        if not any(f".{m}(" in text for m in MUTATIONS):
            continue
        tree = ast.parse(text)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.get_source_segment(text, fn) or ""
            for node in ast.walk(fn):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in MUTATIONS):
                    continue
                recv = ast.get_source_segment(text, node.func.value) or ""
                if "bus" in recv:          # improve.bus.publish is a lesson, not Etsy
                    continue
                call = ast.get_source_segment(text, node) or ""
                after = body[body.find(call) + len(call):]
                out.append({"site": f"{rel}::{fn.name}", "method": node.func.attr,
                            "line": node.lineno, "call": call, "after": after})
    return out


def test_f542_every_customer_affecting_etsy_mutation_is_followed_by_a_readback():
    sites = _sites()
    assert len(sites) >= 12, sites  # the scan is not vacuous
    unchecked = []
    for s in sites:
        key, key_m = s["site"], f"{s['site']}#{s['method']}"
        if key in DRAFT_ONLY or key_m in DRAFT_ONLY:
            if s["method"] == "delete_listing":
                assert "expect_states=(\"draft\",)" in s["call"] or \
                    "expect_states=('draft',)" in s["call"], s
            continue
        if not any(m in s["after"] for m in READBACK):
            unchecked.append(f"{key}:{s['line']} {s['method']}")
    assert not unchecked, ("Etsy writes with no read-back after them in the same function: "
                           f"{unchecked}. Read the field back, or record why it cannot affect a "
                           "customer in DRAFT_ONLY")
    runtime = {s["site"] for s in sites}
    for must in ("runtime/pipeline.py::_publish_and_read_back",
                 "runtime/pipeline.py::handle_store_activate",
                 "commerce/listing_rollback.py::execute"):
        assert must in runtime, (must, sorted(runtime))


def test_f542_an_activation_etsy_accepted_but_did_not_apply_is_not_recorded_live():
    from sqlalchemy import select

    from brambleloop.core.models import Incident, Listing, Phase
    from brambleloop.integrations.etsy import EtsyClient
    from brambleloop.ops import activation_authority as authority

    db = rb._db()
    os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "1"
    orig = rb._gates_pass()
    real_activate = EtsyClient.activate
    token = "test-owner-credential-32-characters"
    try:
        with rb.FakeEtsy() as fake:
            with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": token}):
                p, lid = rb._published(db, fake)
                content = authority.snapshot(db, p["slug"], p["version"])
                approval = authority.approve(
                    db, authorization=token, slug=p["slug"], version=p["version"],
                    expected_digest=authority.digest(content),
                    reason="owner reviewed this exact test draft")

                def accepted_not_applied(self, listing_id, **kw):
                    out = real_activate(self, listing_id, **kw)        # Etsy answers 2xx
                    fake.listings[str(listing_id)]["state"] = "inactive"  # ...and not live
                    return out

                with patch.object(EtsyClient, "activate", accepted_not_applied), \
                        rb._Patched(fake):
                    job = rb._run(db, "store.activate",
                                  {"slug": p["slug"], "version": p["version"],
                                   "owner_activation_approval_id": approval["approval_id"]},
                                  agent="store_operator", phase=Phase.LIMITED_PRODUCTION)
    finally:
        rb._restore(orig)
        os.environ.pop("BRAMBLELOOP_PUBLISH_AUTHORISED", None)
    assert job.outputs["activated"] is False, job.outputs
    assert job.outputs["state_on_etsy"] == "inactive"
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == p["slug"]))
        assert row.state != "active", "a 2xx was recorded as a live listing"
        assert s.scalar(select(Incident).where(Incident.resolved.is_(False)))
    assert rb._audits(db, "store.activate_incomplete")
    assert not rb._audits(db, "store.activated")


def test_f542_a_rollback_etsy_accepted_but_did_not_apply_is_not_recorded_restored():
    from brambleloop.commerce import listing_lifecycle, listing_rollback

    from tests import test_k8_listing_estate as k8

    class _Ignoring(k8._FakeClient):
        def update_listing(self, lid, fields, *, grant=None):
            self.updates.append(dict(fields))      # Etsy answers 2xx and changes nothing
            return dict(self.listing)

    db = rb._db()
    remote = {"title": "Edited", "tags": ["a", "b"], "price": 4.0}
    plan = k8._plan(remote)
    client = _Ignoring(remote)
    orig = listing_rollback._live_phase
    listing_rollback._live_phase = lambda db: "limited_production"
    try:
        out = listing_rollback.execute(db, client, plan, grant=object())
    finally:
        listing_rollback._live_phase = orig
    assert client.updates == [{"title": "Certified"}]
    assert out["restored"] is False and out["unrestored"] == ["title"], out
    last = listing_lifecycle.trail(db, "77")[-1]
    assert last["result"].startswith("read-back still differs") and "title" in last["result"]


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 3, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
