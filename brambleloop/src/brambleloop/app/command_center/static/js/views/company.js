// COMPANY (W4-CC): how the whole company stands right now, on one phone screen. Every card says
// when it was read and on what basis; Unknown is shown as Unknown, never as 0.
import { h, icon } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, freshness, sourcesList, statTile } from "../components.js";
import { relTime, utcStamp, UNKNOWN_TEXT, humanize } from "../format.js";
import { sectionsOf, pageMeta, renderAll, isEnvelope } from "./_shared.js";

const STATE_ORDER = ["active", "sleeping", "blocked", "unhealthy", "UNKNOWN"];
const num = (v) => (typeof v === "number" ? v : null);
const when = (iso) => (iso ? `${relTime(iso)} (${utcStamp(iso)})` : UNKNOWN_TEXT);

function fact(label, text) {
  return h("div", { class: "fact" }, h("dt", null, label), h("dd", null, text));
}

function statusCard(env, result) {
  const it = isEnvelope(env) && env.items && env.items[0] ? env.items[0] : {};
  const d = it.departments || {};
  const build = it.build || {};
  const comp = it.completion_lanes || {};
  return h("section", { class: "card hero", aria: { label: "Company status" } },
    h("header", { class: "card-head" }, h("h2", { class: "card-title" }, "Company status"), statusPill(env && env.status)),
    h("p", { class: "card-meta" }, freshness(env && env.as_of, result)),
    env && env.reason ? h("p", { class: ["callout", env.status === "OK" ? "callout-info" : "callout-warn"] }, env.reason) : null,
    h("div", { class: "tiles tiles-hero" },
      statTile("Phase", it.phase ? String(it.phase).toUpperCase() : null),
      statTile("Build", build.commit_short ? String(build.commit_short).slice(0, 7) : null),
      statTile("Active depts", num(d.active), { href: "#/company/departments" }),
      statTile("Sleeping depts", num(d.sleeping)),
      statTile("Blocked depts", num(d.blocked), { status: num(d.blocked) ? "BLOCKED" : null }),
      statTile("Unhealthy depts", num(d.unhealthy), { status: num(d.unhealthy) ? "DEGRADED" : null }),
      statTile("Unknown depts", num(d.UNKNOWN), { status: num(d.UNKNOWN) ? "UNKNOWN" : null }),
      statTile("Decisions for you", num(it.owner_decisions_open), { href: "#/approvals" }),
      statTile("Open incidents", num(it.incidents_open), { href: "#/operations" }),
      statTile("Build 2 OPEN rows", num(it.build2_open)),
      statTile("Final Master launch-critical OPEN", num(it.final_master_launch_critical_open)),
      statTile("Lanes running", num(comp.RUNNING), { href: "#/completion" })),
    it.phase_why ? h("p", { class: "hero-note" }, `Phase: ${it.phase_why}`) : null,
    sourcesList(env && env.sources));
}

function unitRow(it) {
  const cur = it.current_job;
  const lu = it.last_useful_result;
  return h("li", { class: "row" },
    h("div", { class: "row-head" }, h("p", { class: "row-title" }, it.name || it.department || "Unknown"),
      statusPill(String(it.state || "UNKNOWN").toUpperCase(), it.state || "UNKNOWN")),
    it.why ? h("p", { class: "row-detail" }, it.why) : null,
    h("dl", { class: "facts" },
      fact("Current job", cur ? `${cur.job_type} (#${cur.job_id}, started ${when(cur.started_at)})` : (it.running_jobs === 0 || it.state === "sleeping" ? "None" : UNKNOWN_TEXT)),
      fact("Last useful result", lu ? `${lu.result || lu.job_type} · ${when(lu.finished_at)}` : UNKNOWN_TEXT),
      fact("Next wake", when(it.next_wake)),
      it.last_run !== undefined ? fact("Last run", when(it.last_run)) : null,
      typeof it.useful_24h === "number" ? fact("Useful jobs (24 h)", String(it.useful_24h)) : null));
}

function unitsCard(title, env, result, id) {
  const items = isEnvelope(env) && Array.isArray(env.items) ? env.items : [];
  const counts = (env && env.counts) || {};
  const sorted = [...items].sort((a, b) => STATE_ORDER.indexOf(a.state) - STATE_ORDER.indexOf(b.state));
  return card({ title, actions: statusPill(env && env.status), labelId: id },
    h("p", { class: "card-meta" }, freshness(env && env.as_of, result)),
    h("p", { class: "muted small" }, STATE_ORDER.map((s) => `${humanize(s)}: ${typeof counts[s] === "number" ? counts[s] : UNKNOWN_TEXT}`).join(" · ")),
    env && env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
    items.length ? h("ul", { class: "rows" }, sorted.map(unitRow)) : h("p", { class: "muted" }, "Unknown: nothing reported."),
    env && env.note ? h("p", { class: "muted small" }, env.note) : null,
    sourcesList(env && env.sources));
}

