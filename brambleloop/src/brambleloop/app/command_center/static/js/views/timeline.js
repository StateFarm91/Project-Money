// Company timeline (F-927): autonomous actions, approvals, deployments, spend, incidents, closes.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, sourcesList } from "../components.js";
import { relTime, utcStamp, humanize } from "../format.js";
import { sectionsOf, pageMeta, renderSection } from "./_shared.js";

function when(e) { return e.at || e.occurred_at || e.created_at || e.time || e.ts || null; }

export async function render({ query }) {
  const limit = Math.min(Math.max(Number(query.get("limit")) || 50, 10), 200);
  const result = await api.timeline(limit);
  const data = result.data || {};
  const s = sectionsOf(data);
  const env = s.events || (Array.isArray(data.events) ? { status: "OK", items: data.events, sources: data.sources || [] } : null);
  const events = env && Array.isArray(env.items) ? env.items : [];
  const at = data.autonomy_timeline;
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    at && String(at.status || "").toUpperCase() !== "OK" ? h("p", { class: "callout callout-warn" },
      `Autonomous-work timeline: ${String(at.status || "UNKNOWN")}${at.reason ? `: ${at.reason}` : ""}. Audit-log events are still shown.`) : null,
    env ? card({ title: "Company timeline", subtitle: "Newest first", actions: statusPill(env.status || "UNKNOWN") },
      env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
      events.length ? h("ol", { class: "tl" }, events.map((e) => {
        const ev = e && typeof e === "object" ? e : { title: String(e) };
        const t = when(ev);
        const ref = ev.ref || ev.source || (Array.isArray(ev.sources) && typeof ev.sources[0] === "string" ? ev.sources[0] : null);
        return h("li", null,
          h("time", { datetime: t || "", title: utcStamp(t) }, t ? `${relTime(t)} · ${utcStamp(t)}` : "time unknown"),
          h("p", { class: "row-title" }, ev.title || ev.summary || ev.action || ev.kind || "Event"),
          h("p", { class: "row-detail" }, [ev.kind ? humanize(ev.kind) : null, ev.actor || ev.agent || null, ev.artifact || null].filter(Boolean).join(" · ")),
          ev.detail ? h("p", { class: "row-detail" }, String(ev.detail)) : null,
          ref ? h("a", { href: `#/drill/${encodeURIComponent(ref)}` }, `Source: ${ref}`) : null);
      })) : h("p", { class: "muted" }, "Unknown: no timeline events reported."),
      events.length >= limit ? h("a", { class: "btn", href: `#/timeline?limit=${Math.min(limit * 2, 200)}` }, "Show more") : null,
      sourcesList(env.sources)) : renderSection("events", null, { title: "Company timeline" }),
    ...Object.entries(s).filter(([k]) => k !== "events").map(([k, v]) => renderSection(k, v, { result })));
}
