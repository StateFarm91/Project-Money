"""ENG-LEARN slice 1: the image learning loop on synthetic observation streams.

Every frame below is synthetic: a seeded random stream stands in for gate verdicts. Nothing
is generated, judged or spent. The streams have a KNOWN truth, so the tests can say whether
the loop found it:
- a challenger that really is better is promoted;
- an identical challenger (noise) is not promoted, over many seeds and many looks;
- a worse challenger is retired early;
- a promotion its later frames contradict is demoted;
- a scene feature that really changes product fidelity becomes a lesson, and noise does not.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  per-process temp sandbox
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.learning import image_lessons as IL  # noqa: E402
from brambleloop.learning import stats  # noqa: E402
from brambleloop.visual.image_records import ImageCandidate, ensure_tables  # noqa: E402

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
FAM = lambda slug: "pillow"  # noqa: E731


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    ensure_tables(db)
    return db


def _frame(db, *, i: int, prompt_version: str, accepted: bool, prompt: str = "a pillow",
           role: str = "hero", attempt: int = 1, cost: float = 0.05, fidelity: bool | None = None,
           at: datetime | None = None, run_key: str | None = None):
    pt = "PASS" if (accepted if fidelity is None else fidelity) else "FAIL"
    with db.session() as s:
        s.add(ImageCandidate(
            sha256=f"{i:064d}", run_key=run_key or f"run{i}", method="autonomous",
            provenance_kind="ai_generated_autonomous", slug="fixture-pillow", role=role,
            attempt=attempt, prompt=prompt, prompt_version=prompt_version, cost_cad=cost,
            checks={"product_truth": {"status": pt}, "identity": {"status": "PASS"}},
            technical_status="PASS" if accepted else "FAIL",
            outcome="accepted" if accepted else "rejected",
            failure_categories=[] if accepted else ["product_fidelity"],
            created_at=at or T0 + timedelta(minutes=i)))


def _stream(db, *, n: int, p_champ: float, p_chal: float, seed: int, look_every: int = 50,
            start: int = 0, now0: datetime = T0, stop_on_promote: bool = False) -> list[dict]:
    """Generate n frames through the contract and evaluate every `look_every` frames."""
    rng = random.Random(seed)
    events = []
    for i in range(start, start + n):
        now = now0 + timedelta(minutes=i)
        pf = IL.prompt_for(db, family="pillow", role="hero", assignment_key=f"g{seed}:{i}",
                           now=now)
        p = p_chal if pf["arm"] == "challenger" else p_champ
        _frame(db, i=i, prompt_version=pf["prompt_version"], accepted=rng.random() < p, at=now)
        if (i + 1) % look_every == 0:
            IL.harvest(db, family_for=FAM)
            e = IL.evaluate(db, now=now)
            events += [("promote", x) for x in e["promoted"]]
            events += [("retire", x) for x in e["retired"]]
            events += [("demote", x) for x in e["demoted"]]
            if stop_on_promote and e["promoted"]:
                break
    return events


def _challenger(db, **template) -> int:
    r = IL.register_challenger(db, family="pillow", role="hero",
                               template={**IL.default_template("pillow", "hero"), **template},
                               why="fixture challenger for the synthetic stream test",
                               source="test", now=T0)
    assert r["registered"], r
    return r["arm"]["arm_id"]


def test_known_better_variant_is_promoted():
    db = _db()
    champ = IL.champion(db, family="pillow", role="hero", now=T0)["arm_id"]
    better = _challenger(db, camera="three_quarter")
    events = _stream(db, n=3000, p_champ=0.45, p_chal=0.80, seed=7)
    promos = [e for k, e in events if k == "promote"]
    assert promos and promos[0]["arm_id"] == better and promos[0]["replaced"] == champ, events
    assert promos[0]["basis"] == "first_pass_rate"
    now_champ = IL.champion(db, family="pillow", role="hero")
    assert now_champ["arm_id"] == better
    kinds = [d["kind"] for d in IL.decisions(db, scope="pillow:hero")]
    assert "promote" in kinds and "seed" in kinds and "register" in kinds


def test_noise_is_not_promoted_with_the_database():
    db = _db()
    IL.champion(db, family="pillow", role="hero", now=T0)
    _challenger(db, lighting="daylight")
    events = _stream(db, n=2500, p_champ=0.6, p_chal=0.6, seed=11)
    assert not [e for k, e in events if k == "promote"], events


def test_noise_false_promotion_rate_over_many_seeds_and_looks():
    """Pure counts, no database: 200 seeded identical-arm trials, each looked at 40 times.
    The sequential looks are what inflate false positives; the rate must stay under 2%."""
    false = 0
    for seed in range(200):
        rng = random.Random(seed)
        a = {"n": 0, "k": 0, "galleries": 0, "cost_per_completed": []}
        b = {"n": 0, "k": 0, "galleries": 0, "cost_per_completed": []}
        for look in range(40):
            for _ in range(85):
                a["n"] += 1
                a["k"] += rng.random() < 0.55
            for _ in range(15):
                b["n"] += 1
                b["k"] += rng.random() < 0.55
            v = IL.compare(dict(a), dict(b))
            if v["verdict"] == "promote":
                false += 1
                break
            if v["verdict"].startswith("retire"):
                break
    assert false <= 4, f"{false}/200 identical challengers promoted"


def test_known_better_found_over_many_seeds():
    """Power: a +30pt challenger is promoted in most seeded trials (pure counts)."""
    won = 0
    for seed in range(50):
        rng = random.Random(1000 + seed)
        a = {"n": 0, "k": 0, "galleries": 0, "cost_per_completed": []}
        b = {"n": 0, "k": 0, "galleries": 0, "cost_per_completed": []}
        for look in range(40):
            for _ in range(85):
                a["n"] += 1
                a["k"] += rng.random() < 0.45
            for _ in range(15):
                b["n"] += 1
                b["k"] += rng.random() < 0.75
            v = IL.compare(dict(a), dict(b))
            if v["verdict"] != "continue":
                won += v["verdict"] == "promote"
                break
    assert won >= 45, f"only {won}/50 better challengers promoted"


def test_worse_challenger_is_retired_early():
    db = _db()
    IL.champion(db, family="pillow", role="hero", now=T0)
    worse = _challenger(db, camera="overhead")
    events = _stream(db, n=2000, p_champ=0.7, p_chal=0.2, seed=3)
    retired = [e for k, e in events if k == "retire"]
    assert retired and retired[0]["arm_id"] == worse, events
    assert IL.champion(db, family="pillow", role="hero")["arm_id"] != worse


def test_promotion_contradicted_later_is_demoted():
    db = _db()
    old = IL.champion(db, family="pillow", role="hero", now=T0)["arm_id"]
    new = _challenger(db, camera="three_quarter")
    events = _stream(db, n=3000, p_champ=0.45, p_chal=0.80, seed=7, stop_on_promote=True)
    assert any(k == "promote" for k, _ in events)
    # After promotion the new champion's real rate collapses; every frame goes to it now
    # (no challengers left), at 20%.
    rng = random.Random(5)
    later = T0 + timedelta(days=10)
    for j in range(200):
        _frame(db, i=100000 + j, prompt_version=f"learn:{new}:2", accepted=rng.random() < 0.2,
               at=later + timedelta(minutes=j))
    IL.harvest(db, family_for=FAM)
    e = IL.evaluate(db, now=later + timedelta(days=1))
    assert e["demoted"] and e["demoted"][0]["restored"] == old, e
    assert IL.champion(db, family="pillow", role="hero")["arm_id"] == old
    assert "demote" in [d["kind"] for d in IL.decisions(db, scope="pillow:hero")]


def test_share_is_capped_and_assignment_is_stable():
    db = _db()
    IL.champion(db, family="pillow", role="hero", now=T0)
    _challenger(db, camera="side")
    _challenger(db, camera="front")
    third = IL.register_challenger(db, family="pillow", role="hero",
                                   template={"camera": "close"},
                                   why="a third challenger must be refused by the cap",
                                   source="test")
    assert third["registered"] is False
    arms = [IL.prompt_for(db, family="pillow", role="hero", assignment_key=f"k{i}")["arm"]
            for i in range(4000)]
    frac = arms.count("challenger") / len(arms)
    assert frac <= IL.CHALLENGER_SHARE_CAP and abs(frac - IL.share()) < 0.03, frac
    a = IL.prompt_for(db, family="pillow", role="hero", assignment_key="same")
    b = IL.prompt_for(db, family="pillow", role="hero", assignment_key="same")
    assert a["prompt_version"] == b["prompt_version"]
    assert a["contract"] == IL.CONTRACT and "brief" in a and "record_as" in a


def _scene_stream(db, *, p_3q: float, p_other: float, seed: int, n: int = 400):
    rng = random.Random(seed)
    for i in range(n):
        three_q = i % 2 == 0
        prompt = ("a pillow on a sofa, seen from a three-quarter angle, soft daylight"
                  if three_q else "a pillow on a sofa, seen straight on, soft daylight")
        fid = rng.random() < (p_3q if three_q else p_other)
        _frame(db, i=i, prompt_version="code-default:x", accepted=fid, fidelity=fid,
               prompt=prompt)
    IL.harvest(db, family_for=FAM)


def test_scene_lesson_is_derived_published_and_becomes_a_challenger():
    db = _db()
    _scene_stream(db, p_3q=0.8, p_other=0.4, seed=1)
    d = IL.derive_lessons(db, now=T0)
    assert d["lessons"] >= 1 and d["published"] >= 1, d
    lessons = IL.scene_lessons(db, family="pillow", role="hero")
    pref = [x for x in lessons if x["direction"] == "prefer" and x["dimension"] == "camera"
            and x["value"] == "three_quarter" and x["gate"] == "product_fidelity"]
    assert pref and "pillow hero" in pref[0]["statement"] and pref[0]["lesson_id"]
    from brambleloop.improve import bus

    inbox = bus.inbox(db, "creative_assets", unacted_only=False)
    assert inbox, "the lesson must reach Creative Assets"
    assert any("three quarter" in x["statement"] for x in inbox)
    p = IL.propose_challengers(db, now=T0)
    assert p["registered"], p
    chal = IL.prompt_for(db, family="pillow", role="hero", assignment_key="x")
    assert chal["scene_lessons"]
    # Idempotent: a second derivation publishes nothing new and registers nothing new.
    assert IL.derive_lessons(db, now=T0)["new"] == 0
    assert IL.propose_challengers(db, now=T0)["registered"] == []


def test_scene_noise_yields_no_lesson():
    db = _db()
    _scene_stream(db, p_3q=0.6, p_other=0.6, seed=2)
    d = IL.derive_lessons(db, now=T0)
    assert d["lessons"] == 0, IL.scene_lessons(db, family="pillow", role="hero")


def test_lesson_is_deactivated_when_evidence_weakens():
    db = _db()
    _scene_stream(db, p_3q=0.8, p_other=0.4, seed=1, n=200)
    assert IL.derive_lessons(db, now=T0, publish=False)["lessons"] >= 1
    # A large later stream where the camera makes no difference dilutes the effect away.
    rng = random.Random(9)
    for i in range(200, 3000):
        three_q = i % 2 == 0
        prompt = "seen from a three-quarter angle" if three_q else "seen straight on"
        fid = rng.random() < 0.5
        _frame(db, i=i, prompt_version="code-default:x", accepted=fid, fidelity=fid,
               prompt=prompt)
    IL.harvest(db, family_for=FAM)
    d = IL.derive_lessons(db, now=T0, publish=False)
    assert d["deactivated"] >= 1
    assert not [x for x in IL.scene_lessons(db, family="pillow", role="hero")
                if x["value"] == "three_quarter" and x["gate"] == "product_fidelity"]


def test_features_and_gates_are_deterministic():
    f = IL.features("Laura holding the pillow, seen from a three-quarter angle, warm lamp "
                    "light in the living room", role="hero", laura_present=True,
                    references=[{"kind": "laura_canonical"}, {"kind": "pattern_derived"}])
    assert f == {"camera": "three_quarter", "lighting": "warm_lamp", "pose": "held",
                 "room": "living_room", "laura": "with_laura",
                 "reference_set": "laura_canonical+pattern_derived", "role": "hero"}
    g = IL.gate_verdicts({"outfit": {"status": "PASS"}, "outfit_consistency": {"status": "FAIL"},
                          "product_truth": {"status": "UNKNOWN"}}, "rejected")
    assert g == {"outfit": "FAIL", "product_fidelity": "UNKNOWN", "accepted": "FAIL"}
    rendered = IL.render_brief({"brief": "b", "camera": "overhead", "lighting": "daylight",
                                "negatives": ["n"]})
    assert IL.features(rendered["brief"])["camera"] == "overhead"


def test_harvest_is_idempotent_and_skips_provider_errors():
    db = _db()
    _frame(db, i=1, prompt_version="x", accepted=True)
    with db.session() as s:
        s.add(ImageCandidate(sha256="e" * 64, method="autonomous", provenance_kind="x",
                             slug="fixture-pillow", outcome="provider_error"))
    assert IL.harvest(db, family_for=FAM)["observed"] == 1
    assert IL.harvest(db, family_for=FAM)["observed"] == 0


def test_rate_is_unknown_below_minimum():
    assert stats.rate(3, 5)["status"] == stats.UNKNOWN
    assert stats.rate(30, 50)["status"] == "MEASURED"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{'FAILED' if fails else 'PASSED'}: {fails} failing")
    sys.exit(1 if fails else 0)
