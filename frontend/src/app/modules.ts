/**
 * The product's module registry: navigation, and an honest development status for each
 * area. Statuses here describe the UI; what the backend can compute comes from
 * GET /api/v1/system (`capabilities`) and is shown alongside.
 */

export type ModuleStatus = "available" | "foundation" | "planned";

export interface AppModule {
  id: string;
  path: string;
  navLabel: string;
  title: string;
  summary: string;
  status: ModuleStatus;
  statusNote: string;
  phase: number;
}

export const APP_MODULES: readonly AppModule[] = [
  {
    id: "overview",
    path: "/dashboard",
    navLabel: "Overview",
    title: "Overview",
    summary: "Workspace status, the network at a glance and recent scenarios.",
    status: "available",
    statusNote: "Available",
    phase: 1,
  },
  {
    id: "universe",
    path: "/universe",
    navLabel: "Universe",
    title: "Financial Universe",
    summary: "Explore companies, industries, countries and economic variables as a network.",
    status: "available",
    statusNote: "2D network available · 3D universe planned for Phase 8",
    phase: 1,
  },
  {
    id: "graph",
    path: "/graph",
    navLabel: "Graph",
    title: "Knowledge Graph",
    summary:
      "Explore how RUMIN's records connect: neighbourhoods, paths and the evidence behind every relationship.",
    status: "available",
    statusNote: "Read-only explorer · built from the command line",
    phase: 3,
  },
  {
    id: "data",
    path: "/data",
    navLabel: "Data",
    title: "Data Explorer",
    summary: "Historical series and licensed price files, with their source, licence and quality.",
    status: "available",
    statusNote: "World Bank series and price-file import · ingestion from the command line",
    phase: 2,
  },
  {
    id: "simulation",
    path: "/simulation",
    navLabel: "Simulation",
    title: "Simulation",
    summary:
      "Run a model on stated inputs and assumptions, and see how the result was reached: pathway, months, contributions, sensitivity and provenance.",
    status: "available",
    statusNote: "Preview · five models, one run at a time",
    phase: 4,
  },
  {
    id: "scenarios",
    path: "/scenarios",
    navLabel: "Scenario Lab",
    title: "Scenario Lab",
    summary:
      "Ask what happens if something changes: models chosen by what they declare and what the graph states, the modelled pathway, months, stress cases, sensitivity and comparisons.",
    status: "available",
    statusNote: "Five models · versioned scenarios · reproducible executions",
    phase: 5,
  },
  {
    id: "analyst",
    path: "/analyst",
    navLabel: "Analyst",
    title: "AI Analyst",
    summary: "Ask questions about model assumptions and simulated outputs.",
    status: "planned",
    statusNote: "Not available · planned for Phase 7",
    phase: 7,
  },
  {
    id: "system",
    path: "/system",
    navLabel: "System",
    title: "System & settings",
    summary: "Runtime status, capabilities and display preferences.",
    status: "available",
    statusNote: "Available",
    phase: 1,
  },
];

export const STATUS_LABEL: Record<ModuleStatus, string> = {
  available: "Available",
  foundation: "Foundation",
  planned: "Planned",
};

export interface RoadmapPhase {
  phase: number;
  title: string;
}

export const CURRENT_PHASE = 5;

export const ROADMAP: readonly RoadmapPhase[] = [
  { phase: 1, title: "Foundation & system architecture" },
  { phase: 2, title: "Financial data infrastructure" },
  { phase: 3, title: "Financial knowledge graph" },
  { phase: 4, title: "Simulation engine" },
  { phase: 5, title: "Scenario Lab" },
  { phase: 6, title: "Financial intelligence" },
  { phase: 7, title: "AI Analyst" },
  { phase: 8, title: "3D financial universe" },
  { phase: 9, title: "Advanced simulation & validation" },
  { phase: 10, title: "Productization, security & launch" },
];
