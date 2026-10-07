# Infrastructure gate clearance (W4-GATESI, D-FB-19) — 2026-10-07T02:05Z

Production = Railway project `brambleloop`, service **`brambleloop-os`**, env `production`, deployed commit `fcb982d` (branch `claude/repository-setup-nc9x6o`). Facts below are from GET-only public endpoints and Railway list-projects/list-services. No variable values read; nothing set, deployed or restarted. Machine-readable: `GATE_CLEARANCE_INFRA.json`. CAD at the code's assumed 1.37 USD→CAD; card FX/tax UNKNOWN.

| Gate | Clears in code when | Production now | Repo fix (this branch) | Owner action | CAD | Env vars (brambleloop-os) | Min | Unlocks |
|---|---|---|---|---|---|---|---|---|
| model_provider | latest `model.probe` ok | key present; probe 00:01Z "credit balance is too low" | none needed | Anthropic console → Billing → Buy credits | min US$5 (~CA$6.85); recommended CA$25; code cap CA$100/mo | none (ANTHROPIC_API_KEY present) | 5 | #94 |
| image_vision | latest `vision.probe` ok on a real gallery image | probe 00:03Z same credit 400 | none needed | **same top-up** as model_provider | included | none | 0 | #15 44 61 67 86 88 116 126 218 277 281 304 308 309 |
| image_generation | latest `image.probe` ok | 3 providers credentialled; probe 00:03Z failed "generate() needs a work_dir" — **code defect** | **FIXED**: probe owns a work_dir | deploy this branch (CC package) | ~CA$0.03/probe; BFL credit balance UNKNOWN until probe runs | none | 0 | none (evidence gate) |
| offsite_storage | latest `continuity.offsite_write` full round trip | not configured, no encryption key | **FIXED**: SigV4 region from endpoint host (was hardcoded us-west-004 → R2/other-region buckets would fail) | Backblaze B2: private bucket + app key (read/write/delete, bucket-scoped) + offline-kept passphrase | CA$0 (first 10 GB free; then US$6.95/TB-mo) | BRAMBLELOOP_ARCHIVE_URL, _BUCKET, _KEY_ID, _SECRET, _ENCRYPTION_KEY (opt. _REGION) | 15 | #51 |
| rendered_pages | latest `browser.probe` ok | no worker; all 6 policy sources never checked | **FIXED (partial)**: Help Center article API reader for listing_image_rules + search_guidance; wrong image-rules article corrected | none purchasable: etsy.com/legal = DataDome 403 (re-proven today); a person records the 5 legal sources via POST /api/policy/snapshot each ≤30 days | CA$0 | none | 15 / 30 days | #35 #39 (stay EXTERNAL until person-recorded) |

Sources: [Anthropic credits](https://support.anthropic.com/en/articles/8977456-how-do-i-pay-for-my-api-usage), [Backblaze B2 pricing](https://www.backblaze.com/cloud-storage/pricing).

Wiring requests: B2/FM — narrow `build2.closure.EXTERNAL_GATES["rendered_pages"]` text (help.etsy.com article API answers 200). CC — image_generation and the policy reader need this branch deployed.
