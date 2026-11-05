import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { RulesScreen } from "../../features/partners/RulesScreen";
import {
  PartnerApiError,
  partnersService,
} from "../../features/partners/partnersService";
import { settingsService } from "../../features/settings/settingsService";
import { useAuthStore } from "../../features/auth/authStore";
import type {
  ReferralPartner,
  RevenueShareRule,
} from "../../features/partners/types";

vi.mock("../../features/partners/partnersService", async () => {
  const actual = await vi.importActual(
    "../../features/partners/partnersService",
  );
  return {
    ...actual,
    partnersService: {
      getPartner: vi.fn(),
      getPartnerRules: vi.fn(),
      createPartnerRule: vi.fn(),
      updatePartnerRule: vi.fn(),
    },
  };
});

vi.mock("../../features/settings/settingsService", async () => {
  return {
    settingsService: {
      getBranches: vi.fn(),
    },
  };
});

const mockPartner: ReferralPartner = {
  id: "p-uuid-1234",
  name: "Shifa Medical Centre",
  organisation: "Hospital",
  phone: "+92 321 4567890",
  email: "shifa@example.com",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const mockBranches = [
  {
    id: "b-uuid-1",
    name: "Gulberg Main",
    code: "GLB-01",
    address: "Gulberg III",
    phone: "+92 42 35789012",
    is_collection_centre: false,
    result_entry_enabled: true,
    deleted_at: null,
  },
];

const mockRules: RevenueShareRule[] = [
  {
    id: "rule-1",
    referral_partner_id: "p-uuid-1234",
    branch_id: "b-uuid-1",
    test_category: "Haematology",
    percent: "12.50",
    effective_from: "2026-10-01",
    effective_to: null,
    created_at: "2026-10-01T00:00:00Z",
  },
  {
    id: "rule-2",
    referral_partner_id: "p-uuid-1234",
    branch_id: "b-uuid-1",
    test_category: null,
    percent: "10.00",
    effective_from: "2026-09-01",
    effective_to: null,
    created_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "rule-3",
    referral_partner_id: "p-uuid-1234",
    branch_id: null,
    test_category: "Biochemistry",
    percent: "8.00",
    effective_from: "2026-08-01",
    effective_to: null,
    created_at: "2026-08-01T00:00:00Z",
  },
  {
    id: "rule-4",
    referral_partner_id: "p-uuid-1234",
    branch_id: null,
    test_category: null,
    percent: "5.00",
    effective_from: "2026-01-01",
    effective_to: null,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "rule-5",
    referral_partner_id: "p-uuid-1234",
    branch_id: null,
    test_category: null,
    percent: "4.00",
    effective_from: "2025-01-01",
    effective_to: "2025-12-31",
    created_at: "2025-01-01T00:00:00Z",
  },
];

describe("RulesScreen (Screen 38)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: {
        id: "u-owner",
        email: "owner@labflow.pk",
        role: "owner",
        name: "Lab Owner",
        branch_ids: ["b-uuid-1"],
      },
      accessToken: "mock-token",
    });

    vi.mocked(partnersService.getPartner).mockResolvedValue(mockPartner);
    vi.mocked(partnersService.getPartnerRules).mockResolvedValue(mockRules);
    vi.mocked(settingsService.getBranches).mockResolvedValue(mockBranches);
  });

  const renderComponent = () =>
    render(
      <MemoryRouter initialEntries={["/partners/p-uuid-1234/rules"]}>
        <Routes>
          <Route path="/partners/:id/rules" element={<RulesScreen />} />
        </Routes>
      </MemoryRouter>,
    );

  it("renders partner context banner and groups rules by specificity", async () => {
    renderComponent();

    expect(
      await screen.findByRole("heading", { name: "Shifa Medical Centre" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Active Partner")).toBeInTheDocument();
    expect(screen.getByText("Total rules active: 4")).toBeInTheDocument();

    // Specificity groups check
    expect(
      screen.getAllByText("Branch + category").length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Branch only")).toBeInTheDocument();
    expect(screen.getByText("Category only")).toBeInTheDocument();
    expect(screen.getAllByText("Partner-wide").length).toBeGreaterThanOrEqual(
      1,
    );

    // Rule percentages
    expect(screen.getByText("12.50%")).toBeInTheDocument();
    expect(screen.getByText("10.00%")).toBeInTheDocument();
    expect(screen.getByText("8.00%")).toBeInTheDocument();
    expect(screen.getByText("5.00%")).toBeInTheDocument();
    expect(screen.getByText("4.00%")).toBeInTheDocument();

    // Closed status check
    expect(screen.getByText("Closed")).toBeInTheDocument();
  });

  it("opens create modal and successfully creates a new rule", async () => {
    vi.mocked(partnersService.createPartnerRule).mockResolvedValue({
      id: "rule-new",
      referral_partner_id: "p-uuid-1234",
      branch_id: null,
      test_category: "Molecular",
      percent: "15.00",
      effective_from: "2026-11-01",
      effective_to: null,
      created_at: "2026-11-01T00:00:00Z",
    });

    renderComponent();

    await screen.findByRole("heading", { name: "Shifa Medical Centre" });

    const newRuleBtn = screen.getByRole("button", { name: /new rule/i });
    fireEvent.click(newRuleBtn);

    expect(screen.getByText("New revenue share rule")).toBeInTheDocument();

    // Submit rule
    const saveBtn = screen.getByRole("button", { name: /save rule/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(partnersService.createPartnerRule).toHaveBeenCalledWith(
        "p-uuid-1234",
        expect.objectContaining({
          effective_from: expect.any(String),
          percent: "10.00",
        }),
      );
    });
  });

  it("surfaces 422 rule_overlap collision error", async () => {
    vi.mocked(partnersService.createPartnerRule).mockRejectedValue(
      new PartnerApiError("Rule overlap collision", "rule_overlap", 422),
    );

    renderComponent();

    await screen.findByRole("heading", { name: "Shifa Medical Centre" });
    fireEvent.click(screen.getByRole("button", { name: /new rule/i }));

    const saveBtn = screen.getByRole("button", { name: /save rule/i });
    fireEvent.click(saveBtn);

    expect(
      await screen.findByText(/Rule overlap collision: A rule already exists/i),
    ).toBeInTheDocument();
  });

  it("opens edit modal and updates rule via close-old + insert-new semantics", async () => {
    vi.mocked(partnersService.updatePartnerRule).mockResolvedValue({
      id: "rule-updated",
      referral_partner_id: "p-uuid-1234",
      branch_id: "b-uuid-1",
      test_category: "Haematology",
      percent: "14.00",
      effective_from: "2026-11-01",
      effective_to: null,
      created_at: "2026-11-01T00:00:00Z",
    });

    renderComponent();

    await screen.findByRole("heading", { name: "Shifa Medical Centre" });

    // Click edit on active rule 1
    const editBtn = screen.getByLabelText("Edit rule rule-1");
    fireEvent.click(editBtn);

    expect(screen.getByText("Update revenue share rule")).toBeInTheDocument();
    expect(
      screen.getByText(/Applies close-old \+ insert-new rule semantics/i),
    ).toBeInTheDocument();

    const updateBtn = screen.getByRole("button", { name: /update rule/i });
    fireEvent.click(updateBtn);

    await waitFor(() => {
      expect(partnersService.updatePartnerRule).toHaveBeenCalledWith(
        "rule-1",
        expect.objectContaining({
          percent: "12.50",
        }),
      );
    });
  });

  it("renders honest empty state when no rules exist", async () => {
    vi.mocked(partnersService.getPartnerRules).mockResolvedValue([]);

    renderComponent();

    expect(
      await screen.findByText(
        "No revenue share rules configured for this partner yet.",
      ),
    ).toBeInTheDocument();
  });
});
