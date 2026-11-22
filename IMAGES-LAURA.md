# IMAGES-LAURA — the owner's two-step method, step 2 (Laura frames)

Branch `eng/images-laura`, based on `5297dbba` (`origin/eng/images-pdfref` did not exist when
this was fetched on 2026-11-22). Not merged and not deployed.

## The owner's method

1. Send FLUX 3 the pattern PDF pages as references. This makes the **product** image. Another
   session builds this step (`eng/images-pdfref`).
2. The owner, verbatim: *"Then when it made the product, I sent the product with Laura's
   identity images."* **This branch builds step 2.**

## What changed

**Request builder** (`creative/image_stages.py`):
- `owner_method_references` and `owner_method_lifestyle` (`OWNER_METHOD = "owner_two_step/1"`) build a request with exactly
  these reference inputs, in this fixed order:
  1. Laura face, `neutral_portrait` `a42aeac7…`;
  2. Laura torso, `torso_fit_reference` `afe6191f…`;
  3. Laura full length, `full_length_standing` `f32bac68…`;
  4. the **accepted product frame**.
- That is 4 images, within FLUX 3's documented maximum of 10.
- No pattern references, identity anchor, edit base, room image or outfit image is sent.
- The outfit already assigned to the listing goes into the prompt.
- The canonical three stay first. That keeps the existing check in `_run`, "the canonical three lead", unchanged.
- The request is gated on the flat lay's fidelity PASS through the existing `_require_flat_lay_pass`.

**Generator** (`creative/flux3_generator.py`):
- Declares `accepts_owner_method`.
- A Laura role handed an `accepted_product_frame` goes through `_owner_method`. Before any reservation, it checks that the frame's bytes hash to the anchor this release accepted, and that the anchor's fidelity verdict is still PASS. Anything else is refused.

**Orchestrator** (`visual/image_production.py`):
- `_accepted_product_frame` returns this run's product anchor:
  - only if its `technical_status` is PASS;
  - it is found by its stored sha256;
  - its bytes are re-read from the artifact store and must hash to that sha256;
  - it must have no negative owner decision.
- `lifestyle_generation` and `remaining_roles` now **block before any call** when no product frame is accepted. This holds for every generator, however the job arrived.
- Under the owner method, every Laura role (lifestyle, then scale and colour context) gets:
  - the canonical three, from `laura_refs()`, byte-verified against `canonical.CURRENT_REFERENCE_HASHES`;
  - the accepted frame;
  - the listing's outfit. If it has no outfit, the role is refused.
- Stage A (the identity anchor) is **skipped** under the owner method, so no unused paid intermediate is bought.
- **Idempotency by input hashes.** The replay key is `_owner_operation`, made of:
  - run, stage and role;
  - `input_digest`, which is the sha256 of the method, the four image hashes in order and the outfit id.
  - It deliberately does **not** include the restart epoch. A capability or daily-ceiling redrive therefore recovers the frame it already bought.
  - Repairs add the round and a digest of the repair to the key, so they are still separate, counted calls.
  - The caps are unchanged: `MAX_ATTEMPTS_PER_ROLE`, `MAX_GENERATION_CALLS`, the spend plan and the paid-provider gate.
- **Provenance.** Each Laura candidate stores `checks._reference_provenance`:
  - method and `identity_id` (`laura-r2-a42aeac7`);
  - each image's position, role and sha256;
  - the accepted product frame's candidate id and sha256;
  - Laura's three hashes by frame;
  - outfit id and `input_digest`.

**Unchanged:**
- the identity gate (`identity_gate`, `CG.evaluate`);
- the Product Truth and fidelity gates;
- Laura's canonical set: no file and no hash was touched;
- `PUBLICATION_APPROVED`;
- every spend ceiling.

## One correction to the brief

The brief said `input_image` fields. In FLUX 3 Image's schema the reference field is
**`images`**. I re-read `https://api.bfl.ai/openapi.json` on 2026-11-22: `Flux3ImageInputs.images` takes a string or an array, "one to 10 total", with `additionalProperties: false`. `input_image` is FLUX.2's field. The repository's contract, `gateway/flux_contract.ABSENT_FIELDS`, already refuses it, because sending it would get a 422. The builder therefore sends `images`. A test decodes the real `_request_for` body and pins two things: `images` is exactly the canonical bytes and then the product frame bytes, and the body has no `input_image`.

## Tests

`tests/test_images_laura.py`, 6 tests:
- The lifestyle request carries the accepted product frame plus the canonical Laura images, in a deterministic order. Provenance is recorded and the outfit is carried.
- Laura's references are byte-identical to the canonical set.
- Nothing runs before a product frame is accepted. This covers a blocked run, and a job delivered to an in-flight run whose only frame FAILed.
- The generator refuses a product frame that is not the accepted one, or whose fidelity is not PASS. The FLUX 3 body is `images` in order.
- A redrive makes no repeat paid call. This covers a duplicate delivery and a restart into a new epoch. A mutant that keys the operation per call is killed.
- The operation keys follow the input hashes.

Run: `cd brambleloop && SUITE_REGISTRY=0 SUITES="<touched suites> tests/test_vacuity.py" JOBS=$(nproc) bash run_tests.sh`. The results are below.

RESULTS_PLACEHOLDER

## Not done or not verified

- No live FLUX 3 call was made, and nothing was spent.
- Step 1 (the PDF-page product frame) belongs to `eng/images-pdfref`. When that lands, its accepted product anchor is what this step consumes. Merge it and re-run these suites.
- The owner method applies to normal runs only. Experiments (`exp`) keep their recorded plans.
