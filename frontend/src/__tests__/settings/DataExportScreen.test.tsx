import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DataExportScreen } from "../../features/settings/DataExportScreen";
import { settingsService } from "../../features/settings/settingsService";
import { useAuthStore } from "../../features/auth/authStore";

vi.mock("../../features/settings/settingsService", async () => {
  const actual = await vi.importActual(
    "../../features/settings/settingsService",
  );
  return {
    ...actual,
    settingsService: {
      requestExport: vi.fn(),
      getExportStatus: vi.fn(),
    },
  };
});

describe("Screen 35: DataExportScreen (/settings/exports)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setSession("mock-token", {
      id: "u1",
      email: "owner@labflow.app",
      name: "Ali Raza",
      role: "owner",
      branch_ids: ["b1"],
    });
  });

  it("renders header and explicit secrets exclusion guarantee", () => {
    render(<DataExportScreen />);

    expect(
      screen.getByRole("heading", { name: "Data Export" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Security & Confidentiality Guarantee"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Sensitive authentication secrets are NEVER exported/i),
    ).toBeInTheDocument();
  });

  it("requests export, polls status, and displays download link when ready", async () => {
    vi.mocked(settingsService.requestExport).mockResolvedValue({
      export_id: "exp-12345",
      status: "pending",
    });

    vi.mocked(settingsService.getExportStatus).mockResolvedValue({
      id: "exp-12345",
      status: "complete",
      requested_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
      download_url: "/api/v1/exports/exp-12345/download?sig=mocked_signature",
      error_message: null,
    });

    render(<DataExportScreen />);

    const requestBtn = screen.getByRole("button", { name: /request export/i });
    fireEvent.click(requestBtn);

    await waitFor(() => {
      expect(settingsService.requestExport).toHaveBeenCalled();
      expect(screen.getByText("Current Export Status")).toBeInTheDocument();
    });

    await waitFor(
      () => {
        expect(
          screen.getByText("Download Export Bundle (.zip)"),
        ).toBeInTheDocument();
      },
      { timeout: 3500 },
    );
  });

  it("restricts requesting export to Owner only", () => {
    useAuthStore.getState().setSession("mock-token", {
      id: "u2",
      email: "tech@labflow.app",
      name: "Tariq Tech",
      role: "technician",
      branch_ids: ["b1"],
    });

    render(<DataExportScreen />);

    expect(
      screen.queryByRole("button", { name: "Request export" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        /Only the Lab Owner has permission to request and download full tenant data exports/i,
      ),
    ).toBeInTheDocument();
  });
});
