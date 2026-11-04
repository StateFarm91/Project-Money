"""No-provider tests for a shared FLUX adapter's execution context."""
import threading

from brambleloop.creative import flux3_generator as FG
from brambleloop.creative import image_stages as S


def _child_use_scratch(root, ready, entered):
    gen = FG.Flux3Generator(None, renderer=S.StubRenderer(), work_root=root)
    ready.set()
    with gen._scratch():
        entered.set()


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


def test_supplied_root_serializes_separate_processes(tmp_path):
    import multiprocessing

    root = str(tmp_path / "shared-processes")
    ctx = multiprocessing.get_context("spawn")
    ready, entered = ctx.Event(), ctx.Event()
    gen = FG.Flux3Generator(None, renderer=S.StubRenderer(), work_root=root)
    child = ctx.Process(target=_child_use_scratch, args=(root, ready, entered))
    try:
        with gen._scratch():
            child.start()
            assert ready.wait(10) and not entered.wait(0.3)
        child.join(10)
        assert child.exitcode == 0 and entered.is_set()
    finally:
        if child.is_alive():
            child.terminate()
            child.join(5)


def test_supplied_root_rejects_symlink_lock_file(tmp_path):
    import pytest

    root = tmp_path / "shared"
    root.mkdir()
    target = tmp_path / "target"
    target.write_text("untouched")
    (root / ".brambleloop-flux3.lock").symlink_to(target)
    gen = FG.Flux3Generator(None, renderer=S.StubRenderer(), work_root=str(root))
    with pytest.raises(OSError):
        with gen._scratch():
            pass
    assert target.read_text() == "untouched"


def test_nested_instances_with_same_supplied_root_do_not_deadlock(tmp_path):
    root = str(tmp_path / "nested-shared")
    a = FG.Flux3Generator(None, renderer=S.StubRenderer(), work_root=root)
    b = FG.Flux3Generator(None, renderer=S.StubRenderer(), work_root=root)
    with a._scratch():
        with b._scratch():
            assert a._root == b._root


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
