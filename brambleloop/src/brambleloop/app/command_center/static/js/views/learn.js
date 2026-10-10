// AUTONOMY / LEARN: autonomous work (A), improvement loops (B), time since the owner last acted.
import { h } from "../dom.js";
import { api } from "../api.js";
import { statTile, card, statusPill, freshness, basisNote, sourcesList } from "../components.js";
import { sectionsOf, pageMeta, renderAll, renderSection, isEnvelope } from "./_shared.js";
import { formatNumber, relTime, utcStamp, humanize, UNKNOWN_TEXT } from "../format.js";

const ORDER = [["autonomy", "Autonomous company"], ["jobs_24h", "Jobs in the last 24 h"],
  ["improvement", "Improvement loops"], ["improvements", "Improvements: proposed, tested, promoted, rolled back"],
  ["experiments", "Experiments"], ["visual_rnd", "Visual R&D (per product class)"],
  ["visual_rnd_governance", "Visual R&D: identity review, paid plans, commercial objective, evolution"], ["lessons", "Lessons"], ["last_useful_action", "Last useful action"]];

function ownerGapTile(env) {
  // hours_since_owner_action: envelope with items[0].hours; UNKNOWN stays Unknown.
  const it = isEnvelope(env) && Array.isArray(env.items) && env.items[0] ? env.items[0] : null;
  const hrs = it && typeof it.hours === "number" ? it.hours : null;
  return h("div", { class: "tiles" },
    statTile("Hours since you last acted", hrs === null ? null : formatNumber(hrs, { digits: 1 }),
      { status: isEnvelope(env) ? env.status : "UNKNOWN" }),
    statTile("Last owner action", it && it.last_owner_action_at ? relTime(it.last_owner_action_at) : null));
}

// W4-CCFIN: shared header for the two hand-built cards: status, as-of, basis, reason.
function envHead(title, env, result, subtitle, labelId) {
  const status = String(env.status || "UNKNOWN").toUpperCase();
  return [{ title, subtitle, labelId, actions: statusPill(status) },
    h("p", { class: "card-meta" }, freshness(env.as_of, { stale: result && result.stale, fetchedAt: result && result.fetchedAt }),
      ...basisNote(env.basis, status)),
    env.reason ? h("p", { class: ["callout", status === "OK" ? "callout-info" : "callout-warn"] }, env.reason) : null];
}

const known = (v) => v !== null && v !== undefined;
const fact = (k, v) => h("div", { class: "fact" }, h("dt", null, k), h("dd", null, known(v) ? String(v) : UNKNOWN_TEXT));
const yesNo = (v) => (v === true ? "Yes" : v === false ? "No" : UNKNOWN_TEXT);
const pct = (v) => (typeof v === "number" ? `${formatNumber(v * 100, { digits: 0 })}%` : UNKNOWN_TEXT);
const when = (iso) => (iso ? `${relTime(iso)} (${utcStamp(iso)})` : UNKNOWN_TEXT);

/** Rule #1: does every department find and do useful work without a prompt? UNKNOWN never 0. */
export function rule1Card(env, result) {
  if (!isEnvelope(env)) return renderSection("rule1", env, { title: "Rule #1: useful work without a prompt", result });
  const [opts, ...head] = envHead("Rule #1: useful work without a prompt", env, result,
    "A defect is a department idle while its own generators offer safe, runnable work.", "autonomy-rule1");
  const c = env.counts || {};
  const w = env.window || {};
  const items = Array.isArray(env.items) ? env.items : [];
  return card(opts, ...head,
    h("div", { class: "tiles" },
      statTile("Rule #1 defects", known(c.defects) ? formatNumber(c.defects) : null, { status: env.status }),
      statTile("Departments evaluated", known(c.evaluated) && known(c.departments) ? `${c.evaluated} of ${c.departments}` : null)),
    known(w.hours) ? h("p", { class: "muted small" }, `Window: last ${w.hours} h, ${known(w.jobs_read) ? w.jobs_read : UNKNOWN_TEXT} finished jobs read${w.truncated ? ` (capped at ${w.max_jobs})` : ""}.`) : null,
    items.length ? h("ul", { class: "rows" }, items.map((it) => h("li", { class: "row" },
      h("div", { class: "row-head" }, h("p", { class: "row-title" }, it.name || humanize(it.department || "department")),
        statusPill(it.status || "UNKNOWN", it.rule1_defect === true ? "DEFECT" : null)),
      it.why ? h("p", { class: "row-detail" }, it.why) : null,
      h("dl", { class: "facts" },
        fact("Rule #1 defect", yesNo(it.rule1_defect)),
        fact("Idle now", yesNo(it.idle_now)),
        fact("Eligible work not yet taken", it.eligible_untaken),
        fact(`Useful / done (${known(it.window_hours) ? it.window_hours : "?"} h)`, known(it.done) ? `${it.useful} / ${it.done}` : null),
        fact("Useful rate", pct(it.useful_rate)),
        fact("Dead letters", it.dead),
        fact("As of", when(it.as_of))),
      Array.isArray(it.next_eligible) && it.next_eligible.length
        ? h("p", { class: "row-meta" }, `Next eligible: ${it.next_eligible.map((n) => n.job_type).join(", ")}`) : null)))
      : h("p", { class: "muted" }, "Unknown: Rule #1 has not been measured."),
    sourcesList(env.sources));
}

