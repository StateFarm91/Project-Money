// ENG-CATALOGUE: per-department operating evidence (GET /api/cc/operating-evidence). Read-only;
// last USEFUL job, queues, WIP, dead letters, blocks. null/UNKNOWN shows as Unknown, never 0.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, statTile } from "../components.js";
import { relTime, utcStamp, UNKNOWN_TEXT } from "../format.js";
import { pageMeta } from "./_shared.js";

const txt = (v) => (v === null || v === undefined || v === "" || v === "UNKNOWN" ? UNKNOWN_TEXT : String(v));
const when = (iso) => (iso ? `${relTime(iso)} (${utcStamp(iso)})` : UNKNOWN_TEXT);
const age = (s) => (typeof s === "number" ? `${Math.round(s / 3600)} h` : "none waiting");

function fact(label, text) {
  return h("div", { class: "fact" }, h("dt", null, label), h("dd", null, text));
}

function lastUseful(lu) {
  if (!lu || lu.state === "UNKNOWN") return `Unknown${lu && lu.why ? `: ${lu.why}` : ""}`;
  if (lu.state === "NONE") return `none recorded${lu.why ? ` (${lu.why})` : ""}`;
  return `${lu.job_type} #${lu.job_id} · ${when(lu.finished_at)}`;
}

function deptRow(d) {
  const blocked = d.blocked === "UNKNOWN" ? "Unknown (suspensions could not be read)"
    : (Array.isArray(d.blocked) && d.blocked.length ? d.blocked.map((b) => `${b.job_type}: ${b.why}`).join("; ") : "not blocked");
  const ns = d.next_scheduled || {};
  const cad = ns.cadence === "UNKNOWN" ? UNKNOWN_TEXT : ns.cadence ? `${ns.cadence.cadence} ${when(ns.cadence.next_at)}` : "no cadence";
  return h("li", { class: "row", data: { department: d.department } },
    h("div", { class: "row-head" }, h("p", { class: "row-title" }, d.department), statusPill(d.state)),
    h("dl", { class: "facts" },
      fact("Agents", (d.agents || []).join(", ") || "none recorded"),
      fact("Last useful job", lastUseful(d.last_useful_job)),
      fact("Next scheduled", `${ns.pending_run_after ? `job ${when(ns.pending_run_after)}` : "no pending job"} · ${cad}`),
      fact("Queue", `${txt(d.queue && d.queue.waiting)} waiting · oldest ${age(d.queue && d.queue.oldest_age_s)}`),
      fact("In progress", txt(d.in_progress)),
      fact("Completed 24 h", d.completed_24h ? `${d.completed_24h.useful} useful · ${d.completed_24h.no_op} no-op` : UNKNOWN_TEXT),
      fact("Dead letters", d.dead_letters ? `${d.dead_letters.last_24h} in 24 h · ${d.dead_letters.open} open` : UNKNOWN_TEXT),
      fact("Blocked", blocked)));
}

export async function render() {
  const result = await api.operatingEvidence();
  const d = result.data || {};
  const depts = Array.isArray(d.departments) ? d.departments : null;
  const last = d.last_24h || null;
  const dead = d.dead_letters || null;
  const w = d.workers || {};
  const rec = d.recoveries || {};
  const stages = d.queue_by_stage || null;
  return h("div", { class: "stack" }, ...pageMeta(result, d),
    h("p", { class: "callout" }, "What each department really did, from the database. "
      + "A job counts only when it did useful work; a green health check is not evidence of work."),
    d.state === "UNKNOWN" && d.why ? h("p", { class: "callout callout-warn" }, `Unknown: ${d.why}`) : null,
    card({ title: "Last 24 hours", actions: statusPill(d.state || "UNKNOWN") },
      h("div", { class: "tiles", id: "ev-24h" },
        statTile("Useful jobs", last ? last.useful : null),
        statTile("No-op jobs", last ? last.no_op : null),
        statTile("Listing packages completed", last ? last.listing_packages_completed : null),
        statTile("Versions certified", last ? last.versions_certified : null),
        statTile("Recoveries", rec.state === "UNKNOWN" ? null : rec.last_24h),
        statTile("Open dead letters", dead ? dead.open : null, { status: dead && dead.open_defect ? "DEGRADED" : null })),
      last ? h("dl", { class: "facts" }, ...Object.entries(last.stage_transitions || {}).map(([k, v]) => fact(`Stage: ${k}`, String(v))))
        : null),
    card({ title: "Workers", subtitle: w.why || null, actions: statusPill(w.state || "UNKNOWN") },
      h("div", { class: "tiles", id: "ev-workers" }, statTile("Healthy", w.healthy), statTile("Unhealthy", w.unhealthy)),
      Array.isArray(w.items) && w.items.length ? h("ul", { class: "rows" }, ...w.items.map((i) => h("li", { class: "row" },
        h("p", { class: "row-title" }, `${i.component} · ${i.instance || "-"} · ${i.healthy ? "healthy" : `unhealthy: ${i.why}`} · ${when(i.last_heartbeat)}`)))) : null),
    card({ title: "Queue by stage" },
      stages === null ? h("p", { class: "callout callout-warn" }, "Unknown")
        : Object.keys(stages).length ? h("dl", { class: "facts" }, ...Object.entries(stages).map(([k, v]) => fact(k, `${v.waiting} waiting · oldest ${age(v.oldest_age_s)}`)))
          : h("p", { class: "muted" }, "Nothing waiting.")),
    card({ title: "Departments", labelId: "ev-departments" },
      depts === null ? h("p", { class: "callout callout-warn" }, "Unknown: the jobs could not be read.")
        : depts.length ? h("ul", { class: "rows" }, ...depts.map(deptRow)) : h("p", { class: "muted" }, "No job recorded yet.")),
    card({ title: "Recoveries", subtitle: rec.state === "UNKNOWN" ? `Unknown: ${txt(rec.why)}` : `${txt(rec.last_7d)} in 7 days · ${txt(rec.refused_24h)} refused in 24 h` },
      Array.isArray(rec.recent) && rec.recent.length ? h("ul", { class: "rows" }, ...rec.recent.map((r) => h("li", { class: "row" },
        h("p", { class: "row-title" }, `${r.action} · ${r.actor} · ${when(r.at)}`)))) : h("p", { class: "muted" }, "No recovery recorded.")));
}
