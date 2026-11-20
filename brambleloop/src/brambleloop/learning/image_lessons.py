"""The image learning loop, and the stable interface the image producers read (ENG-LEARN).

**What it learns from.** Every `image_candidates` row is a frame some producer made or
recovered, judged by the shared candidate gates. `harvest` turns each row, once, into a
structured observation:
- the prompt_version, and features read deterministically from the prompt and the scene;
- the references used;
- product family and frame role;
- each gate's verdict and the failure reasons;
- cost and attempt.

No model reads the picture again. A feature is a closed-vocabulary word found in the text
the generator was sent, or a field the generator recorded.

**What it derives.** `derive_lessons` compares, within one family and frame role, the pass
rate of each gate for one feature value against every other value. A lesson is stated only
when both sides have at least `stats.LESSON_MIN_N` frames and the difference clears
`LESSON_ALPHA`, Bonferroni-corrected for the number of comparisons made in that scope.
A lesson whose evidence later weakens is marked inactive. It is not left standing.

**How templates evolve.** Each scope (`family:role`) has one champion template and at most
`MAX_CHALLENGERS` challengers. `prompt_for` assigns each generation deterministically, by
a hash of its assignment key. A capped share (`CHALLENGER_SHARE`, never above
`CHALLENGER_SHARE_CAP`) goes to challengers. The assignment replaces the champion for that
generation; it never adds one. So the generation count, and the spend ceilings the
generation gate already enforces, are unchanged.

`evaluate` compares each challenger with the champion on frames made in the same period:
- **Promotion** needs one of two things:
  - a first-pass QA rate significantly higher (`stats.ALPHA`, `stats.MIN_N` per arm, at least
    `stats.MIN_LIFT` absolute);
  - or a cost per completed gallery significantly lower with no first-pass loss.
- **Early stop.** A challenger measurably worse is retired early, because worse frames cost
  retries.
- **Demotion.** A promoted champion whose later frames do measurably worse than the
  evidence that promoted it is rolled back to the champion it replaced.
- **Ledger.** Every seed, promotion, demotion and retirement is a `learning_decisions` row
  with the counts behind it.

**Contract (for ENG-VIS-GALLERY and ENG-VIS-FLUX).** It is stable, versioned `CONTRACT`:
- `prompt_for(db, family=, role=, assignment_key=)` returns the template to generate from
  this time, its `prompt_version`, and the scene lessons for that scope.
- The producer puts that `prompt_version` (and, optionally, `scene`) on the candidate it
  hands to `image_production.record_candidate`. That is the whole integration: the next
  harvest attributes the frame's QA outcome to the arm.
- `scene_lessons(db, family=, role=)` returns the active lessons for one scope.
- `render_brief(template)` returns the template as brief text plus its negatives.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from . import stats
from .store import Arm, Decision, DerivedLesson, ImageObservation, ensure_tables

CONTRACT = "image_lessons/1"
CHALLENGER_SHARE = 0.15
CHALLENGER_SHARE_CAP = 0.20
MAX_CHALLENGERS = 2
FUTILITY_N = 10 * stats.MIN_N          # a challenger this measured with no verdict is retired
COST_MIN_GALLERIES = 15
COST_MIN_REDUCTION = 0.15
NON_INFERIOR_SLIP = 0.03
PREFIX = "learn:"

# ---- closed feature vocabulary -----------------------------------------------------------
# Each value has the phrase `render_brief` writes and the patterns `features` reads. Because
# the same table writes and reads, a template's own choices are recognised in its output.
CAMERA: dict[str, tuple[str, tuple[str, ...]]] = {
    "three_quarter": ("seen from a three-quarter angle",
                      (r"three[- ]quarter", r"\b3/4\b")),
    "overhead": ("seen from directly above",
                 (r"directly above", r"overhead", r"flat[- ]lay", r"top[- ]down")),
    "side": ("seen from the side", (r"from the side", r"side view", r"\bprofile\b")),
    "front": ("seen straight on", (r"straight on", r"front view", r"head[- ]on")),
    "close": ("a close detail view", (r"close[- ]up", r"\bmacro\b", r"close detail")),
    "full_length": ("full length", (r"full[- ]length",)),
}
LIGHTING: dict[str, tuple[str, tuple[str, ...]]] = {
    "daylight": ("soft daylight", (r"daylight", r"natural light", r"window light",
                                   r"sunlight", r"north window")),
    "warm_lamp": ("warm lamp light", (r"\blamp", r"warm light", r"evening light",
                                      r"candle")),
    "studio": ("even studio light", (r"studio", r"softbox", r"seamless")),
}
POSE: dict[str, tuple[str, ...]] = {
    "draped": (r"draped",), "folded": (r"folded",), "worn": (r"wearing", r"\bworn\b"),
    "held": (r"holding", r"\bheld\b", r"in (?:her|his) hands"),
    "on_shelf": (r"on a shelf",), "on_table": (r"on a (?:wooden |dining )?table",),
    "laid_flat": (r"laid (?:completely )?flat", r"unfolded"),
    "standing": (r"standing upright",),
}
ROOM: dict[str, tuple[str, ...]] = {
    "living_room": (r"living room", r"\bsofa\b", r"\bcouch\b"),
    "nursery": (r"nursery",), "kitchen": (r"kitchen",), "dining": (r"dining",),
    "bedroom": (r"bedroom",), "entry": (r"entry(?:way)?", r"hallway"),
}
DIMENSIONS = ("camera", "lighting", "pose", "room", "laura", "reference_set")

# Gate check keys (visual.candidate_gates) -> the verdict names learning reports.
GATE_OF_CHECK: dict[str, str] = {
    "identity": "identity", "outfit": "outfit", "outfit_consistency": "outfit",
    "outfit_distinctness": "outfit", "product_truth": "product_fidelity",
    "anatomy": "anatomy", "body_proportions": "anatomy", "realism": "realism",
    "scale": "dimensions", "dimensions": "dimensions", "quality": "quality",
}
GATES = ("accepted", "identity", "outfit", "product_fidelity", "anatomy", "realism",
         "dimensions", "quality")


class ImageLessonsRefused(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: datetime | None) -> datetime | None:
    if v is not None and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


def _first(text: str, table: dict) -> str | None:
    for value, spec in table.items():
        pats = spec[1] if len(spec) == 2 and isinstance(spec[1], tuple) else spec
        if any(re.search(p, text) for p in pats):
            return value
    return None


def features(prompt: str, *, role: str = "", scene: dict | None = None,
             laura_present: bool = False, references: list | None = None) -> dict:
    """The closed-vocabulary features of one frame. A value nobody can read is "unstated"."""
    text = " ".join([str(prompt or ""), json.dumps(scene or {}, sort_keys=True)]).lower()
    sc = scene or {}
    kinds = sorted({str(r.get("kind") or "?") for r in references or [] if isinstance(r, dict)})
    return {
        "camera": sc.get("camera") if sc.get("camera") in CAMERA else
        (_first(text, CAMERA) or "unstated"),
        "lighting": sc.get("lighting") if sc.get("lighting") in LIGHTING else
        (_first(text, LIGHTING) or "unstated"),
        "pose": _first(text, POSE) or "unstated",
        "room": sc.get("room") if sc.get("room") in ROOM else (_first(text, ROOM) or "unstated"),
        "laura": "with_laura" if laura_present else "product_only",
        "reference_set": "+".join(kinds) if kinds else "none",
        "role": role or "unstated",
    }


def gate_verdicts(checks: dict, outcome: str) -> dict:
    """Each named gate as PASS / FAIL / UNKNOWN (worst of the checks that map to it)."""
    out: dict[str, str] = {}
    rank = {"FAIL": 2, "UNKNOWN": 1, "PASS": 0}
    for key, gate in GATE_OF_CHECK.items():
        c = (checks or {}).get(key)
        if not isinstance(c, dict) or c.get("status") not in rank:
            continue
        prev = out.get(gate)
        if prev is None or rank[c["status"]] > rank[prev]:
            out[gate] = c["status"]
    out["accepted"] = {"accepted": "PASS", "rejected": "FAIL"}.get(outcome, "UNKNOWN")
    return out


def family_of(slug: str) -> str:
    try:
        from ..visual.laura_home import category_of_slug

        return str(category_of_slug(slug) or "unknown")[:40]
    except Exception:  # noqa: BLE001 - an unreadable catalogue entry is unknown, not a guess
        return "unknown"


def _arm_of(prompt_version: str) -> int | None:
    m = re.match(r"^learn:(\d+):\d+$", prompt_version or "")
    return int(m.group(1)) if m else None


# ---- harvest -----------------------------------------------------------------------------

def harvest(db, *, limit: int = 20000, family_for=None) -> dict:
    """Turn every not-yet-observed image candidate into one observation. Idempotent."""
    from sqlalchemy import func, select

    from ..visual.image_records import ImageCandidate, ensure_tables as ensure_img

    ensure_tables(db)
    ensure_img(db)
    family_for = family_for or family_of
    made = 0
    with db.session() as s:
        last = s.scalar(select(func.max(ImageObservation.candidate_id))) or 0
        rows = list(s.scalars(select(ImageCandidate).where(ImageCandidate.id > last)
                              .order_by(ImageCandidate.id).limit(limit)))
        cache: dict[str, str] = {}
        for r in rows:
            if r.outcome == "provider_error":
                continue           # nothing was judged; a provider fault is not a QA outcome
            checks = dict(r.checks or {})
            scene = checks.get("_scene") if isinstance(checks.get("_scene"), dict) else None
            fam = cache.get(r.slug)
            if fam is None:
                fam = cache[r.slug] = family_for(r.slug)
            s.add(ImageObservation(
                candidate_id=r.id, at=_aware(r.created_at) or _now(), slug=r.slug, family=fam,
                role=r.role or "unstated", method=r.method or "", run_key=r.run_key or "",
                prompt_version=r.prompt_version or "", arm_id=_arm_of(r.prompt_version or ""),
                features=features(r.prompt, role=r.role, scene=scene,
                                  laura_present=bool(r.laura_present),
                                  references=r.references),
                references=list(r.references or []),
                gates=gate_verdicts(checks, r.outcome),
                failures=list(r.failure_categories or []), outcome=r.outcome,
                attempt=int(r.attempt or 1),
                first_pass=bool(int(r.attempt or 1) == 1 and r.outcome == "accepted"),
                cost_cad=r.cost_cad))
            made += 1
    return {"observed": made, "read": len(rows), "work_done": made}


# ---- arms --------------------------------------------------------------------------------

def scope_of(family: str, role: str) -> str:
    return f"{family or 'unknown'}:{role or 'unstated'}"


def default_template(family: str, role: str) -> dict:
    from ..visual.shot_plans import LIFESTYLE_BRIEF

    brief = (LIFESTYLE_BRIEF.get(family) or (False, "the finished piece in use"))[1]
    return {"brief": brief, "camera": None, "lighting": None, "negatives": []}


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _arm_view(a: Arm) -> dict:
    return {"arm_id": a.id, "scope": a.scope, "version": a.version, "status": a.status,
            "prompt_version": f"{PREFIX}{a.id}:{a.version}", "template": dict(a.payload),
            "source": a.source, "why": a.why,
            "created_at": _aware(a.created_at).isoformat() if a.created_at else None}


def _decide(s, scope: str, kind: str, arm_id: int, evidence: dict,
            from_arm_id: int | None = None, now: datetime | None = None) -> None:
    s.add(Decision(at=now or _now(), scope=scope, kind=kind, arm_id=arm_id,
                   from_arm_id=from_arm_id, evidence=evidence))


def champion(db, *, family: str, role: str, now: datetime | None = None) -> dict:
    """The scope's champion, seeded from the code default the first time it is asked for."""
    from sqlalchemy import select

    ensure_tables(db)
    scope = scope_of(family, role)
    with db.session() as s:
        a = s.scalar(select(Arm).where(Arm.scope == scope, Arm.status == "champion"))
        if a is None:
            payload = default_template(family, role)
            a = Arm(scope=scope, version=1, digest=_digest(payload), payload=payload,
                    status="champion", source="code-default:visual.shot_plans.LIFESTYLE_BRIEF",
                    why="the code default brief, seeded as the first champion",
                    created_at=now or _now())
            s.add(a)
            s.flush()
            _decide(s, scope, "seed", a.id, {"why": "first champion is the code default"},
                    now=now)
        return _arm_view(a)


