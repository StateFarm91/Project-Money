"""W3 lane F runtime proof: Talk to Laura on the real app, shadow phase, closed network.

Boots the real FastAPI app on a temp SQLite database, lets the company do real work first
(Laura's executive tick + the COO orchestrator tick, then the shadow worker runs the jobs they
generated for a bounded window), then signs in as the owner through the real /api/cc routes and
holds a conversation: business questions, the D-FB-16 banner delegation (confirmed), a
protected request, voice/live requests (degraded), the presence view, and the private context
(opened with step-up; its CONTENTS are never written to this transcript -- only statuses).

Writes research/final_build/w3/evidence/F_talk_to_laura_transcript.json.
Run: cd brambleloop && PYTHONPATH=src python research/final_build/w3/F_runtime_proof.py
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "research" / "final_build" / "w3" / "evidence" / "F_talk_to_laura_transcript.json"
WORK_SECONDS = float(os.environ.get("F_PROOF_WORK_SECONDS", "90"))

TMP = tempfile.mkdtemp(prefix="w3f_proof_")
os.environ.update({"BRAMBLELOOP_DATABASE_URL": f"sqlite:///{TMP}/proof.db",
                   "BRAMBLELOOP_ARTIFACT_DIR": f"{TMP}/artifacts",
                   "BRAMBLELOOP_EMBEDDED_WORKER": "0", "BRAMBLELOOP_PHASE": "shadow"})
for k in list(os.environ):
    if k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                     "DATABASE_URL", "BRAMBLELOOP_LAURA_PHRASING")):
        os.environ.pop(k)


def _closed(*_a, **_k):
    raise OSError("network closed for the lane F runtime proof")


socket.socket.connect = _closed            # type: ignore[assignment]
socket.create_connection = _closed         # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.laura.private import _testkit as kit  # noqa: E402

PASS = secrets.token_urlsafe(18)
os.environ[opsauth.TOKEN_VAR] = secrets.token_hex(24)
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
kit.set_key(kit.new_key())                 # an ephemeral private key for this run only
DB = main.db
DB.create_all()
Registry(DB).seed_defaults()


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def company_works() -> dict:
    """Real work before the conversation: executive + orchestrator ticks, shadow worker."""
    from brambleloop.autonomy import orchestrator
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.laura.executive import loop
    from brambleloop.runtime.worker import Worker

    out = {"laura_tick": None, "orchestrator_tick": None}
    try:
        t = loop.tick(DB)
        out["laura_tick"] = {k: t.get(k) for k in ("status", "priorities", "delegated",
                                                   "decisions") if k in t} or str(t)[:300]
    except Exception as exc:  # noqa: BLE001
        out["laura_tick"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    try:
        t = orchestrator.tick(DB)
        out["orchestrator_tick"] = {k: (v if not isinstance(v, list) else len(v))
                                    for k, v in t.items()} if isinstance(t, dict) else str(t)
    except Exception as exc:  # noqa: BLE001
        out["orchestrator_tick"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    w = Worker(DB, "proof-worker")
    t0, ran = time.monotonic(), 0
    while time.monotonic() - t0 < WORK_SECONDS:
        if not w.run_once():
            break
        ran += 1
    with DB.session() as s:
        by = {}
        for j in s.query(Job).all():
            by[str(j.status.value if hasattr(j.status, "value") else j.status)] = \
                by.get(str(j.status.value if hasattr(j.status, "value") else j.status), 0) + 1
    out.update({"worker_jobs_run": ran, "work_window_s": round(time.monotonic() - t0, 1),
                "jobs_by_status": by})
    return out


def main_() -> None:
    started = now()
    work = company_works()
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    csrf = r.json()["csrf_token"]

    def post(path, body):
        return c.post(path, json=body, headers={
            "X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))})

    transcript: list[dict] = []

    def ask(q, modes=None):
        body = {"question": q, **({"modes": modes} if modes else {})}
        r = post("/api/cc/laura/ask", body)
        j = r.json()
        transcript.append({"at": now(), "route": "POST /api/cc/laura/ask", "http": r.status_code,
                           "owner": q, "modes_requested": modes,
                           "laura": {k: j.get(k) for k in ("turn_id", "intent", "status",
                                                           "answer", "sources", "unknowns",
                                                           "method", "delivery")},
                           "facts": [{k: f.get(k) for k in ("statement", "source", "basis")}
                                     for f in (j.get("facts") or [])[:8]],
                           "proposals": [{k: p.get(k) for k in ("key", "kind", "department",
                                                                "job_type", "title",
                                                                "requires_step_up", "brief")}
                                         for p in j.get("proposals") or []]})
        return j

    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    access = {"anonymous_laura": anon.get("/api/cc/laura").status_code,
              "anonymous_ask": anon.post("/api/cc/laura/ask",
                                         json={"question": "hi"}).status_code,
              "anonymous_private_view": anon.post("/api/cc/private/view", json={}).status_code}
    overview = c.get("/api/cc/laura").json()
    presence = c.get("/api/cc/laura/presence").json()
    for q in ("Who are you?", "What did your company do overnight?", "What are you working on?",
              "How does your store look?", "What's making money / losing money?",
              "What did your departments discover?", "What did you learn?",
              "What should we launch next?", "What genuinely needs me?"):
        ask(q)
    t = ask("I don't like that banner. Have Design make three more.")
    confirm = {}
    if t.get("proposals"):
        p = t["proposals"][0]
        nc = post("/api/cc/laura/follow-on", {"turn_id": t["turn_id"],
                                              "proposal_key": p["key"]})
        r = post("/api/cc/laura/follow-on", {"turn_id": t["turn_id"], "proposal_key": p["key"],
                                             "confirm": True})
        confirm = {"without_confirm_http": nc.status_code, "without_confirm": nc.json(),
                   "confirmed_http": r.status_code, "confirmed": r.json()}
        if r.status_code == 200 and str(r.json().get("result_ref", "")).startswith("jobs:"):
            from brambleloop.core.models import Job
            with DB.session() as s:
                job = s.get(Job, int(r.json()["result_ref"].split(":")[1]))
                confirm["job"] = {"id": job.id, "job_type": job.job_type, "agent": job.agent,
                                  "status": str(job.status), "brief": job.inputs.get("brief")}
    transcript[-1]["confirmation"] = confirm
    ask("Laura, have Store publish the market basket listing")
    ask("Ask finance to spend 50 dollars on yarn")
    ask("What did your company do overnight?", modes=["live", "voice", "text"])
    voice = post("/api/cc/laura/voice", {"audio_b64": base64.b64encode(b"opus").decode(),
                                         "mime": "audio/ogg"})
    voice_spec = c.get("/api/cc/laura/voice-spec").json()
    # Private context: statuses only -- nothing private is written to this file.
    priv = {"status_before": c.get("/api/cc/private/status").json()}
    priv["open_without_stepup_http"] = None
    r = post("/api/cc/auth/step-up", {"passphrase": PASS})
    priv["stepup_http"] = r.status_code
    r = post("/api/cc/private/open", {})
    priv["open_http"] = r.status_code
    r = post("/api/cc/private/turn", {"text": "neutral proof note " + uuid.uuid4().hex[:8]})
    priv["owner_turn_http"] = r.status_code
    priv["reply_status"] = r.json().get("reply_status")
    r = post("/api/cc/private/view", {})
    priv["view_http"] = r.status_code
    priv["view_counts"] = {"facts": len(r.json().get("facts") or []),
                           "conversation": len(r.json().get("conversation") or []),
                           "laura_turns": sum(1 for t_ in r.json().get("conversation") or []
                                              if t_.get("role") == "laura")}
    priv["close_http"] = post("/api/cc/private/close", {}).status_code
    priv["view_after_close_http"] = post("/api/cc/private/view", {}).status_code
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip()
    doc = {"kind": "W3 lane F runtime proof: Talk to Laura on the real app (TestClient), shadow "
                   "phase, temp SQLite, closed network, no model/provider credentials",
           "started": started, "finished": now(), "commit_base": commit,
           "honesty": ["answers are deterministic retrieval over durable rows; no model call "
                       "(phrasing off: no provider key)",
                       "the company's work before the conversation is real but bounded "
                       f"({WORK_SECONDS:.0f} s worker window), not a soak",
                       "voice/live are GATED: no STT/TTS/avatar provider configured; requests "
                       "degrade to text",
                       "private context: only statuses are recorded here; Laura's private "
                       "reply register is GATED (no reply generated)"],
           "company_work_before_conversation": work, "access_checks": access,
           "overview": {k: overview.get(k) for k in ("speaker", "identity", "needs_you",
                                                     "departments", "phase")},
           "presence": presence, "voice_request": {"http": voice.status_code,
                                                   "code": voice.json().get("code")},
           "voice_spec": {k: voice_spec.get(k) for k in ("spec_id", "spec_sha256",
                                                         "owner_confirmation")},
           "private_context": priv, "conversation": transcript}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes); {len(transcript)} turns")


if __name__ == "__main__":
    try:
        main_()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
