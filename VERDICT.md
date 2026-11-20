VERDICT: DO NOT SHIP 047c2100789f3891f9053c9093c7008d5f9495a6

# ENG-VIS-FLUX full review: FLUX 3 provider integration

- **Unit:** `origin/eng/vis-flux` @ `047c2100789f3891f9053c9093c7008d5f9495a6`
- **Base:** `origin/claude/w6-INTEG3` @ `307c7e6291501238e9c875ad65087128c8d0389b`
- **Merge:** built locally. The only conflicts were in `BUILD_STATE.md`, `DECISION_LOG.md` and
  `scripts/suite_final_segment.txt`, all docs or lists, resolved as a union. No code conflicted.
- **Reviewer:** independent. Reviewed 2026-11-20 UTC.
- **Spend:** no paid BFL call was made. The only BFL host requests were free GETs of
  `api.bfl.ai/openapi.json` and `docs.bfl.ai` pages.

## Blocker (the single reason for DO NOT SHIP)

**B1. `test_vacuity.py` fails, and the failure is new with this branch.** It is a named
required suite.

- **Where it passes and fails:**
  - It fails on the branch HEAD and on the merge.
  - It passes on base `307c7e62` (rc=0).
- **The failing check:**
  ```
  FAIL test_no_new_vacuous_risk_loop_anywhere_in_the_suite
    test_eng_vis_flux.py:223 in test_prices_equal_the_official_rate_card: for ... in by_tier.items()
  ```
- **What is wrong:** the price-parity test asserts inside a loop over a literal dict and never
  proves that the loop ran. The loop over `FC.SOURCES.values()` just below it has the same
  shape.
- **Fix:** add non-emptiness assertions, or a justified `# vacuity-ok:`. For example:
  - `assert len(by_tier) == 5`
  - `assert FC.SOURCES`

  After the fix, re-run `test_vacuity.py` and `test_eng_vis_flux.py`.
- **Size of the change:** about a 2-line change in a test file. It needs no change to the
  integration logic. The rest of this review found the integration sound, so after the fix
  and a green `test_vacuity` this should be a quick re-review.

## Critical checks

| Check | Result | Evidence |
|---|---|---|
| Endpoints, model and request shape cited to official BFL docs with access dates | PASS | See note 1 |
| Nothing invented | PASS, one caveat | See note 2 |
| Contract test uses recorded shapes, no network | PASS | See note 3 |
| Every call goes through the reservation path | PASS | See note 4 |
| Per-agent, per-purpose and monthly ceilings (CA$100 cash cap) | PASS | See note 5 |
| Per-gallery and per-day image caps can only be lowered | PASS | See note 6 |
| Cost recorded per image and per gallery | PASS | See note 7 |
| `test_model_spend_paths`, `test_cert_spend_hosts`; BFL host declared | PASS | See note 8 |
| No call without activation **and** key; key read by name only, never logged | PASS | See note 9 |
| Laura laura-r2-a42aeac7: all three references SHA-validated before conditioning, never modified | PASS | See note 10 |
| Product references come from the CIR | PASS | See note 11 |
| Provenance: model, prompt_version, references with SHAs, receipt id, cost | PASS | See note 12 |
| Recovery before purchase | PASS, with an observation | See note 13 |
| QC: ≥2000 px, valid bytes, aspect ratio; bounded retries | PASS | See note 14 |

### Evidence notes

1. **Citations.** `flux_contract.SOURCES` gives 8 official URLs, each with
   `accessed: 2026-11-20`. I fetched the live `https://api.bfl.ai/openapi.json`:
   - `Flux3ImageInputs` has exactly these fields: `user`, `prompt`, `images` (1–10), `aspect_ratio` (15 ratios + `auto`), `resolution` (`768sq`/`1k`/`1.5k`/`2k`/`4k`/`match_input`), `width`/`height` (256–6256, ≤16,822,272 px, ≤4,194,304 px with references), `safety_tolerance`, `grounding` and `version` (`latest`).
   - It has `additionalProperties: false` and no `seed`.
   - `/v1/flux-3-image` exists.