def register_challenger(db, *, family: str, role: str, template: dict, why: str,
                        source: str, now: datetime | None = None) -> dict:
    """Add a challenger to a scope. Refused beyond MAX_CHALLENGERS; idempotent by content."""
    from sqlalchemy import func, select

    if len((why or "").split()) < 6:
        raise ImageLessonsRefused("a challenger says why it exists, in a sentence")
    champ = champion(db, family=family, role=role, now=now)
    scope = scope_of(family, role)
    payload = {"brief": str(template.get("brief") or champ["template"]["brief"]),
               "camera": template.get("camera") if template.get("camera") in CAMERA else None,
               "lighting": (template.get("lighting") if template.get("lighting") in LIGHTING
                            else None),
               "negatives": [str(n) for n in template.get("negatives") or []][:12]}
    digest = _digest(payload)
    with db.session() as s:
        same = s.scalar(select(Arm).where(Arm.scope == scope, Arm.digest == digest))
        if same is not None:
            return {"registered": False, "why": f"identical template exists ({same.status})",
                    "arm": _arm_view(same)}
        active = s.scalar(select(func.count(Arm.id)).where(
            Arm.scope == scope, Arm.status == "challenger")) or 0
        if active >= MAX_CHALLENGERS:
            return {"registered": False,
                    "why": f"{scope} already has {active} challengers (cap {MAX_CHALLENGERS})"}
        version = (s.scalar(select(func.max(Arm.version)).where(Arm.scope == scope)) or 0) + 1
        a = Arm(scope=scope, version=version, digest=digest, payload=payload,
                status="challenger", source=source[:120], why=why[:2000],
                created_at=now or _now())
        s.add(a)
        s.flush()
        _decide(s, scope, "register", a.id, {"why": why[:500], "source": source}, now=now)
        return {"registered": True, "arm": _arm_view(a)}


