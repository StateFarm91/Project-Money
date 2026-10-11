// W4-OWNERHOME: the six-block owner overview on Home (server: command_center/overview.py).
// Each block: one headline, at most five compact rows, and an expandable evidence list, so the
// owner reads the company in one phone screen per block instead of scrolling records.
// Honesty rules are the app's: a value the server could not read is "Unknown", never 0.
import { h } from "../dom.js";
import { card, freshness, statusPill } from "../components.js";
import { relTime, utcStamp, UNKNOWN_TEXT } from "../format.js";

const ROW_FIELDS = {
  working: (r) => [r.title, r.verified_at ? `verified ${relTime(r.verified_at)} · ${r.verified_basis || ""}` : UNKNOWN_TEXT],
  blocked: (r) => [r.title, `${typeof r.count === "number" ? r.count : UNKNOWN_TEXT} waiting`],
  accomplished: (r) => [r.title, `${r.count}× · ${r.detail || "result not described"}`],
  ready: (r) => [r.title, `${r.publication || UNKNOWN_TEXT} · cert ${r.certified ? "yes" : "no"} · PDF ${stateOf(r.pdf)} · images ${stateOf(r.images)}`],
  money: (r) => [r.title, r.display || UNKNOWN_TEXT],
};

function stateOf(x) {
  return x && x.state ? String(x.state) : UNKNOWN_TEXT;
}

function compactRow(key, r) {
  const [title, value] = (ROW_FIELDS[key] || ((x) => [x.title, x.detail || ""]))(r || {});
  return h("li", { class: "ov-row" },
    h("span", { class: "ov-row-title" }, title || UNKNOWN_TEXT),
    h("span", { class: ["ov-row-value", value === UNKNOWN_TEXT ? "is-unknown" : null] }, value),
    r && r.status && r.status !== "OK" ? statusPill(r.status) : null);
}

function evidenceRow(r) {
  const at = r.verified_at || r.at || r.built_at || null;
  const parts = [];
  if (r.detail) parts.push(String(r.detail));
  if (r.why && r.why !== r.detail) parts.push(String(r.why));
  if (r.pdf) parts.push(`PDF: ${stateOf(r.pdf)}${r.pdf.why ? ` (${r.pdf.why})` : ""}`);
  if (r.images) parts.push(`Images: ${stateOf(r.images)}${r.images.why ? ` (${r.images.why})` : ""}`);
  if (Array.isArray(r.agents) && r.agents.length) parts.push(`agents: ${r.agents.join(", ")}`);
  return h("li", { class: "ov-ev" },
    h("p", { class: "ov-ev-title" }, r.title || UNKNOWN_TEXT, r.status ? [" ", statusPill(r.status)] : null),
    parts.length ? h("p", { class: "ov-ev-detail" }, parts.join(" · ")) : null,
    h("p", { class: "ov-ev-meta" },
      at ? h("time", { datetime: at, title: utcStamp(at) }, `${relTime(at)}`) : "time: unknown",
      r.source ? ` · source: ${r.source}` : ""));
}

function evidence(list, label = "Evidence") {
  const rows = Array.isArray(list) ? list : [];
  return h("details", { class: "ov-evidence" },
    h("summary", null, `${label} (${rows.length})`),
    rows.length ? h("ul", { class: "ov-ev-list" }, rows.map(evidenceRow))
      : h("p", { class: "muted small" }, "No evidence rows: nothing was read for this block."));
}

/** One block card. `extra` nodes render after the rows (e.g. agent activity). */
export function overviewBlock(b, { stale = false, fetchedAt = null, extra = null } = {}) {
  if (!b || typeof b !== "object") return null;
  const items = Array.isArray(b.items) ? b.items : [];
  return card({ title: b.title || b.key, cls: `ov-block ov-${b.key}`, labelId: `ov-${b.key}`,
    actions: statusPill(b.status || "UNKNOWN") },
  h("p", { class: "ov-headline" }, b.headline || (b.reason ? `Unknown: ${b.reason}` : UNKNOWN_TEXT)),
  items.length ? h("ul", { class: "ov-rows" }, items.map((r) => compactRow(b.key, r))) : null,
  extra,
  h("p", { class: "card-meta" }, freshness(b.as_of || null, { stale, fetchedAt }),
    b.href ? [" · ", h("a", { href: b.href }, "Open")] : null),
  evidence(b.evidence));
}

/** Block 3 extension: ranks 4-5 of the same ranked list Decide first shows (compact rows). */
export function nextDecisions(ranked, { from = 3, to = 5 } = {}) {
  const rest = (Array.isArray(ranked) ? ranked : []).slice(from, to);
  if (!rest.length) return null;
  return h("details", { class: "ov-evidence ov-next-decisions" },
    h("summary", null, rest.length === 1 ? `Next decision, ranked #${from + 1}` : `Next ${rest.length} decisions, ranked #${from + 1}–#${from + rest.length}`),
    h("ul", { class: "ov-ev-list" }, rest.map((d, i) => h("li", { class: "ov-ev" },
      h("p", { class: "ov-ev-title" }, `#${from + i + 1} `, h("a", { href: d.kind === "card" && d.id ? `#/approvals/${encodeURIComponent(d.id)}` : "#/approvals" }, d.title)),
      h("p", { class: "ov-ev-detail" }, `Max cost: ${d.cost} · If you do nothing: ${d.consequence || "Not provided"}`)))));
}

function agentList(b) {
  const agents = Array.isArray(b.agents) ? b.agents : null;
  if (!agents) return null;
  const counts = b.agents_counts || {};
  return h("div", { class: "ov-agents" },
    h("p", { class: "ov-sub" }, `Agent activity (24 h): ${typeof counts.active_24h === "number" ? counts.active_24h : UNKNOWN_TEXT} of ${typeof counts.ran_24h === "number" ? counts.ran_24h : UNKNOWN_TEXT} agents that ran produced useful results`),
    agents.length ? h("ul", { class: "ov-rows" }, agents.slice(0, 5).map((a) => h("li", { class: "ov-row" },
      h("span", { class: "ov-row-title" }, a.title),
      h("span", { class: "ov-row-value" }, `${a.useful_24h} useful · ${a.no_work_24h} no work`)))) : null);
}

/** The blocks in the server's order, minus `decisions` (Home renders Decide first for it). */
export function overviewBlocks(ov, { stale = false, fetchedAt = null } = {}) {
  if (!ov || typeof ov !== "object" || !ov.blocks) {
    return [card({ title: "Owner overview", cls: "ov-block", actions: statusPill("UNKNOWN") },
      h("p", { class: "muted" }, `Unknown: the overview was not reported${ov && ov.reason ? ` (${ov.reason})` : ""}.`))];
  }
  const order = Array.isArray(ov.order) ? ov.order : Object.keys(ov.blocks);
  return order.filter((k) => k !== "decisions").map((k) => overviewBlock(ov.blocks[k],
    { stale, fetchedAt, extra: k === "money" ? agentList(ov.blocks[k]) : null }));
}
