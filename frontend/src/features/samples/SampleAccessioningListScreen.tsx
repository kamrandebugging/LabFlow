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
  const [awaitingItems, setAwaitingItems] = useState<AwaitingCollectionItem[]>(
    [],
  );
  const [transfers, setTransfers] = useState<SampleTransfer[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);

  // Selection & UI States
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
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

  // Fetch samples for the standard queue
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

  // Fetch awaiting collection items
  const loadAwaiting = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const res = await service.listAwaitingCollection();
      setAwaitingItems(res.results || []);
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsLoading(false);
    }
  }, [service, t]);

  // Fetch transfers
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
      // Ignored
    }
  }, [service, isManagerOrOwner]);

  // Main reload effect per tab
  useEffect(() => {
    if (activeTab === "awaiting_collection") {
      loadAwaiting();
    } else if (activeTab === "transfers") {
      loadTransfers();
      if (showExceptions) loadExceptions();
    } else {
      loadSamples();
    }
  }, [
    activeTab,
    loadAwaiting,
    loadTransfers,
    loadSamples,
    showExceptions,
    loadExceptions,
  ]);

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

  // Transfer action handlers
  const handleReceiveTransfer = async (
    transferId: string,
    e: React.MouseEvent,
  ) => {
    e.stopPropagation();
    try {
      setTransferActionLoading(true);
      await service.receiveTransfer(transferId);
      await loadTransfers();
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
    if (
      !window.confirm(
        "Are you sure you want to cancel this transfer? The sample will remain at the sending branch.",
      )
    ) {
      return;
    }
    try {
      setTransferActionLoading(true);
      await service.cancelTransfer(transferId);
      await loadTransfers();
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
      await loadTransfers();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setTransferActionLoading(false);
    }
  };

  // KPIs derived strictly from real API responses
  const awaitingTotal = awaitingItems.length;
  const collectedCount = samples.filter((s) => s.status === "collected").length;
  const inProcessCount = samples.filter(
    (s) => s.status === "in_process",
  ).length;
  const readyCount = samples.filter((s) => s.status === "ready").length;

  const kpiItems = [
    {
      id: "awaiting",
      label: "Awaiting collection",
      value: awaitingTotal,
      subtitle: "Pending draw",
    },
    {
      id: "collected",
      label: "Collected today",
      value: collectedCount,
      subtitle: "Drawn / In lab",
    },
    {
      id: "in_process",
      label: "In process",
      value: inProcessCount,
      subtitle: "Bench testing",
    },
    {
      id: "ready",
      label: "Ready / Reported",
      value: readyCount,
      subtitle: "Results approved",
    },
  ];

  // Tab Definitions
  const tabs = [
    {
      id: "awaiting_collection",
      label: "Awaiting collection",
      count: awaitingTotal,
    },
    {
      id: "all",
      label: "All samples",
      count: samples.length,
    },
    {
      id: "transfers",
      label: "Transfers",
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
          <h1 className={styles.pageTitle}>Samples</h1>
          <p className={styles.pageSubtitle}>
            Central specimen accessioning and chain of custody tracking
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
            <span>Print labels ({selectedIds.size})</span>
          </button>
          {onCollectNew && canCollect && (
            <button
              type="button"
              onClick={onCollectNew}
              className={styles.primaryBlackPill}
            >
              <Plus className="w-4 h-4" />
              <span>Collect sample</span>
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
                  ? "Search patient, MRN, or test..."
                  : "Search by Accession ID (e.g. CDL2026...)"
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
              <option value="all">All statuses</option>
              <option value="collected">Collected</option>
              <option value="received">Received</option>
              <option value="in_process">In process</option>
              <option value="ready">Ready / Reported</option>
              <option value="rejected">Rejected</option>
              <option value="cancelled">Cancelled</option>
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
              <option value="all">All directions</option>
              <option value="incoming">Incoming to branch</option>
              <option value="outgoing">Outgoing from branch</option>
            </select>
          )}

          <select
            id={branchSelectId}
            value={selectedBranch}
            onChange={(e) => setSelectedBranch(e.target.value)}
            className={styles.selectDropdown}
          >
            <option value="all">All branches</option>
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
            <option value="oldest">Oldest first</option>
            <option value="newest">Newest first</option>
          </select>

          <button
            type="button"
            onClick={() => {
              if (activeTab === "awaiting_collection") loadAwaiting();
              else if (activeTab === "transfers") loadTransfers();
              else loadSamples();
            }}
            aria-label="Refresh"
            className={styles.outlinePill}
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`}
            />
          </button>
        </div>

        {activeTab === "transfers" && isManagerOrOwner && (
          <button
            type="button"
            onClick={() => {
              setShowExceptions(!showExceptions);
              if (!showExceptions) loadExceptions();
            }}
            className={styles.outlinePill}
          >
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
            <span>
              {showExceptions ? "Hide exceptions" : "Transfer exceptions"}
            </span>
          </button>
        )}
      </div>

      {/* Transfer Exceptions Oversight View (Phase 2.8) */}
      {activeTab === "transfers" && showExceptions && exceptionsData && (
        <div className="bg-amber-50/50 border border-amber-200 rounded-2xl p-5 space-y-4">
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <span>Transfer Exceptions Oversight</span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div className="bg-white p-3.5 rounded-xl border border-amber-200">
              <span className="font-semibold text-slate-700 block mb-1">
                Late Transfers (&gt;24h)
              </span>
              <span className="text-2xl font-bold text-slate-900">
                {exceptionsData.late?.total || 0}
              </span>
            </div>
            <div className="bg-white p-3.5 rounded-xl border border-amber-200">
              <span className="font-semibold text-slate-700 block mb-1">
                Lost Specimen Reports
              </span>
              <span className="text-2xl font-bold text-slate-900">
                {exceptionsData.lost?.total || 0}
              </span>
            </div>
            <div className="bg-white p-3.5 rounded-xl border border-amber-200">
              <span className="font-semibold text-slate-700 block mb-1">
                Active Transfer Routes
              </span>
              <span className="text-2xl font-bold text-slate-900">
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
                  <th className={styles.th}>Patient</th>
                  <th className={styles.th}>Ordered Tests / Panels</th>
                  <th className={styles.th}>Branch</th>
                  <th className={styles.th}>Ordered At</th>
                  <th className={styles.thRight}>Action</th>
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
                          No tests awaiting collection
                        </h2>
                        <p className={styles.emptySubtitle}>
                          Specimens will appear here automatically when orders
                          are created at the front desk.
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
                          {item.patient_mrn}
                        </div>
                      </td>
                      <td className={styles.td}>
                        <span className={styles.testChip}>
                          {item.description ||
                            item.test_name ||
                            "Diagnostic Test"}
                        </span>
                      </td>
                      <td className={styles.td}>{item.branch_name}</td>
                      <td className={styles.td}>
                        <span className="font-mono text-xs">
                          {new Date(item.ordered_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                            hour12: false,
                          })}
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
                            <span>Collect →</span>
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
                  <th className={styles.th}>Accession ID</th>
                  <th className={styles.th}>Patient</th>
                  <th className={styles.th}>Route (From → To)</th>
                  <th className={styles.th}>Dispatched At</th>
                  <th className={styles.th}>Status</th>
                  <th className={styles.thRight}>Actions</th>
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
                          No active transfers
                        </h2>
                        <p className={styles.emptySubtitle}>
                          Specimens in transit between laboratory branches will
                          be tracked here.
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
                            {tItem.accession_id}
                          </button>
                        </td>
                        <td className={styles.td}>
                          <div className={styles.patientName}>
                            {tItem.patient_name || "—"}
                          </div>
                          <div className={styles.patientMrn}>
                            {tItem.mrn || "—"}
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
                            {tItem.dispatched_at
                              ? new Date(
                                  tItem.dispatched_at,
                                ).toLocaleTimeString([], {
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })
                              : "—"}
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
                                Receive
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
                                  Cancel
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
                                  Mark lost
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
                      aria-label="Select all visible samples"
                      checked={
                        samples.length > 0 &&
                        selectedIds.size === samples.length
                      }
                      onChange={toggleSelectAll}
                      className="w-4 h-4 rounded border-slate-300 text-teal-600 cursor-pointer"
                    />
                  </th>
                  <th className={styles.th}>Accession ID</th>
                  <th className={styles.th}>Patient</th>
                  <th className={styles.th}>Tests</th>
                  <th className={styles.th}>Status</th>
                  <th className={styles.th}>Branch</th>
                  <th className={styles.th}>Age</th>
                  <th className={styles.thRight}>Actions</th>
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
                            ? `No samples found for '${searchQuery}'`
                            : "No accessions recorded"}
                        </h2>
                        <p className={styles.emptySubtitle}>
                          {searchQuery
                            ? "Try adjusting your search query or clear the filter."
                            : "Collect your first sample to initiate chain of custody tracking."}
                        </p>
                        {onCollectNew && canCollect && (
                          <button
                            type="button"
                            onClick={onCollectNew}
                            className={styles.primaryBlackPill}
                          >
                            <Plus className="w-4 h-4" />
                            <span>Collect first sample</span>
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
                          isChecked ? "bg-teal-50/20" : "",
                        ].join(" ")}
                      >
                        <td
                          className={styles.tdCenter}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            aria-label={`Select ${sample.accession_id}`}
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
                            {sample.accession_id}
                          </button>
                        </td>
                        <td className={styles.td}>
                          <div className={styles.patientName}>
                            {sample.patient_name}
                          </div>
                          <div className={styles.patientMrn}>
                            {sample.patient_mrn}
                          </div>
                        </td>
                        <td className={styles.td}>
                          <div className="flex items-center gap-1 flex-wrap">
                            {(sample.tests || []).slice(0, 2).map((t, idx) => (
                              <span key={idx} className={styles.testChip}>
                                {t}
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
                          {sample.age_display || "Recent"}
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
                            <span>View ›</span>
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
            Showing{" "}
            {activeTab === "awaiting_collection"
              ? filteredAwaiting.length
              : activeTab === "transfers"
                ? transfers.length
                : samples.length}{" "}
            records
          </span>
          <span className="font-mono text-xs">ISO 15189 Compliant</span>
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
              Mark Transfer as Lost
            </h2>
            <p className="text-xs text-slate-500">
              A clinical non-conformance event will be logged in the audit
              trail. Please provide a required reason note:
            </p>
            <textarea
              rows={3}
              value={markLostNote}
              onChange={(e) => setMarkLostNote(e.target.value)}
              placeholder="e.g. Courier vehicle accident / package unreceived at destination"
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
                Cancel
              </button>
              <button
                type="button"
                disabled={!markLostNote.trim() || transferActionLoading}
                onClick={handleMarkLostSubmit}
                className={styles.primaryBlackPill}
              >
                Confirm Lost
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SampleAccessioningListScreen;
