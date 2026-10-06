// "More" overflow menu for the phone tab bar.
import { h, icon } from "../dom.js";
import { TABS } from "../routes.js";

export async function render() {
  const items = [...TABS.filter((t) => !t.primary), { id: "emergency", label: "Emergency controls", icon: "shield" }];
  return h("div", { class: "stack" },
    h("nav", { class: "card", aria: { label: "More sections" } },
      h("ul", { class: "menu" }, items.map((t) => h("li", null,
        h("a", { href: `#/${t.id}`, data: { more: t.id } }, icon(t.icon, 22), h("span", null, t.label),
          h("span", { class: "badge", hidden: true, data: { badge: t.id } }),
          h("span", { class: "menu-chev" }, icon("chevron", 18))))))));
}
