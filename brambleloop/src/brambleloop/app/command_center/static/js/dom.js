// DOM helpers. Every piece of dynamic text enters the page as a Text node or through
// textContent. There is deliberately no HTML-string path in this app: a product title, an
// agent's reason or an exception message is data, and data is never parsed as markup.

const ALLOWED_PROPS = new Set(["value", "checked", "disabled", "type", "name", "id",
  "placeholder", "autocomplete", "inputMode", "required", "hidden", "tabIndex", "htmlFor",
  "rows", "maxLength", "min", "max", "step", "title", "loading", "alt", "width", "height",
  "open"]);

/** Only same-origin paths, in-app hash routes and http(s) links may become an href/src. */
export function safeUrl(value) {
  const v = String(value ?? "").trim();
  if (v.startsWith("#")) return v;
  if (v.startsWith("/") && !v.startsWith("//")) return v;
  if (/^https:\/\//i.test(v)) return v;
  return "";
}

/**
 * h("div", {class: "card", onclick: fn, aria: {label: "x"}}, "text", child)
 * Strings and numbers become Text nodes. null/undefined/false children are skipped.
 */
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") el.className = Array.isArray(v) ? v.filter(Boolean).join(" ") : v;
      else if (k === "text") el.textContent = String(v);
      else if (k === "aria") for (const [ak, av] of Object.entries(v)) {
        if (av !== undefined && av !== null) el.setAttribute(`aria-${ak}`, String(av));
      }
      else if (k === "data") for (const [dk, dv] of Object.entries(v)) el.dataset[dk] = String(dv);
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (k === "href" || k === "src") {
        const u = safeUrl(v);
        if (u) el.setAttribute(k, u);
      }
      else if (k === "role" || k === "for" || k === "lang" || k === "rel" || k === "target"
               || k === "datetime" || k === "enterkeyhint" || k === "autocapitalize") {
        el.setAttribute(k === "for" ? "for" : k, String(v));
      }
      else if (ALLOWED_PROPS.has(k)) el[k] = v;
      else throw new Error(`h(): attribute ${k} is not allowed`);
    }
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

/** Inline SVG icon from a fixed, code-owned set of path data (never from data). */
const ICONS = {
  home: "M3 11 12 4l9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  approvals: "M9 12l2 2 4-4M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z",
  store: "M4 9l1.5-5h13L20 9M4 9h16v11H4zM4 9a3 3 0 0 0 5.3 1.9A3 3 0 0 0 12 12a3 3 0 0 0 2.7-1.1A3 3 0 0 0 20 9M10 20v-5h4v5",
  money: "M12 3v18M17 7.5C17 5.6 14.8 5 12 5S7 6 7 8s2 2.6 5 3 5 1 5 3.2S14.9 19 12 19s-5-.8-5-2.8",
  operations: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  learn: "M12 3 2 8l10 5 10-5zM6 10.5V16c2 2 10 2 12 0v-5.5",
  insights: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  notifications: "M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
  account: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  laura: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0M17 3.5c1.5.6 2.5 2 2.5 3.5",
  ask: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2zM9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.4M12 14.5v.01",
  timeline: "M12 6v6l4 2M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  back: "M15 18l-6-6 6-6",
  chevron: "M9 18l6-6-6-6",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  pause: "M8 5v14M16 5v14",
  refresh: "M21 12a9 9 0 1 1-2.6-6.4L21 8M21 3v5h-5",
  external: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
};
const SVG_NS = "http://www.w3.org/2000/svg";

export function icon(name, size = 22) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("class", "icon");
  const p = document.createElementNS(SVG_NS, "path");
  p.setAttribute("d", ICONS[name] || ICONS.more);
  svg.append(p);
  return svg;
}
