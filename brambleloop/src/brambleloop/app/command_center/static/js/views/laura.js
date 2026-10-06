// TALK TO LAURA (D-FB-13, spec/07 item 9): the owner's business conversation with Brambleloop's
// AI Founder/CEO. Every answer comes from durable company records with links to the evidence;
// with no evidence she says Unknown. Follow-on work needs explicit confirmation, and protected
// work (publish, spend, price, customer messages) needs a fresh owner step-up and only ever
// becomes an owner decision -- never an action she takes herself.
import { h, clear } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, sourcesList, loading, toast, guardedAction } from "../components.js";
import { relTime, utcStamp } from "../format.js";

const PORTRAIT_LABEL = "Internal — canonical reference, not publication-approved";

function inAppLink(link, text) {
  const href = typeof link === "string" && link.startsWith("#/") ? link : null;
  return href ? h("a", { href }, text) : h("span", { class: "mono" }, text);
}

function pillFor(status) {
  const s = String(status || "UNKNOWN").toUpperCase();
  return statusPill(s === "ANSWERED" ? "OK" : s === "PARTIAL" ? "DEGRADED" : "UNKNOWN", s);
}

function portrait(speaker) {
  const src = speaker && typeof speaker.portrait_path === "string" ? speaker.portrait_path : "";
  const label = (speaker && speaker.portrait_label) || PORTRAIT_LABEL;
  return h("figure", { class: "laura-portrait" },
    src ? h("img", { src, alt: `Laura, ${label}`, width: 96, height: 96, loading: "lazy" }) : null,
    h("figcaption", { class: "laura-internal" }, label));
}

function factList(facts) {
  if (!facts.length) return null;
  return h("details", { class: "laura-evidence" },
    h("summary", null, `Evidence (${facts.length})`),
    h("ul", { class: "rows" }, facts.map((f) => h("li", { class: "row" },
      h("p", { class: "row-title" }, f.statement || String(f)),
      h("p", { class: "row-detail" },
        f.source ? inAppLink(f.link, f.source) : "no source",
        f.basis && f.basis !== "measured" ? ` · ${f.basis}` : "",
        f.as_of ? ` · as of ${relTime(f.as_of)} (${utcStamp(f.as_of)})` : "")))));
}

function proposalRow(turnId, p, onDone) {
  const isProtected = !!p.requires_step_up;
  const btn = h("button", { class: ["btn", isProtected ? "btn-danger" : "btn-primary"], type: "button" },
    isProtected ? "Ask for my decision…" : "Create follow-on…");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    const out = await guardedAction({
      title: isProtected ? "Record a protected decision for you" : "Create internal follow-on work",
      lines: [p.title, `Why: ${p.why}`, `Department: ${p.department} · job: ${p.job_type}`,
        `Authority: ${p.authority}`,
        isProtected ? "Protected: Laura cannot do this herself. It becomes an owner decision in Approvals, and the act still needs its own grant." :
          "Internal GREEN work through the COO orchestrator: no publishing, spending or customer contact."],
      confirmLabel: isProtected ? "Record decision" : "Create",
      requiresStepUp: isProtected,
      run: () => api.lauraFollowOn(turnId, p.key),
      success: isProtected ? "Recorded as an owner decision in Approvals." : "Follow-on created.",
    });
    btn.disabled = false;
    if (out) onDone(out);
  });
  return h("li", { class: "row" },
    h("p", { class: "row-title" }, p.title, " ", statusPill(isProtected ? "BLOCKED" : "OK", isProtected ? "Protected · step-up" : "GREEN")),
    h("p", { class: "row-detail" }, p.why),
    p.evidence && p.evidence.length ? h("p", { class: "row-detail muted" }, `Based on: ${p.evidence.slice(0, 3).join(", ")}`) : null,
    h("div", { class: "row-actions" }, btn));
}

