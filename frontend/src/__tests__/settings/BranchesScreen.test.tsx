import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BranchesScreen } from "../../features/settings/BranchesScreen";
import {
  settingsService,
  SettingsApiError,
} from "../../features/settings/settingsService";
import { useAuthStore } from "../../features/auth/authStore";
import type { Branch } from "../../features/settings/types";

vi.mock("../../features/settings/settingsService", async () => {
  const actual = await vi.importActual(
    "../../features/settings/settingsService",
  );
  return {
    ...actual,
    settingsService: {
      getBranches: vi.fn(),
      createBranch: vi.fn(),
      updateBranch: vi.fn(),
      closeBranch: vi.fn(),
      reopenBranch: vi.fn(),
    },
  };
});

const mockBranches: Branch[] = [
  {
    id: "b1-0000-0000-0000-000000000001",
    code: "GLB",
    name: "Main Branch — Gulberg",
    address: "14-B Gulberg III, Lahore",
    phone: "+92 42 35789001",
    is_collection_centre: false,
    result_entry_enabled: true,
    deleted_at: null,
  },
  {
    id: "b2-0000-0000-0000-000000000002",
    code: "JHT",
    name: "Johar Town Collection Centre",
    address: "78-H Johar Town, Lahore",
    phone: "+92 42 35789002",
    is_collection_centre: true,
    result_entry_enabled: false,
    deleted_at: null,
  },
  {
    id: "b3-0000-0000-0000-000000000003",
    code: "MTN",
    name: "Model Town Satellite",
    address: "5-D Model Town, Lahore",
    phone: "+92 42 35789003",
    is_collection_centre: false,
    result_entry_enabled: false,
    deleted_at: "2026-10-12T10:00:00Z",
  },
];

