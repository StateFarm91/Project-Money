# Frozen live FLUX 3 test: Reading Nook Cable Wrap, seven references (owner-approved, inside the CA$5 experiment)

The plan, prompt and reference fingerprints are frozen in `plan.json` and `prompt.txt`. `run_one.py` refuses to run if any of
them drifts. It makes one FLUX 3 call at 2048x2048, about US$0.10. The key is read from the environment only, and is never
printed or written to disk.

References, in transmission order:

1. Laura face, a42aeac7
2. Laura torso, afe6191f
3. Laura full body, f32bac68
4. The owner's wrap layout, 3f737a08
5. The owner's cable stitch structure, 10d013b8
6. The owner's construction rules, 3638b3a5
7. Crochet-texture reference, bc88ed04

Run from `brambleloop/`, in a session that has `BRAMBLELOOP_IMAGE_KEY_BFL` set as an environment secret:

    PYTHONPATH=src .venv/bin/python research/final_build/w4/flux_live_test_2026-10-20/run_one.py <out_dir> plan   # no spend
    PYTHONPATH=src .venv/bin/python research/final_build/w4/flux_live_test_2026-10-20/run_one.py <out_dir> live

After the image is made, run the independent checks:

- the fidelity checker (`visual/fidelity.verify_lifestyle`);
- the vision judges (`visual/vision_judges`), using `ANTHROPIC_API_KEY`, within the CA$1.00 vision authorisation.

The result is UNCERTIFIED and EXPERIMENT-only, and can never be published.
