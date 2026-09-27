# Visual V2 independent R&D

Start with [CURRENT_STATE.md](CURRENT_STATE.md) for working memory and next actions. The completed first-pass [architecture report](VISUAL_V2_ARCHITECTURE.md) recommends replacing generative product redraw with deterministic product rendering plus protected composition. **No certified product image exists from this proof. External spend$0.**

## Files

| File | Purpose |
|---|---|
| CURRENT_STATE.md / NEXT_SESSION.md | Recovery and continuation without conversation history |
| DECISIONS.md / EXPERIMENTS.md | Durable decisions, negative evidence, measurements and unknowns |
| evidence_audit.py | Read-only reconstruction of committed Visual V1 evidence; no provider calls |
| build_probe.py | Original full CIR -> semantic grid and schematic routes; not crochet topology |
| render_probe.py | Blender background Cycles render and geometry/beauty provenance |
| verify_probe.py | Independent schedule, negative mutations, protected composition and old-instrument adversarial checks |
| run_offline_checks.py | Existing test subprocesses with socket access disabled |
| out/*.json | Raw evidence, manifests, render/proof records and source hashes |
| out/product_probe.png | Transparent schematic product render; not a listing image |
| out/composite_*.png | Protected-product composition examples with synthetic backgrounds |
| out/cable_ids.png | Semantic18-column diagram, not a rendered object-ID pass |
| out/*preview*.png / albedo_0001.png | Display previews; use EXR for calibrated pass values |

## Reproduce locally

Run from the repository root on `codex/visual-v2-rnd`. Use canonical LF checkout bytes (`core.autocrlf=false`) for frozen digest checks. Do not change historical source, truth or tests to repair a mismatch.

The existing workspace has Python3.12 with numpy/Pillow, SciPy1.17.1 in sibling `runtime-python`, and portable Blender4.5.0 in sibling `runtime-blender`. Downloading those free tools incurred no API spend; they are not committed. The official Blender Windows archive SHA256 is `2ee75e9466d293a784fdf020f60fe1309c1e0610ecf73c64f1fc09b01e5eec56`. GTX1070 8GB was detected but unused; rendering used CPU8threads.

```powershell
$v2Python = 'C:\Users\Jacob McKenna\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$v2Blender = '..\runtime-blender\blender-4.5.0-windows-x64\blender.exe'
& $v2Python brambleloop/research/visual_v2/evidence_audit.py
& $v2Python brambleloop/research/visual_v2/build_probe.py
& $v2Blender --background --factory-startup --python brambleloop/research/visual_v2/render_probe.py
& $v2Python brambleloop/research/visual_v2/verify_probe.py --deps ..\runtime-python
& $v2Python brambleloop/research/visual_v2/run_offline_checks.py ..\runtime-python
```

On another machine use an equivalent Python environment with numpy/Pillow/SciPy and the pinned Blender binary; adapt executable paths only. The bundled runtime ignores PYTHONPATH, so the verifier/harness accept an explicit dependency directory. Never run historical generation runners to reproduce an offline result; they can spend money.

Expected proof: full semantic schedulePASS, five structural mutantsFAIL, three opaque restoration checksPASS, one-pixel corruption caught. Old frequency-only instrument passes the two known-defective reference variants, intentionally exposing its blind spots. Overall product/realism remains uncertified. Existing harness exits nonzero because E4/E5 require missing frozen D PNG; six other suites pass151 assertions. That missing evidence is not repaired by inventing a replacement.

Generated local intermediates `routing_probe.npz`, `routing_probe.blend` and `passes_0001.exr` are ignored. Rebuild/render before verification in a fresh checkout. EXR carries raw passes; PNG previews are display-transformed. Current composition uses8-bit straight sRGB/coverage decoded into linear light; production float-EXR/fibre coverage remains a future test. Render seeds are fixed, but hardware/version byte identity is not promised. The manifests tie verification to the actual render being inspected.

Only this directory may change in this lane. No paid API calls, merge, deployment, publication, production changes, Etsy, advertising, Build2 status edits or canonical identity changes are authorized.

## Executed next experiment

[V2-P06 results](coupon/RESULTS.md): four explicit yarn coupon hypotheses built, measured and rejected for physical intersections. The current diagnostic is coupon/out/routed_top/diagnostic.png. Follow its reproduction commands and closeout manifest. A successful runner exit does not mean a structural PASS.


## Evidence audit and current construction increment

[Evidence coverage](evidence_coverage/AUDIT.md) pins Claude4edacff and adds missed yarn/slip, Wave2-5, publishing and artifact evidence. [P07](pullthrough/RESULTS.md) is the current bounded result: named-loop and spatial operation controls pass, but their assembly is blocked by missing persistent yarn/material handoff. It is not a DC or product render. Follow NEXT_SESSION.md for the next action; do not repeat historical experiments.
