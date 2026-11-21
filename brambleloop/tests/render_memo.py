"""A content-addressed memo for the two deterministic renders a release chain repeats.

Not a suite itself. ENG-PRODUCT-RUN-PERF (2026-11-21): `tests/test_product_run.py` spent 59%
of its time in `publish.pdf.build_pattern_pdf` and 24% in `visual.disclosed_render.render`,
with the listing-set pixel checks (`mobile.title_safe_ink`, the CONTENTS and gallery frame
draws) the next largest share
(cProfile of the full unattended cycle: 68 PDF builds and 335 frame renders for about fourteen
products). Most of those calls render bytes the same process had already rendered from the
same inputs: `gates.first_customer` re-renders both customer documents every time
`release_gates.for_publish` runs (twice per product per cycle), the US and UK documents draw
the same disclosed frames, and every rebuild re-renders products whose CIR did not change.

Both functions are pure functions of their arguments plus a small, named set of process
inputs, and both are already required to be byte-deterministic (the determinism tests in
`test_product_run.py` and `test_disclosed_render.py`, and every manifest carries the image
hash). So a repeated call with the same inputs is answered from memory, keyed by a sha256 of
EVERY input the function reads:

* `render(cir, view, layout=)`: the CIR's full canonical dict (not just its fingerprint, so a
  title or slug change is a miss), the view, the layout parameters and RENDERER_VERSION.
* `mobile.title_safe_ink(image, px=)`: the image's mode, size and pixel bytes, and `px`.
* `contents_frame.draw(f, pdf, layout)` / `gallery_frames.draw(f, layout)`: the facts dict, the
  PDF bytes, and whether a layout record was asked for (the lettered lines appended to
  `layout` are recorded and replayed with the bytes).
* `build_pattern_pdf(cir, **kw)`: the CIR's full canonical dict, every keyword argument
  pickled (the twin included, with its calibration and tolerance), the date the document will
  print when `released_on` is defaulted (`date.today()`, under the pinned clock), and the
  benchmark-lesson effects the PDF standard reads from its process snapshot.

A miss -- including any input that cannot be pickled -- calls the real function. Nothing is
skipped: the first call with any given input runs the production code unmodified, every
gate still reads the returned bytes, and a hit returns a deep copy so no caller can see
another caller's mutation. The one side effect `build_pattern_pdf` has (the benchmark-lesson
notes it buffers for the worker to flush) is recorded on the miss and replayed on every hit,
so the learning store receives the same notes it would have.

Exceptions are never memoised: a refusal is recomputed every time.

`bypassed()` turns the memo off for a block -- used by the test that proves repeated renders
are byte-identical, which must render repeatedly for real.
"""
from __future__ import annotations

import collections
import contextlib
import copy
import hashlib
import json
import pickle

STATS: collections.Counter = collections.Counter()
_STATE = {"on": True, "installed": False}
_MEMO: dict[str, object] = {}
_NOTES: dict[str, list] = {}


def _digest(*parts) -> str | None:
    try:
        return hashlib.sha256(pickle.dumps(parts, protocol=4)).hexdigest()
    except Exception:  # noqa: BLE001 - an input we cannot fingerprint is never memoised
        return None


def _cir_canon(cir) -> str:
    return json.dumps(cir.to_dict(), sort_keys=True, default=repr)


@contextlib.contextmanager
def bypassed():
    prior = _STATE["on"]
    _STATE["on"] = False
    try:
        yield
    finally:
        _STATE["on"] = prior


def install() -> None:
    """Wrap the module attributes every caller resolves at call time. Idempotent."""
    if _STATE["installed"]:
        return
    _STATE["installed"] = True

    from brambleloop.learning import benchmark_lessons as BL
    from brambleloop.publish import pdf as P
    from brambleloop.visual import disclosed_render as D

    real_render = D.render
    real_pdf = P.build_pattern_pdf

    def render(cir, view, *, layout=None):
        if not _STATE["on"]:
            return real_render(cir, view, layout=layout)
        key = _digest("render", _cir_canon(cir), view,
                      json.dumps(layout, sort_keys=True, default=repr), D.RENDERER_VERSION)
        if key is not None and key in _MEMO:
            STATS["render.hit"] += 1
            return copy.deepcopy(_MEMO[key])
        STATS["render.miss"] += 1
        frame = real_render(cir, view, layout=layout)
        if key is not None:
            _MEMO[key] = copy.deepcopy(frame)
        return frame

    def build_pattern_pdf(cir, **kw):
        if not _STATE["on"]:
            return real_pdf(cir, **kw)
        from datetime import date

        printed = kw.get("released_on") or date.today()
        key = _digest("pdf", _cir_canon(cir), sorted(kw.items()), printed.isoformat(),
                      sorted(BL.active_effects().items()))
        if key is not None and key in _MEMO:
            STATS["pdf.hit"] += 1
            with BL._LOCK:
                BL._PENDING.extend(copy.deepcopy(_NOTES[key]))
            return copy.deepcopy(_MEMO[key])
        STATS["pdf.miss"] += 1
        with BL._LOCK:
            before = len(BL._PENDING)
        doc = real_pdf(cir, **kw)
        if key is not None:
            with BL._LOCK:
                _NOTES[key] = copy.deepcopy(BL._PENDING[before:])
            _MEMO[key] = copy.deepcopy(doc)
        return doc

    D.render = render
    P.build_pattern_pdf = build_pattern_pdf

    # Second tier: the pure pixel functions the listing-set certificate re-runs on every
    # for_publish / listing.package / launch.plan pass over the same frames.
    from brambleloop.publish import mobile as M
    from brambleloop.visual import contents_frame as CF
    from brambleloop.visual import gallery_frames as G

    real_ink = M.title_safe_ink

    def title_safe_ink(image, *, px: int = M.MOBILE_THUMB_PX) -> float:
        if not _STATE["on"]:
            return real_ink(image, px=px)
        key = _digest("ink", image.mode, image.size,
                      hashlib.sha256(image.tobytes()).hexdigest(), px)
        if key is not None and key in _MEMO:
            STATS["ink.hit"] += 1
            return _MEMO[key]
        STATS["ink.miss"] += 1
        out = real_ink(image, px=px)
        if key is not None:
            _MEMO[key] = out
        return out

    def _drawer(name, real):
        # `layout` is an out-parameter (every lettered line is appended to it); it is part of
        # the result, recorded on the miss and replayed into the caller's list on a hit.
        def draw(*args, layout=None):
            if not _STATE["on"]:
                return real(*args, layout)
            key = _digest(name, args, layout is not None)
            if key is not None and key in _MEMO:
                STATS[f"{name}.hit"] += 1
                png, lines = _MEMO[key]
                if layout is not None:
                    layout.extend(copy.deepcopy(lines))
                return png
            STATS[f"{name}.miss"] += 1
            png = real(*args, layout)
            if key is not None:
                _MEMO[key] = (png, copy.deepcopy(layout) if layout is not None else None)
            return png
        return draw

    real_cf_draw, real_g_draw = CF.draw, G.draw

    def cf_draw(f, pdf, layout=None):
        return _drawer("contents.draw", real_cf_draw)(f, pdf, layout=layout)

    def g_draw(f, layout=None):
        return _drawer("gallery.draw", real_g_draw)(f, layout=layout)

    M.title_safe_ink = title_safe_ink
    CF.draw = cf_draw
    G.draw = g_draw
