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
  { id: "production", label: "Production", icon: "operations", hint: "Product inventory by state, stalls, loops and agent activity" },
  { id: "p0_board", label: "P0 board", icon: "operations", hint: "Everything P0 at once, each with the level its evidence proves" },
  { id: "daily", label: "Daily", icon: "timeline", hint: "Daily production counts and why a stage made nothing" },
  { id: "demand", label: "Demand", icon: "insights", hint: "What the market buys and which engine to build next" },
  { id: "catalogue", label: "Catalogue", icon: "store", hint: "Every product by stage, with evidence, holds and next action" },
  { id: "agents_evidence", label: "Agent evidence", icon: "operations", hint: "Each department's last useful job, queues, dead letters and workers" },
  { id: "completion", label: "Completion effort", icon: "approvals", hint: "Launch packet and what must be true first" },
  { id: "policy", label: "Policy readings", icon: "approvals", hint: "Record your reading of each Etsy policy page" },
  { id: "operations", label: "Operations", icon: "operations", hint: "Incidents, queue, SLOs and cadences" },
  { id: "learn", label: "Autonomy & Learn", icon: "learn", hint: "Agents, Rule #1, loops and lessons" },
  { id: "insights", label: "Insights", icon: "insights", hint: "Market, search, ads and experiments" },
  { id: "notifications", label: "Notifications", icon: "notifications", hint: "Alerts waiting for you" },
  { id: "timeline", label: "Timeline", icon: "timeline", hint: "What happened, in order" },
  { id: "ask", label: "Ask Company", icon: "ask", hint: "Ask a question, get sourced answers" },
  { id: "account", label: "Account", icon: "account", hint: "Devices, sign-in, budgets and authority" },
];

export const MORE_ROUTES = TABS.filter((t) => !t.primary).map((t) => t.id);