function turnCard(t) {
  const facts = Array.isArray(t.facts) ? t.facts : [];
  const unknowns = Array.isArray(t.unknowns) ? t.unknowns : [];
  const proposals = Array.isArray(t.proposals) ? t.proposals : [];
  const status = String(t.status || "UNKNOWN").toUpperCase();
  const done = h("p", { class: "callout callout-info", hidden: true });
  return h("article", { class: "laura-turn" },
    h("p", { class: "laura-q" }, h("span", { class: "muted small" }, "You · "), t.question || ""),
    card({ title: "Laura", actions: pillFor(status), cls: "laura-a" },
      h("p", { class: "answer", data: { answer: status } }, t.answer || "UNKNOWN"),
      status === "UNKNOWN" ? h("p", { class: "callout callout-warn" }, "No durable evidence answers this yet, so Laura says so instead of guessing.") : null,
      unknowns.length && status !== "UNKNOWN" ? h("p", { class: "callout callout-warn" },
        "Unknown: " + unknowns.map((u) => u.title).join(", ")) : null,
      factList(facts),
      sourcesList(t.sources || []),
      proposals.length ? h("div", null, h("h3", { class: "section-title" }, "Follow-on work she can start"),
        h("ul", { class: "rows" }, proposals.map((p) => proposalRow(t.turn_id, p, (out) => {
          done.hidden = false;
          clear(done);
          done.append(`${out.kind === "owner_action" ? "Owner decision" : "Mission"} recorded: `, inAppLink(
            String(out.result_ref || "").startsWith("jobs:") ? `#/drill/${out.result_ref}` : "#/approvals", out.result_ref || ""));
        })))) : null,
      done,
      h("p", { class: "muted small" }, t.at ? `${utcStamp(t.at)} · ` : "", t.method ? `Method: ${t.method}` : "")));
}

function headerCard(ov) {
  const sp = ov.speaker || {};
  const idn = ov.identity || {};
  const needs = ov.needs_you || {};
  return card({ title: `${sp.name || "Laura"} · ${sp.role || ""}`, subtitle: sp.public_identity || "", cls: "laura-head" },
    h("div", { class: "laura-id" }, portrait(sp),
      h("div", null,
        h("p", null, "Talk to me about the business. I answer from the company's records, with links, and I tell you when I don't know."),
        h("p", { class: "muted small" }, `Identity ${idn.identity_id || "UNKNOWN"} · source ${idn.source || "UNKNOWN"}`),
        idn.identity_disagreement ? h("p", { class: "callout callout-bad" }, `Identity disagreement reported: ${idn.identity_disagreement} (canonical id kept)`) : null,
        h("p", null, h("a", { href: "#/approvals" }, needs.status === "UNKNOWN" ? "Needs you: Unknown" :
          `Needs you: ${needs.count ?? "Unknown"}`), " · ", ov.phase || "phase Unknown"))));
}

function modeRow(ph) {
  const active = ph.status === "ACTIVE";
  const needs = Array.isArray(ph.needs) ? ph.needs : [];
  return h("li", { class: "row" },
    h("p", { class: "row-title" }, `Phase ${ph.phase} · ${ph.mode}`, " ", statusPill(active ? "OK" : "BLOCKED", active ? "Active" : "Gated")),
    h("p", { class: "row-detail" }, ph.what || ""),
    needs.length ? h("details", null, h("summary", null, `What it needs (${needs.length})`),
      h("ul", { class: "rows" }, needs.map((n) => h("li", { class: "row" },
        h("p", { class: "row-title" }, n.need), h("p", { class: "row-detail muted" }, `${n.who} · ${n.kind} · max cost ${n.max_cost}`))))) : null);
}

// Visible canonical Laura and how she can be reached: text now; voice and live presence are
// architected (same identity, memory and authority) but gated on provider + owner decisions.
function presenceCard(pres) {
  const caps = (pres && pres.capabilities) || {};
  const vis = (pres && pres.visible_identity) || {};
  const frames = Array.isArray(vis.frames) ? vis.frames.filter((f) => f.displayable_to_owner && typeof f.path === "string" && f.path.startsWith("/api/cc/laura/frame/")) : [];
  return card({ title: "Laura's presence", subtitle: `Modes: ${caps.degradation || "text"}`, cls: "laura-presence" },
    h("p", { class: "callout callout-warn" }, vis.state || "Visible identity: Unknown"),
    frames.length ? h("details", { class: "laura-frames" }, h("summary", null, `Canonical reference frames (${frames.length}) — internal`),
      h("div", { class: "laura-frame-row" }, frames.map((f) => h("figure", { class: "laura-frame" },
        h("img", { src: f.path, alt: `Laura, ${f.frame} (${f.label})`, loading: "lazy", width: 120, height: 160 }),
        h("figcaption", { class: "laura-internal" }, f.label))))) : null,
    h("ul", { class: "rows" }, (Array.isArray(caps.phases) ? caps.phases : []).map(modeRow)),
    h("p", { class: "muted small" }, `Identity ${vis.identity_id || "Unknown"} · publication-approved frames: ${vis.publication_approved_frames ?? "Unknown"}`));
}