def share() -> float:
    return min(CHALLENGER_SHARE, CHALLENGER_SHARE_CAP)


def _bucket(scope: str, key: str) -> float:
    h = hashlib.sha256(f"{scope}|{key}".encode()).hexdigest()
    return int(h[:12], 16) / float(16 ** 12)


def prompt_for(db, *, family: str, role: str, assignment_key: str,
               now: datetime | None = None) -> dict:
    """THE CONTRACT. Which template this generation uses, and what is known about the scope.

    `assignment_key` identifies the generation (e.g. run_key + role + attempt). The same key
    always gets the same arm, so a retry of the same generation is not re-randomised."""
    from sqlalchemy import select

    if not assignment_key:
        raise ImageLessonsRefused("an assignment key is required so assignment is stable")
    champ = champion(db, family=family, role=role, now=now)
    scope = scope_of(family, role)
    with db.session() as s:
        chals = [_arm_view(a) for a in s.scalars(select(Arm).where(
            Arm.scope == scope, Arm.status == "challenger").order_by(Arm.id))]
    u = _bucket(scope, assignment_key)
    chosen, arm = champ, "champion"
    if chals and u < share():
        chosen, arm = chals[min(len(chals) - 1, int(u / (share() / len(chals))))], "challenger"
    rendered = render_brief(chosen["template"])
    return {"contract": CONTRACT, "scope": scope, "family": family, "role": role,
            "arm": arm, "arm_id": chosen["arm_id"], "prompt_version": chosen["prompt_version"],
            "template": chosen["template"], "brief": rendered["brief"],
            "negatives": rendered["negatives"],
            "scene_lessons": scene_lessons(db, family=family, role=role),
            "record_as": {"prompt_version": chosen["prompt_version"],
                          "scene": {"camera": chosen["template"].get("camera"),
                                    "lighting": chosen["template"].get("lighting")}},
            "challenger_share": share()}


