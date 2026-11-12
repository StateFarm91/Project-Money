# WS4: Standing Autonomous Publishing Policy (design)

Status: DESIGN ONLY. Nothing here exists yet. No code was changed and no tests were run.
Read against checkout `/home/user/bl-runs/wt-cert9` at commit `5f4a175e`. Every path is relative
to `brambleloop/src/brambleloop/` unless it says otherwise.

---

## 0. Summary

Today one owner decision authorises one product. The decision is a `publication_authority`
grant sealed with the ops token and bound to `slug@version`, the release, the CIR digest, the
sent fields and the evidence packet. It lasts 24 h. This design adds one new authority:

1. **Standing Policy (SP).** The owner approves a set of operating boundaries once, signs it
   under a Command Center step-up, and activates it in a second, separate act. The record is
   signed with a policy key that only the web process holds, and kept on its own hash chain.
2. **Policy Issuer (PI).** A protected process holds a separate issuer key. For each product,
   it re-derives every fact from the database and from deterministic recomputation. If the
   product is inside the SP, the PI issues a **Standing Execution Grant (SEG)**. A SEG is
   single-use, lasts 15 minutes and is bound to the product content.
3. **The publish path accepts a SEG wherever it accepts an owner grant today**
   (`publication_authority.resolve`), and **nowhere else**. Every existing check still runs:
   the kill switch, the phase chain, the parity and release gates, the payload, PDF and image
   binding, both revalidation stages and the client-side `OwnerGrant.refusal`.
4. **A product outside the SP is held** as one deduplicated owner card that leads to today's
   per-product approval. A stop condition **suspends** the SP automatically. Narrowing is
   always allowed. Widening is possible only through a new owner-signed SP version, and only
   up to ceilings set in code.

Two findings from reading the code shape the design:

* **F-A (existing weakness, not created here).** `publication_authority._seal`
  (`ops/publication_authority.py:57-61`) and `activation_authority._seal`
  (`ops/activation_authority.py:37-41`) are HMACs under `BRAMBLELOOP_OPS_TOKEN`. Verifying a
  grant recomputes that HMAC (`publication_authority.py:450-452`,
  `core/sealed_chain.py:197-202`), so every process that verifies a grant can also mint one.
  The worker verifies at `runtime/pipeline.py:2204` and `:2242`, and at the client in
  `integrations/etsy.py:180-183`. The worker can therefore mint a per-product owner grant
  today. The storefront family already solved this with Ed25519 and a public verify key
  (`ops/storefront_authority.py:46-55, 125-152`; the `GrantLedger(verify=...)` hook is at
  `core/sealed_chain.py:173-181`). **WS4 must not copy the HMAC pattern.** WS4-0 below moves
  the publication family to asymmetric verification first.
* **F-B (deployment limit).** `BRAMBLELOOP_EMBEDDED_WORKER` defaults to `1`
  (`app/runner.py:16, 529`; `ops/storefront_authority.py:94-101`), so job handlers run inside
  the web process. Inside one Railway service, nothing separates a key from code running in
  the same container. The design therefore has two modes. In **Mode S** (single service,
  today) the SP can be recorded and evaluated in shadow, but **no SEG can be issued**. This
  matches decision D-W4-AGENTS-M2R (`brambleloop/DECISION_LOG.md:2519-2527`). **Mode T**
  (split services) is required for live issuance. Moving to Mode T costs money, so it needs
  an owner spend decision.

---

## 1. The policy object

### 1.1 Storage and family

* New module `ops/standing_policy.py`. Rows go in `AuditLog`, like every other authority
  family. Event names:
  * `owner.standing_policy.approved`: owner-signed policy content.
  * `owner.standing_policy.activated`: owner-signed. Points to one approved row.
  * `owner.standing_policy.revoked`: deny-direction. Anyone may write it, and an unsealed row
    still revokes (fail closed), as in `GrantLedger.refusal` (`core/sealed_chain.py:296-300`).
  * `owner.standing_policy.rebased`: owner, step-up. Voids every earlier row.
  * `system.standing_policy.suspended`: written by the stop watch, the PI or the worker. It is
    deny-direction and is not required to verify. See §5.
  * `owner.standing_policy.resumed`: owner-signed, step-up.
* Chain: a `GrantLedger` (`core/sealed_chain.py:158`) with `approved=…approved`,
  `revoked=…revoked`, `rebased=…rebased`. The other events are appended through `append`
  with their own action names. **A rule to implement:** `GrantLedger.actions`
  (`core/sealed_chain.py:175`) loads only three action names, but every SP event must be on
  the chain. This needs a small `GrantLedger` extension, `extra_actions=(...)`, so that
  `load`/`walk` cover activated, suspended and resumed too. Without it, deleting a suspension
  row would go undetected. Test T-CH-4 checks this.
* Seal: **Ed25519**. The signing key is `BRAMBLELOOP_POLICY_SIGNING_KEY` and the verify key
  is `BRAMBLELOOP_POLICY_VERIFY_KEY`. The signing rules are the storefront rules, reused
  as-is:
  * `signing_refusal()` refuses in any job process and whenever the embedded worker is on
    (`ops/storefront_authority.py:94-101`).
  * `mark_job_process()` scrubs the key (`:88-92`).
  * Minting needs the `owner_request` context variable, which only the Command Center action
    route sets (`:106-122`; `app/command_center/api.py:935-941`). The `startswith` test there
    must be extended to `standing_policy.`.
* The policy key must differ from the storefront key, from the issuer key (§2) and from the
  ops token. At boot, `standing_policy.key_health()` compares the raw bytes and the derived
  public keys, and treats a shared key as not configured. This follows
  `core/readbackauth.py:434-440`.

### 1.2 Fields (the signed `content`)

```
{
  "schema": "brambleloop.standing_policy/1",
  "policy_id": "sp-<uuid4>",            # stable across versions
  "version": 3,                          # strictly +1 per approval of this policy_id
  "supersedes": {"row_id": 812, "seal": "<hex>"} | null,
  "actions": ["store.publish"],          # v1: store.publish only; "store.activate" is §1.5
  "etsy": {"shop_id": "12345678", "shop_name": "BrambleloopStudio"},
  "product_classes": [                   # allow-list; anything unlisted is out of policy
    {"class_id": "flat-colourwork-A",
     "categories": ["coaster", "placemat", "mosaic_blanket"],   # publish.eligibility families
     "max_effective_risk_class": "A",    # gates.risk_matrix.assess()["effective"]
     "physical_required": "partial_physical",   # >= REQUIRED_PHYSICAL[effective]
     "price_band_cad": [4.00, 12.00],
     "max_sizes": 1, "colourwork_allowed": true, "wearable_allowed": false}
  ],
  "exclusions": {"launch0_slugs": "ALWAYS",     # fixed in v1, see 1.4
                 "slugs": [], "categories": ["garment", "amigurumi"]},
  "required_certifications": [            # every one must read PASS (UNKNOWN never passes)
    "certification", "parity", "listing_set", "disclosure", "policy", "search", "rollback",
    "first_customer_blocking_empty", "release_gates_for_publish", "originality",
    "standards", "size_claims", "exported_frame_review", "independent_vision_review"],
  "evidence": {"rollback_rehearsal_max_age_days": 14,
               "policy_reading_max_age_days": 7,
               "vision_reviewer_must_differ_from_generator": true,
               "min_shadow_days_before_activation": 7},
  "frequency": {"max_per_day": 2, "max_per_7d": 6, "min_spacing_minutes": 180,
                "max_outstanding_unconsumed_grants": 1},
  "spend": {"max_listing_fees_cad_per_30d": 0.00,   # draft-only scope: drafts are free
            "ads": "NONE"},                         # no paid media under this policy, ever (v1)
  "stop_conditions": {                    # §5; each threshold is a number, never prose
    "open_defect_incident_on_policy_product": 1,
    "refunds_7d_count": 2, "refund_rate_30d_pct": 10.0,
    "etsy_policy_notice_any": true,
    "dead_letters_60m": 5,
    "open_p0_any": true, "authority_tamper_any": true,
    "publish_incomplete_any": true, "census_drift_on_policy_listing": true,
    "stop_watch_max_silence_minutes": 30},
  "validity": {"not_before": "2026-11-20T00:00:00+00:00",
               "review_by":  "2027-01-18T00:00:00+00:00",   # <= 60 days after not_before
               "expires_at": "2027-02-17T00:00:00+00:00"},  # <= review_by + 30 days
  "owner_statement_digest": "<sha256 of the rendered text, 1.3>",
  "code_ceilings_version": "ws4-ceilings/1"
}
```

