import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { useAuthStore } from "../auth/authStore";
import { messageForError } from "../../lib/errors";
import { formatDate } from "../../lib/format";
import { settingsService, SettingsApiError } from "./settingsService";
import type {
  Branch,
  BranchOpenWorkDetails,
  CreateBranchPayload,
  PlanLimitDetails,
  UpdateBranchPayload,
} from "./types";

export const BranchesScreen: React.FC = () => {
  const { t } = useTranslation(["settings", "common"]);
  const user = useAuthStore((s) => s.user);
  const isOwner = user?.role === "owner";

  // Data state
  const [branches, setBranches] = useState<Branch[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Filters state
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [activeTab, setActiveTab] = useState<
    "all" | "open" | "closed" | "collection"
  >("all");
  const [includeClosed, setIncludeClosed] = useState<boolean>(true);

  // Modal states
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [editingBranch, setEditingBranch] = useState<Branch | null>(null);
  const [closingBranch, setClosingBranch] = useState<Branch | null>(null);
  const [closeBlockerDetails, setCloseBlockerDetails] =
    useState<BranchOpenWorkDetails | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Form states for Add / Edit
  const [formCode, setFormCode] = useState<string>("");
  const [formName, setFormName] = useState<string>("");
  const [formAddress, setFormAddress] = useState<string>("");
  const [formPhone, setFormPhone] = useState<string>("");
  const [formIsCollection, setFormIsCollection] = useState<boolean>(false);

  const fetchBranches = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await settingsService.getBranches(
        isOwner ? includeClosed : false,
      );
      setBranches(data);
    } catch (err: unknown) {
      setErrorMsg(
        messageForError(err, (key, options) => t(`common:${key}`, options)),
      );
    } finally {
      setIsLoading(false);
    }
  }, [includeClosed, isOwner, t]);

  useEffect(() => {
    void fetchBranches();
  }, [fetchBranches]);

  // Metric computations
  const metrics = useMemo(() => {
    const total = branches.length;
    const testingLabs = branches.filter((b) => !b.is_collection_centre).length;
    const collectionCentres = branches.filter(
      (b) => b.is_collection_centre,
    ).length;
    const openCount = branches.filter((b) => !b.deleted_at).length;
    const closedCount = branches.filter((b) => !!b.deleted_at).length;

    return { total, testingLabs, collectionCentres, openCount, closedCount };
  }, [branches]);

  // Filtered branches
  const filteredBranches = useMemo(() => {
    return branches.filter((branch) => {
      // Tab filter
      if (activeTab === "open" && branch.deleted_at) return false;
      if (activeTab === "closed" && !branch.deleted_at) return false;
      if (activeTab === "collection" && !branch.is_collection_centre)
        return false;

      // Text search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesName = branch.name.toLowerCase().includes(q);
        const matchesCode = branch.code.toLowerCase().includes(q);
        const matchesAddress =
          branch.address?.toLowerCase().includes(q) ?? false;
        const matchesPhone = branch.phone?.toLowerCase().includes(q) ?? false;
        if (!matchesName && !matchesCode && !matchesAddress && !matchesPhone) {
          return false;
        }
      }

      return true;
    });
  }, [branches, activeTab, searchQuery]);

  // Open Add modal
  const handleOpenAdd = (): void => {
    setFormCode("");
    setFormName("");
    setFormAddress("");
    setFormPhone("");
    setFormIsCollection(false);
    setActionError(null);
    setIsCreateModalOpen(true);
  };

  // Open Edit modal
  const handleOpenEdit = (branch: Branch): void => {
    setEditingBranch(branch);
    setFormCode(branch.code);
    setFormName(branch.name);
    setFormAddress(branch.address || "");
    setFormPhone(branch.phone || "");
    setFormIsCollection(branch.is_collection_centre);
    setActionError(null);
  };

  // Submit Add
  const handleSubmitAdd = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    if (!formCode.trim() || !formName.trim()) {
      setActionError(t("settings:branches.error_required"));
      return;
    }

    setIsSubmitting(true);
    setActionError(null);

    const payload: CreateBranchPayload = {
      code: formCode.trim().toUpperCase(),
      name: formName.trim(),
      address: formAddress.trim() || null,
      phone: formPhone.trim() || null,
      is_collection_centre: formIsCollection,
    };

    try {
      await settingsService.createBranch(payload);
      setIsCreateModalOpen(false);
      await fetchBranches();
    } catch (err: unknown) {
      const isSettingsErr =
        err instanceof SettingsApiError ||
        (typeof err === "object" && err !== null && "code" in err);
      const code = isSettingsErr ? (err as { code: string }).code : undefined;
      const details = isSettingsErr
        ? (err as { details?: unknown }).details
        : undefined;

      if (code === "plan_limit_reached") {
        const limitDetails = details as PlanLimitDetails | undefined;
        if (limitDetails?.plan_limit) {
          setActionError(
            t("settings:branches.error_plan_limit", {
              limit: limitDetails.plan_limit,
              current: limitDetails.current_count,
            }),
          );
        } else {
          setActionError(t("settings:branches.error_plan_limit_short"));
        }
      } else if (code === "duplicate_branch_code") {
        setActionError(
          t("settings:branches.error_duplicate_code", {
            code: formCode.toUpperCase(),
          }),
        );
      } else if (code === "invalid_branch_code") {
        setActionError(t("settings:branches.error_invalid_code_add"));
      } else {
        setActionError(
          messageForError(err, (key, options) => t(`common:${key}`, options)),
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Submit Edit
  const handleSubmitEdit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    if (!editingBranch) return;

    setIsSubmitting(true);
    setActionError(null);

    const payload: UpdateBranchPayload = {
      name: formName.trim(),
      address: formAddress.trim() || null,
      phone: formPhone.trim() || null,
      is_collection_centre: formIsCollection,
    };

    // If code was changed and differs from original
    if (formCode.trim().toUpperCase() !== editingBranch.code) {
      payload.code = formCode.trim().toUpperCase();
    }

    try {
      await settingsService.updateBranch(editingBranch.id, payload);
      setEditingBranch(null);
      await fetchBranches();
    } catch (err: unknown) {
      const isSettingsErr =
        err instanceof SettingsApiError ||
        (typeof err === "object" && err !== null && "code" in err);
      const code = isSettingsErr ? (err as { code: string }).code : undefined;

      if (code === "branch_code_immutable") {
        setActionError(t("settings:branches.error_code_immutable"));
      } else if (code === "duplicate_branch_code") {
        setActionError(
          t("settings:branches.error_duplicate_code", {
            code: formCode.toUpperCase(),
          }),
        );
      } else if (code === "invalid_branch_code") {
        setActionError(t("settings:branches.error_invalid_code_edit"));
      } else {
        setActionError(
          messageForError(err, (key, options) => t(`common:${key}`, options)),
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Confirm close
  const handleExecuteClose = async (): Promise<void> => {
    if (!closingBranch) return;

    setIsSubmitting(true);
    setCloseBlockerDetails(null);
    setActionError(null);

    try {
      await settingsService.closeBranch(closingBranch.id);
      setClosingBranch(null);
      await fetchBranches();
    } catch (err: unknown) {
      const isSettingsErr =
        err instanceof SettingsApiError ||
        (typeof err === "object" && err !== null && "code" in err);
      const code = isSettingsErr ? (err as { code: string }).code : undefined;
      const details = isSettingsErr
        ? (err as { details?: unknown }).details
        : undefined;

      if (code === "branch_has_open_work") {
        const workDetails = details as BranchOpenWorkDetails | undefined;
        setCloseBlockerDetails(workDetails || {});
        setActionError(t("settings:branches.error_open_work"));
      } else {
        setActionError(
          messageForError(err, (key, options) => t(`common:${key}`, options)),
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Reopen branch
  const handleExecuteReopen = async (branchId: string): Promise<void> => {
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      await settingsService.reopenBranch(branchId);
      await fetchBranches();
    } catch (err: unknown) {
      setErrorMsg(
        messageForError(err, (key, options) => t(`common:${key}`, options)),
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex-1 bg-slate-50 min-h-screen px-4 sm:px-8 py-6 max-w-[1280px] mx-auto space-y-6">
      {/* Header & Breadcrumb */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-3 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
            <span>{t("common:nav.settings")}</span>
            <span className="material-symbols-outlined text-[14px] rtl:rotate-180">
              chevron_right
            </span>
            <span className="text-teal-700 font-medium">
              {t("settings:branches.title")}
            </span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            {t("settings:branches.title")}
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            {t("settings:branches.subtitle")}
          </p>
        </div>

        {isOwner && (
          <button
            type="button"
            onClick={handleOpenAdd}
            className="inline-flex items-center gap-2 bg-teal-600 hover:bg-teal-700 active:bg-teal-800 text-white font-medium text-sm px-4 py-2.5 rounded-lg shadow-sm transition-all"
          >
            <span className="material-symbols-outlined text-[19px]">add</span>
            <span>{t("settings:branches.add")}</span>
          </button>
        )}
      </div>

      {/* Global Error Banner */}
      {errorMsg && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3 text-red-800">
          <span className="material-symbols-outlined text-[20px] text-red-600 shrink-0">
            error
          </span>
          <div className="text-sm">
            <p className="font-semibold">
              {t("settings:branches.load_error_title")}
            </p>
            <p className="text-red-700 mt-0.5">{errorMsg}</p>
          </div>
        </div>
      )}

      {/* Summary Metrics Pills */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* Total Facilities */}
        <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              {t("settings:branches.metric_total")}
            </p>
            <p className="text-xl font-bold text-slate-900 mt-0.5">
              {metrics.total}
            </p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-600">
            <span className="material-symbols-outlined text-[20px]">
              domain
            </span>
          </div>
        </div>

        {/* Full Testing Labs */}
        <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              {t("settings:branches.metric_testing")}
            </p>
            <p className="text-xl font-bold text-slate-900 mt-0.5">
              {metrics.testingLabs}
            </p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-teal-50 border border-teal-100 flex items-center justify-center text-teal-700">
            <span className="material-symbols-outlined text-[20px]">
              science
            </span>
          </div>
        </div>

        {/* Collection Centres */}
        <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              {t("settings:branches.metric_collection")}
            </p>
            <p className="text-xl font-bold text-slate-900 mt-0.5">
              {metrics.collectionCentres}
            </p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-700">
            <span className="material-symbols-outlined text-[20px]">
              point_of_sale
            </span>
          </div>
        </div>

        {/* Operations */}
        <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              {t("settings:branches.metric_operations")}
            </p>
            <p className="text-base font-bold text-slate-900 mt-0.5 flex items-center gap-1.5">
              <span className="text-teal-700">
                {t("settings:branches.open_count", { n: metrics.openCount })}
              </span>
              <span className="text-slate-300 font-normal">·</span>
              <span className="text-slate-500 font-medium text-xs">
                {t("settings:branches.closed_count", {
                  n: metrics.closedCount,
                })}
              </span>
            </p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-600">
            <span className="material-symbols-outlined text-[20px]">
              schedule
            </span>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Filter Tabs */}
        <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg">
          <button
            type="button"
            onClick={() => setActiveTab("all")}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeTab === "all"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {t("settings:branches.tab_all", { n: metrics.total })}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("open")}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeTab === "open"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {t("settings:branches.tab_open", { n: metrics.openCount })}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("closed")}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeTab === "closed"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {t("settings:branches.tab_closed", { n: metrics.closedCount })}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("collection")}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeTab === "collection"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {t("settings:branches.tab_collection", {
              n: metrics.collectionCentres,
            })}
          </button>
        </div>

        {/* Search input + Include closed toggle */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1 sm:w-64">
            <span className="material-symbols-outlined absolute start-2.5 top-2.5 text-[18px] text-slate-400">
              search
            </span>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t("settings:branches.search_placeholder")}
              className="w-full ps-8 pe-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-teal-600 text-slate-900"
            />
          </div>

          {isOwner && (
            <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-slate-600 shrink-0">
              <input
                type="checkbox"
                checked={includeClosed}
                onChange={(e) => setIncludeClosed(e.target.checked)}
                className="rounded border-slate-300 text-teal-600 focus:ring-teal-500 w-3.5 h-3.5"
              />
              <span>{t("settings:branches.include_closed")}</span>
            </label>
          )}
        </div>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 animate-pulse shadow-sm"
            >
              <div className="h-6 bg-slate-200 rounded w-1/2"></div>
              <div className="h-4 bg-slate-100 rounded w-1/3"></div>
              <div className="h-16 bg-slate-50 rounded"></div>
            </div>
          ))}
        </div>
      )}

      {/* Honest Empty State */}
      {!isLoading && filteredBranches.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-12 text-center space-y-3 shadow-sm">
          <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-500 mx-auto flex items-center justify-center">
            <span className="material-symbols-outlined text-[24px]">store</span>
          </div>
          <h3 className="text-base font-semibold text-slate-900">
            {t("settings:branches.empty_title")}
          </h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {searchQuery ? (
              <Trans
                i18nKey="settings:branches.empty_search"
                values={{ query: searchQuery }}
                components={{ bdi: <bdi dir="ltr" /> }}
              />
            ) : (
              t("settings:branches.empty_none")
            )}
          </p>
          {isOwner && !searchQuery && (
            <button
              type="button"
              onClick={handleOpenAdd}
              className="mt-2 inline-flex items-center gap-2 bg-teal-600 hover:bg-teal-700 text-white text-xs font-medium px-3.5 py-2 rounded-lg"
            >
              <span className="material-symbols-outlined text-[16px]">add</span>
              <span>{t("settings:branches.add_first")}</span>
            </button>
          )}
        </div>
      )}

      {/* Branch Cards Grid */}
      {!isLoading && filteredBranches.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {filteredBranches.map((branch) => {
            const isClosed = !!branch.deleted_at;

            return (
              <div
                key={branch.id}
                className={`bg-white border border-slate-200 rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow flex flex-col justify-between ${
                  isClosed ? "opacity-90 bg-slate-50/50" : ""
                }`}
              >
                <div className="space-y-4">
                  {/* Card Header Strip */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center flex-wrap gap-2">
                        <h3 className="text-base font-bold text-slate-900">
                          <bdi dir="ltr">{branch.name}</bdi>
                        </h3>
                        {branch.is_collection_centre ? (
                          <span className="inline-flex items-center gap-1 bg-blue-50 text-blue-700 border border-blue-200 font-semibold px-2 py-0.5 rounded text-[11px]">
                            <span className="material-symbols-outlined text-[13px]">
                              point_of_sale
                            </span>
                            {t("settings:branches.badge_collection")}
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-teal-50 text-teal-800 border border-teal-200">
                            {t("settings:branches.badge_testing")}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 pt-0.5">
                        <span
                          className="inline-flex items-center gap-1 font-mono text-[12px] bg-slate-100 text-slate-700 px-2 py-0.5 rounded border border-slate-200 font-medium"
                          title={t("settings:branches.code_title")}
                        >
                          <span className="material-symbols-outlined text-[13px] text-slate-500">
                            lock
                          </span>
                          <bdi dir="ltr">{branch.code}</bdi>
                        </span>
                        <span className="text-[11px] text-slate-400">
                          {t("settings:branches.code_locked")}
                        </span>
                      </div>
                    </div>

                    {/* Status Pill */}
                    {isClosed ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs bg-slate-100 text-slate-600 border border-slate-200 font-medium shrink-0">
                        <span className="w-2 h-2 rounded-full bg-slate-400"></span>
                        {t("settings:branches.status_closed")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs bg-green-50 text-green-700 border border-green-200 font-medium shrink-0">
                        <span className="w-2 h-2 rounded-full bg-green-600"></span>
                        {t("settings:branches.status_open")}
                      </span>
                    )}
                  </div>

                  {/* Address & Phone */}
                  <div className="space-y-1 text-xs text-slate-600">
                    <div className="flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-[16px] text-slate-400">
                        pin_drop
                      </span>
                      <span>
                        {branch.address ? (
                          <bdi dir="ltr">{branch.address}</bdi>
                        ) : (
                          t("settings:branches.no_address")
                        )}
                      </span>
                    </div>
                    {branch.phone && (
                      <div className="flex items-center gap-1.5">
                        <span className="material-symbols-outlined text-[16px] text-slate-400">
                          call
                        </span>
                        <span dir="ltr">{branch.phone}</span>
                      </div>
                    )}
                  </div>

                  <div className="h-px bg-slate-100"></div>

                  {/* Capabilities & Operational Details */}
                  <div className="space-y-2 text-xs">
                    <div className="flex items-center gap-2 text-slate-700">
                      {branch.result_entry_enabled ? (
                        <>
                          <span className="material-symbols-outlined text-[16px] text-green-600">
                            check_circle
                          </span>
                          <span>{t("settings:branches.result_entry_on")}</span>
                        </>
                      ) : (
                        <>
                          <span className="material-symbols-outlined text-[16px] text-slate-400">
                            block
                          </span>
                          <span className="text-slate-500">
                            {t("settings:branches.result_entry_off")}
                          </span>
                        </>
                      )}
                    </div>

                    {branch.is_collection_centre ? (
                      <div className="flex items-center gap-2 text-slate-600">
                        <span className="material-symbols-outlined text-[16px] text-teal-600">
                          sync_alt
                        </span>
                        <span>{t("settings:branches.routes_specimens")}</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-slate-600">
                        <span className="material-symbols-outlined text-[16px] text-teal-600">
                          biotech
                        </span>
                        <span>{t("settings:branches.full_bench")}</span>
                      </div>
                    )}

                    {isClosed && branch.deleted_at && (
                      <div className="flex items-center gap-2 text-slate-500 text-[11px] bg-slate-100/70 p-2 rounded-lg">
                        <span className="material-symbols-outlined text-[15px] text-slate-400">
                          history
                        </span>
                        <span>
                          <Trans
                            i18nKey="settings:branches.closed_on"
                            values={{ date: formatDate(branch.deleted_at) }}
                            components={{ bdi: <bdi dir="ltr" /> }}
                          />
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Footer Action Strip */}
                {isOwner && (
                  <div className="pt-4 mt-4 border-t border-slate-100 flex items-center justify-between gap-3">
                    {isClosed ? (
                      <button
                        type="button"
                        onClick={() => handleExecuteReopen(branch.id)}
                        disabled={isSubmitting}
                        className="px-3.5 py-1.5 bg-white border border-teal-600 hover:bg-teal-50 text-teal-700 text-xs font-semibold rounded-lg shadow-sm transition-colors"
                      >
                        {t("settings:branches.reopen")}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setClosingBranch(branch);
                          setCloseBlockerDetails(null);
                          setActionError(null);
                        }}
                        disabled={isSubmitting}
                        className="px-3.5 py-1.5 bg-white border border-slate-300 hover:border-red-300 text-slate-700 hover:text-red-600 text-xs font-medium rounded-lg shadow-sm hover:bg-red-50/50 transition-colors"
                      >
                        {t("settings:branches.close")}
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => handleOpenEdit(branch)}
                      className="text-teal-700 hover:text-teal-800 text-xs font-semibold hover:underline"
                    >
                      {t("settings:branches.edit")}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Policy and Traceability Information Box */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex items-start gap-4">
        <div className="w-10 h-10 rounded-lg bg-teal-50 text-teal-700 border border-teal-100 flex items-center justify-center shrink-0">
          <span className="material-symbols-outlined text-[22px]">policy</span>
        </div>
        <div className="space-y-1 text-xs">
          <h4 className="font-bold text-slate-900">
            {t("settings:branches.policy_title")}
          </h4>
          <p className="text-slate-600 leading-relaxed">
            <Trans
              i18nKey="settings:branches.policy_body"
              components={{
                code: (
                  <code className="font-mono bg-slate-100 px-1 py-0.5 rounded text-slate-800" />
                ),
              }}
            />
          </p>
        </div>
      </div>

      {/* Modal: Add Branch */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full p-6 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900">
                {t("settings:branches.modal_add_title")}
              </h3>
              <button
                type="button"
                onClick={() => setIsCreateModalOpen(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <span className="material-symbols-outlined text-[20px]">
                  close
                </span>
              </button>
            </div>

            {actionError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700">
                {actionError}
              </div>
            )}

            <form onSubmit={handleSubmitAdd} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  {t("settings:branches.code_label_add")}
                </label>
                <input
                  type="text"
                  required
                  maxLength={3}
                  value={formCode}
                  onChange={(e) => setFormCode(e.target.value.toUpperCase())}
                  placeholder={t("settings:branches.code_placeholder")}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono text-sm uppercase focus:ring-1 focus:ring-teal-500 focus:outline-none"
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  {t("settings:branches.code_help")}
                </p>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  {t("settings:branches.name_label")}
                </label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder={t("settings:branches.name_placeholder")}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-1 focus:ring-teal-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  {t("settings:branches.address_label")}
                </label>
                <input
                  type="text"
                  value={formAddress}
                  onChange={(e) => setFormAddress(e.target.value)}
                  placeholder={t("settings:branches.address_placeholder")}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-1 focus:ring-teal-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  {t("settings:branches.phone_label")}
                </label>
                <input
                  type="text"
                  value={formPhone}
                  onChange={(e) => setFormPhone(e.target.value)}
                  placeholder={t("settings:branches.phone_placeholder")}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-1 focus:ring-teal-500 focus:outline-none"
                />
              </div>

              <div className="pt-2">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formIsCollection}
                    onChange={(e) => setFormIsCollection(e.target.checked)}
                    className="mt-0.5 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                  />
                  <div>
                    <span className="font-semibold text-slate-800 block">
                      {t("settings:branches.is_collection")}
                    </span>
                    <span className="text-slate-500 block text-[11px]">
                      {t("settings:branches.collection_help_add")}
                    </span>
                  </div>
                </label>
              </div>

              <div className="pt-4 flex items-center justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  disabled={isSubmitting}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-slate-700 hover:bg-slate-50 text-xs font-medium"
                >
                  {t("common:actions.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {isSubmitting
                    ? t("common:actions.saving")
                    : t("settings:branches.create")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Edit Branch */}
      {editingBranch && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full p-6 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900">
                <Trans
                  i18nKey="settings:branches.modal_edit_title"
                  values={{ name: editingBranch.name }}
                  components={{ bdi: <bdi dir="ltr" /> }}
                />
              </h3>
              <button
                type="button"
                onClick={() => setEditingBranch(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <span className="material-symbols-outlined text-[20px]">
                  close
                </span>
              </button>
            </div>

            {actionError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700">
                {actionError}
              </div>
            )}

            <form onSubmit={handleSubmitEdit} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  {t("settings:branches.code_label_edit")}
                </label>
                <input
                  type="text"
                  maxLength={3}
                  value={formCode}
                  onChange={(e) => setFormCode(e.target.value.toUpperCase())}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono text-sm uppercase focus:ring-1 focus:ring-teal-500 focus:outline-none"
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  {t("settings:branches.code_note_edit")}
                </p>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  {t("settings:branches.name_label")}
                </label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-1 focus:ring-teal-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  {t("settings:branches.address_label")}
                </label>
                <input
                  type="text"
                  value={formAddress}
                  onChange={(e) => setFormAddress(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-1 focus:ring-teal-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  {t("settings:branches.phone_label")}
                </label>
                <input
                  type="text"
                  value={formPhone}
                  onChange={(e) => setFormPhone(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-1 focus:ring-teal-500 focus:outline-none"
                />
              </div>

              <div className="pt-2">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formIsCollection}
                    onChange={(e) => setFormIsCollection(e.target.checked)}
                    className="mt-0.5 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                  />
                  <div>
                    <span className="font-semibold text-slate-800 block">
                      {t("settings:branches.is_collection")}
                    </span>
                    <span className="text-slate-500 block text-[11px]">
                      {t("settings:branches.collection_help_edit")}
                    </span>
                  </div>
                </label>
              </div>

              <div className="pt-4 flex items-center justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setEditingBranch(null)}
                  disabled={isSubmitting}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-slate-700 hover:bg-slate-50 text-xs font-medium"
                >
                  {t("common:actions.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {isSubmitting
                    ? t("common:actions.saving")
                    : t("settings:branches.save_changes")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Close Branch Confirmation */}
      {closingBranch && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-3 text-red-600">
              <span className="material-symbols-outlined text-[24px]">
                warning
              </span>
              <h3 className="text-base font-bold text-slate-900">
                <Trans
                  i18nKey="settings:branches.modal_close_title"
                  values={{
                    name: closingBranch.name,
                    code: closingBranch.code,
                  }}
                  components={{ bdi: <bdi dir="ltr" /> }}
                />
              </h3>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              {t("settings:branches.close_help")}
            </p>

            {/* If blocked by open work */}
            {closeBlockerDetails && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3.5 space-y-2 text-xs text-red-800">
                <p className="font-bold flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[16px]">
                    error
                  </span>
                  {t("settings:branches.blocker_title")}
                </p>
                <ul className="list-disc list-inside space-y-1 text-red-700 ps-1">
                  {typeof closeBlockerDetails.samples_held === "number" &&
                    closeBlockerDetails.samples_held > 0 && (
                      <li>
                        <strong>
                          <bdi dir="ltr">
                            {closeBlockerDetails.samples_held}
                          </bdi>
                        </strong>{" "}
                        {t("settings:branches.blocker_samples")}
                      </li>
                    )}
                  {typeof closeBlockerDetails.open_transfers_in === "number" &&
                    closeBlockerDetails.open_transfers_in > 0 && (
                      <li>
                        <strong>
                          <bdi dir="ltr">
                            {closeBlockerDetails.open_transfers_in}
                          </bdi>
                        </strong>{" "}
                        {t("settings:branches.blocker_in")}
                      </li>
                    )}
                  {typeof closeBlockerDetails.open_transfers_out === "number" &&
                    closeBlockerDetails.open_transfers_out > 0 && (
                      <li>
                        <strong>
                          <bdi dir="ltr">
                            {closeBlockerDetails.open_transfers_out}
                          </bdi>
                        </strong>{" "}
                        {t("settings:branches.blocker_out")}
                      </li>
                    )}
                </ul>
                <p className="text-[11px] text-red-600 mt-1">
                  {t("settings:branches.blocker_hint")}
                </p>
              </div>
            )}

            {actionError && !closeBlockerDetails && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700">
                {actionError}
              </div>
            )}

            <div className="pt-4 flex items-center justify-end gap-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setClosingBranch(null)}
                disabled={isSubmitting}
                className="px-4 py-2 border border-slate-300 rounded-lg text-slate-700 hover:bg-slate-50 text-xs font-medium"
              >
                {t("common:actions.cancel")}
              </button>
              <button
                type="button"
                onClick={handleExecuteClose}
                disabled={isSubmitting}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold shadow-sm"
              >
                {isSubmitting
                  ? t("settings:branches.closing")
                  : t("settings:branches.confirm_close")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
