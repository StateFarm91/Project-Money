// COMPLETION EFFORT (W4-CC): the parallel completion lanes, read from the committed
// research/final_build/w4/COMPLETION_BOARD.json. A null is Unknown, never 0.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, freshness, sourcesList, statTile } from "../components.js";
import { relTime, utcStamp, UNKNOWN_TEXT } from "../format.js";
import { sectionsOf, pageMeta } from "./_shared.js";

const ORDER = ["BLOCKED", "RUNNING", "REVIEW", "QUEUED", "UNKNOWN", "MERGED", "DONE", "ABANDONED"];
const when = (iso) => (iso ? `${relTime(iso)} (${utcStamp(iso)})` : UNKNOWN_TEXT);
const txt = (v) => (v === null || v === undefined || v === "" ? UNKNOWN_TEXT : String(v));

function fact(label, text) {
  return h("div", { class: "fact" }, h("dt", null, label), h("dd", null, text));
}

function laneRow(it) {
  const rc = it.rows_closed;
  const ids = rc && Array.isArray(rc.ids) ? rc.ids : [];
  return h("li", { class: "row" },
    h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${it.lane}: ${txt(it.task)}`),
      statusPill(it.stale ? "STALE" : it.status, it.stale ? `${it.status} · STALE` : it.status)),
    it.blocker ? h("p", { class: "callout callout-warn" }, `Blocker: ${it.blocker}`) : null,
    h("dl", { class: "facts" },
      fact("Worker", txt(it.worker)),
      fact("Started", when(it.started_at)),
      fact("Last update", when(it.last_update_at)),
      fact("Useful output", txt(it.useful_output)),
      fact("Next action", txt(it.next_action)),
      fact("Rows closed", typeof it.rows_closed_count === "number" ? `${it.rows_closed_count}${ids.length ? ` (${ids.slice(0, 12).join(", ")}${ids.length > 12 ? ", …" : ""})` : ""}` : UNKNOWN_TEXT),
      it.branch ? fact("Branch", `${it.branch}${it.head_sha ? ` @ ${String(it.head_sha).slice(0, 7)}` : ""}`) : null));
}

export async function render() {
  const result = await api.completion();
  const data = result.data || {};
  const env = sectionsOf(data).board || {};
  const items = Array.isArray(env.items) ? [...env.items] : [];
  items.sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status));
  const c = env.counts || {};
  const n = (v) => (typeof v === "number" ? v : null);
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    card({ title: "Completion effort", subtitle: "Parallel lanes finishing the existing build", actions: statusPill(env.status) },
      h("p", { class: "card-meta" }, freshness(env.as_of, result), env.updated_by ? ` · updated by ${env.updated_by}` : ""),
      env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
      h("div", { class: "tiles" },
        statTile("Running", n(c.RUNNING)), statTile("Blocked", n(c.BLOCKED), { status: n(c.BLOCKED) ? "BLOCKED" : null }),
        statTile("In review", n(c.REVIEW)), statTile("Merged / done", n(c.MERGED) === null || n(c.DONE) === null ? null : c.MERGED + c.DONE),
        statTile("Unknown", n(c.UNKNOWN)),
        statTile("Rows closed (known lanes)", n(env.rows_closed_total))),
      typeof env.rows_closed_lanes_unknown === "number" && env.rows_closed_lanes_unknown
        ? h("p", { class: "muted small" }, `${env.rows_closed_lanes_unknown} lane(s) have not reported rows closed; they are not counted as 0.`) : null,
      Array.isArray(env.stale) && env.stale.length ? h("p", { class: "callout callout-warn" }, `Stale (running, no update for 3 h): ${env.stale.join(", ")}`) : null,
      Array.isArray(env.schema_errors) && env.schema_errors.length ? h("p", { class: "callout callout-warn" }, `Board problems: ${env.schema_errors.slice(0, 5).join("; ")}`) : null,
      env.note ? h("p", { class: "muted small" }, env.note) : null),
    card({ title: "Lanes" },
      items.length ? h("ul", { class: "rows" }, items.map(laneRow)) : h("p", { class: "muted" }, "Unknown: the board did not report any lane."),
      sourcesList(env.sources)));
}
