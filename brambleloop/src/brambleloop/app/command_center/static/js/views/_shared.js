// Helpers shared by tab views: turning a lane C tab response into honest cards.
import { h, icon } from "../dom.js";
import { envelopeCard, statusPill, freshness, staleBanner, statTile, moneyTile, itemRow, sourcesList, card } from "../components.js";
import { humanize, UNKNOWN_TEXT, relTime, utcStamp, formatMoney } from "../format.js";

export function isEnvelope(v) {
  return v && typeof v === "object" && !Array.isArray(v) && "status" in v && ("items" in v || "reason" in v || "as_of" in v);
}
export function isMoney(v) {
  return v && typeof v === "object" && !Array.isArray(v) && ("value_cad" in v || ("state" in v && "display" in v));
}

export function sectionsOf(data) {
  return (data && typeof data.sections === "object" && data.sections) || {};
}

/** Page header: generated_at freshness, stale banner. */
export function pageMeta(result, data) {
  const at = (data && (data.generated_at || data.as_of)) || null;
  const stale = !!(result && result.stale);
  const fetchedAt = result && result.fetchedAt;
  return [staleBanner(result),
    h("p", { class: "card-meta page-meta" }, at || stale ? freshness(at || fetchedAt, { stale, fetchedAt })
      : h("time", { datetime: fetchedAt || "", title: utcStamp(fetchedAt) }, `Loaded ${relTime(fetchedAt)}`))];
}

/**
 * Render one named section of a tab, whatever honest shape it has: an envelope, a money value,
 * a scalar, a list or a plain object. A missing section renders as Unknown, not as absent.
 */
export function renderSection(name, value, { title = null, result = null, limit = 20, asOf = null } = {}) {
  const label = title || humanize(name);
  const opts = { stale: result && result.stale, fetchedAt: result && result.fetchedAt, limit };
  // W4-CCFIN: a section that is not an envelope carries no as_of of its own; it was read when
  // the tab was generated, so it shows that reading time (never no timestamp at all).
  const meta = () => h("p", { class: "card-meta" }, freshness(asOf || (result && result.fetchedAt) || null, opts));
  if (value === undefined || value === null) {
    return card({ title: label, actions: statusPill("UNKNOWN") }, meta(), h("p", { class: "muted" }, "Unknown: this section was not reported."));
  }
  if (isEnvelope(value)) return envelopeCard(label, value, opts);
  const tileWithMeta = (tile) => { tile.append(h("p", { class: "tile-meta" }, freshness(asOf || (result && result.fetchedAt) || null, opts))); return h("div", { class: "tiles" }, tile); };
  if (isMoney(value)) return tileWithMeta(moneyTile(label, value));
  if (typeof value !== "object") return tileWithMeta(statTile(label, value));
  if (Array.isArray(value)) {
    return card({ title: label }, meta(),
      value.length ? h("ul", { class: "rows" }, value.slice(0, limit).map((it) => itemRow(it))) : h("p", { class: "muted" }, "None."));
  }
  return objectCard(label, value, { meta: meta() });
}

/** A plain object as a fact list (nested envelopes/arrays rendered beneath). */
export function objectCard(title, obj, { actions = null, meta = null } = {}) {
  const facts = [];
  const nested = [];
  for (const [k, v] of Object.entries(obj || {})) {
    if (k === "sources") continue;
    if (isEnvelope(v)) { nested.push(envelopeCard(humanize(k), v)); continue; }
    if (isMoney(v)) { facts.push([k, formatMoney(v)]); continue; }
    if (Array.isArray(v)) {
      nested.push(h("div", { class: "sub" }, h("h3", { class: "section-title" }, humanize(k)),
        v.length ? h("ul", { class: "rows" }, v.slice(0, 30).map((it) => itemRow(it))) : h("p", { class: "muted" }, "None.")));
      continue;
    }
    if (v && typeof v === "object") { nested.push(objectCard(humanize(k), v)); continue; }
    let text = v === null || v === undefined ? UNKNOWN_TEXT : typeof v === "boolean" ? (v ? "Yes" : "No") : String(v);
    if (typeof v === "string" && /(_at|_until|^at|deadline|time)$/i.test(k) && !Number.isNaN(Date.parse(v))) text = `${relTime(v)} (${utcStamp(v)})`;
    facts.push([k, text]);
  }
  return card({ title, actions }, meta,
    facts.length ? h("dl", { class: "facts" }, facts.map(([k, t]) => h("div", { class: "fact" }, h("dt", null, humanize(k)), h("dd", null, t)))) : null,
    ...nested,
    Array.isArray(obj && obj.sources) ? sourcesList(obj.sources) : null);
}

