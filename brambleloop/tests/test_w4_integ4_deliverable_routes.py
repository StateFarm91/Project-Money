"""W4-INTEG4: no public route serves the bytes of a paid customer deliverable.

Security review of 7f6dbe8, B1: a public digest-addressed route served any stored artifact,
the public audit trail published the certified PDFs' digests, and this release keeps those
PDFs durably in Postgres -- so the product being sold became a free download. The fix closes
that route; this test closes the class. It enumerates EVERY GET route the application serves
(routers included, via `security.iter_api_routes`, never a hand list), fills every path
parameter with each value an attacker could know (the PDF's digest, the slug, slug@version,
the version and "1"), adds every public mutating route, and requests each one WITHOUT any
credential (no owner session, no operator token presented although one is configured).
No response may carry the paid PDF's bytes: not raw, not base64, not as a PDF body.

There is no customer delivery-token route in this build (fulfilment is Etsy's digital-file
delivery; `commerce.deliverables.delivery_links` are internal references), so "without a
token or owner auth" is "without any credential" here. The owner's own route
(`/api/cc/store/pdf/{slug}`) is in the sweep and must refuse an anonymous caller.

The sweep runs twice: with the PDF on disk, and after a simulated redeploy (disk gone, bytes
only in `durable_artifacts`), because the Postgres fallback is what made the leak permanent.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_integ4_deliverable_routes.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import base64
import os
import re
import socket
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="w4_integ4_deliv_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'd.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                      "BRAMBLELOOP_IMAGE_KEY")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the deliverable-route harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402
from brambleloop.commerce import deliverables  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.models import AuditLog, DurableArtifact  # noqa: E402

TOKEN = "d" * 40
SLUG, VERSION = "paid-cable-wrap", "1.0.0"
MARKER = ("PAID-PATTERN-BYTES-" + uuid.uuid4().hex).encode()
PDF = b"%PDF-1.7\n" + MARKER + b"\n" + b"row 1: ch 40, turn. " * 200 + b"\n%%EOF\n"
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db


def _seed() -> str:
    stored = ArtifactStore().put("pdf/US.pdf", PDF, "application/pdf", db=DB,
                                 keep=deliverables.keep_why(SLUG, VERSION, "pdf:US"))
    assert stored.durable, "the PDF is kept in Postgres, as this release does"
    with DB.session() as s:
        # The rows an attacker reads the digest from (B1's path), and every other place a
        # digest appears in this release's audit vocabulary.
        s.add(AuditLog(actor="test", action="assets.built", artifact=f"{SLUG}@{VERSION}",
                       detail={"pdf": {"sha256": stored.sha256},
                               "pdfs": {"US": {"sha256": stored.sha256}}}))
        s.add(AuditLog(actor="test", action="deliverables.secured",
                       artifact=f"{SLUG}@{VERSION}", detail={"sha256": stored.sha256}))
    return stored.sha256


SHA = _seed()
B64 = base64.b64encode(PDF)


def _leak(content: bytes) -> str | None:
    if MARKER in content:
        return "raw bytes"
    if B64[:200] in content or base64.urlsafe_b64encode(PDF)[:200] in content:
        return "base64"
    if content.lstrip().startswith(b"%PDF"):
        return "a PDF body"
    return None


def _urls() -> list[tuple[str, str]]:
    values = [SHA, SLUG, f"{SLUG}@{VERSION}", VERSION, "1"]
    out = set()
    for path, methods, _ in security.iter_api_routes(main.app):
        if "GET" not in methods:
            continue
        if "{" not in path:
            out.add(("GET", path))
            continue
        for v in values:
            out.add(("GET", re.sub(r"\{[^}]+\}", v, path)))
    for (method, path) in security.PUBLIC_MUTATING_ROUTES:
        for v in values:
            out.add((method, re.sub(r"\{[^}]+\}", v, path)))
    return sorted(out)


def _sweep(label: str) -> dict:
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    os.environ[opsauth.TOKEN_VAR] = TOKEN   # configured, never presented
    leaks, served = {}, 0
    try:
        for method, url in _urls():
            try:
                r = c.request(method, url, json={} if method != "GET" else None)
            except Exception:  # noqa: BLE001 - a route that raises serves nothing
                continue
            served += 1
            why = _leak(r.content)
            if why:
                leaks[f"{method} {url}"] = (r.status_code, why)
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    assert not leaks, f"{label}: public routes serving the paid PDF: {leaks}"
    return {"requests": served}


def test_the_sweep_covers_the_surface_and_the_known_routes():
    urls = _urls()
    paths = {u for _, u in urls}
    assert len(urls) > 250, len(urls)   # 296 at 263e94d: 160+ GET routes, 5 fills each
    for must in (f"/api/model-tournament/image/{SHA}", f"/api/cc/store/pdf/{SLUG}",
                 "/api/audit", "/api/etsy/webhook"):
        assert must in paths, must


def test_no_public_route_serves_the_paid_pdf_with_the_file_on_disk():
    out = _sweep("disk")
    assert out["requests"] > 250, out


def test_no_public_route_serves_the_paid_pdf_after_a_redeploy():
    path = ArtifactStore().root / SHA[:2] / SHA
    if path.exists():
        path.unlink()
    with DB.session() as s:
        assert s.get(DurableArtifact, SHA) is not None, "the bytes live on in Postgres"
    _sweep("postgres-only")
    # The store itself still recovers it for the delivery path (owner/Etsy fulfilment): the
    # bytes are durable, just not public.
    assert ArtifactStore().get(SHA, db=DB) == PDF


def test_the_sweep_would_catch_a_leak():
    """Self-test: the detector flags exactly what B1 served."""
    assert _leak(PDF) == "raw bytes"
    assert _leak(b"%PDF-1.4 another paid file") == "a PDF body"
    assert _leak(b'{"x": "' + B64 + b'"}') == "base64"
    assert _leak(b"<html>" + MARKER + b"</html>") == "raw bytes"
    assert _leak(b'{"ok": true}') is None


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:2000])
            traceback.print_exc(limit=4)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
