// W4-LISTREADY (D-W4-LAUNCH-VISION-BATCH): the owner's Launch-0 image-review batch.
// Shows the batch from GET /api/cc/launch-review and activates it with the same
// POST /api/cc/launch-review/activate, through the shared CSRF + step-up flow (api.js, components.js).
// The server decides; the button is disabled, with the reason, whenever the server would refuse.
import { h } from "../dom.js";
import { api, stepUp, stepUpValid, authState } from "../api.js";
import { card, statusPill, guardedAction, stepUpDialog, toast } from "../components.js";
import { UNKNOWN_TEXT } from "../format.js";

const txt = (v) => (v === null || v === undefined || v === "" ? UNKNOWN_TEXT : String(v));
const money = (v) => (typeof v === "number" ? `CA$${v.toFixed(2)}` : UNKNOWN_TEXT);

// Why Activate would be refused right now, or "" when it would be accepted.
export function activateBlockedReason(st, stepped) {
  if (!st) return "The batch state could not be read.";
  if (st.status && st.status !== "not_activated" && st.status !== "unused") {
    return st.status === "open" ? "Already active." : `Already used (${st.status}).`;
  }
  if (st.frames_ready !== true) {
    const missing = Array.isArray(st.missing_releases) ? st.missing_releases : [];
    return `Frames are not yet built for every Launch-0 release${missing.length ? ` (${missing.length} missing: ${missing.slice(0, 3).join(", ")}${missing.length > 3 ? "…" : ""})` : ""}.`;
  }
  if (st.vision_open !== true) return "The image-vision gate is closed, so no frame could be reviewed.";
  if (!stepped) return "Step-up needed first.";
  return "";
}

export function launchReviewCard(settled, rerender) {
  const title = "Launch image review";
  if (!settled || settled.status === "rejected") {
    const msg = settled && settled.reason && settled.reason.message ? settled.reason.message : "not loaded";
    return card({ title, labelId: "completion-launch-review", actions: statusPill("UNKNOWN") },
      h("p", { class: "callout callout-warn" }, `Unknown: the review batch could not be loaded (${msg}).`));
  }
  const st = (settled.value && settled.value.data) || settled.value || {};
  const status = String(st.status || "UNKNOWN");
  const pill = status === "open" ? "RUNNING" : status === "completed" ? "OK"
    : status === "not_activated" ? "BLOCKED" : "UNKNOWN";
  const stepped = stepUpValid();
  const blocked = activateBlockedReason(st, stepped);
  const reload = rerender || (() => {});
  const releases = st.releases && typeof st.releases === "object" ? Object.entries(st.releases) : [];

  const activate = h("button", { class: "btn btn-primary", type: "button", disabled: !!blocked,
    aria: { describedby: "launch-review-why" },
    onclick: async () => {
      const out = await guardedAction({
        title: "Activate the launch image review",
        lines: [`Up to ${money(st.total_cap_cad ?? 7.07)} in total, for the Launch-0 listing frames only.`,
          `The reviewer's daily ceiling is ${money(st.daily_cap_cad ?? 8)} for this batch only, and returns to CA$1.00 by itself.`,
          "The CA$100 monthly ceiling is unchanged. Nothing is published."],
        confirmLabel: "Activate", requiresStepUp: true,
        run: () => api.activateLaunchReview(), success: "Launch image review activated." });
      if (out) reload();
    } }, "Activate");
  const stepBtn = !stepped && !blocked.startsWith("Already") ? h("button", { class: "btn", type: "button",
    onclick: async () => {
      const cred = await stepUpDialog({ totpRequired: authState().totpRequired });
      if (!cred) { toast("Cancelled. Nothing changed."); return; }
      try { await stepUp(cred.passphrase, cred.totp); toast("Step-up accepted.", "info"); reload(); }
      catch (err) { toast(`${err.message || "Refused"}${err.code ? ` (${err.code})` : ""}`, "bad"); }
    } }, "Step up") : null;

  return card({ title, labelId: "completion-launch-review",
    subtitle: "Owner-approved paid review of the Launch-0 listing images (D-W4-LAUNCH-VISION-BATCH)",
    actions: statusPill(pill, status.replace("_", " ")) },
    h("dl", { class: "facts" },
      h("div", { class: "fact" }, h("dt", null, "Spent / cap"), h("dd", null, `${money(st.committed_cad ?? (status === "not_activated" ? 0 : null))} of ${money(st.total_cap_cad ?? 7.07)}`)),
      h("div", { class: "fact" }, h("dt", null, "Reviewer daily ceiling now"), h("dd", null, money(st.effective_daily_ceiling_cad))),
      h("div", { class: "fact" }, h("dt", null, "Frames in scope"), h("dd", null, txt(st.frames))),
      h("div", { class: "fact" }, h("dt", null, "Releases reviewed"), h("dd", null,
        typeof st.releases_total === "number" ? `${st.releases_reviewed ?? 0} of ${st.releases_total}` : UNKNOWN_TEXT)),
      h("div", { class: "fact" }, h("dt", null, "Expires"), h("dd", null, txt(st.expires_at)))),
    st.closed_why ? h("p", { class: "row-detail" }, `Closed: ${st.closed_why}`) : null,
    releases.length ? h("ul", { class: "rows" }, releases.map(([rel, s]) => h("li", { class: "row" },
      h("p", { class: "row-title" }, statusPill(s === "done" ? "OK" : s === "interrupted" ? "BAD" : "UNKNOWN", txt(s)), ` ${rel}`)))) : null,
    h("div", { class: "row" }, activate, stepBtn, status === "open" ? h("button", { class: "btn", type: "button",
      onclick: async () => {
        const out = await guardedAction({ title: "Resume the launch image review",
          lines: ["Queues one more run for releases not yet reviewed, under the same caps and expiry."],
          confirmLabel: "Resume", requiresStepUp: true,
          run: () => api.resumeLaunchReview(), success: "Resumed." });
        if (out) reload();
      } }, "Resume") : null),
    h("p", { id: "launch-review-why", class: blocked ? "callout callout-warn" : "muted small" },
      blocked || "Ready: tap Activate. The server re-checks every rule."),
    h("p", { class: "muted small" }, "Results feed the independent frame review unchanged; an unreviewed frame stays Unknown, never a pass."));
}
