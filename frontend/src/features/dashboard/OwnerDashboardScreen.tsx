import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAuthStore } from "../auth/authStore";
import { partnersService } from "../partners/partnersService";
import { reportsService } from "../reports/reportsService";
import { resultsService } from "../results/resultsService";
import { DashboardDateLine } from "./DashboardUI";
import { StaffPasswordSection } from "./StaffPasswordSection";
import styles from "./OwnerDashboardScreen.module.css";
import {
  fetchSampleStatusCounts,
  formatCount,
  formatPkr,
  isTodayInPkt,
  listAllInvoices,
  type SampleStatusCounts,
} from "./dashboardService";

interface DashboardStats {
  invoicesCount: number | null;
  invoicedTotal: number | null;
  collectionsTotal: number | null;
  samples: SampleStatusCounts | null;
  pendingApprovals: number | null;
  draftSettlements: number | null;
  exceptions: {
    total: number;
    lateTransfers: number;
    failedDeliveries: number;
    criticalUnacknowledged: number;
  } | null;
}

const INITIAL_STATS: DashboardStats = {
  invoicesCount: null,
  invoicedTotal: null,
  collectionsTotal: null,
  samples: null,
  pendingApprovals: null,
  draftSettlements: null,
  exceptions: null,
};

export function OwnerDashboardScreen(): ReactElement {
  const { t, i18n } = useTranslation("common");
  const lang = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const [stats, setStats] = useState<DashboardStats>(INITIAL_STATS);
  const accessToken = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    const loadRealData = async () => {
      if (!accessToken) return;

      const [
        invoicesResult,
        samplesResult,
        approvalsResult,
        settlementsResult,
        exceptionsResult,
      ] = await Promise.allSettled([
        listAllInvoices({ signal: controller.signal }),
        fetchSampleStatusCounts(controller.signal),
        resultsService.getApprovalsQueue(controller.signal),
        partnersService.getSettlements({
          status: "draft",
          signal: controller.signal,
        }),
        reportsService.getExceptions(controller.signal),
      ]);

      if (!active) return;

      let invoicesCount: number | null = null;
      let invoicedTotal: number | null = null;
      let collectionsTotal: number | null = null;
      if (invoicesResult.status === "fulfilled") {
        const todayInvoices = invoicesResult.value.filter((invoice) =>
          isTodayInPkt(invoice.created_at),
        );
        invoicesCount = todayInvoices.length;
        invoicedTotal = todayInvoices.reduce(
          (sum, invoice) => sum + Number.parseFloat(invoice.total || "0"),
          0,
        );
        const paidRows = todayInvoices
          .map((invoice) =>
            invoice.net_paid === undefined || invoice.net_paid === null
              ? null
              : Number.parseFloat(invoice.net_paid),
          )
          .filter((value): value is number => value !== null);
        collectionsTotal =
          paidRows.length === todayInvoices.length
            ? paidRows.reduce((sum, value) => sum + value, 0)
            : null;
      }

      setStats({
        invoicesCount,
        invoicedTotal,
        collectionsTotal,
        samples:
          samplesResult.status === "fulfilled" ? samplesResult.value : null,
        pendingApprovals:
          approvalsResult.status === "fulfilled"
            ? approvalsResult.value.length
            : null,
        draftSettlements:
          settlementsResult.status === "fulfilled"
            ? (settlementsResult.value.results?.length ?? 0)
            : null,
        exceptions:
          exceptionsResult.status === "fulfilled" &&
          exceptionsResult.value?.counts
            ? {
                total: exceptionsResult.value.counts.total || 0,
                lateTransfers: exceptionsResult.value.counts.late_transfer || 0,
                failedDeliveries:
                  exceptionsResult.value.counts.failed_delivery || 0,
                criticalUnacknowledged:
                  exceptionsResult.value.counts.critical_unacknowledged || 0,
              }
            : null,
      });
    };

    void loadRealData();

    return () => {
      active = false;
      controller.abort();
    };
  }, [accessToken]);

  const sampleRows = [
    {
      key: "collected",
      label: t("status.sample.collected"),
      value: stats.samples?.collected,
      dot: styles.dotInfo,
    },
    {
      key: "received",
      label: t("status.sample.received"),
      value: stats.samples?.received,
      dot: styles.dotInfo,
    },
    {
      key: "in_process",
      label: t("status.sample.in_process"),
      value: stats.samples?.inProcess,
      dot: styles.dotWarning,
    },
    {
      key: "ready",
      label: t("status.sample.ready"),
      value: stats.samples?.ready,
      dot: styles.dotSuccess,
    },
    {
      key: "rejected",
      label: t("status.sample.rejected"),
      value: stats.samples?.rejected,
      dot: styles.dotDanger,
    },
    {
      key: "cancelled",
      label: t("status.sample.cancelled"),
      value: stats.samples?.cancelled,
      dot: styles.dotMuted,
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>{t("dashboard.owner.title")}</h1>
            <p className={styles.subtitle}>
              <DashboardDateLine />
            </p>
          </div>
          <span className={styles.liveBadge}>
            <span className={styles.liveDot} aria-hidden="true" />
            {t("dashboard.live_data")}
          </span>
        </div>

        <div className={styles.grid}>
          <div className={`${styles.card} ${styles.cardWide}`}>
            <div>
              <div className={styles.cardTitleRow}>
                <h2 className={styles.cardTitle}>
                  {t("dashboard.owner.today_business")}
                </h2>
                <span className={styles.pill}>
                  {t("dashboard.owner.day_to_date_batch")}
                </span>
              </div>
              <div className={styles.rows}>
                <div className={styles.row}>
                  <span className={styles.rowLabel}>
                    {t("dashboard.owner.invoices_label")}
                  </span>
                  <span className={styles.rowValue}>
                    {formatCount(stats.invoicesCount)}
                  </span>
                </div>
                <div className={styles.row}>
                  <span className={styles.rowLabel}>
                    {t("dashboard.owner.invoiced_total")}
                  </span>
                  <span className={styles.moneyValue}>
                    {formatPkr(stats.invoicedTotal, lang)}
                  </span>
                </div>
                <div className={styles.row}>
                  <span className={styles.rowLabel}>
                    {t("dashboard.owner.collections_today")}
                  </span>
                  <span className={styles.moneyValue}>
                    {formatPkr(stats.collectionsTotal, lang)}
                  </span>
                </div>
              </div>
            </div>
            <div className={styles.footer}>
              <Trans
                i18nKey="dashboard.owner.business_footer"
                components={{ zone: <bdi dir="ltr" /> }}
              />
            </div>
          </div>

          <div className={styles.card}>
            <div>
              <div className={styles.cardTitleRow}>
                <h2 className={styles.cardTitle}>
                  {t("dashboard.samples_by_status")}
                </h2>
              </div>
              {stats.samples ? (
                <div className={styles.samples}>
                  {sampleRows.map((row) => (
                    <div key={row.key} className={styles.sampleRow}>
                      <span className={styles.sampleLabel}>
                        <span
                          aria-hidden="true"
                          className={`${styles.dot} ${row.dot}`}
                        />
                        {row.label}
                      </span>
                      <span className={styles.sampleValue}>{row.value}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className={styles.hint}>
                  {t("dashboard.unavailable.samples")}
                </p>
              )}
            </div>
            <div className={styles.footer}>
              {stats.samples ? (
                <Trans
                  i18nKey="dashboard.samples.total_accessions_scope"
                  values={{ total: stats.samples.total }}
                  components={{ acc: <bdi dir="ltr" /> }}
                />
              ) : (
                t("dashboard.samples.totals_unavailable")
              )}
            </div>
          </div>

          <div className={styles.card}>
            <div>
              <div className={styles.cardTitleRow}>
                <h2 className={styles.cardTitle}>
                  {t("dashboard.stat.pending_approvals")}
                </h2>
              </div>
              <div className={styles.cardTitleRow}>
                <span className={styles.bigNumber}>
                  {formatCount(stats.pendingApprovals)}
                </span>
                <span
                  className={`${styles.statusBadge} ${styles.statusWarning}`}
                >
                  <span className={styles.badgeIcon} aria-hidden="true" />
                  {t("dashboard.owner.review_badge")}
                </span>
              </div>
              <p className={styles.hint}>{t("dashboard.owner.pending_hint")}</p>
            </div>
            <Link to="/results/approvals" className={styles.link}>
              <span>{t("dashboard.links.open_approvals")}</span>
              <span className={styles.linkArrow} aria-hidden="true">
                →
              </span>
            </Link>
          </div>

          <div className={styles.card}>
            <div>
              <div className={styles.cardTitleRow}>
                <h2 className={styles.cardTitle}>
                  {t("dashboard.owner.settlements")}
                </h2>
              </div>
              <div className={styles.bigNumber}>
                {formatCount(stats.draftSettlements)}
              </div>
              <p className={styles.hint}>
                {t("dashboard.owner.draft_settlements")}
              </p>
              <p className={styles.footer}>
                {t("dashboard.owner.counts_only")}
              </p>
            </div>
            <Link to="/settlements" className={styles.link}>
              <span>{t("dashboard.links.review_settlements")}</span>
              <span className={styles.linkArrow} aria-hidden="true">
                →
              </span>
            </Link>
          </div>

          <div className={styles.card}>
            <div>
              <div className={styles.cardTitleRow}>
                <h2 className={styles.cardTitle}>
                  {t("dashboard.exceptions")}
                </h2>
                <span
                  className={`${styles.statusBadge} ${styles.statusDanger}`}
                >
                  <span className={styles.badgeIcon} aria-hidden="true" />
                  {t("dashboard.requires_action")}
                </span>
              </div>
              <div className={styles.bigNumber}>
                {formatCount(stats.exceptions?.total ?? null)}
              </div>
              <div className={styles.exceptions}>
                <div className={styles.exceptionRow}>
                  <span className={styles.exceptionDot} aria-hidden="true" />
                  <span>
                    {stats.exceptions
                      ? t("dashboard.counts.late_transfers", {
                          count: stats.exceptions.lateTransfers,
                        })
                      : t("dashboard.counts.late_transfers_unknown")}
                  </span>
                </div>
                <div className={styles.exceptionRow}>
                  <span className={styles.exceptionDot} aria-hidden="true" />
                  <span>
                    {stats.exceptions
                      ? t("dashboard.counts.failed_deliveries", {
                          count: stats.exceptions.failedDeliveries,
                        })
                      : t("dashboard.counts.failed_deliveries_unknown")}
                  </span>
                </div>
                <div
                  className={`${styles.exceptionRow} ${styles.exceptionCritical}`}
                >
                  <span
                    className={`${styles.exceptionDot} ${styles.exceptionDotCritical}`}
                    aria-hidden="true"
                  />
                  <span>
                    {stats.exceptions
                      ? t("dashboard.counts.critical_unacknowledged", {
                          count: stats.exceptions.criticalUnacknowledged,
                        })
                      : t("dashboard.counts.critical_unacknowledged_unknown")}
                  </span>
                </div>
              </div>
            </div>
            <Link to="/exceptions" className={styles.link}>
              <span>{t("dashboard.view_all")}</span>
              <span className={styles.linkArrow} aria-hidden="true">
                →
              </span>
            </Link>
          </div>
        </div>

        <StaffPasswordSection />
      </div>
    </div>
  );
}
