// ASK COMPANY (F-928, F-929): source-linked answers from durable evidence; nothing invented.
import { h, clear } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, sourcesList, loading, toast } from "../components.js";
import { relTime, utcStamp } from "../format.js";

const SUGGESTIONS = ["What did Brambleloop do overnight?", "What is blocking launch?", "Why did profit fall?",
  "Why does this product need my approval?", "Are there open incidents?"];

const history = []; // this tab only; cleared on reload

function answerCard(a) {
  const status = String(a.status || "UNKNOWN").toUpperCase();
  const facts = Array.isArray(a.facts) ? a.facts : [];
  const sources = Array.isArray(a.sources) ? a.sources : [];
  return card({ title: a.question || "Question", actions: statusPill(status === "ANSWERED" ? "OK" : "UNKNOWN", status), cls: "answer-card" },
    h("p", { class: "answer", data: { answer: status } }, a.answer || "No answer."),
    status !== "ANSWERED" ? h("p", { class: "callout callout-warn" }, "The company could not find durable evidence for a confident answer, so it says so instead of guessing.") : null,
    !sources.length && status === "ANSWERED" ? h("p", { class: "callout callout-bad" }, "This answer has no sources, so treat it as unverified.") : null,
    facts.length ? h("div", null, h("h3", { class: "section-title" }, "Facts"),
      h("ul", { class: "rows" }, facts.map((f) => h("li", { class: "row" },
        h("p", { class: "row-title" }, f.statement || String(f)),
        h("p", { class: "row-detail" },
          f.source ? h("a", { href: `#/drill/${encodeURIComponent(f.source)}` }, f.source) : "no source",
          f.as_of ? ` · as of ${relTime(f.as_of)} (${utcStamp(f.as_of)})` : ""))))) : null,
    a.next_action ? h("p", { class: "callout callout-info" }, `Next action: ${a.next_action}`) : null,
    sourcesList(sources),
    a.method ? h("p", { class: "muted small" }, `Method: ${a.method}`) : null);
}

export async function render() {
  const out = h("div", { class: "qa", aria: { live: "polite" } });
  const input = h("input", { id: "ask-q", type: "search", maxLength: 300, autocomplete: "off", enterkeyhint: "send",
    placeholder: "Ask about work, money, launch, products…" });
  const btn = h("button", { class: "btn btn-primary", type: "submit" }, "Ask");
  const redraw = () => { clear(out); for (const a of history.slice().reverse()) out.append(answerCard(a)); };
  const ask = async (question) => {
    const q = String(question || "").trim();
    if (!q) return;
    btn.disabled = true;
    const pending = loading("Searching company evidence");
    out.prepend(pending);
    try {
      const a = await api.ask(q);
      history.push({ ...(a || {}), question: (a && a.question) || q });
      input.value = "";
    } catch (e) {
      toast(e.message, "bad");
    } finally {
      btn.disabled = false;
      redraw();
    }
  };
  const form = h("form", { class: "ask-form", role: "search" },
    h("div", null, h("label", { class: "field", for: "ask-q" }, "Ask the company"), input), btn);
  form.addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); });
  redraw();
  return h("div", { class: "stack" },
    card({ title: "Ask Company", subtitle: "Answers come from durable company records with links to the evidence. If there is no evidence, it says Unknown." },
      form,
      h("div", { class: "chips" }, SUGGESTIONS.map((s) => h("button", { class: "chip", type: "button", onclick: () => ask(s) }, s)))),
    out);
}
