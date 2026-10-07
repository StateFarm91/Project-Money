# Owner deploy checklist — Command Center + production catch-up

All values are entered by the owner. No secret is ever printed, stored in the repo or sent to Claude.
Where: Railway → project → service **brambleloop-os** → **Variables** → *New Variable* (paste name, paste value) → *Deploy*/apply.
Railway applies variable changes with a redeploy of the same build; setting them **before** approving the deploy means one rebuild only.

| # | Railway variable | Where you get the value | Secret? | Restart/redeploy |
|---|---|---|---|---|
| 1 | `BRAMBLELOOP_OWNER_PASSPHRASE_HASH` | On your own computer, in a checkout of the repo: `cd brambleloop && PYTHONPATH=src python3 -m brambleloop.app.command_center.auth hash` → type your chosen passphrase twice (12+ characters) → it prints `BRAMBLELOOP_OWNER_PASSPHRASE_HASH=<hash>`; copy only the part after `=`. Never paste the passphrase itself anywhere. | yes (hash) | applied on next deploy |
| 2 | `BRAMBLELOOP_OWNER_TOTP_SECRET` | Generate a base32 secret (e.g. `python3 -c "import base64,os;print(base64.b32encode(os.urandom(20)).decode())"`), add it to your authenticator app as *Brambleloop* (manual key, time-based, 6 digits, 30 s), then paste the same secret here. | yes | applied on next deploy |
| 3 | `BRAMBLELOOP_TRUSTED_PROXY_HOPS` | literal `1` | no | applied on next deploy |
| 4 | `BRAMBLELOOP_PUBLIC_ORIGIN` | literal `https://brambleloop-os-production.up.railway.app` | no | applied on next deploy |
| 5 | `BRAMBLELOOP_ARCHIVE_URL` | Backblaze → *Buckets* → your bucket → **Endpoint**, written as `https://s3.<region>.backblazeb2.com` | no | applied on next deploy |
| 6 | `BRAMBLELOOP_ARCHIVE_BUCKET` | the bucket name you create (e.g. `brambleloop-continuity`) | no | applied on next deploy |
| 7 | `BRAMBLELOOP_ARCHIVE_KEY_ID` | Backblaze → *Application Keys* → *Add a New Application Key* (restricted to that bucket, Read and Write) → **keyID** | yes | applied on next deploy |
| 8 | `BRAMBLELOOP_ARCHIVE_SECRET` | the same new key → **applicationKey** (shown once) | yes | applied on next deploy |
| 9 | `BRAMBLELOOP_ARCHIVE_ENCRYPTION_KEY` | a long passphrase you create; **also keep a copy offline** (without it backups cannot be restored) | yes | applied on next deploy |
| — | `DATABASE_URL` | already set — only confirm it exists on the web, worker and scheduler services | yes | none |
| opt | `BRAMBLELOOP_PRIVATE_MEMORY_KEY` | optional: `python3 -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`; leave unset to keep Laura's private memory off | yes | applied on next deploy |

**Backblaze account steps (CA$0 up to 10 GB):** sign in / create a free account → *Buckets* → *Create a Bucket*: name as #6, **Private**, default encryption off (the app encrypts), Object Lock off → note its Endpoint (#5) → *Application Keys* → new key restricted to that bucket with Read and Write → copy keyID (#7) and applicationKey (#8). ~15 min.

**Anthropic credits (separate from Claude development usage):** console.anthropic.com → sign in to the account whose API key production uses → *Settings* → *Billing* → *Buy credits* → **US$18 ≈ CA$25** (minimum US$5 ≈ CA$6.85). No variable change. Unlocks in production: the model gateway (`model_provider` gate: Laura's answers, research and copy jobs that need a model), image vision (`image_vision` gate: the creative taste check for 11 catalogue products + 8 candidates, competitor gallery analysis stalled since 2026-09-24, visual QA). Spend stays capped by code at CA$100/month; phase stays shadow. ~5 min.

**After the deploy (owner, ~15 min, every 30 days):** record the 5 etsy.com/legal policy pages via the Command Center (`POST /api/policy/snapshot`); etsy.com blocks automated reading.

Total owner time ≈ 50 min. Maximum cost: CA$25 one-off (credits) + Railway usage delta UNKNOWN (repo estimate ~CA$7/month, hard ceiling CA$20/month) + CA$0 Backblaze.
