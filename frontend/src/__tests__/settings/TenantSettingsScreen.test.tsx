import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { TenantSettingsScreen } from "../../features/settings/TenantSettingsScreen";
import { settingsService } from "../../features/settings/settingsService";
import { useAuthStore } from "../../features/auth/authStore";

vi.mock("../../features/settings/settingsService", async () => {
  const actual = await vi.importActual(
    "../../features/settings/settingsService",
  );
  return {
    ...actual,
    settingsService: {
      getSettings: vi.fn(),
      updateSettings: vi.fn(),
    },
  };
});

const mockSettings = {
  brand_display_name: {
    value: "City Diagnostic Lab",
    default: "City Diagnostic Lab",
    type: "str",
    description: "Lab display name on patient reports",
  },
  brand_accent_colour: {
    value: "#005C55",
    default: "#005C55",
    type: "hex_colour",
    description: "Brand accent colour for report headers",
  },
  billing_hold_enabled: {
    value: false,
    default: false,
    type: "bool",
    description: "Block new invoices when tenant billing hold is enabled",
  },
  report_default_language: {
    value: "en",
    default: "en",
    type: "str",
    description: "Default language for patient notices (en/ur)",
  },
  report_link_validity_days: {
    value: 7,
    default: 7,
    type: "int",
    description: "Report link token validity in days (1-30)",
  },
  transfer_late_after_hours: {
    value: 24,
    default: 24,
    type: "int",
    description: "Hours before specimen transfer is flagged late",
  },
};

describe("Screen 34: TenantSettingsScreen (/settings/tenant)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setSession("mock-token", {
      id: "u1",
      email: "owner@labflow.app",
      name: "Ali Raza",
      role: "owner",
      branch_ids: ["b1"],
    });
    vi.mocked(settingsService.getSettings).mockResolvedValue(mockSettings);
  });

  it("renders all 6 registered settings and the Asia/Karachi timezone indicator", async () => {
    render(<TenantSettingsScreen />);

    expect(
      screen.getByRole("heading", { name: "Tenant Settings" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Asia\/Karachi \(PKT, UTC\+5\)/),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByLabelText("Brand Display Name")).toHaveValue(
        "City Diagnostic Lab",
      );
      expect(screen.getByLabelText("Default Patient Language")).toHaveValue(
        "en",
      );
      expect(screen.getByLabelText("Report Link Validity")).toHaveValue(7);
      expect(screen.getByLabelText("Transfer Late Threshold")).toHaveValue(24);
      expect(screen.getByLabelText("Tenant Billing Hold")).not.toBeChecked();
    });
  });

  it("submits stringified values via settingsService.updateSettings", async () => {
    vi.mocked(settingsService.updateSettings).mockResolvedValue({
      brand_display_name: { value: "City Reference Labs" },
    });

    render(<TenantSettingsScreen />);

    await waitFor(() => {
      expect(screen.getByLabelText("Brand Display Name")).toHaveValue(
        "City Diagnostic Lab",
      );
    });

    fireEvent.change(screen.getByLabelText("Brand Display Name"), {
      target: { value: "City Reference Labs" },
    });
    fireEvent.click(screen.getByLabelText("Tenant Billing Hold"));
    fireEvent.change(screen.getByLabelText("Default Patient Language"), {
      target: { value: "ur" },
    });
    fireEvent.change(screen.getByLabelText("Report Link Validity"), {
      target: { value: "14" },
    });

    fireEvent.click(screen.getByText("Save Settings"));

    await waitFor(() => {
      expect(settingsService.updateSettings).toHaveBeenCalledWith({
        brand_display_name: "City Reference Labs",
        brand_accent_colour: "#005C55",
        billing_hold_enabled: "true",
        report_default_language: "ur",
        report_link_validity_days: "14",
        transfer_late_after_hours: "24",
      });
      expect(
        screen.getByText("Tenant settings updated successfully."),
      ).toBeInTheDocument();
    });
  });

  it("validates report_link_validity_days bounds (1-30)", async () => {
    render(<TenantSettingsScreen />);

    await waitFor(() => {
      expect(screen.getByLabelText("Report Link Validity")).toHaveValue(7);
    });

    fireEvent.change(screen.getByLabelText("Report Link Validity"), {
      target: { value: "45" },
    });

    fireEvent.submit(screen.getByTestId("tenant-settings-form"));

    await waitFor(() => {
      expect(
        screen.getByText(
          "Report link validity days must be between 1 and 30 days.",
        ),
      ).toBeInTheDocument();
      expect(settingsService.updateSettings).not.toHaveBeenCalled();
    });
  });

  it("renders read-only mode for non-owner/manager roles", async () => {
    useAuthStore.getState().setSession("mock-token", {
      id: "u3",
      email: "reception@labflow.app",
      name: "Rehan Reception",
      role: "receptionist",
      branch_ids: ["b1"],
    });

    render(<TenantSettingsScreen />);

    await waitFor(() => {
      expect(screen.getByLabelText("Brand Display Name")).toBeDisabled();
      expect(screen.getByLabelText("Tenant Billing Hold")).toBeDisabled();
      expect(screen.getByLabelText("Default Patient Language")).toBeDisabled();
      expect(screen.queryByText("Save Settings")).not.toBeInTheDocument();
      expect(
        screen.getByText(/You are viewing tenant settings in read-only mode/i),
      ).toBeInTheDocument();
    });
  });
});
