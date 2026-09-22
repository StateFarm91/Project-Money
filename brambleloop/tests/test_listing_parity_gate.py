"""#75 where it belongs: in front of listing export, and actually running.

The eight checks existed and nothing consulted them. A gate that is implemented and never
wired up is the shape of every "requirement met" this build has had to take back -- and it
is worse than an absent gate, because the absent one is visible.

Two properties are protected here and they pull in opposite directions, which is why the
wiring splits computing the verdict from enforcing it.
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Phase  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _published(phase: Phase, *, slug: str = "market-basket-trio"):
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/parity.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    JobQueue(db).enqueue("store_operator", "store.publish",
                         {"slug": slug, "version": "1.0.0"})
    w = Worker(db, "publish-worker", phase=phase)
    for _ in range(20):
        if not w.run_once():
            break
    with db.session() as s:
        rows = [(r.action, dict(r.detail or {})) for r in s.scalars(select(AuditLog))]
    return db, rows


def test_the_gate_runs_on_every_publish_attempt_including_the_refused_ones():
    """A gate that only runs past shadow has never been seen to run.

    Shadow Mode refuses every publication, so a parity gate enforced behind the phase
    check would reach its first real listing having executed zero times. It reads evidence
    already on file -- no render, no model call, no network -- so running it on a refused
    attempt costs nothing and is the only way to gather the record of it working.
    """
    _, rows = _published(Phase.SHADOW)
    parity = [d for a, d in rows if a == "listing.parity"]
    assert parity, "the parity gate did not run on a shadow publish attempt"
    assert set(parity[0]["dimensions"]) or parity[0]["blocks_release"]
    assert parity[0]["slug"] == "market-basket-trio"


def test_shadow_mode_is_still_the_reason_publication_was_refused():
    """The boundary that must stay outermost.

    A system that refuses to publish for a creative reason before establishing that it is
    allowed to publish at all has inverted its own gates -- and the refusal `/api/verify`
    counts as evidence of Shadow Mode working would quietly start saying something else.
    """
    _, rows = _published(Phase.SHADOW)
    refusals = [d for a, d in rows if a == "store.publish_refused"]
    assert refusals
    assert "shadow" in str(refusals[0]["reason"]).lower()
    # And the parity verdict rides along, so the refusal still records what was found.
    assert "creative_parity" in refusals[0]


def test_parity_is_enforced_after_capability_and_before_anything_is_sent():
    """Order as a property of the source, because it is invisible in any one run."""
    source = (ROOT / "src/brambleloop/runtime/pipeline.py").read_text()
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "handle_store_publish")
    lines = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            lines.setdefault(node.func.id, node.lineno)
        if isinstance(node, ast.Attribute) and node.attr in ("refusal", "publish"):
            lines.setdefault(node.attr, node.lineno)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            name = getattr(node.exc.func, "id", "")
            if name:
                lines.setdefault(f"raise {name}", node.lineno)

    assert lines["_listing_parity"] < lines["raise ShadowModeRefusal"], \
        "the verdict is computed after the phase check, so shadow never exercises it"
    assert lines["refusal"] < lines["raise ParityRefusal"], \
        "parity is enforced before the client's own capability refusals"
    assert lines["raise ParityRefusal"] < lines["publish"], \
        "a blocked listing would already have been sent"


def test_a_product_with_no_frames_is_unjudged_rather_than_clean():
    """Parity on no evidence is the emptiest kind of pass, so it is not one."""
    from brambleloop.visual import parity

    verdict = parity.assess([])
    assert verdict["verdict"] == parity.UNJUDGED
    assert verdict["blocks_release"] is True
    assert len(verdict["dimensions"]) == len(parity.DIMENSIONS)


def test_the_benchmark_comparison_is_absent_rather_than_favourable():
    """Assuming this company compares well beside MJs is the one answer with no evidence."""
    db = Database("sqlite://")
    db.create_all()
    assert pipeline._benchmark_quality(db, "anything") is None

    from brambleloop.visual import parity

    verdict = parity.assess([], benchmark_quality=None)
    assert verdict["dimensions"][parity.COMPETITIVE]["verdict"] == parity.UNJUDGED
    assert "nobody has evidence" in verdict["dimensions"][parity.COMPETITIVE]["why"]


def test_a_parity_refusal_is_terminal_rather_than_retried():
    """Re-running the same job against the same frames asks the same question."""
    from brambleloop.runtime.worker import CapabilityNotEnabled

    assert issubclass(pipeline.ParityRefusal, CapabilityNotEnabled)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
