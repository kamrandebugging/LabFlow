import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowDownToLine,
  Calendar,
  ChevronRight,
  Lock,
  Receipt,
  Search,
  ShieldCheck,
  Wallet,
  X,
} from "lucide-react";
import { PartnerApiError, partnersService } from "./partnersService";
import type {
  ReferralPartner,
  ShareLedgerEntry,
  ShareLedgerResponse,
} from "./types";

export const LedgerScreen: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  // URL query params
  const initialPartnerId = searchParams.get("partner_id") || "";
  const initialPeriod = searchParams.get("period") || "";
  const initialRuleId = searchParams.get("rule_id") || "";

  // Data state
  const [entries, setEntries] = useState<ShareLedgerEntry[]>([]);
  const [totals, setTotals] = useState<{ count: number; amount: string }>({
    count: 0,
    amount: "0.00",
  });
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [partners, setPartners] = useState<ReferralPartner[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Filter state
  const [selectedPartnerId, setSelectedPartnerId] =
    useState<string>(initialPartnerId);
  const [selectedPeriod, setSelectedPeriod] = useState<string>(initialPeriod);
  const [searchTerm, setSearchTerm] = useState<string>("");

  // Load partners list for dropdown
  useEffect(() => {
    let isMounted = true;
    partnersService
      .getPartners()
      .then((data) => {
        if (isMounted) setPartners(data);
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, []);

  const fetchLedger = useCallback(
    async (cursor?: string): Promise<void> => {
      const isInitial = !cursor;
      if (isInitial) {
        setIsLoading(true);
        setErrorMsg(null);
      } else {
        setIsLoadingMore(true);
      }

      try {
        const response: ShareLedgerResponse =
          await partnersService.getShareLedger({
            partner_id: selectedPartnerId || undefined,
            period: selectedPeriod || undefined,
            rule_id: initialRuleId || undefined,
            cursor: cursor || undefined,
            limit: 50,
          });

        if (isInitial) {
          setEntries(response.results);
          setTotals(response.totals);
        } else {
          setEntries((prev) => [...prev, ...response.results]);
        }
        setNextCursor(response.next_cursor);
      } catch (err: unknown) {
        if (err instanceof PartnerApiError) {
          setErrorMsg(err.message);
        } else if (err instanceof Error) {
          setErrorMsg(err.message);
        } else {
          setErrorMsg("Failed to load share ledger.");
        }
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [selectedPartnerId, selectedPeriod, initialRuleId],
  );

  useEffect(() => {
    fetchLedger();
  }, [fetchLedger]);

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
    setSelectedPartnerId("");
    setSelectedPeriod("");
    setSearchTerm("");
    setSearchParams(new URLSearchParams());
  };

  const handleExportCsv = () => {
    if (entries.length === 0) return;
    const headers = [
      "ID",
      "Created At",
      "Payment ID",
      "Partner Name",
      "Basis Amount (PKR)",
      "Percent Applied",
      "Commission (PKR)",
      "Period",
      "Settlement Status",
      "Settlement Period",
    ];

    const rows = entries.map((e) => [
      e.id,
      e.created_at,
      e.payment_id,
      `"${e.referral_partner_name.replace(/"/g, '""')}"`,
      e.basis_amount,
      e.percent_applied,
      e.amount,
      e.period,
      e.settlement ? e.settlement.status : "UNSETTLED",
      e.settlement ? e.settlement.period : "",
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute(
      "download",
      `revenue-share-ledger-${selectedPeriod || "all"}-${Date.now()}.csv`,
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Client-side search filtering on loaded entries
  const filteredEntries = useMemo(() => {
    if (!searchTerm.trim()) return entries;
    const term = searchTerm.toLowerCase();
    return entries.filter(
      (e) =>
        e.payment_id.toLowerCase().includes(term) ||
        e.referral_partner_name.toLowerCase().includes(term) ||
        e.id.toLowerCase().includes(term),
    );
  }, [entries, searchTerm]);

  // Derived settled vs pending
  const settledCount = useMemo(
    () => entries.filter((e) => e.settlement !== null).length,
    [entries],
  );
  const unsettledCount = useMemo(
    () => entries.filter((e) => e.settlement === null).length,
    [entries],
  );

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
            <span className="text-slate-900 font-semibold">Share Ledger</span>
          </nav>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                Revenue Share Ledger
              </h1>
              <p className="text-xs text-slate-600 mt-0.5">
                Every revenue-share entry, recorded per payment
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="px-2.5 py-1 rounded-md bg-slate-200/70 border border-slate-300 text-slate-700 text-xs flex items-center gap-1.5 font-medium">
                <Lock className="w-3.5 h-3.5" />
                <span>Audit Lock: Active</span>
              </div>
              <button
                type="button"
                onClick={handleExportCsv}
                disabled={entries.length === 0}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
              >
                <ArrowDownToLine className="w-3.5 h-3.5 text-slate-500" />
                <span>Export CSV</span>
              </button>
            </div>
          </div>
        </div>

        {/* IMMUTABLE LEDGER COMPLIANCE BANNER */}
        <div className="p-3.5 bg-sky-50/80 border border-sky-200 rounded-xl flex items-start gap-3 text-sky-900 shadow-xs">
          <ShieldCheck className="w-5 h-5 text-sky-700 shrink-0 mt-0.5" />
          <div className="text-xs space-y-0.5">
            <p className="font-semibold text-slate-900">
              Append-only — entries cannot be edited or deleted.
            </p>
            <p className="text-slate-600">
              Immutable financial audit log complying with multi-tenant
              laboratory fiscal governance.
            </p>
          </div>
        </div>

        {/* ERROR BANNER */}
        {errorMsg && (
          <div className="p-4 bg-red-50 border border-red-200 text-red-800 rounded-xl text-xs flex items-center gap-3">
            <span>{errorMsg}</span>
          </div>
        )}

        {/* STAT BENTO CARDS */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium">Recorded Shares</span>
              <Receipt className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-slate-900 tracking-tight">
              PKR {totals.amount}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {totals.count} total ledger entries
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium">Filtered Period</span>
              <Calendar className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-slate-900 tracking-tight">
              {selectedPeriod || "All periods"}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {selectedPartnerId
                ? partners.find((p) => p.id === selectedPartnerId)?.name ||
                  "Partner filtered"
                : "All referral partners"}
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-medium">Settlement Status</span>
              <Wallet className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-slate-900 tracking-tight">
              {unsettledCount} Unsettled
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {settledCount} entries linked to settlements
            </div>
          </div>
        </div>

        {/* TOOLBAR: SEARCH & FILTERS */}
        <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-xs flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5 flex-1 min-w-[300px]">
            {/* Search */}
            <div className="relative flex-1 min-w-[220px]">
              <Search className="absolute left-2.5 top-2.5 text-slate-400 w-4 h-4 pointer-events-none" />
              <input
                type="text"
                placeholder="Search invoice ref, partner or entry ID..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-teal-600 focus:border-teal-600 focus:bg-white transition-all"
              />
            </div>

            {/* Partner dropdown */}
            <div className="relative min-w-[180px]">
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

            {/* Period input */}
            <div className="relative w-36">
              <input
                type="text"
                placeholder="YYYY-MM"
                value={selectedPeriod}
                onChange={(e) => handlePeriodChange(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-700 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-teal-600 focus:border-teal-600"
              />
            </div>

            {/* Reset button */}
            {(selectedPartnerId || selectedPeriod || searchTerm) && (
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

        {/* LEDGER TABLE */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
          {isLoading ? (
            <div className="p-12 text-center text-xs text-slate-500">
              Loading revenue share ledger...
            </div>
          ) : filteredEntries.length === 0 ? (
            <div className="p-12 text-center text-xs text-slate-500">
              No ledger entries found for this selection.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50/80 border-b border-slate-200 text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
                    <th className="py-3 px-4 w-40">Date / Time</th>
                    <th className="py-3 px-4 w-36 font-mono">Payment Ref</th>
                    <th className="py-3 px-4 w-48">Partner</th>
                    <th className="py-3 px-4 w-32 text-right font-mono">
                      Basis Amount
                    </th>
                    <th className="py-3 px-4 w-24 text-right font-mono">
                      Rate
                    </th>
                    <th className="py-3 px-4 w-36 text-right font-mono">
                      Commission
                    </th>
                    <th className="py-3 px-4 w-36 text-center">Settlement</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {filteredEntries.map((entry) => {
                    const formattedDate = new Date(entry.created_at)
                      .toLocaleString("en-GB", {
                        day: "2-digit",
                        month: "short",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                      .replace(",", "");

                    return (
                      <tr
                        key={entry.id}
                        className="hover:bg-slate-50/70 transition-colors"
                        data-testid={`ledger-row-${entry.id}`}
                      >
                        <td className="py-3.5 px-4 text-slate-600 whitespace-nowrap font-mono text-[11px]">
                          {formattedDate}
                        </td>
                        <td className="py-3.5 px-4 font-mono font-medium text-slate-900 whitespace-nowrap">
                          {entry.payment_id}
                        </td>
                        <td className="py-3.5 px-4 font-medium text-slate-900">
                          <Link
                            to={`/partners/${entry.referral_partner_id}`}
                            className="hover:text-teal-700 transition-colors"
                          >
                            {entry.referral_partner_name}
                          </Link>
                        </td>
                        <td className="py-3.5 px-4 text-right font-mono text-slate-900 whitespace-nowrap">
                          PKR {entry.basis_amount}
                        </td>
                        <td className="py-3.5 px-4 text-right font-mono text-slate-600 whitespace-nowrap">
                          {entry.percent_applied}%
                        </td>
                        <td className="py-3.5 px-4 text-right font-mono font-semibold text-slate-900 whitespace-nowrap">
                          PKR {entry.amount}
                        </td>
                        <td className="py-3.5 px-4 text-center whitespace-nowrap">
                          {entry.settlement ? (
                            <Link
                              to={`/settlements/${entry.settlement.id}`}
                              className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-teal-50 text-teal-700 border border-teal-200 hover:bg-teal-100 transition-colors"
                            >
                              <span className="w-1.5 h-1.5 rounded-full bg-teal-600"></span>
                              <span>{entry.settlement.status}</span>
                            </Link>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200">
                              <span className="w-1.5 h-1.5 rounded-full bg-amber-600"></span>
                              <span>Unsettled</span>
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* TABLE FOOTER / CURSOR PAGINATION */}
          <div className="p-4 bg-slate-50/90 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
            <div className="text-slate-500 font-mono text-[11px]">
              Showing {filteredEntries.length} of {totals.count} entries
            </div>

            {nextCursor && (
              <button
                type="button"
                disabled={isLoadingMore}
                onClick={() => fetchLedger(nextCursor)}
                className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg text-xs font-medium shadow-xs transition-colors disabled:opacity-50"
              >
                {isLoadingMore ? "Loading..." : "Load next 50 entries"}
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};
