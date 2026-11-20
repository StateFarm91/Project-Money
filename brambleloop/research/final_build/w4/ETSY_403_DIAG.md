# Etsy API 403: diagnostic (2026-10-12)

**Conclusion.** Etsy itself refuses the app credential. The most likely cause is that the app's API key was not re-activated when the app was reinstated, or the shared secret no longer matches. Two code-side causes are ruled out: the 403 started with no deploy and the code unchanged, and the header matches Etsy's documented format. Etsy's own error text from production has never been captured, because 0417f35 discards it. The deployed build therefore cannot yet distinguish a deactivated key from a wrong secret.

What I did:
- Production was read through its public `/api/*` endpoints and Railway (deployment metadata and logs only).
- No variable values were read and no real-key request was made.
- Two unauthenticated requests were sent to the ping endpoint at 2026-10-12T02:03Z: one with no key, one with an obviously fake key.

## 1. Which endpoint returns 403
`GET https://openapi.etsy.com/v3/application/openapi-ping`. This is `etsy_public.BASE` + `ALLOWED["ping"]` at 0417f35, and it matches the pinned spec's `servers[0]` (`https://openapi.etsy.com`, sha256 b993d52f…).

Probe history from `/api/audit?action=etsy.probe`:
- OK every 6 hours from 2026-09-19 to 2026-10-07T06:00Z, with application_id 1516181443672.
- 403 at every probe since 2026-10-07T12:00Z.
- Last probe: 2026-10-11T12:00:41Z.
- No probe has run since. The thrash backoff suspended it, and the 16:25Z redeploy has not been tested.

## 2. The body
- **"…requires x-api-key as keystring:shared_secret; check ETSY_SHARED_SECRET" is our code's hint, not Etsy's message.** It comes from `etsy_public._request_with_retries` at 0417f35 (`hint = (" — Etsy v3 requires x-api-key as keystring:shared_secret; check …")`). That build raises `ReadFailed` without the response body, so **Etsy's actual message from production was never recorded.** Railway deploy logs around 12:00Z and 02:04Z contain only access lines.
- Etsy's bodies, captured from here:
  - With no key: `403 {"error":"Invalid API key: should be in the format 'keystring:shared_secret'."}`
  - With a fake `keystring:secret`: `403 {"error":"API key not found or not active, or incorrect shared secret for API key."}`
  - Response headers: `server: Apache`, `x-etsy-request-uuid`, `content-type: application/json`.
- Production always sends `key:secret`: the key is trimmed, there is one colon, and `/api/etsy` reports both values set. So the production 403 is almost certainly the second message. That is an inference, not a reading.

## 3. Meaning
Etsy gives a single message for "API key not found", "not active" and "incorrect shared secret". There is no separate rate-limit 403: rate limits are 429, and the probe does not retry a 403.
- Not rate limiting.
- Not a scope or permission problem: `ping` needs only `api_key`.
- Not malformed: that would be the first message.
- It means **app or key inactive (suspension) or a wrong secret.** The timing (working → refused at 2026-10-07 12:00Z, with no deploy and unchanged code) fits the ban.

## 4. Minimal public request
The unauthenticated ping returns the "missing key" body above. The fake-key ping returns "not found or not active". Etsy's endpoint is up, and it distinguishes a malformed header from an inactive or wrong key. The real key could not be tested from here, by rule.

## 5. Dashboard vs API
They disagree. The dashboard shows the app under **Personal Access**, not Banned, but the key is still refused.
- Etsy's documentation says Personal Apps are "subject to Etsy's review" and "go through a deeper review process": https://developers.etsy.com/documentation/
- A new or reviewed key is shown as "YOUR KEY IS NOT YET ACTIVE … We will be reviewing your key shortly": https://github.com/etsy/open-api/discussions/1060
- So "Personal Access" is an access *tier*, not proof that the key is *active*.
- For a single-shop seller, Etsy now recommends a **Seller App**: "approved within minutes". That is an owner decision and needs a new key; nothing here creates one.

## 6. Configuration and formatting
- Deployments: 0417f35 at 13:58Z, 16:06Z and **16:25Z** on 2026-10-11. Earlier, fcb982d ran from 2026-09-25 to 2026-10-11, covering both the success period and the onset of the 403.
- A Railway redeploy picks up the variables current at deploy time. **No probe has run since the 16:25Z redeploy**, so whether it picked up corrected values is unverified.
- Code at 0417f35 reads `ETSY_API_KEY` and `ETSY_SHARED_SECRET`, `.strip()`s both, and sends `x-api-key: <keystring>:<shared_secret>` exactly as https://developers.etsy.com/documentation/essentials/authentication specifies.
- The host is the spec's server. The docs' request-standards page names `https://api.etsy.com/v3/`, but `openapi.etsy.com` returns Etsy's own JSON errors and served this app for 18 days.
- Gap: the `taxonomy` and `etsy` modules also accept `ETSY_KEYSTRING`, but the ping does not. The probe now reports whether that variable is set or differs (booleans only).

## 7. Is separate reactivation needed?
Very likely. The closest precedent is Etsy's 2022-08-16 mass key deactivation. Etsy staff wrote: "an errant script ... deactivated a lot of keys", then "All apps and keys should now be restored", and asked affected developers to "reach out to developers@etsy.com". Source: https://www.valueaddedresource.net/etsy-third-party-integration-problems-pirateship-more/ (published 2022-08-16).

Etsy has no published procedure for reinstating a banned app. Without one, developers@etsy.com is Etsy's stated contact for key problems.

## Code changes (`claude/w4-ETSY403`, from w4-INTEG2; not deployed)
- **Already on INTEG2 (W4-ETSYCOMM):** Etsy's refusal text is stored on the probe row as `etsy_error`, with credentials removed.
- **New:** a refused probe also records `credential_shape`, booleans only:
  - each value is alphanumeric;
  - colon, quotes or inner whitespace inside a value;
  - surrounding whitespace was trimmed;
  - `ETSY_KEYSTRING` is also set, or differs.

  This separates a paste error from an Etsy-side state without revealing a value. Test: `tests/test_w4_etsy403.py`.

## Smallest next action
1. **Owner, about 2 minutes:** on etsy.com/developers/your-apps, check whether the app's key says active, or "not yet active" / pending review.
   - If it is pending or inactive, send the email below.
   - Re-copy the shared secret into Railway only if Etsy shows a different one; then redeploy and press Re-check.
2. **Email to developers@etsy.com.** Subject: "Reinstated app's API key still refused (403)".

   > Hello, my Open API v3 app (application id 1516181443672, shop BrambleloopStudio) was suspended over an overdue
   > payment, which has now been paid. The app now shows under Personal Access in Your Apps, but every request,
   > including GET /v3/application/openapi-ping, returns 403 "API key not found or not active, or incorrect shared
   > secret for API key." This has happened since 2026-10-07 12:00 UTC; the same key worked from 2026-09-19 to
   > 2026-10-07. Could you please reactivate the app's API key, or tell me what is still required? I use it only for
   > my own shop. Thank you.
3. **After deploying INTEG2 (or this branch),** the next probe records Etsy's own words and the credential shape. That settles "inactive" vs "secret mismatch" without anyone reading a secret.
