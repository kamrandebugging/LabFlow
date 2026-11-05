import React, { useCallback, useEffect, useMemo, useState } from "react";
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
import { PartnerApiError, partnersService } from "./partnersService";
import type {
  ReferralPartner,
  Settlement,
  SettlementExceptionsData,
  SettlementListResponse,
  SettlementStatus,
} from "./types";

export const SettlementsScreen: React.FC = () => {
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
          setErrorMsg(err.message);
        } else if (err instanceof Error) {
          setErrorMsg(err.message);
        } else {
          setErrorMsg("Failed to load settlements.");
        }
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [activeTab, selectedPartnerId, selectedPeriod, isAuthorized],
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

  if (!isAuthorized) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6 text-xs text-slate-600">
        <div className="bg-white border border-slate-200 rounded-xl p-8 max-w-md text-center shadow-xs">
          <AlertTriangle className="w-8 h-8 text-amber-600 mx-auto mb-3" />
          <h2 className="text-sm font-bold text-slate-900 mb-1">
            Access Restricted
          </h2>
          <p className="text-slate-600 mb-4">
            Only the Lab Owner and Manager can view monthly settlements.
          </p>
          <Link
            to="/partners"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-teal-600 text-white rounded-lg font-semibold hover:bg-teal-700 transition-colors"
          >
            <span>Back to Partners</span>
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
            <span>Management</span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
            <Link
              to="/partners"
              className="hover:text-slate-800 transition-colors"
            >
              Partners
            </Link>
            <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-900 font-semibold">Settlements</span>
          </nav>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                Settlements
              </h1>
              <p className="text-xs text-slate-600 mt-0.5">
                Monthly revenue-share settlements with referral partners
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
                <span>Export CSV</span>
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
                  Settlement Exceptions Detected
                </p>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-slate-700">
                  {exceptions.drafts_awaiting_approval > 0 && (
                    <span>
                      •{" "}
                      <strong className="font-semibold">
                        {exceptions.drafts_awaiting_approval}
                      </strong>{" "}
                      draft(s) awaiting approval
                    </span>
                  )}
                  {exceptions.drafts_older_than_7_days > 0 && (
                    <span className="text-amber-800 font-medium">
                      • <strong>{exceptions.drafts_older_than_7_days}</strong>{" "}
                      draft(s) older than 7 days
                    </span>
                  )}
                  {exceptions.failed_deliveries > 0 && (
                    <span className="text-red-700 font-medium">
                      • <strong>{exceptions.failed_deliveries}</strong> failed
                      delivery notification(s)
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
              <span className="text-xs font-medium">Loaded Total</span>
              <Wallet className="w-4 h-4 text-teal-600" />
            </div>
            <div className="text-2xl font-bold font-mono text-slate-900 tracking-tight">
              PKR {totalSettlementAmount}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Across {settlements.length} settlement batches
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium">Selected Filter</span>
              <Filter className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-slate-900 tracking-tight">
              {activeTab}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {selectedPeriod || "All periods"} ·{" "}
              {selectedPartnerId
                ? partnerMap.get(selectedPartnerId) || "Selected partner"
                : "All partners"}
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium">Pending Approvals</span>
              <Clock className="w-4 h-4 text-amber-500" />
            </div>
            <div className="text-2xl font-bold font-mono text-slate-900 tracking-tight">
              {exceptions?.drafts_awaiting_approval ?? 0}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Draft settlements awaiting sign-off
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
                  {tab === "ALL"
                    ? "All"
                    : tab.charAt(0) + tab.slice(1).toLowerCase()}
                </button>
              ))}
            </div>

            {/* Right filters */}
            <div className="flex flex-wrap items-center gap-2.5">
              {/* Search */}
              <div className="relative min-w-[200px]">
                <Search className="absolute left-2.5 top-2.5 text-slate-400 w-4 h-4 pointer-events-none" />
                <input
                  type="text"
                  placeholder="Search partner or settlement..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-teal-600 focus:border-teal-600 focus:bg-white transition-all"
                />
              </div>

              {/* Partner filter */}
              <div className="relative min-w-[160px]">
                <select
                  aria-label="Filter by Partner"
                  value={selectedPartnerId}
                  onChange={(e) => handlePartnerChange(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-700 focus:bg-white focus:outline-none focus:ring-1 focus:ring-teal-600 focus:border-teal-600"
                >
                  <option value="">All partners</option>
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
                  placeholder="YYYY-MM"
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
                  title="Reset filters"
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
              Loading settlements...
            </div>
          ) : filteredSettlements.length === 0 ? (
            <div className="p-12 text-center text-xs text-slate-500">
              No settlements found matching the criteria.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50/80 border-b border-slate-200 text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
                    <th className="py-3 px-4 w-44 font-mono">Settlement ID</th>
                    <th className="py-3 px-4 w-52">Partner</th>
                    <th className="py-3 px-4 w-28 font-mono">Period</th>
                    <th className="py-3 px-4 w-36 text-right font-mono">
                      Total
                    </th>
                    <th className="py-3 px-4 w-32 text-center">Status</th>
                    <th className="py-3 px-4 w-40 text-slate-500">
                      Created At
                    </th>
                    <th className="py-3 px-4 text-right w-28">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {filteredSettlements.map((settlement) => {
                    const partnerName =
                      partnerMap.get(settlement.referral_partner_id) ||
                      `Partner ${settlement.referral_partner_id.slice(0, 8)}`;

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
                          {settlement.id.slice(0, 13)}...
                        </td>
                        <td className="py-3.5 px-4 font-medium text-slate-900">
                          <Link
                            to={`/partners/${settlement.referral_partner_id}`}
                            className="hover:text-teal-700 transition-colors"
                          >
                            {partnerName}
                          </Link>
                        </td>
                        <td className="py-3.5 px-4 font-mono text-slate-800 whitespace-nowrap">
                          {settlement.period}
                        </td>
                        <td className="py-3.5 px-4 text-right font-mono font-semibold text-slate-900 whitespace-nowrap">
                          PKR {settlement.total}
                        </td>
                        <td className="py-3.5 px-4 text-center whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${style.badge}`}
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${style.dot}`}
                            ></span>
                            <span>{settlement.status}</span>
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-slate-500 font-mono text-[11px] whitespace-nowrap">
                          {settlement.created_at.slice(0, 10)}
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <Link
                            to={`/settlements/${settlement.id}`}
                            className="inline-flex items-center gap-1 text-teal-700 hover:text-teal-900 font-semibold"
                          >
                            <span>Detail</span>
                            <ChevronRight className="w-3.5 h-3.5" />
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
              Showing {filteredSettlements.length} settlements
            </div>

            {nextCursor && (
              <button
                type="button"
                disabled={isLoadingMore}
                onClick={() => fetchSettlements(nextCursor)}
                className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg text-xs font-medium shadow-xs transition-colors disabled:opacity-50"
              >
                {isLoadingMore ? "Loading..." : "Load next 50 settlements"}
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};