The signed row's `detail` wraps `content` with `principal: "owner:command-center"`, `actor`,
`owner_session`, `stepped_up: true`, `digest`, `reason`, `approved_at` and the chain fields
`seq`/`prev_id`/`prev_seal` that `GrantLedger.append` adds (`core/sealed_chain.py:231-236`).

**Code ceilings.** These are constants in `ops/standing_policy.py`. Changing one is a reviewed
code change and can never be done through data. `approve()` refuses any policy that exceeds
one, and the PI re-checks them before every issuance:

| Field | Ceiling |
|---|---|
| `frequency.max_per_day` | ≤ 3 |
| `max_per_7d` | ≤ 10 |
| `max_outstanding_unconsumed_grants` | ≤ 2 |
| SEG TTL | ≤ 30 min (default 15) |
| `review_by - not_before` | ≤ 90 days |
| `max_effective_risk_class` | ≤ "B" (Class C is never standing in v1) |
| `price_band_cad` | within [1.00, 40.00] |
| `spend.ads` | must be "NONE" |
| `actions` | ⊆ {"store.publish"} in v1 |
| `exclusions.launch0_slugs` | must be "ALWAYS" |

### 1.3 The text the owner signs

`standing_policy.render_statement(content)` builds the text deterministically from the
fields. The `owner_statement_digest` is the sha256 of that rendered text, so the screen, the
signature and the content cannot drift apart. Template (v1):

```
STANDING PUBLICATION POLICY {policy_id} version {version}

I, the owner of Brambleloop Studio, authorise the Brambleloop policy authority to create
Etsy DRAFT listings on shop {shop_name} (id {shop_id}) without asking me for each product,
only while ALL of the following hold:

  Products: only {class list with categories, max risk class, price band, physical evidence}.
  Never: Launch-0 products, {excluded categories/slugs}, or anything not listed above.
  Evidence: every one of {required_certifications} reads PASS on the exact release;
            UNKNOWN is a refusal.
  Pace: at most {max_per_day} per day, {max_per_7d} per 7 days, {min_spacing} minutes apart.
  Money: CA${max_fees} in listing fees per 30 days; no advertising.
  Stops: the policy suspends itself on {each stop condition with its threshold}.
  Period: from {not_before} until {expires_at}; I will review it by {review_by}.

This policy cannot activate a listing, change a price, spend on advertising, or change itself.
Any product outside it is held for my individual decision. I can suspend or revoke it at any
time, and either takes effect at the next check (at most 15 minutes).

Digest: {digest[:16]}
```

To confirm, the owner types `AUTHORISE {policy_id} v{version} {digest[:8]}`. This uses the
same exact-string confirmation pattern as `physical_photo.attest_unedited`
(`app/command_center/approvals.py:696-703`).

### 1.4 Launch-0 and the first-customer rule

`gates/first_customer.py:28-33, 70-74` (`NEVER_AUTHORISES`) is the owner's standing rule: a
person publishes the first Launch-0 listings. The SP does not override it. In v1,
`exclusions.launch0_slugs` is fixed to `"ALWAYS"`: any slug in `products/launch0.LAUNCH0_SLUGS`
(`products/launch0.py:1200`) or in `HELD_FOR_VERIFICATION` is out of policy. The SP does
still require the first-customer gate's `blocking()` list to be empty for every product
(`gates/first_customer.py:874-886`), so the standard does not drop outside Launch-0.

### 1.5 Activation (`store.activate`) is not in v1

A draft is invisible to buyers and costs nothing (`ops/publication_authority.py:335-336`). The
listing fee is charged on activation (`integrations/etsy.py:1483-1487`). A v1 policy that
covers only `store.publish` removes the repeated draft decision. Making a listing live stays a
per-product `activation_authority` grant. Extending the SP to `store.activate` would be **WS4
v2**. It needs a code-ceiling change plus its own gate (G-ACT in §7.3), and it adds a binding
to the listing id and the read-back files (`ops/activation_authority.py:44-63`). This is
stated plainly so that nobody reads v1 as "autonomous going live".

### 1.6 Versioning, review and expiry

* `version` must be the previous version of the same `policy_id` plus 1, and `supersedes`
  must name that row and its seal. Otherwise `approve()` refuses.
* Exactly one SP may be **effective** at a time: the newest `activated` row whose approved row
  verifies, is not revoked, sits inside the current chain segment and is within its validity
  window. Activating version N+1 supersedes version N at once. Outstanding SEGs issued under
  version N are refused at use, because the SEG binds `policy_version` and `policy_seal`.
* **Rollback of the policy** means approving a new version whose content equals an older
  version (a "revert to v2" button that pre-fills the form). Rows are never deleted.
* At `review_by - 7d` the system opens a deduplicated owner card. After `review_by` passes,
  the SP becomes **issue-paused**: no new SEG is issued and the owner card escalates. At
  `expires_at` the SP is dead. A dead SP can only be renewed as a new version, never by
  extending the old one.

### 1.7 Owner approval flow

These steps reuse existing patterns.

1. **Draft.** `standing_policy.preview` (no step-up). This is a read action in
   `app/command_center/approvals.py` `ACTIONS` (`:27`). It returns `content`, the rendered
   statement, its `digest`, a field-by-field diff against the effective SP, and the
   code-ceiling check result. An LLM or agent may *propose* a draft. A proposal is only a form
   pre-fill: nothing an agent writes is signed.
2. **Approve.** `standing_policy.approve` (step-up `True`). The route runs `require_stepup`
   (`app/command_center/api.py:932-933`; 5-minute window at `app/command_center/auth.py:73`;
   TOTP step replay refusal at `:249-265`). It then sets the `owner_request` context,
   recomputes the preview, compares the digest in constant time (as at
   `ops/publication_authority.py:415-416`), checks the typed confirmation, checks the code
   ceilings and `reject_private` (as at `:409-410`), and signs. The resulting state is
   APPROVED, which is not yet effective.
3. **Shadow.** For at least `min_shadow_days_before_activation` days, the PI runs in
   **would-issue** mode against real candidates. It writes `standing_policy.shadow_decision`
   rows (issue or hold, with reasons) and signs nothing.
4. **Activate.** `standing_policy.activate` (step-up `True`) is a separate owner act on a
   separate day. It is refused unless:
   * the shadow period has passed;
   * the shadow decisions are on the card for the owner to read;
   * the deployment is Mode T (§2.4);
   * the effective phase is `limited_production` or `production` (`core/phase.py:191`);
   * `BRAMBLELOOP_STANDING_POLICY_ENABLED=1`, a new deny-only switch in the pattern of
     `kill_switch_refusal` (`ops/publication_authority.py:68-73`).

   This two-step act is the "explicit approval to activate" that the requirement asks for.
