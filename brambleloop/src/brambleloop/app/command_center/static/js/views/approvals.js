import { h, clear } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, sourcesList, guardedAction, toast, freshness, releaseNote } from "../components.js";
import { formatMoney, relTime, utcStamp, humanize, UNKNOWN_TEXT } from "../format.js";
import { sectionsOf, pageMeta, renderSection, backLink, tabStatus } from "./_shared.js";
import { rankDecisions, decideFirstCard } from "./_decisions.js";
import { approveAllCard } from "./_mission.js";

const FIELDS = [
  ["recommendation", "Agent recommendation"],
  ["uncertainty", "Uncertainty"],
  ["expected_benefit", "Expected benefit"],
  ["downside", "Downside"],
  ["max_spend_cad", "Max spend"],
  ["reversibility", "Reversibility"],
  ["deadline", "Deadline"],
  ["consequence_of_no_action", "If you do nothing"],
];

function fieldText(key, v) {
  if (key === "max_spend_cad") {
    return v === null || v === undefined ? UNKNOWN_TEXT : formatMoney({ value_cad: v, state: "MEASURED" });
  }
  if (key === "deadline") return v ? `${relTime(v)} (${utcStamp(v)})` : "No deadline";
  if (v === null || v === undefined || v === "") return null;
  return String(v);
}

function evidenceList(evidence) {
  const list = Array.isArray(evidence) ? evidence : [];
  return h("div", { class: "evidence", data: { evidence: String(list.length) } },
    h("h3", null, `Evidence (${list.length})`),
    list.length ? h("ul", { class: "rows" }, list.map((e) => {
      const ev = typeof e === "string" ? { label: e, source: e } : (e || {});
      return h("li", { class: "row" },
        h("div", { class: "row-head" }, h("p", { class: "row-title" }, ev.label || ev.source || "Evidence"),
          ev.state ? statusPill(ev.state === "PASS" ? "OK" : ev.state === "FAIL" ? "BLOCKED" : ev.state, ev.state) : null),
        ev.why ? h("p", { class: "row-detail" }, ev.why) : null,
        ev.source ? h("p", { class: "row-detail" }, h("a", { href: `#/drill/${encodeURIComponent(ev.source)}` }, `Source: ${ev.source}`)) : null);
    })) : h("p", { class: "callout callout-bad" }, "No evidence attached. Approval is disabled until evidence exists."));
}

function actionLabel(action) {
  const verb = String(action || "").split(".").pop();
  return { approve: "Approve", preview: "Preview", revoke: "Revoke", defer: "Defer", acknowledge: "Acknowledge" }[verb] || humanize(verb);
}

export function previewKey(action, params) {
  const p = params || {};
  return `${action}|${JSON.stringify(Object.keys(p).sort().map((k) => [k, p[k]]))}`;
}

export function isPreviewVerb(verb) {
  return /preview/.test(String(verb || ""));
}

export function fillPreviewParams(params, digests, previewParams) {
  const out = { ...(params || {}) };
  for (const [k, v] of Object.entries(out)) {
    const m = typeof v === "string" ? /^<from ([a-z_]+\.[a-z_]+)>$/.exec(v) : null;
    if (!m) continue;
    const pp = previewParams && previewParams[m[1]];
    const got = digests && pp !== undefined ? digests[previewKey(m[1], pp)] : undefined;
    if (typeof got !== "string" || !got) return null;
    out[k] = got;
  }
  return out;
}

function actionParams(a, reason) {
  const params = { ...(a.params || {}) };
  const ns = String(a.action || "").split(".")[0];
  if (ns === "improvement" || ns === "challenger") params.why = reason;
  else if (ns === "owner_action") params.note = reason;
  else params.reason = reason;
  return params;
}

