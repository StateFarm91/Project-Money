// W4-LAURAONE (D-W4-LAURA-UNIFIED, ADD-LCONT-01..10): ONE Laura, ONE thread. Shown instead of
// the split business / private cards only when the owner has switched the unified thread on
// (BRAMBLELOOP_LAURA_UNIFIED=venice). Every turn, whatever its subject, is kept encrypted;
// content is fetched by POST only (no GET cache). Laura (Venice) decides when to use a
// business tool; anything from our private conversation crosses to the business side only
// after the owner approves the exact text shown, with a fresh step-up.
import { h, clear } from "../dom.js";
import { api, authState } from "../api.js";
import { card, statusPill, toast, guardedAction, confirmDialog } from "../components.js";
import { utcStamp } from "../format.js";

const LABEL_TEXT = { business: "Business", private: "Private", everyday: "Everyday", mixed: "Mixed" };

function prereqList(list) {
  if (!Array.isArray(list) || !list.length) return null;
  return h("ul", { class: "rows" }, list.map((p) => h("li", { class: "row" },
    h("p", { class: "row-title" }, `${p.met ? "Met" : "Not met"}: ${p.label || p.id}`))));
}

function crossingRow(x, refresh) {
  const pending = x.status === "pending";
  const yes = h("button", { class: "btn btn-primary", type: "button" }, "Share exactly this…");
  const no = h("button", { class: "btn", type: "button" }, "Keep it private");
  yes.addEventListener("click", async () => {
    // Delta review N-3: re-authentication (when needed) is verified inside THIS approval.
    const r = await confirmDialog({
      title: "Share with the business side",
      lines: [x.question || "", x.origin === "laura_draft" ? "Laura drafted this request; it is shown word for word." : "Quoted from what you wrote.",
        "Recorded as a boundary crossing holding this text only."],
      confirmLabel: "Share", stepUp: !!x.requires_stepup, totpRequired: authState().totpRequired });
    if (!r.confirmed) { toast("Cancelled. Nothing was shared.", "info"); return; }
    try {
      await api.lauraUnifiedCrossing(x.id, true, x.requires_stepup ? { passphrase: r.passphrase, totp: r.totp } : null);
      toast("Shared with the business side.", "info");
      refresh();
    } catch (e) { toast(`${e.message || "Refused"}${e.code ? ` (${e.code})` : ""}`, "bad"); }
  });
  no.addEventListener("click", async () => {
    try { await api.lauraUnifiedCrossing(x.id, false); toast("Kept private. Nothing was shared.", "info"); refresh(); }
    catch (e) { toast(e.message, "bad"); }
  });
  return h("li", { class: "row laura-crossing", data: { status: x.status } },
    h("p", { class: "row-title" }, "Laura: Can I share this with the business side? ", statusPill(pending ? "BLOCKED" : (x.status === "approved" ? "OK" : "UNKNOWN"), x.status)),
    h("p", { class: "row-detail" }, `“${x.text}”`),
    pending ? h("div", { class: "row-actions" }, yes, no) : null);
}

function turnRow(t, refresh, selected) {
  const box = h("input", { type: "checkbox", aria: { label: "select message" } });
  box.addEventListener("change", () => { if (box.checked) selected.add(t.id); else selected.delete(t.id); });
  const who = t.role === "laura" ? "Laura" : "You";
  const side = t.role === "laura" && String(t.model_ref || "").startsWith("business/") ? " · business tool" : "";
  return h("li", { class: ["row", t.role === "laura" ? "laura-a" : "laura-q"], data: { label: t.label } },
    h("p", { class: "row-title" }, t.role === "owner" ? box : null, `${who}${side} · `, h("span", { class: "muted small" }, LABEL_TEXT[t.label] || t.label),
      t.excluded ? h("span", { class: "muted small" }, " · excluded from context") : null),
    h("p", { class: "row-detail" }, t.text || ""),
    h("p", { class: "muted small" }, t.at ? utcStamp(t.at) : ""));
}

// D-W4-LAURA-UNIFIED-FEED: exactly which allowlisted company-context fields Venice would get.
function feedPreview() {
  const box = h("div", { class: "stack" });
  const btn = h("button", { class: "btn", type: "button" }, "Preview the company context Laura's conversation model would see");
  btn.addEventListener("click", async () => {
    try {
      const p = ((await api.lauraUnifiedFeedPreview()) || {}).data || {};
      clear(box);
      box.append(h("p", { class: "muted small" }, `${p.enabled ? "ON" : "OFF (nothing is sent)"} · ${p.switch || ""} · ${p.bytes || 0} of ${p.max_bytes || 0} bytes · sha256 ${String(p.sha256 || "").slice(0, 12)}…`),
        h("ul", { class: "rows" }, (p.fields || []).map((f) => h("li", { class: "row" },
          h("p", { class: "row-title" }, `${f.name} (${f.sensitivity})`),
          h("p", { class: "row-detail" }, JSON.stringify(f.value)),
          h("p", { class: "muted small" }, `source: ${f.source}`)))),
        (p.dropped || []).length ? h("p", { class: "callout callout-warn" }, `Dropped (failed a check; never sent): ${(p.dropped || []).map((d) => d.name).join(", ")}`) : null);
    } catch (e) { toast(e.message, "bad"); }
  });
  return h("details", { class: "laura-feed" }, h("summary", null, "Company context feed"), btn, box);
}

