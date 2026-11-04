"""No-provider tests for a shared FLUX adapter's execution context."""
import threading

from brambleloop.creative import flux3_generator as FG
from brambleloop.creative import image_stages as S


def test_shared_generator_serializes_scratch_and_keeps_run_key_per_thread(monkeypatch):
    gen = FG.Flux3Generator(None, renderer=S.StubRenderer())
    entered_a, entered_b, release_a = threading.Event(), threading.Event(), threading.Event()
    observed, failures = [], []

    def fake_generate(**kwargs):
        role = kwargs["role"]
        before = (role, gen.current_run_key, str(gen._root))
        if role == "a":
            entered_a.set()
            assert release_a.wait(5)
        else:
            entered_b.set()
        observed.append((before, (role, gen.current_run_key, str(gen._root))))
        return {"role": role}

    monkeypatch.setattr(gen, "_generate", fake_generate)

    def run(role):
        try:
            gen.current_run_key = "run-" + role
            gen.generate(stage="test", role=role, brief="", references=[], outfit=None, attempt=1)
            assert gen.current_run_key is None
        except BaseException as exc:
            failures.append(exc)

    a = threading.Thread(target=run, args=("a",))
    b = threading.Thread(target=run, args=("b",))
    a.start()
    assert entered_a.wait(5)
    b.start()
    try:
        assert not entered_b.wait(0.2)
    finally:
        release_a.set()
        a.join(5)
        b.join(5)
    assert not a.is_alive() and not b.is_alive() and not failures
    assert len(observed) == 2
    for before, after in observed:
        assert before == after and before[1] == "run-" + before[0]
    assert observed[0][0][2] != observed[1][0][2]


def test_generator_clears_run_key_after_exception(monkeypatch):
    import pytest

    gen = FG.Flux3Generator(None, renderer=S.StubRenderer())
    gen.current_run_key = "run-a"
    def fail(**kwargs):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(gen, "_generate", fail)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        gen.generate(stage="test", role="a", brief="", references=[], outfit=None, attempt=1)
    assert gen.current_run_key is None and gen._root is None


def test_nested_scratch_restores_outer_context():
    gen = FG.Flux3Generator(None, renderer=S.StubRenderer())
    with gen._scratch() as outer:
        with gen._scratch() as inner:
            assert gen._root == inner and inner != outer
        assert gen._root == outer
    assert gen._root is None


def test_instances_with_same_supplied_root_serialize_in_process(tmp_path):
    root = str(tmp_path / "shared")
    a = FG.Flux3Generator(None, renderer=S.StubRenderer(), work_root=root)
    b = FG.Flux3Generator(None, renderer=S.StubRenderer(), work_root=root)
    entered, done = threading.Event(), threading.Event()
    def use_second():
        entered.set()
        with b._scratch():
            done.set()
    with a._scratch():
        thread = threading.Thread(target=use_second)
        thread.start()
        assert entered.wait(5) and not done.wait(0.2)
    thread.join(5)
    assert not thread.is_alive() and done.is_set()


def test_nested_generate_refused_without_changing_outer_key(monkeypatch):
    import pytest

    gen = FG.Flux3Generator(None, renderer=S.StubRenderer())
    gen.current_run_key = "outer"
    def nested(**kwargs):
        gen.current_run_key = "inner"
        with pytest.raises(FG.GeneratorRefused, match="nested generation"):
            gen.generate(stage="test", role="inner", brief="", references=[], outfit=None, attempt=1)
        assert gen.current_run_key == "outer"
        return {}
    monkeypatch.setattr(gen, "_generate", nested)
    gen.generate(stage="test", role="outer", brief="", references=[], outfit=None, attempt=1)
    assert gen.current_run_key is None
