/**
 * Route table. The landing page loads eagerly (it is the entry point); application
 * pages are code-split with route-level `lazy`, so the first load stays small.
 */
import { createBrowserRouter, type RouteObject } from "react-router";
import { AppShell } from "@/layouts/AppShell";
import { LandingPage } from "@/pages/LandingPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { RouteErrorPage } from "@/pages/RouteErrorPage";
import { RouteLoading } from "@/pages/RouteLoading";

export const routes: RouteObject[] = [
  {
    path: "/",
    Component: LandingPage,
    ErrorBoundary: RouteErrorPage,
    HydrateFallback: RouteLoading,
  },
  {
    Component: AppShell,
    ErrorBoundary: RouteErrorPage,
    HydrateFallback: RouteLoading,
    children: [
      {
        path: "dashboard",
        lazy: async () => ({ Component: (await import("@/pages/DashboardPage")).DashboardPage }),
      },
      {
        path: "universe",
        lazy: async () => ({ Component: (await import("@/pages/UniversePage")).UniversePage }),
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
      { path: "*", Component: NotFoundPage },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