function approvalCard(c, { stale, rerender, open = false, readAt = null }) {
  const evidence = Array.isArray(c.evidence) ? c.evidence : [];
  const actions = Array.isArray(c.actions) ? c.actions : [];
  const out = h("div", { class: "preview-out" });
  const digests = {};
  const previewParams = {};
  for (const a of actions) {
    if (isPreviewVerb(String(a.action || "").split(".").pop())) previewParams[a.action] = a.params || {};
  }
  const buttons = actions.map((a) => {
    const verb = String(a.action || "").split(".").pop();
    const isApprove = verb === "approve";
    const isPreview = isPreviewVerb(verb);
    const blocked = stale || (isApprove && (!evidence.length || c.executable === false));
    const btn = h("button", { type: "button", class: ["btn", isApprove ? "btn-primary" : verb === "revoke" ? "btn-danger" : null],
      disabled: blocked, data: { action: a.action || "" } }, a.label || actionLabel(a.action));
    btn.addEventListener("click", async () => {
      if (isPreview) {
        btn.disabled = true;
        const key = previewKey(a.action, a.params || {});
        delete digests[key];            // L2: a stale digest never survives a new preview
        try {
          const r = await api.action(a.action, a.params || {});
          const res = (r && r.result) || {};
          const dg = (typeof res.digest === "string" && res.digest) ? res.digest
            : (typeof res.review_digest === "string" && res.review_digest) ? res.review_digest : "";
          if (dg) digests[key] = dg;
          const shown = Array.isArray(res.display)
            ? res.display.map((d) => `${d.section}: ${d.state}`).join(" · ")
            : res.display;
          clear(out).append(h("div", { class: "callout callout-info" },
            h("p", { class: "answer" }, shown || "Preview generated."),
            dg ? h("p", { class: "mono" }, `Digest: ${dg}`) : null));
        } catch (e) { toast(e.message, "bad"); }
        finally { btn.disabled = false; }
        return;
      }
      if (fillPreviewParams(a.params, digests, previewParams) === null) {
        toast("Preview first: this approval binds the exact content the preview shows.", "bad");
        return;
      }
      const body = await guardedAction({
        title: `${a.label || actionLabel(a.action)}: ${c.title || "this proposal"}?`,
        lines: [c.proposed_action || "", `Max spend: ${fieldText("max_spend_cad", c.max_spend_cad)}`,
          `Reversibility: ${c.reversibility || "Not stated"}`].filter(Boolean),
        confirmLabel: actionLabel(a.action), danger: verb === "revoke",
        requiresStepUp: !!a.requires_step_up,
        reasonLabel: isApprove || a.requires_step_up ? "Why are you deciding this?" : "Note",
        reasonRequired: isApprove || !!a.requires_step_up,
        run: (reason) => api.action(a.action, actionParams({ ...a, params: fillPreviewParams(a.params, digests, previewParams) }, reason)),
        success: `${actionLabel(a.action)} recorded.`,
      });
      if (body) rerender();
    });
    return btn;
  });

  return h("article", { class: "card approval", data: { card: c.card_id || "" }, aria: { label: c.title || "Approval" } },
    h("header", { class: "card-head" },
      h("div", null, h("p", { class: "tile-label" }, c.kind || "DECISION"), h("h2", { class: "card-title" }, c.title || "Untitled proposal")),
      statusPill(c.executable === false ? "BLOCKED" : "PENDING", c.executable === false ? "NOT EXECUTABLE" : "AWAITING YOU")),
    h("p", { class: "card-meta" }, "Inbox read: ", freshness(c.as_of || readAt || null)),
    h("p", { class: "proposal" }, c.proposed_action || "Proposed action not stated."),
    h("details", { class: "review", open },
      h("summary", null, `Review evidence (${evidence.length}) and decide`,
        c.deadline ? h("span", { class: "muted small" }, ` · due ${relTime(c.deadline)}`) : null),
      h("dl", { class: "kv" }, FIELDS.map(([k, label]) => {
        const t = fieldText(k, c[k]);
        return h("div", { class: t === null ? "missing" : null }, h("dt", null, label), h("dd", null, t === null ? "Not provided" : t));
      })),
      evidenceList(evidence),
      c.executable === false ? h("p", { class: "callout callout-warn" }, c.not_executable_reason || "This cannot be executed from here.") : null,
      buttons.length ? h("div", { class: "btn-row" }, buttons) : null,
      out,
      sourcesList(c.sources)));
}