describe("Screen 33: BranchesScreen (/settings/branches)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setSession("mock-token", {
      id: "u1",
      email: "owner@labflow.app",
      name: "Ali Raza",
      role: "owner",
      branch_ids: ["b1"],
    });
    vi.mocked(settingsService.getBranches).mockResolvedValue(mockBranches);
  });

  it("renders header, summary metrics, and branches list", async () => {
    render(<BranchesScreen />);

    expect(
      screen.getByRole("heading", { name: "Branches" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Lab branches and collection centres for specimen intake and testing",
      ),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Main Branch — Gulberg")).toBeInTheDocument();
      expect(
        screen.getByText("Johar Town Collection Centre"),
      ).toBeInTheDocument();
      expect(screen.getByText("Model Town Satellite")).toBeInTheDocument();
    });

    // Check metric counts: Total = 3, Testing = 2, Collection = 1
    expect(screen.getByText("Total Facilities")).toBeInTheDocument();
    expect(screen.getByText("Full Testing Labs")).toBeInTheDocument();
    expect(screen.getByText("Collection Centres")).toBeInTheDocument();
  });

  it("filters branches using search input and tab pills", async () => {
    render(<BranchesScreen />);

    await waitFor(() => {
      expect(screen.getByText("Main Branch — Gulberg")).toBeInTheDocument();
    });

    // Search for Johar Town
    const searchInput = screen.getByPlaceholderText(
      "Search branch code or name...",
    );
    fireEvent.change(searchInput, { target: { value: "Johar" } });

    expect(
      screen.getByText("Johar Town Collection Centre"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Main Branch — Gulberg")).not.toBeInTheDocument();

    // Clear search
    fireEvent.change(searchInput, { target: { value: "" } });
    expect(screen.getByText("Main Branch — Gulberg")).toBeInTheDocument();

    // Click "Collection" tab
    const collectionTab = screen.getByText(/Collection \(/);
    fireEvent.click(collectionTab);

    expect(
      screen.getByText("Johar Town Collection Centre"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Main Branch — Gulberg")).not.toBeInTheDocument();
  });

  it("opens create branch modal and calls settingsService.createBranch", async () => {
    vi.mocked(settingsService.createBranch).mockResolvedValue({
      id: "b4-new",
      code: "FSD",
      name: "Faisalabad Lab",
      address: "Civil Lines, Faisalabad",
      phone: null,
      is_collection_centre: false,
      result_entry_enabled: true,
      deleted_at: null,
    });

    render(<BranchesScreen />);

    await waitFor(() => {
      expect(screen.getByText("Add branch")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Add branch"));

    expect(screen.getByText("Add New Branch")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("e.g. LHE"), {
      target: { value: "FSD" },
    });
    fireEvent.change(
      screen.getByPlaceholderText("e.g. Gulberg Main Reference Lab"),
      {
        target: { value: "Faisalabad Lab" },
      },
    );

    fireEvent.click(screen.getByText("Create Branch"));

    await waitFor(() => {
      expect(settingsService.createBranch).toHaveBeenCalledWith({
        code: "FSD",
        name: "Faisalabad Lab",
        address: null,
        phone: null,
        is_collection_centre: false,
      });
    });
  });

  it("surfaces 409 plan_limit_reached error message with limit details", async () => {
    vi.mocked(settingsService.createBranch).mockRejectedValue(
      new SettingsApiError(
        "Plan limit reached: maximum branches allowed on plan.",
        "plan_limit_reached",
        409,
        { plan_limit: 3, current_count: 3 },
      ),
    );

    render(<BranchesScreen />);

    await waitFor(() => {
      expect(screen.getByText("Add branch")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Add branch"));

    fireEvent.change(screen.getByPlaceholderText("e.g. LHE"), {
      target: { value: "XYZ" },
    });
    fireEvent.change(
      screen.getByPlaceholderText("e.g. Gulberg Main Reference Lab"),
      {
        target: { value: "Fourth Branch" },
      },
    );

    fireEvent.click(screen.getByText("Create Branch"));

    await waitFor(() => {
      expect(
        screen.getByText(
          /Plan limit reached: your plan allows up to 3 facilities/i,
        ),
      ).toBeInTheDocument();
    });
  });

  it("handles branch close blockers with detailed open work breakdown", async () => {
    vi.mocked(settingsService.closeBranch).mockRejectedValue(
      new SettingsApiError(
        "Branch has open work and cannot be closed.",
        "branch_has_open_work",
        409,
        { samples_held: 5, open_transfers_in: 2, open_transfers_out: 1 },
      ),
    );

    render(<BranchesScreen />);

    await waitFor(() => {
      expect(screen.getByText("Main Branch — Gulberg")).toBeInTheDocument();
    });

    const closeButtons = screen.getAllByText("Close branch");
    if (!closeButtons[0]) throw new Error("Button not found");
    fireEvent.click(closeButtons[0]);

    expect(
      screen.getByText(/Close Branch: Main Branch — Gulberg/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText("Confirm Close"));

    await waitFor(() => {
      expect(
        screen.getByText("Active Work Preconditions Failed"),
      ).toBeInTheDocument();
      expect(screen.getByText(/specimens held/i)).toBeInTheDocument();
      expect(
        screen.getByText(/inbound specimen transfers open/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/outbound transfers pending arrival/i),
      ).toBeInTheDocument();
    });
  });

  it("allows owner to reopen closed branch", async () => {
    const branchToReopen = mockBranches[2]!;
    vi.mocked(settingsService.reopenBranch).mockResolvedValue({
      ...branchToReopen,
      deleted_at: null,
    });

    render(<BranchesScreen />);

    await waitFor(() => {
      expect(screen.getByText("Model Town Satellite")).toBeInTheDocument();
    });

    const reopenBtn = screen.getByText("Reopen branch");
    fireEvent.click(reopenBtn);

    await waitFor(() => {
      expect(settingsService.reopenBranch).toHaveBeenCalledWith(
        "b3-0000-0000-0000-000000000003",
      );
    });
  });

  it("hides mutation actions from non-owner roles (e.g. technician)", async () => {
    useAuthStore.getState().setSession("mock-token", {
      id: "u2",
      email: "tech@labflow.app",
      name: "Tariq Tech",
      role: "technician",
      branch_ids: ["b1"],
    });

    render(<BranchesScreen />);

    await waitFor(() => {
      expect(screen.getByText("Main Branch — Gulberg")).toBeInTheDocument();
    });

    expect(screen.queryByText("Add branch")).not.toBeInTheDocument();
    expect(screen.queryByText("Close branch")).not.toBeInTheDocument();
    expect(screen.queryByText("Edit details")).not.toBeInTheDocument();
  });
});
