import React, { useCallback, useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import {
  Plus,
  Search,
  RefreshCw,
  AlertCircle,
  Check,
  X,
  Tag,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { catalogService } from "./catalogService";
import { ReferenceRangesManager } from "./ReferenceRangesManager";
import type { DiagnosticTest, TestCreateInput } from "./types";

const CATEGORIES = [
  { value: "All", slug: "all" },
  { value: "Hematology", slug: "hematology" },
  { value: "Biochemistry", slug: "biochemistry" },
  { value: "Immunology", slug: "immunology" },
  { value: "Microbiology", slug: "microbiology" },
  { value: "Histopathology", slug: "histopathology" },
  { value: "Molecular", slug: "molecular" },
] as const;

interface TestCatalogScreenProps {
  onSwitchToPanels?: () => void;
  service?: typeof catalogService;
}

export function TestCatalogScreen({
  onSwitchToPanels,
  service = catalogService,
}: TestCatalogScreenProps): JSX.Element {
  const { t } = useTranslation(["settings", "common"]);
  const [tests, setTests] = useState<DiagnosticTest[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New Test Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  // Reference Ranges Modal State (KAN-119)
  const [rangesTest, setRangesTest] = useState<DiagnosticTest | null>(null);
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
      setError(
        err && typeof err === "object" && "code" in err
          ? messageForError(err, (key, options) => t(`common:${key}`, options))
          : t("settings:catalog.load_failed"),
      );
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, selectedCategory, service, t]);

  useEffect(() => {
    fetchTests();
  }, [fetchTests]);

  const handleCreateTest = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalError(null);

    if (!newCode.trim()) {
      setModalError(t("settings:catalog.error_code"));
      return;
    }
    if (!newName.trim()) {
      setModalError(t("settings:catalog.error_name"));
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
        err && typeof err === "object" && "code" in err
          ? messageForError(err, (key, options) => t(`common:${key}`, options))
          : t("settings:catalog.error_create"),
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
            {t("settings:catalog.title")}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            {t("settings:catalog.subtitle")}
          </p>
        </div>

        {/* Switcher Pill */}
        <div className="flex items-center bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs font-medium">
          <button
            type="button"
            className="px-3 py-1.5 rounded-md bg-white text-teal-800 font-semibold shadow-xs"
          >
            {t("settings:catalog.tab_individual")}
          </button>
          <button
            type="button"
            onClick={onSwitchToPanels}
            className="px-3 py-1.5 rounded-md text-slate-600 hover:text-slate-900 transition-colors"
          >
            {t("settings:catalog.tab_panels")}
          </button>
        </div>
      </div>

      {/* 2. Department Category Pills */}
      <div
        className="flex items-center gap-2 overflow-x-auto pb-1"
        aria-label={t("settings:catalog.dept_filter_aria")}
      >
        {CATEGORIES.map((cat) => (
          <button
            key={cat.value}
            type="button"
            onClick={() => setSelectedCategory(cat.value)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
              selectedCategory === cat.value
                ? "bg-[#005c55] text-white shadow-xs"
                : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
            }`}
          >
            {t(`settings:catalog.categories.${cat.slug}`)}
          </button>
        ))}
      </div>

      {/* 3. Search Bar & Action Buttons */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div className="relative w-full sm:w-96">
          <Search className="absolute start-3 top-1/2 -translate-y-1/2 text-slate-400 w-4 h-4 pointer-events-none" />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("settings:catalog.search_placeholder")}
            className="w-full ps-9 pe-4 py-2 bg-white text-slate-900 text-sm placeholder:text-slate-400 rounded-lg border border-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
          />
        </div>

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => fetchTests()}
            className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
            title={t("settings:catalog.refresh_title")}
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
            <span>{t("settings:catalog.add")}</span>
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
            {t("settings:catalog.retry")}
          </button>
        </div>
      )}

      {/* 4. Tests Data Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table
            className="w-full text-start border-collapse"
            data-testid="test-catalog-table"
          >
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  {t("settings:catalog.col_code")}
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  {t("settings:catalog.col_name")}
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  {t("settings:catalog.col_department")}
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  {t("settings:catalog.col_unit")}
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  {t("settings:catalog.col_status")}
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 text-end"
                >
                  {t("settings:catalog.col_ranges")}
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
                      <span>{t("settings:catalog.loading")}</span>
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
                    <p className="font-medium text-slate-700">
                      {t("settings:catalog.empty_title")}
                    </p>
                    <p className="text-xs text-slate-400 mt-1">
                      {searchQuery
                        ? t("settings:catalog.empty_search")
                        : t("settings:catalog.empty_hint")}
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
                        <bdi dir="ltr">{test.code}</bdi>
                      </span>
                    </td>
                    <td className="py-3.5 px-4 align-middle font-medium text-slate-900 text-sm">
                      <bdi dir="ltr">{test.name}</bdi>
                    </td>
                    <td className="py-3.5 px-4 align-middle text-sm text-slate-600">
                      {test.category || t("settings:catalog.general")}
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
                        {test.is_active
                          ? t("common:status.active")
                          : t("common:status.inactive")}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 align-middle text-end">
                      <button
                        type="button"
                        onClick={() => setRangesTest(test)}
                        className="px-2.5 py-1 text-xs font-medium text-teal-800 bg-teal-50 hover:bg-teal-100 border border-teal-200 rounded-md transition-colors cursor-pointer"
                      >
                        {t("settings:catalog.ranges_button")}
                      </button>
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
                {t("settings:catalog.modal_title")}
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
                    {t("settings:catalog.code_label")}{" "}
                    <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="testCodeInput"
                    type="text"
                    required
                    placeholder={t("settings:catalog.code_placeholder")}
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
                    {t("settings:catalog.dept_label")}
                  </label>
                  <select
                    id="testCategorySelect"
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 outline-none"
                  >
                    {CATEGORIES.filter((c) => c.value !== "All").map((c) => (
                      <option key={c.value} value={c.value}>
                        {t(`settings:catalog.categories.${c.slug}`)}
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
                  {t("settings:catalog.name_label")}{" "}
                  <span className="text-red-500">*</span>
                </label>
                <input
                  id="testNameInput"
                  type="text"
                  required
                  placeholder={t("settings:catalog.name_placeholder")}
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
                    {t("settings:catalog.unit_label")}
                  </label>
                  <input
                    id="testUnitInput"
                    type="text"
                    placeholder={t("settings:catalog.unit_placeholder")}
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
                    {t("settings:catalog.price_label")}
                  </label>
                  <input
                    id="testPriceInput"
                    type="text"
                    placeholder={t("settings:catalog.price_placeholder")}
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
                  {t("common:actions.cancel")}
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
                  <span>{t("settings:catalog.save")}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 6. Reference Ranges Modal (KAN-119) */}
      {rangesTest && (
        <div
          className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50"
          role="dialog"
          aria-modal="true"
          aria-label={t("settings:catalog.ranges_modal_aria", {
            code: rangesTest.code,
          })}
        >
          <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[85vh] overflow-y-auto">
            <div className="sticky top-0 bg-white border-b border-slate-100 px-5 py-4 flex items-center justify-between rounded-t-xl">
              <h2 className="text-base font-bold text-slate-900">
                <Trans
                  i18nKey="settings:catalog.ranges_modal_title"
                  values={{ code: rangesTest.code }}
                  components={{ bdi: <bdi dir="ltr" /> }}
                />
              </h2>
              <button
                type="button"
                onClick={() => setRangesTest(null)}
                className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                aria-label={t("settings:catalog.ranges_close_aria")}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5">
              <ReferenceRangesManager
                testId={rangesTest.id}
                testCode={rangesTest.code}
                service={service}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
export default TestCatalogScreen;