2. **Pricing and the caveat.**
   - The live pricing page shows tier1k 4.8, tier2k 10 and tier4k 60.7 credits. That matches the rate-card fixture and `BFL3_TIER_USD`.
   - **Caveat (non-blocking):** the live schema gives `safety_tolerance` as 0–7, "the route and organization determine the approved maximum". The contract enforces 0–4, which it cites to the errors page. That page renders client-side, and I could not confirm the 0–4 text from its HTML. The stricter range only refuses more requests, never fewer, so I accept it, but the citation should be confirmed.
3. **No network in the contract test.**
   - The recorded shapes are in `tests/fixtures/bfl_flux3/{openapi_snapshot,response_shapes,pricing_rate_card}.json`.
   - The test stubs `I._post`, `I._get` and `urllib.request.urlopen`. The stubbed `urlopen` asserts that it is only asked for `https://delivery.*`.
   - `flux_contract.py` contains no HTTP client, which `test_cert_spend_hosts` pins as data only.
4. **Reservation path.**
   - `images.generate` builds the request and runs `flux_contract.validate_request` before `reserve_render`. The send happens inside `paid_provider_gate.enforce`.
   - Mutation: disabling `validate_request` was killed.
5. **Existing ceilings.** The image caps are appended inside the same `budget_lock`, after the existing activation, day, month, gallery and run checks, so the lower limit binds. `test_cost_governance_wave2`, `test_w3_spend_gateway_w8` and `test_w5_v0_paid_provider_gate` (52/52) all pass.
6. **Lower-only caps.**
   - `_lower_only` accepts a value only when `0 <= value < constant`. Otherwise the constant stays: 60 images per day, 16 images per gallery, CA$2.50 per gallery.
   - Mutations killed: allowing a raise, the off-by-one in the day count, the off-by-one in the gallery count, the gallery CA$ check without the estimate, and removing the caps entirely.
7. **Cost per image and per gallery.** Each image gets a ledger `cost_entry_id`, `cad` and its provenance `cost_cad`. `gallery_spend()` reports cost per gallery and per provider.
8. **Spend-path suites and host declaration.** Both suites pass on the merge. `flux_contract.py` is in `DECLARED`, `DATA_ONLY` and `FREE_REQUEST_MODULES`, with an HTTP-client ban.
9. **Activation and key.**
   - `Flux3Generator._preflight` calls `flux_provider.require_ready`, which requires both the key's presence (`images.key_for`, a boolean) and an active `generation` activation. This runs before any reservation, and the gateway gate enforces activation again on every send.
   - `env_var_report` and `readiness` expose only the variable name.
   - Mutations killed: removing the readiness activation check, removing the key-presence check, and removing the preflight.
10. **Laura references.** This code predates the branch and the branch does not change it.
    - `image_stages.laura_references` requires exactly 3 references. It compares each sha256 with `canonical.CURRENT_REFERENCE_HASHES` and refuses forbidden hashes.
    - The references are written out byte-for-byte and are never merged or altered.
    - My mutant that removed the `g != w` comparison survived the suites only because a second, independent check also refuses: the references must be the canonical three, in order, as the first inputs. I confirmed that every altered or substituted set is still refused, with nothing sent. This is defence in depth, not a gap.
11. **Product references.** `Flux3Generator._bind` refuses unless the product reference SHAs equal `rel.pattern_ref_sha256s` of the certified release.
12. **Provenance.** `flux_provenance.build` records:
    - model, endpoint, contract version, `prompt_version`, prompt and request hashes;
    - each reference SHA, in order, taken from the body that was sent, with Laura's three marked by fingerprint;
    - `receipt_id` (the task id), `cost_cad`, `cost_entry_id`, `reservation_id`;
    - the output's SHA, size and format;
    - the gallery, the disclosure, and `seed_supported: false`.

    `missing()` makes an incomplete record UNKNOWN.
13. **Recovery before purchase.**
    - `replacement_allowed` re-checks every un-rechecked rejection of the gallery from its kept bytes before a purchase. Open `motif_recovery` rows also block, and an unreadable table refuses. Both audit actions are retention-protected.
    - Mutation: forcing `allowed: True` was killed.
    - **Observation (non-blocking):** the preflight runs before *every* render, not only before replacements. So one RECOVERED rejection blocks all further renders in that gallery until ENG-VIS-GALLERY consumes the recovered bytes. The review request already discloses this. It fails closed and spends nothing.
