/**
 * i18n configuration — LabFlow
 *
 * Supports English (en, LTR) and Urdu (ur, RTL) per Doc 07 §9.
 * Translation resources are placeholder stubs; real strings are added in LAB-38.
 *
 * IMPORTANT: Do NOT store access tokens in translation resources or anywhere
 * accessible to client-side storage (localStorage / sessionStorage / cookies).
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const resources = {
  en: {
    translation: {
      app_name: "LabFlow",
      welcome: "Welcome to LabFlow",
    },
  },
  ur: {
    translation: {
      app_name: "لیب فلو",
      welcome: "لیب فلو میں خوش آمدید",
    },
  },
} as const;

void i18n.use(initReactI18next).init({
  resources,
  lng: "en",
  fallbackLng: "en",
  interpolation: {
    // React already escapes values — disable i18next escaping to avoid double-escaping
    escapeValue: false,
  },
});

export default i18n;