function decisionRow(d) {
  const kv = [["Why", d.why], ["Evidence", d.evidence], ["Max cost", d.max_cost || UNKNOWN_TEXT],
    ["If yes", d.consequence_of_yes], ["If no / delay", d.consequence_of_no],
    ["Minutes", typeof d.minutes === "number" ? String(d.minutes) : null]];
  return h("li", { class: "row" },
    h("p", { class: "row-title" }, d.decision || d.id || "Decision"),
    h("dl", { class: "kv" }, kv.map(([label, t]) => h("div", { class: t ? null : "missing" },
      h("dt", null, label), h("dd", null, t ? String(t) : "Not provided")))));
}

function batchesCard(env) {
  if (!env) return null;
  const batches = Array.isArray(env.items) ? env.items : [];
  if (!batches.length) {
    return card({ title: "Decision batches", actions: statusPill(env.status || "UNKNOWN") },
      h("p", { class: "muted" }, env.reason || "Unknown: no decision batches reported."));
  }
  const isLive = env.live === true;
  const extra = Array.isArray(env.release_only) ? env.release_only : [];
  return card({ title: "Your decisions, batch by batch", labelId: "approvals-batches", subtitle: `${env.decisions ?? UNKNOWN_TEXT} decisions in ${env.batches ?? batches.length} batches${isLive ? " · live owner queue" : ""}`, actions: statusPill(env.status) },
    h("p", { class: "card-meta" }, freshness(env.as_of || null), env.as_of ? ` (${utcStamp(env.as_of)})` : ""),
    isLive ? null : releaseNote(env),
    env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
    env.note ? h("p", { class: "muted small" }, env.note) : null,
    batches.map((b, i) => h("details", { class: "review", open: i === 0 },
      h("summary", null, h("strong", null, `${i + 1}. ${b.title || b.id}`),
        h("span", { class: "muted small" }, ` · ${b.decisions ?? UNKNOWN_TEXT} decision(s) · max ${b.max_cost || UNKNOWN_TEXT} · ${typeof b.minutes_total === "number" ? `${b.minutes_total} min` : "minutes unknown"}`)),
      b.why_batched ? h("p", { class: "muted small" }, b.why_batched) : null,
      h("ul", { class: "rows" }, (b.items || []).map(decisionRow)))),
    extra.length ? h("details", { class: "review release-only" },
      h("summary", null, h("strong", null, `Also in the release packet, not tracked live (${env.release_only_decisions ?? UNKNOWN_TEXT})`)),
      releaseNote(env),
      env.release_only_note ? h("p", { class: "muted small" }, env.release_only_note) : null,
      extra.map((b) => h("div", null, h("p", { class: "row-title" }, b.title || b.id),
        h("ul", { class: "rows" }, (b.items || []).map(decisionRow))))) : null,
    sourcesList(env.sources));
}

function releaseCard(env) {
  if (!env) return null;
  const items = Array.isArray(env.items) ? env.items : [];
  if (!env.pending) {
    return card({ title: "Release approval", labelId: "approvals-release", actions: statusPill("OK", "NO CANDIDATE") },
      h("p", { class: "card-meta" }, freshness(env.as_of || null)),
      h("p", { class: "muted" }, env.reason || "No release candidate is awaiting approval."),
      env.latest_deployed ? h("p", { class: "muted small" }, `Production runs ${String(env.latest_deployed).slice(0, 12)}.`) : null);
  }
  return card({ title: "Release approval", labelId: "approvals-release",
    subtitle: `Candidate ${String(env.candidate_sha || "").slice(0, 12)}: authorise the deploy on the production-window decision`,
    actions: statusPill(env.status, env.status === "OK" ? "READY TO AUTHORISE" : "NOT READY") },
  h("p", { class: "card-meta" }, freshness(env.as_of || null)),
  env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
  evidenceList(items),
  h("p", { class: "muted small" }, "Nothing deploys from this screen: the integrator deploys after your recorded authorisation, and the rollback target is the only commit a rollback may use."));
}

