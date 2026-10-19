// Navigation model. `primary` tabs sit in the phone bottom bar; the rest live under "More".
// Each id maps to js/views/<id>.js. `hint` is the one-line description in the More menu.
export const TABS = [
  { id: "laura", label: "Laura", icon: "laura", primary: true },
  { id: "home", label: "Home", icon: "home", primary: true },
  { id: "approvals", label: "Approvals", icon: "approvals", primary: true },
  { id: "money", label: "Money", icon: "money", primary: true },
  { id: "store", label: "Store", icon: "store", primary: true },
  { id: "company", label: "Company", icon: "operations", hint: "Departments, agents, blockers and your actions" },
  { id: "images", label: "Images", icon: "store", hint: "Gallery production, owner image upload" },
  { id: "completion", label: "Completion effort", icon: "approvals", hint: "Launch packet and what must be true first" },
  { id: "operations", label: "Operations", icon: "operations", hint: "Incidents, queue, SLOs and cadences" },
  { id: "learn", label: "Autonomy & Learn", icon: "learn", hint: "Agents, Rule #1, loops and lessons" },
  { id: "insights", label: "Insights", icon: "insights", hint: "Market, search, ads and experiments" },
  { id: "notifications", label: "Notifications", icon: "notifications", hint: "Alerts waiting for you" },
  { id: "timeline", label: "Timeline", icon: "timeline", hint: "What happened, in order" },
  { id: "ask", label: "Ask Company", icon: "ask", hint: "Ask a question, get sourced answers" },
  { id: "account", label: "Account", icon: "account", hint: "Devices, sign-in, budgets and authority" },
];

export const MORE_ROUTES = TABS.filter((t) => !t.primary).map((t) => t.id);
