"""A Launch-0 size label is what the certified twin measures, to the label's own precision."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from brambleloop.products import launch0 as L


def test_every_launch0_variant_label_is_backed_by_its_twin():
    checked = 0
    for c in L.CANDIDATES:
        from brambleloop.cir.compiler import compile_cir
        from brambleloop.cir.twin import build_twin
        for v in c.variants:
            cir = L.cir_for(v.build); r = compile_cir(cir); assert r.ok, (c.slug, v.key)
            t = build_twin(cir, r)
            got = L.size_label_backed(v.label, t.width_cm, t.height_cm)
            assert got["backed"], (c.slug, v.key, got)
            checked += 1
    assert checked >= 6


def test_a_hand_typed_label_that_drifted_from_the_twin_is_caught():
    # The large basket measures 24.4 x 23.2 cm; "25 cm across" was its old hand-typed label.
    assert not L.size_label_backed("25 cm across, 23 cm tall", 24.44, 23.19)["backed"]
    assert L.size_label_backed("24 cm across, 23 cm tall", 24.44, 23.19)["backed"]
    assert not L.size_label_backed("4 pieces, 9.6 cm across", 9.22, 9.22)["backed"]
    assert L.size_label_backed("79.2 x 97.1 cm", 79.2, 97.1)["backed"]
    assert not L.size_label_backed("one size", 10.0, 10.0)["backed"]  # no figure is not backed


if __name__ == '__main__':
    failed = 0
    for k, f in list(globals().items()):
        if k.startswith('test_'):
            try: f(); print('OK  ', k)
            except Exception as e: failed += 1; print('FAIL', k, repr(e)[:300])
    sys.exit(1 if failed else 0)
