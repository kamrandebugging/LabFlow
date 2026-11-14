import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { StaffLoginWrapper } from "../../App";
import { useAuthStore } from "../../features/auth/authStore";
import { defaultAuthService } from "../../features/auth/authService";
import type { AuthUser } from "../../features/auth/types";

vi.mock("../../features/auth/authService", () => ({
  defaultAuthService: {
    login: vi.fn(),
    verifyTotp: vi.fn(),
    logout: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../../features/auth/tenantContext", () => ({
  getSubdomainTenant: () => null,
  fetchTenantContext: () => Promise.resolve(null),
}));

const Zahra: AuthUser = {
  id: "usr_zahra",
  name: "Zahra Khan",
  email: "zahra@lahore21.localhost",
  role: "reception",
  branch_ids: ["br_lahore_21"],
};

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<StaffLoginWrapper />} />
        <Route path="/" element={<div>Dashboard home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Staff login with an existing session", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().clear();
  });

  it("shows the active session banner with name, role and both actions", () => {
    useAuthStore.getState().setSession("staff-token", Zahra);

    renderLogin();

    expect(
      screen.getByText("You're logged in as Zahra Khan (Receptionist)"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Continue" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Log in as someone else" }),
    ).toBeInTheDocument();
    // The normal sign-in form must not compete with the active session.
    expect(
      screen.queryByRole("button", { name: /^Sign in$/i }),
    ).not.toBeInTheDocument();
  });

  it("Continue goes to the role dashboard", async () => {
    const user = userEvent.setup();
    useAuthStore.getState().setSession("staff-token", Zahra);

    renderLogin();
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Dashboard home")).toBeInTheDocument();
  });

  it("Log in as someone else logs out and shows the normal login form", async () => {
    const user = userEvent.setup();
    useAuthStore.getState().setSession("staff-token", Zahra);

    renderLogin();
    await user.click(
      screen.getByRole("button", { name: "Log in as someone else" }),
    );

    await waitFor(() => {
      expect(defaultAuthService.logout).toHaveBeenCalledTimes(1);
      expect(useAuthStore.getState().user).toBeNull();
      expect(useAuthStore.getState().accessToken).toBeNull();
    });
    expect(
      screen.getByRole("button", { name: /^Sign in$/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/You're logged in as/i)).not.toBeInTheDocument();
  });

  it("keeps the logged-out login flow unchanged", () => {
    renderLogin();

    expect(
      screen.getByRole("button", { name: /^Sign in$/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/You're logged in as/i)).not.toBeInTheDocument();
  });
});
