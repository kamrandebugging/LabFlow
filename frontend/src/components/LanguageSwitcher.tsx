import clsx from "clsx";
import { useTranslation } from "react-i18next";

import type { AppLanguage } from "../i18n";

export interface LanguageSwitcherProps {
  className?: string;
  /** Smaller control for dense headers. */
  compact?: boolean;
}

/**
 * The one shared English / اردو control.
 *
 * It reads and writes the same i18next instance as the Settings option, and
 * i18next persists the choice to localStorage (`labflow.lang`). There is no
 * second copy of the language state anywhere.
 */
export function LanguageSwitcher({
  className,
  compact = false,
}: LanguageSwitcherProps): JSX.Element {
  const { t, i18n } = useTranslation("common");
  const current: AppLanguage = i18n.resolvedLanguage?.startsWith("ur")
    ? "ur"
    : "en";

  const change = (lang: AppLanguage): void => {
    if (lang !== current) void i18n.changeLanguage(lang);
  };

  return (
    <div
      role="group"
      aria-label={t("language.switcher_aria")}
      className={clsx(
        "flex items-center bg-slate-100 p-0.5 rounded-full border border-slate-200/60",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => change("en")}
        aria-pressed={current === "en"}
        className={clsx(
          "rounded-full font-semibold transition-all",
          compact ? "px-2.5 py-1 text-[11px]" : "px-3 py-1 text-xs",
          current === "en"
            ? "bg-white text-[#005c55] shadow-sm"
            : "text-slate-500 hover:text-slate-900",
        )}
      >
        {t("language.english")}
      </button>
      <button
        type="button"
        onClick={() => change("ur")}
        aria-pressed={current === "ur"}
        lang="ur"
        dir="rtl"
        className={clsx(
          "rounded-full transition-colors font-urdu",
          compact ? "px-2.5 py-1 text-[11px]" : "px-3 py-1 text-xs",
          current === "ur"
            ? "bg-white text-[#005c55] font-semibold shadow-sm"
            : "text-slate-500 hover:text-slate-900",
        )}
      >
        {t("language.urdu")}
      </button>
    </div>
  );
}
