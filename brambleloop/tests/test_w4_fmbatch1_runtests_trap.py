"""F-146: run_tests.sh keeps exactly one EXIT trap, and the interrupt path routes through it.

A second `trap ... EXIT` replaces the first rather than adding to it, which is how a previous
version silently discarded its containment cleanup. This fails the moment someone adds one.
"""
import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "run_tests.sh").read_text()


def traps(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines()
            if re.match(r"\s*trap\s", ln) and not ln.lstrip().startswith("#")]


def exit_traps(text: str) -> list[str]:
    return [t for t in traps(text) if re.search(r"\bEXIT\b", t)]


TRAPS = traps(SRC)


def test_exactly_one_exit_trap_and_it_is_the_cleanup():
    exits = exit_traps(SRC)
    assert len(exits) == 1, exits
    assert exits[0].split()[1] == "_brambleloop_cleanup", exits


def test_int_and_term_are_trapped_and_exit_through_the_exit_trap():
    sig = [t for t in TRAPS if re.search(r"\bINT\b", t) and re.search(r"\bTERM\b", t)]
    assert len(sig) == 1 and "exit" in sig[0] and "EXIT" not in sig[0], sig
    assert len(TRAPS) == 2, TRAPS


def test_the_check_catches_a_second_exit_trap():
    assert len(exit_traps(SRC + "\ntrap 'rm -rf x' EXIT\n")) == 2
    assert len(exit_traps(SRC + "\n  trap cleanup EXIT INT TERM\n")) == 2
    assert len(exit_traps(SRC + "\n# trap commented EXIT\n")) == 1


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
