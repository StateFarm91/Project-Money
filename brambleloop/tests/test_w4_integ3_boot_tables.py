"""W4-INTEG3: REL2's two new tables are created at boot, not only lazily on first use.

`etsy_webhook_refusals` (M1 counters) and `prospecting_brief_cursors` (B3 brief offsets) were
each created on first use with a non-atomic `checkfirst` create. On Postgres two processes
reaching first use together could race the CREATE. `Database.create_all` (run at boot by the
web and worker processes) now registers both, so first use finds them present. Proven on a
local Postgres 16 in research/final_build/w4/evidence_INTEG3/rc_pg_boot_output.txt.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_integ3_boot_tables.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

NEW_TABLES = ("etsy_webhook_refusals", "prospecting_brief_cursors")


def test_a_fresh_process_boot_creates_both_new_tables():
    """In a fresh interpreter (no module imported beforehand, as at boot), create_all alone
    creates both tables."""
    path = os.path.join(tempfile.mkdtemp(prefix="integ3_boot_"), "boot.sqlite")
    code = ("import sys; from sqlalchemy import inspect; from brambleloop.core.db import Database;"
            f"db = Database('sqlite:///{path}'); db.create_all();"
            "print(','.join(sorted(inspect(db.engine).get_table_names())))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    tables = set(out.stdout.strip().splitlines()[-1].split(","))
    assert len(tables) > 100, "the boot schema was not built"
    for t in NEW_TABLES:
        assert t in tables, (t, "not created at boot")


def test_first_use_after_boot_works_and_boot_is_idempotent():
    from types import SimpleNamespace

    from brambleloop.core.db import Database
    from brambleloop.creative import prospecting as P
    from brambleloop.integrations import etsy_webhooks as W

    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='integ3_boot2_')}/b.sqlite")
    db.create_all()
    assert db.create_all() == [], "a second boot changes nothing"
    W._refused(db, W.WebhookRefused("bad_signature", "x", status=401))
    W._refused(db, W.WebhookRefused("bad_signature", "x", status=401))
    assert W.summary(db)["refused"] == {"bad_signature": 2}
    slot = SimpleNamespace(arena=SimpleNamespace(event="halloween", pod="decor"), form="pillow")
    assert P.brief_offset(db, slot) == 0
    assert P.advance_brief_offset(db, slot, 3) == 3


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 2, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
