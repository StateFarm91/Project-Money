// Navigation model. `primary` tabs sit in the phone bottom bar; the rest live under "More".
// Each id maps to js/views/<id>.js.
export const TABS = [
  { id: "home", label: "Home", icon: "home", primary: true },
  { id: "approvals", label: "Approvals", icon: "approvals", primary: true },
  { id: "money", label: "Money", icon: "money", primary: true },
  { id: "store", label: "Store", icon: "store", primary: true },
  { id: "operations", label: "Operations", icon: "operations" },
  { id: "learn", label: "Autonomy & Learn", icon: "learn" },
  { id: "insights", label: "Insights", icon: "insights" },
  { id: "notifications", label: "Notifications", icon: "notifications" },
  { id: "timeline", label: "Timeline", icon: "timeline" },
  { id: "ask", label: "Ask Company", icon: "ask" },
  { id: "account", label: "Account", icon: "account" },
];

export const MORE_ROUTES = TABS.filter((t) => !t.primary).map((t) => t.id);
