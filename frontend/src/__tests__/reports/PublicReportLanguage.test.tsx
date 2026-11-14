import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { PatientReportAccessScreen } from "../../features/reports/PatientReportAccessScreen";
import { reportsService } from "../../features/reports/reportsService";
import i18n from "../../i18n";

vi.mock("../../features/reports/reportsService", () => ({
  reportsService: {
    checkPublicReportAccess: vi.fn(),
  },
}));

describe("public patient report page language", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.history.pushState({}, "", "/");
    void i18n.changeLanguage("en");
    vi.mocked(reportsService.checkPublicReportAccess).mockResolvedValue({
      status: 200,
    });
  });

  it("offers an English / اردو toggle and flips the public page to RTL", async () => {
    render(
      <MemoryRouter initialEntries={["/report-access/token-123"]}>
        <Routes>
          <Route
            path="/report-access/:token"
            element={<PatientReportAccessScreen />}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("link", { name: /download official pdf/i }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "اردو" }));

    await waitFor(() => {
      expect(document.documentElement.dir).toBe("rtl");
      expect(window.localStorage.getItem("labflow.lang")).toBe("ur");
      expect(
        screen.getByRole("heading", { name: "سرکاری کلینیکل رپورٹ" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /سرکاری PDF ڈاؤن لوڈ کریں/ }),
      ).toBeInTheDocument();
    });
  });
});
