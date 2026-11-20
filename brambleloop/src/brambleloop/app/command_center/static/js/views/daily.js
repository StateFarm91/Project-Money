// ENG-DAILY: per-UTC-day production counts and today's zero-output diagnoses. Read-only.
// UNKNOWN is a gap in the sparkline and the word Unknown, never 0.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, barChart } from "../components.js";
import { UNKNOWN_TEXT } from "../format.js";
import { pageMeta } from "./_shared.js";

const ROWS = [["scans_succeeded", "Competitor scans"], ["concepts_created", "Concepts created"],
  ["concepts_approved", "Concepts admitted by intake"], ["concepts_admitted", "Concepts admitted to engineering"],
  ["concepts_held", "Concepts held"], ["products_started", "Products started"],
  ["certifications", "Certified"], ["pdfs_us", "US PDFs"], ["pdfs_uk", "UK PDFs"],
  ["images_generated", "Images generated"], ["images_recovered", "Images recovered"],
  ["images_verified", "Images verified"], ["galleries_completed", "Galleries completed"],
  ["listing_packages", "Listing packages"], ["etsy_drafts", "Etsy drafts"], ["etsy_live", "Live on Etsy"],
  ["lessons_learned", "Lessons learned"], ["lessons_applied", "Lessons applied"],
  ["failures", "Failures", "invert"], ["dead_letters", "Dead letters", "invert"], ["spend_cad", "Spend (CA$)", "neutral"]];
const num = (v) => (typeof v === "number" ? v : null);
const txt = (v) => (v === null || v === undefined || v === "UNKNOWN" ? UNKNOWN_TEXT : String(v));

// The pill: Failures and Dead letters are bad when high; Spend is neutral; a stage row
// follows its reading (zero output is DEGRADED, not yet due is never DEGRADED); any other
// row reads "None today" for a 0, never DEGRADED.
function pill(today, mode, reading) {
  if (today === "UNKNOWN" || today === undefined || today === null) return statusPill("UNKNOWN");
  if (mode === "invert") return today ? statusPill("DEGRADED", `${today} today`) : statusPill("OK", "None today");
  if (mode === "neutral") return statusPill("INFO", "Recorded");
  if (reading === "zero_output") return statusPill("DEGRADED", "Zero output");
  if (reading === "not_yet_due") return statusPill("INFO", "Not yet due");
  return today ? statusPill("OK") : statusPill("INFO", "None today");
}

function line(label, m, days, mode, reading) {
  const vals = days.map((d) => num(((m || {}).days || {})[d]));
  const today = ((m || {}).days || {})[days[days.length - 1]];
  return h("li", { class: "row" },
    h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${label}: today ${txt(today)}`),
      pill(today, mode, reading)),
    barChart(vals, { labels: days, label, height: 24 }),
    m && m.basis ? h("p", { class: "muted" }, m.basis) : null);
}

function cause(c) {
  const bits = [c.kind, c.job_type, c.hold, c.upstream ? `upstream ${c.upstream}` : null, c.why,
    (c.top_reasons || []).map((r) => `${r.reason} x${r.count}`).join(", ") || null];
  return h("li", null, bits.filter(Boolean).join(" · "));
}

function diagnosis(d) {
  return h("li", { class: "row" }, h("p", { class: "row-title" }, `${d.stage}: today ${txt(d.today)}`),
    h("ul", null, ...(d.causes || []).map(cause)),
    ...(d.actions || []).map((a) => h("p", { class: "muted" }, `Action ${a.action}${a.job_type ? ` ${a.job_type}` : ""}: ${a.enqueued ? "taken" : `not taken (${txt(a.why)})`}`)),
    ...(d.ecrs || []).map((e) => h("p", { class: "muted" }, e.filed ? `Change request #${e.id}` : "Change request pending ENG-IMPROVE")));
}

export async function render() {
  const result = await api.daily();
  const data = result.data || {};
  const led = data.ledger || {};
  const days = led.days || [];
  const m = led.metrics || {};
  const recorded = Array.isArray(data.diagnoses) ? data.diagnoses : [];
  const diag = recorded.length ? recorded : (data.live_zero_stages || []);
  const adv = Object.keys(m).filter((k) => k.startsWith("advanced:"));
  const readings = Array.isArray(data.stage_readings) ? data.stage_readings : [];
  const byMetric = Object.fromEntries(readings.map((r) => [r.metric, r.status]));
  const notDue = readings.filter((r) => r.status === "not_yet_due").map((r) => r.stage);
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    h("p", { class: "callout" }, led.unknown_rule || "Unknown is never 0."),
    card({ title: "Today's zero-output diagnoses", subtitle: recorded.length ? "Recorded" : "Live reading, not yet recorded" },
      diag.length ? h("ul", { class: "rows" }, ...diag.map(diagnosis)) : h("p", { class: "muted" }, "No stage is at zero output."),
      notDue.length ? h("p", { class: "muted" }, `Not yet due today: ${notDue.join(", ")}`) : null),
    card({ title: "Daily production", subtitle: `${days[0] || ""} to ${days[days.length - 1] || ""} UTC` },
      h("ul", { class: "rows" }, ...ROWS.map(([k, label, mode]) => line(label, m[k], days, mode, byMetric[k])))),
    card({ title: "Products advanced per stage" }, h("ul", { class: "rows" }, ...adv.map((k) => line(k.slice(9), m[k], days)))),
    card({ title: "Scans per shop" }, Array.isArray(led.shops) ? h("ul", { class: "rows" },
      ...led.shops.map((s) => line(`${s.owner_order}. ${txt(s.alias)}${s.registered ? "" : " (not registered)"}`,
        { days: s.succeeded, basis: s.basis }, days))) : h("p", { class: "callout callout-warn" }, "Unknown: shops unreadable.")));
}
