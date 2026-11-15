import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  HelpCircle,
  Plus,
  Receipt,
  RefreshCw,
  RotateCcw,
  Search,
  X,
  XCircle,
} from "lucide-react";
import { billingService } from "./billingService";
import { formatMoney, statusLabel } from "../../lib/format";
import { messageForError } from "../../lib/errors";
import type { InvoiceStatus, InvoiceSummary } from "./types";
import styles from "./InvoicesListScreen.module.css";

interface InvoicesListScreenProps {
  onNewInvoice?: () => void;
  onSelectInvoice?: (id: string) => void;
  service?: typeof billingService;
}

export function InvoicesListScreen({
  onNewInvoice,
  onSelectInvoice,
  service = billingService,
}: InvoicesListScreenProps): JSX.Element {
  const { t, i18n } = useTranslation(["billing", "common"]);
  const lang: "en" | "ur" = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dailyTotal, setDailyTotal] = useState<string | null>(null);

  const fetchInvoices = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await service.listInvoices({
        status: selectedStatus === "all" ? undefined : selectedStatus,
      });
      setInvoices(data.results);
      // Never derive a "daily" total from the loaded page: it mixes dates and
      // statuses. Absence is shown as unavailable.
      setDailyTotal(data.daily_total ?? null);
    } catch (err: unknown) {
      setError(messageForError(err, t));
    } finally {
      setIsLoading(false);
    }
  }, [selectedStatus, service, t]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const filteredInvoices = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return invoices;
    return invoices.filter(
      (inv) =>
        inv.id.toLowerCase().includes(q) ||
        (inv.patient_name && inv.patient_name.toLowerCase().includes(q)) ||
        (inv.patient_mrn && inv.patient_mrn.toLowerCase().includes(q)) ||
        (inv.items_summary && inv.items_summary.toLowerCase().includes(q)),
    );
  }, [invoices, searchQuery]);

  const getStatusBadge = (status: InvoiceStatus) => {
    switch (status) {
      case "paid":
        return (
          <span className={`${styles.statusBadge} ${styles.statusPaid}`}>
            <CheckCircle2 className={styles.statusIcon} aria-hidden="true" />
            {statusLabel("invoice", "paid", (key) => t(`common:${key}`))}
          </span>
        );
      case "unpaid":
        return (
          <span className={`${styles.statusBadge} ${styles.statusUnpaid}`}>
            <AlertCircle className={styles.statusIcon} aria-hidden="true" />
            {statusLabel("invoice", "unpaid", (key) => t(`common:${key}`))}
          </span>
        );
      case "partial":
        return (
          <span className={`${styles.statusBadge} ${styles.statusPartial}`}>
            <Clock className={styles.statusIcon} aria-hidden="true" />
            {statusLabel("invoice", "partial", (key) => t(`common:${key}`))}
          </span>
        );
      case "refunded":
        return (
          <span className={`${styles.statusBadge} ${styles.statusRefunded}`}>
            <RotateCcw className={styles.statusIcon} aria-hidden="true" />
            {statusLabel("invoice", "refunded", (key) => t(`common:${key}`))}
          </span>
        );
      case "cancelled":
        return (
          <span className={`${styles.statusBadge} ${styles.statusCancelled}`}>
            <XCircle className={styles.statusIcon} aria-hidden="true" />
            {statusLabel("invoice", "cancelled", (key) => t(`common:${key}`))}
          </span>
        );
      default:
        return (
          <span className={`${styles.statusBadge} ${styles.statusUnknown}`}>
            <HelpCircle className={styles.statusIcon} aria-hidden="true" />
            {t("common:labels.unknown")}
          </span>
        );
    }
  };

  const formatDate = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return `${d.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })} · ${d.toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
      })} PKT`;
    } catch {
      return isoString;
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* 1. Header & Daily Summary */}
        <div className={styles.header}>
          <div className={styles.titleBlock}>
            <span className={styles.iconTile}>
              <Receipt className={styles.titleIcon} aria-hidden="true" />
            </span>
            <div>
              <h1 className={styles.title}>{t("billing:list.title")}</h1>
              <p className={styles.subtitle}>
                {t("billing:list.subtitle")} · {t("common:time.pkt")}
              </p>
            </div>
          </div>

          <div className={styles.headerActions}>
            {/* Daily Total Summary Pill — flat, API value verbatim. */}
            <div className={styles.dailyPill}>
              <Calendar className={styles.dailyIcon} aria-hidden="true" />
              <span className={styles.dailyLabel}>
                {t("billing:list.daily_total")}
              </span>
              <span className={styles.dailyValue}>
                {formatMoney(dailyTotal, lang)}
              </span>
            </div>

            {onNewInvoice ? (
              <button
                type="button"
                onClick={onNewInvoice}
                className={styles.primaryButton}
              >
                <Plus className={styles.buttonIcon} aria-hidden="true" />
                {t("billing:list.new_invoice")}
              </button>
            ) : null}
          </div>
        </div>

        {/* 2. Filter Bar */}
        <div className={styles.filterBar}>
          <div className={styles.filterGroup}>
            {/* Status Dropdown */}
            <div className={styles.selectWrap}>
              <label htmlFor="invoiceStatusFilter" className={styles.srOnly}>
                {t("billing:list.status_filter_aria")}
              </label>
              <select
                id="invoiceStatusFilter"
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className={styles.select}
              >
                <option value="all">{t("billing:list.all_statuses")}</option>
                <option value="paid">
                  {statusLabel("invoice", "paid", (key) => t(`common:${key}`))}
                </option>
                <option value="unpaid">
                  {statusLabel("invoice", "unpaid", (key) =>
                    t(`common:${key}`),
                  )}
                </option>
                <option value="partial">
                  {statusLabel("invoice", "partial", (key) =>
                    t(`common:${key}`),
                  )}
                </option>
                <option value="refunded">
                  {statusLabel("invoice", "refunded", (key) =>
                    t(`common:${key}`),
                  )}
                </option>
                <option value="cancelled">
                  {statusLabel("invoice", "cancelled", (key) =>
                    t(`common:${key}`),
                  )}
                </option>
              </select>
              <ChevronDown className={styles.selectIcon} aria-hidden="true" />
            </div>

            {/* Search Input */}
            <div className={styles.searchWrap}>
              <Search className={styles.searchIcon} aria-hidden="true" />
              <label htmlFor="invoiceSearchInput" className={styles.srOnly}>
                {t("billing:list.search_aria")}
              </label>
              <input
                id="invoiceSearchInput"
                type="text"
                placeholder={t("billing:list.search_placeholder")}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className={styles.searchInput}
              />
            </div>
          </div>

          <button
            type="button"
            onClick={fetchInvoices}
            disabled={isLoading}
            className={styles.iconButton}
            title={t("billing:list.refresh_title")}
            aria-label={t("billing:list.refresh_title")}
            aria-disabled={isLoading}
          >
            <RefreshCw
              className={`${styles.spinIcon} ${isLoading ? "" : styles.spinHidden}`}
              aria-hidden="true"
            />
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className={styles.alert} role="alert">
            <div className={styles.alertBody}>
              <AlertCircle className={styles.alertIcon} aria-hidden="true" />
              <span>{error}</span>
            </div>
            <button
              type="button"
              onClick={() => setError(null)}
              aria-label={t("billing:shared.dismiss_error_aria")}
              className={styles.dismiss}
            >
              <X className={styles.dismissIcon} aria-hidden="true" />
            </button>
          </div>
        )}

        {/* 3. Invoices Table Card */}
        <div className={styles.tableCard}>
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th} scope="col">
                    {t("billing:list.col_invoice")}
                  </th>
                  <th className={styles.th} scope="col">
                    {t("billing:list.col_patient")}
                  </th>
                  <th className={styles.th} scope="col">
                    {t("common:labels.date")}
                  </th>
                  <th
                    className={`${styles.th} ${styles.testsCell}`}
                    scope="col"
                  >
                    {t("billing:list.col_tests")}
                  </th>
                  <th className={styles.th} scope="col">
                    {t("billing:list.col_total")}
                  </th>
                  <th className={styles.th} scope="col">
                    {t("common:labels.status")}
                  </th>
                  <th
                    className={`${styles.th} ${styles.thEnd}`}
                    scope="col"
                  >
                    {t("billing:list.col_action")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr className={styles.row}>
                    <td colSpan={7} className={styles.td}>
                      <div className={styles.loading}>
                        <RefreshCw
                          className={`${styles.spin} ${styles.spinBrand}`}
                          aria-hidden="true"
                        />
                        <span>{t("billing:list.loading")}</span>
                      </div>
                    </td>
                  </tr>
                ) : filteredInvoices.length === 0 ? (
                  <tr className={styles.row}>
                    <td
                      colSpan={7}
                      className={`${styles.td} ${styles.emptyCell}`}
                    >
                      <div className={styles.emptyPanel}>
                        <Receipt
                          className={styles.emptyIcon}
                          aria-hidden="true"
                        />
                        <p className={styles.emptyText}>
                          {t("billing:list.empty")}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filteredInvoices.map((inv) => (
                    <tr key={inv.id} className={styles.row}>
                      <td className={styles.td}>
                        <span className={styles.invoiceId}>
                          {inv.id.startsWith("INV-")
                            ? inv.id
                            : `INV-${inv.id.slice(0, 8).toUpperCase()}`}
                        </span>
                      </td>
                      <td className={styles.td}>
                        <span className={styles.patientName}>
                          {inv.patient_name ||
                            t("billing:list.patient_fallback")}
                        </span>
                        <span className={styles.patientMrn}>
                          {inv.patient_mrn ||
                            `${t("billing:list.mrn_label")} ${inv.patient_id.slice(0, 8)}`}
                        </span>
                      </td>
                      <td className={styles.td}>
                        <bdi dir="ltr" className={styles.date}>
                          {formatDate(inv.created_at)}
                        </bdi>
                      </td>
                      <td className={`${styles.td} ${styles.testsCell}`}>
                        <span
                          className={styles.tests}
                          title={
                            inv.items_summary ||
                            t("billing:list.tests_fallback")
                          }
                        >
                          {inv.items_summary ||
                            t("billing:list.tests_fallback")}
                        </span>
                      </td>
                      <td className={styles.td}>
                        <span className={styles.totalChip}>
                          {formatMoney(inv.total, lang)}
                        </span>
                      </td>
                      <td className={styles.td}>
                        {getStatusBadge(inv.status)}
                      </td>
                      <td className={`${styles.td} ${styles.cellEnd}`}>
                        <button
                          type="button"
                          onClick={() => onSelectInvoice?.(inv.id)}
                          className={styles.viewButton}
                        >
                          {t("billing:list.view")}{" "}
                          <span aria-hidden="true" className={styles.rtlArrow}>
                            →
                          </span>
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Table Footer */}
          <div className={styles.footer}>
            <div>
              {t("billing:list.showing", { total: filteredInvoices.length })}
            </div>
            <div className={styles.pager}>
              <button
                type="button"
                disabled
                aria-disabled="true"
                aria-label={t("common:actions.previous")}
                className={styles.pageButton}
              >
                <ChevronLeft className={styles.pageIcon} aria-hidden="true" />
              </button>
              <button
                type="button"
                disabled
                aria-disabled="true"
                aria-label={t("common:actions.next")}
                className={styles.pageButton}
              >
                <ChevronRight className={styles.pageIcon} aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
export default InvoicesListScreen;
