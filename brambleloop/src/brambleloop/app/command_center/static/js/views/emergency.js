// EMERGENCY CONTROLS (F-889). Pausing is always one confirmation away and never needs step-up;
// resuming loosens a control, so it requires step-up (contract §4). Read-only monitoring,
// evidence and recovery are never paused.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, guardedAction } from "../components.js";
import { humanize } from "../format.js";
import { pageMeta, backLink } from "./_shared.js";

function control({ label, detail, paused, scope, department, stale, rerender, pausable = true }) {
  const btn = paused
    ? h("button", { class: "btn btn-primary", type: "button", disabled: stale, data: { control: `resume:${scope}:${department || ""}` },
      onclick: async () => {
        const ok = await guardedAction({ title: `Resume ${label}?`, lines: ["Resuming lets this part of the company act again. It does not move the company phase up."],
          confirmLabel: "Resume", requiresStepUp: true, reasonLabel: "Why resume now?", reasonRequired: true,
          run: (reason) => api.resume(scope, reason, department), success: `${label} resumed.` });
        if (ok) rerender();
      } }, "Resume")
    : h("button", { class: "btn btn-danger", type: "button", disabled: stale || !pausable, data: { control: `pause:${scope}:${department || ""}` },
      onclick: async () => {
        const ok = await guardedAction({ title: `Pause ${label} now?`, lines: ["Takes effect immediately. Monitoring, evidence and recovery keep running."],
          confirmLabel: "Pause now", danger: true, reasonLabel: "Reason",
          run: (reason) => api.pause(scope, reason || "owner pause from command center", department), success: `${label} paused.` });
        if (ok) rerender();
      } }, "Pause");
  return h("div", { class: "control" },
    h("div", { class: "control-text" }, h("strong", null, label), " ", statusPill(paused ? "PAUSED" : "ACTIVE"), detail ? h("p", null, detail) : null),
    btn);
}

function neverPaused(v) {
  if (Array.isArray(v)) return v.map((k) => [String(k), null]);
  if (v && typeof v === "object") return Object.entries(v).map(([k, why]) => [k, why ? String(why) : null]);
  return [["monitoring", null], ["evidence", null], ["recovery", null]];
}

export async function render({ rerender }) {
  const result = await api.emergency();
  const d = result.data || {};
  const stale = !!result.stale;
  const phase = d.phase && typeof d.phase === "object" ? d.phase.phase : d.phase;
  const depts = Array.isArray(d.departments) ? d.departments : [];
  const spend = d.spend || {};
  const pub = d.publishing || {};
  const kill = h("button", { class: "btn btn-danger btn-block", type: "button", disabled: stale, data: { control: "kill" },
    onclick: async () => {
      const ok = await guardedAction({ title: "Return the company to SHADOW and pause everything?",
        lines: ["This records an owner phase transition down to shadow and pauses every pausable department, all spend and all publishing.",
          "Monitoring, evidence collection and recovery keep running."],
        confirmLabel: "Return to shadow", danger: true, reasonLabel: "Reason", reasonRequired: true,
        run: (reason) => api.kill(reason), success: "Company returned to shadow and paused." });
      if (ok) rerender();
    } }, "Kill switch: return to shadow");
  return h("div", { class: "stack" }, backLink("#/account", "Account"), ...pageMeta(result, d),
    card({ title: "Company phase", actions: statusPill(phase ? "INFO" : "UNKNOWN", phase ? String(phase).toUpperCase() : "UNKNOWN") },
      h("p", { class: "muted" }, "Moving the phase up is never done here; it stays on the evidence-bound owner phase route."),
      kill),
    card({ title: "Publishing & spend", cls: "card-danger" },
      control({ label: "Publishing", detail: pub.live_grants && pub.live_grants.length ? `${pub.live_grants.length} live grant(s) will be revoked` : "No live grants", paused: !!pub.paused, scope: "publishing", stale, rerender }),
      control({ label: "All spend", detail: spend.no_scopes_configured ? "No spend scopes configured" : Array.isArray(spend.scopes) ? spend.scopes.map((x) => `${x.scope}${x.paused ? " (paused)" : ""}`).join(", ") : "Scopes unknown", paused: !!spend.all_paused, scope: "spend", stale, rerender }),
      control({ label: "Whole company", detail: "Every pausable department, spend and publishing", paused: depts.length > 0 && depts.every((x) => x.paused || x.pausable === false), scope: "company", stale, rerender })),
    card({ title: "Departments" },
      depts.length ? depts.map((x) => control({ label: humanize(x.department),
        detail: x.pausable === false ? (x.never_paused_because || "Never paused") : Array.isArray(x.agents) ? `Agents: ${x.agents.join(", ")}` : null,
        paused: !!x.paused, scope: "department", department: x.department, stale, rerender, pausable: x.pausable !== false }))
        : h("p", { class: "muted" }, "Unknown: departments not reported.")),
    card({ title: "Never paused" }, h("p", { class: "muted" },
      "These keep running so the company stays observable and recoverable:"),
      h("ul", { class: "rows" }, neverPaused(d.never_paused).map(([k, why]) => h("li", { class: "row" },
        h("p", { class: "row-title" }, humanize(k)), why ? h("p", { class: "row-detail" }, why) : null)))));
}