def render_brief(template: dict) -> dict:
    parts = [str(template.get("brief") or "").strip()]
    if template.get("camera") in CAMERA:
        parts.append(CAMERA[template["camera"]][0])
    if template.get("lighting") in LIGHTING:
        parts.append(LIGHTING[template["lighting"]][0])
    return {"brief": ", ".join(p for p in parts if p),
            "negatives": list(template.get("negatives") or [])}


# ---- evaluation --------------------------------------------------------------------------

def _arm_stats(obs: list[ImageObservation]) -> dict:
    first = [o for o in obs if o.attempt == 1 and o.outcome in ("accepted", "rejected")]
    k = sum(1 for o in first if o.outcome == "accepted")
    galleries: dict[str, dict] = {}
    for o in obs:
        g = galleries.setdefault(o.run_key or f"cand:{o.candidate_id}",
                                 {"cost": 0.0, "accepted": 0, "costed": True})
        if o.cost_cad is None:
            g["costed"] = False
        else:
            g["cost"] += float(o.cost_cad)
        g["accepted"] += 1 if o.outcome == "accepted" else 0
    per_gallery = [g["cost"] / g["accepted"] for g in galleries.values()
                   if g["costed"] and g["accepted"] > 0]
    return {"n": len(first), "k": k, "first_pass_rate": round(k / len(first), 4) if first else None,
            "galleries": len(per_gallery), "cost_per_completed": per_gallery}


