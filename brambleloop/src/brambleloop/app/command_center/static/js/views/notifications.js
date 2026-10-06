// NOTIFICATIONS (F-897): severity-ranked, deduplicated, actionable; policy controls.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, toast, guardedAction } from "../components.js";
import { relTime, utcStamp, humanize } from "../format.js";
import { pageMeta, renderSection, toHashRoute, sectionsOf } from "./_shared.js";

const SEV_RANK = { critical: 0, high: 1, normal: 2, low: 3 };
const SEV_STATUS = { critical: "CRITICAL", high: "HIGH", normal: "INFO", low: "LOW" };

function notificationCard(n, { stale, rerender }) {
  const sev = String(n.severity || "normal").toLowerCase();
  const link = toHashRoute(n.deep_link);
  const ev = Array.isArray(n.evidence) ? n.evidence : [];
  return h("article", { class: ["card", "notif", n.acked_at ? "is-acked" : null], data: { notification: String(n.id ?? "") } },
    h("header", { class: "card-head" },
      h("div", null, h("p", { class: "tile-label" }, `${humanize(n.category || "notice")}${n.occurrences > 1 ? ` · ${n.occurrences}×` : ""}`),
        h("h2", { class: "card-title" }, n.title || "Notification")),
      statusPill(SEV_STATUS[sev] || "INFO", sev.toUpperCase())),
    n.body ? h("p", null, n.body) : null,
    n.consequence ? h("p", { class: "callout callout-warn" }, `Consequence: ${n.consequence}`) : null,
    h("p", { class: "card-meta" }, n.deadline ? `Deadline ${relTime(n.deadline)} (${utcStamp(n.deadline)}) · ` : "",
      `Last seen ${relTime(n.last_seen_at || n.first_seen_at)}`, n.held_for_quiet_hours ? " · held for quiet hours" : ""),
    ev.length ? h("p", { class: "row-detail" }, "Evidence: ",
      ...ev.map((e, i) => [i ? ", " : "", h("a", { href: `#/drill/${encodeURIComponent(String(e))}` }, String(e))])) : null,
    h("div", { class: "btn-row" },
      link ? h("a", { class: "btn btn-primary", href: link }, "Open") : h("span", { class: "muted" }, "No direct action"),
      n.acked_at ? h("span", { class: "muted" }, `Acknowledged ${relTime(n.acked_at)}`) :
        h("button", { class: "btn", type: "button", disabled: stale, onclick: async (e) => {
          e.currentTarget.disabled = true;
          try { await api.ackNotification(n.id); toast("Acknowledged."); rerender(); }
          catch (err) { toast(err.message, "bad"); }
        } }, "Acknowledge")));
}

function policyCard(policy, stale, rerender) {
  const p = policy && typeof policy === "object" ? policy : {};
  const qh = p.quiet_hours || {};
  const start = h("input", { id: "qh-start", type: "text", value: qh.start || "22:00", maxLength: 5, inputMode: "numeric" });
  const end = h("input", { id: "qh-end", type: "text", value: qh.end || "07:00", maxLength: 5, inputMode: "numeric" });
  const tz = h("input", { id: "qh-tz", type: "text", value: qh.tz || "America/Toronto", maxLength: 64 });
  const sev = h("select", { id: "min-sev" }, ["critical", "high", "normal", "low"].map((v) => {
    const o = h("option", { value: v }, humanize(v));
    if ((p.min_severity || "normal") === v) o.selected = true;
    return o;
  }));
  const digest = h("select", { id: "digest" }, ["morning", "none"].map((v) => {
    const o = h("option", { value: v }, humanize(v));
    if ((p.digest || "morning") === v) o.selected = true;
    return o;
  }));
  const save = h("button", { class: "btn btn-primary", type: "submit", disabled: stale }, "Save policy");
  const form = h("form", null,
    h("p", { class: "muted" }, "Critical and security notifications always come through, even in quiet hours. Only in-app delivery exists today; email, SMS and push are gated pending owner authority and a CASL review."),
    h("div", { class: "grid-2" },
      h("div", null, h("label", { class: "field", for: "qh-start" }, "Quiet hours start"), start),
      h("div", null, h("label", { class: "field", for: "qh-end" }, "Quiet hours end"), end)),
    h("label", { class: "field", for: "qh-tz" }, "Time zone"), tz,
    h("label", { class: "field", for: "min-sev" }, "Minimum severity"), sev,
    h("label", { class: "field", for: "digest" }, "Digest"), digest,
    h("div", { class: "btn-row" }, save));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!/^\d{2}:\d{2}$/.test(start.value) || !/^\d{2}:\d{2}$/.test(end.value)) { toast("Use HH:MM for quiet hours.", "bad"); return; }
    save.disabled = true;
    try {
      await api.setNotificationPolicy({ quiet_hours: { start: start.value, end: end.value, tz: tz.value.trim() },
        min_severity: sev.value, digest: digest.value });
      toast("Notification policy saved.");
      rerender();
    } catch (err) { toast(err.message, "bad"); save.disabled = false; }
  });
  return h("details", { class: "card" }, h("summary", { class: "card-title" }, "Notification policy"), form);
}

export async function render({ rerender, setBadge }) {
  const result = await api.notifications();
  const data = result.data || {};
  const list = (Array.isArray(data.notifications) ? data.notifications : []).slice()
    .sort((a, b) => (!!a.acked_at - !!b.acked_at) || ((SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9)));
  setBadge("notifications", list.filter((n) => !n.acked_at).length);
  const refresh = h("button", { class: "btn", type: "button", disabled: result.stale, onclick: async () => {
    const r = await guardedAction({ title: "Re-check company state for notifications?", lines: ["This regenerates alerts from durable state. Nothing external is sent."],
      confirmLabel: "Re-check", run: () => api.refreshNotifications(), success: "Notifications refreshed." });
    if (r) rerender();
  } }, "Re-check");
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    card({ title: "Alerts", subtitle: "Decisions, risk, deadlines and anomalies only. Routine machine chatter is suppressed.", actions: refresh },
      h("p", { class: "muted" }, typeof data.suppressed_count === "number" ? `${data.suppressed_count} routine event(s) suppressed as noise.` : "Suppressed count: Unknown.")),
    list.length ? list.map((n) => notificationCard(n, { stale: result.stale, rerender }))
      : card({ title: "All clear" }, h("p", { class: "muted" }, "No notifications need you.")),
    data.digest !== undefined ? renderSection("digest", data.digest, { title: "Digest", result }) : null,
    policyCard(data.policy, result.stale, rerender),
    ...Object.entries(sectionsOf(data)).map(([k, v]) => renderSection(k, v, { result })));
}
