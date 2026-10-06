// MONEY (F-914 dashboard) and financial drill-through (F-915).
// Rules: UNKNOWN renders "Unknown" (never CA$0.00); estimated/modelled figures carry a visible
// basis tag; every tile links to its source rows.
import { h, clear } from "../dom.js";
import { api } from "../api.js";
import { card, moneyTile, statusPill, freshness, basisTag, basisNote, sourcesList, itemRow } from "../components.js";
import { formatMoney, humanize, UNKNOWN_TEXT, relTime, utcStamp } from "../format.js";
import { sectionsOf, pageMeta, renderSection, renderAll, tabStatus, isMoney, backLink } from "./_shared.js";

const PERIODS = [["month", "This month"], ["last_month", "Last month"], ["ytd", "Year to date"], ["all", "All time"]];
const MONEY_SECTIONS = [["accounting", "Accounting (controller)"], ["revenue", "Revenue"], ["recorded_spend", "Recorded spend"]];

function metricKey(item, fallback) {
  return String(item.metric || item.key || item.id || item.name || fallback);
}

/** Pull money tiles out of an envelope's items: an item that is money, or carries one. */
function moneyItems(env) {
  const tiles = [];
  const rest = [];
  for (const [i, it] of (env && Array.isArray(env.items) ? env.items : []).entries()) {
    if (!it || typeof it !== "object") { rest.push(it); continue; }
    let value = null;
    if (isMoney(it)) value = it;
    else for (const k of ["value", "amount", "money", "total"]) if (isMoney(it[k])) { value = it[k]; break; }
    if (value) tiles.push({ key: metricKey(it, i), label: it.label || it.title || humanize(metricKey(it, i)), value, item: it });
    else rest.push(it);
  }
  return { tiles, rest };
}

function moneySection(name, title, env, result, period) {
  if (!env) return renderSection(name, env, { title, result });
  const { tiles, rest } = moneyItems(env);
  if (!tiles.length) return renderSection(name, env, { title, result });
  const status = String(env.status || "UNKNOWN").toUpperCase();
  return card({ title, actions: statusPill(status) },
    h("p", { class: "card-meta" }, freshness(env.as_of, result), ...basisNote(env.basis, status)),
    env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
    h("div", { class: "tiles" }, tiles.map((t) => moneyTile(t.label, t.value, {
      drillHref: `#/money/drill/${encodeURIComponent(t.key)}${period ? `?period=${encodeURIComponent(period)}` : ""}` }))),
    rest.length ? h("ul", { class: "rows" }, rest.map((it) => itemRow(it))) : null,
    sourcesList(env.sources));
}

function legend() {
  return h("details", { class: "card legend" },
    h("summary", null, "How to read these numbers"),
    h("ul", null,
      h("li", null, h("strong", null, "Actual"), " is measured from source records (orders, payouts, receipts)."),
      h("li", null, h("strong", null, "Estimated / Modelled"), " is a calculation or forecast, not booked money."),
      h("li", null, h("strong", null, "Unknown"), " means a source is missing or disconnected. It is NOT zero. CA$0.00 only ever means a measured zero.")));
}

