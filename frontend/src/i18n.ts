/**
 * i18n configuration — LabFlow
 *
 * Two locales: English (en, LTR) and Urdu (ur, RTL), per Doc 07 §9.
 * Ten namespaces, one JSON file per namespace per locale, bundled at build time.
 *
 * The staff UI language is a client-only preference stored in localStorage
 * under `labflow.lang`. It is never sent to the API and never stored on
 * StaffUser (Doc 07 §9.3).
 *
 * Platform routes (/platform/*) are English-only forever: this module forces
 * `lang="en"` / `dir="ltr"` there and never lets a tenant language flip them.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import enCommon from "./locales/en/common.json";
import enAuth from "./locales/en/auth.json";
import enPatients from "./locales/en/patients.json";
import enBilling from "./locales/en/billing.json";
import enSamples from "./locales/en/samples.json";
import enResults from "./locales/en/results.json";
import enReports from "./locales/en/reports.json";
import enPartners from "./locales/en/partners.json";
import enSettlements from "./locales/en/settlements.json";
import enSettings from "./locales/en/settings.json";

import urCommon from "./locales/ur/common.json";
import urAuth from "./locales/ur/auth.json";
import urPatients from "./locales/ur/patients.json";
import urBilling from "./locales/ur/billing.json";
import urSamples from "./locales/ur/samples.json";
import urResults from "./locales/ur/results.json";
import urReports from "./locales/ur/reports.json";
import urPartners from "./locales/ur/partners.json";
import urSettlements from "./locales/ur/settlements.json";
import urSettings from "./locales/ur/settings.json";

export const APP_LANGUAGES = ["en", "ur"] as const;
export type AppLanguage = (typeof APP_LANGUAGES)[number];

export const LANGUAGE_STORAGE_KEY = "labflow.lang";

export const NAMESPACES = [
  "common",
  "auth",
  "patients",
  "billing",
  "samples",
  "results",
  "reports",
  "partners",
  "settlements",
  "settings",
] as const;

const resources = {
  en: {
    common: enCommon,
    auth: enAuth,
    patients: enPatients,
    billing: enBilling,
    samples: enSamples,
    results: enResults,
    reports: enReports,
    partners: enPartners,
    settlements: enSettlements,
    settings: enSettings,
  },
  ur: {
    common: urCommon,
    auth: urAuth,
    patients: urPatients,
    billing: urBilling,
    samples: urSamples,
    results: urResults,
    reports: urReports,
    partners: urPartners,
    settlements: urSettlements,
    settings: urSettings,
  },
} as const;

/** True for the apex Platform console, which is English-only, LTR, forever. */
export function isPlatformRoute(
  pathname: string = typeof window === "undefined"
    ? ""
    : window.location.pathname,
): boolean {
  return pathname === "/platform" || pathname.startsWith("/platform/");
}

/** Read the persisted staff language. Absent/invalid storage means English. */
export function readStoredLanguage(): AppLanguage {
  if (typeof window === "undefined") return "en";
  try {
    return window.localStorage.getItem(LANGUAGE_STORAGE_KEY) === "ur"
      ? "ur"
      : "en";
  } catch {
    return "en";
  }
}

/** Persist the staff language. Best-effort: private mode may refuse. */
export function persistLanguage(lang: AppLanguage): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
  } catch {
    /* preference is optional; never break the app over storage */
  }
}

/** Browser preference → Urdu only when the browser asks for Urdu. */
export function browserLanguage(): AppLanguage {
  if (typeof navigator === "undefined") return "en";
  return navigator.language?.toLowerCase().startsWith("ur") ? "ur" : "en";
}

/**
 * Public patient report page default (Doc 07 §9.3):
 * explicit choice → tenant's report_default_language → browser → English.
 */
export function resolvePublicLanguage(
  tenantDefault?: string | null,
): AppLanguage {
  if (typeof window !== "undefined") {
    try {
      const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
      if (stored === "ur" || stored === "en") return stored;
    } catch {
      /* fall through to tenant/browser */
    }
  }
  if (tenantDefault === "ur" || tenantDefault === "en") return tenantDefault;
  return browserLanguage();
}

function normalizeLanguage(lang: string | undefined): AppLanguage {
  return lang?.toLowerCase().startsWith("ur") ? "ur" : "en";
}

/**
 * Set <html lang> and <html dir>. Platform routes are pinned to English/LTR.
 * Doc 07 §9.2: the switch is at <html> level only, never per component.
 */
export function applyDocumentLanguage(lang: string | undefined): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const effective = isPlatformRoute() ? "en" : normalizeLanguage(lang);
  root.lang = effective;
  root.dir = effective === "ur" ? "rtl" : "ltr";
}

void i18n.use(initReactI18next).init({
  resources,
  lng: isPlatformRoute() ? "en" : readStoredLanguage(),
  fallbackLng: "en",
  ns: [...NAMESPACES],
  defaultNS: "common",
  interpolation: {
    // React already escapes values — disable i18next escaping to avoid
    // double-escaping.
    escapeValue: false,
  },
  // Never render a raw key. A missing Urdu key falls back to English.
  returnNull: false,
});

i18n.on("languageChanged", (lng) => {
  const normalized = normalizeLanguage(lng);
  // The platform console never remembers or applies a tenant language.
  if (!isPlatformRoute()) persistLanguage(normalized);
  applyDocumentLanguage(normalized);
});

applyDocumentLanguage(i18n.language);

export default i18n;
