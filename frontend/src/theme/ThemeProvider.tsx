/**
 * Theme preference (light | dark | system) for the neumorphism auth screens.
 *
 * The preference lives in localStorage (`labflow.theme`) and is applied as
 * `data-theme` on <html>. The inline <head> script in index.html resolves the
 * same value before first paint; this provider keeps React in sync afterwards.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  THEME_STORAGE_KEY,
  ThemeContext,
  applyTheme,
  resolveTheme,
  storedPreference,
  systemTheme,
  type ResolvedTheme,
  type ThemePreference,
} from "./themeContext";

export function ThemeProvider({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  const [preference, setPreferenceState] =
    useState<ThemePreference>(storedPreference);
  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    resolveTheme(storedPreference()),
  );

  useEffect(() => {
    applyTheme(resolved);
  }, [resolved]);

  // A "system" preference follows the OS live.
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (): void => {
      if (preference === "system") setResolved(systemTheme());
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [preference]);

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
    setResolved(resolveTheme(next));
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Persisting is best-effort; the in-memory preference still applies.
    }
  }, []);

  const toggle = useCallback(() => {
    setPreference(resolved === "dark" ? "light" : "dark");
  }, [resolved, setPreference]);

  const value = useMemo(
    () => ({ preference, resolved, setPreference, toggle }),
    [preference, resolved, setPreference, toggle],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}
