// S4b: the P0 command board (#/p0_board), read from GET /api/cc/p0-board. Read-only.
// Each section shows its state and the highest rung the running system proved, with the rule
// that proved it. INDEPENDENTLY REVIEWED and INTEGRATED are never shown as reached: the
// running system cannot read them, and the page says so. A null is Unknown, never 0.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, statTile } from "../components.js";
import { relTime, utcStamp, UNKNOWN_TEXT } from "../format.js";
import { pageMeta } from "./_shared.js";

const TITLES = {
  running: "Running build and health",
  shops: "The mandatory shops",  // the count is the Required tile (server-computed)
  opportunities: "Opportunities scored",
  development: "Products in development",
  releases: "Certified releases",
  assets: "PDFs and galleries",
  etsy: "Etsy drafts and live listings",
  sales: "Published and sales",
  costs: "Costs and API credits",
  blockers: "Open blockers and owners",
  agents: "Agents",
  research_sources: "Research sources and the research loop",
  concept_pool: "Concept pool (evidence-backed original concepts)",
};
const txt = (v) => (v === null || v === undefined || v === "" ? UNKNOWN_TEXT : String(v));
const when = (iso) => (iso ? `${relTime(iso)} (${utcStamp(iso)})` : UNKNOWN_TEXT);

function fact(label, text) {
  return h("div", { class: "fact" }, h("dt", null, label), h("dd", null, text));
}

function ladder(vocabulary, sec) {
  const reached = sec.level ? vocabulary.indexOf(sec.level) : -1;
  const notHere = new Set(sec.not_provable_here || []);
  return h("ol", { class: "ladder", aria: { label: "status level" } },
    ...vocabulary.map((rung, i) => {
      const rule = (sec.proved_by || {})[rung];
      const state = notHere.has(rung) ? "not readable here" : i <= reached ? "proved" : "not proved";
      return h("li", { class: ["ladder-rung", i <= reached && !notHere.has(rung) ? "is-reached" : null] },
        `${rung}: ${state}${rule ? ` (${rule})` : ""}`);
    }));
}

function rows(items, render, empty) {
  if (!Array.isArray(items) || !items.length) return h("p", { class: "muted" }, empty);
  return h("ul", { class: "rows" }, ...items.slice(0, 25).map(render));
}