function notYetAskableCard(env) {
  if (!env) return null;
  const items = Array.isArray(env.items) ? env.items : [];
  if (!items.length) {
    return env.status === "OK" ? null : card({ title: "Not yet askable", actions: statusPill(env.status || "UNKNOWN") },
      h("p", { class: "muted" }, env.reason || "Unknown: not reported."));
  }
  return card({ title: "Not yet askable", subtitle: `${items.length} decision(s) wait on a precondition`, actions: statusPill(env.status) },
    h("p", { class: "card-meta" }, freshness(env.as_of || null)),
    h("ul", { class: "rows" }, items.map((it) => h("li", { class: "row" },
      h("p", { class: "row-title" }, it.what || it.gate),
      h("p", { class: "muted small" }, `Askable when: ${it.askable_when || UNKNOWN_TEXT}`)))),
    sourcesList(env.sources));
}

function adoptListingCard() {
  const inp = (id, placeholder) => h("input", { id, type: "text", placeholder, required: true });
  const lid = inp("adopt-listing-id", "Etsy listing id, from the listing URL");
  const slug = inp("adopt-slug", "e.g. hexagon-coaster-set");
  const version = inp("adopt-version", "e.g. 1.2.0");
  const release = inp("adopt-release", "certified release hash (64 hex)");
  const out = h("div", { class: "preview-out" });
  const row = (label, el) => h("label", { class: "field" }, h("span", null, label), el);
  const btn = h("button", { class: "btn btn-primary", type: "submit" }, "Adopt listing");
  const form = h("form", { class: "stack" }, row("Etsy listing id", lid), row("Product slug", slug),
    row("Version", version), row("Release hash", release), btn);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const params = { etsy_listing_id: lid.value.trim(), slug: slug.value.trim(),
      version: version.value.trim(), release: release.value.trim() };
    const body = await guardedAction({
      title: `Adopt Etsy listing ${params.etsy_listing_id} as ${params.slug}@${params.version}?`,
      lines: ["Reads the listing from Etsy and records what it holds; nothing is written to Etsy.",
        "Differences from the certified package are recorded and open a review item.",
        "Afterwards the system will not create another listing for this release."],
      confirmLabel: "Adopt", requiresStepUp: true, reasonLabel: "Why are you deciding this?",
      reasonRequired: true, run: (reason) => api.action("listing.adopt_manual", { ...params, reason }),
      success: "Adoption recorded.",
    });
    const res = (body && body.result) || null;
    if (!res) return;
    const diffs = Array.isArray(res.differences) ? res.differences : [];
    clear(out).append(h("div", { class: res.verification === "VERIFIED" && !diffs.length ? "callout callout-info" : "callout callout-warn" },
      h("p", { class: "answer" }, `${res.verification}${res.repeat ? " (already adopted)" : ""}: Etsy listing ${res.etsy_listing_id}`),
      diffs.length ? h("ul", null, diffs.map((d) => h("li", null, `${d.field}${d.note ? `: ${d.note}` : ""}`))) : null));
  });
  return card({ title: "Adopt a hand-made Etsy listing", labelId: "approvals-adopt",
    subtitle: "For a listing you published yourself in Shop Manager" }, form, out, baselineForm(lid, slug, version));
}

function baselineForm(lid, slug, version) {
  const out = h("div", { class: "preview-out" });
  let shown = null;
  const params = () => ({ etsy_listing_id: lid.value.trim(), slug: slug.value.trim(), version: version.value.trim() });
  const accept = h("button", { type: "button", class: "btn btn-primary", disabled: true }, "Accept live copy as baseline");
  const preview = h("button", { type: "button", class: "btn" }, "Preview live copy");
  preview.addEventListener("click", async () => {
    preview.disabled = true; accept.disabled = true; shown = null;
    try {
      const r = await api.action("listing.baseline_preview", params());
      shown = (r && r.result) || null;
      const refusals = (shown && shown.refusals) || [];
      const diffs = (shown && shown.differences_from_certified) || [];
      clear(out).append(h("div", { class: refusals.length ? "callout callout-bad" : "callout callout-info" },
        h("p", { class: "answer" }, refusals.length ? "Cannot be accepted:" : `Acceptable. Differs from the certified copy in ${diffs.length} field(s).`),
        refusals.length ? h("ul", null, refusals.map((x) => h("li", null, x))) : null,
        diffs.length ? h("ul", null, diffs.map((d) => h("li", null, `${d.field}${d.note ? `: ${d.note}` : ""}`))) : null,
        h("p", { class: "mono" }, `Digest: ${(shown && shown.digest) || ""}`)));
      accept.disabled = !(shown && shown.acceptable);
    } catch (e) { toast(e.message, "bad"); }
    finally { preview.disabled = false; }
  });
  accept.addEventListener("click", async () => {
    if (!shown) return;
    const body = await guardedAction({
      title: `Accept the live copy of Etsy listing ${shown.etsy_listing_id} as its baseline?`,
      lines: ["The daily census will compare this listing with exactly the copy you previewed.",
        "Only changes made after now will raise a drift incident."],
      confirmLabel: "Accept", requiresStepUp: true, reasonLabel: "Why are you deciding this?",
      reasonRequired: true,
      run: (reason) => api.action("listing.accept_baseline", { ...params(), expected_digest: shown.digest, reason }),
      success: "Baseline accepted.",
    });
    if (body) { accept.disabled = true; shown = null; }
  });
  return h("div", { class: "stack" }, h("h3", null, "Accept your Shop Manager edits as the baseline"),
    h("div", { class: "btn-row" }, preview, accept), out);
}

