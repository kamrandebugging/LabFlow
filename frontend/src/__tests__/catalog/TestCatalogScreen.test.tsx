import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TestCatalogScreen } from "@/features/catalog/TestCatalogScreen";
import { catalogService } from "@/features/catalog/catalogService";
import type { DiagnosticTest } from "@/features/catalog/types";

describe("Screen 31: Diagnostic Test Catalog (TestCatalogScreen)", () => {
  const mockTests: DiagnosticTest[] = [
    {
      id: "test-001",
      code: "CBC-01",
      name: "Complete Blood Count",
      category: "Hematology",
      unit: "g/dL",
      is_active: true,
      price: "1200.00",
      created_at: "2026-10-20T10:00:00Z",
      updated_at: "2026-10-20T10:00:00Z",
    },
    {
      id: "test-002",
      code: "GLU-F",
      name: "Fasting Blood Glucose",
      category: "Biochemistry",
      unit: "mg/dL",
      is_active: true,
      price: "450.00",
      created_at: "2026-10-21T10:00:00Z",
      updated_at: "2026-10-21T10:00:00Z",
    },
    {
      id: "test-003",
      code: "COVID-PCR",
      name: "SARS-CoV-2 RT-PCR",
      category: "Molecular",
      unit: null,
      is_active: false,
      price: "3500.00",
      created_at: "2026-10-22T10:00:00Z",
      updated_at: "2026-10-22T10:00:00Z",
    },
  ];

  let mockService: typeof catalogService;
  const mockOnSwitchToPanels = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockService = {
      ...catalogService,
      listTests: vi.fn().mockResolvedValue(mockTests),
      getTest: vi.fn(),
      createTest: vi.fn(),
      updateTest: vi.fn(),
      getTestPrices: vi.fn(),
      setTestPrice: vi.fn(),
      listPanels: vi.fn(),
      getPanel: vi.fn(),
      createPanel: vi.fn(),
      updatePanel: vi.fn(),
      getPanelPrices: vi.fn(),
      setPanelPrice: vi.fn(),
    };
  });

  it("renders screen header, categories, and test list properly", async () => {
    render(
      <TestCatalogScreen
        service={mockService}
        onSwitchToPanels={mockOnSwitchToPanels}
      />,
    );

    expect(screen.getByText(/Diagnostic Test Catalog/i)).toBeInTheDocument();
    expect(screen.getByText("Add New Test")).toBeInTheDocument();

    await waitFor(() => {
      expect(mockService.listTests).toHaveBeenCalled();
    });

    expect(screen.getByText("Complete Blood Count")).toBeInTheDocument();
    expect(screen.getByText("CBC-01")).toBeInTheDocument();
    expect(screen.getByText("Fasting Blood Glucose")).toBeInTheDocument();
    expect(screen.getByText("SARS-CoV-2 RT-PCR")).toBeInTheDocument();
  });

  it("filters tests by category pill click", async () => {
    const user = userEvent.setup();
    render(
      <TestCatalogScreen
        service={mockService}
        onSwitchToPanels={mockOnSwitchToPanels}
      />,
    );

    await waitFor(() => {
      expect(mockService.listTests).toHaveBeenCalledWith({
        q: undefined,
        category: undefined,
      });
    });

    const bioPill = screen.getByRole("button", { name: "Biochemistry" });
    await user.click(bioPill);

    await waitFor(() => {
      expect(mockService.listTests).toHaveBeenCalledWith({
        q: undefined,
        category: "Biochemistry",
      });
    });
  });

  it("opens modal and creates a new test successfully", async () => {
    const user = userEvent.setup();
    const createdTest: DiagnosticTest = {
      id: "test-004",
      code: "LFT-ALT",
      name: "Alanine Aminotransferase",
      category: "Biochemistry",
      unit: "U/L",
      is_active: true,
      price: "600.00",
      created_at: "2026-11-02T12:00:00Z",
      updated_at: "2026-11-02T12:00:00Z",
    };
    vi.mocked(mockService.createTest).mockResolvedValue(createdTest);

    render(
      <TestCatalogScreen
        service={mockService}
        onSwitchToPanels={mockOnSwitchToPanels}
      />,
    );

    const addBtn = screen.getByRole("button", { name: /Add New Test/i });
    await user.click(addBtn);

    expect(
      screen.getByRole("heading", { name: "Define Diagnostic Test" }),
    ).toBeInTheDocument();

    const codeInput = screen.getByPlaceholderText(/e\.g\. CBC/i);
    const nameInput = screen.getByPlaceholderText(
      /e\.g\. Complete Blood Count/i,
    );
    const unitInput = screen.getByPlaceholderText(/e\.g\. mg\/dL/i);
    const priceInput = screen.getByPlaceholderText(/e\.g\. 1200\.00/i);

    await user.type(codeInput, "LFT-ALT");
    await user.type(nameInput, "Alanine Aminotransferase");
    await user.type(unitInput, "U/L");
    await user.type(priceInput, "600.00");

    const submitBtn = screen.getByRole("button", { name: /Save Test/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(mockService.createTest).toHaveBeenCalledWith({
        code: "LFT-ALT",
        name: "Alanine Aminotransferase",
        category: "Hematology", // default initial category
        unit: "U/L",
        initial_price: "600.00",
      });
    });
  });

  it("navigates to panels screen when panels switcher tab is clicked", async () => {
    const user = userEvent.setup();
    render(
      <TestCatalogScreen
        service={mockService}
        onSwitchToPanels={mockOnSwitchToPanels}
      />,
    );

    const panelsTab = screen.getByRole("button", { name: /Test Panels/i });
    await user.click(panelsTab);

    expect(mockOnSwitchToPanels).toHaveBeenCalled();
  });
});
