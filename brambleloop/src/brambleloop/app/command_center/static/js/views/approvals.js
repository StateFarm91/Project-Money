// APPROVALS (F-885 evidence-backed inbox, F-886 one-tap actions, F-887 step-up).
import { h, clear } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, sourcesList, guardedAction, toast } from "../components.js";
import { formatMoney, relTime, utcStamp, humanize, UNKNOWN_TEXT } from "../format.js";
import { sectionsOf, pageMeta, renderSection, backLink, tabStatus } from "./_shared.js";

// Every field F-885 requires on a card, in reading order. A missing one is shown as missing.
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

function actionParams(a, reason) {
  const params = { ...(a.params || {}) };
  const ns = String(a.action || "").split(".")[0];
  if (ns === "improvement" || ns === "challenger") params.why = reason;
  else if (ns === "owner_action") params.note = reason;
  else params.reason = reason;
  return params;
}

function approvalCard(c, { stale, rerender, open = false }) {
  const evidence = Array.isArray(c.evidence) ? c.evidence : [];
  const actions = Array.isArray(c.actions) ? c.actions : [];
  const out = h("div", { class: "preview-out" });
  const buttons = actions.map((a) => {
    const verb = String(a.action || "").split(".").pop();
    const isApprove = verb === "approve";
    const isPreview = verb === "preview";
    const blocked = stale || (isApprove && (!evidence.length || c.executable === false));
    const btn = h("button", { type: "button", class: ["btn", isApprove ? "btn-primary" : verb === "revoke" ? "btn-danger" : null],
      disabled: blocked, data: { action: a.action || "" } }, actionLabel(a.action));
    btn.addEventListener("click", async () => {
      if (isPreview) {
        btn.disabled = true;
        try {
          const r = await api.action(a.action, a.params || {});
          const res = (r && r.result) || {};
          clear(out).append(h("div", { class: "callout callout-info" },
            h("p", { class: "answer" }, res.display || "Preview generated."),
            res.digest ? h("p", { class: "mono" }, `Digest: ${res.digest}`) : null));
        } catch (e) { toast(e.message, "bad"); }
        finally { btn.disabled = false; }
        return;
      }
      const body = await guardedAction({
        title: `${actionLabel(a.action)}: ${c.title || "this proposal"}?`,
        lines: [c.proposed_action || "", `Max spend: ${fieldText("max_spend_cad", c.max_spend_cad)}`,
          `Reversibility: ${c.reversibility || "Not stated"}`].filter(Boolean),
        confirmLabel: actionLabel(a.action), danger: verb === "revoke",
        requiresStepUp: !!a.requires_step_up,
        reasonLabel: isApprove ? "Why are you approving this?" : "Note",
        reasonRequired: isApprove,
        run: (reason) => api.action(a.action, actionParams(a, reason)),
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

// W4-OWNER: the owner's decisions consolidated into batches, answered batch by batch. Every
// decision states why, evidence, max cost (UNKNOWN when not costed, never CA$0), yes / no-or-
// delay consequence and minutes. Read-only here: deciding happens on the cards below.
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
  return card({ title: "Your decisions, batch by batch", subtitle: `${env.decisions ?? UNKNOWN_TEXT} decisions in ${env.batches ?? batches.length} batches`, actions: statusPill(env.status) },
    h("p", { class: "card-meta" }, env.as_of ? `As of ${relTime(env.as_of)} (${utcStamp(env.as_of)})` : "As of: Unknown"),
    env.note ? h("p", { class: "muted small" }, env.note) : null,
    batches.map((b, i) => h("details", { class: "review", open: i === 0 },
      h("summary", null, h("strong", null, `${i + 1}. ${b.title || b.id}`),
        h("span", { class: "muted small" }, ` · ${b.decisions ?? UNKNOWN_TEXT} decision(s) · max ${b.max_cost || UNKNOWN_TEXT} · ${typeof b.minutes_total === "number" ? `${b.minutes_total} min` : "minutes unknown"}`)),
      b.why_batched ? h("p", { class: "muted small" }, b.why_batched) : null,
      h("ul", { class: "rows" }, (b.items || []).map(decisionRow)))),
    sourcesList(env.sources));
}

// W4-GATESB: decisions not asked yet, each with what makes it askable (never a card to answer).
function notYetAskableCard(env) {
  if (!env) return null;
  const items = Array.isArray(env.items) ? env.items : [];
  if (!items.length) {
    return env.status === "OK" ? null : card({ title: "Not yet askable", actions: statusPill(env.status || "UNKNOWN") },
      h("p", { class: "muted" }, env.reason || "Unknown: not reported."));
  }
  return card({ title: "Not yet askable", subtitle: `${items.length} decision(s) wait on a precondition`, actions: statusPill(env.status) },
    h("ul", { class: "rows" }, items.map((it) => h("li", { class: "row" },
      h("p", { class: "row-title" }, it.what || it.gate),
      h("p", { class: "muted small" }, `Askable when: ${it.askable_when || UNKNOWN_TEXT}`)))),
    sourcesList(env.sources));
}

export async function render({ params, rerender }) {
  if (params[0]) {
    const result = await api.approval(params[0]);
    return h("div", { class: "stack" }, backLink("#/approvals", "All approvals"), ...pageMeta(result, result.data),
      approvalCard(result.data || {}, { stale: result.stale, rerender, open: true }));
  }
  const result = await api.approvals();
  const data = result.data || {};
  const cards = Array.isArray(data.cards) ? data.cards : [];
  const s = sectionsOf(data);
  return h("div", { class: "stack" },
    ...pageMeta(result, data),
    data.reason ? tabStatus(data) : null,
    batchesCard(data.decision_batches),
    notYetAskableCard(data.not_yet_askable),
    cards.length ? cards.map((c, i) => approvalCard(c, { stale: result.stale, rerender, open: i === 0 }))
      : card({ title: "Nothing needs your decision" }, h("p", { class: "muted" }, "No approval cards are waiting. The company keeps working on everything that is not gated.")),
    data.waiting_on_data !== undefined ? renderSection("waiting_on_data", data.waiting_on_data, { title: "Waiting on data", result }) : null,
    data.external_capability_unavailable !== undefined ? renderSection("external_capability_unavailable", data.external_capability_unavailable, { title: "External capability unavailable", result }) : null,
    ...Object.entries(s).map(([k, v]) => renderSection(k, v, { result })));
}
