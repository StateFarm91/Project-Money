// W4-LAUNCHFIX: Etsy policy page readings from the owner's phone (#/policy).
// One card per watched source: its URL (tap to open in your own browser), its state, and the
// questions to answer. Recording needs step-up and goes through the same server path as the
// operator intake (record_page_reading): only the SHA-256 of the pasted text is kept, and the
// reader is the signed-in owner. Nothing is pre-filled. A later reading whose text differs is a
// policy change: it opens the review card in Approvals and blocks publishing until reviewed.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, guardedAction, toast } from "../components.js";
import { pageMeta } from "./_shared.js";

const STATE_LABEL = { never_read: "Never read", fresh: "Fresh", stale: "Stale",
  changed_unreviewed: "Changed: review needed" };
const STATE_STATUS = { never_read: "UNKNOWN", fresh: "OK", stale: "DEGRADED", changed_unreviewed: "BLOCKED" };

function field(label, input) {
  return h("div", null, h("label", { class: "field", for: input.id }, label), input);
}

function stateLine(s) {
  const bits = [STATE_LABEL[s.state] || s.state];
  if (s.checked_on) bits.push(`read ${s.checked_on}`);
  if (s.read_by) bits.push(`by ${s.read_by}`);
  if (s.version) bits.push(`version ${s.version}`);
  return bits.join(" · ");
}

function historyList(s) {
  const rows = Array.isArray(s.history) ? s.history : [];
  if (!rows.length) return h("p", { class: "muted small" }, "No reading by a person yet.");
  const KIND = { baseline: "Baseline (first reading)", change: "Change", same_as_before: "Same as before" };
  return h("ul", { class: "rows" }, rows.map((r) => h("li", null,
    `${r.checked_on || "?"} · ${KIND[r.kind] || r.kind} · by ${r.read_by || "?"} · fingerprint ${r.digest || "?"}`,
    r.kind === "change" ? (r.reviewed_at ? ` · reviewed ${r.reviewed_at.slice(0, 10)}` : " · NOT REVIEWED") : "",
    r.attested ? ` · you confirmed: "${r.attested.confirmed}"` : "")));
}

function sourceCard(s, limits, reload) {
  const id = (k) => `pr-${s.source}-${k}`;
  const fetched = s.way_in === "help_center_api";
  const text = fetched ? null : h("textarea", { id: id("text"), rows: 6,
    placeholder: "On the page: Select all, Copy, then paste here" });
  const version = h("input", { id: id("version"), type: "text", maxLength: limits.version_max,
    placeholder: "the page's 'last updated' date, else the day you read it" });
  const summary = h("textarea", { id: id("summary"), rows: 5, maxLength: limits.summary_max,
    placeholder: "Your answers to the questions above, in your own words" });
  const checked = h("input", { id: id("checked"), type: "date" });
  const confirm = h("input", { id: id("confirm"), type: "checkbox" });
  const btn = h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
    if ((!fetched && !text.value.trim()) || !summary.value.trim()) { toast(fetched ? "Write your answers." : "Paste the page text and write your answers.", "bad"); return; }
    if (!confirm.checked) { toast("Tick the confirmation: it records what you personally did.", "bad"); return; }
    if (version.value.length > limits.version_max) { toast(`Version is at most ${limits.version_max} characters.`, "bad"); return; }
    const payload = { source: s.source, version: version.value.trim(), summary: summary.value.trim(),
      checked_on: checked.value || "", confirm: s.confirm_with };
    if (fetched) payload.fetch_article = true; else payload.text = text.value;
    const r = await guardedAction({ title: `Record your reading of ${s.title}?`,
      lines: [fetched ? "The system fetches the article text from Etsy's public Help Center API; only its fingerprint (SHA-256) is kept."
        : "Only a fingerprint (SHA-256) of the pasted text is kept, never the text.",
        `You are recorded as the reader, with your confirmation: "${s.confirm_with}".`,
        "Your first reading of a page is its baseline. If a later reading differs, it is a policy change: publishing stops until you review it in Approvals."],
      confirmLabel: "Record reading", requiresStepUp: true,
      run: () => api.recordPolicyReading(payload),
      success: "Reading recorded." });
    if (r) {
      if (text) text.value = "";
      if (r.kind === "change") toast("Recorded as a CHANGE since your last reading: review it in Approvals.", "bad");
      else if (r.kind === "baseline") toast("Recorded as this page's baseline.");
      reload();
    }
  } }, "Record reading");
  return card({ title: s.title, subtitle: s.source, actions: statusPill(STATE_STATUS[s.state] || "UNKNOWN", STATE_LABEL[s.state]) },
    h("p", null, h("a", { href: s.url, target: "_blank", rel: "noopener noreferrer" }, "Open the official page"), " ", h("span", { class: "muted small" }, s.url)),
    h("p", { class: "card-meta" }, stateLine(s)),
    s.note ? h("p", { class: "muted small" }, s.note) : null,
    s.review ? h("p", { class: "callout callout-warn" }, "A change is waiting for your review. ",
      h("a", { href: "#/approvals" }, "Open Approvals")) : null,
    h("details", { class: "review" }, h("summary", null, "Questions to answer"),
      h("ol", null, (s.questions || []).map((q) => h("li", null, q)))),
    h("details", { class: "review" }, h("summary", null, "Record a reading"),
      h("div", { class: "stack" },
        fetched ? h("p", { class: "muted small" }, "This is a Help Center article: the system fetches its text from Etsy when you record. Read it at the link above, then answer.")
          : field("Page text (only its fingerprint is kept)", text),
        field("Version", version), field("Your answers", summary), field("Date you read it (blank = today)", checked),
        h("label", { class: "field", for: confirm.id }, confirm, ` ${s.confirm_with}`), btn)),
    h("details", { class: "review" }, h("summary", null, "History"), historyList(s)));
}

export async function render({ rerender } = {}) {
  const result = await api.policyReadings();
  const data = result.data || {};
  const sources = Array.isArray(data.sources) ? data.sources : [];
  const limits = { version_max: data.version_max || 120, summary_max: data.summary_max || 8000 };
  const reload = rerender || (() => {});
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    card({ title: "Policy readings", subtitle: `Read each page in your own browser and record it. A reading is current for ${data.max_age_days || 30} days.` },
      h("p", { class: "muted small" }, "Step-up required to record. Nothing is sent to Etsy."),
      data.baseline_rule ? h("p", { class: "muted small" }, data.baseline_rule) : null),
    sources.length ? sources.map((s) => sourceCard(s, limits, reload))
      : card({ title: "Unknown" }, h("p", { class: "muted" }, "The server did not report any watched source.")));
}
