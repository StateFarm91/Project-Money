// "More" overflow menu for the phone tab bar.
import { h, icon } from "../dom.js";
import { TABS } from "../routes.js";

export async function render() {
  const items = [...TABS.filter((t) => !t.primary), { id: "emergency", label: "Emergency controls", icon: "shield", hint: "Pause publishing, spend or departments" }];
  return h("div", { class: "stack" },
    h("nav", { class: "card", aria: { label: "More sections" } },
      h("ul", { class: "menu" }, items.map((t) => h("li", null,
        h("a", { href: `#/${t.id}`, data: { more: t.id } }, icon(t.icon, 22),
          // W4-CCUX: a one-line hint under each label, so the phone menu says what is inside.
          h("span", { class: "menu-text" }, h("span", { class: "menu-label" }, t.label),
            t.hint ? h("span", { class: "menu-hint" }, t.hint) : null),
          h("span", { class: "badge", hidden: true, data: { badge: t.id } }),
          h("span", { class: "menu-chev" }, icon("chevron", 18))))))));
}
