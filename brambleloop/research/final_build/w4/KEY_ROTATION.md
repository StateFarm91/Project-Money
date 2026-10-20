# Rotating a provider key (owner guide)

Read this on a phone. A rotation takes about five minutes and costs nothing.

**How keys work here.** Railway is the only place the keys are kept. Every image and vision
call comes from a backend job running on Railway. Claude Code never runs those jobs and never
holds a key. The Command Center never shows a key. The most it shows is a **fingerprint**: the
last 4 characters and a short, domain-separated sha256 prefix, enough to tell one key from another.

| Provider | Railway variable | Where the key is made |
|---|---|---|
| Black Forest Labs (FLUX 3 images) | `BRAMBLELOOP_IMAGE_KEY_BFL` | dashboard.bfl.ai → API Keys |
| Anthropic (Claude vision and text) | `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |

## When to rotate

- A Command Center card says the key was **rejected**.
- You think a key may have been seen by someone else.
- Routine hygiene, whenever you like.

## Steps

1. **Create the new key** at the provider (see the table). Copy it. Do not delete the old key
   yet.
2. **Set it in Railway:** open the project → the Brambleloop service → **Variables**. Edit the
   variable from the table and paste the new key over the old value. Save.
3. **The service restarts** by itself so it can pick up the new value. Wait about two minutes.
4. **Check it in the Command Center:** open **Home → Run checks now → Provider credentials →
   Run now** (this is the "Check now" button), then confirm your passphrase. A minute later,
   open **Provider keys (Railway)** on the same card. For the provider you changed, check:
   - the status is **OK**;
   - the fingerprint's last 4 characters match the end of the new key you copied.
5. **Delete the old key** at the provider. Do this only after step 4 shows OK. If you delete it
   first and the new key was pasted wrongly, image or vision work stops until you fix it.

## What the statuses mean

| Status | Meaning | What to do |
|---|---|---|
| OK | The key is set, authenticates and the provider accepts the call. | Nothing. |
| MISSING | The Railway variable is not set. | Do steps 1 to 4. |
| REJECTED | The provider refused the key. | Rotate it: steps 1 to 5. |
| INSUFFICIENT_CREDIT | The key works but the account balance is too low. | Add credit at the provider. Nothing changes in Railway. |
| PERMISSION | The key works but the model or feature is not enabled for it. | Enable it at the provider, or use a key from an account that has it. |
| OUTAGE / RATE_LIMITED | The provider is down or busy. | Nothing. You are told only after 3 failed checks in a row. |
| UNKNOWN | The answer could not be read. This is never treated as OK. | Run the check again. If it repeats, look at the card. |

## How it is checked (cost: CA$0)

The check runs daily, and whenever you tap **Check now**. It uses only calls the providers
document as free:

- **BFL:** `GET https://api.bfl.ai/v1/credits` with the key. This proves the key works and
  reads the balance. A balance below one 2k image (10 credits, US$0.10) shows as
  INSUFFICIENT_CREDIT. BFL has no free way to check whether a given model is enabled, so a
  PERMISSION problem shows up only on a real render.
- **Anthropic:** `POST /v1/messages/count_tokens` with a one-pixel image. Token counting is
  free. This proves the key works and that the model accepts images. A free call cannot prove
  the account has credit. Credit is therefore read from the latest real call (the six-hourly
  model probe). If that call was refused for credit, the status is INSUFFICIENT_CREDIT.

You get one card when a key moves into MISSING, REJECTED, INSUFFICIENT_CREDIT or PERMISSION,
and one card when it recovers. Repeat checks do not send more cards.
