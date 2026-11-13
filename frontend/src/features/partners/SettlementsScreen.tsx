import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowDownToLine,
  ChevronRight,
  Clock,
  Filter,
  Search,
  Wallet,
  X,
} from "lucide-react";
import { useAuthStore } from "../auth/authStore";
import { messageForError } from "../../lib/errors";
import { formatMoney, statusLabel } from "../../lib/format";
import { PartnerApiError, partnersService } from "./partnersService";
import type {
  ReferralPartner,
  Settlement,
  SettlementExceptionsData,
  SettlementListResponse,
  SettlementStatus,
} from "./types";

export const SettlementsScreen: React.FC = () => {
  const { t, i18n } = useTranslation(["settlements", "common"]);
  const lang = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const [searchParams, setSearchParams] = useSearchParams();
  const user = useAuthStore((s) => s.user);
  const isAuthorized = user?.role === "owner" || user?.role === "manager";

  // URL query params
  const initialPartnerId = searchParams.get("partner_id") || "";
  const initialPeriod = searchParams.get("period") || "";
  const initialStatus = (searchParams.get("status") || "ALL").toUpperCase();

  // Data state
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [exceptions, setExceptions] = useState<SettlementExceptionsData | null>(
    null,
  );
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [partners, setPartners] = useState<ReferralPartner[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Filter state
  const [activeTab, setActiveTab] = useState<string>(initialStatus);
  const [selectedPartnerId, setSelectedPartnerId] =
    useState<string>(initialPartnerId);
  const [selectedPeriod, setSelectedPeriod] = useState<string>(initialPeriod);
  const [searchTerm, setSearchTerm] = useState<string>("");

  // Partner map
  const partnerMap = useMemo(() => {
    const map = new Map<string, string>();
    partners.forEach((p) => map.set(p.id, p.name));
    return map;
  }, [partners]);

  /** Server codes become translated text; a raw `detail` is never rendered. */
  const translateError = useCallback(
    (err: unknown): string =>
      messageForError(err, (key) =>
        key.includes(":") ? t(key) : t(`common:${key}`),
      ),
    [t],
  );

  // Load partners and exceptions
  useEffect(() => {
    if (!isAuthorized) return;
    let isMounted = true;
    partnersService
      .getPartners()
      .then((data) => {
        if (isMounted) setPartners(data);
      })
      .catch(() => {});

    partnersService
      .getSettlementExceptions()
      .then((data) => {
        if (isMounted) setExceptions(data);
      })
      .catch(() => {});

    return () => {
      isMounted = false;
    };
  }, [isAuthorized]);

  const fetchSettlements = useCallback(
    async (cursor?: string): Promise<void> => {
      if (!isAuthorized) return;
      const isInitial = !cursor;
      if (isInitial) {
        setIsLoading(true);
        setErrorMsg(null);
      } else {
        setIsLoadingMore(true);
      }

      try {
        const statusParam =
          activeTab === "ALL" ? undefined : (activeTab as SettlementStatus);

        const response: SettlementListResponse =
          await partnersService.getSettlements({
            partner_id: selectedPartnerId || undefined,
            period: selectedPeriod || undefined,
            status: statusParam,
            cursor: cursor || undefined,
            limit: 50,
          });

        if (isInitial) {
          setSettlements(response.results);
        } else {
          setSettlements((prev) => [...prev, ...response.results]);
        }
        setNextCursor(response.next_cursor);
      } catch (err: unknown) {
        if (err instanceof PartnerApiError) {
          setErrorMsg(translateError(err));
        } else if (err instanceof Error) {
          setErrorMsg(t("settlements:errors.load_failed"));
        } else {
          setErrorMsg(t("settlements:errors.load_failed"));
        }
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [
      activeTab,
      selectedPartnerId,
      selectedPeriod,
      isAuthorized,
      translateError,
      t,
    ],
  );

  useEffect(() => {
    fetchSettlements();
  }, [fetchSettlements]);

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    const newParams = new URLSearchParams(searchParams);
    if (tab === "ALL") {
      newParams.delete("status");
    } else {
      newParams.set("status", tab);
    }
    setSearchParams(newParams);
  };

  const handlePartnerChange = (partnerId: string) => {
    setSelectedPartnerId(partnerId);
    const newParams = new URLSearchParams(searchParams);
    if (partnerId) {
      newParams.set("partner_id", partnerId);
    } else {
      newParams.delete("partner_id");
    }
    setSearchParams(newParams);
  };

  const handlePeriodChange = (period: string) => {
    setSelectedPeriod(period);
    const newParams = new URLSearchParams(searchParams);
    if (period) {
      newParams.set("period", period);
    } else {
      newParams.delete("period");
    }
    setSearchParams(newParams);
  };

  const resetFilters = () => {
    setActiveTab("ALL");
    setSelectedPartnerId("");
    setSelectedPeriod("");
    setSearchTerm("");
    setSearchParams(new URLSearchParams());
  };

  const handleExportCsv = () => {
    if (settlements.length === 0) return;
    // The exported file keeps its stable English column names: it is a data
    // artefact consumed by spreadsheets, not on-screen text.
    const headers = [
      "Settlement ID",
      "Partner Name",
      "Partner ID",
      "Period",
      "Total (PKR)",
      "Status",
      "Created At",
      "Approved At",
    ];

    const rows = settlements.map((s) => [
      s.id,
      `"${(partnerMap.get(s.referral_partner_id) || s.referral_partner_id).replace(/"/g, '""')}"`,
      s.referral_partner_id,
      s.period,
      s.total,
      s.status,
      s.created_at,
      s.approved_at || "",
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute(
      "download",
      `settlements-${activeTab.toLowerCase()}-${Date.now()}.csv`,
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Filter client-side by search
  const filteredSettlements = useMemo(() => {
    if (!searchTerm.trim()) return settlements;
    const term = searchTerm.toLowerCase();
    return settlements.filter((s) => {
      const partnerName = partnerMap.get(s.referral_partner_id) || "";
      return (
        s.id.toLowerCase().includes(term) ||
        s.period.toLowerCase().includes(term) ||
        partnerName.toLowerCase().includes(term) ||
        s.referral_partner_id.toLowerCase().includes(term)
      );
    });
  }, [settlements, searchTerm, partnerMap]);

  // Aggregate stats from loaded set
  const totalSettlementAmount = useMemo(() => {
    const sum = settlements.reduce(
      (acc, s) => acc + parseFloat(s.total || "0"),
      0,
    );
    return sum.toFixed(2);
  }, [settlements]);

  // Status tabs read from the shared settlement status words.
  const statusTabLabel = (tab: string): string =>
    tab === "ALL"
      ? t("common:labels.all")
      : t(`common:status.settlement.${tab.toLowerCase()}`);

  const selectedPartnerName = selectedPartnerId
    ? partnerMap.get(selectedPartnerId)
    : undefined;

  if (!isAuthorized) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6 text-xs text-slate-600">
        <div className="bg-white border border-slate-200 rounded-xl p-8 max-w-md text-center shadow-xs">
          <AlertTriangle className="w-8 h-8 text-amber-600 mx-auto mb-3" />
          <h2 className="text-sm font-bold text-slate-900 mb-1">
            {t("settlements:access.title")}
          </h2>
          <p className="text-slate-600 mb-4">{t("settlements:access.body")}</p>
          <Link
            to="/partners"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-teal-600 text-white rounded-lg font-semibold hover:bg-teal-700 transition-colors"
          >
            <span>{t("settlements:access.back_to_partners")}</span>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col selection:bg-teal-100 selection:text-teal-900">
      <main className="flex-1 p-6 md:p-8 max-w-6xl mx-auto w-full space-y-6">
        {/* BREADCRUMB & HEADER */}
        <div>
          <nav className="flex items-center gap-1.5 text-xs text-slate-500 mb-1.5">
            <span>{t("common:nav.management")}</span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-400 rtl:rotate-180" />
            <Link
              to="/partners"
              className="hover:text-slate-800 transition-colors"
            >
              {t("settlements:page.partners_breadcrumb")}
            </Link>
            <ChevronRight className="w-3.5 h-3.5 text-slate-400 rtl:rotate-180" />
            <span className="text-slate-900 font-semibold">
              {t("common:nav.settlements")}
            </span>
          </nav>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                {t("common:nav.settlements")}
              </h1>
              <p className="text-xs text-slate-600 mt-0.5">
                {t("settlements:page.subtitle")}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleExportCsv}
                disabled={settlements.length === 0}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
              >
                <ArrowDownToLine className="w-3.5 h-3.5 text-slate-500" />
                <span>{t("settlements:actions.export_csv")}</span>
              </button>
            </div>
          </div>
        </div>

        {/* EXCEPTIONS BANNER */}
        {exceptions &&
          (exceptions.drafts_awaiting_approval > 0 ||
            exceptions.drafts_older_than_7_days > 0 ||
            exceptions.failed_deliveries > 0) && (
            <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3 text-amber-900 shadow-xs">
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="text-xs space-y-1">
                <p className="font-semibold text-slate-900">
                  {t("settlements:exceptions.title")}
                </p>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-slate-700">
                  {exceptions.drafts_awaiting_approval > 0 && (
                    <span>
                      •{" "}
                      <strong className="font-semibold">
                        {exceptions.drafts_awaiting_approval}
                      </strong>{" "}
                      {t("settlements:exceptions.drafts_awaiting")}
                    </span>
                  )}
                  {exceptions.drafts_older_than_7_days > 0 && (
                    <span className="text-amber-800 font-medium">
                      • <strong>{exceptions.drafts_older_than_7_days}</strong>{" "}
                      {t("settlements:exceptions.drafts_older")}
                    </span>
                  )}
                  {exceptions.failed_deliveries > 0 && (
                    <span className="text-red-700 font-medium">
                      • <strong>{exceptions.failed_deliveries}</strong>{" "}
                      {t("settlements:exceptions.failed")}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

        {/* ERROR BANNER */}
        {errorMsg && (
          <div className="p-4 bg-red-50 border border-red-200 text-red-800 rounded-xl text-xs flex items-center gap-3">
            <span>{errorMsg}</span>
          </div>
        )}

        {/* SUMMARY STAT CARDS */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium">
                {t("settlements:summary.loaded_total")}
              </span>
              <Wallet className="w-4 h-4 text-teal-600" />
            </div>
            <div className="text-2xl font-bold font-mono text-slate-900 tracking-tight">
              {formatMoney(totalSettlementAmount, lang)}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {t("settlements:summary.batches", {
                batches: settlements.length,
              })}
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium">
                {t("settlements:summary.selected_filter")}
              </span>
              <Filter className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-slate-900 tracking-tight">
              {statusTabLabel(activeTab)}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {selectedPeriod ? (
                <bdi dir="ltr">{selectedPeriod}</bdi>
              ) : (
                t("settlements:summary.all_periods")
              )}{" "}
              ·{" "}
              {selectedPartnerName ? (
                <bdi dir="ltr">{selectedPartnerName}</bdi>
              ) : selectedPartnerId ? (
                t("settlements:summary.selected_partner")
              ) : (
                t("settlements:summary.all_partners")
              )}
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium">
                {t("settlements:summary.pending_approvals")}
              </span>
              <Clock className="w-4 h-4 text-amber-500" />
            </div>
            <div className="text-2xl font-bold font-mono text-slate-900 tracking-tight">
              {exceptions?.drafts_awaiting_approval ?? 0}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {t("settlements:summary.pending_approvals_hint")}
            </div>
          </div>
        </div>

        {/* STATUS TABS & TOOLBAR */}
        <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-xs space-y-3">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            {/* Status tabs */}
            <div className="inline-flex p-1 bg-slate-100 rounded-lg self-start text-xs font-medium">
              {(
                [
                  "ALL",
                  "DRAFT",
                  "APPROVED",
                  "SENT",
                  "PAID",
                  "CANCELLED",
                ] as const
              ).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => handleTabChange(tab)}
                  className={`px-3 py-1 rounded-md transition-colors ${
                    activeTab === tab
                      ? "bg-white text-slate-900 shadow-xs font-semibold"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {statusTabLabel(tab)}
                </button>
              ))}
            </div>

            {/* Right filters */}
            <div className="flex flex-wrap items-center gap-2.5">
              {/* Search */}
              <div className="relative min-w-[200px]">
                <Search className="absolute start-2.5 top-2.5 text-slate-400 w-4 h-4 pointer-events-none" />
                <input
                  type="text"
                  placeholder={t("settlements:filters.search_placeholder")}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg ps-9 pe-3 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-teal-600 focus:border-teal-600 focus:bg-white transition-all"
                />
              </div>

              {/* Partner filter */}
              <div className="relative min-w-[160px]">
                <select
                  aria-label={t("settlements:filters.partner_aria")}
                  value={selectedPartnerId}
                  onChange={(e) => handlePartnerChange(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-700 focus:bg-white focus:outline-none focus:ring-1 focus:ring-teal-600 focus:border-teal-600"
                >
                  <option value="">
                    {t("settlements:filters.all_partners")}
                  </option>
                  {partners.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Period filter */}
              <div className="relative w-32">
                <input
                  type="text"
                  placeholder={t("settlements:filters.period_placeholder")}
                  value={selectedPeriod}
                  onChange={(e) => handlePeriodChange(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-700 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-teal-600 focus:border-teal-600"
                />
              </div>

              {/* Reset */}
              {(selectedPartnerId ||
                selectedPeriod ||
                searchTerm ||
                activeTab !== "ALL") && (
                <button
                  type="button"
                  onClick={resetFilters}
                  className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors"
                  title={t("settlements:filters.reset")}
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* SETTLEMENTS TABLE */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
          {isLoading ? (
            <div className="p-12 text-center text-xs text-slate-500">
              {t("settlements:states.loading")}
            </div>
          ) : filteredSettlements.length === 0 ? (
            <div className="p-12 text-center text-xs text-slate-500">
              {t("settlements:states.empty")}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-start border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50/80 border-b border-slate-200 text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
                    <th className="py-3 px-4 w-44 font-mono">
                      {t("settlements:table.id")}
                    </th>
                    <th className="py-3 px-4 w-52">
                      {t("settlements:table.partner")}
                    </th>
                    <th className="py-3 px-4 w-28 font-mono">
                      {t("settlements:table.period")}
                    </th>
                    <th className="py-3 px-4 w-36 text-end font-mono">
                      {t("common:labels.total")}
                    </th>
                    <th className="py-3 px-4 w-32 text-center">
                      {t("common:labels.status")}
                    </th>
                    <th className="py-3 px-4 w-40 text-slate-500">
                      {t("settlements:table.created_at")}
                    </th>
                    <th className="py-3 px-4 text-end w-28">
                      {t("common:labels.actions")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {filteredSettlements.map((settlement) => {
                    const partnerName = partnerMap.get(
                      settlement.referral_partner_id,
                    );

                    const statusStyles: Record<
                      SettlementStatus,
                      { badge: string; dot: string }
                    > = {
                      DRAFT: {
                        badge: "bg-amber-50 text-amber-700 border-amber-200",
                        dot: "bg-amber-600",
                      },
                      APPROVED: {
                        badge: "bg-blue-50 text-blue-700 border-blue-200",
                        dot: "bg-blue-600",
                      },
                      SENT: {
                        badge: "bg-purple-50 text-purple-700 border-purple-200",
                        dot: "bg-purple-600",
                      },
                      PAID: {
                        badge:
                          "bg-emerald-50 text-emerald-700 border-emerald-200",
                        dot: "bg-emerald-600",
                      },
                      CANCELLED: {
                        badge: "bg-slate-100 text-slate-600 border-slate-200",
                        dot: "bg-slate-400",
                      },
                    };

                    const style =
                      statusStyles[settlement.status] || statusStyles.DRAFT;

                    return (
                      <tr
                        key={settlement.id}
                        className="hover:bg-slate-50/70 transition-colors"
                        data-testid={`settlement-row-${settlement.id}`}
                      >
                        <td className="py-3.5 px-4 font-mono font-medium text-slate-900 whitespace-nowrap">
                          <bdi dir="ltr">{settlement.id.slice(0, 13)}...</bdi>
                        </td>
                        <td className="py-3.5 px-4 font-medium text-slate-900">
                          <Link
                            to={`/partners/${settlement.referral_partner_id}`}
                            className="hover:text-teal-700 transition-colors"
                          >
                            {partnerName ? (
                              partnerName
                            ) : (
                              <>
                                {t("settlements:table.partner")}{" "}
                                <bdi dir="ltr">
                                  {settlement.referral_partner_id.slice(0, 8)}
                                </bdi>
                              </>
                            )}
                          </Link>
                        </td>
                        <td className="py-3.5 px-4 font-mono text-slate-800 whitespace-nowrap">
                          <bdi dir="ltr">{settlement.period}</bdi>
                        </td>
                        <td className="py-3.5 px-4 text-end font-mono font-semibold text-slate-900 whitespace-nowrap">
                          {formatMoney(settlement.total, lang)}
                        </td>
                        <td className="py-3.5 px-4 text-center whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${style.badge}`}
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${style.dot}`}
                            ></span>
                            {/* Raw status code: shared with the ledger badge. */}
                            <bdi>
                              {statusLabel(
                                "settlement",
                                settlement.status.toLowerCase(),
                                (key) => t(`common:${key}`),
                              )}
                            </bdi>
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-slate-500 font-mono text-[11px] whitespace-nowrap">
                          <bdi dir="ltr">
                            {settlement.created_at.slice(0, 10)}
                          </bdi>
                        </td>
                        <td className="py-3.5 px-4 text-end">
                          <Link
                            to={`/settlements/${settlement.id}`}
                            className="inline-flex items-center gap-1 text-teal-700 hover:text-teal-900 font-semibold"
                          >
                            <span>{t("settlements:actions.detail")}</span>
                            <ChevronRight className="w-3.5 h-3.5 rtl:rotate-180" />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* TABLE FOOTER / PAGINATION */}
          <div className="p-4 bg-slate-50/90 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
            <div className="text-slate-500 font-mono text-[11px]">
              {t("settlements:states.showing", {
                settlements: filteredSettlements.length,
              })}
            </div>

            {nextCursor && (
              <button
                type="button"
                disabled={isLoadingMore}
                onClick={() => fetchSettlements(nextCursor)}
                className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg text-xs font-medium shadow-xs transition-colors disabled:opacity-50"
              >
                {isLoadingMore
                  ? t("settlements:actions.loading")
                  : t("settlements:actions.load_next")}
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};
