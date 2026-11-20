// ENG-DEMAND-SUPPLY: what the market buys (stored evidence only) and which engine to build
// next. Read-only. An UNKNOWN reading says Unknown; it is never shown as 0.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill as P } from "../components.js";
import { pageMeta } from "./_shared.js";

const muted = (t) => h("p", { class: "muted" }, t);
const list = (xs) => h("ul", { class: "rows" }, ...xs);
const pct = (v) => (typeof v === "number" ? v.toFixed(2) : "Unknown");
const pill = (s) => (s === "MEASURED" ? P("OK", "Measured") : s === "PARTIAL" ? P("INFO", "Partial") : P("UNKNOWN"));

function engineRow(e) {
  return h("li", { class: "row" },
    h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${e.rank}. ${e.engine}: ${e.count} concept(s) waiting`), P("DEGRADED", `demand ${pct(e.top_demand)}`)),
    muted(`Build: ${e.build}`),
    muted((e.concepts || []).slice(0, 6).map((c) => `${c.slug} (${pct(c.demand)})`).join(", ")));
}

function scoreRow(label, r) {
  return h("li", { class: "row" },
    h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${label}: ${pct(r.score)}${r.core ? " · core" : ""}`), pill(r.status)),
    muted(`confidence ${pct(r.confidence)} · ${r.observations || 0} reading(s)${(r.shops || []).length ? ` · ${r.shops.length} shop(s)` : ""}`));
}

function poolRow(r) {
  return h("li", { class: "row" },
    h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${r.slug} · ${r.cluster} · ${pct(r.demand)}`),
      r.buildable ? P("OK", `Engine ${r.engine}`) : P("DEGRADED", `Needs ${r.engine}`)),
    r.buildable ? null : muted(r.needs || ""));
}

export async function render() {
  const result = await api.demand();
  const data = result.data || {};
  const engines = data.engines || [];
  const counts = data.pool_counts || {};
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    h("p", { class: "callout" }, data.rule || "Unknown is never 0."),
    card({ title: "Build this engine next", subtitle: "Concepts waiting for an engine, ranked by demand" },
      engines.length ? list(engines.map(engineRow)) : muted("No concept is waiting for an engine.")),
    card({ title: "Demand by family", subtitle: "Owner core families: amigurumi, baby, cushions, garments" },
      list((data.families || []).map((f) => scoreRow(f.family, f)))),
    card({ title: "Top demand clusters", subtitle: "family / form / subject" },
      (data.clusters || []).length ? list(data.clusters.slice(0, 20).map((c) => scoreRow(c.cluster, c))) : muted("Unknown: no stored readings yet.")),
    card({ title: "Concept pool by engine", subtitle: `${counts.buildable ?? "Unknown"} buildable, ${counts.held ?? "Unknown"} waiting for an engine` },
      list((data.pool || []).map(poolRow))));
}