function closureCard(env, result) {
  const c = (env && env.closure) || null;
  const m = (env && env.maturity) || null;
  const hd = (env && env.headline) || null;
  const counts = (c && c.counts) || {};
  return card({ title: "Build 2 closure", actions: statusPill(env && env.status) },
    h("p", { class: "card-meta" }, freshness(env && env.as_of, result), env && env.refreshing ? " · refreshing" : ""),
    env && env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
    hd ? h("div", { class: "tiles" },
      statTile("PROVEN", num(hd.proven), { status: "OK" }),
      statTile("OWNER-GATED", num(hd.owner_gated), { status: "GATED" }),
      statTile("DATA-GATED", num(hd.data_gated), { status: "GATED" }),
      statTile("EXTERNAL-GATED", num(hd.external_gated), { status: "GATED" }),
      statTile("NOT-APPLICABLE", num(hd.not_applicable)),
      statTile("OPEN-DEFECT", num(hd.open_defects), { status: num(hd.open_defects) ? "DEGRADED" : "OK" }),
      statTile("Executable remaining (OPEN only)", num(hd.executable_remaining)),
      statTile("Total requirements", num(hd.total))) : null,
    hd && hd.basis ? h("p", { class: "muted small" }, hd.basis) : null,
    c ? h("details", { class: "sources" }, h("summary", null, "Closure matrix counts"),
      h("div", { class: "tiles" }, Object.entries(counts).map(([k, v]) => statTile(k, num(v))),
        statTile("Total requirements", num(c.total)), statTile("Gates read live", c.gates_checked_live ? "Yes" : "No"))) : null,
    m && m.highest_rung_reached ? h("details", { class: "sources" }, h("summary", null, "Maturity: highest rung reached"),
      h("dl", { class: "facts" }, Object.entries(m.highest_rung_reached).map(([k, v]) => fact(humanize(k), String(v))),
        fact("Production observed", m.is_production ? "Yes" : "No"))) : null,
    c && Array.isArray(c.open) && c.open.length ? h("details", { class: "sources" }, h("summary", null, `OPEN rows (${c.open.length})`),
      h("ul", null, c.open.slice(0, 40).map((r) => h("li", null, `#${r.id} ${r.title || ""}`)))) : null,
    env && env.note ? h("p", { class: "muted small" }, env.note) : null,
    sourcesList(env && env.sources));
}

function finalMasterCard(env, result) {
  const lc = (env && env.launch_critical) || {};
  const gk = (env && env.gated_by_kind) || {};
  return card({ title: "Final Master closure", actions: statusPill(env && env.status) },
    h("p", { class: "card-meta" }, freshness(env && env.read_at, result), " · ", env && env.as_of_basis ? env.as_of_basis : ""),
    env && env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
    h("div", { class: "tiles" },
      statTile("Launch-critical", num(env && env.launch_critical_total)),
      statTile("Complete", num(lc.COMPLETE), { status: "OK" }),
      statTile("Gated", num(lc.GATED), { status: "GATED" }),
      statTile("Open", num(lc.OPEN), { status: num(lc.OPEN) ? "DEGRADED" : "OK" }),
      statTile("Owner-gated", num(gk.owner)), statTile("Data-gated", num(gk.data)), statTile("External", num(gk.external)),
      statTile("Launch ready", env && typeof env.launch_ready === "boolean" ? (env.launch_ready ? "Yes" : "No") : null)),
    env && env.rule ? h("p", { class: "muted small" }, env.rule) : null,
    sourcesList(env && env.sources));
}

export async function render({ params }) {
  const result = await api.company();
  const data = result.data || {};
  const s = sectionsOf(data);
  const out = h("div", { class: "stack" }, ...pageMeta(result, data),
    statusCard(s.company_status, result),
    h("div", { class: "quick" },
      h("a", { class: "btn btn-primary", href: "#/laura" }, icon("laura", 18), "Talk to Laura"),
      h("a", { class: "btn", href: "#/completion" }, icon("approvals", 18), "Completion effort")),
    unitsCard("Departments", s.departments, result, "company-departments"),
    unitsCard("Agents", s.agents, result, "company-agents"),
    closureCard(s.build2_closure, result),
    finalMasterCard(s.final_master_closure, result),
    ...renderAll(data, [["blockers", "Blockers"], ["owner_actions", "Your actions"], ["approvals", "Approvals"],
      ["finance", "Finance"], ["store", "Store"], ["store_visibility", "Store visibility"], ["product_pipeline", "Product pipeline"],
      ["autonomy", "Autonomy"], ["learn", "Learn / improvement"], ["visual_stages", "Visual pipeline stages"], ["visual", "Visual R&D"],
      ["store_live_drift", "Live shop vs repo drafts"], ["competitor_intel", "Competitor findings"], ["laura", "Laura"],
      ["completion_effort", "Completion effort"]],
    { result, required: ["blockers", "finance", "store", "product_pipeline", "visual", "visual_stages"],
      skip: ["company_status", "departments", "agents", "build2_closure", "final_master_closure"] }));
  if (params && params[0] === "departments") {
    queueMicrotask(() => { const el = document.getElementById("company-departments"); if (el) el.scrollIntoView(); });
  }
  return out;
}
