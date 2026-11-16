import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowRight,
  CircleCheck,
  CreditCard,
  Plus,
  Receipt,
  RefreshCw,
  Search,
} from "lucide-react";
import { billingService } from "./billingService";
import { formatMoney, statusLabel } from "../../lib/format";
import { messageForError } from "../../lib/errors";
import type { InvoiceStatus, InvoiceSummary } from "./types";
import styles from "../patients/PatientListScreen.module.css";
import billingStyles from "./InvoicesListScreen.module.css";

interface InvoicesListScreenProps {
  onNewInvoice?: () => void;
  /** Opens the invoice record drawer over the list. */
  onSelectInvoice?: (id: string) => void;
  service?: typeof billingService;
}

const STATUS_CLASS: Record<InvoiceStatus, string> = {
  draft: "statusUnknown",
  unpaid: "statusUnpaid",
  partial: "statusPartial",
  paid: "statusPaid",
  refunded: "statusRefunded",
  cancelled: "statusCancelled",
};

export function InvoicesListScreen({
  onNewInvoice,
  onSelectInvoice,
  service = billingService,
}: InvoicesListScreenProps): JSX.Element {
  const { t } = useTranslation(["billing", "common"]);
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dailyTotal, setDailyTotal] = useState<string | null>(null);
  const [animateRows, setAnimateRows] = useState(false);
  const entrancePlayed = useRef(false);

  const fetchInvoices = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await service.listInvoices({});
      setInvoices(data.results);
      setDailyTotal(data.daily_total ?? null);
    } catch (err: unknown) {
      setError(messageForError(err, t));
    } finally {
      setIsLoading(false);
    }
  }, [service, t]);

  useEffect(() => {
    void fetchInvoices();
  }, [fetchInvoices]);

  useEffect(() => {
    if (isLoading || entrancePlayed.current) return;
    entrancePlayed.current = true;
    setAnimateRows(true);
    const timer = window.setTimeout(() => setAnimateRows(false), 600);
    return () => window.clearTimeout(timer);
  }, [isLoading]);

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

  const statusPill = (status: InvoiceStatus) => (
    <span
      className={`${billingStyles.statusBadge} ${
        billingStyles[STATUS_CLASS[status]] ?? billingStyles.statusUnknown
      }`}
    >
      {statusLabel("invoice", status, (key) => t(`common:${key}`))}
    </span>
  );

  const balanceOf = (inv: InvoiceSummary): number | null => {
    // The list payload does not always carry net_paid; only claim a balance
    // when the status says money is still due AND the server gave a paid
    // figure. Never infer a balance from the total alone.
    if (inv.status !== "partial" && inv.status !== "unpaid") return null;
    if (inv.net_paid === undefined || inv.net_paid === null) return null;
    const total = Number.parseFloat(inv.total || "0");
    const paid = Number.parseFloat(inv.net_paid || "0");
    if (!Number.isFinite(total) || !Number.isFinite(paid)) return null;
    return Math.max(0, total - paid);
  };

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* Header — same anatomy as Patients. */}
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>{t("common:nav.invoices")}</h1>
            <p className={styles.subtitle}>{t("billing:list.subtitle")}</p>
          </div>
          <span className={styles.syncBadge}>
            <CircleCheck className={styles.syncIcon} aria-hidden="true" />
            {dailyTotal !== null
              ? `${t("billing:list.daily_total")}: ${formatMoney(
                  dailyTotal,
                  "en",
                )}`
              : t("billing:list.daily_total")}
          </span>
        </div>

        {/* Toolbar */}
        <div className={styles.toolbar}>
          <div className={styles.searchWrap}>
            <Search className={styles.searchIcon} aria-hidden="true" />
            <input
              id="invoice-search-input"
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t("billing:list.search_placeholder")}
              aria-label={t("billing:list.search_placeholder")}
              className={styles.searchInput}
              autoComplete="off"
            />
          </div>
          <div className={styles.toolbarActions}>
            <button
              type="button"
              onClick={() => void fetchInvoices()}
              className={styles.iconButton}
              title={t("billing:list.refresh_title")}
              aria-label={t("billing:list.refresh_title")}
            >
              <RefreshCw
                className={`${styles.spin} ${isLoading ? "" : styles.spinHidden}`}
                aria-hidden="true"
              />
            </button>
            {onNewInvoice ? (
              <button
                type="button"
                onClick={onNewInvoice}
                className={styles.primaryButton}
              >
                <Plus className={styles.buttonIcon} aria-hidden="true" />
                <span>{t("billing:list.new_invoice")}</span>
              </button>
            ) : null}
          </div>
        </div>

        {error && (
          <div role="alert" className={styles.alert}>
            <div className={styles.alertBody}>
              <AlertCircle className={styles.alertIcon} aria-hidden="true" />
              <span>{error}</span>
            </div>
            <button
              type="button"
              onClick={() => void fetchInvoices()}
              className={styles.retry}
            >
              {t("common:actions.retry")}
            </button>
          </div>
        )}

        {/* Table */}
        <div className={styles.tableCard}>
          <div className={styles.tableScroll}>
            <table className={styles.table} data-testid="invoice-table">
              <thead>
                <tr>
                  <th scope="col" className={styles.th}>
                    {t("billing:list.col_invoice")}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t("billing:list.col_patient")}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t("common:labels.date")}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t("billing:list.col_tests")}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t("billing:list.col_total")}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t("common:labels.status")}
                  </th>
                  <th scope="col" className={`${styles.th} ${styles.thEnd}`}>
                    {t("billing:list.col_action")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  [0, 1, 2, 3].map((row) => (
                    <tr key={row} className={styles.row}>
                      <td colSpan={7} className={styles.td}>
                        <div
                          className={styles.skeletonRow}
                          aria-hidden="true"
                          data-testid="invoice-skeleton-row"
                        >
                          <span
                            className={`${styles.skeletonBlock} ${styles.skeletonMono}`}
                          />
                          <span
                            className={`${styles.skeletonBlock} ${styles.skeletonName}`}
                          />
                          <span
                            className={`${styles.skeletonBlock} ${styles.skeletonShort}`}
                          />
                        </div>
                      </td>
                    </tr>
                  ))
                ) : filteredInvoices.length === 0 ? (
                  <tr className={styles.row}>
                    <td colSpan={7} className={styles.emptyCell}>
                      <div className={styles.emptyInner}>
                        <span className={styles.emptyIconCircle}>
                          <Receipt
                            className={styles.emptyIcon}
                            aria-hidden="true"
                          />
                        </span>
                        <p className={styles.emptyTitle}>
                          {searchQuery
                            ? t("billing:list.empty")
                            : t("billing:list.empty")}
                        </p>
                        {onNewInvoice ? (
                          <button
                            type="button"
                            onClick={onNewInvoice}
                            className={styles.emptyAction}
                          >
                            <Plus
                              className={styles.buttonIcon}
                              aria-hidden="true"
                            />
                            <span>{t("billing:list.new_invoice")}</span>
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ) : (
                  filteredInvoices.map((inv, index) => {
                    const balance = balanceOf(inv);
                    return (
                      <tr
                        key={inv.id}
                        role="button"
                        tabIndex={0}
                        aria-label={inv.invoice_number || inv.id}
                        className={`${styles.row} ${styles.rowClickable}${
                          animateRows ? ` ${styles.rowEnter}` : ""
                        }`}
                        style={
                          animateRows
                            ? {
                                animationDelay: `${Math.min(index, 9) * 20}ms`,
                              }
                            : undefined
                        }
                        onClick={() => onSelectInvoice?.(inv.id)}
                        onKeyDown={(event) => {
                          if (event.key !== "Enter" && event.key !== " ") {
                            return;
                          }
                          event.preventDefault();
                          onSelectInvoice?.(inv.id);
                        }}
                      >
                        <td className={styles.td}>
                          <span dir="ltr" className={styles.mrn}>
                            {inv.invoice_number || inv.id.slice(0, 12)}
                          </span>
                        </td>
                        <td className={styles.td}>
                          <span
                            className={styles.patientName}
                            style={{ whiteSpace: "nowrap" }}
                          >
                            {inv.patient_name || "—"}
                          </span>
                          <span className={styles.patientMeta}>
                            {inv.patient_mrn || "—"}
                          </span>
                        </td>
                        <td className={styles.td}>
                          <span className={styles.lastVisit}>
                            {new Date(inv.created_at).toLocaleDateString(
                              "en-GB",
                              {
                                day: "2-digit",
                                month: "short",
                                year: "numeric",
                              },
                            )}
                          </span>
                        </td>
                        <td className={styles.td}>
                          <span className={styles.patientMeta}>
                            {inv.items_summary ||
                              t("billing:list.tests_fallback")}
                          </span>
                        </td>
                        <td className={styles.td}>
                          <span
                            className={styles.phone}
                            dir="ltr"
                            style={{ whiteSpace: "nowrap" }}
                          >
                            {formatMoney(inv.total, "en")}
                          </span>
                          {balance !== null && balance > 0 ? (
                            <span className={styles.patientMeta}>
                              {t("billing:detail.balance_due")}:{" "}
                              {formatMoney(balance.toFixed(2), "en")}
                            </span>
                          ) : null}
                        </td>
                        <td className={styles.td}>{statusPill(inv.status)}</td>
                        <td className={`${styles.td} ${styles.cellEnd}`}>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectInvoice?.(inv.id);
                            }}
                            className={styles.viewButton}
                          >
                            {t("billing:list.view")}
                            <ArrowRight
                              className={styles.arrow}
                              aria-hidden="true"
                            />
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {!isLoading && filteredInvoices.length > 0 ? (
          <div className={styles.footerCount}>
            <CreditCard size={14} aria-hidden="true" />
            {t("billing:list.showing", { count: filteredInvoices.length })}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default InvoicesListScreen;