async function renderDrill(metric, period) {
  const result = await api.moneyDrill(metric, period);
  const d = result.data || {};
  const rows = Array.isArray(d.rows) ? d.rows : Array.isArray(d.items) ? d.items : [];
  const cols = [];
  for (const r of rows.slice(0, 20)) for (const k of Object.keys(r || {})) if (!cols.includes(k) && cols.length < 6 && k !== "sources") cols.push(k);
  const status = String(d.status || (rows.length ? "OK" : "UNKNOWN")).toUpperCase();
  const cell = (k, v) => {
    if (isMoney(v)) return h("td", { class: "num" }, formatMoney(v));
    if (typeof v === "number" && /(_cad|amount)$/i.test(k)) return h("td", { class: "num" }, formatMoney({ value_cad: v, state: "MEASURED" }));
    if (v === null || v === undefined) return h("td", null, UNKNOWN_TEXT);
    if (typeof v === "string" && /(_at|date|^at)$/i.test(k)) return h("td", { title: utcStamp(v) }, relTime(v));
    if (typeof v === "string" && /(source|ref)$/i.test(k)) return h("td", null, h("a", { href: `#/drill/${encodeURIComponent(v)}` }, v));
    return h("td", null, typeof v === "object" ? JSON.stringify(v) : String(v));
  };
  return h("div", { class: "stack" },
    backLink("#/money", "Money"),
    ...pageMeta(result, d),
    card({ title: d.label || humanize(metric), subtitle: "Why this number exists", actions: statusPill(status) },
      d.value !== undefined ? h("div", { class: "tiles" }, moneyTile("Value", d.value)) : null,
      h("p", { class: "card-meta" }, freshness(d.as_of, result), " · ", basisTag(d.basis || "unknown")),
      d.reason ? h("p", { class: "callout callout-warn" }, d.reason) : null,
      rows.length ? h("div", { class: "table-wrap" }, h("table", null,
        h("caption", { class: "muted" }, `${rows.length} source record${rows.length === 1 ? "" : "s"}`),
        h("thead", null, h("tr", null, cols.map((c) => h("th", { class: /(_cad|amount)$/i.test(c) ? "num" : null }, humanize(c))))),
        h("tbody", null, rows.map((r) => h("tr", null, cols.map((c) => cell(c, r ? r[c] : null)))))))
        : h("p", { class: "muted" }, status === "UNKNOWN" ? "Unknown: no source records are available for this metric." : "No source records."),
      Array.isArray(d.corrections) && d.corrections.length ? h("div", null, h("h3", { class: "section-title" }, "Corrections"),
        h("ul", { class: "rows" }, d.corrections.map((c) => itemRow(c)))) : null,
      sourcesList(d.sources)));
}

function sourceHealthCard(sh) {
  if (!sh || typeof sh !== "object") return null;
  const measured = sh.order_source_measured === true;
  return card({ title: "Source health", actions: statusPill(measured ? "OK" : "DEGRADED", measured ? "CONNECTED" : "NOT CONNECTED") },
    sh.warning ? h("p", { class: "callout callout-warn" }, sh.warning) : null,
    sh.why ? h("p", { class: "muted" }, sh.why) : null,
    h("p", { class: "card-meta" }, sh.last_read_at ? `Last read ${relTime(sh.last_read_at)} (${utcStamp(sh.last_read_at)})` : "Never read"));
}

export async function render({ params, query }) {
  const period = query.get("period") || "";
  if (params[0] === "drill" && params[1]) return renderDrill(params[1], period);
  const result = await api.money(period);
  const data = result.data || {};
  const s = sectionsOf(data);
  const echoed = data.period || (s.accounting && s.accounting.period) || null;
  const seg = h("div", { class: "seg", role: "group", aria: { label: "Period" } },
    PERIODS.map(([k, label]) => h("a", { class: "btn", href: `#/money?period=${k}`,
      aria: { current: (period || "month") === k ? "true" : null } }, label)));
  const q = period ? `?period=${encodeURIComponent(period)}` : "";
  const headline = [["revenue", "Revenue"], ["profit", "Profit"], ["recorded_spend", "Recorded spend"]]
    .filter(([k]) => data[k] !== undefined);
  return h("div", { class: "stack" },
    ...pageMeta(result, data),
    tabStatus(data),
    headline.length ? card({ title: "Headline", subtitle: "Tap a figure to see the records behind it." },
      h("div", { class: "tiles" }, headline.map(([k, label]) => moneyTile(isMoney(data[k]) && data[k].label ? data[k].label : label,
        isMoney(data[k]) ? data[k] : null, { drillHref: `#/money/drill/${k}${q}` })))) : null,
    sourceHealthCard(data.source_health),
    card({ title: "Period" }, seg,
      h("p", { class: "muted" }, echoed ? `Showing: ${echoed}` : period ? "The server did not confirm this period filter, so figures may be for its default period." : "Server default period.")),
    ...MONEY_SECTIONS.filter(([k]) => s[k] !== undefined || k === "accounting").map(([k, t]) => moneySection(k, t, s[k], result, period)),
    ...renderAll(data, [["spend_limits", "Spend limits"]], { result,
      skip: [...MONEY_SECTIONS.map(([k]) => k), "revenue", "profit", "recorded_spend", "source_health", "period"] }),
    legend());
}
