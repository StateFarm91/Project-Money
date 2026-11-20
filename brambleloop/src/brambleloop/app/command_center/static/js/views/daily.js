// ENG-DAILY: per-UTC-day production counts and today's zero-output diagnoses. Read-only.
// UNKNOWN is a sparkline gap and the word Unknown, never 0. Rows come with the panel.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill as P, barChart } from "../components.js";
import { UNKNOWN_TEXT } from "../format.js";
import { pageMeta } from "./_shared.js";

const num = (v) => (typeof v === "number" ? v : null);
const txt = (v) => (v == null || v === "UNKNOWN" ? UNKNOWN_TEXT : String(v));
const muted = (t) => h("p", { class: "muted" }, t);

// "invert" rows are bad when high, "neutral" (spend) neither; a stage row follows its
// reading, so not yet due is never DEGRADED; any other 0 reads "None today".
function pill(t, mode, r) {
  if (t == null || t === "UNKNOWN") return P("UNKNOWN");
  if (mode === "invert") return t ? P("DEGRADED", `${t} today`) : P("OK", "None today");
  if (mode === "neutral") return P("INFO", "Recorded");
  if (r === "zero_output") return P("DEGRADED", "Zero output");
  if (r === "not_yet_due") return P("INFO", "Not yet due");
  return t ? P("OK") : P("INFO", "None today");
}

function line(label, m, days, mode, r) {
  const d = (m || {}).days || {}, t = d[days[days.length - 1]];
  return h("li", { class: "row" },
    h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${label}: today ${txt(t)}`), pill(t, mode, r)),
    barChart(days.map((x) => num(d[x])), { labels: days, label, height: 24 }),
    m && m.basis ? muted(m.basis) : null);
}

function diagnosis(d) {
  const cause = (c) => h("li", null, [c.kind, c.job_type, c.hold, c.upstream ? `upstream ${c.upstream}` : null, c.why,
    (c.top_reasons || []).map((r) => `${r.reason} x${r.count}`).join(", ") || null].filter(Boolean).join(" · "));
  return h("li", { class: "row" }, h("p", { class: "row-title" }, `${d.stage}: today ${txt(d.today)}`),
    h("ul", null, ...(d.causes || []).map(cause)),
    ...(d.actions || []).map((a) => muted(`Action ${a.action}${a.job_type ? ` ${a.job_type}` : ""}: ${a.enqueued ? "taken" : `not taken (${txt(a.why)})`}`)),
    ...(d.ecrs || []).map((e) => muted(e.filed ? `Change request #${e.id}` : "Change request pending ENG-IMPROVE")));
}

export async function render() {
  const result = await api.daily();
  const data = result.data || {};
  const led = data.ledger || {}, days = led.days || [], m = led.metrics || {};
  const recorded = Array.isArray(data.diagnoses) ? data.diagnoses : [];
  const diag = recorded.length ? recorded : (data.live_zero_stages || []);
  const reads = data.stage_readings || [];
  const by = Object.fromEntries(reads.map((r) => [r.metric, r.status]));
  const notDue = reads.filter((r) => r.status === "not_yet_due").map((r) => r.stage);
  const list = (xs) => h("ul", { class: "rows" }, ...xs);
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    h("p", { class: "callout" }, led.unknown_rule || "Unknown is never 0."),
    card({ title: "Today's zero-output diagnoses", subtitle: recorded.length ? "Recorded" : "Live reading, not yet recorded" },
      diag.length ? list(diag.map(diagnosis)) : muted("No stage is at zero output."),
      notDue.length ? muted(`Not yet due today: ${notDue.join(", ")}`) : null),
    card({ title: "Daily production", subtitle: `${days[0] || ""} to ${days[days.length - 1] || ""} UTC` },
      list((data.rows || []).map(([k, label, mode]) => line(label, m[k], days, mode, by[k])))),
    card({ title: "Products advanced per stage" }, list(Object.keys(m).filter((k) => k.startsWith("advanced:")).map((k) => line(k.slice(9), m[k], days)))),
    card({ title: "Scans per shop" }, Array.isArray(led.shops) ? list(led.shops.map((s) => line(`${s.owner_order}. ${txt(s.alias)}${s.registered ? "" : " (not registered)"}`,
      { days: s.succeeded, basis: s.basis }, days))) : h("p", { class: "callout callout-warn" }, "Unknown: shops unreadable.")));
}