export function unifiedCard(status) {
  const st = status || {};
  const body = h("div", { class: "stack" });
  const selected = new Set();
  const refresh = async () => {
    let v;
    try { v = ((await api.lauraUnifiedView()) || {}).data || {}; } catch (e) { toast(e.message, "bad"); return; }
    clear(body);
    selected.clear();
    const turns = Array.isArray(v.turns) ? v.turns : [];
    const xs = Array.isArray(v.crossings) ? v.crossings : [];
    body.append(h("p", { class: "muted small" }, `${turns.length} message(s) in one encrypted thread · ${v.notes || 0} private note(s). ` +
      (v.business_to_venice ? "Business exchanges are shared with Laura's conversation model (you approved this)." : "Business exchanges stay with the business side; Laura's conversation model sees only that one happened.")));
    body.append(h("ul", { class: "rows laura-thread" }, turns.map((t) => turnRow(t, refresh, selected))));
    if (xs.length) body.append(h("ul", { class: "rows" }, xs.map((x) => crossingRow(x, refresh))));
    const control = (action, label) => h("button", { class: "btn", type: "button", onclick: async () => {
      if (!selected.size) { toast("Select your messages first (their replies follow them).", "info"); return; }
      try { await api.lauraUnifiedControl(action, [...selected]); toast(`${label}: done.`, "info"); refresh(); } catch (e) { toast(e.message, "bad"); } } }, label);
    body.append(h("div", { class: "row-actions" }, control("mark_private", "Mark private"), control("exclude", "Exclude from context"),
      control("include", "Include again"), control("forget", "Delete")));
    const input = h("input", { type: "text", maxLength: 2000, autocomplete: "off", placeholder: "Talk to Laura — anything (stored encrypted)" });
    const keep = h("input", { type: "checkbox", id: "laura-keep-private" });
    const send = h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
      const text = input.value.trim(); if (!text) return;
      send.disabled = true;
      try {
        const out = ((await api.lauraUnifiedTurn(text, keep.checked)) || {}).data || {};
        input.value = "";
        if (out.reply_status && out.reply_status !== "REPLIED") toast(out.why || out.reply_status, "info");
        // Security review B-1(d): say when code, not Laura, routed the turn (nothing was sent).
        const rb = (out.intent && out.intent.routed_by) || "laura";
        if (rb !== "laura") toast(`Routed by code (${rb}): nothing was sent to the business side automatically; tap "Share" to send your words.`, "info");
      } catch (e) { toast(e.message, "bad"); }
      send.disabled = false;
      refresh();
    } }, "Send");
    body.append(h("div", { class: "ask-form" }, input, send),
      h("label", { class: "muted small", for: "laura-keep-private" }, keep, " Keep this private (never sent to the business side)"),
      h("button", { class: "btn", type: "button", onclick: async () => { await api.privateClose(); clear(body); toast("Conversation closed.", "info"); } }, "Close"));
  };
  const openBtn = h("button", { class: "btn btn-primary", type: "button" }, "Open our conversation…");
  openBtn.addEventListener("click", async () => {
    const out = await guardedAction({ title: "Open your conversation with Laura",
      lines: ["One thread for everything: business, everyday, personal.",
        "Owner-only and encrypted. Business work goes to the business side with business content only; anything private crosses only if you approve the exact text.",
        "Needs a fresh re-authentication; closes on sign-out or after 30 minutes."],
      confirmLabel: "Open", requiresStepUp: true, run: () => api.privateOpen(), success: "Open." });
    if (out) refresh();
  });
  return card({ title: "Laura", subtitle: "One conversation", cls: "laura-unified" },
    h("p", { class: "muted small" }, `Conversation: ${st.venice_replies === "ENABLED" ? "Venice, enabled" : "Venice, gated"} · business tools: Claude (budget laura) · conversation budget: laura_private.`),
    h("p", { class: "muted small" }, st.business_to_venice_label || ""),
    st.prerequisites ? h("p", { class: "muted small" }, `Activation prerequisites: ${st.prerequisites.filter((p) => p.met).length} of ${st.prerequisites.length} met.`) : null,
    prereqList(st.prerequisites),
    feedPreview(),
    st.configured ? openBtn : h("p", { class: "callout callout-warn" }, "The encrypted store has no key here, so the conversation cannot open."),
    body);
}