def _obs_for(s, arm_id: int, since: datetime | None = None) -> list[ImageObservation]:
    from sqlalchemy import select

    q = select(ImageObservation).where(ImageObservation.arm_id == arm_id)
    if since is not None:
        q = q.where(ImageObservation.at >= since)
    return list(s.scalars(q))


def compare(champ: dict, chal: dict) -> dict:
    """The verdict on one challenger. Pure: counts in, decision out."""
    q = stats.two_proportion(champ["k"], champ["n"], chal["k"], chal["n"])
    harm = stats.two_proportion(chal["k"], chal["n"], champ["k"], champ["n"])
    out = {"champion": {k: v for k, v in champ.items() if k != "cost_per_completed"},
           "challenger": {k: v for k, v in chal.items() if k != "cost_per_completed"},
           "quality_test": q, "harm_test": harm}
    if (champ["n"] >= stats.HARM_MIN_N and chal["n"] >= stats.HARM_MIN_N
            and harm["p"] < stats.HARM_ALPHA):
        return {**out, "verdict": "retire_harm",
                "why": (f"challenger first-pass {chal['k']}/{chal['n']} is measurably worse "
                        f"than champion {champ['k']}/{champ['n']} (p={harm['p']})")}
    if champ["n"] >= stats.MIN_N and chal["n"] >= stats.MIN_N:
        if q["p"] < stats.ALPHA and (q["lift"] or 0) >= stats.MIN_LIFT:
            return {**out, "verdict": "promote", "basis": "first_pass_rate",
                    "why": (f"first-pass {chal['k']}/{chal['n']} vs {champ['k']}/{champ['n']}, "
                            f"lift {q['lift']}, p={q['p']} < {stats.ALPHA}")}
        if (champ["galleries"] >= COST_MIN_GALLERIES and chal["galleries"] >= COST_MIN_GALLERIES
                and (q["lift"] or 0) >= -NON_INFERIOR_SLIP):
            c = stats.welch_lower(champ["cost_per_completed"], chal["cost_per_completed"])
            out["cost_test"] = c
            if (c["p"] < stats.ALPHA and c["mean_a"]
                    and c["mean_b"] <= c["mean_a"] * (1 - COST_MIN_REDUCTION)):
                return {**out, "verdict": "promote", "basis": "cost_per_completed_gallery",
                        "why": (f"cost per completed gallery CA${c['mean_b']} vs "
                                f"CA${c['mean_a']} (p={c['p']}) with first-pass not worse")}
    if chal["n"] >= FUTILITY_N:
        return {**out, "verdict": "retire_futile",
                "why": f"{chal['n']} first-pass frames and no measurable difference"}
    return {**out, "verdict": "continue",
            "why": (f"needs {stats.MIN_N} first-pass frames per arm "
                    f"(champion {champ['n']}, challenger {chal['n']}) and a significant lift")}


