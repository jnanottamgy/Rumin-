/**
 * Theme and motion preferences.
 *
 * Preferences are per-viewer conveniences stored in localStorage (wrapped in try/catch:
 * storage can be unavailable). The resolved values are written to <html> as
 * `data-theme` and `data-motion`, which the design tokens and global CSS read.
 * index.html applies the same logic before first paint to avoid a theme flash.
 */
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { useMediaQuery } from "@/hooks/useMediaQuery";

export type ThemePreference = "system" | "light" | "dark";
export type MotionPreference = "system" | "reduce" | "full";

const THEME_KEY = "rumin.theme";
const MOTION_KEY = "rumin.motion";

function readPreference<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = window.localStorage.getItem(key);
    return allowed.includes(value as T) ? (value as T) : fallback;
  } catch {
    return fallback;
  }
}

function writePreference(key: string, value: string): void {
  try {
    if (value === "system") window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Not persisted; the preference still applies for this visit.
  }
}

interface ThemeContextValue {
  theme: ThemePreference;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: ThemePreference) => void;
  motion: MotionPreference;
  reducedMotion: boolean;
  setMotion: (motion: MotionPreference) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>(() =>
    readPreference(THEME_KEY, ["system", "light", "dark"], "system"),
  );
  const [motion, setMotionState] = useState<MotionPreference>(() =>
    readPreference(MOTION_KEY, ["system", "reduce", "full"], "system"),
  );
  const systemDark = useMediaQuery("(prefers-color-scheme: dark)");
  const systemReduce = useMediaQuery("(prefers-reduced-motion: reduce)");

  const resolvedTheme = theme === "system" ? (systemDark ? "dark" : "light") : theme;
  const reducedMotion = motion === "system" ? systemReduce : motion === "reduce";

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
  }, [resolvedTheme]);

  useEffect(() => {
    document.documentElement.dataset.motion = reducedMotion ? "reduce" : "full";
  }, [reducedMotion]);

  const setTheme = useCallback((value: ThemePreference) => {
    setThemeState(value);
    writePreference(THEME_KEY, value);
  }, []);

  const setMotion = useCallback((value: MotionPreference) => {
    setMotionState(value);
    writePreference(MOTION_KEY, value);
  }, []);

  return (
    <ThemeContext.Provider
      value={{ theme, resolvedTheme, setTheme, motion, reducedMotion, setMotion }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside <ThemeProvider>.");
  return value;
}
