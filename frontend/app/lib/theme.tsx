"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Theme = "light" | "dark";

type ThemeContextValue = {
  theme: Theme;
  toggle: () => void;
  setTheme: (theme: Theme) => void;
};

const ThemeContext = createContext<ThemeContextValue>({
  theme: "light",
  toggle: () => {},
  setTheme: () => {}
});

const STORAGE_KEY = "safewalk-theme";

// App-wide theme so every page (map, reports, about) shares one toggle and the
// choice persists across navigations. The `dark-mode` class is applied to <body>
// so the existing `.dark-mode ...` rules in globals.css apply on every page.
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("light");

  // Hydrate from the last saved choice (after mount, to avoid SSR mismatch).
  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark") setThemeState(saved);
  }, []);

  useEffect(() => {
    document.body.classList.toggle("dark-mode", theme === "dark");
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => setThemeState(next), []);
  const toggle = useCallback(
    () => setThemeState((current) => (current === "dark" ? "light" : "dark")),
    []
  );

  return (
    <ThemeContext.Provider value={{ theme, toggle, setTheme }}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
