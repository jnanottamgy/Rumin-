/**
 * Route table. The landing page and the sign-in pages load eagerly (they are the entry
 * points); application pages are code-split with route-level `lazy`, so the first load stays
 * small.
 *
 * Everything sits under `SessionRoot`, which knows who is signed in. The introduction and
 * the sign-in page are public; every other page is behind `RequireSession` (Phase 10), which
 * sends a visitor to sign in and a person with a temporary password to choose their own.
 * The API enforces the same rules on every request; these routes only follow them.
 */
import { createBrowserRouter, type RouteObject } from "react-router";
import { RequireSession, SessionRoot } from "@/app/session";
import { AppShell } from "@/layouts/AppShell";
import { LandingPage } from "@/pages/LandingPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { PasswordPage } from "@/pages/PasswordPage";
import { RouteErrorPage } from "@/pages/RouteErrorPage";
import { RouteLoading } from "@/pages/RouteLoading";

const workspace: RouteObject[] = [
  {
    path: "dashboard",
    lazy: async () => ({ Component: (await import("@/pages/DashboardPage")).DashboardPage }),
  },
  {
    path: "universe",
    lazy: async () => ({ Component: (await import("@/pages/UniversePage")).UniversePage }),
  },
  {
    path: "universe/3d",
    lazy: async () => ({
      Component: (await import("@/pages/UniverseSpacePage")).UniverseSpacePage,
    }),
  },
  {
    path: "graph",
    lazy: async () => ({
      Component: (await import("@/pages/GraphExplorerPage")).GraphExplorerPage,
    }),
  },
  {
    path: "data",
    lazy: async () => ({
      Component: (await import("@/pages/DataExplorerPage")).DataExplorerPage,
    }),
  },
  {
    path: "data/series/:seriesId",
    lazy: async () => ({
      Component: (await import("@/pages/EconomicSeriesPage")).EconomicSeriesPage,
    }),
  },
  {
    path: "data/instruments/:instrumentId",
    lazy: async () => ({
      Component: (await import("@/pages/InstrumentPage")).InstrumentPage,
    }),
  },
  {
    path: "data/jobs/:jobId",
    lazy: async () => ({
      Component: (await import("@/pages/IngestionJobPage")).IngestionJobPage,
    }),
  },
  {
    path: "scenarios",
    lazy: async () => ({
      Component: (await import("@/pages/ScenarioLabPage")).ScenarioLabPage,
    }),
  },
  {
    path: "scenarios/new",
    lazy: async () => ({
      Component: (await import("@/pages/ScenarioLabPage")).ScenarioLabPage,
    }),
  },
  {
    path: "scenarios/compare",
    lazy: async () => ({
      Component: (await import("@/pages/ScenarioLabPage")).ScenarioLabPage,
    }),
  },
  {
    path: "scenarios/:scenarioId",
    lazy: async () => ({
      Component: (await import("@/pages/ScenarioLabPage")).ScenarioLabPage,
    }),
  },
  {
    path: "simulation",
    lazy: async () => ({
      Component: (await import("@/pages/SimulationPage")).SimulationPage,
    }),
  },
  {
    path: "simulation/runs/:runId",
    lazy: async () => ({
      Component: (await import("@/pages/SimulationPage")).SimulationPage,
    }),
  },
  {
    path: "intelligence",
    lazy: async () => ({
      Component: (await import("@/pages/IntelligencePage")).IntelligencePage,
    }),
  },
  {
    path: "intelligence/analyses/:analysisId",
    lazy: async () => ({
      Component: (await import("@/pages/IntelligencePage")).IntelligencePage,
    }),
  },
  {
    path: "intelligence/:entityKey",
    lazy: async () => ({
      Component: (await import("@/pages/IntelligencePage")).IntelligencePage,
    }),
  },
  {
    path: "analyst",
    lazy: async () => ({ Component: (await import("@/pages/AnalystPage")).AnalystPage }),
  },
  {
    path: "system",
    lazy: async () => ({ Component: (await import("@/pages/SystemPage")).SystemPage }),
  },
  {
    path: "people",
    lazy: async () => ({ Component: (await import("@/pages/PeoplePage")).PeoplePage }),
  },
  { path: "*", Component: NotFoundPage },
];

export const routes: RouteObject[] = [
  {
    Component: SessionRoot,
    ErrorBoundary: RouteErrorPage,
    HydrateFallback: RouteLoading,
    children: [
      { path: "/", Component: LandingPage, ErrorBoundary: RouteErrorPage },
      { path: "login", Component: LoginPage, ErrorBoundary: RouteErrorPage },
      {
        Component: RequireSession,
        ErrorBoundary: RouteErrorPage,
        children: [
          { path: "account/password", Component: PasswordPage },
          { Component: AppShell, ErrorBoundary: RouteErrorPage, children: workspace },
        ],
      },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
