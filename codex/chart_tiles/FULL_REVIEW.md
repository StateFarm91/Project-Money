# Complete pre-repair visual inspection

Artifact checkpoint: 8e954b4 (PDF hashes independently verified in committed_pdf_hashes.json). Inspection performed 2026-09-28, source unchanged at inspection.

Coverage: US and UK pages 1-30 rendered with Poppler at 1400px long edge. All 60 pages inspected through six contact sheets inspection/all-{us,uk}-{1,2,3}.png. All 20 non-tile pages additionally inspected individually at full rendered resolution: pages 1,2,3,4,5,6,7,28,29,30 in each terminology. Chart pages 8-27 overview inspected; previously full-resolution sampled US8/17, UK27 and numerical bounds/font measurements of every one of the 40 tiles remain applicable.

Findings:
- Confirmed defect both page2: BLOCKING PINS AND A SURFACE overlaps value. Fixed-width key/value helper neither wraps nor measures key. Exact before PNGs inspection/before-us-02.png and before-uk-02.png.
- Confirmed margin overflow both page29: long AAP source URL exceeds right printable margin. _wrap retains oversized single tokens intact. Exact PNGs before-us-29.png and before-uk-29.png.
- Usability limits: row34 count suffix splits onto page5; page6 contains only finishing continuation; 20 chart pages in 30-page document. No text omission identified. No customer usability validation or physical make proof.
- Tile overview shows coherent global coverage/row numbering/borders, no obvious overlap or clipping. Exact cell coverage comes from existing deterministic tests, not visual inference.
- Poppler reports missing legacy font aliases; observed text uses rendered Helvetica/embedded chart font with no visible missing glyphs. This is not an all-viewer compatibility guarantee.

Approved repair scope from integrator: _Doc.kv in publish/pdf.py, focused regression tests, retain full text and >=9pt. Proposed accompanying _wrap oversized-token repair pending integrator response. No truth, thresholds, statuses or DOC_VERSION changes in worker. Regenerate PDFs and re-inspect all body pages after repair; pre-repair overall document visual verdict is NOT PASS.

## Repair and second inspection

Integrator approved both layout repairs and failure-contract repair. Source changed only publish/pdf.py: kv wraps both columns at original 9pt/10pt with measured height; _wrap splits oversized tokens without deleting characters; infeasible tiling returns None to the original measured PDF_CHART_CELL_BELOW_BRAND_MINIMUM result. It does not raise or pass silently. No floor, CIR, design, claims, or certification status changed.

Commerce failure interpretation corrected: the existing QA test explicitly raises the floor to50mm after its normal catalogue assertions and expects a structured problem containing `mm on the page`. The new exception violated that contract. Direct execution of that entire original test now passes, including all normal catalogue+basket assertions and both raised-floor probes. Seven focused tests pass; exact output layout-test-result.txt. No full commerce rerun claimed.

All60 pages re-rendered. All20 body pages (1-7,28-30 each terminology) individually re-inspected at1400px. Both materials blocks now wrap without overlap; long source URLs remain inside margin. Value wrapping also corrects the long row-definition value on page3. All40 chart page rasters are pixel-identical to the overview-inspected prior version; complete pixel comparison in full_inspection.json. Changed body pages:2,3,28,29 only. After images inspection/after-{us,uk}-{02,03,28,29}.png. No new clipping/overlap seen on inspected surfaces. The prior five full-resolution chart samples remain valid with pixel-identical chart pages.

Both PDFs remain30pages; CIR fingerprint ae84a8e8ec5a; all6930 cells exact with zero duplicates. Re-extracted40 PDF chart transforms remain in margins with minimum9.2960125pt. PDF hashes in result.json now identify repaired PDFs; committed_pdf_hashes.json intentionally identifies prior8e954b4 checkpoint, not the regenerated artifact.

Limits unchanged: no customer make/usability validation, 20 chart pages, orphaned row count across pages4-5 and sparse finishing continuation6. This is a bounded visual/layout review, not a blanket product/certification PASS, accessibility audit, legal-content verification, or every-platform rendering guarantee. Character-split URLs may require joining line breaks when copied from a reader. Other catalogue body PDFs were not visually reviewed in this slice. Root DOC_VERSION3 integration remains authoritative.
