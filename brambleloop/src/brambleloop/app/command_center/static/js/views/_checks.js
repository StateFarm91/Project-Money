// W4-ONDEMAND: "Run checks now". One card, shown on Home and Operations. Each button queues the
// same job the schedule runs (model probe, capabilities, Etsy key, offsite archive, continuity,
// certification, launch readiness), so the owner does not wait for the next cadence. Checks
// that call a third party ask for step-up. The server rate-limits and audits every run.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, guardedAction, statusPill } from "../components.js";
import { relTime } from "../format.js";

function lastLine(jobs) {
  const parts = [];
  for (const j of jobs || []) {
    const l = j.last;
    if (!l) { parts.push(`${j.cadence}: never run`); continue; }
    const verdict = l.ok === true ? "OK" : l.ok === false ? "not OK" : l.status;
    parts.push(`${verdict}${l.at ? `, ${relTime(l.at)}` : ""}${l.on_demand ? " (on demand)" : ""}`);
  }
  return parts.join(" · ");
}

function pillFor(jobs) {
  const lasts = (jobs || []).map((j) => j.last).filter(Boolean);
  if (!lasts.length) return statusPill("UNKNOWN", "Never run");
  if (lasts.some((l) => l.status === "pending" || l.status === "running")) return statusPill("PENDING", "Running");
  if (lasts.every((l) => l.ok === true || (l.ok === null && l.status === "done"))) return statusPill("OK", "OK");
  if (lasts.some((l) => l.ok === false || l.status === "dead" || l.status === "failed")) return statusPill("FAIL", "Not OK");
  return statusPill("UNKNOWN");
}

export async function checksCard({ rerender, stale } = {}) {
  let data;
  try { data = (await api.checks()).data || {}; }
  catch (e) {
    // W4-OWNERHOME merge fix: this block used to hold the "other cadences" code, so a failed
    // load threw on `data.other_cadences` (data undefined) and a successful one threw on
    // `more` (scoped to the catch) -- either way Home failed to render.
    return card({ title: "Run checks now", actions: statusPill("UNKNOWN") },
      h("p", { class: "muted" }, `Checks could not be loaded (${e.message || "error"}).`));
  }
  const others = Array.isArray(data.other_cadences) ? data.other_cadences : [];
  const pick = h("select", { id: "rerun-cadence", aria: { label: "Scheduled check" } },
    others.map((o) => h("option", { value: o.cadence }, `${o.cadence} (${o.job_type})`)));
  const rerun = h("button", { class: "btn btn-sm", type: "button", disabled: stale || !others.length,
    onclick: async () => {
      const r = await guardedAction({ title: `Re-run "${pick.value}" now?`,
        lines: ["Queues this scheduled job now. Refused if one is already running.",
          "Budgets, authority and rate limits still apply."],
        confirmLabel: "Re-run", requiresStepUp: true,
        run: () => api.rerunCycle(pick.value), success: "Queued." });
      if (r && rerender) rerender();
    } }, "Re-run");
  const more = others.length ? h("details", { class: "page-index" },
    h("summary", null, `Any other scheduled check · ${others.length}`),
    h("label", { class: "field", for: "rerun-cadence" }, "Scheduled check"), pick, rerun) : null;
  const rows = (data.checks || []).map((c) => {
    const btn = h("button", { class: "btn btn-sm", type: "button", disabled: stale || !c.available_now,
      onclick: async () => {
        const r = await guardedAction({ title: `Run "${c.label}" now?`,
          lines: [c.why || "Queues the scheduled check now.",
            c.external ? "Calls an outside service, so it asks you to confirm it is you." : "Runs inside the company only.",
            "Budgets, authority and rate limits still apply."],
          confirmLabel: "Run now", requiresStepUp: !!c.requires_stepup,
          run: () => api.runCheck(c.key), success: "Queued. The result appears here in a minute or two." });
        if (r && rerender) rerender();
      } }, c.available_now ? "Run now" : `Wait ${relTime(c.next_allowed_at)}`);
    return h("li", { class: "row" },
      h("div", { class: "row-main" },
        h("div", { class: "row-title" }, c.label, " ", pillFor(c.jobs)),
        h("p", { class: "muted" }, lastLine(c.jobs))),
      h("div", { class: "row-actions" }, btn));
  });
  return card({ title: "Run checks now", subtitle: "Run a scheduled check now instead of waiting for it. Each check has a short cool-down between runs." },
    h("ul", { class: "rows" }, rows), more);
}
