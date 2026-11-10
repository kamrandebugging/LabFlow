import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { StaffScreen } from "../../features/staff/StaffScreen";
import { staffService } from "../../features/staff/staffService";
import { useAuthStore } from "../../features/auth/authStore";
import type {
  StaffListResponse,
  StaffRow,
  StaffTempPasswordResponse,
} from "../../features/staff/types";

vi.mock("../../features/staff/staffService", () => ({
  staffService: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    deactivate: vi.fn(),
    reactivate: vi.fn(),
    resetPassword: vi.fn(),
  },
}));

const branch = { id: "b1", code: "HQ1", name: "Main Branch" };

const owner: StaffRow = {
  id: "owner-1",
  display_name: "Ayesha Owner",
  email: "owner@lab.pk",
  role: "owner",
  role_label: "Lab Owner",
  is_owner: true,
  branch: null,
  status: "active",
  is_active: true,
  totp_status: "enabled",
  totp_enabled: true,
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
};

const technician: StaffRow = {
  id: "staff-1",
  display_name: "Usman Tariq",
  email: "usman@lab.pk",
  role: "technician",
  role_label: "Lab Technician",
  is_owner: false,
  branch,
  status: "active",
  is_active: true,
  totp_status: "disabled",
  totp_enabled: false,
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
};

const listPayload: StaffListResponse = {
  owner,
  results: [technician],
  next_cursor: null,
  staff_count: 2,
  plan_staff_limit: 5,
  enabled_roles: [
    { role: "reception", label: "Receptionist / Collection Staff" },
    { role: "technician", label: "Lab Technician" },
  ],
  branches: [branch],
};

const createdPayload: StaffTempPasswordResponse = {
  staff: { ...technician, id: "staff-2", display_name: "Sana Reception" },
  temp_password: "Tmp-Pass-1234!",
  password_is_temporary: true,
};

describe("Settings → Staff", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setSession("token", {
      id: "owner-1",
      email: "owner@lab.pk",
      name: "Ayesha Owner",
      role: "owner",
      branch_ids: ["b1"],
    });
    vi.mocked(staffService.list).mockResolvedValue(listPayload);
  });

  it("lists real staff, shows the Owner row and the seat count", async () => {
    render(<StaffScreen />);

    expect(
      await screen.findByRole("heading", { name: "Staff accounts" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Usman Tariq")).toBeInTheDocument();
    expect(screen.getByText("Ayesha Owner")).toBeInTheDocument();
    expect(
      screen.getByText(/2 of 5 plan seats used \(Owner counts as a seat\)/),
    ).toBeInTheDocument();
    expect(screen.getByText("Lab Technician")).toBeInTheDocument();
  });

  it("renders an honest empty state when the Owner is alone", async () => {
    vi.mocked(staffService.list).mockResolvedValue({
      ...listPayload,
      results: [],
      staff_count: 1,
    });
    render(<StaffScreen />);

    expect(
      await screen.findByText("No staff accounts yet"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/You are running the lab alone/),
    ).toBeInTheDocument();
  });

  it("creates a staff account and shows the temporary password once", async () => {
    vi.mocked(staffService.create).mockResolvedValue(createdPayload);
    render(<StaffScreen />);

    fireEvent.click(await screen.findByRole("button", { name: /Add staff/i }));
    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "Sana Reception" },
    });
    fireEvent.change(screen.getByLabelText("Work email"), {
      target: { value: "sana@lab.pk" },
    });
    fireEvent.change(screen.getByLabelText("Role"), {
      target: { value: "reception" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Create staff account/i }),
    );

    await waitFor(() => expect(staffService.create).toHaveBeenCalledTimes(1));
    expect(staffService.create).toHaveBeenCalledWith({
      display_name: "Sana Reception",
      email: "sana@lab.pk",
      role: "reception",
      branch_id: "b1",
    });
    expect(
      await screen.findByText("Temporary password — shown once"),
    ).toBeInTheDocument();
    expect(screen.getByText("Tmp-Pass-1234!")).toBeInTheDocument();
  });

  it("shows the backend's role_not_enabled error instead of inventing success", async () => {
    vi.mocked(staffService.create).mockRejectedValue(
      new Error("The Pathologist role is not enabled for this lab."),
    );
    render(<StaffScreen />);

    fireEvent.click(await screen.findByRole("button", { name: /Add staff/i }));
    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "Dr Path" },
    });
    fireEvent.change(screen.getByLabelText("Work email"), {
      target: { value: "path@lab.pk" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Create staff account/i }),
    );

    expect(
      await screen.findByText(
        "The Pathologist role is not enabled for this lab.",
      ),
    ).toBeInTheDocument();
  });
});