5. **Revoke** (no step-up, tightens) and **suspend** (no step-up, tightens) are open to the
   owner from the card, and also through the bearer ops token, as
   `publication_authority.revoke` is today (`:427-430`). **Resume** and **rebase** need a
   step-up.

---

## 2. The issuing authority

### 2.1 Where it runs

**Mode T (required for live issuance).** There are three processes. Railway isolates
environment variables per service, but not between processes inside one service.

| Process | Public domain | Holds | Can not |
|---|---|---|---|
| `web` (Command Center, `BRAMBLELOOP_EMBEDDED_WORKER=0`) | yes | policy **signing** key, storefront signing key, ops token, issuer **verify** key | issue SEGs (it has no issuer key) |
| `worker` (`app/worker_entry.py`) | none | ops token (see WS4-0), policy **verify** key, issuer **verify** key, Etsy credentials | sign a policy (key scrubbed, `mark_job_process`), issue a SEG |
| `policy-issuer` (new `app/issuer_entry.py`) | **none**: no HTTP listener at all, private network not needed | issuer **signing** key `BRAMBLELOOP_GRANT_ISSUER_KEY`, policy verify key, a DB role (§2.3) | sign a policy, call Etsy (no Etsy creds), write any SP row other than `suspended` |

The issuer uses a **pull model**. Each tick, which is 60 s with a lease from `ops/lock.py`, it
reads `policy.grant_requested` rows and also scans publish-ready candidates. It has no inbound
interface, so a compromised worker can only *ask*, by writing a request row. A request row
carries no authority. The issuer ignores everything in it except `(slug, version, release,
job_id)` and re-derives every other fact.

**Mode S (today, single service).** `issuer.signing_refusal()` uses the same tests as
`storefront_authority.signing_refusal`. It refuses when the embedded worker is on or the
process is a job process, so a SEG cannot be minted. The PI logic still runs in shadow, as a
cadence job of class OBSERVE, and writes only `shadow_decision` rows. This makes the shadow
period of §1.7 step 3 possible today at no cost.

### 2.2 Keys and how they differ from the ops token

* **Issuer key.** Ed25519 key `BRAMBLELOOP_GRANT_ISSUER_KEY`, with public key
  `BRAMBLELOOP_GRANT_ISSUER_VERIFY_KEY`. The worker verifies a SEG with the public key through
  `GrantLedger(verify=...)` (`core/sealed_chain.py:179-196`). **The worker holds no secret
  that can produce a SEG.** This is the property the ops-token HMAC cannot give (F-A).
* **Why not a key derived from the ops token**, such as
  `HKDF(ops_token, info="brambleloop/standing-grant/v1")`? Domain separation of that kind does
  stop a seal from one family validating in another. That matters, because today the phase,
  activation and publication families all use the *same* raw ops-token HMAC
  (`core/phase.py:66-70`), and only the action names and the chain separate them. But anyone
  who holds the ops token can derive the key, so derivation gives **no privilege separation**
  from the worker or the web process. The design adopts derivation **only** as
  defence-in-depth for families that must stay HMAC (WS4-0b: `ops_subkey(label)`, used by the
  existing families from then on). It is **never** used as the SEG key.
* **Generation and rotation.** `standing_policy.generate_keypairs()` prints fresh pairs, as
  `ops/storefront_authority.py:154-168` does. Rotating the issuer key invalidates every
  outstanding SEG, at most 15 minutes of work, so rotation is safe at any time. Rotating the
  policy key invalidates the SP, which fails closed, and the owner must re-approve and
  re-activate. Each rotation is recorded as an audited `key_rotated` row that names only the
  public key fingerprint.

### 2.3 Least privilege in the database

The existing families keep everything in `AuditLog`, and any process with `DATABASE_URL` can
write any row. Seals and chains detect forged rows, but they do not prevent them. Mode T adds
Postgres roles. This is an owner action: CA$0, about 10 minutes of SQL in the Railway
Postgres query tab.

* `bl_issuer` may `INSERT` into `standing_grants` and `standing_grant_slots`, and only
  `SELECT` elsewhere. It may also `INSERT` `AuditLog` rows. Postgres cannot restrict an
  `INSERT` by row content, so this is accepted, and every row the issuer writes must verify
  under its key anyway.
