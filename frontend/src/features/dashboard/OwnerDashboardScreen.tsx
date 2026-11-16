import type { ReactElement } from "react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { useAuthStore } from "../auth/authStore";
import { FadeValue } from "../../components/ui/FadeValue";
import { partnersService } from "../partners/partnersService";
import { reportsService } from "../reports/reportsService";
import { resultsService } from "../results/resultsService";
import type { ApprovalQueueItem } from "../results/types";
import {
  DashboardDateLine,
  DashboardHeader,
  DashboardLink,
  EmptyState,
  Panel,
  ReviewQueueRing,
  StatCard,
} from "./DashboardUI";
import { ChecksWaffle, type WaffleDay } from "./ChecksWaffle";
import { fetchSampleDayBuckets } from "./sampleDayBuckets";
import { StaffPasswordSection } from "./StaffPasswordSection";
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
  approvalQueue: ApprovalQueueItem[];
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
  approvalQueue: [],
  draftSettlements: null,
  exceptions: null,
};

export function OwnerDashboardScreen(): ReactElement {
  const { t, i18n } = useTranslation("common");
  const navigate = useNavigate();
  const lang = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const [stats, setStats] = useState<DashboardStats>(INITIAL_STATS);
  const accessToken = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);

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
      const dayCounts: Record<string, number> = {};

      if (invoicesResult.status === "fulfilled") {
        const invoices = invoicesResult.value;
        const todayInvoices = invoices.filter((invoice) =>
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

        // Group invoice volume over the last 7 days for the waffle chart
        for (const inv of invoices) {
          if (!inv.created_at) continue;
          const dayKey = inv.created_at.slice(0, 10);
          dayCounts[dayKey] = (dayCounts[dayKey] || 0) + 1;
        }
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
        approvalQueue:
          approvalsResult.status === "fulfilled" &&
          Array.isArray(approvalsResult.value)
            ? approvalsResult.value
            : [],
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

  const greeting = useMemo(() => {
    const name = user?.display_name || user?.name || "Owner";
    return `Welcome back, ${name}`;
  }, [user]);

  // Status mapping for LabFlow real categories
  const statusConfig: Record<string, { label: string; color: string }> = {
    ready: { label: t("status.sample.ready") || "Ready", color: "#0E6B3A" },
    in_process: {
      label: t("status.sample.in_process") || "In Process",
      color: "#8C5800",
    },
    received: {
      label: t("status.sample.received") || "Received",
      color: "#0369A1",
    },
    collected: {
      label: t("status.sample.collected") || "Collected",
      color: "#357C6B",
    },
    rejected: {
      label: t("status.sample.rejected") || "Rejected",
      color: "#B91C1C",
    },
    cancelled: {
      label: t("status.sample.cancelled") || "Cancelled",
      color: "#747C7C",
    },
  };

  // Real per-day sample buckets for the waffle, derived from the existing
  // GET /samples endpoint. No fabricated counts.
  const [range, setRange] = useState<7 | 14 | 30>(7);
  const [waffleDays, setWaffleDays] = useState<WaffleDay[]>([]);
  const [waffleError, setWaffleError] = useState(false);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setWaffleError(false);

    fetchSampleDayBuckets(range, controller.signal)
      .then((buckets) => {
        if (active) setWaffleDays(buckets);
      })
      .catch(() => {
        if (active) setWaffleError(true);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [range]);

  const [activeWaffleDay, setActiveWaffleDay] = useState<WaffleDay | null>(
    null,
  );

  // Side panel defaults to the most recent day that actually has samples.
  const panelDay = useMemo<WaffleDay | null>(() => {
    if (activeWaffleDay) return activeWaffleDay;
    for (let i = waffleDays.length - 1; i >= 0; i--) {
      const day = waffleDays[i];
      if (day && day.total > 0) return day;
    }
    return waffleDays[waffleDays.length - 1] ?? null;
  }, [activeWaffleDay, waffleDays]);

  return (
    <div className="space-y-6">
      {/* Veyla Overview Header */}
      <DashboardHeader
        title={t("dashboard.owner.title") || "Business overview"}
        subtitle={
          <span className="flex items-center gap-2">
            <span>{greeting}</span>
            <span>·</span>
            <DashboardDateLine />
          </span>
        }
        badge={t("dashboard.live_data") || "Live data"}
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => navigate("/samples")}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full font-bold text-xs bg-[var(--veyla-well)] text-[var(--color-text)] hover:bg-[var(--veyla-teal)]/40 transition-colors border border-[var(--color-border)] shadow-sm"
            >
              <span className="material-symbols-outlined text-[16px]">
                colorize
              </span>
              <span>Start a check</span>
            </button>
            <button
              type="button"
              onClick={() => navigate("/reports")}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full font-bold text-xs bg-[var(--veyla-card)] text-[var(--color-text)] hover:bg-[var(--veyla-well)] transition-colors border border-[var(--color-border)] shadow-sm"
            >
              <span className="material-symbols-outlined text-[16px]">
                analytics
              </span>
              <span>Export</span>
            </button>
          </div>
        }
      />

      {/* 4 KPIs as Veyla-Style Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          testId="kpi-invoices-count"
          label={t("dashboard.owner.invoices_label") || "Today's Invoices"}
          value={formatCount(stats.invoicesCount)}
          hint={t("dashboard.owner.day_to_date_batch") || "Day to date"}
          icon="receipt_long"
          animateValue
        />
        <StatCard
          testId="kpi-invoiced-total"
          label={t("dashboard.owner.invoiced_total") || "Invoiced total"}
          value={formatPkr(stats.invoicedTotal, lang)}
          hint="Total billed across branches today"
          icon="payments"
          animateValue
        />
        <StatCard
          testId="kpi-collections-today"
          label={t("dashboard.owner.collections_today") || "Collections today"}
          value={formatPkr(stats.collectionsTotal, lang)}
          hint="Net settled collections today"
          icon="account_balance_wallet"
          tone="success"
          animateValue
        />
        <StatCard
          testId="kpi-pending-approvals"
          label={t("dashboard.stat.pending_approvals") || "Pending Approvals"}
          value={formatCount(stats.pendingApprovals)}
          hint={
            t("dashboard.owner.pending_hint") ||
            "Results awaiting pathologist sign-off"
          }
          icon="verified"
          tone={
            stats.pendingApprovals && stats.pendingApprovals > 0
              ? "warning"
              : "default"
          }
          animateValue
        />
      </div>

      {/* Main Analysis Row: Checks per day Waffle Chart + Fixed Side Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Checks per day (Waffle Chart) */}
        <div className="lg:col-span-2">
          <Panel
            title="Checks per day"
            subtitle="Every tile is a batch of samples. Pick a day to read it."
            action={
              <div
                role="group"
                aria-label="Date range"
                className="flex items-center gap-1 p-1 rounded-full bg-[var(--veyla-well)] border border-[var(--color-border)]"
              >
                {([7, 14, 30] as const).map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => setRange(r)}
                    aria-pressed={range === r}
                    className={`px-3 py-1 rounded-full text-xs font-semibold transition-colors ${
                      range === r
                        ? "bg-[var(--veyla-black)] text-[var(--color-surface)] dark:bg-[var(--color-surface)] dark:text-[var(--veyla-black)]"
                        : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                    }`}
                  >
                    {r} days
                  </button>
                ))}
              </div>
            }
          >
            {waffleError ? (
              <EmptyState message="Sample history unavailable" />
            ) : (
              <ChecksWaffle
                days={waffleDays}
                statusConfig={statusConfig}
                unitLabel="sample"
                onActiveDayChange={setActiveWaffleDay}
              />
            )}
          </Panel>
        </div>

        {/* Fixed Side Panel: Today's Real Breakdown */}
        <div>
          <Panel
            title={panelDay ? panelDay.label : "Samples by status"}
            subtitle={
              panelDay
                ? `${panelDay.total} sample${panelDay.total === 1 ? "" : "s"} collected`
                : "No samples in this range"
            }
          >
            <div className="space-y-2.5">
              {[
                { key: "ready", label: "Passed", color: "var(--veyla-teal)" },
                {
                  key: "review",
                  label: "Review",
                  color: "rgba(18,16,17,0.55)",
                },
                {
                  key: "declined",
                  label: "Declined",
                  color: "var(--veyla-black)",
                },
              ].map((row) => (
                <div
                  key={row.key}
                  className="flex items-center justify-between p-2 rounded-xl bg-[var(--veyla-well)]/60 border border-[var(--color-card-border)] hover:bg-[var(--veyla-well)] transition-colors"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: row.color }}
                      aria-hidden="true"
                    />
                    <span className="text-xs font-semibold text-[var(--color-text)] truncate">
                      {row.label}
                    </span>
                  </div>
                  <span className="text-xs font-mono font-bold text-[var(--color-text)] px-2 py-0.5 rounded-full bg-[var(--veyla-card)] border border-[var(--color-border)]">
                    <FadeValue
                      value={String(
                        panelDay
                          ? (panelDay as unknown as Record<string, number>)[
                              row.key
                            ]
                          : 0,
                      )}
                    />
                  </span>
                </div>
              ))}
              <div className="pt-3 border-t border-[var(--color-card-border)] flex items-center justify-between text-xs text-[var(--color-text-muted)]">
                <span className="font-mono font-bold text-[var(--color-text)]">
                  <FadeValue value={String(panelDay?.total ?? 0)} />
                </span>
                <DashboardLink to="/samples">View samples</DashboardLink>
              </div>
            </div>
          </Panel>
        </div>
      </div>

      {/* Review Queue X/Y Ring + Next Up List */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Review Queue Ring */}
        <div>
          <Panel
            title="Review queue"
            subtitle="Progress through pending result validations"
            action={
              <Link
                to="/results/approvals"
                className="text-xs font-bold text-[var(--color-brand)] hover:underline"
              >
                Open queue →
              </Link>
            }
          >
            <div className="flex flex-col items-center justify-center py-4 text-center">
              <ReviewQueueRing
                pending={stats.pendingApprovals ?? 0}
                total={Math.max(
                  stats.samples?.ready ?? 0,
                  stats.pendingApprovals ?? 0,
                  1,
                )}
                size={130}
              />
              <p className="mt-4 text-xs font-medium text-[var(--color-text-muted)] max-w-xs">
                {stats.pendingApprovals && stats.pendingApprovals > 0
                  ? `${stats.pendingApprovals} results currently require pathologist review and approval.`
                  : "All entered test results are approved and up to date."}
              </p>
            </div>
          </Panel>
        </div>

        {/* Next Up List (Real Data from Wired Queue) */}
        <div className="lg:col-span-2">
          <Panel
            title="Next up"
            subtitle="Prioritized queue items waiting for approval"
            action={
              <DashboardLink to="/results/approvals">
                {t("dashboard.links.open_approvals") || "Open approvals"}
              </DashboardLink>
            }
          >
            {stats.approvalQueue.length > 0 ? (
              <div className="space-y-2">
                {stats.approvalQueue.slice(0, 4).map((item) => (
                  <div
                    key={item.result_id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-xl bg-[var(--veyla-well)]/70 border border-[var(--color-border)] hover:bg-[var(--veyla-well)] transition-colors gap-2"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-xs text-[var(--color-text)]">
                          {item.accession_id}
                        </span>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[#fef3d6] text-[#8c5800] dark:bg-[rgba(232,163,61,0.2)] dark:text-[#f6c776]">
                          Needs Review
                        </span>
                      </div>
                      <p className="text-xs text-[var(--color-text-muted)] mt-0.5 truncate">
                        {item.test_name} · Patient: {item.patient_name}
                      </p>
                    </div>
                    <Link
                      to="/results/approvals"
                      className="self-end sm:self-center px-3 py-1 rounded-full text-xs font-semibold bg-[var(--veyla-black)] text-[var(--color-surface)] dark:bg-[var(--color-surface)] dark:text-[var(--veyla-black)] hover:opacity-90 transition-opacity"
                    >
                      Review
                    </Link>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState message="Review queue is clear. No test results are pending approval." />
            )}
          </Panel>
        </div>
      </div>

      {/* Honest Empty States for Unconfigured Telemetry (Channels & Hourly) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <Panel
          title="Channel breakdown"
          subtitle="Report delivery distribution by channel (WhatsApp, Email, SMS)"
        >
          <EmptyState
            badge="Not configured"
            message="Automated delivery channel metrics are not configured for this tenant. Channel charts will activate once patient notification telemetry is connected."
          />
        </Panel>

        <Panel
          title="Turnaround time by hour"
          subtitle="Specimen receipt-to-result turnaround duration by accession hour"
        >
          <EmptyState
            badge="Not configured"
            message="Hourly turnaround analytics are not configured for this tenant. Telemetry tracking will populate this chart once laboratory instrumentation feeds are active."
          />
        </Panel>
      </div>

      {/* Settlements & Exceptions Management */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        {/* Settlements */}
        <Panel
          title={t("dashboard.owner.settlements") || "Settlements"}
          subtitle={
            t("dashboard.owner.draft_settlements") ||
            "Partner commission settlements"
          }
          action={
            <DashboardLink to="/settlements">
              {t("dashboard.links.review_settlements") || "Review"}
            </DashboardLink>
          }
        >
          <div className="flex items-baseline justify-between py-2">
            <div>
              <span className="text-3xl font-mono font-extrabold text-[var(--color-text)]">
                {formatCount(stats.draftSettlements)}
              </span>
              <p className="text-xs text-[var(--color-text-muted)] mt-1">
                {t("dashboard.owner.counts_only") ||
                  "Draft settlements pending review"}
              </p>
            </div>
          </div>
        </Panel>

        {/* Exceptions */}
        <Panel
          title={t("dashboard.exceptions") || "Exceptions"}
          subtitle="Operational alerts requiring supervisor attention"
          action={
            <DashboardLink to="/exceptions">
              {t("dashboard.view_all") || "View all"}
            </DashboardLink>
          }
        >
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs p-2 rounded-xl bg-[var(--veyla-well)]/70">
              <span className="flex items-center gap-2 text-[var(--color-text)]">
                <span
                  className="w-2 h-2 rounded-full bg-[var(--color-warning)]"
                  aria-hidden="true"
                />
                {stats.exceptions
                  ? t("dashboard.counts.late_transfers", {
                      count: stats.exceptions.lateTransfers,
                    })
                  : t("dashboard.counts.late_transfers_unknown")}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs p-2 rounded-xl bg-[var(--veyla-well)]/70">
              <span className="flex items-center gap-2 text-[var(--color-text)]">
                <span
                  className="w-2 h-2 rounded-full bg-[var(--color-info)]"
                  aria-hidden="true"
                />
                {stats.exceptions
                  ? t("dashboard.counts.failed_deliveries", {
                      count: stats.exceptions.failedDeliveries,
                    })
                  : t("dashboard.counts.failed_deliveries_unknown")}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs p-2 rounded-xl bg-[#fee2e2]/60 dark:bg-[rgba(239,68,68,0.15)] font-bold text-[var(--color-danger)]">
              <span className="flex items-center gap-2">
                <span
                  className="w-2 h-2 rounded-full bg-[var(--color-danger)] animate-ping"
                  aria-hidden="true"
                />
                {stats.exceptions
                  ? t("dashboard.counts.critical_unacknowledged", {
                      count: stats.exceptions.criticalUnacknowledged,
                    })
                  : t("dashboard.counts.critical_unacknowledged_unknown")}
              </span>
              {/* Veyla signature worst flip element */}
              <span className="px-2 py-0.5 rounded-full text-[10px] uppercase font-bold bg-[var(--color-veyla-worst-bg)] text-[var(--color-veyla-worst-text)] shadow-sm">
                Urgent
              </span>
            </div>
          </div>
        </Panel>
      </div>

      {/* Staff Password Section */}
      <StaffPasswordSection />
    </div>
  );
}