export async function render({ params, rerender }) {
  if (params[0]) {
    const result = await api.approval(params[0]);
    return h("div", { class: "stack" }, backLink("#/approvals", "All approvals"), ...pageMeta(result, result.data),
      approvalCard(result.data || {}, { stale: result.stale, rerender, open: true, readAt: (result.data && result.data.generated_at) || null }));
  }
  const [result, bulk] = await Promise.all([api.approvals(), approveAllCard({ rerender })]);
  const data = result.data || {};
  const all = Array.isArray(data.cards) ? data.cards : [];
  // APPROVE-ALL-V2: only OwnerAction rows are owner approvals; gates, grant and review cards
  // close through their own doors, folded apart and never counted.
  const own = (c) => String((c && c.card_id) || "").startsWith("owner_action:");
  const cards = all.filter(own);
  const doors = all.filter((c) => !own(c));
  const s = sectionsOf(data);
  const ranked = rankDecisions(cards, data.decision_batches);
  const order = new Map(ranked.filter((d) => d.kind === "card").map((d, i) => [d.id, i]));
  const sorted = cards.map((c, i) => [c, i]).sort(([a, ia], [b, ib]) =>
    (order.get(a && a.card_id) ?? ia) - (order.get(b && b.card_id) ?? ib) || ia - ib).map(([c]) => c);
  const toBatches = () => {
    const sec = document.querySelector("section[aria-labelledby='approvals-batches']");
    if (!sec) return;
    const first = sec.querySelector("details.review");
    if (first) first.open = true;
    sec.scrollIntoView({ block: "start" });
  };
  return h("div", { class: "stack" },
    ...pageMeta(result, data),
    data.reason ? tabStatus(data) : null,
    bulk,
    decideFirstCard(ranked, { limit: 3, onBatch: toBatches,
      meta: h("p", { class: "card-meta" }, "Inbox read: ", freshness(data.generated_at || null, { stale: result.stale, fetchedAt: result.fetchedAt })) }),
    sorted.length ? sorted.map((c, i) => approvalCard(c, { stale: result.stale, rerender, open: i === 0, readAt: data.generated_at || null }))
      : card({ title: "Nothing needs your decision" }, h("p", { class: "muted" }, "No approval cards are waiting. The company keeps working on everything that is not gated.")),
    doors.length ? h("details", null, h("summary", null, `Not owner actions: close through their own doors (${doors.length})`),
      ...doors.map((c) => approvalCard(c, { stale: result.stale, rerender, readAt: data.generated_at || null }))) : null,
    card({ title: "Etsy policy readings" }, h("p", null, h("a", { href: "#/policy" }, "Record your reading of each Etsy policy page"))),
    releaseCard(data.release),
    adoptListingCard(),
    batchesCard(data.decision_batches),
    notYetAskableCard(data.not_yet_askable),
    data.waiting_on_data !== undefined ? renderSection("waiting_on_data", data.waiting_on_data, { title: "Waiting on data", result }) : null,
    data.external_capability_unavailable !== undefined ? renderSection("external_capability_unavailable", data.external_capability_unavailable, { title: "External capability unavailable", result }) : null,
    ...Object.entries(s).map(([k, v]) => renderSection(k, v, { result })));
}