function blockerText(b) {
  if (!b || typeof b !== "object") return String(b);
  const why = b.reason || b.error || b.what || b.gate || "";
  return `${humanize(b.kind || "blocker")}${why ? `: ${why}` : ""}`;
}

function usefulText(r) {
  if (!r) return null;
  const made = r.produced && typeof r.produced === "object" ? Object.entries(r.produced).map(([k, v]) => `${humanize(k)} ${v}`).join(", ") : "";
  return `${r.job_type}${made ? ` (${made})` : ""} · ${when(r.at)}`;
}

/** Per-agent status: agent, department, status, current work, useful output, blockers. */
export function agentsCard(env, result) {
  if (!isEnvelope(env)) return renderSection("agents", env, { title: "Agents: status, current work, useful output, blockers", result });
  const [opts, ...head] = envHead("Agents: status, current work, useful output, blockers", env, result, null, "autonomy-agents");
  const items = Array.isArray(env.items) ? env.items : [];
  return card(opts, ...head,
    items.length ? h("ul", { class: "rows" }, items.map((it) => {
      const blockers = Array.isArray(it.blockers) ? it.blockers : [];
      return h("li", { class: "row" },
        h("div", { class: "row-head" }, h("p", { class: "row-title" }, it.agent || "agent"), statusPill(it.state || "UNKNOWN", it.state ? String(it.state).toUpperCase() : null)),
        h("dl", { class: "facts" },
          fact("Department", it.department ? humanize(it.department) : null),
          fact("Current work", it.doing_now || "Nothing running"),
          fact("Last useful output", usefulText(it.last_useful_result) || "None recorded"),
          fact(`Useful / done (${known(it.window_hours) ? it.window_hours : "?"} h)`, known(it.completed) ? `${it.useful} / ${it.completed}` : null),
          fact("Next wake", it.next_wake ? when(it.next_wake) : null),
          fact("As of", when(it.as_of))),
        blockers.length ? h("div", null, blockers.map((b) => h("p", { class: "callout callout-warn" }, blockerText(b))))
          : h("p", { class: "row-meta" }, "No blockers."));
    })) : h("p", { class: "muted" }, String(env.status).toUpperCase() === "UNKNOWN" ? "Unknown: no agent status reported." : "No agents reported."),
    sourcesList(env.sources));
}

export async function render() {
  const result = await api.autonomy();
  const data = result.data || {};
  const s = sectionsOf(data);
  const gap = s.hours_since_owner_action;
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    ownerGapTile(gap),
    isEnvelope(gap) ? h("p", { class: "card-meta" }, freshness(gap.as_of, { stale: result.stale, fetchedAt: result.fetchedAt })) : null,
    isEnvelope(gap) && gap.note ? h("p", { class: "muted small" }, gap.note) : null,
    isEnvelope(gap) && gap.reason ? h("p", { class: "callout callout-warn" }, gap.reason) : null,
    rule1Card(s.rule1, result),
    agentsCard(s.agents, result),
    ...renderAll(data, ORDER, { result, required: ["autonomy", "improvement"], skip: ["hours_since_owner_action", "rule1", "agents"] }));
}