/** Collapsible section summary: "Completed · 4 · OK", expanding to the envelope's rows. */
export function sectionDetails(title, env) {
  const items = env && Array.isArray(env.items) ? env.items : [];
  const status = env ? String(env.status || "UNKNOWN").toUpperCase() : "UNKNOWN";
  const count = status === "UNKNOWN" && !items.length ? UNKNOWN_TEXT : String(items.length);
  return h("details", { class: "brief-item" },
    h("summary", null, h("span", { class: "brief-title" }, title), h("span", { class: "brief-count" }, count), statusPill(status)),
    env && env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
    items.length ? h("ul", { class: "rows" }, items.slice(0, 15).map((it) => itemRow(it))) : h("p", { class: "muted" }, status === "UNKNOWN" ? "Unknown: no data." : "Nothing."),
    env ? sourcesList(env.sources) : null);
}

export function backLink(href, label) {
  return h("a", { class: "back", href }, icon("back", 18), label);
}

/** "/cc/#/approvals/x" or "#/approvals/x" -> "#/approvals/x"; anything else -> null. */
export function toHashRoute(deepLink) {
  const s = String(deepLink || "");
  const i = s.indexOf("#/");
  if (i < 0) return null;
  const prefix = s.slice(0, i);
  if (prefix && prefix !== "/cc/" && prefix !== "/cc" && prefix !== "./") return null;
  return s.slice(i);
}

const META_KEYS = new Set(["tab", "generated_at", "sections", "sources", "status", "reason", "provider"]);

/**
 * Render a lane C tab response: the named `order` first (from sections, else top-level), then
 * every remaining section and top-level field, so nothing the API reports is silently dropped.
 * A key in `required` that is absent renders as Unknown; other absent keys are skipped.
 */
export function renderAll(data, order, { result = null, required = [], skip = [], limit = 20 } = {}) {
  const s = sectionsOf(data);
  const done = new Set([...skip, ...META_KEYS]);
  const out = [];
  const take = (k) => (s[k] !== undefined ? s[k] : data ? data[k] : undefined);
  const asOf = (data && (data.generated_at || data.as_of)) || null;
  for (const [k, title] of order) {
    done.add(k);
    const v = take(k);
    if (v === undefined && !required.includes(k)) continue;
    out.push(renderSection(k, v, { title, result, limit, asOf }));
  }
  for (const [k, v] of Object.entries(s)) if (!done.has(k)) { done.add(k); out.push(renderSection(k, v, { result, limit, asOf })); }
  for (const [k, v] of Object.entries(data || {})) if (!done.has(k) && v !== null && v !== undefined) out.push(renderSection(k, v, { result, limit, asOf }));
  return out;
}

/** Top-of-tab status/reason line, when the tab reports one. */
export function tabStatus(data) {
  if (!data || (!data.status && !data.reason)) return null;
  const st = String(data.status || "UNKNOWN").toUpperCase();
  return h("p", { class: ["callout", st === "OK" ? "callout-info" : "callout-warn"] }, `${st}${data.reason ? `: ${data.reason}` : ""}`);
}
