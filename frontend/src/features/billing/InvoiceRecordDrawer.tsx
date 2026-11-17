import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Printer } from "lucide-react";

import { billingService } from "./billingService";
import type {
  InvoiceDetail,
  InvoiceHistoryEvent,
  InvoiceStatus,
} from "./types";
import { formatMoney, statusLabel } from "../../lib/format";
import { messageForError } from "../../lib/errors";
import { VeylaDrawer } from "../patients/VeylaDrawer";
import record from "../patients/PatientRecord.module.css";
import styles from "./InvoiceDetailScreen.module.css";

interface InvoiceRecordDrawerProps {
  invoiceId: string;
  onClose: () => void;
  /** Opens the full invoice page for payment / refund / cancel actions. */
  service?: typeof billingService;
}

const STATUS_CLASS: Record<InvoiceStatus, string | undefined> = {
  draft: styles.statusUnknown,
  unpaid: styles.statusUnpaid,
  partial: styles.statusPartial,
  paid: styles.statusPaid,
  refunded: styles.statusRefunded,
  cancelled: styles.statusCancelled,
};

/**
 * Invoice record in the same right-side drawer as a patient record:
 * identity header, Overview | Payments tabs, sticky footer.
 */
export function InvoiceRecordDrawer({
  invoiceId,
  onClose,
  service = billingService,
}: InvoiceRecordDrawerProps): JSX.Element {
  const { t } = useTranslation(["billing", "common"]);
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<
    "overview" | "settle" | "refund" | "payments" | "history"
  >("overview");
  const [history, setHistory] = useState<InvoiceHistoryEvent[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<
    "cash" | "card" | "bank_transfer" | "easypaisa" | "jazzcash" | "other"
  >("cash");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const reload = () => setReloadKey((n) => n + 1);

  // History loads lazily when its tab opens (and after every action reload).
  useEffect(() => {
    if (tab !== "history") return;
    let active = true;
    setHistoryLoading(true);
    setHistoryError(null);
    service
      .getInvoiceHistory(invoiceId)
      .then((data) => {
        if (active) setHistory(data.events ?? []);
      })
      .catch((err: unknown) => {
        if (active) setHistoryError(messageForError(err, t));
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [tab, invoiceId, service, t, reloadKey]);

  const submitSettle = async (kind: "payment" | "refund") => {
    if (!invoice) return;
    if (kind === "refund" && !reference.trim()) {
      setActionError(t("billing:detail.refund_reason_required"));
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      await service.recordPayment(invoice.id, {
        kind,
        method,
        amount,
        reference: kind === "refund" ? null : reference || null,
        refund_reason: kind === "refund" ? reference || null : null,
      });
      setAmount("");
      setReference("");
      reload();
      setTab("payments");
    } catch (err: unknown) {
      const raw = messageForError(err, t);
      setActionError(
        /^[a-z_]+\.[a-z_]+/i.test(raw)
          ? kind === "refund"
            ? "Refund could not be processed — check the amount and the reason."
            : "Payment could not be recorded — check the amount."
          : raw,
      );
    } finally {
      setBusy(false);
    }
  };

  const cancelInvoice = async () => {
    if (!invoice) return;
    setBusy(true);
    setActionError(null);
    try {
      await service.cancelInvoice(
        invoice.id,
        "Cancelled from the record drawer",
      );
      reload();
    } catch (err: unknown) {
      const raw = messageForError(err, t);
      setActionError(
        /^[a-z_]+\.[a-z_]+/i.test(raw) || /conflict/i.test(raw)
          ? "This invoice cannot be cancelled — it already has payments or a settled balance. Use Refund instead."
          : raw,
      );
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setError(null);
    service
      .getInvoice(invoiceId)
      .then((data) => {
        if (active) setInvoice(data);
      })
      .catch((err: unknown) => {
        if (active) setError(messageForError(err, t));
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [invoiceId, service, t, reloadKey]);

  const balance = useMemo(() => {
    if (!invoice) return 0;
    const total = Number.parseFloat(invoice.total || "0");
    const paid = Number.parseFloat(invoice.net_paid || "0");
    if (!Number.isFinite(total) || !Number.isFinite(paid)) return 0;
    return Math.max(0, total - paid);
  }, [invoice]);

  const header = invoice ? (
    <div className={record.nameRow}>
      <h1 className={record.title} dir="ltr">
        {invoice.invoice_number || invoice.id.slice(0, 12)}
      </h1>
      <span
        className={`${styles.statusBadge} ${STATUS_CLASS[invoice.status] ?? styles.statusUnknown}`}
      >
        {statusLabel("invoice", invoice.status, (key) => t(`common:${key}`))}
      </span>
      <span className={record.branchPill}>
        {invoice.branch_name || t("patients:main_branch")}
      </span>
      <p className={record.metaLine}>
        {invoice.patient_name || "—"} ·{" "}
        <strong className={record.metaStrong}>
          <bdi dir="ltr">{invoice.patient_mrn || "—"}</bdi>
        </strong>{" "}
        · <bdi dir="ltr">{new Date(invoice.created_at).toLocaleString()}</bdi>
      </p>
    </div>
  ) : null;

  const footer = invoice ? (
    <>
      <button
        type="button"
        disabled={
          busy ||
          invoice.status === "paid" ||
          invoice.status === "refunded" ||
          invoice.status === "cancelled"
        }
        onClick={() => void cancelInvoice()}
        className={record.secondaryButton}
        style={{
          color: "var(--color-danger)",
          borderColor: "var(--color-danger)",
        }}
      >
        {t("billing:detail.cancel_invoice") || "Cancel Invoice"}
      </button>
      <button
        type="button"
        onClick={() =>
          window.open(
            `/invoices/${invoice.id}/print`,
            "_blank",
            "noopener,noreferrer",
          )
        }
        className={record.secondaryButton}
      >
        <Printer className={record.buttonIcon} aria-hidden="true" />
        <span>{t("billing:detail.print_receipt")}</span>
      </button>
    </>
  ) : undefined;

  return (
    <VeylaDrawer
      open
      onClose={onClose}
      title={invoice?.invoice_number || invoice?.id || ""}
      header={header}
      footer={footer}
    >
      <div className={record.drawerShell}>
        {isLoading ? (
          <p className={record.fieldValue}>{t("billing:detail.loading")}</p>
        ) : error || !invoice ? (
          <div role="alert" className={record.alert}>
            <AlertCircle className={record.statusIcon} aria-hidden="true" />
            <span>{error || t("billing:detail.not_found_title")}</span>
          </div>
        ) : (
          <>
            <div
              className={record.drawerTabs}
              role="tablist"
              style={{ gridTemplateColumns: "repeat(5, 1fr)" }}
            >
              <button
                type="button"
                role="tab"
                aria-selected={tab === "overview"}
                onClick={() => setTab("overview")}
                className={`${record.drawerTab} ${tab === "overview" ? record.drawerTabActive : ""}`}
              >
                {t("common:labels.summary")}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "settle"}
                onClick={() => setTab("settle")}
                className={`${record.drawerTab} ${tab === "settle" ? record.drawerTabActive : ""}`}
              >
                {t("billing:detail.record_payment_title")}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "refund"}
                onClick={() => setTab("refund")}
                className={`${record.drawerTab} ${tab === "refund" ? record.drawerTabActive : ""}`}
              >
                {t("billing:detail.kind.refund")}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "payments"}
                onClick={() => setTab("payments")}
                className={`${record.drawerTab} ${tab === "payments" ? record.drawerTabActive : ""}`}
              >
                {t("billing:detail.ledger_title")}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "history"}
                onClick={() => setTab("history")}
                className={`${record.drawerTab} ${tab === "history" ? record.drawerTabActive : ""}`}
              >
                {t("billing:detail.history_title")}
              </button>
            </div>

            {tab === "overview" ? (
              <>
                <div className={record.card}>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 12,
                    }}
                  >
                    <div>
                      <p className={record.fieldLabel}>
                        {t("billing:detail.gross_subtotal")}
                      </p>
                      <p className={record.monoValue} dir="ltr">
                        {formatMoney(invoice.subtotal, "en")}
                      </p>
                    </div>
                    <div>
                      <p className={record.fieldLabel}>
                        {t("billing:detail.discount_applied")}
                      </p>
                      <p className={record.monoValue} dir="ltr">
                        {formatMoney(invoice.discount_amount, "en")}
                      </p>
                    </div>
                    <div>
                      <p className={record.fieldLabel}>
                        {t("billing:detail.net_payable")}
                      </p>
                      <p className={record.fieldValue} dir="ltr">
                        {formatMoney(invoice.total, "en")}
                      </p>
                    </div>
                    <div>
                      <p className={record.fieldLabel}>
                        {t("billing:detail.balance_due")}
                      </p>
                      <p className={record.fieldValue} dir="ltr">
                        {formatMoney(balance.toFixed(2), "en")}
                      </p>
                    </div>
                  </div>
                </div>

                <div className={record.card}>
                  <div className={record.cardHead}>
                    <h2 className={record.cardTitle}>
                      {t("billing:detail.lines_title")}
                    </h2>
                  </div>
                  {invoice.items?.length ? (
                    invoice.items.map((item) => (
                      <div key={item.id} className={record.field}>
                        <span className={record.fieldLabel}>
                          {item.description || item.name || "—"}
                        </span>
                        <span className={record.fieldValue} dir="ltr">
                          {item.quantity} × {formatMoney(item.unit_price, "en")}{" "}
                          = {formatMoney(item.line_total, "en")}
                        </span>
                      </div>
                    ))
                  ) : (
                    <p className={record.fieldLabel}>
                      {t("billing:detail.no_items")}
                    </p>
                  )}
                </div>
              </>
            ) : tab === "refund" ? (
              <div className={record.card}>
                <div className={record.cardHead}>
                  <h2 className={record.cardTitle}>
                    {t("billing:detail.kind.refund")}
                  </h2>
                  <span className={record.fieldLabel}>
                    {t("billing:detail.total_settled")}:{" "}
                    <bdi dir="ltr">{formatMoney(invoice.net_paid, "en")}</bdi>
                  </span>
                </div>

                {actionError ? (
                  <div role="alert" className={record.alert}>
                    <AlertCircle
                      className={record.statusIcon}
                      aria-hidden="true"
                    />
                    <span>{actionError}</span>
                  </div>
                ) : null}

                <div className={record.field}>
                  <span className={record.fieldLabel}>
                    {t("common:labels.amount")}
                  </span>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className={styles.input}
                    dir="ltr"
                  />
                </div>

                <div className={record.field}>
                  <span className={record.fieldLabel}>
                    {t("billing:detail.method.cash")}
                  </span>
                  <select
                    value={method}
                    onChange={(e) => setMethod(e.target.value as typeof method)}
                    className={styles.input}
                  >
                    {(
                      [
                        "cash",
                        "card",
                        "bank_transfer",
                        "easypaisa",
                        "jazzcash",
                        "other",
                      ] as const
                    ).map((m) => (
                      <option key={m} value={m}>
                        {t(`billing:detail.method.${m}`)}
                      </option>
                    ))}
                  </select>
                </div>

                <div className={record.field}>
                  <span className={record.fieldLabel}>
                    {t("common:labels.reason")}{" "}
                    <span style={{ color: "var(--color-danger)" }}>*</span>
                  </span>
                  <input
                    type="text"
                    value={reference}
                    onChange={(e) => setReference(e.target.value)}
                    className={styles.input}
                    placeholder={t("common:labels.reason")}
                    required
                  />
                </div>

                <div
                  style={{
                    display: "flex",
                    justifyContent: "center",
                    gap: 10,
                    marginTop: 8,
                  }}
                >
                  <button
                    type="button"
                    disabled={
                      busy ||
                      !amount ||
                      Number(amount) <= 0 ||
                      Number(amount) > Number(invoice.net_paid || 0)
                    }
                    onClick={() => void submitSettle("refund")}
                    className={record.primaryButton}
                  >
                    {t("billing:detail.kind.refund")}
                  </button>
                </div>
              </div>
            ) : tab === "payments" ? (
              <div className={record.card}>
                <div className={record.cardHead}>
                  <h2 className={record.cardTitle}>
                    {t("billing:detail.ledger_title")}
                  </h2>
                </div>
                {invoice.payments?.length ? (
                  invoice.payments.map((p) => (
                    <div key={p.id} className={record.field}>
                      <span className={record.fieldLabel}>
                        {t(`billing:detail.kind.${p.kind}`)}:{" "}
                        {t(`billing:detail.method.${p.method}`)} ·{" "}
                        {new Date(p.created_at).toLocaleString()}
                      </span>
                      <span className={record.fieldValue} dir="ltr">
                        {p.kind === "refund" ? "-" : "+"}
                        {formatMoney(p.amount, "en")}
                      </span>
                      {p.kind === "refund" &&
                      (p.refund_reason || p.reference) ? (
                        <span className={record.fieldLabel}>
                          {t("billing:detail.history_reason")}:{" "}
                          {p.refund_reason || p.reference}
                        </span>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className={record.fieldLabel}>
                    {t("billing:detail.no_payments")}
                  </p>
                )}
              </div>
            ) : tab === "history" ? (
              <div className={record.card}>
                <div className={record.cardHead}>
                  <h2 className={record.cardTitle}>
                    {t("billing:detail.history_title")}
                  </h2>
                </div>
                {historyLoading ? (
                  <p className={record.fieldLabel}>
                    {t("billing:detail.history_loading")}
                  </p>
                ) : historyError ? (
                  <div role="alert" className={record.alert}>
                    <AlertCircle
                      className={record.statusIcon}
                      aria-hidden="true"
                    />
                    <span>{historyError}</span>
                  </div>
                ) : history.length === 0 ? (
                  <p className={record.fieldLabel}>
                    {t("billing:detail.history_empty")}
                  </p>
                ) : (
                  <div className={record.timeline}>
                    {history.map((ev, idx) => (
                      <div
                        key={`${ev.event}-${ev.at}-${idx}`}
                        className={record.event}
                      >
                        <div className={record.eventHead}>
                          <div className={record.eventTitleRow}>
                            <span className={record.dot} aria-hidden="true" />
                            <span className={record.eventTitle}>
                              {t(`billing:detail.event.${ev.event}`)}
                            </span>
                          </div>
                          <span className={record.eventDate}>
                            <bdi dir="ltr">
                              {new Date(ev.at).toLocaleString()}
                            </bdi>
                          </span>
                        </div>
                        <div className={record.note}>
                          {[
                            ev.amount ? formatMoney(ev.amount, "en") : null,
                            ev.actor,
                            ev.reason,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className={record.card}>
                <div className={record.cardHead}>
                  <h2 className={record.cardTitle}>
                    {t("billing:detail.record_payment_title")}
                  </h2>
                  <span className={record.fieldLabel}>
                    {t("billing:detail.balance_due")}:{" "}
                    <bdi dir="ltr">{formatMoney(balance.toFixed(2), "en")}</bdi>
                  </span>
                </div>

                {actionError ? (
                  <div role="alert" className={record.alert}>
                    <AlertCircle
                      className={record.statusIcon}
                      aria-hidden="true"
                    />
                    <span>{actionError}</span>
                  </div>
                ) : null}

                <div className={record.field}>
                  <span className={record.fieldLabel}>
                    {t("common:labels.amount")}
                  </span>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className={styles.input}
                    dir="ltr"
                  />
                </div>

                <div className={record.field}>
                  <span className={record.fieldLabel}>
                    {t("billing:detail.method.cash")}
                  </span>
                  <select
                    value={method}
                    onChange={(e) => setMethod(e.target.value as typeof method)}
                    className={styles.input}
                  >
                    {(
                      [
                        "cash",
                        "card",
                        "bank_transfer",
                        "easypaisa",
                        "jazzcash",
                        "other",
                      ] as const
                    ).map((m) => (
                      <option key={m} value={m}>
                        {t(`billing:detail.method.${m}`)}
                      </option>
                    ))}
                  </select>
                </div>

                <div className={record.field}>
                  <span className={record.fieldLabel}>
                    {t("billing:detail.reference_label")}
                  </span>
                  <input
                    type="text"
                    value={reference}
                    onChange={(e) => setReference(e.target.value)}
                    className={styles.input}
                    dir="ltr"
                  />
                </div>

                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    justifyContent: "center",
                    gap: 10,
                    marginTop: 8,
                    width: "100%",
                  }}
                >
                  <button
                    type="button"
                    disabled={busy || !amount || Number(amount) <= 0}
                    onClick={() => void submitSettle("payment")}
                    className={record.primaryButton}
                  >
                    {t("billing:detail.record_payment_title")}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </VeylaDrawer>
  );
}

export default InvoiceRecordDrawer;
