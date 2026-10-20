# Overnight handoff, 2026-10-20 (as of 10:55Z)

## 1. Production

- **Build:** b931d17, deployed 2026-10-20 at 03:49Z with owner approval. SHADOW. The worker is alive with 0 restarts.
- **/api/verify:** RED on `no_unexpected_dead_letters_in_24h`. There are 3 `intel.gallery_analysis` read timeouts (last at 08:06Z), so the 24-hour window for #195 is broken. The fix is in progress on CLOSE5.
- **Spend:** October so far is CA$64.72 of the CA$100 ceiling.
- **Known production bug:** `GET /api/departments` returns 500. It is fixed on CLOSE5 and awaits the next deploy.

## 2. The b931d17 deploy

- A fresh backup was taken and verified by a restore (133 tables, 142,931 rows).
- `deploy.sh` pushed the release, and the readback passed 10 of 12 checks. The 2 failures were transient: the worker was still starting, and old-build dead letters had not yet cleared.
- The deploy is recorded in DEPLOYED_HISTORY (INTEG3 364ade0).
- **Backup volume:** resized to 4 GB with owner approval. 682 MB are free and all 9 dumps are kept.

## 3. Engineering completed (branches, all pushed, none deployed)

| Branch | Head | Contents |
|---|---|---|
| w4-FIRSTSALE | cc0c54e | Durable PDF delivery (Postgres, byte-identical re-render), purchase→download rehearsal 10/10, Etsy image-upload readiness 69/69, first-sale view, taxonomy matcher (UNKNOWN until real data), retention, alt-text ≤250 characters |
| w4-VISNEXT | 0beb522 | Vision-judge adapters, lifestyle region detector, restart of blocked runs, approved frames → ListingAsset, CC gallery card and wardrobe editor, learning records, outfit reference after canonical 3, generated-frame provenance, F-852 verified-exception gate (D-W4-F852-AMEND), six-reference baseline harness, owner-only production experiment command (`POST /api/cc/experiments/{id}/run`, step-up, caps, idempotent, publication refused, key-leak test) |
| w4-CLOSE5 | 27fb1d4 | Webhook concurrency gate (R1), grid_tournament token cut (≈CA$13 → ≤CA$2.1 per run), 39 FM rows closed on production evidence, 6 dev-proven, 4 downgraded and re-closed, `/api/departments` 500 fixed |
| w4-VISNEXT2 | 8404672 (WIP) | Stage A identity anchor, stage D edit base, Cloudline experiment definition |
| w4-FLUXLIVE | 7886f58 | Frozen seven-reference live test plan |
| w4-BRANDRULE | 55083da | D-W4-LAURA-OUTFIT, D-W4-LAURA-FLUX3, D-W4-F852-PROPOSED/AMEND (+ traceability), experiment records |
| w4-INTEG4 | 7f6dbe8 (in progress) | Next release candidate: FIRSTSALE + VISNEXT merged; CLOSE5 pending its timeout fix |

## 4. Board

- **Final Master:** 421 verified (388 at the 10-19 recount). Launch-critical: 365 complete, 118 gated, 7 open.
- **Build 2:** shown as 198 verified on the CLOSE5 branch. That count is affected by modules changed since deploy, which are marked dev-proven, and is re-evaluated after the next deploy (225 at the 10-19 recount).

## 5. Release candidate

- Not frozen yet.
- INTEG4 is waiting for CLOSE5's gallery_analysis timeout fix.
- After that: full suite, independent security review (including the experiment command), deploy guard, rollback rehearsal.

## 6. FLUX live test

- **Not run.** Nothing was spent on it.
- The attempts with keys pasted in chat were blocked by the permission system or failed (OCR, 403). Those keys must be rotated.
- The network-secret session got 422: the secret format needs re-saving as the bare key.
- The Railway route (owner-only experiment command) is built and arrives with the next release.

## 7. First-sale blockers

1. Etsy category: company work. The next deploy plus one daily refresh, then the live verifier.
2. Vision review funding.
3. A physical sample.
4. Go-live decision and draft-publication grant.
5. Etsy listing-image policy reading.

## 8. Owner actions

1. Rotate the two keys pasted in chat.
2. Re-save the `api.bfl.ai` Network secret as the bare key, OR wait for the next release and use the experiment command.
3. Read Etsy's Listing Image Requirements page.
4. Approve vision-review funding.
5. Physical sample.
6. Approve the next release SHA when presented.

## 9. Next steps

1. CLOSE5: gallery_analysis timeout fix.
2. INTEG4: merge, freeze, certify, then present the SHA.
3. VISNEXT2: staged method and Cloudline harness.
4. After deploy: taxonomy live verifier, then the #195 window restarts.
