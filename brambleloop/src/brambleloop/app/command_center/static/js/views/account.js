// ACCOUNT & SECURITY (F-888): owner, sessions/devices, refused attempts, services, scopes,
// providers, budgets, authorities, notification policy, emergency controls entry point.
import { h, icon } from "../dom.js";
import { api, authState } from "../api.js";
import { card, statusPill, guardedAction, errorState, freshness, basisNote, sourcesList, itemRow } from "../components.js";
import { relTime, utcStamp, humanize, formatMoney, UNKNOWN_TEXT } from "../format.js";
import { pageMeta, renderAll, renderSection, isEnvelope, sectionsOf } from "./_shared.js";
import { getTheme, setTheme, signOut } from "../app.js";

const ORDER = [["owner", "Owner"], ["security_events", "Refused & suspicious attempts"], ["refused_attempts_24h", "Refused attempts (24 h)"],
  ["connected_services", "Connected services & OAuth scopes"], ["model_providers", "Model providers"], ["budgets", "Budgets & spend limits"],
  ["authorities", "Live authorities & grants"], ["notification_policy", "Notification policy"]];

function sessionsCard(result, rerender) {
  if (result.status === "rejected") return errorState(result.reason);
  const r = result.value;
  const list = Array.isArray(r.data) ? r.data : (r.data && Array.isArray(r.data.sessions)) ? r.data.sessions : [];
  const active = list.filter((s) => !s.revoked_at);
  return card({ title: "Signed-in devices", subtitle: "Revoke anything you do not recognise." },
    active.length ? h("ul", { class: "rows" }, active.map((s) => h("li", { class: "row" },
      h("div", { class: "row-head" }, h("p", { class: "row-title" }, s.device_label || "Unnamed device"),
        s.current ? statusPill("OK", "THIS DEVICE") : null),
      h("p", { class: "row-detail" }, `Signed in ${relTime(s.created_at)} · last seen ${relTime(s.last_seen_at)} · expires ${relTime(s.expires_at)}`),
      h("p", { class: "row-detail mono", title: utcStamp(s.created_at) }, s.session_id || ""),
      s.current ? null : h("div", { class: "row-actions" }, h("button", { class: "btn btn-danger", type: "button", disabled: r.stale,
        onclick: async () => {
          const ok = await guardedAction({ title: "Sign this device out?", lines: [s.device_label || s.session_id || "Session"],
            confirmLabel: "Revoke", danger: true, run: () => api.revokeSession(s.session_id), success: "Session revoked." });
          if (ok) rerender();
        } }, "Revoke"))))) : h("p", { class: "muted" }, "Unknown: no session list returned."),
    active.length > 1 ? h("div", { class: "btn-row" }, h("button", { class: "btn btn-danger", type: "button", disabled: r.stale,
      onclick: async () => {
        const ok = await guardedAction({ title: "Sign out every other device?", lines: ["Only this device stays signed in."],
          confirmLabel: "Sign out others", danger: true, run: () => api.revokeOthers(), success: "Other sessions revoked." });
        if (ok) rerender();
      } }, "Sign out all other devices")) : null);
}

function securityCard() {
  const a = authState();
  return card({ title: "Authentication" },
    h("dl", { class: "facts" },
      h("div", { class: "fact" }, h("dt", null, "Method"), h("dd", null, a.totpRequired ? "Passphrase + authenticator code" : "Passphrase")),
      h("div", { class: "fact" }, h("dt", null, "Re-authenticated until"), h("dd", null, a.stepupValidUntil ? `${relTime(a.stepupValidUntil)} (${utcStamp(a.stepupValidUntil)})` : "Not currently"))),
    h("p", { class: "muted" }, "Consequential actions (approvals, resuming anything paused) ask for your passphrase again. Pausing never does."));
}

// W4-CCFIN: governance, read-only. Grants and approvals stay behind step-up elsewhere.
function govHead(title, env, result, subtitle, labelId) {
  const status = String(env.status || "UNKNOWN").toUpperCase();
  return [{ title, subtitle, labelId, actions: statusPill(status) },
    h("p", { class: "card-meta" }, freshness(env.as_of, { stale: result && result.stale, fetchedAt: result && result.fetchedAt }),
      ...basisNote(env.basis, status)),
    env.reason ? h("p", { class: ["callout", status === "OK" ? "callout-info" : "callout-warn"] }, env.reason) : null];
}
const gfact = (k, v) => h("div", { class: "fact" }, h("dt", null, k),
  h("dd", null, v === null || v === undefined || v === "" ? UNKNOWN_TEXT : String(v)));