* `bl_worker` (the worker's `DATABASE_URL`) may `SELECT` from `standing_grants` and `UPDATE`
  only the `consumed_*` columns (column-level grant). It has **no INSERT** on
  `standing_grants` or `standing_grant_slots`.
* `bl_web` keeps today's role.
* New table `standing_grants` has the columns `id`, `policy_row_id`, `policy_version`,
  `scope`, `release`, `digest`, `detail_json`, `seal`, `issued_at`, `expires_at`,
  `consumed_at`, `consumed_job_id` and `consumed_stage`. Constraints:
  * `UNIQUE(consumed_job_id)`;
  * `UNIQUE(policy_row_id, scope, release) WHERE consumed_at IS NULL`;
  * `CHECK(expires_at - issued_at <= interval '30 minutes')`.
* New table `standing_grant_slots` has `UNIQUE(policy_row_id, day, slot_no)` and
  `CHECK(slot_no BETWEEN 1 AND 3)`, so the database itself refuses the 4th grant of a day.
* SEG rows are *also* appended to the SP-grant chain in `AuditLog` (a `GrantLedger`), so they
  are audited and chained the same way as the existing families.

**Honest limit:** if the roles are not created, Mode T still gives key separation (the worker
cannot mint). It does not stop the worker from *writing evidence rows* that the issuer then
reads. §6 T1 covers this.

### 2.4 Mode T readiness check (`standing_policy.deployment_mode()`)

Mode T is reported only when the issuer process's latest heartbeat row shows **all** of:

* `BRAMBLELOOP_EMBEDDED_WORKER=0` on web;
* the issuer verify key present on the worker and the issuer signing key **absent** there.
  The worker reports this at boot with `mark_job_process`-style scrubbing and a sealed boot
  row;
* the three key fingerprints pairwise distinct;
* the DB role reported by `SELECT current_user` differing between worker and issuer.

`activate` refuses if the mode is not T. Each process is the only witness to its own
environment, so this check can be lied to by a compromised process. It catches
misconfiguration. It does not defend against an attacker.

---

## 3. The per-product Standing Execution Grant (SEG)

### 3.1 Content binding

A SEG binds everything `publication_authority.snapshot` binds today
(`ops/publication_authority.py:76-101`). It **reuses that function** to compute the binding,
so the two can never diverge. It then adds the policy fields.

```
{"schema": "brambleloop.seg/1", "action": "store.publish",
 "scope": "slug@version", "release": "<release_hash>",
 "content": publication_authority.snapshot(db, slug, version, release),
     # = {action, slug, version, release, cir_digest, payload (sent_fields), evidence}
 "digest": publication_authority.digest(content),
 "publish_binding": {"pdf_sha256": {...}, "image_shas": [...], "image_order": [...],
                     "listing_set_record": id},   # the same elements _publish_content_digest
                                                  # binds (runtime/pipeline.py:2160-2166)
 "shop": {"shop_id": "...", "shop_name": "..."},
 "classification": {"class_id": "...", "category": "...", "effective_risk_class": "A",
                    "physical_bound_classes": [...], "price_cad": 5.00},
 "policy": {"row_id": 812, "version": 3, "seal": "<hex>", "activation_row_id": 830},
 "budget": {"day": "2026-11-21", "slot_no": 1, "seven_day_count_before": 2},
 "job_id": 4471, "nonce": "<128-bit hex>",
 "issued_at": db_now, "not_before": db_now, "expires_at": db_now + 15 min,
 "issuer_key_fp": "<sha256(pub)[:16]>", "issuer_host": "policy-issuer"}
```

### 3.2 TTL

The TTL is **15 minutes**. The code ceiling is 30. The SEG is **single use**: it is consumed
by `UPDATE … SET consumed_at = now(), consumed_job_id = :job WHERE id = :id AND consumed_at IS
NULL AND expires_at > now()`, which must affect exactly one row. That update runs in the same
transaction as the durable draft-intent claim (`publish/draft_intent`, called at
`runtime/pipeline.py:2302` `stage="pre_claim"`). The `before_create` stage then accepts only
a SEG that this same `job_id` consumed. Today's owner grant keeps its 24 h, multi-use
semantics. A SEG does not.

### 3.3 Issue-time checks

`issuer.evaluate(db, slug, version, release, job_id)` is a pure function of facts read now.
Every read is wrapped like `_guard` (`ops/publication_authority.py:123-131`), so an exception
reads as UNKNOWN, and UNKNOWN means **HOLD**. The checks run in this order. The first failure
stops issuance, but all reasons are collected for the hold card.

1. **Switches and deployment.** `kill_switch_refusal()` is clear (`:68-73`).
   `BRAMBLELOOP_STANDING_POLICY_ENABLED=1`. Mode T is confirmed. `signing_refusal()` is None.
2. **Phase.** `core.phase.effective(db)` is in `PHASES_THAT_MAY_PUBLISH`
   (`integrations/etsy.py:86`).
3. **Effective SP.** The SP chain verifies (`GrantLedger.chain`), the approval and activation
   rows verify under the policy verify key, nothing is revoked or suspended, now is within
   `not_before..review_by`, and the content passes the code ceilings again.
4. **Stop conditions.** All are clear (§5), and the stop-watch's last reading is younger than
   `stop_watch_max_silence_minutes`.
5. **Scope exclusions.** The slug is not in Launch-0 or the held set, not in
   `exclusions.slugs`, and not an experiment (`visual.experiment.refuse_if_experiment`, as in
   `ops/publication_authority.py:403-405`).
6. **Classification.** This must be deterministic and must not come from any LLM field:
   * The category comes from the CIR, using the same families as `publish/eligibility.py:147-152`.
   * The category must agree with the listing taxonomy id from `search_gate`
     (`publish/release_gates.py:309`). If they disagree, the product is OUT.
   * The effective risk class is `gates.risk_matrix.assess()["effective"]` = max(declared,
     derived) (`gates/risk_matrix.py:250-268`), so a CIR that *declares* a low class cannot
     lower the result.
   * The class must match exactly one `product_classes` entry. Zero or several matches is OUT.
7. **Certification and Product Truth.** `publication_authority.evidence()` gives
   `summary.all_gated_sections_pass is True` (`:367-388`). This is the same rule
   `_require_publication_evidence` enforces for the owner (`app/command_center/approvals.py:
   445-466`). It covers certification with `granted`, release match and nothing withheld
   (`:152-178`), parity with independent frame review (`:181-220`), the listing set
   (`:223-236`), disclosure, platform policy freshness, search, and a rollback rehearsal
   within the policy's age limit.
8. **Release gates.** `release_gates.for_publish(...)["blocks_release"] is False`
   (`publish/release_gates.py:1554-1670`). This includes originality, standards, size claims,
   withholding, `eligibility.product_publication` (which runs the first-customer gate),
   `launch_price_check` that is not `DRIFT`, and held taxonomy drift. The issuer calls the same
   functions the worker's `_release_gates` calls. It does not read the worker's
   `store.release_gates` audit row, because that row is written by the worker.
9. **Independent deterministic re-verification.** The issuer itself loads `pv.cir_json`,
   recomputes the CIR digest, recompiles, re-renders the US pattern text and recomputes the
   content and release hash (`gates.certificate._release_hash`, as used at
   `gates/first_customer.py:290`). It refuses if any differs from the stored values. "Deterministic
   validation wins": the issuer does not trust a stored `certified=True` that its own compiler
   cannot reproduce.
10. **Physical sample per class.** The issuer runs `first_customer.physical_binding(db, cir)`
    (`gates/first_customer.py:273-302`). `bound_classes` must satisfy both
    `REQUIRED_PHYSICAL[effective]` (`gates/risk_matrix.py:176-178`) and the class's
    `physical_required`, using `risk_matrix.satisfies` (`:100`). Every bound PhysicalTest must
    carry an owner attestation (`physical_photo.attest_unedited`, which is session-signed),
    never an operator-token intake.
11. **Independent vision review.** `exported_review.review_state(...).reviewed` and
    `frame_review_state(...).reviewed` must both be true (`ops/publication_authority.py:
    203-208`). In addition, every reviewed frame must carry a reviewer `model_id` from a
    provider and model family different from the generator model recorded in that frame's
    provenance, bound to the frame sha. A review without a recorded reviewer identity reads
    UNKNOWN.
12. **Price.** `Listing.price_cad` must be within the class's `price_band_cad`, inclusive and
    exact to the cent. `pricing.check_no_fake_discount` must pass (`commerce/pricing.py:380`).
    There is no "reference price" field in the sent payload.
13. **Frequency budget.** The issuer counts the consumed and unexpired SEGs of this SP today
    and over the last 7 days, the spacing since the last consumed SEG, and the outstanding
    unconsumed SEGs. It then allocates `slot_no`, and the DB unique constraint is the arbiter.
    Days are UTC.
14. **Spend.** v1 has no fee-bearing action, so the requirement is `max_listing_fees_cad_per_30d
    >= 0` and nothing to spend. Even so, it checks that `ads == "NONE"` and that no ads job is
    queued under this SP's lineage. v2 would compute fees with `commerce.fee_schedule` times the
    count of planned activations, plus `SpendGuard` (`agents/registry.py:683`).
15. **Etsy account.** `etsy_shop_binding.bound_shop_id(db)` (`integrations/etsy_shop_binding.py:51`)
    and the worker-reported `ETSY_SHOP_ID` must both equal `policy.etsy.shop_id`. The shop name
    must equal `expected_shop_name()` (`:45`).
16. **Not already on Etsy.** `listing.etsy_listing_id` is empty, which `snapshot` already
    refuses at `:93-94`. There is no open `store.publish_incomplete` for the slug.

If every check passes, the issuer signs the SEG. It inserts the `standing_grants` and slot rows
in one transaction and appends the chained `policy.grant.issued` audit row. If any check fails,
it writes a HOLD (§4.2).

### 3.4 Use-time checks (worker)

The change in the pipeline is one line. `_revalidate_publish_effect`
(`runtime/pipeline.py:2172-2256`) calls `publication_authority.resolve` twice (`:2204` and
`:2242`). `resolve` becomes `authority_for_publish.resolve`, which returns
`(refusal, Grant(kind="owner"|"standing", id))`:

* `kind="owner"` follows exactly today's path, unchanged.
* `kind="standing"` follows `standing_grants.check(db, id, slug, version, release, job_id,
  stage)`. It refuses unless:
  * the kill switch is on and the standing-policy switch is on;
  * the seal verifies under the issuer **verify** key;
  * the SEG is on the SEG chain and not revoked;
  * the DB time is in `[not_before, expires_at)`;
  * `scope` and `release` match;
  * `digest(publication_authority.snapshot(...)) == seg.digest`. The snapshot is recomputed
    now, as `_check_one` does (`ops/publication_authority.py:460-461`);
  * `publish_binding` equals the bytes the worker is about to send, compared against the
    reserved `content_digest` elements;
  * the shop id the client will use equals `seg.shop.shop_id`;
  * the referenced SP is **still the effective SP**: same row, same version, not revoked, not
    suspended, within its window;
  * every stop condition is clear;
  * at `pre_claim`, the consume-update affects one row. At `before_create`, `consumed_job_id
    == job_id`.

  The rest of `_revalidate_publish_effect` (phase, parity, gates, payload, PDF, images) still
  runs unchanged.
* `OwnerGrant` at the client (`integrations/etsy.py:100-200`) gains `kind`.
  `OwnerGrant.refusal` re-resolves through the same `authority_for_publish` function, and
  `_completion_refusal` accepts a standing grant **only** for the listing id that grant's job
  created (the `on_created` checkpoint), as today.
* The kill switch `BRAMBLELOOP_PUBLISH_AUTHORISED` is still read at
  `runtime/pipeline.py:1992` and in `resolve`. It still denies everything, including SEGs.

---

## 4. Boundaries

### 4.1 Deciding "out of policy"

`standing_policy.classify(policy_content, facts) -> {"in_policy": bool, "reasons": [...]}`
lives in its own small module, `ops/standing_boundary.py`, and has no I/O. `facts` is built
by `issuer.read_facts()`, and each fact is `{state, value, why}`. The rules:

* Any fact whose state is not PASS (or the explicitly numeric value) produces a reason, and
  any reason means **out**.
* Anything the policy does not mention is out. The class list is an allow-list. An unknown
  category, an unknown evidence section or a new `GATED_SECTIONS` member that the policy does
  not list all fail.
* A policy schema the code does not know (`schema` ≠ `standing_policy/1`) is out.
* A code ceiling exceeded at read time is out, and also suspends the SP.

### 4.2 Holding for the owner

A hold writes `standing_policy.held` with `scope`, `release`, `reasons` and `policy_version`,
and calls `owner_queue.ensure(s, "standing_policy.hold:{slug}@{version}:{release[:12]}", …)`
(`ops/owner_queue.py:180`). That function is idempotent by key, so one card covers a product
however many times it is re-held. The card links to the existing `publication.preview` →
`publication.approve` flow (`app/command_center/approvals.py:27-29, 595-616`). The owner
decides per product, exactly as today. A hold never retries silently into an issue. If the
facts change, for example a new release, the card's key changes and the old card closes on
evidence (`owner_queue.close`). The held job ends with `PermanentError` and is re-enqueued by
the normal release chain.

### 4.3 Why the system cannot widen its own boundaries

These are the code paths that may write an SP row:

| Row | Writer | Authority required |
|---|---|---|
| approved, activated, resumed, rebased | `standing_policy.approve/activate/resume/rebase` only | policy **signing** key (web only, refused in job processes and with the embedded worker on) + `owner_request` context (Command Center route only) + step-up + typed confirmation + code ceilings |
| revoked, suspended | anyone (owner, ops token, stop-watch, issuer, worker) | none; deny-direction, effective even if unsealed |

Enforcement:

1. **Cryptography.** A widening row must verify under the policy verify key. Only the web
   process can sign, and only inside the owner request.
2. **Code ceilings** sit above the owner's own key. A stolen policy key still cannot exceed
   them.
3. **Static tests.** These tests parse source files without running them, so they run fast:
   * an AST scan asserts that the only call sites of `SP_LEDGER.append(action=APPROVED |
     ACTIVATED | RESUMED)` are in `ops/standing_policy.py`, inside `approve`, `activate` and
     `resume`;
   * an import-graph test asserts that `app/issuer_entry.py`, `runtime/*` and `agents/*` never
     import those three functions;
   * a test asserts that `authority/classes.JOB_CLASS` has **no** job type that writes SP rows.
     A new `policy.stop_watch` job is classified OBSERVE.
4. **The authority ladder is separate.** The `AuthorityPolicy` ladder
   (`authority/policy.py:152-225`) cannot stand in for an SP, and an SP cannot be granted
   through it. `grant()` refuses agents (`:162-166`), and the SP check never reads
   `authority_policies`. A test asserts that the `standing` rung there does not make
   `authority_for_publish.resolve` return a grant.
5. **Agents and LLMs** reach the SP only through `standing_policy.preview` input, which runs
   through `reject_private` (`laura/private/firewall`). A proposal is never signed without the
   owner's typed confirmation over the rendered digest.

---

## 5. Emergency stop, revocation and rollback

### 5.1 Automatic stop conditions

The new job `policy.stop_watch` is class OBSERVE and runs every 5 minutes on the scheduler.
Its function `stop_conditions(db, policy)` is also called inline at issue and at use. Each
condition is read from rows. An unreadable source means **STOP**.

| Condition | Source |
|---|---|
| open support-defect incident on any product the SP published | `support/defects.signature` (`support/defects.py:76`), `_active` (`:277`); joined via SEG lineage |
| refunds ≥ N in 7 d, or refund rate > X% over 30 d | `commerce/orders_ingest.countable_orders` (as used at `ops/publication_authority.py:313-316`); refund fields from `commerce/order_ledger` |
| any Etsy policy notice / violation incident (any severity) | `commerce/policy_violations.py` incidents (P0 account, P1 IP/removal, P2 warning, `:9-14`) |
| platform-policy reading stale or changed-unreviewed | `gates/platform_policy.freshness` (as at `ops/publication_authority.py:252-271`) |
| spend over cap, or any SpendGuard refusal naming SP lineage | `agents/registry.SpendGuard`, `finance/accounting/policy.check_spend` (`:102`) |
| dead letters ≥ N in 60 min | `queue.dead_letters()` (`runtime/pipeline.py:2743, 3051`) |
| any open P0 incident | `Incident` severity |
| any `authority_chain_tamper:*` incident | `core/sealed_chain.tamper_incident` (`:134-155`) |
| any `store.publish_incomplete:` on an SP product | `runtime/etsy_ops.PUBLISH_INCOMPLETE` (`:48`) |
| census drift on an SP listing | `etsy.listing_census` (`runtime/etsy_ops.py:1263`) |
| stop-watch silent > 30 min | the issuer and the worker check the last reading's age; silence counts as stop |
| effective phase drops below limited_production | `core/phase.effective` |

When any condition holds, the job appends `system.standing_policy.suspended` with the
condition, its reading and the time. It opens a P1 incident
`standing_policy_suspended:{policy_id}` and an owner card. A suspension is **sticky**: it does
not clear by itself when the condition clears. Only the owner's `resume` (step-up) clears it,
and `resume` refuses while any condition still holds. Outstanding SEGs die at use, because
§3.4 re-checks suspension and stop conditions.

### 5.2 Revocation

* `standing_policy.revoke`: owner, Command Center or ops token, no step-up. Effective at the
  next check. Permanent, and voids every SEG under that policy.
* `standing_grants.revoke(id)`: kills one SEG.
* Global: unset `BRAMBLELOOP_STANDING_POLICY_ENABLED` (SPs only) or
  `BRAMBLELOOP_PUBLISH_AUTHORISED` (everything).
* Worst-case latency from revocation to refusal is the time to the next `before_create`
  check, which is seconds. A create request already in flight cannot be recalled. That is
  covered by rollback below.

### 5.3 Rollback of published listings

* **v1 (draft-only).** An SP-created draft is invisible to buyers. Rollback is
  `EtsyClient.delete_listing(listing_id, expect_states=("draft",))`
  (`integrations/etsy.py:1369-1393`). It reads the listing back and refuses unless the listing
  is a draft. New job `policy.rollback_drafts`:
  * on suspend or revoke, it builds the list of SP-lineage drafts from consumed SEG ↔
    `Listing.etsy_listing_id`;
  * by default it **plans only** and puts the plan on the owner card;
  * the owner can tick "auto-delete SP drafts on stop" in the policy. That is a boolean field,
    owner-signed and default false.

  A delete rides a narrow new grant kind `OwnerGrant.WITHDRAW` (§5.4).
* **v2 (when activation is in scope).** `ROLLBACK_PATH` says no automated deactivation exists
  (`ops/publication_authority.py:339-344`), and `update_listing` refuses `state`
  (`integrations/etsy.py:1355-1359`). v2 adds `EtsyClient.deactivate(listing_id, grant)`. It is
  the only door that sends `state=inactive`. It reads back first and refuses unless the
  listing is `active` and in SP lineage. Afterwards the release chain marks the local Listing
  `withdrawn` (audited `listing.withdrawn`). Buyer impact is unchanged and UNKNOWN as the code
  states (`:345-348`).

### 5.4 Withdrawal authority (deny-direction, but still bounded)

Deleting or deactivating does not widen what the system can do, but a compromised worker
could use it to destroy work. So `OwnerGrant.WITHDRAW` is valid only when:

* the target is in **SP lineage**;
* the SP is suspended or revoked, or the owner asked;
* no more than 10 withdrawals happen per hour;
* every withdrawal is audited with a before-state read-back.

It never applies to listings the owner published personally.

---

## 6. Threat model

| # | Threat | What stops it | Residual |
|---|---|---|---|
| T1 | **Compromised worker mints a grant** | SEG verify key only on the worker (§2.2). No SP signing key (scrubbed; job-process refusal). Postgres role blocks INSERT on `standing_grants` (§2.3). Pre-WS4-0, a worker *can* mint a per-product owner grant via the ops-token HMAC (F-A); WS4-0 closes this. | In Mode S nothing separates processes, so no SEG is ever minted there. |
| T1b | **Compromised worker forges evidence** (e.g. writes `certified=True`, a fake review row) | Issuer re-derives the release hash by recompiling (§3.3 #9). Physical evidence must carry an owner session attestation. Vision reviewer identity bound to frame sha. Frequency ceiling caps blast radius at ≤3 drafts/day. Drafts are buyer-invisible. | Rows with no seal (e.g. a review verdict) can be forged by a DB writer. Honest limit: the issuer is a second, independent evaluator, not an oracle. v1's draft-only scope keeps the worst case at "a bad draft exists". |
| T2 | **Database edit** of SP/SEG rows | Ed25519 seals. Chains (`core/sealed_chain.walk`). Unsealed revocation/suspension still denies. Deleting a mid-chain row breaks the chain → P1 tamper → every grant refused (`:296-308`). | Tail truncation of the newest rows is undetectable inside the DB (`core/sealed_chain.py:26-29`). Mitigations: SEG TTL 15 min; a deleted *suspension* is re-written by the next stop-watch tick while its condition holds. A deleted *revocation* is not re-derived, so the issuer also keeps a local high-water mark (last seen SP chain seq + seal) in its own process and refuses if the chain gets shorter. The owner card also shows the chain length. |
| T3 | **Replay** of an old SEG or SP row | SEG single-use consume + `UNIQUE(consumed_job_id)`. Nonce. 15 min TTL. Bound to `policy_version`+seal, so a superseded version's SEGs are dead. Chain link check stops copied rows (`walk` `:77-83`). | None known. |
| T4 | **Clock skew** | All issue and check times are `SELECT now()` from Postgres, never the container clock. Each process refuses when `abs(local - db) > 30 s` and records an incident. `not_before` has no grace period. | DB clock compromise equals DB compromise (T2). |
| T5 | **Policy drift** (the SP silently means something else) | `owner_statement_digest` binds the rendered text. `schema` versioned. Code ceilings. Unknown sections are out. `review_by` forces review. The effective SP's digest is shown on every SEG and hold card. | Code changes to what a section *means* (e.g. `GATED_SECTIONS` semantics). Mitigation: `code_ceilings_version` and `evidence()` code hash recorded on each SEG. Deploying a change to `ops/standing_*`, `publication_authority.evidence` or `release_gates.for_publish` sets `issue-paused` until the owner acknowledges (a step-up "re-confirm under new code"). |
| T6 | **TOCTOU between issue and publish** | SEG binds `snapshot` digest + publish binding. Re-checked at `pre_claim` and `before_create` (`runtime/pipeline.py:2204, 2242`). Consume is atomic with the draft-intent claim. The full gate run repeats at use. Final resolve must return the same grant id (`:2242-2247`). | Window between `before_create` and Etsy receiving the request: milliseconds. Covered by read-back (`_publish_and_read_back`) and rollback. |
| T7 | **LLM-influenced fields** (title, description, tags, alt text, CIR `risk_class`, reviewer verdict text) | Classification uses the CIR plus deterministic `risk_matrix` max(declared, derived). Category cross-checked with taxonomy. Price checked numerically. Title, tags and description are bound into `payload`, so the owner-equivalent gates (`product_type_findings`, disclosure, `claims_of`) judge them. No free text is ever parsed for a decision. Policy drafts from agents are only pre-fills. `reject_private` on every input. | A persuasive but compliant listing text is judged by existing gates only. That is the same as today. |
| T8 | **Compromised web process** | Can sign SPs, but only inside an owner request with a step-up (needs passphrase + TOTP, `auth.py:249-265`). Code ceilings still bind. Cannot mint SEGs (no issuer key). | A full web RCE with a live step-up window could sign an SP within the ceilings. Mitigation: activation is a second step-up act on a later day after shadow, and SP approval sends an out-of-band owner notification (`app/command_center/notifications.py`). |
| T9 | **Compromised issuer** | Can mint SEGs inside whatever it reads, but cannot sign an SP, cannot call Etsy, and has no public listener. The worker still runs every gate at use. Frequency ceilings also enforced by DB constraint. | It could issue a SEG for an out-of-policy product. The worker's use-time check re-runs `classify` (cheap, pure) against the effective SP, so the issuer is not the only judge. |
| T10 | **Denial by stop-condition spam** | Accepted: a stop only narrows. The owner sees the condition and its reading. | Availability, not safety. |
| T11 | **Shop swap** (credentials for another shop) | SEG binds `shop_id`. Checked against the binding and the client's credentials at use. | Today's owner grant does not bind the shop. Recommend adding it (WS4-0c). |

---

## 7. Tests and acceptance

### 7.1 Test list

New files go under `brambleloop/tests/`. Each file is runnable on its own with `python3`, as
the repository's tests are.

`test_ws4_policy_object.py`
* T-PO-1: approve refuses without step-up, without `owner_request`, with a wrong typed
  confirmation, or with a digest mismatch.
* T-PO-2: each code ceiling exceeded by 1 is refused (table-driven over every ceiling).
* T-PO-3: `version` gap, wrong `supersedes` seal, or two activations is refused, or only the
  newest is effective.
* T-PO-4: `render_statement` is deterministic, and changing any field changes the digest.
* T-PO-5: signing refuses with the embedded worker on, or after `mark_job_process`.
* T-PO-6: a shared key (policy = storefront = issuer = ops) is reported not configured.
* T-PO-7: `review_by` passed means issue-paused; `expires_at` passed means dead; a dead SP is
  not renewed by editing.

`test_ws4_chain.py`
* T-CH-1: a deleted mid-chain revocation refuses all and opens a P1.
* T-CH-2: a copied old approval row breaks the link.
* T-CH-3: an unsealed suspension still suspends and is reported as tamper.
* T-CH-4: a deleted `suspended` or `activated` row is detected (the `extra_actions` fix).
* T-CH-5: the issuer high-water mark refuses a shorter chain.

`test_ws4_issuer.py`
* T-IS-1 to T-IS-16: one test per §3.3 check. Each test makes exactly one fact non-PASS, or
  UNKNOWN by raising inside a reader, and asserts HOLD with that reason. A further test makes
  everything PASS and asserts ISSUE.
* T-IS-17: CIR whose stored `release_hash` differs from the recompiled hash is held.
* T-IS-18: a CIR declaring risk "A" whose derived class is "B" lands in the B rules.
* T-IS-19: category and taxonomy disagree, so the product is out.
* T-IS-20: the 4th SEG of the day is refused by the DB constraint even with the counting code
  stubbed out.
* T-IS-21: the issuer ignores every request-row field except `(slug, version, release,
  job_id)`.
* T-IS-22: Mode S issues nothing and writes `shadow_decision` rows.

`test_ws4_use.py`
* T-US-1: an expired SEG, one in its last second, and a `not_before` one second in the future
  are all refused.
* T-US-2: a SEG used twice is refused, and so is a SEG used by another job id.
* T-US-3: a changed payload, PDF or image after issue is refused at both stages.
* T-US-4: an SP superseded, revoked or suspended between issue and use is refused.
* T-US-5: a stop condition raised between `pre_claim` and `before_create` is refused at
  `before_create`.
* T-US-6: a SEG verified with the ops token, or forged with the storefront key, is refused.
* T-US-7: a SEG for shop A used with shop B's credentials is refused.
* T-US-8: the kill switch off refuses a SEG.
* T-US-9: the client-level `OwnerGrant(kind=standing).refusal` refuses on its own, without the
  pipeline.
* T-US-10: `_completion_refusal` with a standing grant refuses for any other listing id.
* T-US-11: the use-time `classify` re-run catches an out-of-policy SEG that a misbehaving
  issuer minted.

`test_ws4_boundary_static.py`
* T-ST-1: AST: approve, activate and resume `append` calls appear only in `ops/standing_policy.py`.
* T-ST-2: the import graph from `app/issuer_entry.py`, `runtime/`, `agents/` and `autonomy/`
  never reaches the SP signer functions.
* T-ST-3: `JOB_CLASS` has no SP-writing job type, and `policy.stop_watch` is OBSERVE.
* T-ST-4: the `AuthorityPolicy` `standing` rung yields no publish grant.
* T-ST-5: `first_customer.NEVER_AUTHORISES` is unchanged, and Launch-0 slugs are always out.

`test_ws4_stop.py`
* T-SW-1: one test per stop condition, plus unreadable means stop.
* T-SW-2: a suspension is sticky, and resume refuses while a condition holds.
* T-SW-3: stop-watch silence for more than 30 min blocks issue and use.
* T-SW-4: the rollback plan lists exactly the SP-lineage drafts; withdraw refuses non-lineage
  listings and active listings in v1; the rate limit is enforced.

`test_ws4_regression.py`
* T-RG-1: with no SP, every existing publication test still passes unchanged (the whole
  `test_w4_pl_boundary.py`, `test_draft_intent_precreate_refusal.py` and
  `test_r2_product_client_grant.py` suites).
* T-RG-2: an owner grant still works when an SP exists, is suspended or is revoked. The SP
  never blocks the owner's own path.

### 7.2 Mutants that must die

Each mutant is applied mechanically, and the suite must fail for each one.

| Mutant | Killed by |
|---|---|
| M1: `issuer.evaluate` returns ISSUE when a fact is UNKNOWN (`!= PASS` → `== FAIL`) | T-IS-1..16 |
| M2: drop `_guard` around any reader (exception propagates as ISSUE or crash-as-pass) | T-IS-* unknown variants |
| M3: TTL constant 15 → 1440 min, or ceiling check removed | T-PO-2, T-US-1 |
| M4: consume `WHERE consumed_at IS NULL` removed | T-US-2 |
| M5: `before_create` skips `consumed_job_id == job_id` | T-US-2 |
| M6: use-time check skips the snapshot digest comparison | T-US-3 |
| M7: use-time check skips "still the effective SP" | T-US-4 |
| M8: stop conditions checked at issue only | T-US-5 |
| M9: SEG verified with HMAC(ops token) fallback | T-US-6 |
| M10: `shop_id` comparison removed | T-US-7 |
| M11: `kill_switch_refusal` bypassed for `kind=standing` | T-US-8 |
| M12: `effective` risk class replaced by `declared` | T-IS-18 |
| M13: unsealed suspension ignored (`verify_row is None` required to suspend) | T-CH-3 |
| M14: `extra_actions` dropped from the SP ledger | T-CH-4 |
| M15: `signing_refusal` returns None when the embedded worker is on | T-PO-5 |
| M16: `owner_request` requirement removed | T-PO-1 |
| M17: Launch-0 exclusion removed | T-ST-5, T-IS-5 |
| M18: a `product_classes` match of "≥1" instead of "exactly 1" | T-IS-6 multi-match case |
| M19: price band check `<=` → `<` on the upper bound, or the band ignored | T-IS-12 (boundary cent) |
| M20: frequency counts only consumed SEGs, not outstanding ones | T-IS-13 |
| M21: suspension auto-clears when the condition clears | T-SW-2 |
| M22: `resolve` prefers a SEG over a present owner grant in a way that skips owner-grant checks | T-RG-2 |
| M23: physical requirement uses only `REQUIRED_PHYSICAL`, ignoring the class's stricter field | T-IS-10 |
| M24: the issuer trusts the stored `certified` without recompiling | T-IS-17 |

### 7.3 Production acceptance criteria (the gates; Doc 03 style)

The capability moves SHADOW → STAGING → LIMITED PRODUCTION → PRODUCTION only as follows.

* **G-SHADOW (Mode S allowed).**
  * Every §7.1 test and §7.2 mutant run is green.
  * An SP is approved by the owner under step-up.
  * At least 7 days and at least 10 real candidates of `shadow_decision` rows exist.
  * Each would-issue decision is compared with what the owner decided for that product through
    today's per-product grant. There must be **zero cases where the policy would have issued
    and the owner refused or held**. The comparison is recorded as a reading.
  * Stop-watch ran with no silence over 30 minutes for 7 days.
* **G-STAGING.**
  * Mode T is deployed, which needs an owner spend decision: a third Railway service at roughly
    US$5 a month, to be confirmed from the Railway bill.
  * The DB roles are created, and `deployment_mode()` reads T.
  * WS4-0 is done: publication and activation grants are verified asymmetrically.
  * One end-to-end issue → use → consume runs against `tests/fake_etsy.py`, plus one
    each of: a refused replay, a refused expired SEG, and a revoked SP.
  * A key rotation drill invalidates outstanding SEGs.
* **G-LIMITED.**
  * The owner runs `activate` under step-up.
  * Ceilings for the first 14 days: `max_per_day=1`, `max_per_7d=3`.
  * Every SEG-created draft is still reviewed by the owner before activation, because
    activation is per-product in v1.
  * Measured over 14 days: zero drafts the owner rejected for a reason the policy should have
    caught, zero `publish_incomplete`, zero tamper incidents, and one deliberate stop drill
    (raise a synthetic P0 → suspension within one stop-watch tick → SEG refused at use →
    rollback plan produced).
* **G-PRODUCTION.**
  * 30 days at the policy's own limits with the same zero counts.
  * The owner completes a `review_by` review.
  * A written incident drill (revocation latency measured in seconds, reported as a reading).

---

## 8. Implementation plan

Secondary Opus should implement this in small, reviewable increments. Each increment ships
with its own tests and leaves the system shippable. Line counts are rough estimates of
non-test and test lines.

| # | Increment | Files | Size |
|---|---|---|---|
| WS4-0a | Publication and activation families move to Ed25519 verification (sign in web only, verify key on the worker), reusing the storefront key plumbing; keep the ops-token HMAC verification for already-issued rows behind a deprecation (24 h) and then remove it. Closes F-A. | `ops/publication_authority.py`, `ops/activation_authority.py`, `app/command_center/approvals.py` (approve inside `owner_request`), `app/publication_authority_api.py` (bearer approve path: retire, or keep as read-only preview) | 250 + 300 tests |
| WS4-0b | `opsauth.subkey(label)` HKDF for the remaining HMAC families (phase); domain separation only | `core/opsauth.py`, `core/phase.py` | 60 + 80 |
| WS4-0c | Bind `shop_id` into the owner publication snapshot | `ops/publication_authority.py:96-101` | 30 + 40 |
| WS4-1 | `GrantLedger(extra_actions=...)` + tests | `core/sealed_chain.py` | 40 + 120 |
| WS4-2 | SP object: fields, code ceilings, `render_statement`, `approve/activate/revoke/suspend/resume/rebase`, `effective()`, key health | new `ops/standing_policy.py` | 400 + 450 |
| WS4-3 | Command Center actions: preview, approve, activate, revoke, suspend, resume, rebase; card; statement view; `owner_request` for `standing_policy.*` | `app/command_center/approvals.py`, `app/command_center/api.py:935`, static UI | 250 + 250 |
| WS4-4 | Boundary classifier (pure) + fact readers (guarded) | new `ops/standing_boundary.py`, new `ops/standing_facts.py` | 350 + 500 |
| WS4-5 | Stop watch: conditions, sticky suspension, incident, card; job registered as OBSERVE | new `ops/standing_stop.py`, `authority/classes.py` (add `policy.stop_watch`), `runtime/pipeline.py` (handler), scheduler cadence | 300 + 350 |
| WS4-6 | Issuer in shadow (Mode S): `evaluate`, `shadow_decision` rows, independent recompile, hold cards | new `ops/standing_issuer.py`, cadence job `policy.issuer_shadow` (OBSERVE) | 400 + 500 |
| — | **Stop here until the owner approves the Mode T spend.** G-SHADOW can be run on WS4-0..6. | | |
| WS4-7 | Mode T: `app/issuer_entry.py` (no HTTP, lease loop), `standing_grants` and slot tables + migration, DB-role SQL as an owner runbook (not executed by code), `deployment_mode()`, issuer signing | new `app/issuer_entry.py`, `core/models.py`, `core/migrate.py`, `ops/standing_issuer.py` | 350 + 400 |
| WS4-8 | Use path: `authority_for_publish.resolve`, `OwnerGrant(kind=)`, consume-at-claim, `before_create` job binding, use-time `classify` re-run | new `ops/authority_for_publish.py`, `runtime/pipeline.py:2189-2256`, `integrations/etsy.py:100-200, 279-283` | 250 + 500 |
| WS4-9 | Withdrawal: `OwnerGrant.WITHDRAW`, `policy.rollback_drafts` (plan by default) | `integrations/etsy.py`, new `ops/standing_rollback.py` | 200 + 250 |
| WS4-10 | Static boundary tests, mutation script, regression wiring, BUILD_STATE / DECISION_LOG entries | `tests/test_ws4_*.py`, `tests/mutants_ws4.py` | 0 + 400 |

The total is roughly 3,100 lines of code and 4,100 lines of tests, across 13 reviewable
changes. WS4-0a is the riskiest. It touches the live publish authority and needs its own
independent security review before the rest proceeds.

### Owner actions this design will eventually need (batched; none requested now)

1. **Approve Mode T.** Run the worker and the issuer as their own Railway services and set the
   web service to `BRAMBLELOOP_EMBEDDED_WORKER=0`.
   * Why: without this, no SEG can be minted safely (F-B).
   * Cost: the extra service cost, roughly US$5–10 a month, to be confirmed from the Railway
     usage page.
   * Time: about 20 minutes.
   * If you wait: the SP can only run in shadow.
2. **Set the key pairs** (policy and issuer) in Railway variables, each in its own service
   only. CA$0, about 10 minutes.
3. **Create the Postgres roles** (§2.3) from the runbook. CA$0, about 10 minutes.
4. **Approve the SP** under step-up. Then, on a later day after the shadow evidence, activate
   it. About 15 minutes each.

---

## 9. What this design does not claim

* It does not make Mode S safe for live issuance. Mode S is shadow only.
* Inside a shared database, it cannot prove that unsealed evidence rows are honest. It narrows
  that risk with independent recompilation, owner-attested physical evidence, frequency
  ceilings and a draft-only scope.
* It does not detect tail truncation of the newest chain rows from inside the database (only
  the issuer's in-process high-water mark helps, and that is lost on restart).
* It does not cover activation, pricing changes, ads or storefront writes. Each stays a
  separate per-decision owner grant.

---

## 9. Main's decisions and amendments (2026-11-12, binding on implementation)

These are integrator decisions under the owner directive "FINISH P0 AND ACTIVATE THE COMPANY". Where the sections above conflict with them, this section governs.

**M1. Going live (`store.activate`) is in P0 scope.** The owner's definition of P0 complete is "future eligible listings publish without recurring owner approval", and a buyer-invisible draft is not publishing. So:
- WS4 is delivered in two stages, and **both are P0**.
  - **Stage D** covers draft creation, as §1–§8 v1 describe.
  - **Stage A** covers activation, as the §1.5, §5.3 and §7.3 G-ACT "v2" material describes, and adds `EtsyClient.deactivate`.
- Stage A may not begin issuing until Stage D has passed its shadow gate. Its own shadow gate follows.
- The per-product `activation_authority` path stays in place as the fallback, and it is used whenever a product is out of policy.

**M2. Launch-0 and the first-customer rule stay as designed (§1.4).** The first real public listing goes through today's per-product, owner-approved path. The standing policy covers later eligible listings only. That still meets the acceptance list: "at least one approved Etsy listing" plus "a revocable standing policy for future listings".

**M3. WS4-0 comes first and stands alone as a security fix.** It moves the publication and activation grants from HMAC under the ops token to Ed25519 with a verify-only key on the worker. This closes F-A whether or not the policy is ever activated. It gets its own independent security review and its own deploy.

**M4. The service split is an owner decision.**
- Live standing issuance needs a separate issuer process (§2.1), which means a second Railway service and extra cost.
- Until the owner approves that, the policy runs in shadow only, deciding and recording but not issuing.
- Main will put the split, with its measured cost, in the owner checklist.
- Every Railway change is made through the owner-approved release path. None is made by Secondary.

**M5. Ceilings set in code (§1.2) are approved as drafted:**
- at most 3 grants per day;
- risk class B or lower;
- no ads;
- 7 days of shadow before activation.

The owner may tighten them. Changing a ceiling needs a reviewed code change.

**M6. Increment order for Secondary.** Each increment gets its own REVIEW-REQUEST, and each is reviewed independently against the §7 tests and mutants.
1. WS4-0 (Ed25519 migration)
2. the policy object and its chain
3. the owner signing flow
4. the pure in/out decision
5. the issuer in shadow mode
6. issue-time checks
7. use-time re-checks and single-use consumption
8. the stop watch
9. holds turned into owner cards
10. Stage D acceptance
11. Stage A: activation grant, `deactivate`, rollback
12. Stage A acceptance
