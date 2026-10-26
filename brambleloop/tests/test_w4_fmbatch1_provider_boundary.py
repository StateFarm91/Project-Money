"""F-091: business code reaches a model through gateway/providers.py, not a vendor module.

The scan is AST-based: every `import`/`from ... import` outside `gateway/` that names the
vendor module `gateway.anthropic`. PENDING lists, by file, the callers that still do, with the
reason each is not yet migrated. A new direct importer fails this test; a migrated file left
on PENDING fails it too, so the list can only shrink truthfully.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "brambleloop"
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.gateway import model_gateway, providers  # noqa: E402

VENDOR_MODULES = {"anthropic"}
LANE_C = "visual/ is the product-engine lane (Workstream C); migration handed to that lane"
PENDING = {
    "visual/model_registry.py": LANE_C,
    "visual/photoreal.py": LANE_C,
    "visual/inspect.py": LANE_C,
    "visual/tournament.py": LANE_C,
    "visual/bible.py": LANE_C,
    "visual/fidelity.py": LANE_C,
    "runtime/release.py": "product-run handlers (Workstream C); vision probes and judges",
    "runtime/worker.py": "worker boot reads the vendor's probe state; operator plumbing",
    "ops/provider_accounts.py": "vendor account bookkeeping is vendor-specific by design",
    "ops/health.py": "reads the vendor probe record (last_probe) for the health sweep",
    "app/main.py": "the model-probe API route reads vendor probe state",
    # Product engine / creative pipeline (Workstream C lane):
    "creative/blinded.py": LANE_C, "creative/image_stages.py": LANE_C,
    "creative/intake.py": LANE_C, "creative/prospecting.py": LANE_C,
    "creative/reference.py": LANE_C, "experiments/controlled.py": LANE_C,
    # Publication (W-LISTREADY lane):
    "publish/motif_fidelity.py": "publication lane (W-LISTREADY); provider_for for a judge",
    # Ceiling-ledger readers: they import the ledger, not a model; neutral names exist in
    # providers.NEUTRAL, migration is an import change each.
    "finance/funding_packet.py": "ceiling ledger reader (check_budget_cad, probe)",
    "finance/governor.py": "ceiling ledger reader",
    "finance/spend_policy.py": "ceiling ledger reader (check_budget_cad)",
    "build2/executor.py": "reads vendor probe/capability state for closure checks",
    "launch/readiness.py": "reads vendor probe state (last_probe) for readiness",
    "scale/dependency.py": "dependency register names the vendor it measures",
    "intel/insights_budget.py": "ceiling ledger reader",
    "intel/market_map.py": "gallery analysis path; vision judge",
    # Research vision callers: provider_for + budget; next to migrate.
    "intel/serp.py": "vision caller (provider_for, check_budget); next to migrate",
    "intel/vision.py": "vision caller (provider_for, check_budget); next to migrate",
}


def _direct_importers() -> set[str]:
    out = set()
    for p in SRC.rglob("*.py"):
        rel = p.relative_to(SRC).as_posix()
        if rel.startswith("gateway/"):
            continue
        tree = ast.parse(p.read_text(), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.endswith("gateway") and any(a.name in VENDOR_MODULES for a in node.names):
                    out.add(rel)
                if any(mod.endswith(f"gateway.{v}") for v in VENDOR_MODULES):
                    out.add(rel)
            elif isinstance(node, ast.Import):
                if any(a.name.endswith(f"gateway.{v}") for a in node.names
                       for v in VENDOR_MODULES):
                    out.add(rel)
    return out


def test_no_new_direct_vendor_importer_and_pending_only_shrinks():
    found = _direct_importers()
    new = sorted(found - set(PENDING))
    stale = sorted(set(PENDING) - found)
    assert not new, f"business modules importing a vendor module directly: {new}"
    assert not stale, f"migrated, remove from PENDING: {stale}"
    assert "culture/classify.py" not in found


def test_vendor_is_chosen_at_the_boundary_and_unknown_refuses():
    class Fake:
        name, model = "fakevendor", "fake-1"
        cost_per_1k_input_cad = cost_per_1k_output_cad = 0.0

        def __init__(self, task):
            self.task = task

        def complete(self, system, user, *, max_tokens):
            return model_gateway.ModelResponse(text="{}", provider=self.name, model=self.model,
                                               input_tokens=0, output_tokens=0, latency_ms=0)

    providers.register_vendor("fakevendor", lambda task, **kw: Fake(task))
    try:
        p = providers.for_task("culture_classify", env={providers.VENDOR_VAR: "fakevendor"})
        assert p.name == "fakevendor" and p.task == "culture_classify"
        try:
            providers.for_task("x", env={providers.VENDOR_VAR: "nobody"})
            raise AssertionError("an unregistered vendor must refuse")
        except model_gateway.NoProviderAvailable as exc:
            assert "nobody" in str(exc)
        default = providers.for_task("topic_filing", env={})
        assert default.name == "anthropic"     # constructed only; no call is made
    finally:
        providers.unregister_vendor("fakevendor")
    assert providers.vendor({}) == "anthropic"
    from brambleloop.gateway import anthropic
    for n in providers.NEUTRAL:
        assert getattr(providers, n) is getattr(anthropic, n), n


def test_migrated_caller_uses_the_boundary(monkeypatch=None):
    from brambleloop.culture import classify as C

    seen = {}

    class Stub:
        name, model = "stub", "stub-1"
        cost_per_1k_input_cad = cost_per_1k_output_cad = 0.0

        def complete(self, system, user, *, max_tokens):
            seen["called"] = True
            return model_gateway.ModelResponse(text='{}', provider="stub",
                                               model="stub-1", input_tokens=0,
                                               output_tokens=0, latency_ms=0)

    providers.register_vendor("stubv", lambda task, **kw: seen.setdefault("task", task)
                              and Stub())
    import os
    os.environ[providers.VENDOR_VAR] = "stubv"
    try:
        C.classify(["Wednesday_(TV_series)"], db=None)
    finally:
        os.environ.pop(providers.VENDOR_VAR, None)
        providers.unregister_vendor("stubv")
    assert seen.get("called") and seen.get("task") == C.TASK


def test_the_dependency_register_no_longer_claims_a_caller_free_swap():
    from brambleloop.ops import dependencies

    deps = dependencies.DEPENDENCIES
    d = deps["model_provider"] if isinstance(deps, dict) else next(
        x for x in deps if x.key == "model_provider")
    assert "without touching the callers" not in d.recovery
    assert "F-091" in d.recovery


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
