# Controlled visual experiments: how to authorize and run them (owner guide)

Read this on a phone. The whole process takes about a minute: Authorize once, then Run.

## What an experiment is

An experiment is a frozen, versioned recipe: the exact references, the exact prompt, the model, the size and two spending caps. Every
experiment lives in the repository under `brambleloop/src/brambleloop/experiments/definitions/<id>/`.

The first one is **`exp-2026-10-20-wrap-7ref`**, the Reading Nook Cable Wrap:

- **References**, seven of them, sent in this order:
  1. Laura's face (a42aeac7)
  2. Laura's torso (afe6191f)
  3. Laura full length (f32bac68)
  4. your wrap layout (3f737a08)
  5. your cable stitch structure (10d013b8)
  6. your construction rules (3638b3a5)
  7. a crochet texture reference (bc88ed04)
- **Prompt:** the frozen prompt, sha256 99f0f1a8….
- **Model:** FLUX 3, 2048×2048.
- **Caps:** generation up to **CA$5.00**; vision checks up to **CA$1.00**, kept separate.
- **Retries:** at most one, and only if the provider has an error. A retry is never used just to try for a better-looking image.

Everything an experiment makes is labelled **EXPERIMENT — UNCERTIFIED — NOT FOR PUBLICATION**. It can never be published: the
publication paths refuse it.

## Before you start

The worker needs `BRAMBLELOOP_IMAGE_KEY_BFL` set in the Railway environment. The vision checks also need
`ANTHROPIC_API_KEY` and the `image_vision` capability; without them, those checks read UNKNOWN. The keys never pass through
the Command Center, and they are never stored or shown.

## 1. Authorize it (once per definition)

1. Open the Command Center and sign in.
2. Go to **More → Images → Controlled experiments**.
3. Check that the experiment says **inputs verified**. If it says **inputs drifted**, stop: a file or the prompt changed.
4. Tap **Authorize** and confirm your passphrase (the step-up).
   - This records an authorization id (`auth-…`) bound to this exact definition (its sha256) and to its caps.
   - You can ask for lower caps, but never higher ones.

If the definition file changes later, the authorization no longer matches it, and the experiment must be authorized again.

## 2. Run it

1. Tap **Run** and confirm with the step-up.
2. One job is queued. Tapping Run again while it is queued or running returns the same job; it does not start a second one.
3. The job then works through these steps:
   1. It checks every reference file and the prompt against their fingerprints. Any difference means nothing is spent.
   2. It checks the generation cap, and then makes one FLUX call. Every existing agent, monthly and provider ceiling also
      still applies.
   3. It stores the original image bytes in the database, together with the receipt, the fingerprints and the real cost.
   4. It runs the independent checks: identity, body proportions, outfit, anatomy, realism and product fidelity.

## 3. Look at the result

Under the experiment, tap **Open** on the run. The gallery card shows:

- the image, with the EXPERIMENT banner;
- the references sent, in order;
- what was spent against each cap;
- the provider receipt;
- every check result. UNKNOWN is listed as UNKNOWN and is never treated as a pass;
- the authorization id.

Publication shows as **not available**, always.

## Adding another experiment later

1. Commit a new definition folder: `definition.json`, `prompt.txt` and `refs/`.
2. Authorize it in the Command Center.

No code change is needed.

## Production acceptance runbook (after deploy)

Do these in order, from your phone. All the spending comes from the one experiment run, which
is capped at **CA$5 for images** and **CA$1 for vision**. Each cap is enforced in code before
any call is made.

**A. Credentials are healthy.**
Go to **Home → Run checks now → Provider credentials → Run now** and confirm with your
passphrase. Then open **Provider keys (Railway)**.
- *Pass:* both FLUX 3 / BFL and Anthropic show **OK**, with a fingerprint.
- *Fail:* anything else. Follow the card's exact action, or see `KEY_ROTATION.md`. Stop here
  until both are OK.

**B. One authorized run of the frozen 7-reference experiment.**
Go to **More → Images → Controlled experiments** and find `exp-2026-10-20-wrap-7ref`.
- Check that it says **inputs verified**.
- Tap **Authorize**, then **Run**, confirming your passphrase each time.
- *Pass:* exactly one job. Tapping Run again returns the same job.
- Afterwards the receipt shows one FLUX call, and generation spend is at most CA$5.

**C. 2048×2048.**
Open the run's card and the image.
- *Pass:* the receipt and the stored image are both 2048×2048. Any other size is a fail.

**D. Vision review.**
On the same card, look at every check: identity, body proportions, outfit, anatomy, realism
and fidelity.
- *Pass:* every check has a recorded result, and vision spend is at most CA$1.
- UNKNOWN is listed as UNKNOWN and never counts as a pass. If a check is UNKNOWN because
  vision is closed, note it. That is a finding, not a pass.

**E. The results are in the Command Center.**
The card shows the authorization id, the references in order, the costs against both caps,
the provider receipt and the EXPERIMENT banner.

**F. The run survives a restart.**
In Railway, restart the service, which is the same as a redeploy. Then reopen the card.
- *Pass:* the same image (same sha256) and the same results are still shown. The bytes are
  kept in the database, not on the container's disk, so a restart does not lose them.
- *Pass:* no second FLUX call appears. A restart during a run either resumes from the stored
  image or settles the run as "billing unknown", counted once at its reservation. A paid call
  whose outcome is unknown is never sent again.

**G. Publication is refused.**
- *Pass:* on the card, publication shows **not available**.
- *Pass:* no listing, export or Etsy payload can use this image.
- *Pass:* nothing appears in the store.
