// ACCOUNT & SECURITY (F-888): owner, sessions/devices, refused attempts, services, scopes,
// providers, budgets, authorities, notification policy, emergency controls entry point.
import { h, icon } from "../dom.js";
import { api, authState } from "../api.js";
import { card, statusPill, guardedAction, errorState } from "../components.js";
import { relTime, utcStamp } from "../format.js";
import { pageMeta, renderAll } from "./_shared.js";
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
    ...renderAll(data, ORDER, { result, required: ["connected_services", "budgets"], skip: ["sessions", "emergency"] }),
    appearanceCard(),
    card({ title: "Sign out" }, h("button", { class: "btn btn-block", type: "button", onclick: () => signOut() }, "Sign out of this device")));
}