def evaluate(db, *, now: datetime | None = None) -> dict:
    """Judge every challenger and every recent promotion. Each change is a Decision row."""
    from sqlalchemy import select

    ensure_tables(db)
    now = now or _now()
    out = {"promoted": [], "demoted": [], "retired": [], "continuing": [], "work_done": 0}
    with db.session() as s:
        scopes = sorted({a.scope for a in s.scalars(select(Arm))})
        for scope in scopes:
            champ = s.scalar(select(Arm).where(Arm.scope == scope, Arm.status == "champion"))
            if champ is None:
                continue
            # Demotion first: a champion promoted on evidence that its own later frames
            # contradict goes back to the champion it replaced.
            if champ.previous_champion_id and champ.decided_at is not None:
                prev = s.get(Arm, champ.previous_champion_id)
                promo = s.scalar(select(Decision).where(
                    Decision.scope == scope, Decision.kind == "promote",
                    Decision.arm_id == champ.id).order_by(Decision.id.desc()))
                base = ((promo.evidence or {}).get("champion") if promo else None) or {}
                after = _arm_stats(_obs_for(s, champ.id, since=_aware(champ.decided_at)))
                if prev is not None and base.get("n") and after["n"] >= stats.MIN_N:
                    t = stats.two_proportion(after["k"], after["n"], base["k"], base["n"])
                    if t["p"] < stats.ALPHA:
                        champ.status, prev.status = "demoted", "champion"
                        champ.decided_at = prev.decided_at = now
                        ev = {"why": (f"after promotion {after['k']}/{after['n']} first-pass, "
                                      f"measurably worse than the {base['k']}/{base['n']} the "
                                      f"replaced champion had (p={t['p']})"),
                              "after": {k: v for k, v in after.items()
                                        if k != "cost_per_completed"},
                              "baseline": base, "test": t}
                        _decide(s, scope, "demote", prev.id, ev, from_arm_id=champ.id, now=now)
                        out["demoted"].append({"scope": scope, "demoted": champ.id,
                                               "restored": prev.id, **ev})
                        out["work_done"] += 1
                        continue
            chals = list(s.scalars(select(Arm).where(Arm.scope == scope,
                                                     Arm.status == "challenger")
                                   .order_by(Arm.id)))
            for ch in chals:
                since = _aware(ch.created_at)
                v = compare(_arm_stats(_obs_for(s, champ.id, since=since)),
                            _arm_stats(_obs_for(s, ch.id, since=since)))
                if v["verdict"] == "promote":
                    champ.status, champ.decided_at = "retired", now
                    ch.status, ch.decided_at, ch.previous_champion_id = "champion", now, champ.id
                    _decide(s, scope, "promote", ch.id, v, from_arm_id=champ.id, now=now)
                    out["promoted"].append({"scope": scope, "arm_id": ch.id,
                                            "replaced": champ.id, "why": v["why"],
                                            "basis": v["basis"]})
                    out["work_done"] += 1
                    # The other challengers were measured against the old champion; they
                    # restart against the new one from now.
                    for other in chals:
                        if other.id != ch.id and other.status == "challenger":
                            other.created_at = now
                    break
                if v["verdict"].startswith("retire"):
                    ch.status, ch.decided_at = "retired", now
                    _decide(s, scope, "retire", ch.id, v, from_arm_id=champ.id, now=now)
                    out["retired"].append({"scope": scope, "arm_id": ch.id, "why": v["why"]})
                    out["work_done"] += 1
                else:
                    out["continuing"].append({"scope": scope, "arm_id": ch.id, "why": v["why"]})
    return out


# ---- lessons -----------------------------------------------------------------------------

def _scope_obs(db) -> dict[str, list[ImageObservation]]:
    from sqlalchemy import select

    with db.session() as s:
        rows = list(s.scalars(select(ImageObservation)))
        s.expunge_all()
    by: dict[str, list] = {}
    for o in rows:
        by.setdefault(scope_of(o.family, o.role), []).append(o)
    return by


