import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckSquare,
  ChevronDown,
  ChevronUp,
  Layers,
  Plus,
  RefreshCw,
  Search,
  Square,
  Tag,
  X,
} from "lucide-react";
import { catalogService } from "./catalogService";
import type {
  DiagnosticPanel,
  DiagnosticTest,
  PanelCreateInput,
} from "./types";

interface TestPanelsScreenProps {
  onSwitchToTests?: () => void;
  service?: typeof catalogService;
}

export function TestPanelsScreen({
  onSwitchToTests,
  service = catalogService,
}: TestPanelsScreenProps): JSX.Element {
  const [panels, setPanels] = useState<DiagnosticPanel[]>([]);
  const [availableTests, setAvailableTests] = useState<DiagnosticTest[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<
    "ALL" | "ACTIVE" | "INACTIVE"
  >("ALL");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedPanelId, setExpandedPanelId] = useState<string | null>(null);

  // Create Panel Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [selectedTestIds, setSelectedTestIds] = useState<string[]>([]);
  const [newPrice, setNewPrice] = useState("");
  const [testSearchInModal, setTestSearchInModal] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  const fetchPanelsAndTests = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [panelsData, testsData] = await Promise.all([
        service.listPanels({ q: searchQuery || undefined }),
        service.listTests({ isActive: true }),
      ]);
      setPanels(panelsData);
      setAvailableTests(testsData);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to load diagnostic panels",
      );
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, service]);

  useEffect(() => {
    fetchPanelsAndTests();
  }, [fetchPanelsAndTests]);

  const filteredPanels = useMemo(() => {
    return panels.filter((panel) => {
      if (statusFilter === "ACTIVE") return panel.is_active;
      if (statusFilter === "INACTIVE") return !panel.is_active;
      return true;
    });
  }, [panels, statusFilter]);

  const stats = useMemo(() => {
    const total = panels.length;
    const active = panels.filter((p) => p.is_active).length;
    const totalComponents = panels.reduce(
      (sum, p) => sum + (p.test_ids?.length || 0),
      0,
    );
    const avgComponents =
      total > 0 ? (totalComponents / total).toFixed(1) : "0";
    return { total, active, totalComponents, avgComponents };
  }, [panels]);

  const toggleTestSelection = (testId: string) => {
    setSelectedTestIds((prev) =>
      prev.includes(testId)
        ? prev.filter((id) => id !== testId)
        : [...prev, testId],
    );
  };

  const handleTogglePanelStatus = async (panel: DiagnosticPanel) => {
    try {
      const updated = await service.updatePanel(panel.id, {
        is_active: !panel.is_active,
      });
      setPanels((prev) =>
        prev.map((p) =>
          p.id === panel.id ? { ...p, is_active: updated.is_active } : p,
        ),
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to update panel status",
      );
    }
  };

  const handleCreatePanel = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalError(null);

    const trimmedCode = newCode.trim().toUpperCase();
    const trimmedName = newName.trim();

    if (!trimmedCode) {
      setModalError("Panel code is required.");
      return;
    }
    if (!trimmedName) {
      setModalError("Panel name is required.");
      return;
    }
    if (selectedTestIds.length === 0) {
      setModalError(
        "Please select at least one component test for this panel.",
      );
      return;
    }

    setIsSaving(true);
    try {
      const payload: PanelCreateInput = {
        code: trimmedCode,
        name: trimmedName,
        test_ids: selectedTestIds,
        initial_price: newPrice.trim() || undefined,
        is_active: true,
      };

      await service.createPanel(payload);
      setIsModalOpen(false);
      setNewCode("");
      setNewName("");
      setSelectedTestIds([]);
      setNewPrice("");
      setTestSearchInModal("");
      fetchPanelsAndTests();
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Failed to create panel.";
      if (msg.includes("empty_panel")) {
        setModalError(
          "A diagnostic panel must bundle at least one active test.",
        );
      } else if (msg.includes("inactive_component")) {
        setModalError(
          "Selected tests contain inactive components. Please choose active tests.",
        );
      } else {
        setModalError(msg);
      }
    } finally {
      setIsSaving(false);
    }
  };

  const modalFilteredTests = useMemo(() => {
    const q = testSearchInModal.toLowerCase().trim();
    if (!q) return availableTests;
    return availableTests.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.code.toLowerCase().includes(q) ||
        (t.category && t.category.toLowerCase().includes(q)),
    );
  }, [availableTests, testSearchInModal]);

  return (
    <div className="flex flex-col w-full max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* 1. Header & Navigation Switcher */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
              <Layers className="w-6 h-6" />
            </span>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                Diagnostic Panels (Screen 32)
              </h1>
              <p className="text-sm text-slate-500">
                Configure multi-test diagnostic panels, specimen routing, and
                bundled package rates.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Switcher Tab Pills */}
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1">
            <button
              type="button"
              onClick={onSwitchToTests}
              className="px-3.5 py-1.5 text-xs font-semibold rounded-md text-slate-600 hover:text-slate-900 transition-colors"
            >
              Individual Tests (31)
            </button>
            <button
              type="button"
              className="px-3.5 py-1.5 text-xs font-semibold rounded-md bg-white text-indigo-700 shadow-sm"
            >
              Test Panels (32)
            </button>
          </div>

          <button
            type="button"
            onClick={() => setIsModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm transition-all"
          >
            <Plus className="w-4 h-4" />
            Create Panel
          </button>
        </div>
      </div>

      {/* 2. Metric KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
            Total Panels
          </p>
          <p className="text-2xl font-bold text-slate-800 mt-1">
            {stats.total}
          </p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
            Active Panels
          </p>
          <p className="text-2xl font-bold text-emerald-600 mt-1">
            {stats.active}
          </p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
            Total Bundled Tests
          </p>
          <p className="text-2xl font-bold text-indigo-600 mt-1">
            {stats.totalComponents}
          </p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
            Avg Tests / Panel
          </p>
          <p className="text-2xl font-bold text-slate-800 mt-1">
            {stats.avgComponents}
          </p>
        </div>
      </div>

      {/* 3. Search and Status Filters */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="relative w-full md:w-96">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search panels by code, name, or keyword..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition"
          />
        </div>

        <div className="flex items-center gap-3 w-full md:w-auto justify-end">
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1 text-xs font-medium text-slate-600">
            {(["ALL", "ACTIVE", "INACTIVE"] as const).map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => setStatusFilter(filter)}
                className={`px-3 py-1 rounded-md transition-colors ${
                  statusFilter === filter
                    ? "bg-white text-indigo-600 shadow-xs font-semibold"
                    : "hover:text-slate-900"
                }`}
              >
                {filter.charAt(0) + filter.slice(1).toLowerCase()}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={fetchPanelsAndTests}
            disabled={isLoading}
            className="p-2 border border-slate-300 rounded-lg text-slate-600 hover:bg-slate-50 focus:outline-none transition"
            title="Refresh panels"
          >
            <RefreshCw
              className={`w-4 h-4 ${isLoading ? "animate-spin text-indigo-600" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded-xl flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-rose-500 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-rose-500 hover:text-rose-700"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* 4. Panels Data Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-600">
            <thead className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4 w-28">Panel Code</th>
                <th className="py-3 px-4">Panel Name</th>
                <th className="py-3 px-4">Bundled Component Tests</th>
                <th className="py-3 px-4">Package Price</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-400">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto text-indigo-500 mb-2" />
                    Loading diagnostic panels...
                  </td>
                </tr>
              ) : filteredPanels.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-400">
                    No diagnostic panels found matching your criteria.
                  </td>
                </tr>
              ) : (
                filteredPanels.map((panel) => {
                  const isExpanded = expandedPanelId === panel.id;
                  const testsCount =
                    panel.tests?.length || panel.test_ids?.length || 0;
                  const displayTests = panel.tests || [];

                  return (
                    <React.Fragment key={panel.id}>
                      <tr className="hover:bg-slate-50/75 transition-colors">
                        <td className="py-3.5 px-4 font-mono font-bold text-indigo-600">
                          {panel.code}
                        </td>
                        <td className="py-3.5 px-4 font-medium text-slate-900">
                          <div>{panel.name}</div>
                          <div className="text-xs text-slate-400 font-mono mt-0.5">
                            ID: {panel.id.slice(0, 8)}...
                          </div>
                        </td>
                        <td className="py-3.5 px-4">
                          <div className="flex flex-wrap items-center gap-1.5 max-w-md">
                            {displayTests.slice(0, 3).map((test) => (
                              <span
                                key={test.id}
                                className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200"
                              >
                                {test.name}
                              </span>
                            ))}
                            {testsCount > 3 && (
                              <button
                                type="button"
                                onClick={() =>
                                  setExpandedPanelId(
                                    isExpanded ? null : panel.id,
                                  )
                                }
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition"
                              >
                                +{testsCount - 3} more
                                {isExpanded ? (
                                  <ChevronUp className="w-3 h-3" />
                                ) : (
                                  <ChevronDown className="w-3 h-3" />
                                )}
                              </button>
                            )}
                          </div>
                        </td>
                        <td className="py-3.5 px-4 font-semibold text-slate-900">
                          {panel.price ? `PKR ${panel.price}` : "Standard"}
                        </td>
                        <td className="py-3.5 px-4">
                          <span
                            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                              panel.is_active
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : "bg-slate-100 text-slate-600 border border-slate-200"
                            }`}
                          >
                            {panel.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <button
                            type="button"
                            onClick={() => handleTogglePanelStatus(panel)}
                            className="text-xs font-medium text-slate-500 hover:text-indigo-600 underline transition"
                          >
                            {panel.is_active ? "Deactivate" : "Activate"}
                          </button>
                        </td>
                      </tr>

                      {/* Expanded View for All Component Tests */}
                      {isExpanded && (
                        <tr className="bg-slate-50/50">
                          <td
                            colSpan={6}
                            className="p-4 border-t border-slate-100"
                          >
                            <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-xs">
                              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-1.5">
                                <Tag className="w-3.5 h-3.5 text-indigo-500" />
                                All Bundled Tests in {panel.name} (
                                {displayTests.length})
                              </h4>
                              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                                {displayTests.map((t) => (
                                  <div
                                    key={t.id}
                                    className="p-2.5 rounded-lg border border-slate-100 bg-slate-50/50 flex flex-col justify-between"
                                  >
                                    <div className="flex items-center justify-between">
                                      <span className="font-mono text-xs font-bold text-slate-700">
                                        {t.code}
                                      </span>
                                      <span className="text-[10px] uppercase font-semibold text-slate-400 bg-white px-1.5 py-0.5 rounded border border-slate-100">
                                        {t.category || "General"}
                                      </span>
                                    </div>
                                    <div className="text-xs font-medium text-slate-900 mt-1">
                                      {t.name}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 5. Create Panel Modal / Dialog */}
      {isModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-panel-heading"
          className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4"
        >
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-slate-100 animate-in fade-in zoom-in duration-150">
            <div className="flex justify-between items-center pb-4 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <span className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
                  <Layers className="w-5 h-5" />
                </span>
                <h3
                  id="create-panel-heading"
                  className="text-lg font-bold text-slate-900"
                >
                  Create Diagnostic Panel
                </h3>
              </div>
              <button
                type="button"
                aria-label="Close dialog"
                onClick={() => setIsModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {modalError && (
              <div className="mt-4 p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-center gap-2 text-rose-700 text-sm">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{modalError}</span>
              </div>
            )}

            <form onSubmit={handleCreatePanel} className="mt-4 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="panelCodeInput"
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Panel Code *
                  </label>
                  <input
                    id="panelCodeInput"
                    type="text"
                    required
                    placeholder="e.g. CBC, LFT, CMP"
                    value={newCode}
                    onChange={(e) => setNewCode(e.target.value.toUpperCase())}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono uppercase focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label
                    htmlFor="panelNameInput"
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Panel Name *
                  </label>
                  <input
                    id="panelNameInput"
                    type="text"
                    required
                    placeholder="e.g. Complete Blood Count"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="panelPriceInput"
                  className="block text-xs font-semibold text-slate-700 mb-1"
                >
                  Bundled Package Base Price (PKR)
                </label>
                <input
                  id="panelPriceInput"
                  type="text"
                  placeholder="e.g. 1500.00"
                  value={newPrice}
                  onChange={(e) => setNewPrice(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>

              {/* Component Test Selection */}
              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-xs font-semibold text-slate-700">
                    Select Component Tests * ({selectedTestIds.length} selected)
                  </label>
                  {selectedTestIds.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setSelectedTestIds([])}
                      className="text-xs text-indigo-600 hover:text-indigo-800"
                    >
                      Clear Selection
                    </button>
                  )}
                </div>

                <div className="relative mb-2">
                  <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Filter tests by name or department..."
                    value={testSearchInModal}
                    onChange={(e) => setTestSearchInModal(e.target.value)}
                    className="w-full pl-8 pr-3 py-1.5 border border-slate-200 rounded-md text-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>

                <div className="max-h-48 overflow-y-auto border border-slate-200 rounded-lg divide-y divide-slate-100 p-1">
                  {modalFilteredTests.length === 0 ? (
                    <div className="py-6 text-center text-xs text-slate-400">
                      No matching diagnostic tests available.
                    </div>
                  ) : (
                    modalFilteredTests.map((test) => {
                      const isSelected = selectedTestIds.includes(test.id);
                      return (
                        <div
                          key={test.id}
                          role="checkbox"
                          aria-checked={isSelected}
                          tabIndex={0}
                          onClick={() => toggleTestSelection(test.id)}
                          onKeyDown={(e) => {
                            if (e.key === " " || e.key === "Enter") {
                              e.preventDefault();
                              toggleTestSelection(test.id);
                            }
                          }}
                          className={`flex items-center justify-between p-2 rounded cursor-pointer transition-colors ${
                            isSelected ? "bg-indigo-50/70" : "hover:bg-slate-50"
                          }`}
                        >
                          <div className="flex items-center gap-2.5">
                            {isSelected ? (
                              <CheckSquare className="w-4 h-4 text-indigo-600" />
                            ) : (
                              <Square className="w-4 h-4 text-slate-300" />
                            )}
                            <div>
                              <span className="font-mono text-xs font-bold text-slate-800 mr-2">
                                {test.code}
                              </span>
                              <span className="text-xs text-slate-700">
                                {test.name}
                              </span>
                            </div>
                          </div>
                          <span className="text-[10px] font-medium text-slate-400 uppercase">
                            {test.category || "General"}
                          </span>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              <div className="pt-4 flex justify-end gap-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition flex items-center gap-2"
                >
                  {isSaving ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    <>
                      <Check className="w-4 h-4" />
                      Create Diagnostic Panel
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
