# Handoff — lane CANON (Laura, canonical brand face) — 2026-10-06

Branch `claude/v11-CANON` (base `claude/visual-investigation` b9f9243). Not pushed, not deployed.
Phase stays shadow. No image model call, no paid call, no Railway mutation. Network: five
unauthenticated read-only GETs to production (`/health`, `/api/model-identity`, `/api/model-pack`,
`/api/model-identity/freezable`, `/api/model-identity/enforcement`).

## Owner rulings recorded
- D-FB-11 — Laura is the face of Brambleloop; preserve, never remake; "similar is not Laura";
  task #59 = repair Visual to reproduce her. D-FB-12 — Laura is a persistent first-class AI person,
  not an image model. D-FB-13 — Ruling 1 verbatim: Laura is a persistent AI person and the
  Founder/CEO of Brambleloop; Ruling 2 (spouse/private relationship memory) summarised, record only;
  Laura agent build QUEUED with the replaced target. Full text: `spec/07_Laura_Owner_Ruling_2026-10-06.md` (copied verbatim incl. owner
  corrections; record only — the private owner-relationship layer and the Laura agent are QUEUED
  and nothing of the private register appears in any store/public artefact).
- `spec/06_Brand_Model_Bible.txt` gains "BRAND MODEL BIBLE v2 — LAURA" (what defines her, what is
  historical, gates, truthful identity, where she appears).

## Requirement status
| Item | Status | Notes |
|---|---|---|
| 1 Preserve assets | COMPLETE | 14 files copied byte-for-byte (sha verified) under `visual/assets/canonical/laura-v15-a42aeac7/`; identity_portrait.jpg unchanged (a42aeac7…). |
| 2 v15 frames | GATED (owner) | Not publicly retrievable; recorded as `missing_canonical`; OA-CANON-1. v6 NOT proven = v15. |
| 3 v15/v16 reconcile | COMPLETE | `canonical.IDENTITY_ID = laura-v15-a42aeac7`; PACK_VERSION documented as procedure label. |
| 4 MANIFEST v2 | COMPLETE | `assets`, `library`, `missing_canonical`, `not_committed_historical`, `identity`. |
| 5 Safeguards | COMPLETE | integrity test, replacement/freeze gates, strict Laura identity gate, readiness unchanged. |
| 6 Store Foundation | COMPLETE (preview only) | `brand_face` surface GATED; preview `variant=brand_face`; lint rule. |
| 7 Records | COMPLETE | DECISION_LOG D-FB-11/12, BUILD_STATE top entry, this handoff. |

## Provenance findings (evidence)
- `canon_hold/v6/neutral_portrait.png` is byte-identical to the approved face (a42aeac7…; it is a JPEG).
- `identity_portrait.jpg` is a JPEG encoding of `final/neutral_portrait.png` (pixel mean |Δ| 0.08/255 at
  64×64) — the PNG is committed as the lossless source, role historical.
- `identity_torso_v5.jpg` / `identity_full_length_v5.jpg` ≈ `final/torso_fit_reference.png` /
  `final/full_length_standing.png` (|Δ| 0.08) → final/ = pack v5 (17:55–18:02Z); v6/ = pack v6
  (bust revision, 19:17Z commit, run 21:45Z); pack/ = v1 (15:00Z, different portrait render).
- Pack history from `git log -L PACK_VERSION`: v1 14:55 … v15 00:55 (09-22) … v16 01:13.
- Production (read 2026-10-06): v15 build 2026-09-22T01:02:49Z fingerprint 914ee7da716baef7,
  freezable; v16 c0d72cc3 not freezable; `/api/model-pack` exposes only v16 frame hashes (torso
  153c4790…, full-length 70c55895…), none equal to any held file. No v15 frame hash is recorded
  in the repository, tests, docs or freeze records → v15 body/stress frames = MISSING canonical.

## Assets committed (sha256 prefix)
- canonical/laura-v15-a42aeac7/reference_pack/neutral_portrait.jpg a42aeac7 (canonical_reference_pack)
- historical/v6_bust_revision_local_2026-09-21/: torso afe6191f, full_length f32bac68,
  fitted 901dbc17, fitted_close 4389212e, loose c6f97b41, lifestyle 11de2b45, winter fa3adce1