def derive_lessons(db, *, now: datetime | None = None, publish: bool = True) -> dict:
    """Lessons with evidence: within a scope, a feature value that changes a gate's pass rate.

    Bonferroni over every comparison made in the scope, so testing more values never makes
    a lesson easier to find. A previously active lesson that no longer clears the bar is
    deactivated, never left standing."""
    from sqlalchemy import select

    ensure_tables(db)
    now = now or _now()
    found: dict[str, dict] = {}
    for scope, obs in _scope_obs(db).items():
        tests: list[tuple] = []
        for dim in DIMENSIONS:
            values = sorted({o.features.get(dim, "unstated") for o in obs} - {"unstated"})
            for v in values:
                for gate in GATES:
                    judged = [o for o in obs if (o.gates or {}).get(gate) in ("PASS", "FAIL")]
                    a = [o for o in judged if o.features.get(dim) == v]
                    b = [o for o in judged if o.features.get(dim) != v]
                    if len(a) < stats.LESSON_MIN_N or len(b) < stats.LESSON_MIN_N:
                        continue
                    tests.append((dim, v, gate, a, b))
        if not tests:
            continue
        alpha = stats.LESSON_ALPHA / len(tests)
        for dim, v, gate, a, b in tests:
            ka = sum(1 for o in a if o.gates[gate] == "PASS")
            kb = sum(1 for o in b if o.gates[gate] == "PASS")
            up = stats.two_proportion(kb, len(b), ka, len(a))
            down = stats.two_proportion(ka, len(a), kb, len(b))
            for direction, t in ((1, up), (-1, down)):
                if t["p"] >= alpha:
                    continue
                ra, rb = ka / len(a), kb / len(b)
                ratio = (ra / rb) if direction > 0 and rb else (rb / ra) if ra else None
                fam, role = scope.split(":", 1)
                gate_words = "is accepted" if gate == "accepted" else f"passes {gate.replace('_', ' ')}"
                verb = "more" if direction > 0 else "less"
                times = f"{ratio:.1f}x" if ratio else "far"
                statement = (f"For {fam} {role} frames, {dim.replace('_', ' ')} "
                             f"{v.replace('_', ' ')} {gate_words} {times} {verb} often than "
                             f"the alternatives ({ka}/{len(a)} vs {kb}/{len(b)}, "
                             f"p={t['p']:.2g}).")
                key = f"image:{scope}:{dim}:{v}:{gate}:{'+' if direction > 0 else '-'}"
                found[key] = {"scope": scope, "direction": direction, "statement": statement,
                              "evidence": {"dim": dim, "value": v, "gate": gate,
                                           "with": [ka, len(a)], "without": [kb, len(b)],
                                           "p": t["p"], "alpha": round(alpha, 8),
                                           "tests_in_scope": len(tests)}}
    made = updated = deactivated = 0
    with db.session() as s:
        existing = {r.key: r for r in s.scalars(select(DerivedLesson).where(
            DerivedLesson.loop == "image"))}
        for key, f in found.items():
            row = existing.get(key)
            if row is None:
                s.add(DerivedLesson(loop="image", key=key, at=now, scope=f["scope"],
                                    direction=f["direction"], statement=f["statement"],
                                    evidence=f["evidence"], active=True))
                made += 1
            else:
                if not row.active or row.evidence != f["evidence"]:
                    updated += 1
                row.active, row.statement, row.evidence = True, f["statement"], f["evidence"]
        for key, row in existing.items():
            if key not in found and row.active:
                row.active = False
                deactivated += 1
    published = _publish(db) if publish else 0
    return {"lessons": len(found), "new": made, "updated": updated,
            "deactivated": deactivated, "published": published,
            "work_done": made + updated + deactivated}


