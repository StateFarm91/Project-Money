// AUTONOMY / LEARN: autonomous work (A), improvement loops (B), time since the owner last acted.
import { h } from "../dom.js";
import { api } from "../api.js";
import { statTile } from "../components.js";
import { sectionsOf, pageMeta, renderAll, isEnvelope } from "./_shared.js";
import { formatNumber, relTime } from "../format.js";

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

export async function render() {
  const result = await api.autonomy();
  const data = result.data || {};
  const s = sectionsOf(data);
  const gap = s.hours_since_owner_action;
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    ownerGapTile(gap),
    isEnvelope(gap) && gap.note ? h("p", { class: "muted small" }, gap.note) : null,
    isEnvelope(gap) && gap.reason ? h("p", { class: "callout callout-warn" }, gap.reason) : null,
    ...renderAll(data, ORDER, { result, required: ["autonomy", "improvement"], skip: ["hours_since_owner_action"] }));
}
