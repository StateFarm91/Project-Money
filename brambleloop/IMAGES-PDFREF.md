# IMAGES-PDFREF — the certified pattern PDF's pages as FLUX 3 reference images

Branch `eng/images-pdfref`, based on `5297dbba` (`origin/eng/images-dialin` did not exist at
start or when this was pushed). Date 2026-11-22 (UTC).

## Why

When asked what they gave FLUX 3 to make the basket images by hand (zero rejections), the
owner said: "PDF pages as images". The autonomous pipeline sent only the four CIR reference
renders (layout, texture, chart, rules), and the fidelity gate rejected its basket frames for
OFF_PALETTE_COLOUR, WRONG_COLOUR_LAYOUT (wall bands) and WRONG_REPEAT_COUNT (sides). This
branch adds the owner's method: pages of the release's **certified premium PDF** go in as
reference images, alongside the CIR renders.

## Field used: `images`, not `input_image`

The brief named `input_image`, `input_image_2` … I re-read the live schema at
`https://api.bfl.ai/openapi.json` on 2026-11-22. **`Flux3ImageInputs` has no `input_image`
field.** References go in `images` (a string or an array, "each is an http(s) URL or base64,
one to 10 total"), and the schema is `additionalProperties: false`. The `input_image` …
`input_image_8` fields belong to FLUX.2 (`Flux2Inputs`). Sending them to `/v1/flux-3-image`
would get a 422, and `flux_contract.ABSENT_FIELDS` already refuses `input_image`. So the pages go in
the documented field: `images[4]` … `images[9]`, base64 inline, after the four CIR renders in
`images[0..3]`. The documented maximum is 10, so at most 6 PDF pages fit.

## Pages chosen (`creative/pdf_page_refs.py`)

Each page is classified from its own heading lines, using PDFium's text layer. The heading lines are
the first short lines (48 characters or fewer) with the running "BRAMBLELOOP · …" header
removed, so a word inside a paragraph never decides a page's kind. Priority order, and the
order the pages are sent in:

| order | kind | heading it matches | why |
|---|---|---|---|
| 1 | `pdf_cover` | page 1 | the finished-product render |
| 2 | `pdf_colour_key` | Materials / WHAT YOU NEED / colour key / palette / COLOUR A | the exact yarn colours |
| 3 | `pdf_chart` (up to 3) | Chart / CONSTRUCTION AND SCHEMATIC / diagram / colour bands | the bands and repeats |
| 4 | `pdf_finished` | THE FINISHED DESIGN / Gallery | the finished piece |
| 5 | `pdf_chart_key` | Chart symbols / chart key | how to read the chart |
| 6 | `pdf_instructions` | Instructions / STEP BY STEP | the colour of each round, named |

The list is filled until there are 6 pages or the request has no free reference slots,
whichever comes first. For `market-basket-small-1.3.0` the result is pages 1, 4, 3, 10, 12
and 11 (cover, materials, schematic, chart, gallery, chart symbols).

Rendering uses the existing PDFium tooling (`visual.contents_frame._pdfium` / `PDFIUM_LOCK`).
Each page is rendered at a fixed 1536 px long side (1187×1536 for US Letter, about 1.8 MP) and saved
as RGB PNG with no metadata. That size is inside the documented 256–6256 px side bounds and
under the 4 MP limit that applies with references. The source is the US-terms edition from
`sale_pipeline.certified_premium_pdfs`, which re-hashes the bytes against the certificate.

## Where the pages are sent

- `Flux3Generator.prepare_references` renders the pages and returns them after the four CIR
  references. Each page is `kind: "pattern_derived"`, `source: "certified_pdf_page"`, with
  label `"<kind>:<page>|slug@version|release"`.
- `Flux3Generator._bind` derives the pages again from the certified PDF and compares them byte for byte, in
  order. A substituted page is refused before anything is sent.
- `image_stages.campaign_references` adds the pages to **no-Laura** requests: the
  product-only flat lay, which is the frame the fidelity gate judges, its side view, and
  product-only styled scenes. Pages only fill free slots. They never displace a reference and
  never trigger the combined-sheet merge. Laura requests already fill their 10 slots and are
  unchanged.
- The prompt's reference map names each page by position (`flux_prompt.build` labels). No
  pinned prompt template changed.

## Provenance

- Every candidate row's `references` now carries each page's sha256 with `kind
  pattern_derived`, `source certified_pdf_page` and its label
  (`image_production._ref_provenance`).
- The stage receipt (`identity_evidence`) adds `pdf_reference_pages`, a list of
  `{position, kind, page, sha256, field}`, plus `pdf_sha256`.
- The `cir_references` gate (`gallery_persist`, `owner_frames`) still measures exactly the
  four CIR renders: it skips `certified_pdf_page` references. **No gate changed.** The
  fidelity gate still judges the output.

## Cache and idempotency

- `pdf_page_refs.pages_for` is keyed by the PDF's sha256 and `RENDER_VERSION`, which names
  the PDFium build. There is an in-process cache, plus an on-disk cache at
  `$BRAMBLELOOP_PDF_PAGE_CACHE` (default: under the temp directory). Each page file is
  verified against its recorded hash, and a torn or tampered entry is rendered again to the
  same bytes.
- `gateway.images` paid-call fingerprints (`_render_fp` and the `_guarded_render` replay key)
  now hash each reference file's **content** (`sha256:<hex>`) instead of its path. Before
  this, the same pages written to another attempt's scratch directory gave a different
  fingerprint, so a redrive could buy the same render twice. Note that a job that started
  before this deploy and is redriven after it computes a fingerprint in the new form. Its
  orchestrator-level recovery (`_recover_generation`, keyed by the operation) still applies.
- FLUX 3 does not charge for references. The per-call price, the CA$2.50 gallery cap, the
  16-image gallery cap, the daily cap of 60 images and the publishing agent's daily ceiling
  are unchanged.
- The BFL host is unchanged: `api.us.bfl.ai`, header `x-key`.

## Tests

New suite: `tests/test_images_pdfref.py`, 12 tests, all passing:

- the request carries the rendered PDF pages in `images`, in a fixed order, after the CIR
  references. The body is the one the real `_request_for` builds, it passes
  `flux_contract.validate_request`, it has no `input_image*` field, and the conditioning
  receipt proves every page is in the body;
- the same PDF gives the same page hashes (two independent renders, byte-identical);
- pages are cached per PDF hash and never rendered twice (memory and disk), and a tampered cache entry is healed;
- the order, the prompt and the request body are identical across scratch directories;
- **no second paid call on a redrive**: the real `paid_calls` guard on a real job, run twice
  with pages in different directories, called the provider once. This test fails if the old
  path-keyed fingerprint is restored;
- the BFL regional host, the `x-key` header, the caps and the per-call price are unchanged;
- a substituted page is refused with nothing sent;
- the provider limit is respected (pages never displace a CIR reference);
- without a certified PDF the request is the four CIR references alone;
- candidate provenance records the page hashes as `pattern_derived`, and the CIR-reference
  gate still counts four.

The results for the touched suites and `test_vacuity` are in the commit message for this
branch.
