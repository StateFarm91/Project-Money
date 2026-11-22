# IMAGE-METHOD-REDRIVE — one restart per new generation method

Branch `eng/image-method-redrive`, from 9c18ab5e (Batch 19i16 release record). Not deployed.

## Problem

Production 19i16 makes images with the owner's method: the certified PDF pages are the
FLUX 3 references for the product frame, then the accepted product frame plus Laura's
canonical identity images are the references for the lifestyle frames, and the prompt
builder carries palette, bands and sides. Three gallery runs (market-basket-small,
hexagon-coaster-set, housewarming-key-basket) are blocked at `fidelity_gate` on
product_truth. The frames that FAILed were made under the old method. `restartable()` refused
them with "FAIL on [role]: attempts were spent", so the new method never got to run on them.

## What changed (`visual/image_production.py`)

1. **The method version is stamped on each candidate.** `generation_method(gen)` builds the
   version from fixed identifiers:
   `flux_prompt.BUILDER_VERSION | pattern_refs.VERSION | pdf-page-refs/<ver> | OWNER_METHOD`.
   Only code changes move the version. What the generator declares
   (`accepts_owner_method`) is kept beside it as `generator_owner_method`, as provenance, and
   is not part of the version.
   The pdfium build is stripped from the page-reference version because it says which
   environment ran the code, not which method. `_generate` puts the stamp on every candidate,
   including provider-error rows. `record_candidate` saves it as `checks._generation_method`,
   and `reverify` keeps it.
2. **Old candidates read as `pre-method`.** `candidate_method_version()` returns `pre-method`
   for any row without a stamp. The rows are not rewritten. Stored provenance does not record
   the pattern-reference version, so a pre-stamp row cannot be shown to match the current
   method. Calling it `pre-method` is the honest reading.
3. **`restartable()` allows one method redrive.** All of these must hold:
   - the run is blocked at `fidelity_gate` with a FAILed role;
   - every FAIL candidate of the failed roles was made under a method version other than the
     current one;
   - no earlier restart of this run (by anyone) recorded `method_version == current`;
   - the run's existing caps still leave room for one product-frame attempt (see below).

   If all hold, it resumes at `product_generation` and regenerates instead of reverifying.
   `restart()` writes `method_version` into the history and `_restart.method_redrive`. The
   other refusals still apply unchanged: experiments, budget stops and `MAX_RESTARTS`.
4. **Attempts after a redrive count only the current method.** Once a run has been redriven,
   `_attempts()` counts only candidates stamped with the version it was redriven for, so the
   new method gets its own `MAX_ATTEMPTS_PER_ROLE`. Generation calls and spend are never
   scoped or reset.
5. **Headroom.** The run needs one product-frame attempt: one call, or two for a vessel
   (side view plus top-down). Each call is costed at the FLUX 3 2k-tier maximum in CAD.
   Headroom is checked against the same spend plan the generation guard enforces:
   `MAX_GENERATION_CALLS` and `gallery_budget.effective_cap`. With no room, the run stays
   blocked with the code `method_redrive:no_headroom`. The readback is in
   `get_run()["method_redrive"]`, which holds the code, why, and calls and CAD left versus
   needed. No cap is raised or reset.
6. **The hourly sweep picks these runs up.** `redrive_capability_blocked`, called by the
   hourly `chain.successors`, now considers blocked runs at `fidelity_gate`. It returns
   `method_redrives: {eligible, done, no_headroom}` as lists of run keys, and
   `chain_successors` reports the counts under the same three keys. Refusal codes come from
   a fixed set: `method_redrive:no_headroom`, `method_redrive:already_redriven` and
   `method_redrive:failed_under_current_method`.

## Caps (unchanged)

- `MAX_GENERATION_CALLS = 12` per gallery.
- `MAX_SPEND_CAD_PER_GALLERY = 2.00` (the brief said CA$2.50). The code cap is lower, and
  `effective_cap` (the lower of the code cap and the owner's cap) is what binds. It is not
  raised here.

## Known limits

- A run whose failures were made under the 19i16 method before this stamp existed reads as
  `pre-method` and gets one restart. That restart is bounded by the existing caps and happens
  once per version.
- Live effect on the three named runs is not verified. That needs a deploy, and this branch
  deploys nothing.

## Tests

`tests/test_image_method_redrive.py` covers:
- the stamp fields and storage;
- an old-method block restarts once under the new method, and attempts are then scoped;
- the same method never restarts twice;
- calls, spend and caps are not reset;
- no headroom (calls, or money) stays blocked with the fixed code and readback;
- current-method or mixed failures never restart;
- an older stamped method is redriven, and other blocks are not considered;
- the sweep vocabulary.