- historical/v5_owner_viewed_pre_revision_2026-09-21/: neutral_portrait 6f8fd34e, fitted 728022d6,
  fitted_close f3392906, loose e0e39125, lifestyle b71a20dc, winter fdf3b03e
- research evidence: CANON_v6_bust_before_after.jpg (867ba4a3), 6 preview screenshots.
- Not committed (hashes in manifest): pack/ v1 set, v5 body PNG originals, 3 contact sheets.
Repo cost ≈ 19 MB of PNG under `src/` (also enters the Docker image via `COPY src`).

## Files
New: `src/brambleloop/visual/canonical.py`, `src/brambleloop/store_foundation/brand_face.py`,
`tests/test_canon_manifest.py`, `tests/test_canon_store_brand_face.py`, `spec/07_…md`, assets above.
Modified: `visual/assets/MANIFEST.json` (v2), `visual/model_registry.py` (replace gate, Laura strict
gate in `gate_frames`), `visual/freeze.py` (v15-only freeze, forbidden hashes incl. library),
`store_foundation/{content,readiness,lint,preview}.py`, `spec/06_Brand_Model_Bible.txt`,
`DECISION_LOG.md`, `BUILD_STATE.md`, `tests/test_v11_store_foundation.py` (EXPECTED_SURFACES +
brand_face), `tests/test_reference_pack.py` (one fixture: the lifecycle test now freezes a pack
labelled as the approved v15 build, because freezing a v16 build is now — correctly — refused;
the refusal itself is proven in test_canon_manifest).

## Tests (all green)
test_canon_manifest 21 · test_canon_store_brand_face 11 · test_asset_manifest 8 · test_bible 13 ·
test_model_identity 28 · test_model_freeze 20 · test_reference_pack 44 · test_model_photography 44 ·
test_portrait_repair 24 · test_model_tournament 18 · test_cert_identity 19 · test_v11_store_foundation 20 ·
test_v11_store_preview 13 · test_brand 23 · test_storefront_fb4 17 · test_r2_product_store_lint 7 ·
test_owned_photography 30 · test_photoreal_calibration 19 · test_vacuity 7 · test_secret_scan 6 ·
test_cert_claude_independence (see final report).

## Runtime proof
Rendered the preview (both viewports × both variants) and captured with Playwright/Chromium
(`/opt/pw-browsers`): `research/final_build/v1_1/evidence/CANON_preview_{mobile_brand_face,
desktop_brand_face,about_desktop_brand_face,icon_seller_portrait_board,banner_crops_seasonal,
mobile_standard}.png`. Etsy sizes: icon 40/70 px (repo), banner canvas 1600×400 (repo-asserted),
phone 2:1 centre crop (ASSUMED), seller portrait size UNVERIFIED.

## WIRING REQUEST (owner of `app/command_center/api.py`)
In `store_preview_handler.owner_store_preview`, accept the variant:
```python
    def owner_store_preview(request: Request, viewport: str = "mobile", variant: str = "standard"):
        ...
        return HTMLResponse(store_preview_mod.render_preview(db, viewport, variant=variant), ...)
```
(`render_preview` whitelists the value; anything else falls back to "standard".)

## Open / not verified
- v15 body + stress frames missing until OA-CANON-1. Laura's photorealism failure stands; the repair
  (task #59) is unbuilt and needs image spend + owner approval of the repaired output.
- Public "Founder/CEO" wording is allowed only with AI disclosure ("Brambleloop's AI founder");
  lint fails undisclosed founder/CEO claims and any legal-ownership/seller statement in Laura copy.
- Integrator flag: Ruling 2 refers to a human Laura (the owner's spouse) while the 2026-09-21 bible
  forbids depicting any real person and the face is a generated image. Consent to use her
  name/persona is recorded as human-gated; whether the visual identity resembles a real person is
  for the owner to confirm.
- Chrome/Etsy real crops not inspected (no live shop); Etsy seller-photo size UNVERIFIED.