def _publish(db) -> int:
    """Route active, unpublished image lessons through the lesson bus (verified_lesson)."""
    from sqlalchemy import select

    from ..improve import bus

    n = 0
    with db.session() as s:
        rows = list(s.scalars(select(DerivedLesson).where(
            DerivedLesson.loop == "image", DerivedLesson.active == True,  # noqa: E712
            DerivedLesson.bus_lesson_id.is_(None))))
        pending = [(r.id, r.statement, r.key) for r in rows]
    for rid, statement, key in pending:
        try:
            lid = bus.publish(db, origin_cell="quality", subject="image_production",
                              statement=statement, evidence_ref=key[:200],
                              confidence="measured")
        except bus.LessonRefused:
            continue
        with db.session() as s:
            s.get(DerivedLesson, rid).bus_lesson_id = lid
        n += 1
    return n


def scene_lessons(db, *, family: str, role: str) -> list[dict]:
    """THE CONTRACT. Active lessons for one scope, strongest evidence first."""
    from sqlalchemy import select

    ensure_tables(db)
    scope = scope_of(family, role)
    with db.session() as s:
        rows = list(s.scalars(select(DerivedLesson).where(
            DerivedLesson.loop == "image", DerivedLesson.scope == scope,
            DerivedLesson.active == True)))  # noqa: E712
        out = [{"key": r.key, "direction": "prefer" if r.direction > 0 else "avoid",
                "dimension": r.evidence.get("dim"), "value": r.evidence.get("value"),
                "gate": r.evidence.get("gate"), "statement": r.statement,
                "evidence": dict(r.evidence), "lesson_id": r.bus_lesson_id} for r in rows]
    return sorted(out, key=lambda x: x["evidence"].get("p", 1.0))


def propose_challengers(db, *, now: datetime | None = None) -> dict:
    """Turn evidence into challengers. Never edits a champion in place.

    A scope's active "prefer" lesson on camera or lighting (accepted or product fidelity)
    that its champion does not already apply becomes a challenger: the champion plus that one
    change. It must still win its own trial; a lesson is a hypothesis about the template,
    not proof that the template change works."""
    from sqlalchemy import select

    ensure_tables(db)
    made = []
    with db.session() as s:
        rows = [(r.scope, r.key, dict(r.evidence), r.statement) for r in s.scalars(
            select(DerivedLesson).where(DerivedLesson.loop == "image",
                                        DerivedLesson.active == True,  # noqa: E712
                                        DerivedLesson.direction == 1))]
    for scope, key, ev, statement in sorted(rows, key=lambda r: r[2].get("p", 1.0)):
        if ev.get("dim") not in ("camera", "lighting"):
            continue
        if ev.get("gate") not in ("accepted", "product_fidelity"):
            continue
        family, role = scope.split(":", 1)
        champ = champion(db, family=family, role=role, now=now)
        if champ["template"].get(ev["dim"]) == ev["value"]:
            continue
        template = {**champ["template"], ev["dim"]: ev["value"]}
        r = register_challenger(
            db, family=family, role=role, template=template,
            why=f"derived from lesson {key}: {statement}", source=f"lesson:{key}"[:120],
            now=now)
        if r.get("registered"):
            made.append(r["arm"]["arm_id"])
    return {"registered": made, "work_done": len(made)}


def decisions(db, *, scope: str | None = None, limit: int = 100) -> list[dict]:
    from sqlalchemy import select

    ensure_tables(db)
    with db.session() as s:
        q = select(Decision).order_by(Decision.id.desc()).limit(limit)
        if scope:
            q = q.where(Decision.scope == scope)
        return [{"id": d.id, "at": _aware(d.at).isoformat(), "scope": d.scope, "kind": d.kind,
                 "arm_id": d.arm_id, "from_arm_id": d.from_arm_id,
                 "why": (d.evidence or {}).get("why")} for d in s.scalars(q)]


def cycle(db, *, now: datetime | None = None) -> dict:
    """One pass of the loop: harvest, derive, propose, evaluate."""
    h = harvest(db)
    d = derive_lessons(db, now=now)
    p = propose_challengers(db, now=now)
    e = evaluate(db, now=now)
    return {"harvest": h, "lessons": d, "challengers": p, "evaluation": e,
            "work_done": h["work_done"] + d["work_done"] + p["work_done"] + e["work_done"]}
