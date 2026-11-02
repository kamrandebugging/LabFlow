import React, { useCallback, useEffect, useState } from "react";
import {
  Plus,
  Search,
  RefreshCw,
  AlertCircle,
  Check,
  X,
  Tag,
} from "lucide-react";
import { catalogService } from "./catalogService";
import type { DiagnosticTest, TestCreateInput } from "./types";

const CATEGORIES = [
  "All",
  "Hematology",
  "Biochemistry",
  "Immunology",
  "Microbiology",
  "Histopathology",
  "Molecular",
];

interface TestCatalogScreenProps {
  onSwitchToPanels?: () => void;
  service?: typeof catalogService;
}

export function TestCatalogScreen({
  onSwitchToPanels,
  service = catalogService,
}: TestCatalogScreenProps): JSX.Element {
  const [tests, setTests] = useState<DiagnosticTest[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New Test Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [newCategory, setNewCategory] = useState("Hematology");
  const [newUnit, setNewUnit] = useState("");
  const [newPrice, setNewPrice] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  const fetchTests = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await service.listTests({
        q: searchQuery || undefined,
        category: selectedCategory === "All" ? undefined : selectedCategory,
      });
      setTests(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load tests");
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, selectedCategory, service]);

  useEffect(() => {
    fetchTests();
  }, [fetchTests]);

  const handleCreateTest = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalError(null);

    if (!newCode.trim()) {
      setModalError("Test code is required.");
      return;
    }
    if (!newName.trim()) {
      setModalError("Test name is required.");
      return;
    }

    setIsSaving(true);
    try {
      const payload: TestCreateInput = {
        code: newCode.trim().toUpperCase(),
        name: newName.trim(),
        category: newCategory,
        unit: newUnit.trim() || null,
        initial_price: newPrice.trim() || undefined,
      };

      await service.createTest(payload);
      setIsModalOpen(false);
      setNewCode("");
      setNewName("");
      setNewUnit("");
      setNewPrice("");
      fetchTests();
    } catch (err: unknown) {
      setModalError(
        err instanceof Error ? err.message : "Failed to create test.",
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex flex-col w-full max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* 1. Header & Section Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 font-headline">
            Diagnostic Test Catalog
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Standard laboratory investigations, departments & reference
            parameters
          </p>
        </div>

        {/* Switcher Pill */}
        <div className="flex items-center bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs font-medium">
          <button
            type="button"
            className="px-3 py-1.5 rounded-md bg-white text-teal-800 font-semibold shadow-xs"
          >
            Individual Tests
          </button>
          <button
            type="button"
            onClick={onSwitchToPanels}
            className="px-3 py-1.5 rounded-md text-slate-600 hover:text-slate-900 transition-colors"
          >
            Test Panels
          </button>
        </div>
      </div>

      {/* 2. Department Category Pills */}
      <div
        className="flex items-center gap-2 overflow-x-auto pb-1"
        aria-label="Department filters"
      >
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setSelectedCategory(cat)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
              selectedCategory === cat
                ? "bg-[#005c55] text-white shadow-xs"
                : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* 3. Search Bar & Action Buttons */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div className="relative w-full sm:w-96">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 w-4 h-4 pointer-events-none" />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by code, test name or department..."
            className="w-full pl-9 pr-4 py-2 bg-white text-slate-900 text-sm placeholder:text-slate-400 rounded-lg border border-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
          />
        </div>

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => fetchTests()}
            className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
            title="Refresh test catalog"
          >
            <RefreshCw
              className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`}
            />
          </button>
          <button
            type="button"
            onClick={() => setIsModalOpen(true)}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-[#005c55] hover:bg-[#0f766e] text-white text-sm font-medium rounded-lg shadow-sm transition-colors cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>Add New Test</span>
          </button>
        </div>
      </div>

      {/* Error Notice */}
      {error && (
        <div
          role="alert"
          className="flex items-center justify-between p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 shrink-0 text-red-600" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => fetchTests()}
            className="underline font-semibold hover:text-red-900"
          >
            Retry
          </button>
        </div>
      )}

      {/* 4. Tests Data Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table
            className="w-full text-left border-collapse"
            data-testid="test-catalog-table"
          >
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  Test Code
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  Investigation Name
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  Department
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  Unit
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                <tr>
                  <td
                    colSpan={5}
                    className="py-12 text-center text-slate-500 text-sm"
                  >
                    <div className="inline-flex items-center gap-2">
                      <RefreshCw className="w-4 h-4 animate-spin text-teal-600" />
                      <span>Loading test catalog...</span>
                    </div>
                  </td>
                </tr>
              ) : tests.length === 0 ? (
                <tr>
                  <td
                    colSpan={5}
                    className="py-12 text-center text-slate-500 text-sm"
                  >
                    <Tag className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                    <p className="font-medium text-slate-700">No tests found</p>
                    <p className="text-xs text-slate-400 mt-1">
                      {searchQuery
                        ? "Try searching for a different code or investigation name"
                        : "Click 'Add New Test' above to define laboratory tests"}
                    </p>
                  </td>
                </tr>
              ) : (
                tests.map((test) => (
                  <tr
                    key={test.id}
                    className="hover:bg-slate-50/80 transition-colors"
                  >
                    <td className="py-3.5 px-4 align-middle">
                      <span className="font-mono text-xs font-bold text-teal-800 bg-teal-50 px-2 py-0.5 rounded border border-teal-200">
                        {test.code}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 align-middle font-medium text-slate-900 text-sm">
                      {test.name}
                    </td>
                    <td className="py-3.5 px-4 align-middle text-sm text-slate-600">
                      {test.category || "General"}
                    </td>
                    <td className="py-3.5 px-4 align-middle font-mono text-xs text-slate-500">
                      {test.unit || "—"}
                    </td>
                    <td className="py-3.5 px-4 align-middle">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${
                          test.is_active
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            : "bg-slate-100 text-slate-500 border border-slate-200"
                        }`}
                      >
                        {test.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 5. Add New Test Modal */}
      {isModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4"
        >
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-base font-bold text-slate-900">
                Define Diagnostic Test
              </h2>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateTest} className="p-6 space-y-4">
              {modalError && (
                <div className="p-3 bg-red-50 text-red-700 rounded-lg text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{modalError}</span>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="testCodeInput"
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Test Code <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="testCodeInput"
                    type="text"
                    required
                    placeholder="e.g. CBC"
                    value={newCode}
                    onChange={(e) => setNewCode(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono uppercase focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 outline-none"
                  />
                </div>
                <div>
                  <label
                    htmlFor="testCategorySelect"
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Department
                  </label>
                  <select
                    id="testCategorySelect"
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 outline-none"
                  >
                    {CATEGORIES.filter((c) => c !== "All").map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label
                  htmlFor="testNameInput"
                  className="block text-xs font-semibold text-slate-700 mb-1"
                >
                  Investigation Name <span className="text-red-500">*</span>
                </label>
                <input
                  id="testNameInput"
                  type="text"
                  required
                  placeholder="e.g. Complete Blood Count"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="testUnitInput"
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Unit of Measurement
                  </label>
                  <input
                    id="testUnitInput"
                    type="text"
                    placeholder="e.g. mg/dL, g/dL"
                    value={newUnit}
                    onChange={(e) => setNewUnit(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 outline-none"
                  />
                </div>
                <div>
                  <label
                    htmlFor="testPriceInput"
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Base Price (PKR)
                  </label>
                  <input
                    id="testPriceInput"
                    type="text"
                    placeholder="e.g. 1200.00"
                    value={newPrice}
                    onChange={(e) => setNewPrice(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 outline-none"
                  />
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="px-5 py-2 bg-[#005c55] hover:bg-[#0f766e] text-white rounded-lg text-sm font-semibold shadow-xs flex items-center gap-1.5 disabled:opacity-60 cursor-pointer"
                >
                  {isSaving ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <Check className="w-4 h-4" />
                  )}
                  <span>Save Test</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
export default TestCatalogScreen;
