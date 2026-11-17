/**
 * Theme context + resolution helpers.
 *
 * Kept separate from ThemeProvider.tsx so that file only exports a component
 * (react-refresh requirement).
 */
import { createContext, useContext } from "react";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export interface ThemeContextValue {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
  toggle: () => void;
}

export const THEME_STORAGE_KEY = "labflow.theme";

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function systemTheme(): ResolvedTheme {
  if (typeof window === "undefined" || !window.matchMedia) return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function storedPreference(): ThemePreference {
  // LabFlow defaults to Light on every screen. Only an explicit Dark choice
  // is honoured; "system" from older builds resolves to Light.
  if (typeof window === "undefined") return "light";
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "dark") return "dark";
  } catch {
    // Private mode / storage disabled: fall through to the Light default.
  }
  return "light";
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  return preference === "system" ? systemTheme() : preference;
}

export function applyTheme(resolved: ResolvedTheme): void {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", resolved);
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error("useTheme must be used inside a ThemeProvider");
  }
  return value;
}
