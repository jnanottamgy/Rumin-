import "@fontsource-variable/inter";
import "@fontsource-variable/newsreader/opsz.css";
import "@fontsource-variable/jetbrains-mono";
import "@/styles/tokens.css";
import "@/styles/global.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";
import { createAppRouter } from "@/app/router";
import { ThemeProvider } from "@/app/theme";

const container = document.getElementById("root");
if (!container) throw new Error("RUMIN could not find its #root element.");

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <RouterProvider router={createAppRouter()} />
    </ThemeProvider>
  </StrictMode>,
);
