// Apply the saved theme before first paint to avoid a flash of the wrong theme. A file
// rather than an inline script, so the Content-Security-Policy can forbid inline scripts.
(() => {
  let pref = "system";
  let motion = "system";
  try {
    pref = localStorage.getItem("rumin.theme") || "system";
    motion = localStorage.getItem("rumin.motion") || "system";
  } catch {
    // Storage can be unavailable (private mode, blocked site data): use defaults.
  }
  const dark =
    pref === "dark" ||
    (pref === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const reduce =
    motion === "reduce" ||
    (motion === "system" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.dataset.motion = reduce ? "reduce" : "full";
})();
