import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  FlaskConical,
  Plus,
  Printer,
  RefreshCw,
  Search,
  Truck,
  X,
  AlertTriangle,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { sampleService } from "./sampleService";
import { useAuthStore } from "../auth/authStore";
import { settingsService } from "../settings/settingsService";
import type { Branch } from "../settings/types";
import type {
  AwaitingCollectionItem,
  SampleSummary,
  SampleTransfer,
  TransferDirection,
  TransferExceptionsResponse,
} from "./types";
import {
  SampleKpiRow,
  SampleQueueTabs,
  SampleStatusPill,
  SampleBulkBar,
} from "./components";
import styles from "./SampleAccessioningListScreen.module.css";

export interface SampleAccessioningListScreenProps {
  onSelectSample?: (id: string) => void;
  onCollectNew?: () => void;
  onPrintLabels?: (accessionIds: string[]) => void;
  service?: typeof sampleService;
}

export function SampleAccessioningListScreen({
  onSelectSample,
  onCollectNew,
  onPrintLabels,
  service = sampleService,
}: SampleAccessioningListScreenProps): JSX.Element {
  const { t } = useTranslation(["samples", "common"]);
  const user = useAuthStore((s) => s.user);
  const userRole = (user?.role || "").toLowerCase();
  const canCollect =
    userRole === "owner" ||
    userRole === "manager" ||
    userRole === "reception" ||
    userRole === "technician";
  const isManagerOrOwner = userRole === "owner" || userRole === "manager";

  // Tab State
  const [activeTab, setActiveTab] = useState<string>("awaiting_collection");
  const [transferDirection, setTransferDirection] =
    useState<TransferDirection>("all");
  const [showExceptions, setShowExceptions] = useState(false);
  const [exceptionsData, setExceptionsData] =
    useState<TransferExceptionsResponse | null>(null);

  // Data States
  const [samples, setSamples] = useState<SampleSummary[]>([]);
  const [summarySamples, setSummarySamples] = useState<SampleSummary[]>([]);
  const [summaryTotal, setSummaryTotal] = useState(0);
  const [awaitingItems, setAwaitingItems] = useState<AwaitingCollectionItem[]>(
    [],
  );
  const [awaitingTotalCount, setAwaitingTotalCount] = useState(0);
  const [transfers, setTransfers] = useState<SampleTransfer[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);

  // Selection & UI States
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [selectedBranch, setSelectedBranch] = useState<string>("all");
  const [sortOrder, setSortOrder] = useState<"oldest" | "newest">("oldest");

  // Transfer Action Modals
  const [markLostId, setMarkLostId] = useState<string | null>(null);
  const [markLostNote, setMarkLostNote] = useState("");
  const [transferActionLoading, setTransferActionLoading] = useState(false);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchInputId = useId();
  const statusSelectId = useId();
  const branchSelectId = useId();

  // Shortcut "/" focuses search input on this screen
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key === "/" &&
        document.activeElement?.tagName !== "INPUT" &&
        document.activeElement?.tagName !== "TEXTAREA" &&
        document.activeElement?.tagName !== "SELECT"
      ) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Fetch branches once
  useEffect(() => {
    let active = true;
    void settingsService
      .getBranches(false)
      .then((list) => {
        if (active && Array.isArray(list)) setBranches(list);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  /**
   * Live aggregate bootstrap.
   *
   * The old screen fetched only the active tab, so "All samples" and three
   * KPI cards stayed at zero until the operator clicked the tab. Every queue
   * and every counter is now resolved from the live API on mount, before any
   * tab interaction, and refreshed together after custody actions.
   */
  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const [samplesResult, awaitingResult, transfersResult] =
        await Promise.allSettled([
          service.listSamples({ limit: 200, order: sortOrder }),
          service.listAwaitingCollection(),
          service.listTransfers({ status: "open", direction: "all" }),
        ]);

      if (samplesResult.status === "fulfilled") {
        setSummarySamples(samplesResult.value.results || []);
        setSummaryTotal(samplesResult.value.total ?? 0);
      } else {
        setErrorMessage(messageForError(samplesResult.reason, t));
      }

      if (awaitingResult.status === "fulfilled") {
        setAwaitingItems(awaitingResult.value.results || []);
        setAwaitingTotalCount(
          awaitingResult.value.total ?? awaitingResult.value.results.length,
        );
      } else {
        setErrorMessage(messageForError(awaitingResult.reason, t));
      }

      if (transfersResult.status === "fulfilled") {
        setTransfers(transfersResult.value.results || []);
      } else {
        setErrorMessage(messageForError(transfersResult.reason, t));
      }
    } finally {
      setSummaryLoading(false);
    }
  }, [service, sortOrder, t]);

  // Fetch filtered samples for the standard queue
  const loadSamples = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const res = await service.listSamples({
        q: searchQuery.trim() || undefined,
        status: selectedStatus !== "all" ? selectedStatus : undefined,
        branch_id: selectedBranch !== "all" ? selectedBranch : undefined,
        order: sortOrder,
      });
      setSamples(res.results || []);
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, selectedStatus, selectedBranch, sortOrder, service, t]);

  // Fetch transfers for the transfers queue
  const loadTransfers = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const res = await service.listTransfers({
        status: "open",
        direction: transferDirection,
      });
      setTransfers(res.results || []);
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsLoading(false);
    }
  }, [service, transferDirection, t]);

  // Load exceptions if toggled
  const loadExceptions = useCallback(async () => {
    if (!isManagerOrOwner) return;
    try {
      const data = await service.getTransferExceptions();
      setExceptionsData(data);
    } catch {
      // Ignored: the oversight panel is optional.
    }
  }, [service, isManagerOrOwner]);

  // Bootstrap all live queues and KPI aggregates on first paint.
  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  // Filtered sample list refreshes whenever the operator changes a filter.
  useEffect(() => {
    void loadSamples();
  }, [loadSamples]);

  // Transfer direction is server-side; reload only when that queue is used.
  useEffect(() => {
    if (activeTab === "transfers") {
      void loadTransfers();
      if (showExceptions) void loadExceptions();
    }
  }, [activeTab, loadTransfers, showExceptions, loadExceptions]);

  // Checkbox Selection
  const toggleSelectAll = () => {
    if (selectedIds.size === samples.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(samples.map((s) => s.id)));
    }
  };

  const toggleSelectOne = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBatchPrint = () => {
    if (selectedIds.size === 0) return;
    const ids = Array.from(selectedIds);
    if (onPrintLabels) {
      onPrintLabels(ids);
    } else if (onSelectSample && ids.length === 1 && ids[0]) {
      onSelectSample(ids[0]);
    }
  };

  const refreshAll = useCallback(async () => {
    await Promise.allSettled([loadSummary(), loadSamples()]);
  }, [loadSummary, loadSamples]);

  // Transfer action handlers
  const handleReceiveTransfer = async (
    transferId: string,
    e: React.MouseEvent,
  ) => {
    e.stopPropagation();
    try {
      setTransferActionLoading(true);
      await service.receiveTransfer(transferId);
      await refreshAll();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setTransferActionLoading(false);
    }
  };

  const handleCancelTransfer = async (
    transferId: string,
    e: React.MouseEvent,
  ) => {
    e.stopPropagation();
    if (!window.confirm(t("samples:list_page.cancel_transfer_confirm"))) {
      return;
    }
    try {
      setTransferActionLoading(true);
      await service.cancelTransfer(transferId);
      await refreshAll();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setTransferActionLoading(false);
    }
  };

  const handleMarkLostSubmit = async () => {
    if (!markLostId || !markLostNote.trim()) return;
    try {
      setTransferActionLoading(true);
      await service.markLostTransfer(markLostId, markLostNote.trim());
      setMarkLostId(null);
      setMarkLostNote("");
      await refreshAll();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setTransferActionLoading(false);
    }
  };

  // KPIs are computed from the unfiltered live aggregate, so they never
  // collapse to zero while a different queue is active.
  const awaitingTotal = awaitingTotalCount;
  const collectedCount = summarySamples.filter(
    (s) => s.status === "collected",
  ).length;
  const inProcessCount = summarySamples.filter(
    (s) => s.status === "in_process",
  ).length;
  const readyCount = summarySamples.filter((s) => s.status === "ready").length;

  const kpiItems = [
    {
      id: "awaiting",
      label: t("samples:kpi.awaiting_collection"),
      value: awaitingTotal,
      subtitle: t("samples:kpi.awaiting_sub"),
    },
    {
      id: "collected",
      label: t("samples:kpi.collected_today"),
      value: collectedCount,
      subtitle: t("samples:kpi.collected_sub"),
    },
    {
      id: "in_process",
      label: t("samples:kpi.in_process"),
      value: inProcessCount,
      subtitle: t("samples:kpi.in_process_sub"),
    },
    {
      id: "ready",
      label: t("samples:kpi.ready_reported"),
      value: readyCount,
      subtitle: t("samples:kpi.ready_sub"),
    },
  ];

  // Tab Definitions
  const tabs = [
    {
      id: "awaiting_collection",
      label: t("samples:tabs.awaiting_collection"),
      count: awaitingTotal,
    },
    {
      id: "all",
      label: t("samples:tabs.all_samples"),
      count: summaryTotal,
    },
    {
      id: "transfers",
      label: t("samples:tabs.transfers"),
      count: transfers.length,
    },
  ];

  // Filtered Awaiting Items
  const filteredAwaiting = awaitingItems.filter((item) => {
    if (selectedBranch !== "all" && item.branch_id !== selectedBranch)
      return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      const matchName = item.patient_name.toLowerCase().includes(q);
      const matchMrn = item.patient_mrn.toLowerCase().includes(q);
      const matchDesc = item.description?.toLowerCase().includes(q);
      if (!matchName && !matchMrn && !matchDesc) return false;
    }
    return true;
  });

  return (
    <div className={styles.pageContainer}>
      {/* 1. Header Area */}
      <header className={styles.headerRow}>
        <div className={styles.titleArea}>
          <h1 className={styles.pageTitle}>
            {t("samples:page.samples_title")}
          </h1>
          <p className={styles.pageSubtitle}>
            {t("samples:page.samples_subtitle")}
          </p>
        </div>
        <div className={styles.headerActions}>
          <button
            type="button"
            onClick={handleBatchPrint}
            disabled={selectedIds.size === 0}
            className={styles.outlinePill}
          >
            <Printer className="w-4 h-4" />
            <span>
              {t("samples:page.print_labels", { n: selectedIds.size })}
            </span>
          </button>
          {onCollectNew && canCollect && (
            <button
              type="button"
              onClick={onCollectNew}
              className={styles.primaryBlackPill}
            >
              <Plus className="w-4 h-4" />
              <span>{t("samples:page.collect_sample")}</span>
            </button>
          )}
        </div>
      </header>

      {/* 2. Real KPI Row */}
      <SampleKpiRow items={kpiItems} />

      {/* 3. Error Banner */}
      {errorMessage && (
        <div
          role="alert"
          className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center justify-between"
        >
          <span>{errorMessage}</span>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            aria-label={t("samples:page.dismiss")}
            className="text-red-500 hover:text-red-700"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* 4. Queue Tabs */}
      <SampleQueueTabs
        tabs={tabs}
        activeTab={activeTab}
        onSelectTab={(tabId) => {
          setActiveTab(tabId);
          setSelectedIds(new Set());
          setErrorMessage(null);
        }}
      />

      {/* 5. Filters and Search */}
      <div className={styles.filterCard}>
        <div className={styles.filterGroup}>
          <div className={styles.searchBox}>
            <Search className={styles.searchIcon} />
            <input
              ref={searchInputRef}
              id={searchInputId}
              type="text"
              placeholder={
                activeTab === "awaiting_collection"
                  ? t("samples:list_page.search_awaiting")
                  : t("samples:list_page.search_all")
              }
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={styles.searchInput}
            />
            <span className={styles.shortcutHint} aria-hidden="true">
              /
            </span>
          </div>

          {activeTab === "all" && (
            <select
              id={statusSelectId}
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className={styles.selectDropdown}
            >
              <option value="all">{t("samples:list_page.all_statuses")}</option>
              <option value="collected">
                {t("common:status.sample.collected")}
              </option>
              <option value="received">
                {t("common:status.sample.received")}
              </option>
              <option value="in_process">
                {t("common:status.sample.in_process")}
              </option>
              <option value="ready">
                {t("samples:status.ready_reported")}
              </option>
              <option value="rejected">
                {t("common:status.sample.rejected")}
              </option>
              <option value="cancelled">
                {t("common:status.sample.cancelled")}
              </option>
            </select>
          )}

          {activeTab === "transfers" && (
            <select
              value={transferDirection}
              onChange={(e) =>
                setTransferDirection(e.target.value as TransferDirection)
              }
              className={styles.selectDropdown}
            >
              <option value="all">
                {t("samples:list_page.all_directions")}
              </option>
              <option value="incoming">
                {t("samples:list_page.incoming")}
              </option>
              <option value="outgoing">
                {t("samples:list_page.outgoing")}
              </option>
            </select>
          )}

          <select
            id={branchSelectId}
            value={selectedBranch}
            onChange={(e) => setSelectedBranch(e.target.value)}
            className={styles.selectDropdown}
          >
            <option value="all">{t("samples:list_page.all_branches")}</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>

          <select
            value={sortOrder}
            onChange={(e) =>
              setSortOrder(e.target.value as "oldest" | "newest")
            }
            className={styles.selectDropdown}
          >
            <option value="oldest">
              {t("samples:list_page.oldest_first")}
            </option>
            <option value="newest">
              {t("samples:list_page.newest_first")}
            </option>
          </select>

          <button
            type="button"
            onClick={() => void refreshAll()}
            aria-label={t("samples:page.refresh")}
            className={styles.outlinePill}
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${
                isLoading || summaryLoading ? "animate-spin" : ""
              }`}
            />
          </button>
        </div>

        {activeTab === "transfers" && isManagerOrOwner && (
          <button
            type="button"
            onClick={() => {
              setShowExceptions(!showExceptions);
              if (!showExceptions) void loadExceptions();
            }}
            className={styles.outlinePill}
          >
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
            <span>
              {showExceptions
                ? t("samples:list_page.hide_exceptions")
                : t("samples:list_page.transfer_exceptions")}
            </span>
          </button>
        )}
      </div>

      {/* Transfer Exceptions Oversight View (Phase 2.8) */}
      {activeTab === "transfers" && showExceptions && exceptionsData && (
        <div className={styles.exceptionPanel}>
          <h2 className={styles.exceptionTitle}>
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <span>{t("samples:list_page.exceptions_title")}</span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div className={styles.exceptionCard}>
              <span className={styles.exceptionLabel}>
                {t("samples:list_page.late_transfers")}
              </span>
              <span className={styles.exceptionValue}>
                {exceptionsData.late?.total || 0}
              </span>
            </div>
            <div className={styles.exceptionCard}>
              <span className={styles.exceptionLabel}>
                {t("samples:list_page.lost_reports")}
              </span>
              <span className={styles.exceptionValue}>
                {exceptionsData.lost?.total || 0}
              </span>
            </div>
            <div className={styles.exceptionCard}>
              <span className={styles.exceptionLabel}>
                {t("samples:list_page.active_routes")}
              </span>
              <span className={styles.exceptionValue}>
                {exceptionsData.route_health?.routes?.length || 0}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 6. Main Tables Card */}
      <div className={styles.tableCard}>
        {/* TAB 1: Awaiting Collection */}
        {activeTab === "awaiting_collection" && (
          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead className={styles.tableHead}>
                <tr>
                  <th className={styles.th}>
                    {t("samples:list_page.col_patient")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_ordered_tests")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_branch")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_ordered_at")}
                  </th>
                  <th className={styles.thRight}>
                    {t("samples:list_page.col_action")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading && filteredAwaiting.length === 0 ? (
                  Array.from({ length: 4 }).map((_, i) => (
                    <tr key={i} className={styles.skeletonRow}>
                      <td colSpan={5} className="py-4 px-4">
                        <div className={styles.skeletonBar} />
                      </td>
                    </tr>
                  ))
                ) : filteredAwaiting.length === 0 ? (
                  <tr>
                    <td colSpan={5}>
                      <div className={styles.emptyCard}>
                        <div className={styles.emptyIconCircle}>
                          <FlaskConical className="w-6 h-6" />
                        </div>
                        <h2 className={styles.emptyTitle}>
                          {t("samples:list_page.no_awaiting_title")}
                        </h2>
                        <p className={styles.emptySubtitle}>
                          {t("samples:list_page.no_awaiting_body")}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filteredAwaiting.map((item) => (
                    <tr
                      key={item.invoice_item_id}
                      className={styles.tableRow}
                      onClick={() => {
                        if (canCollect) {
                          window.location.href = `/samples/collect/step1?invoice_id=${item.invoice_id}`;
                        }
                      }}
                    >
                      <td className={styles.td}>
                        <div className={styles.patientName}>
                          {item.patient_name}
                        </div>
                        <div className={styles.patientMrn}>
                          <bdi dir="ltr">{item.patient_mrn}</bdi>
                        </div>
                      </td>
                      <td className={styles.td}>
                        <span className={styles.testChip}>
                          {item.description ||
                            item.test_name ||
                            t("samples:list_page.diagnostic_test")}
                        </span>
                      </td>
                      <td className={styles.td}>{item.branch_name}</td>
                      <td className={styles.td}>
                        <span className="font-mono text-xs">
                          <bdi dir="ltr">
                            {new Date(item.ordered_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                              hour12: false,
                            })}
                          </bdi>
                        </span>
                      </td>
                      <td className={styles.tdRight}>
                        {canCollect ? (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              window.location.href = `/samples/collect/step1?invoice_id=${item.invoice_id}`;
                            }}
                            className={styles.primaryBlackPill}
                          >
                            <span>{t("samples:page.collect_cta")}</span>
                          </button>
                        ) : (
                          <span className="text-slate-400 text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* TAB 2: Transfers Queue */}
        {activeTab === "transfers" && (
          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead className={styles.tableHead}>
                <tr>
                  <th className={styles.th}>
                    {t("samples:list_page.col_accession")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_patient")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_route")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_dispatched")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_status")}
                  </th>
                  <th className={styles.thRight}>
                    {t("samples:list_page.col_actions")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading && transfers.length === 0 ? (
                  Array.from({ length: 4 }).map((_, i) => (
                    <tr key={i} className={styles.skeletonRow}>
                      <td colSpan={6} className="py-4 px-4">
                        <div className={styles.skeletonBar} />
                      </td>
                    </tr>
                  ))
                ) : transfers.length === 0 ? (
                  <tr>
                    <td colSpan={6}>
                      <div className={styles.emptyCard}>
                        <div className={styles.emptyIconCircle}>
                          <Truck className="w-6 h-6" />
                        </div>
                        <h2 className={styles.emptyTitle}>
                          {t("samples:list_page.no_transfers_title")}
                        </h2>
                        <p className={styles.emptySubtitle}>
                          {t("samples:list_page.no_transfers_body")}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  transfers.map((tItem) => {
                    return (
                      <tr
                        key={tItem.id}
                        className={styles.tableRow}
                        onClick={() => onSelectSample?.(tItem.sample_id)}
                      >
                        <td className={styles.td}>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectSample?.(tItem.sample_id);
                            }}
                            className={styles.accessionLink}
                          >
                            <bdi dir="ltr">{tItem.accession_id}</bdi>
                          </button>
                        </td>
                        <td className={styles.td}>
                          <div className={styles.patientName}>
                            {tItem.patient_name || "—"}
                          </div>
                          <div className={styles.patientMrn}>
                            <bdi dir="ltr">{tItem.mrn || "—"}</bdi>
                          </div>
                        </td>
                        <td className={styles.td}>
                          <span className="font-semibold text-slate-800">
                            {tItem.from_branch?.name}
                          </span>{" "}
                          →{" "}
                          <span className="font-semibold text-slate-800">
                            {tItem.to_branch?.name}
                          </span>
                        </td>
                        <td className={styles.td}>
                          <span className="font-mono text-xs">
                            <bdi dir="ltr">
                              {tItem.dispatched_at
                                ? new Date(
                                    tItem.dispatched_at,
                                  ).toLocaleTimeString([], {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })
                                : "—"}
                            </bdi>
                          </span>
                        </td>
                        <td className={styles.td}>
                          <SampleStatusPill status={tItem.status} />
                        </td>
                        <td className={styles.tdRight}>
                          <div
                            className="inline-flex items-center gap-2 justify-end"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {/* Destination Receive Action */}
                            {(userRole === "owner" ||
                              userRole === "manager" ||
                              userRole === "technician") && (
                              <button
                                type="button"
                                disabled={transferActionLoading}
                                onClick={(e) =>
                                  handleReceiveTransfer(tItem.id, e)
                                }
                                className={styles.primaryBlackPill}
                              >
                                {t("samples:list_page.receive")}
                              </button>
                            )}
                            {/* Sender Cancel & Mark Lost Actions */}
                            {isManagerOrOwner && (
                              <>
                                <button
                                  type="button"
                                  disabled={transferActionLoading}
                                  onClick={(e) =>
                                    handleCancelTransfer(tItem.id, e)
                                  }
                                  className={styles.outlinePill}
                                >
                                  {t("samples:list_page.cancel")}
                                </button>
                                <button
                                  type="button"
                                  disabled={transferActionLoading}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setMarkLostId(tItem.id);
                                  }}
                                  className={styles.outlinePill}
                                >
                                  {t("samples:list_page.mark_lost")}
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* TAB 3: All Samples List */}
        {activeTab === "all" && (
          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead className={styles.tableHead}>
                <tr>
                  <th className={styles.thCenter}>
                    <input
                      type="checkbox"
                      aria-label={t("samples:list.select_all_aria")}
                      checked={
                        samples.length > 0 &&
                        selectedIds.size === samples.length
                      }
                      onChange={toggleSelectAll}
                      className="w-4 h-4 rounded border-slate-300 text-teal-600 cursor-pointer"
                    />
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_accession")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_patient")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_tests")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_status")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_branch")}
                  </th>
                  <th className={styles.th}>
                    {t("samples:list_page.col_age")}
                  </th>
                  <th className={styles.thRight}>
                    {t("samples:list_page.col_actions")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading && samples.length === 0 ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i} className={styles.skeletonRow}>
                      <td colSpan={8} className="py-4 px-4">
                        <div className={styles.skeletonBar} />
                      </td>
                    </tr>
                  ))
                ) : samples.length === 0 ? (
                  <tr>
                    <td colSpan={8}>
                      <div className={styles.emptyCard}>
                        <div className={styles.emptyIconCircle}>
                          <FlaskConical className="w-6 h-6" />
                        </div>
                        <h2 className={styles.emptyTitle}>
                          {searchQuery
                            ? t("samples:list_page.no_search_results", {
                                query: searchQuery,
                              })
                            : t("samples:list_page.no_accessions")}
                        </h2>
                        <p className={styles.emptySubtitle}>
                          {searchQuery
                            ? t("samples:list_page.no_search_body")
                            : t("samples:list_page.no_accessions_body")}
                        </p>
                        {onCollectNew && canCollect && (
                          <button
                            type="button"
                            onClick={onCollectNew}
                            className={styles.primaryBlackPill}
                          >
                            <Plus className="w-4 h-4" />
                            <span>{t("samples:list_page.collect_first")}</span>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ) : (
                  samples.map((sample) => {
                    const isChecked = selectedIds.has(sample.id);
                    return (
                      <tr
                        key={sample.id}
                        onClick={() => onSelectSample?.(sample.id)}
                        className={[
                          styles.tableRow,
                          isChecked ? styles.rowSelected : "",
                        ].join(" ")}
                      >
                        <td
                          className={styles.tdCenter}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            aria-label={t("samples:list.select_one_aria", {
                              accession: sample.accession_id,
                            })}
                            checked={isChecked}
                            onChange={(e) =>
                              toggleSelectOne(
                                sample.id,
                                e as unknown as React.MouseEvent,
                              )
                            }
                            className="w-4 h-4 rounded border-slate-300 text-teal-600 cursor-pointer"
                          />
                        </td>
                        <td className={styles.td}>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectSample?.(sample.id);
                            }}
                            className={styles.accessionLink}
                          >
                            <bdi dir="ltr">{sample.accession_id}</bdi>
                          </button>
                        </td>
                        <td className={styles.td}>
                          <div className={styles.patientName}>
                            {sample.patient_name}
                          </div>
                          <div className={styles.patientMrn}>
                            <bdi dir="ltr">{sample.patient_mrn}</bdi>
                          </div>
                        </td>
                        <td className={styles.td}>
                          <div className="flex items-center gap-1 flex-wrap">
                            {(sample.tests || [])
                              .slice(0, 2)
                              .map((test, idx) => (
                                <span key={idx} className={styles.testChip}>
                                  {test}
                                </span>
                              ))}
                            {(sample.tests || []).length > 2 && (
                              <span className={styles.testChip}>
                                +{(sample.tests || []).length - 2}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className={styles.td}>
                          <SampleStatusPill status={sample.status} />
                        </td>
                        <td className={styles.td}>{sample.branch_name}</td>
                        <td className={styles.td}>
                          {sample.age_display || t("samples:list.recent")}
                        </td>
                        <td className={styles.tdRight}>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectSample?.(sample.id);
                            }}
                            className={styles.outlinePill}
                          >
                            <span>{t("samples:page.view")}</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer info */}
        <footer className={styles.tableFooter}>
          <span>
            {t("samples:page.showing_records", {
              n:
                activeTab === "awaiting_collection"
                  ? filteredAwaiting.length
                  : activeTab === "transfers"
                    ? transfers.length
                    : samples.length,
            })}
          </span>
          <span className="font-mono text-xs">
            {t("samples:page.iso_compliant")}
          </span>
        </footer>
      </div>

      {/* Floating Bulk Bar on Checkbox Selection */}
      <SampleBulkBar
        selectedCount={selectedIds.size}
        onClear={() => setSelectedIds(new Set())}
        onPrintLabels={handleBatchPrint}
      />

      {/* Mark Lost Modal */}
      {markLostId && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="mark-lost-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/45 veyla-modal-scrim"
        >
          <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl border border-slate-200 veyla-modal space-y-4">
            <h2
              id="mark-lost-title"
              className="text-base font-bold text-slate-900"
            >
              {t("samples:list_page.mark_lost_title")}
            </h2>
            <p className="text-xs text-slate-500">
              {t("samples:list_page.mark_lost_desc")}
            </p>
            <textarea
              rows={3}
              value={markLostNote}
              onChange={(e) => setMarkLostNote(e.target.value)}
              placeholder={t("samples:list_page.mark_lost_placeholder")}
              className="w-full p-2.5 text-xs border border-slate-200 rounded-xl outline-none focus:border-teal-600 focus:ring-1 focus:ring-teal-600"
            />
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => {
                  setMarkLostId(null);
                  setMarkLostNote("");
                }}
                className={styles.outlinePill}
              >
                {t("samples:list_page.cancel")}
              </button>
              <button
                type="button"
                disabled={!markLostNote.trim() || transferActionLoading}
                onClick={handleMarkLostSubmit}
                className={styles.primaryBlackPill}
              >
                {t("samples:list_page.confirm_lost")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SampleAccessioningListScreen;