// Owner-private context: opened only with a fresh step-up; content is fetched by POST and
// shown only here. Laura's private reply register is GATED -- nothing is generated.
function privateCard(status) {
  const st = status || {};
  const body = h("div", { class: "stack" });
  const show = (v) => {
    clear(body);
    const rows = [...(v.facts || []), ...(v.conversation || [])];
    body.append(h("p", { class: "muted small" }, `${(v.facts || []).length} note(s) · ${(v.conversation || []).length} message(s). Laura's private replies: ${v.reply_register || "GATED"}.`));
    if (rows.length) body.append(h("ul", { class: "rows" }, rows.map((r) => h("li", { class: "row" },
      h("p", { class: "row-title" }, r.key ? `${r.key}: ` : (r.role ? `${r.role}: ` : ""), r.text || ""),
      h("div", { class: "row-actions" }, h("button", { class: "btn", type: "button", onclick: async () => {
        await api.privateForget(r.id); show(await api.privateView()); } }, "Forget"))))));
    const note = h("input", { type: "text", maxLength: 2000, autocomplete: "off", placeholder: "Write to Laura (stored encrypted; no reply is generated)" });
    const send = h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
      const t = note.value.trim(); if (!t) return;
      try { const out = await api.privateTurn(t); note.value = ""; toast(out.why || "Stored.", "info"); show(await api.privateView()); }
      catch (e) { toast(e.message, "bad"); } } }, "Store");
    body.append(h("div", { class: "ask-form" }, note, send),
      h("button", { class: "btn", type: "button", onclick: async () => { await api.privateClose(); clear(body); toast("Private context closed.", "info"); } }, "Close private context"));
  };
  const openBtn = h("button", { class: "btn", type: "button" }, "Open private context…");
  openBtn.addEventListener("click", async () => {
    const out = await guardedAction({ title: "Open the private context",
      lines: ["Owner-only, encrypted, never shown to customers, the store, departments or Ask Company.",
        "Needs a fresh re-authentication; closes on sign-out or after 30 minutes.",
        "Laura's private reply register is not implemented (gated)."],
      confirmLabel: "Open", requiresStepUp: true, run: () => api.privateOpen(), success: "Private context open." });
    if (out) { try { show(await api.privateView()); } catch (e) { toast(e.message, "bad"); } }
  });
  return card({ title: "Private", subtitle: st.configured ? "Configured · closed by default" : "Not configured on this server", cls: "laura-private" },
    h("p", { class: "muted small" }, st.reply_why || "Laura's private register: gated."),
    st.configured ? openBtn : h("p", { class: "callout callout-warn" }, "The private store has no key here, so it refuses everything. Nothing else is affected."),
    body);
}

export async function render() {
  const [ovRes, histRes, presRes, privRes] = await Promise.all([api.laura(), api.lauraConversation(20),
    api.lauraPresence().catch(() => ({ data: null })), api.privateStatus().catch(() => ({ data: null }))]);
  const ov = ovRes.data || {};
  const turns = ((histRes.data && histRes.data.turns) || []).slice().reverse(); // oldest first
  const thread = h("div", { class: "laura-thread", aria: { live: "polite" } });
  const redraw = () => { clear(thread); for (const t of turns) thread.append(turnCard(t)); };
  const input = h("input", { id: "laura-q", type: "text", maxLength: 300, autocomplete: "off", enterkeyhint: "send",
    placeholder: "Ask Laura about the business…" });
  const btn = h("button", { class: "btn btn-primary", type: "submit" }, "Ask");
  const ask = async (question) => {
    const q = String(question || "").trim();
    if (!q) return;
    btn.disabled = true;
    const pending = loading("Laura is reading the records");
    thread.append(pending);
    try {
      const a = await api.lauraAsk(q);
      turns.push(a || { question: q, status: "UNKNOWN", answer: "UNKNOWN" });
      input.value = "";
    } catch (e) {
      toast(e.message, "bad");
    } finally {
      btn.disabled = false;
      redraw();
      const last = thread.lastElementChild;
      if (last && last.scrollIntoView) last.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  };
  const form = h("form", { class: "ask-form laura-form" },
    h("div", null, h("label", { class: "field", for: "laura-q" }, "Ask Laura"), input), btn);
  form.addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); });
  const suggested = [...(Array.isArray(ov.suggested) ? ov.suggested : []), "I don't like that banner. Have Design make three more."];
  redraw();
  return h("div", { class: "stack laura" },
    headerCard(ov),
    presRes.data ? presenceCard(presRes.data) : null,
    thread,
    card({ title: "Ask", subtitle: "Business conversation. Evidence-linked answers; Unknown when there is no evidence." },
      form,
      h("div", { class: "chips" }, suggested.map((s) => h("button", { class: "chip", type: "button", onclick: () => ask(s) }, s)))),
    privRes.data ? privateCard(privRes.data) : null);
}