14. **Generation-time QC.**
    - The listing floor is 2000 px. The check also covers aspect tolerance (0.01), PNG/JPEG, opacity, and corruption.
    - At most 2 free re-fetches are made for corrupt bytes.
    - A rejected render is billed once, its reservation is released at its price, and its bytes are kept.
    - `poll_render` now ends a billed failure as FAILED_BILLED.
    - Mutations killed: the floor lowered to 1000, the aspect check disabled, the re-fetch bound raised, and the price release removed on rejection.

## Mutations (independent; each applied to the merge tree, then reverted)

| Mutant | Result |
|---|---|
| readiness activation check off | KILLED (test_eng_vis_flux) |
| key-presence check off | KILLED |
| generator preflight removed | KILLED |
| image caps bypassed (`refusal = None`) | KILLED |
| lower-only allows a raise | KILLED |
| gallery CA$ cap ignores the estimate | KILLED |
| gallery image count off by one | KILLED |
| day image count off by one | KILLED |
| `replacement_allowed` always true | KILLED |
| re-fetch bound +3 | KILLED |
| QC floor 2000 → 1000 | KILLED |
| aspect tolerance disabled | KILLED |
| `flux_contract.validate_request` skipped | KILLED |
| rejected render's price release removed | KILLED (test_eng_vis_flux) |
| Laura `g != w` SHA comparison removed | SURVIVED; the altered reference is still refused by the second fingerprint check (see note 10) |

## Suites on the merge (`460e737`, local)

Every suite whose name contains flux, image_generation, model_photography, provider or gateway passes.

| Suite | Result |
|---|---|
| test_cc_provider_facade | PASS |
| test_codex_v1_flux_concurrency | PASS |
| test_eng_vis_flux | PASS, 23/23 |
| test_gateway | PASS |
| test_model_photography | PASS |
| test_model_provider | PASS |
| test_provider_accounts | PASS |
| test_provider_trial | PASS |
| test_s2_openai_provider | PASS |
| test_v11_reliability_gateway | PASS |
| test_w3_k12_model_photography | PASS |
| test_w3_laura_cc_providers | PASS |
| test_w3_spend_gateway_w8 | PASS |
| test_w4_flux3generator | PASS |
| test_w4_fluxapi | PASS |
| test_w4_fluxstages | PASS |
| test_w4_fluxtexture | PASS |
| test_w4_fm_provider_table | PASS |
| test_w4_fmbatch1_provider_boundary | PASS |
| test_w4_fmbatch1_provider_health | PASS |
| test_w4_fmbatch1_providers | PASS |
| test_w5_v0_paid_provider_gate | PASS, 52/52 |

The other suites named in the request, with related ones:

| Suite | Result |
|---|---|
| test_model_spend_paths | PASS |
| test_cert_spend_hosts | PASS |
| test_cost_governance_wave2 | PASS |
| test_w4_resume_runner | PASS |
| test_v11_autonomy_timeline | PASS |
| test_w4_fmbatch1_retention_guard | PASS |
| test_etsy_oauth_callback | PASS |
| **test_vacuity** | **FAIL: new (B1). Base passes** |
| test_visual_factory_e2e, test_visual_pipeline_evidence, test_visual_campaign_standard, test_v2_gallery_consistency | PASS |
| test_compiler, test_reverse, test_twin | PASS |
| test_w4_readback_evidence | 22/23. Pre-existing: the same failure occurs on base 307c7e62 |
| test_codex_v1_spend_guard | 20/28. Pre-existing and environmental: it needs pytest fixtures, and base fails the same way |
| test_eng_recovery | Inconclusive: it hit my 900 s timeout under 6-way parallel load, with no failures before the timeout |

`autonomy_map.json` was not regenerated, because this unit touches no autonomy-map inputs and `test_v11_autonomy_timeline` passes.

## To reach SHIP

1. Fix B1 and re-run `test_vacuity.py`.
2. Optionally, confirm the citation for the 0–4 `safety_tolerance` range, or align it with the schema's "approved maximum" wording (caveat in note 2).
