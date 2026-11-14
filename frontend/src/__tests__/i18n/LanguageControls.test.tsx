import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useTranslation } from "react-i18next";

import i18n, {
  LANGUAGE_STORAGE_KEY,
  applyDocumentLanguage,
  readStoredLanguage,
} from "../../i18n";
import { LanguageSwitcher } from "../../components/LanguageSwitcher";
import { TenantSettingsScreen } from "../../features/settings/TenantSettingsScreen";
import { useAuthStore } from "../../features/auth/authStore";

vi.mock("../../features/settings/settingsService", async () => {
  const actual = await vi.importActual(
    "../../features/settings/settingsService",
  );
  return {
    ...actual,
    settingsService: {
      getSettings: vi.fn().mockResolvedValue({
        brand_display_name: { value: "City Diagnostic Lab" },
        brand_accent_colour: { value: "#005C55" },
        billing_hold_enabled: { value: false },
        report_default_language: { value: "en" },
        report_link_validity_days: { value: 7 },
        transfer_late_after_hours: { value: 24 },
      }),
      updateSettings: vi.fn(),
    },
  };
});

function Probe(): JSX.Element {
  const { t } = useTranslation("common");
  return <span data-testid="probe">{t("nav.patients")}</span>;
}

describe("language preference (Doc 07 §9)", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.pushState({}, "", "/");
    void i18n.changeLanguage("en");
    useAuthStore.getState().setSession("mock-token", {
      id: "u1",
      email: "owner@labflow.app",
      name: "Ali Raza",
      role: "owner",
      branch_ids: ["b1"],
    });
  });

  afterEach(() => {
    window.localStorage.clear();
    window.history.pushState({}, "", "/");
    applyDocumentLanguage("en");
  });

  it("defaults to English when localStorage is empty", () => {
    expect(readStoredLanguage()).toBe("en");
    render(<Probe />);
    expect(screen.getByTestId("probe")).toHaveTextContent("Patients");
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
  });

  it("shared switcher translates text, flips dir, and persists labflow.lang", async () => {
    render(
      <>
        <LanguageSwitcher />
        <Probe />
      </>,
    );

    fireEvent.click(screen.getByRole("button", { name: "اردو" }));

    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent("مریض");
      expect(document.documentElement.lang).toBe("ur");
      expect(document.documentElement.dir).toBe("rtl");
      expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("ur");
    });

    fireEvent.click(screen.getByRole("button", { name: "English" }));
    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent("Patients");
      expect(document.documentElement.dir).toBe("ltr");
      expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("en");
    });
  });

  it("Settings option switches the whole app and stays in sync with the header switcher", async () => {
    render(
      <>
        <LanguageSwitcher />
        <TenantSettingsScreen />
      </>,
    );

    const select = await screen.findByLabelText("Select Language");
    expect(select).toHaveValue("en");

    fireEvent.change(select, { target: { value: "ur" } });

    await waitFor(() => {
      expect(document.documentElement.lang).toBe("ur");
      expect(document.documentElement.dir).toBe("rtl");
      expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("ur");
      expect(screen.getByRole("button", { name: "اردو" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect(screen.getByLabelText("زبان منتخب کریں")).toHaveValue("ur");
    });

    // The header control writes the same key; the Settings select must follow.
    fireEvent.click(screen.getByRole("button", { name: "English" }));
    await waitFor(() => {
      expect(screen.getByLabelText("Select Language")).toHaveValue("en");
      expect(document.documentElement.dir).toBe("ltr");
      expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("en");
    });
  });

  it("never flips the Platform console to RTL or Urdu", async () => {
    window.history.pushState({}, "", "/platform/overview");
    void i18n.changeLanguage("ur");

    await waitFor(() => {
      expect(document.documentElement.lang).toBe("en");
      expect(document.documentElement.dir).toBe("ltr");
    });

    // Even a direct apply with "ur" is pinned to English/LTR on platform.
    applyDocumentLanguage("ur");
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
  });
});