export function authorityPolicyCard(env, result) {
  const title = "Authority ladder: recorded grants";
  if (!isEnvelope(env)) return renderSection("authority_policy", env, { title, result });
  const [opts, ...head] = govHead(title, env, result, "What each agent may do on its own, as recorded. Read-only here.", "account-authority-policy");
  const items = Array.isArray(env.items) ? env.items : [];
  const cls = env.classes && typeof env.classes === "object" ? env.classes : null;
  return card(opts, ...head,
    h("dl", { class: "facts" }, gfact("Phase", env.phase),
      cls ? gfact("Gated action classes", Array.isArray(cls.gated) ? cls.gated.join(", ") : null) : null,
      cls ? gfact("Autonomous action classes", Array.isArray(cls.autonomous) ? cls.autonomous.join(", ") : null) : null),
    items.length ? h("ul", { class: "rows" }, items.map((p) => h("li", { class: "row" },
      h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${p.agent || "any agent"} · ${humanize(p.action_class || p.job_type || "action")}`),
        statusPill("OK", String(p.level || "granted").toUpperCase())),
      h("dl", { class: "facts" },
        gfact("Job type", p.job_type || "any"),
        gfact("Max per day", p.max_per_day),
        gfact("Max cost", typeof p.max_cost_cad === "number" ? formatMoney({ value_cad: p.max_cost_cad, state: "RECORDED" }) : null),
        gfact("Granted by", p.granted_by),
        gfact("Granted", p.at ? `${relTime(p.at)} (${utcStamp(p.at)})` : null)))))
      : h("p", { class: "muted" }, String(env.status).toUpperCase() === "UNKNOWN" ? "Unknown: authority not reported." : "No authority grant is recorded: every gated action needs your approval."),
    sourcesList(env.sources));
}

export function authorityDagCard(env, result) {
  const title = "Company work DAG: awaiting your approval";
  if (!isEnvelope(env)) return renderSection("authority_dag", env, { title, result });
  const [opts, ...head] = govHead(title, env, result, "Work items by state; approve them from Approvals.", "account-authority-dag");
  const items = Array.isArray(env.items) ? env.items : [];
  const counts = env.counts && typeof env.counts === "object" ? Object.entries(env.counts) : [];
  return card(opts, ...head,
    counts.length ? h("dl", { class: "facts" }, counts.map(([k, v]) => gfact(humanize(k), v))) : null,
    items.length ? h("ul", { class: "rows" }, items.slice(0, 20).map((it) => itemRow(it, { drill: false })))
      : h("p", { class: "muted" }, String(env.status).toUpperCase() === "UNKNOWN" ? "Unknown: no work items recorded yet." : "Nothing awaits your approval."),
    sourcesList(env.sources));
}

function appearanceCard() {
  const cur = getTheme();
  const group = h("div", { class: "seg", role: "radiogroup", aria: { label: "Theme" } });
  for (const [v, label] of [["auto", "System"], ["light", "Light"], ["dark", "Dark"]]) {
    const b = h("button", { class: "btn", type: "button", role: "radio", aria: { checked: String(cur === v) } }, label);
    b.addEventListener("click", () => {
      setTheme(v);
      for (const x of group.children) x.setAttribute("aria-checked", String(x === b));
    });
    group.append(b);
  }
  return card({ title: "Appearance" }, group);
}

export async function render({ rerender }) {
  const result = await api.account();
  const data = result.data || {};
  // The account payload carries the session list; fall back to the dedicated endpoint.
  const sess = Array.isArray(data.sessions)
    ? { status: "fulfilled", value: { data: data.sessions, stale: result.stale } }
    : await Promise.allSettled([api.sessions()]).then(([x]) => x);
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    card({ title: "Emergency controls", cls: "card-danger", subtitle: "Pause publishing, spend or departments immediately. Monitoring, evidence and recovery keep running." },
      h("a", { class: "btn btn-danger btn-block", href: "#/emergency" }, icon("shield", 18), "Open emergency controls")),
    securityCard(),
    sessionsCard(sess, rerender),
    ...renderAll(data, ORDER, { result, required: ["connected_services", "budgets"], skip: ["sessions", "emergency", "authority_policy", "authority_dag"] }),
    authorityPolicyCard(sectionsOf(data).authority_policy, result),
    authorityDagCard(sectionsOf(data).authority_dag, result),
    appearanceCard(),
    card({ title: "Sign out" }, h("button", { class: "btn btn-block", type: "button", onclick: () => signOut() }, "Sign out of this device")));
}
