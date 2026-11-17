import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router-dom";
import { Printer, X } from "lucide-react";

import { billingService } from "./billingService";
import { settingsService } from "../settings/settingsService";
import type { InvoiceDetail } from "./types";
import { formatDateTime, formatMoney, statusLabel } from "../../lib/format";
import { messageForError } from "../../lib/errors";
import { useAuthStore } from "../auth/authStore";
import { canAccessPath, roleHome } from "../auth/access";
import { Code128Barcode } from "../samples/components/Code128Barcode";
import styles from "./InvoicePrintScreen.module.css";

type PrintFormat = "a5" | "thermal";

interface InvoicePrintScreenProps {
  invoiceId: string;
  /** Injectable for tests; production uses the real billing API. */
  service?: typeof billingService;
}

/** px → mm at the CSS 96dpi reference; rounded up so the page never clips. */
function pxToMm(px: number): number {
  return Math.ceil((px * 25.4) / 96);
}

/**
 * Dedicated print window for one invoice: no sidebar, top bar, drawer or any
 * other app chrome, so window.print() emits receipt content only.
 * Default format is A5 portrait; the preview can toggle to 80mm thermal
 * (72mm printable), whose @page height is measured after fonts load.
 */
export function InvoicePrintScreen({
  invoiceId,
  service = billingService,
}: InvoicePrintScreenProps): JSX.Element {
  const { t, i18n } = useTranslation(["billing", "common"]);
  const navigate = useNavigate();
  const accessToken = useAuthStore((state) => state.accessToken);
  const user = useAuthStore((state) => state.user);

  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [branding, setBranding] = useState<{
    labName?: string;
    address?: string | null;
    phone?: string | null;
  }>({});
  const [format, setFormat] = useState<PrintFormat>("a5");
  const [thermalHeightMm, setThermalHeightMm] = useState<number | null>(null);
  const sheetRef = useRef<HTMLDivElement>(null);

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
  }, [invoiceId, service, t]);

  // Tenant lab name from tenant settings; branch directory supplies address
  // and phone. Any failure degrades to the branch name — never to "LabFlow".
  useEffect(() => {
    if (!invoice) return;
    let active = true;
    const loadBranding = async () => {
      let labName: string | undefined;
      let address: string | null = null;
      let phone: string | null = null;
      try {
        const settings = await settingsService.getSettings();
        const raw = settings.brand_display_name?.value;
        if (typeof raw === "string" && raw.trim()) labName = raw.trim();
      } catch {
        // Settings unavailable → the branch name fallback below applies.
      }
      try {
        const branches = await settingsService.getBranches();
        const branch = branches.find((b) => b.id === invoice.branch_id);
        if (branch) {
          address = branch.address;
          phone = branch.phone;
        }
      } catch {
        // Branch directory unavailable → contact lines are simply omitted.
      }
      if (active) setBranding({ labName, address, phone });
    };
    void loadBranding();
    return () => {
      active = false;
    };
  }, [invoice]);

  const balance = useMemo(() => {
    if (!invoice) return 0;
    const total = Number.parseFloat(invoice.total || "0");
    const paid = Number.parseFloat(invoice.net_paid || "0");
    if (!Number.isFinite(total) || !Number.isFinite(paid)) return 0;
    return Math.max(0, total - paid);
  }, [invoice]);

  /**
   * The invoice payload carries no reporting timestamp today; the row is
   * rendered only when a server version that does provide one is in front
   * of us — a value is never invented here.
   */
  const reportingTime = (invoice as { reporting_time?: string | null } | null)
    ?.reporting_time;

  const labName = (branding.labName || invoice?.branch_name || "").trim();

  /**
   * Thermal: measure the rendered sheet (72mm wide, same padding in print)
   * and inject `@page { size: 72mm <measured>mm; margin: 0 }`. `80mm auto`
   * is invalid in Chrome and falls back to A4, so the height is always a
   * measured number — no rule is emitted until it exists.
   */
  const measureThermal = useCallback(() => {
    const el = sheetRef.current;
    if (!el) return;
    const px = el.getBoundingClientRect().height;
    if (!Number.isFinite(px) || px <= 0) return;
    const mm = pxToMm(px);
    setThermalHeightMm((prev) => (prev === mm ? prev : mm));
  }, []);

  useEffect(() => {
    if (format !== "thermal") return;
    measureThermal();
    let alive = true;
    const remeasure = () => {
      if (alive) measureThermal();
    };
    // Fonts (Urdu subsets) and any late-loading assets change the height.
    void document.fonts?.ready.then(remeasure).catch(() => undefined);
    if (document.readyState !== "complete") {
      window.addEventListener("load", remeasure, { once: true });
    }
    const frame = requestAnimationFrame(remeasure);
    return () => {
      alive = false;
      cancelAnimationFrame(frame);
      window.removeEventListener("load", remeasure);
    };
    // Re-run when the receipt content itself can change height.
  }, [format, measureThermal, invoice, branding, i18n.language]);

  const pageRule =
    format === "a5"
      ? "@page { size: A5 portrait; margin: 10mm 10mm 12mm 10mm; }"
      : thermalHeightMm !== null
        ? `@page { size: 72mm ${thermalHeightMm}mm; margin: 0; }`
        : "";

  const handleClose = () => {
    if (window.opener && !window.opener.closed) {
      window.close();
      return;
    }
    navigate("/invoices", { replace: true });
  };

  const sheetClass =
    format === "a5"
      ? `${styles.sheet} ${styles.sheetA5}`
      : `${styles.sheet} ${styles.sheetThermal}`;

  // ---- Guards: same session + billing access as the tenant shell ----
  if (!accessToken || !user) {
    return <Navigate to="/login" replace />;
  }
  if (!canAccessPath(user.role, `/invoices/${invoiceId}/print`)) {
    return <Navigate to={roleHome(user.role)} replace />;
  }

  const toolbar = (
    <div className={`${styles.toolbar} no-print`}>
      <button
        type="button"
        onClick={handleClose}
        className={styles.iconBtn}
        aria-label={t("common:actions.close")}
        title={t("common:actions.close")}
      >
        <X className="w-4 h-4" aria-hidden="true" />
      </button>
      <span className={styles.toolbarTitle} dir="ltr">
        {invoice?.invoice_number || invoiceId.slice(0, 12)}
      </span>
      <div
        className={styles.toggle}
        role="group"
        aria-label={t("billing:detail.print_receipt")}
      >
        <button
          type="button"
          aria-pressed={format === "a5"}
          onClick={() => setFormat("a5")}
          className={`${styles.toggleBtn} ${format === "a5" ? styles.toggleBtnActive : ""}`}
        >
          {t("billing:print.format_a5")}
        </button>
        <button
          type="button"
          aria-pressed={format === "thermal"}
          onClick={() => setFormat("thermal")}
          className={`${styles.toggleBtn} ${format === "thermal" ? styles.toggleBtnActive : ""}`}
        >
          {t("billing:print.format_thermal")}
        </button>
      </div>
      <button
        type="button"
        onClick={() => window.print()}
        disabled={format === "thermal" && thermalHeightMm === null}
        className={styles.printBtn}
      >
        <Printer className="w-4 h-4" aria-hidden="true" />
        <span>{t("billing:detail.print_receipt")}</span>
      </button>
    </div>
  );

  const hint = (
    <p className={`${styles.hint} no-print`}>
      {format === "thermal" && thermalHeightMm === null
        ? t("billing:print.measuring")
        : format === "a5"
          ? t("billing:print.hint_a5")
          : t("billing:print.hint_thermal")}
    </p>
  );

  let body: JSX.Element;
  if (isLoading) {
    body = (
      <div className={styles.centerState} role="status">
        <p>{t("billing:detail.loading")}</p>
      </div>
    );
  } else if (error || !invoice) {
    body = (
      <div className={styles.centerState}>
        <div className={styles.errorCard} role="alert">
          <p className={styles.errorTitle}>
            {t("billing:detail.not_found_title")}
          </p>
          <p className={styles.errorBody}>
            {error || t("billing:detail.not_found_body")}
          </p>
          <button
            type="button"
            onClick={handleClose}
            className={styles.backBtn}
          >
            {t("billing:detail.back_to_invoices")}
          </button>
        </div>
      </div>
    );
  } else {
    body = (
      <>
        {toolbar}
        {hint}
        <div ref={sheetRef} className={sheetClass}>
          <div className={styles.receipt}>
            <header className={styles.header}>
              {labName ? <p className={styles.labName}>{labName}</p> : null}
              {invoice.branch_name ? (
                <p className={styles.branch}>{invoice.branch_name}</p>
              ) : null}
              {branding.address ? (
                <p className={styles.address}>{branding.address}</p>
              ) : null}
              {branding.phone ? (
                <p className={styles.phone} dir="ltr">
                  {branding.phone}
                </p>
              ) : null}
            </header>

            <hr className={styles.divider} />

            <div className={styles.invoiceRow}>
              <span className={styles.invoiceNo} dir="ltr">
                {invoice.invoice_number || invoice.id.slice(0, 12)}
              </span>
              <span className={styles.statusPill}>
                {statusLabel("invoice", invoice.status, (key) =>
                  t(`common:${key}`),
                )}
              </span>
            </div>

            <div className={styles.meta}>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>
                  {t("billing:print.patient_label")}
                </span>
                <span className={styles.metaValue}>
                  {invoice.patient_name || "—"}
                </span>
              </div>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>
                  {t("billing:print.mrn_label")}
                </span>
                <span className={`${styles.metaValue} lf-ltr`}>
                  {invoice.patient_mrn || "—"}
                </span>
              </div>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>
                  {t("billing:print.datetime_label")}
                </span>
                <span className={`${styles.metaValue} lf-ltr`}>
                  {formatDateTime(invoice.created_at)}
                </span>
              </div>
              {reportingTime ? (
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>
                    {t("billing:print.reporting_time_label")}
                  </span>
                  <span className={`${styles.metaValue} lf-ltr`}>
                    {formatDateTime(reportingTime)}
                  </span>
                </div>
              ) : null}
            </div>

            <div className={styles.items}>
              {invoice.items?.length ? (
                invoice.items.map((item) => (
                  <div key={item.id} className={styles.lineItem}>
                    <span className={styles.lineName}>
                      {item.description || item.name || "—"}
                    </span>
                    <span className={`${styles.lineCalc} lf-ltr`}>
                      {item.quantity} × {formatMoney(item.unit_price, "en")} ={" "}
                      {formatMoney(item.line_total, "en")}
                    </span>
                  </div>
                ))
              ) : (
                <p className={styles.emptyItems}>
                  {t("billing:detail.no_items")}
                </p>
              )}
            </div>

            <div className={styles.moneyBlock}>
              <div className={styles.moneyRow}>
                <span>{t("billing:detail.gross_subtotal")}</span>
                <span className="lf-ltr">
                  {formatMoney(invoice.subtotal, "en")}
                </span>
              </div>
              <div className={styles.moneyRow}>
                <span>{t("billing:detail.discount_applied")}</span>
                <span className="lf-ltr">
                  {formatMoney(invoice.discount_amount, "en")}
                </span>
              </div>
              <div className={`${styles.moneyRow} ${styles.moneyRowStrong}`}>
                <span>{t("billing:detail.net_payable")}</span>
                <span className="lf-ltr">
                  {formatMoney(invoice.total, "en")}
                </span>
              </div>
              <div className={styles.moneyRow}>
                <span>{t("billing:print.paid_label")}</span>
                <span className="lf-ltr">
                  {formatMoney(invoice.net_paid, "en")}
                </span>
              </div>
              <div className={styles.moneyRow}>
                <span>{t("billing:detail.balance_due")}</span>
                <span className="lf-ltr">
                  {formatMoney(balance.toFixed(2), "en")}
                </span>
              </div>
            </div>

            <div className={styles.barcodeWrap}>
              <Code128Barcode
                value={invoice.invoice_number || invoice.id}
                height={format === "thermal" ? 30 : 40}
                barWidth={format === "thermal" ? 1 : 2}
                showText
                className={styles.barcode}
              />
            </div>

            <div className={styles.pickup}>
              <p className={styles.pickupEn} dir="ltr">
                {t("billing:print.pickup_en")}
              </p>
              <p className={styles.pickupUr} dir="rtl" lang="ur">
                {t("billing:print.pickup_ur")}
              </p>
            </div>

            <p className={styles.credit}>Software by LabFlow</p>
            <p className={styles.contact} dir="ltr">
              Contact: 0320-6744652
            </p>
          </div>
        </div>
      </>
    );
  }

  return (
    <div className={styles.stage}>
      <style>{`
${pageRule}
@media print {
  html, body { margin: 0 !important; padding: 0 !important; background: #ffffff !important; }
}
`}</style>
      {body}
    </div>
  );
}

export default InvoicePrintScreen;
