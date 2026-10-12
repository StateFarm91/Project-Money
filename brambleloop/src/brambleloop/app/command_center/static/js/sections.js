// W4-CCUX: long pages on a phone. A tab with many titled cards gets a small toolbar:
//   * "On this page" -- a list of its sections; tapping one opens it and scrolls to it;
//   * "Collapse all" / "Expand all" -- folds every card down to its header (title + status),
//     so the page reads as a scannable list. A folded card has a "Show" button.
// Nothing is removed from the DOM: a folded card's evidence links and actions are hidden, not
// dropped, and come back on Show / Expand all. Cards start expanded unless the owner folded
// this tab earlier in the same page session (kept in memory only: no browser storage).
import { h, icon } from "./dom.js";

export const LONG_PAGE_MIN = 5;
const foldedTabs = new Set(); // tabs folded with "Collapse all" during this page session

function remembered(tab) { return foldedTabs.has(tab); }
function remember(tab, on) { if (on) foldedTabs.add(tab); else foldedTabs.delete(tab); }

/** The page's foldable cards: direct children of the view's stack with a titled header. */
export function foldableCards(stack) {
  if (!stack) return [];
  return [...stack.children].filter((el) => el.classList.contains("card") && !el.classList.contains("hero")
    && !el.classList.contains("card-error") && el.querySelector(":scope > .card-head .card-title"));
}

function titleOf(c) {
  return (c.querySelector(":scope > .card-head .card-title")?.textContent || "Section").trim();
}

function setFolded(c, folded) {
  c.classList.toggle("is-collapsed", folded);
  let btn = c.querySelector(":scope > .card-expand");
  if (folded && !btn) {
    btn = h("button", { class: "btn card-expand", type: "button", aria: { label: `Show ${titleOf(c)}` } },
      icon("chevron", 18), "Show");
    btn.addEventListener("click", () => { setFolded(c, false); c.querySelector(":scope > .card-head .card-title")?.focus?.(); });
    c.querySelector(":scope > .card-head").after(btn);
  } else if (!folded && btn) btn.remove();
}

/** Enhance a rendered view. Returns the toolbar (or null for a short page). */
export function enhanceLongPage(container, tab, { min = LONG_PAGE_MIN } = {}) {
  const stack = container && (container.classList?.contains("stack") ? container : container.querySelector(":scope > .stack"));
  const cards = foldableCards(stack);
  if (cards.length < min) return null;
  cards.forEach((c, i) => {
    const t = c.querySelector(":scope > .card-head .card-title");
    if (t && !t.hasAttribute("tabindex")) t.tabIndex = -1;
    if (!c.dataset.section) c.dataset.section = String(i + 1);
  });
  const toggle = h("button", { class: "btn btn-sm", type: "button", data: { fold: "all" } });
  const paint = (folded) => {
    toggle.textContent = folded ? "Expand all" : "Collapse all";
    toggle.setAttribute("aria-pressed", folded ? "true" : "false");
  };
  const foldAll = (on) => { for (const c of cards) setFolded(c, on); paint(on); remember(tab, on); };
  toggle.addEventListener("click", () => foldAll(toggle.getAttribute("aria-pressed") !== "true"));

  const index = h("details", { class: "page-index" },
    h("summary", null, `On this page · ${cards.length} sections`),
    h("ol", null, cards.map((c) => h("li", null, h("button", { class: "index-link", type: "button",
      onclick: () => {
        setFolded(c, false);
        index.open = false;
        c.scrollIntoView({ block: "start" });
        c.querySelector(":scope > .card-head .card-title")?.focus({ preventScroll: true });
      } }, titleOf(c))))));
  const bar = h("div", { class: "page-tools", role: "group", aria: { label: "Page sections" } }, index, toggle);
  stack.insertBefore(bar, cards[0]);
  const start = remembered(tab);
  if (start) foldAll(true); else paint(false);
  return bar;
}