const DETAIL = {
  running: (s) => h("dl", { class: "facts" },
    fact("Commit", txt(s.commit)), fact("Branch", txt(s.branch)),
    fact("Health", txt(s.health && s.health.state)),
    fact("Swept", when(s.health && s.health.swept_at)),
    fact("Why", txt(s.health && s.health.why))),
  shops: (s) => h("div", null,
    h("div", { class: "tiles" }, statTile("Required", s.required), statTile("Fresh", s.fresh),
      statTile("Failing", s.failing, { status: s.failing ? "DEGRADED" : null }),
      statTile("Failures unknown", s.failures_unknown, { status: s.failures_unknown ? "UNKNOWN" : null })),
    rows(s.shops, (r) => h("li", { class: "row" },
      h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${txt(r.owner_order)}. ${txt(r.alias)}`),
        statusPill(r.stale ? "STALE" : (typeof r.consecutive_failures !== "number" ? "UNKNOWN"
          : (r.consecutive_failures ? "DEGRADED" : "OK")))),
      h("dl", { class: "facts" },
        fact("Last attempted", when(r.last_attempted)), fact("Last successful", when(r.last_successful)),
        fact("Etsy source time", when(r.etsy_source_timestamp)),
        fact("Listings seen", txt(r.listings_seen_last_scan)),
        fact("Failures", `${txt(r.consecutive_failures)}${r.failure_class ? ` (${r.failure_class})` : ""}`),
        fact("Next scan", when(r.next_due)),
        fact("Downstream", r.downstream ? `${txt(r.downstream.mission_events)} mission events, ${txt(r.downstream.coverage_gaps)} gaps` : UNKNOWN_TEXT))),
    "No shop reading yet.")),
  opportunities: (s) => rows(s.scored, (r) => h("li", { class: "row" },
    h("p", { class: "row-title" }, `${r.slug} · ${r.state} · quality ${txt(r.quality)}`)), "No concept scored yet."),
  development: (s) => h("dl", { class: "facts" }, ...Object.entries(s.count_by_stage || {}).map(([k, v]) => fact(k, txt(v)))),
  releases: (s) => rows(s.certified, (r) => h("li", { class: "row" },
    h("p", { class: "row-title" }, `${r.slug}@${r.version} · ${txt(r.listing_state)} · Etsy ${txt(r.etsy_listing_id)}${r.listing_release_matches === false ? " · listing is not this release" : ""}`)),
    "No certified release yet."),
  assets: (s) => rows(s.not_proven, (r) => h("li", { class: "row" },
    h("p", { class: "row-title" }, `${txt(r.title)} · ${txt(r.status)}${r.gate ? ` · gate: ${r.gate}` : ""}`)), "Every readiness item is proven."),
  etsy: (s) => h("div", null,
    h("div", { class: "tiles" }, statTile("Drafts on Etsy", s.drafts_on_etsy),
      statTile("Not live on Etsy", s.not_live_on_etsy), statTile("Live on Etsy", s.live_on_etsy),
      statTile("With an Etsy id", s.remote_total)),
    rows(s.remote, (r) => h("li", { class: "row" }, h("p", { class: "row-title" }, `${r.slug}@${r.version} · ${r.state} · ${r.etsy_listing_id}`)), "No listing has an Etsy id yet.")),
  // Verdict 6990820438 M2: an unmeasured order source is Unknown (null), never 0 orders / $0.
  sales: (s) => h("div", null,
    s.why ? h("p", { class: "callout callout-warn" }, `Unknown: ${s.why}`) : null,
    h("div", { class: "tiles" }, statTile("Real orders", s.real_orders),
      statTile("Revenue (CA$)", s.revenue_cad), statTile("Last order", s.last_order_at ? relTime(s.last_order_at) : null)),
    s.recorded_countable_orders ? h("p", { class: "muted" },
      `At least ${s.recorded_countable_orders} countable order(s) are recorded${s.as_of ? `, ${s.as_of}` : ""}; the total is Unknown until the source is read.`) : null,
    s.counted ? h("p", { class: "muted" }, `Counted: ${s.counted}`) : null),
  costs: (s) => h("p", { class: "muted" }, s.note || ""),
  blockers: (s) => h("div", null,
    rows(s.owner_actions, (a) => h("li", { class: "row" }, h("p", { class: "row-title" },
      `Owner: ${a.action}${a.max_cost_cad !== null && a.max_cost_cad !== undefined ? ` · up to CA$${a.max_cost_cad}` : ""}${a.minutes ? ` · ${a.minutes} min` : ""}`)), "No owner action open."),
    rows(s.incidents, (i) => h("li", { class: "row" }, h("p", { class: "row-title" },
      `System: ${i.severity} ${i.family}${i.product ? ` · ${i.product}` : ""}${i.halts_publication ? " · halts publication" : ""}`)), "No incident open.")),
  agents: (s) => h("dl", { class: "facts" }, ...Object.entries(s.counts || {}).map(([k, v]) => fact(k, txt(v)))),
  // ENG-CONCEPTS-100: pool counts, held reasons by family, per shop and research requests.
  concept_pool: (s) => !s.counts ? h("p", { class: "callout callout-warn" }, `Unknown: ${txt(s.why)}`) : h("div", null,
    h("div", { class: "tiles" },
      statTile("evidence-backed", `${s.counts.evidence_backed} / ${s.counts.target}`, { status: s.counts.target_met ? null : "DEGRADED" }),
      ...["ready", "admitted", "held", "refused_clone_or_copy", "stale", "intake_approved", "engineered", "section_33_pool"].map((k) => statTile(k, s.counts[k]))),
    rows(Object.entries(s.held_reasons || {}), ([k, v]) => h("li", { class: "row" }, h("p", { class: "row-title" }, `Held · ${k}: ${v}`)), "Nothing held."),
    rows(Object.entries(s.by_family || {}), ([k, v]) => h("li", { class: "row" }, h("p", { class: "row-title" },
      `${k} · ${Object.entries(v).map(([st, n]) => `${st} ${n}`).join(" · ")}`)), "No family yet."),
    rows(Object.entries(s.by_shop || {}), ([k, v]) => h("li", { class: "row" }, h("p", { class: "row-title" },
      `${k} · evidence-backed ${txt(v.evidence_backed)} · admissible ${txt(v.admissible || 0)}`)), "No shop evidence yet."),
    (s.shops_without_signal || []).length ? h("p", { class: "callout" }, `No validated signal yet: ${s.shops_without_signal.join(", ")}`) : null,
    rows(s.research_requests, (r) => h("li", { class: "row" }, h("p", { class: "row-title" },
      `Research needed · ${r.pod} · ${r.ready_concepts} ready${r.priority_shop ? " · priority shop" : ""} · ${r.needs}`)), "No research request open.")),
  // ENG-RESEARCH: every registered source (shops by alias), then the loop and its conclusion.
  research_sources: (s) => h("div", null,
    h("div", { class: "tiles" }, ...Object.entries(s.counts || {}).map(([k, v]) =>
      statTile(k, v, { status: k === "scheduled" ? null : (v ? "DEGRADED" : null) }))),
    s.conclusion ? h("p", { class: "callout" }, `Latest conclusion (${txt(s.conclusion.at)}): ${txt(s.conclusion.outcome)}: ${txt(s.conclusion.why)}`)
      : h("p", { class: "callout callout-warn" }, "Unknown: no research conclusion recorded yet."),
    rows((s.loop || {}).stages, (r) => h("li", { class: "row" }, h("p", { class: "row-title" },
      `${r.pod} · ${r.stage}${r.held_because ? ` · ${r.held_because}` : ""}${(r.engineering || []).length ? ` · engineering: ${r.engineering.join(", ")}` : ""}`)),
      "No validated opportunity."),
    rows(s.sources, (r) => h("li", { class: "row" },
      h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${txt(r.id)} · ${txt(r.agent)} · ${txt(r.job_type)}`),
        statusPill(["OK", "STALE", "DEGRADED", "UNKNOWN"].includes(r.health) ? r.health : "UNKNOWN")),
      h("dl", { class: "facts" },
        fact("Method", txt(r.method)), fact("Status", `${txt(r.status)}: ${txt(r.why)}`),
        fact("Last attempt", when(r.last_attempt)), fact("Last success", when(r.last_success)),
        r.source_timestamp !== undefined ? fact("Source time", when(r.source_timestamp)) : null,
        r.listings_observed !== undefined ? fact("Listings observed", txt(r.listings_observed)) : null,
        r.changes_discovered !== undefined ? fact("Changes discovered", txt(r.changes_discovered)) : null,
        fact("Next scan", when(r.next_scan)),
        fact("Failures", r.consecutive_failures !== undefined
          ? `${txt(r.consecutive_failures)}${r.failure_class ? ` (${r.failure_class})` : ""}${r.backoff_until ? ` · backoff until ${utcStamp(r.backoff_until)}` : ""}`
          : `${txt(r.failures_7d)} in 7 days`),
        r.findings !== undefined ? fact("Downstream", r.findings === null ? "Unknown: no lineage recorded yet"
          : `${txt(r.findings)} findings · concepts: ${(r.concepts || []).join(", ") || "none"} · engineering: ${(r.engineering || []).join(", ") || "none"}`) : null)),
      "No source registered.")),
};

export async function render() {
  const result = await api.p0Board();
  const data = result.data || {};
  const vocabulary = Array.isArray(data.vocabulary) ? data.vocabulary : [];
  const sections = data.sections || {};
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    h("p", { class: "callout" },
      "Each level is the highest the running system can prove from its own records. "
      + "INDEPENDENTLY REVIEWED and INTEGRATED are review and branch facts it cannot read, so they are never shown as reached."),
    ...Object.keys(TITLES).map((name) => {
      const sec = sections[name];
      if (!sec) return card({ title: TITLES[name], actions: statusPill("UNKNOWN") }, h("p", { class: "callout callout-warn" }, "Unknown: not in the response."));
      const detail = sec.why && !sec.level ? h("p", { class: "callout callout-warn" }, `Unknown: ${sec.why}`)
        : (DETAIL[name] ? DETAIL[name](sec) : null);
      return card({ title: TITLES[name], subtitle: sec.level ? `Level: ${sec.level}` : "Level: Unknown",
        actions: statusPill(sec.state) }, detail, ladder(vocabulary, sec));
    }));
}
