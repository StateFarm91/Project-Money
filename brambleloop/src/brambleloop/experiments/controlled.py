"""Owner-only controlled visual experiments in production (W-VISNEXT).

This is the existing image pipeline run on frozen inputs. It is not a parallel system:

* **Definitions are frozen files.** Each lives in
  `experiments/definitions/<id>/definition.json` and holds the id, purpose, product, CIR
  hash, ordered references with their sha256, the frozen prompt (file + sha256), model,
  size, retry limit, both caps and the owner authorization it needs. Reference bytes and the
  prompt are committed next to it; the canonical Laura frames are named and verified from the
  canonical pack. Adding an experiment means committing a definition and getting an owner
  authorization. No code changes.
* **Authorization.** `authorize` records the owner's authorization. It is reached only
  through the Command Center, behind the owner session and step-up, and binds the
  definition id, its sha256 and the caps. The caps can never exceed the definition's.
* **Run.** `submit` enqueues ONE durable job (`visual.controlled_experiment`, agent
  `publishing`) with idempotency key `exp:{id}:{definition_sha}:{n}`. The job, `run_job`,
  works in this order:
  1. It verifies every reference and the prompt by sha256 BEFORE any spend, and refuses on
     drift.
  2. It checks the generation cap, then calls `gateway.images.generate`. That call reserves
     against the agent, monthly and provider ceilings, and bills.
  3. It keeps the original bytes durably (`ArtifactStore`, durable_artifacts), together with
     the receipt, the fingerprints and the actual cost.
  4. It runs the blind vision adapters (`visual.vision_judges`) within the vision cap, and the
     fidelity verifier's lifestyle path.
  At most `max_retries` retries are made, and only on a transient/provider error.
* **Never publication.** The output is labelled EXPERIMENT. Its image sha256 is refused by
  the publication guards (`visual.experiment.refuse_if_experiment_image`). For an
  uncertified product, the product is marked for `refuse_if_experiment` too.
* **Keys.** The provider key is read from the process environment by
  `gateway.images.key_for` at call time. It never enters job inputs or outputs, audit rows,
  run rows or the API: `_scrub` removes any environment secret value from everything stored.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow
from ..core.resilience import PermanentError, TransientError

JOB_TYPE = "visual.controlled_experiment"
AGENT = "publishing"
DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"
ACTION_AUTHORIZED = "experiment.authorized"
ACTION_RUN = "experiment.controlled_run"
ACTIVE, TERMINAL = ("queued", "running"), ("completed", "refused", "failed")


class ControlledRefused(PermanentError):
    """The experiment may not do this; nothing was spent."""


# ---- tables ---------------------------------------------------------------------------------

class ExperimentAuthorization(Base):
    """The owner's authorization of one exact definition, with its caps."""

    __tablename__ = "experiment_authorizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auth_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    definition_id: Mapped[str] = mapped_column(String(80), index=True)
    definition_sha256: Mapped[str] = mapped_column(String(64))
    generation_cap_cad: Mapped[float] = mapped_column(Float)
    vision_cap_cad: Mapped[float] = mapped_column(Float)
    authorized_by: Mapped[str] = mapped_column(String(120))
    step_up: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ControlledRun(Base):
    """One run of one authorized definition: inputs verified, spend, bytes, verdicts."""

    __tablename__ = "controlled_experiment_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    definition_id: Mapped[str] = mapped_column(String(80), index=True)
    definition_sha256: Mapped[str] = mapped_column(String(64))
    auth_id: Mapped[str] = mapped_column(String(40), index=True)
    n: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    why: Mapped[str] = mapped_column(Text, default="")
    submitted_by: Mapped[str] = mapped_column(String(120), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    generation_spent_cad: Mapped[float] = mapped_column(Float, default=0.0)
    vision_spent_cad: Mapped[float] = mapped_column(Float, default=0.0)
    image_sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    references: Mapped[list] = mapped_column(JSON, default=list)
    receipt: Mapped[dict] = mapped_column(JSON, default=dict)
    verification: Mapped[dict] = mapped_column(JSON, default=dict)
    attempt_log: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_TABLES = (ExperimentAuthorization.__table__, ControlledRun.__table__)
_ensured: set[int] = set()
_lock = threading.Lock()


def ensure_tables(db) -> None:
    key = id(db.engine)
    if key in _ensured:
        return
    with _lock:
        if key not in _ensured:
            for t in _TABLES:
                t.create(db.engine, checkfirst=True)
            _ensured.add(key)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- secrets never stored -------------------------------------------------------------------

def _secret_values(env=None) -> list[str]:
    e = env if env is not None else os.environ
    out = []
    for k, v in e.items():
        if not v or len(str(v)) < 8:
            continue
        ku = k.upper()
        if any(w in ku for w in ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASSPHRASE")):
            out.append(str(v))
    return out


def _scrub(obj, secrets: list[str]):
    """Any environment secret value removed from anything about to be stored or returned."""
    if isinstance(obj, dict):
        return {k: _scrub(v, secrets) for k, v in obj.items()
                if not any(w in str(k).lower() for w in ("api_key", "authorization",
                                                         "x-key", "headers"))}
    if isinstance(obj, (list, tuple)):
        return [_scrub(v, secrets) for v in obj]
    if isinstance(obj, str):
        for s in secrets:
            if s and s in obj:
                obj = obj.replace(s, "[redacted]")
        return obj
    return obj


# ---- definitions ----------------------------------------------------------------------------

def definition_ids() -> list[str]:
    return sorted(p.name for p in DEFINITIONS_DIR.iterdir()
                  if (p / "definition.json").is_file())


def load(definition_id: str) -> dict:
    d = DEFINITIONS_DIR / str(definition_id)
    f = d / "definition.json"
    if "/" in str(definition_id) or ".." in str(definition_id) or not f.is_file():
        raise ControlledRefused(f"no experiment definition {definition_id!r}")
    raw = f.read_bytes()
    defn = json.loads(raw)
    if defn.get("id") != definition_id:
        raise ControlledRefused("the definition's id is not its folder name")
    return {"definition": defn, "sha256": hashlib.sha256(raw).hexdigest(), "dir": d}


def verify(loaded: dict, db=None) -> dict:
    """Every reference and the prompt, by sha256, in order. Nothing is spent here."""
    from ..visual import canonical

    defn, d = loaded["definition"], loaded["dir"]
    if defn.get("kind") == "pipeline":
        return verify_pipeline(loaded, db)
    problems, refs = [], []
    for want in sorted(defn.get("references") or [], key=lambda r: r["position"]):
        if want.get("canonical_frame"):
            path = canonical.reference_file(want["canonical_frame"])
        else:
            rel = str(want.get("file") or "")
            path = str(d / rel) if rel and ".." not in rel else ""
        got = hashlib.sha256(Path(path).read_bytes()).hexdigest() if path and \
            Path(path).is_file() else ""
        if got != want["sha256"]:
            problems.append(f"reference {want['position']} ({want['role']}): fingerprint "
                            f"{got[:12] or 'missing'} is not the frozen {want['sha256'][:12]}")
        refs.append({"position": want["position"], "role": want["role"],
                     "sha256": want["sha256"], "path": path})
    positions = [r["position"] for r in refs]
    if positions != list(range(1, len(refs) + 1)):
        problems.append(f"reference positions are not 1..n in order: {positions}")
    pf = d / str((defn.get("prompt") or {}).get("file") or "prompt.txt")
    text = pf.read_text() if pf.is_file() else ""
    if hashlib.sha256(text.encode()).hexdigest() != (defn.get("prompt") or {}).get("sha256"):
        problems.append("prompt: the text is not the frozen prompt (sha256 drift)")
    for k in ("generation_cap_cad", "vision_cap_cad", "model", "size"):
        if not defn.get(k):
            problems.append(f"definition is missing {k}")
    return {"ok": not problems, "problems": problems, "references": refs, "prompt": text}


def verify_pipeline(loaded: dict, db=None) -> dict:
    """A pipeline definition (W-VISNEXT2): the inputs the orchestrator will generate from are
    frozen as fingerprints and checked before any spend. The canonical Laura bytes, the prompt
    builder and every prompt section's sha256 are checked always. With a database, the product
    must be certified at exactly the frozen content hash, and its pattern references must
    re-render to exactly the frozen fingerprints."""
    from ..creative import flux_prompt as FP
    from ..visual import canonical

    defn = loaded["definition"]
    pipe = defn.get("pipeline") or {}
    problems = []
    for want in pipe.get("canonical_laura") or []:
        frames = [f for f, h in canonical.CURRENT_REFERENCE_HASHES.items() if h == want]
        path = canonical.reference_file(frames[0]) if frames else ""
        got = hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else ""
        if got != want:
            problems.append(f"canonical Laura {want[:12]}: not the frozen bytes")
    if len(pipe.get("canonical_laura") or []) != 3:
        problems.append("the three canonical Laura fingerprints are not all frozen")
    if pipe.get("prompt_builder") != FP.BUILDER_VERSION:
        problems.append(f"prompt builder {FP.BUILDER_VERSION} is not the frozen "
                        f"{pipe.get('prompt_builder')}")
    live = {p.ref: p.sha256 for p in (FP.REFERENCES, FP.IDENTITY, FP.REFERENCE_CLOTHING,
                                       FP.PRODUCT, FP.NEGATIVES, FP.SCENE, FP.REALISM,
                                       FP.DISCLOSURE, FP.IDENTITY_ANCHOR,
                                       FP.PROPORTION_CORRECTION)}
    for ref, sha in (pipe.get("prompt_sections") or {}).items():
        if live.get(ref) != sha:
            problems.append(f"prompt section {ref}: drift from the frozen sha256")
    refs = []
    if db is not None:
        from ..creative import pattern_refs as P
        from ..publish.release_gates import _release

        product = defn.get("product") or {}
        try:
            cir, release_hash = _release(db, product.get("slug", ""), product.get("version", ""))
        except Exception as exc:  # noqa: BLE001 - unreadable is refused
            cir, release_hash = None, None
            problems.append(f"certified release unreadable ({type(exc).__name__})")
        if cir is None:
            problems.append(f"{product.get('slug')}@{product.get('version')} has no certified "
                            f"release here")
        elif release_hash != product.get("cir_hash"):
            problems.append(f"the certified release {str(release_hash)[:12]} is not the frozen "
                            f"{str(product.get('cir_hash'))[:12]}")
        else:
            import tempfile

            with tempfile.TemporaryDirectory(prefix="experiment-") as tmp:
                m = P.build(cir, release_hash=release_hash, out_dir=tmp)
            got = [(r["role"], r["sha256"]) for r in m["references"]]
            want = [(r["role"], r["sha256"]) for r in pipe.get("pattern_references") or []]
            if got != want:
                problems.append("pattern references do not re-render to the frozen "
                                "fingerprints")
            refs = [{"position": i + 1, "role": r, "sha256": h} for i, (r, h) in enumerate(got)]
    for k in ("generation_cap_cad", "vision_cap_cad", "model", "size"):
        if not defn.get(k):
            problems.append(f"definition is missing {k}")
    return {"ok": not problems, "problems": problems, "references": refs, "prompt": "",
            "pipeline": True, "release_checked": db is not None}


def cap_group(definition_id: str) -> set[str]:
    """The definitions whose spend counts against one shared cap (`shares_cap_with`, either
    direction). A shared cap is counted once across the group, never once per member."""
    group = {definition_id}
    for did in definition_ids():
        try:
            other = load(did)["definition"]
        except ControlledRefused:
            continue
        shares = set(other.get("shares_cap_with") or [])
        if did == definition_id:
            group |= shares
        elif definition_id in shares:
            group.add(did)
    return group


def _group_spent(db, definition_id: str) -> tuple[float, float]:
    from sqlalchemy import func, select

    ensure_tables(db)
    with db.session() as s:
        g, v = s.execute(select(func.coalesce(func.sum(ControlledRun.generation_spent_cad), 0.0),
                                func.coalesce(func.sum(ControlledRun.vision_spent_cad), 0.0))
                         .where(ControlledRun.definition_id.in_(cap_group(definition_id)))).one()
    return float(g or 0.0), float(v or 0.0)


# ---- authorization --------------------------------------------------------------------------

def authorize(db, definition_id: str, *, by: str, stepped_up: bool,
              generation_cap_cad: float | None = None,
              vision_cap_cad: float | None = None) -> dict:
    """The owner's authorization, bound to the definition's sha256 and caps. Step-up only."""
    from ..core.models import AuditLog

    if not stepped_up:
        raise ControlledRefused("authorizing an experiment needs the owner's step-up")
    if not str(by or "").strip():
        raise ControlledRefused("an authorization names the owner who gave it")
    loaded = load(definition_id)
    v = verify(loaded)
    if not v["ok"]:
        raise ControlledRefused("the definition's inputs drifted; nothing is authorized: "
                                + "; ".join(v["problems"]))
    defn = loaded["definition"]
    gen = float(defn["generation_cap_cad"] if generation_cap_cad is None else generation_cap_cad)
    vis = float(defn["vision_cap_cad"] if vision_cap_cad is None else vision_cap_cad)
    if not 0 < gen <= float(defn["generation_cap_cad"]):
        raise ControlledRefused(f"generation cap CA${gen} is outside 0..CA$"
                                f"{defn['generation_cap_cad']} (the definition's cap)")
    if not 0 <= vis <= float(defn["vision_cap_cad"]):
        raise ControlledRefused(f"vision cap CA${vis} is outside 0..CA$"
                                f"{defn['vision_cap_cad']} (the definition's cap)")
    ensure_tables(db)
    auth_id = "auth-" + hashlib.sha256(f"{definition_id}|{loaded['sha256']}|{gen}|{vis}|"
                                       f"{_now().isoformat()}".encode()).hexdigest()[:16]
    from sqlalchemy import select

    with db.session() as s:
        for old in s.scalars(select(ExperimentAuthorization).where(
                ExperimentAuthorization.definition_id == definition_id,
                ExperimentAuthorization.revoked.is_(False))):
            old.revoked = True               # one live authorization per definition
        s.add(ExperimentAuthorization(auth_id=auth_id, definition_id=definition_id,
                                      definition_sha256=loaded["sha256"],
                                      generation_cap_cad=gen, vision_cap_cad=vis,
                                      authorized_by=str(by)[:120], step_up=True))
        s.add(AuditLog(actor=str(by)[:64], action=ACTION_AUTHORIZED, artifact=definition_id,
                       detail={"auth_id": auth_id, "definition_sha256": loaded["sha256"],
                               "generation_cap_cad": gen, "vision_cap_cad": vis,
                               "step_up": True}))
    return {"auth_id": auth_id, "definition_id": definition_id,
            "definition_sha256": loaded["sha256"], "generation_cap_cad": gen,
            "vision_cap_cad": vis, "authorized_by": str(by)[:120]}


def authorization(db, definition_id: str, definition_sha: str | None = None) -> dict | None:
    from sqlalchemy import select

    ensure_tables(db)
    with db.session() as s:
        q = select(ExperimentAuthorization).where(
            ExperimentAuthorization.definition_id == definition_id,
            ExperimentAuthorization.revoked.is_(False))
        if definition_sha:
            q = q.where(ExperimentAuthorization.definition_sha256 == definition_sha)
        r = s.scalar(q.order_by(ExperimentAuthorization.id.desc()))
        if r is None:
            return None
        return {"auth_id": r.auth_id, "definition_id": r.definition_id,
                "definition_sha256": r.definition_sha256,
                "generation_cap_cad": r.generation_cap_cad, "vision_cap_cad": r.vision_cap_cad,
                "authorized_by": r.authorized_by, "step_up": r.step_up,
                "created_at": r.created_at.isoformat() if r.created_at else None}


def _spent(db, auth_id: str) -> tuple[float, float]:
    from sqlalchemy import func, select

    with db.session() as s:
        g, v = s.execute(select(func.coalesce(func.sum(ControlledRun.generation_spent_cad), 0.0),
                                func.coalesce(func.sum(ControlledRun.vision_spent_cad), 0.0))
                         .where(ControlledRun.auth_id == auth_id)).one()
    return float(g or 0.0), float(v or 0.0)


# ---- submit ---------------------------------------------------------------------------------

def submit(db, definition_id: str, *, by: str, enqueue, stepped_up: bool) -> dict:
    """Enqueue ONE run. A duplicate submit while a run is queued or running returns it."""
    from sqlalchemy import func, select

    from ..core.models import AuditLog
    from ..visual import experiment as XP

    if not stepped_up:
        raise ControlledRefused("running an experiment needs the owner's step-up")
    loaded = load(definition_id)
    auth = authorization(db, definition_id, loaded["sha256"])
    if auth is None:
        raise ControlledRefused("no owner authorization for this exact definition (its sha256 "
                                "changed, or it was never authorized); authorize it first")
    defn = loaded["definition"]
    ensure_tables(db)
    with db.session() as s:
        live = s.scalar(select(ControlledRun).where(
            ControlledRun.definition_sha256 == loaded["sha256"],
            ControlledRun.status.in_(ACTIVE)).order_by(ControlledRun.id.desc()))
        if live is not None:
            return {"duplicate": True, "run_id": live.id, "job_id": live.job_id, "n": live.n,
                    "idempotency_key": live.idempotency_key, "status": live.status}
        done = int(s.scalar(select(func.count()).select_from(ControlledRun).where(
            ControlledRun.definition_sha256 == loaded["sha256"])) or 0)
    n = done + 1
    key = f"exp:{definition_id}:{loaded['sha256']}:{n}"
    with db.session() as s:
        run = ControlledRun(definition_id=definition_id, definition_sha256=loaded["sha256"],
                            auth_id=auth["auth_id"], n=n, idempotency_key=key,
                            submitted_by=str(by)[:120])
        s.add(run)
        s.flush()
        run_id = run.id
        if not (defn.get("product") or {}).get("certified", False):
            # An uncertified product's experiment marks the product itself: every
            # publication path refuses it (`experiment.refuse_if_experiment`).
            p = defn["product"]
            s.add(AuditLog(actor="experiment", action=XP.ACTION_CONTROLLED,
                           artifact=f"{p['slug']}@{p['version']}",
                           detail={"label": XP.LABEL, "definition_id": definition_id,
                                   "release": p.get("cir_hash"), "controlled": True}))
    job = enqueue({"definition_id": definition_id, "definition_sha256": loaded["sha256"],
                   "run_id": run_id, "auth_id": auth["auth_id"]}, key)
    job_id = getattr(job, "id", job if isinstance(job, int) else None)
    with db.session() as s:
        s.get(ControlledRun, run_id).job_id = job_id
    return {"duplicate": False, "run_id": run_id, "job_id": job_id, "n": n,
            "idempotency_key": key, "status": "queued"}


# ---- the job --------------------------------------------------------------------------------

class CappedVision:
    """The vision transport inside the experiment's vision cap (plus every gateway ceiling).

    Wraps `fidelity.GatewayVisionJudge`: gated on `image_vision` and reserved through the
    gateway. Before each call the padded estimate must fit under the remaining cap; the
    actual cost is added after. Over the cap nothing is sent and the reading is UNKNOWN."""

    name = "image_vision(capped)"

    def __init__(self, inner, *, cap_cad: float, spent_cad: float = 0.0):
        self.inner, self.cap, self.spent = inner, float(cap_cad), float(spent_cad)
        self.calls: list[dict] = []
        self.provider = getattr(inner, "provider", None)

    def read(self, prompt, images, *, system=None, max_tokens=300):
        from ..gateway import anthropic as gw

        model = getattr(self.provider, "model", None) or gw.DEFAULT_MODEL
        try:
            est = gw.estimate_cad(model, input_tokens=len(prompt) // 4 +
                                  gw.IMAGE_TOKENS_ESTIMATE * len(images),
                                  output_tokens=max_tokens)
        except Exception:  # noqa: BLE001 - an unpriceable call is not made
            return {"answered": False, "why": "the vision call cannot be priced; not sent"}
        if self.spent + est > self.cap + 1e-9:
            self.calls.append({"sent": False, "estimate_cad": est})
            return {"answered": False, "why": f"experiment vision cap CA${self.cap:.2f} "
                                              f"reached (spent CA${self.spent:.4f}); not sent"}
        kw = {"max_tokens": max_tokens}
        if system:
            kw["system"] = system
        got = self.inner.read(prompt, images, **kw)
        cost = float(got.get("cost_cad") or (est if got.get("answered") else 0.0))
        self.spent += cost
        self.calls.append({"sent": True, "estimate_cad": est, "cost_cad": cost,
                           "answered": bool(got.get("answered"))})
        return got


def _price_cad(model: str, size: str) -> float:
    from ..gateway import images

    if model == "flux-3-image":
        return round(images.BFL3_TIER_USD[images.bfl3_tier(size)] * images.USD_TO_CAD, 6)
    return float(images.BY_KEY[model].cad_per_image)


def _update(db, run_id: int, **fields) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    with db.session() as s:
        r = s.get(ControlledRun, run_id)
        for k, v in fields.items():
            setattr(r, k, v)
            if isinstance(v, (dict, list)):
                flag_modified(r, k)
        r.updated_at = _now()


def run_job(db, inputs: dict, *, job_id: int | None = None, env=None, vision=None,
            cir_loader=None, enqueue=None) -> dict:
    """One controlled run. Verifies, then spends within both caps, then judges."""
    from ..core import workspace
    from ..core.artifacts import ArtifactStore
    from ..gateway import images
    from ..visual import experiment as XP

    ensure_tables(db)
    secrets = _secret_values(env)
    run_id = int(inputs.get("run_id") or 0)
    with db.session() as s:
        run = s.get(ControlledRun, run_id)
        if run is None:
            return {"ran": False, "why": "no such run"}
        if run.status != "queued":
            return {"ran": False, "why": f"run is {run.status}", "run_id": run_id}
        auth_id, def_id = run.auth_id, run.definition_id

    def refuse(why: str) -> dict:
        _update(db, run_id, status="refused", why=_scrub(why, secrets)[:2000])
        return {"ran": False, "refused": True, "why": _scrub(why, secrets), "run_id": run_id}

    try:
        loaded = load(def_id)
    except ControlledRefused as exc:
        return refuse(str(exc))
    if loaded["sha256"] != inputs.get("definition_sha256"):
        return refuse("the definition changed after it was submitted; nothing was spent")
    auth = authorization(db, def_id, loaded["sha256"])
    if auth is None or auth["auth_id"] != auth_id:
        return refuse("the authorization was revoked or replaced; nothing was spent")
    v = verify(loaded, db)
    if not v["ok"]:
        return refuse("input drift, refused before any spend: " + "; ".join(v["problems"]))
    defn = loaded["definition"]
    if defn.get("kind") == "pipeline":
        return _start_pipeline(db, run_id, defn, v, enqueue=enqueue, job_id=job_id)
    refs = [r["path"] for r in v["references"]]
    model, size = defn["model"], defn["size"]
    price = _price_cad(model, size)
    max_attempts = 1 + int(defn.get("max_retries") or 0)
    _update(db, run_id, status="running", job_id=job_id,
            references=[{k: r[k] for k in ("position", "role", "sha256")}
                        for r in v["references"]])
    log: list[dict] = []
    result = None
    e = env if env is not None else os.environ
    with workspace.work_dir(None, prefix="experiment-") as work:
        for attempt in range(1, max_attempts + 1):
            gen_spent, _ = _group_spent(db, def_id)
            if gen_spent + price > float(auth["generation_cap_cad"]) + 1e-9:
                log.append({"attempt": attempt, "sent": False,
                            "why": f"generation cap CA${auth['generation_cap_cad']:.2f} would "
                                   f"be exceeded (spent CA${gen_spent:.4f}, next CA${price})"})
                break
            # Reserved against the cap before the call; a failed call stays billed at its
            # reservation (never zero) unless the provider reports otherwise.
            _update(db, run_id, generation_spent_cad=_run_spent(db, run_id) + price,
                    attempts=attempt)
            try:
                result = images.generate(v["prompt"], reference_urls=refs, env=e, size=size,
                                         provider_key=model, work_dir=str(work), db=db,
                                         agent=AGENT, purpose=f"experiment.{def_id}",
                                         job_id=job_id)
                actual = float(result.get("cad") if result.get("cad") is not None else price)
                _update(db, run_id, generation_spent_cad=_run_spent(db, run_id) - price + actual)
                log.append({"attempt": attempt, "sent": True, "cost_cad": actual})
                break
            except TransientError as exc:
                log.append({"attempt": attempt, "sent": True, "transient": True,
                            "error": _scrub(f"{type(exc).__name__}: {str(exc)[:300]}", secrets)})
                result = None
                continue
            except Exception as exc:  # noqa: BLE001 - not retried: only transient errors are
                log.append({"attempt": attempt, "sent": True, "transient": False,
                            "error": _scrub(f"{type(exc).__name__}: {str(exc)[:300]}", secrets)})
                if isinstance(exc, (images.ImagesRefused,)) or "Budget" in type(exc).__name__:
                    # refused before sending: nothing was spent on this attempt
                    _update(db, run_id, generation_spent_cad=max(
                        0.0, _run_spent(db, run_id) - price))
                    log[-1]["sent"] = False
                result = None
                break
        if result is None:
            _update(db, run_id, status="failed", attempt_log=log,
                    why=_scrub("no image: " + "; ".join(str(x.get("error") or x.get("why"))
                                                       for x in log), secrets)[:2000])
            return {"ran": True, "image": False, "run_id": run_id, "attempts": log}
        data = Path(result["path"]).read_bytes()
    stored = ArtifactStore().put(f"experiment/{def_id}/{run_id}", data,
                                 "image/png", db=db, keep=f"{XP.LABEL}; {def_id}")
    receipt = _scrub({k: v_ for k, v_ in result.items() if k not in ("path", "image_ref")},
                     secrets)
    _update(db, run_id, image_sha256=stored.sha256, receipt=receipt, attempt_log=log)
    verification = _verify_image(db, data, defn, auth, run_id, vision=vision,
                                 cir_loader=cir_loader)
    _update(db, run_id, status="completed", verification=_scrub(verification, secrets),
            vision_spent_cad=float(verification.get("vision_spent_cad") or 0.0))
    return {"ran": True, "image": True, "run_id": run_id, "image_sha256": stored.sha256,
            "status": "completed", "verification": verification.get("summary")}


def _run_spent(db, run_id: int) -> float:
    with db.session() as s:
        return float(s.get(ControlledRun, run_id).generation_spent_cad or 0.0)


def _verify_image(db, data: bytes, defn: dict, auth: dict, run_id: int, *, vision=None,
                  cir_loader=None) -> dict:
    """The independent checks: blind vision adapters within the vision cap, then fidelity."""
    from ..visual import fidelity as F
    from ..visual import vision_judges as VJ

    _, vis_spent = _group_spent(db, auth["definition_id"])
    inner = vision if vision is not None else F.GatewayVisionJudge(db)
    judge = CappedVision(inner, cap_cad=float(auth["vision_cap_cad"]), spent_cad=vis_spent)
    product = defn.get("product") or {}
    sha = hashlib.sha256(data).hexdigest()
    outfit = {"outfit_id": (defn.get("outfit") or {}).get("id"),
              **(defn.get("outfit") or {})}
    cand = {"sha256": sha, "data": data, "slug": product.get("slug"),
            "version": product.get("version"), "laura_present": True,
            "outfit_id": outfit.get("outfit_id"), "listing": product.get("slug"),
            "references": [{"sha256": r["sha256"],
                            "kind": "laura_canonical" if r["role"].startswith("laura_")
                            else "pattern_derived"} for r in defn.get("references") or []]}
    ad = VJ.Adapters(db, judge)
    checks = {"identity": ad.identity(cand), "body_proportions": ad.body_proportions(cand),
              "outfit_consistency": ad.outfit_consistency(cand, outfit),
              "anatomy": ad.anatomy(cand), "realism": ad.realism(cand)}
    fid = {"status": "UNKNOWN", "why": "the product CIR could not be loaded"}
    try:
        from ..creative.pattern_refs import release_hash_of

        load_cir = cir_loader or _engineered
        cir = load_cir(product.get("slug"))
        if cir is None or release_hash_of(cir) != product.get("cir_hash"):
            fid = {"status": "UNKNOWN", "why": "the product's CIR is not the frozen content "
                                               "hash; fidelity is not measured"}
        else:
            patches = VJ.locate_product(judge, data).get("patches") or None
            got = F.verify_lifestyle(data, cir, release_hash=product["cir_hash"], anchor=None,
                                     product_region=patches, judge=judge,
                                     consistency=VJ.blind_consistency)
            fid = {"status": got["status"], "codes": got["codes"], "failed": got["failed"],
                   "unknown": got["unknown"],
                   "checks": [{k: c.get(k) for k in ("check", "status", "why", "code")}
                              for c in got["checks"]]}
    except Exception as exc:  # noqa: BLE001 - an unmeasured check is UNKNOWN
        fid = {"status": "UNKNOWN", "why": f"{type(exc).__name__}: {str(exc)[:200]}"}
    checks["fidelity"] = fid
    st = [c.get("status", "UNKNOWN") for c in checks.values()]
    summary = "FAIL" if "FAIL" in st else "UNKNOWN" if "UNKNOWN" in st else "PASS"
    return {"summary": summary, "checks": {k: {kk: c.get(kk) for kk in (
        "status", "why", "codes", "failed", "unknown", "checks", "slots", "band")
        if c.get(kk) is not None} for k, c in checks.items()},
            "unknown": sorted(k for k, c in checks.items() if c.get("status") == "UNKNOWN"),
            "vision_calls": judge.calls, "vision_spent_cad": round(judge.spent - vis_spent, 6)}


def _engineered(slug: str):
    from ..runtime.pipeline import _engineered_cir

    return _engineered_cir(slug)


# ---- pipeline runs (W-VISNEXT2) ---------------------------------------------------------------

def pipeline_ns(run_id: int) -> str:
    return f"exp{int(run_id)}"


def _start_pipeline(db, run_id: int, defn: dict, v: dict, *, enqueue, job_id) -> dict:
    """Start the orchestrator on the certified release under this run's namespace. The
    orchestrator then spends only through `guard_generation`, inside the shared cap."""
    from ..visual import image_production as IP

    if enqueue is None:
        _update(db, run_id, status="refused", why="no queue to start the pipeline on")
        return {"ran": False, "refused": True, "why": "no queue", "run_id": run_id}
    p = defn["product"]
    _update(db, run_id, status="running", job_id=job_id, references=v["references"])
    got = IP.trigger(enqueue, slug=p["slug"], version=p["version"], release=p["cir_hash"],
                     ns=pipeline_ns(run_id), controlled_run_id=run_id)
    _update(db, run_id, receipt={"pipeline": True, "ip_run_key": got.get("run_key"),
                                 "images": []})
    return {"ran": True, "pipeline": True, "run_id": run_id, "ip_run_key": got.get("run_key"),
            "status": "running"}


def require_pipeline_run(db, run_id, *, ns: str, slug: str, version: str, release: str) -> dict:
    """The orchestrator refuses a namespaced stage unless it belongs to a live, authorised
    pipeline run for exactly this product and release."""
    from ..visual import experiment as XP

    r = get_run(db, run_id) if run_id else None
    if r is None or ns != pipeline_ns(run_id):
        raise XP.ExperimentRefused("a controlled stage names no controlled run of its own")
    loaded = load(r["definition_id"])
    defn = loaded["definition"]
    p = defn.get("product") or {}
    if defn.get("kind") != "pipeline" or (p.get("slug"), p.get("version"), p.get("cir_hash")) \
            != (slug, version, release):
        raise XP.ExperimentRefused("the controlled run is not for this product release")
    if r["status"] not in ("running", "completed"):
        raise XP.ExperimentRefused(f"the controlled run is {r['status']}")
    auth = authorization(db, r["definition_id"], loaded["sha256"])
    if auth is None or auth["auth_id"] != r["auth_id"]:
        raise XP.ExperimentRefused("the authorization was revoked or replaced")
    return {"run": r, "auth": auth, "definition": defn}


def guard_generation(db, run_id: int, price_cad: float) -> None:
    """Before a pipeline generation: the shared cap must hold the price; it is reserved."""
    from ..visual.image_production import BudgetStop, CapabilityBlocked

    r = get_run(db, run_id)
    if r is None or r["status"] != "running":
        raise CapabilityBlocked("the controlled run is not running; nothing is sent")
    loaded = load(r["definition_id"])
    auth = authorization(db, r["definition_id"], loaded["sha256"])
    if auth is None or auth["auth_id"] != r["auth_id"]:
        raise CapabilityBlocked("the owner authorization was revoked or replaced")
    gen, _ = _group_spent(db, r["definition_id"])
    if gen + float(price_cad) > float(auth["generation_cap_cad"]) + 1e-9:
        raise BudgetStop(f"shared generation cap CA${auth['generation_cap_cad']:.2f} would be "
                         f"exceeded (spent CA${gen:.4f} across {sorted(cap_group(r['definition_id']))}"
                         f", next CA${float(price_cad):.4f})")
    _update(db, run_id, generation_spent_cad=float(r["generation_spent_cad"]) + float(price_cad),
            attempts=int(r["attempts"] or 0) + 1)


def record_generation(db, run_id: int, *, reserved_cad: float, actual_cad, sha256: str | None):
    """After a pipeline generation: bill the actual (the reservation if unknown) and mark the
    bytes as an experiment image, before anything evaluates them."""
    r = get_run(db, run_id)
    actual = float(reserved_cad if actual_cad is None else actual_cad)
    receipt = dict(r["receipt"] or {})
    if sha256:
        receipt["images"] = list(receipt.get("images") or []) + [sha256]
    _update(db, run_id, generation_spent_cad=max(0.0, float(r["generation_spent_cad"])
                                                 - float(reserved_cad) + actual),
            receipt=receipt)


def sync_pipeline(db, run_id: int, ip_key: str) -> None:
    """Mirror the orchestrator's end state onto the controlled run."""
    from ..visual import image_production as IP

    ip = IP.get_run(db, ip_key)
    if not ip or ip["state"] not in ("ready_for_owner_review", "blocked"):
        return
    r = get_run(db, run_id)
    receipt = {**dict(r["receipt"] or {}), "ip_state": ip["status"]}
    card = IP.gallery_card(db, ip_key) or {}
    tech = ((card.get("decisions") or {}).get("technical_certification") or {}).get("state")
    _update(db, run_id, status="completed", receipt=receipt,
            why=str(ip.get("blocked_reason") or "")[:2000],
            verification={"summary": tech or "UNKNOWN", "ip_run_key": ip_key,
                          "unknown": sorted({u for f in card.get("frames") or []
                                             for u in f.get("unknown") or []})})


# ---- reading it back ------------------------------------------------------------------------

def _run_view(r) -> dict:
    return {"run_id": r.id, "definition_id": r.definition_id,
            "definition_sha256": r.definition_sha256, "auth_id": r.auth_id, "n": r.n,
            "idempotency_key": r.idempotency_key, "job_id": r.job_id, "status": r.status,
            "why": r.why, "attempts": r.attempts,
            "generation_spent_cad": round(r.generation_spent_cad or 0.0, 6),
            "vision_spent_cad": round(r.vision_spent_cad or 0.0, 6),
            "image_sha256": r.image_sha256 or None, "references": list(r.references or []),
            "receipt": dict(r.receipt or {}), "verification": dict(r.verification or {}),
            "attempt_log": list(r.attempt_log or []),
            "created_at": r.created_at.isoformat() if r.created_at else None}


def runs(db, definition_id: str | None = None) -> list[dict]:
    from sqlalchemy import select

    ensure_tables(db)
    with db.session() as s:
        q = select(ControlledRun)
        if definition_id:
            q = q.where(ControlledRun.definition_id == definition_id)
        return [_run_view(r) for r in s.scalars(q.order_by(ControlledRun.id.desc()))]


def get_run(db, run_id: int) -> dict | None:
    ensure_tables(db)
    with db.session() as s:
        r = s.get(ControlledRun, int(run_id))
        return _run_view(r) if r else None


def board(db) -> list[dict]:
    """Every definition, its live authorization, its runs and whether its inputs verify."""
    out = []
    for did in definition_ids():
        loaded = load(did)
        defn = loaded["definition"]
        out.append({"id": did, "definition_sha256": loaded["sha256"],
                    "purpose": defn.get("purpose"), "product": defn.get("product"),
                    "model": defn.get("model"), "size": defn.get("size"),
                    "generation_cap_cad": defn.get("generation_cap_cad"),
                    "vision_cap_cad": defn.get("vision_cap_cad"),
                    "max_retries": defn.get("max_retries"),
                    "inputs_verified": verify(loaded)["ok"],
                    "authorization": authorization(db, did, loaded["sha256"]),
                    "runs": runs(db, did)[:5]})
    return out


def card(db, run_id: int) -> dict | None:
    """The gallery approval card for an experiment run: the same three decisions, plus the
    EXPERIMENT banner, the receipt, the fingerprints in order, costs against caps, every
    verification result (UNKNOWNs listed) and the authorization id."""
    from ..visual import experiment as XP

    r = get_run(db, run_id)
    if r is None:
        return None
    loaded = load(r["definition_id"])
    defn = loaded["definition"]
    auth = None
    from sqlalchemy import select

    with db.session() as s:
        a = s.scalar(select(ExperimentAuthorization).where(
            ExperimentAuthorization.auth_id == r["auth_id"]))
        if a is not None:
            auth = {"auth_id": a.auth_id, "generation_cap_cad": a.generation_cap_cad,
                    "vision_cap_cad": a.vision_cap_cad, "authorized_by": a.authorized_by,
                    "revoked": a.revoked}
    ver = r["verification"] or {}
    blockers = [XP.LABEL, "controlled experiment output: never publishable"]
    ip_key = (r["receipt"] or {}).get("ip_run_key")
    if defn.get("kind") == "pipeline" and ip_key:
        from ..visual import image_production as IP

        base = IP.gallery_card(db, ip_key) or {}
        dec = dict(base.get("decisions") or {})
        dec["publication_authorization"] = {"state": "not_available", "blockers": blockers,
                                            "requires": "not available for experiments",
                                            "what": "experiments never publish"}
        return {**base, "experiment": True, "label": XP.LABEL, "banner": XP.LABEL,
                "run_id": r["run_id"], "definition_id": r["definition_id"],
                "definition_sha256": r["definition_sha256"], "authorization": auth,
                "references_in_order": r["references"], "receipt": r["receipt"],
                "verification": ver, "decisions": dec,
                "costs": {"generation_spent_cad": r["generation_spent_cad"],
                          "generation_cap_cad": (auth or {}).get("generation_cap_cad"),
                          "shared_with": sorted(cap_group(r["definition_id"]) -
                                                {r["definition_id"]}),
                          "vision_spent_cad": r["vision_spent_cad"],
                          "vision_cap_cad": (auth or {}).get("vision_cap_cad")}}
    if not (defn.get("product") or {}).get("certified"):
        blockers.append("the product is uncertified")
    img = (f"/api/cc/experiments/runs/{r['run_id']}/image" if r["image_sha256"] else None)
    return {
        "experiment": True, "label": XP.LABEL, "banner": XP.LABEL, "run_key": None,
        "run_id": r["run_id"], "listing": (defn.get("product") or {}).get("slug"),
        "definition_id": r["definition_id"], "definition_sha256": r["definition_sha256"],
        "authorization": auth, "state": r["status"], "status": r["status"], "why": r["why"],
        "frames": [{"position": 1, "role": "experiment", "job": "LIFESTYLE",
                    "source": "experiment", "image_url": img, "sha256": r["image_sha256"],
                    "technical_status": ver.get("summary"),
                    "failed": {k: c.get("why") for k, c in (ver.get("checks") or {}).items()
                               if c.get("status") == "FAIL"},
                    "unknown": ver.get("unknown") or [],
                    "label": "AI-generated EXPERIMENT image, never a photograph",
                    "status": r["status"]}],
        "references_in_order": r["references"], "receipt": r["receipt"],
        "attempt_log": r["attempt_log"], "verification": ver,
        "costs": {"generation_spent_cad": r["generation_spent_cad"],
                  "generation_cap_cad": (auth or {}).get("generation_cap_cad"),
                  "vision_spent_cad": r["vision_spent_cad"],
                  "vision_cap_cad": (auth or {}).get("vision_cap_cad")},
        "spent_cad": round(r["generation_spent_cad"] + r["vision_spent_cad"], 6),
        "generation_calls": r["attempts"], "restarts": 0,
        "restartable": {"restartable": False, "why": "an experiment run is one-shot"},
        "decisions": {
            "visual_approval": {"state": "not_recorded", "record": None, "affects_gates": False,
                                "what": "your look at this image only"},
            "technical_certification": {"state": ver.get("summary") or "UNKNOWN",
                                        "what": "independent checks; UNKNOWN is never PASS"},
            "publication_authorization": {"state": "not_available", "blockers": blockers,
                                          "requires": "not available for experiments",
                                          "what": "experiments never publish"}},
        "recommended_fix": []}
