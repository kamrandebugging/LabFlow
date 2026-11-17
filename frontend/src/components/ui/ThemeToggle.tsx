import type { ReactElement } from "react";

import { useTheme, type ResolvedTheme } from "../../theme/themeContext";
import styles from "./ThemeToggle.module.css";

export interface ThemeToggleProps {
  /** Extra class for placement on the host screen. */
  className?: string;
}

const OPTIONS: ReadonlyArray<{ value: ResolvedTheme; label: string }> = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

/**
 * The one Light/Dark control. Every state carries two signals: the pressed
 * attribute plus a fill/border change, never colour alone.
 */
export function ThemeToggle({ className }: ThemeToggleProps): ReactElement {
  const { resolved, setPreference } = useTheme();

  return (
    <div
      role="group"
      aria-label="Colour theme"
      className={[styles.group, className].filter(Boolean).join(" ")}
    >
      {OPTIONS.map((option) => {
        const active = resolved === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            aria-label={`${option.label} theme`}
            onClick={() => setPreference(option.value)}
            className={`${styles.option} ${active ? styles.active : ""}`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
