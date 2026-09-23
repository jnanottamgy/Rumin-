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
        path: "scenarios",
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
