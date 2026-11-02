import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TestPanelsScreen } from "@/features/catalog/TestPanelsScreen";
import { catalogService } from "@/features/catalog/catalogService";
import type { DiagnosticPanel, DiagnosticTest } from "@/features/catalog/types";

describe("Screen 32: Diagnostic Panels (TestPanelsScreen)", () => {
  const mockTests: DiagnosticTest[] = [
    {
      id: "t-1",
      code: "ALT",
      name: "Alanine Transaminase",
      category: "Biochemistry",
      unit: "U/L",
      is_active: true,
      created_at: "2026-10-20T10:00:00Z",
      updated_at: "2026-10-20T10:00:00Z",
    },
    {
      id: "t-2",
      code: "AST",
      name: "Aspartate Aminotransferase",
      category: "Biochemistry",
      unit: "U/L",
      is_active: true,
      created_at: "2026-10-20T10:00:00Z",
      updated_at: "2026-10-20T10:00:00Z",
    },
    {
      id: "t-3",
      code: "ALP",
      name: "Alkaline Phosphatase",
      category: "Biochemistry",
      unit: "U/L",
      is_active: true,
      created_at: "2026-10-20T10:00:00Z",
      updated_at: "2026-10-20T10:00:00Z",
    },
    {
      id: "t-4",
      code: "BIL-T",
      name: "Bilirubin Total",
      category: "Biochemistry",
      unit: "mg/dL",
      is_active: true,
      created_at: "2026-10-20T10:00:00Z",
      updated_at: "2026-10-20T10:00:00Z",
    },
  ];

  const mockPanels: DiagnosticPanel[] = [
    {
      id: "panel-001",
      code: "LFT",
      name: "Liver Function Tests",
      is_active: true,
      test_ids: ["t-1", "t-2", "t-3", "t-4"],
      tests: [
        {
          id: "t-1",
          code: "ALT",
          name: "Alanine Transaminase",
          category: "Biochemistry",
          unit: "U/L",
          is_active: true,
        },
        {
          id: "t-2",
          code: "AST",
          name: "Aspartate Aminotransferase",
          category: "Biochemistry",
          unit: "U/L",
          is_active: true,
        },
        {
          id: "t-3",
          code: "ALP",
          name: "Alkaline Phosphatase",
          category: "Biochemistry",
          unit: "U/L",
          is_active: true,
        },
        {
          id: "t-4",
          code: "BIL-T",
          name: "Bilirubin Total",
          category: "Biochemistry",
          unit: "mg/dL",
          is_active: true,
        },
      ],
      price: "2200.00",
      created_at: "2026-10-20T10:00:00Z",
      updated_at: "2026-10-20T10:00:00Z",
    },
    {
      id: "panel-002",
      code: "LIPID",
      name: "Lipid Profile",
      is_active: false,
      test_ids: ["t-1"],
      tests: [
        {
          id: "t-1",
          code: "ALT",
          name: "Alanine Transaminase",
          category: "Biochemistry",
          unit: "U/L",
          is_active: true,
        },
      ],
      price: "1800.00",
      created_at: "2026-10-21T10:00:00Z",
      updated_at: "2026-10-21T10:00:00Z",
    },
  ];

  let mockService: typeof catalogService;
  const mockOnSwitchToTests = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockService = {
      ...catalogService,
      listPanels: vi.fn().mockResolvedValue(mockPanels),
      getPanel: vi.fn(),
      createPanel: vi.fn(),
      updatePanel: vi.fn(),
      listTests: vi.fn().mockResolvedValue(mockTests),
      getTest: vi.fn(),
      createTest: vi.fn(),
      updateTest: vi.fn(),
      getTestPrices: vi.fn(),
      setTestPrice: vi.fn(),
      getPanelPrices: vi.fn(),
      setPanelPrice: vi.fn(),
    };
  });

  it("renders panel header, KPI metrics, and panels table", async () => {
    render(
      <TestPanelsScreen
        service={mockService}
        onSwitchToTests={mockOnSwitchToTests}
      />,
    );

    expect(
      screen.getByText(/Diagnostic Panels \(Screen 32\)/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Create Panel/i }),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(mockService.listPanels).toHaveBeenCalled();
      expect(mockService.listTests).toHaveBeenCalledWith({ isActive: true });
    });

    expect(screen.getByText("Liver Function Tests")).toBeInTheDocument();
    expect(screen.getByText("LFT")).toBeInTheDocument();
    expect(screen.getByText("Lipid Profile")).toBeInTheDocument();
    expect(screen.getByText("PKR 2200.00")).toBeInTheDocument();
  });

  it("expands panel details to show all component tests", async () => {
    const user = userEvent.setup();
    render(
      <TestPanelsScreen
        service={mockService}
        onSwitchToTests={mockOnSwitchToTests}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Liver Function Tests")).toBeInTheDocument();
    });

    const expandBtn = screen.getByRole("button", { name: /\+1 more/i });
    await user.click(expandBtn);

    expect(
      screen.getByText(/All Bundled Tests in Liver Function Tests \(4\)/i),
    ).toBeInTheDocument();
  });

  it("validates empty selection and successfully creates panel when tests are chosen", async () => {
    const user = userEvent.setup();
    const createdPanel: DiagnosticPanel = {
      id: "panel-003",
      code: "RFT",
      name: "Renal Function Tests",
      is_active: true,
      test_ids: ["t-1", "t-2"],
      tests: [
        {
          id: "t-1",
          code: "ALT",
          name: "Alanine Transaminase",
          category: "Biochemistry",
          unit: "U/L",
          is_active: true,
        },
        {
          id: "t-2",
          code: "AST",
          name: "Aspartate Aminotransferase",
          category: "Biochemistry",
          unit: "U/L",
          is_active: true,
        },
      ],
      price: "1900.00",
      created_at: "2026-11-02T12:00:00Z",
      updated_at: "2026-11-02T12:00:00Z",
    };
    vi.mocked(mockService.createPanel).mockResolvedValue(createdPanel);

    render(
      <TestPanelsScreen
        service={mockService}
        onSwitchToTests={mockOnSwitchToTests}
      />,
    );

    const openModalBtn = screen.getByRole("button", { name: /Create Panel/i });
    await user.click(openModalBtn);

    expect(
      screen.getByRole("heading", { name: "Create Diagnostic Panel" }),
    ).toBeInTheDocument();

    const codeInput = screen.getByPlaceholderText(/e\.g\. CBC, LFT, CMP/i);
    const nameInput = screen.getByPlaceholderText(
      /e\.g\. Complete Blood Count/i,
    );
    const priceInput = screen.getByPlaceholderText(/e\.g\. 1500\.00/i);

    await user.type(codeInput, "RFT");
    await user.type(nameInput, "Renal Function Tests");
    await user.type(priceInput, "1900.00");

    // Click submit without selecting component tests -> should display validation message
    const submitBtn = screen.getByRole("button", {
      name: /Create Diagnostic Panel/i,
    });
    await user.click(submitBtn);

    expect(
      screen.getByText(
        /Please select at least one component test for this panel\./i,
      ),
    ).toBeInTheDocument();

    // Now select a component test from modal
    const modalHeading = screen.getByRole("heading", {
      name: "Create Diagnostic Panel",
    });
    const modal = modalHeading.closest(".fixed") as HTMLElement;
    const testOption = within(modal).getByText("Alanine Transaminase");
    await user.click(testOption);

    // Click submit again
    await user.click(submitBtn);

    await waitFor(() => {
      expect(mockService.createPanel).toHaveBeenCalledWith({
        code: "RFT",
        name: "Renal Function Tests",
        test_ids: ["t-1"],
        initial_price: "1900.00",
        is_active: true,
      });
    });
  });

  it("navigates to tests screen when switcher tab is clicked", async () => {
    const user = userEvent.setup();
    render(
      <TestPanelsScreen
        service={mockService}
        onSwitchToTests={mockOnSwitchToTests}
      />,
    );

    const testsTab = screen.getByRole("button", { name: /Individual Tests/i });
    await user.click(testsTab);

    expect(mockOnSwitchToTests).toHaveBeenCalled();
  });
});
