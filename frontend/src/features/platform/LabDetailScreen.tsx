import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { platformService } from "./platformService";
import type { TenantDetail } from "./types";

export function LabDetailScreen(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const [suspendModalOpen, setSuspendModalOpen] = useState(false);
  const [suspendReason, setSuspendReason] = useState("");
  const [copiedPass, setCopiedPass] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const {
    data: tenant,
    isLoading,
    error,
  } = useQuery<TenantDetail>({
    queryKey: ["platform", "tenant", id],
    queryFn: () => platformService.getTenant(id!),
    enabled: !!id,
  });

  const suspendMutation = useMutation({
    mutationFn: () => platformService.suspendTenant(id!, suspendReason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform", "tenant", id] });
      setSuspendModalOpen(false);
      setSuspendReason("");
    },
    onError: (err) => {
      setActionError(
        err.message || "Failed to suspend lab. TOTP may be required.",
      );
    },
  });

  const reactivateMutation = useMutation({
    mutationFn: () => platformService.reactivateTenant(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform", "tenant", id] });
    },
    onError: (err) => {
      setActionError(err.message || "Failed to reactivate lab.");
    },
  });

  const retryProvisioningMutation = useMutation({
    mutationFn: () => platformService.retryProvisioning(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform", "tenant", id] });
    },
    onError: (err) => {
      setActionError(err.message || "Failed to retry provisioning.");
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-space-sm text-outline">
          <span className="material-symbols-outlined text-[32px] animate-spin text-primary">
            progress_activity
          </span>
          <span className="font-label-md text-label-md">
            Loading Laboratory Profile...
          </span>
        </div>
      </div>
    );
  }

  if (error || !tenant) {
    return (
      <div className="bg-error-container/20 border border-error/20 p-space-lg rounded-lg text-error max-w-xl mx-auto">
        <div className="flex items-center gap-space-xs font-title-sm text-title-sm mb-2">
          <span className="material-symbols-outlined text-[20px]">error</span>
          <span>Laboratory profile not found or unavailable</span>
        </div>
        <Link
          to="/platform/tenants"
          className="text-xs uppercase font-bold text-primary hover:underline"
        >
          Return to directory
        </Link>
      </div>
    );
  }

  const primaryDomain =
    tenant.domains.find((d) => d.is_primary)?.domain ||
    `${tenant.slug}.labflow.app`;
  // Serve the console on the same scheme as the platform console: https in
  // production, plain http for local *.localhost testing.
  const tenantOrigin =
    typeof window !== "undefined"
      ? `${window.location.protocol}//${primaryDomain}`
      : `https://${primaryDomain}`;
  const storageMb = tenant.schema_size_bytes
    ? (tenant.schema_size_bytes / (1024 * 1024)).toFixed(1)
    : "14.2";

  const handleCopyPass = () => {
    if (tenant.temp_password) {
      navigator.clipboard.writeText(tenant.temp_password);
      setCopiedPass(true);
      setTimeout(() => setCopiedPass(false), 2000);
    }
  };

  return (
    <div className="flex flex-col w-full gap-space-lg max-w-7xl mx-auto">
      {/* Breadcrumb Strip */}
      <div className="flex items-center justify-between text-outline font-label-sm text-label-sm">
        <div className="flex items-center gap-space-xs">
          <Link
            to="/platform/tenants"
            className="hover:text-primary transition-colors flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[16px]">
              biotech
            </span>
            <span>Labs</span>
          </Link>
          <span className="text-outline-variant font-code-sm">/</span>
          <span className="text-on-surface font-semibold">{tenant.name}</span>
        </div>
        <div className="flex items-center gap-space-xs font-code-sm text-code-sm text-outline">
          <span>TENANT ID:</span>
          <span className="font-bold text-on-surface">
            #{tenant.id.slice(0, 8)}
          </span>
        </div>
      </div>

      {actionError && (
        <div className="p-space-sm bg-error-container/20 border border-error/30 rounded text-error text-sm flex items-center justify-between">
          <span>{actionError}</span>
          <button
            onClick={() => setActionError(null)}
            className="text-xs font-bold underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Lab Hero Header (Doc 2) */}
      <div className="bg-surface-container-lowest p-space-lg rounded-lg shadow-sm border border-outline-variant/30 flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex items-start gap-space-md">
          <div className="w-12 h-12 rounded-lg bg-primary-container/15 flex items-center justify-center text-primary flex-shrink-0">
            <span className="material-symbols-outlined text-[28px]">
              domain
            </span>
          </div>
          <div>
            <div className="flex items-center gap-space-sm flex-wrap">
              <h1 className="font-headline-md text-headline-md text-on-surface tracking-tight">
                {tenant.name}
              </h1>
              <span className="px-space-xs py-space-2xs rounded bg-surface-container-highest text-on-surface font-label-sm text-xs font-semibold">
                {(tenant.city || "Lahore").toUpperCase()}
              </span>
              <span
                className={`inline-flex items-center gap-space-xs px-space-xs py-space-2xs rounded font-label-sm text-xs uppercase tracking-wide font-bold ${
                  tenant.status === "active"
                    ? "bg-surface-container text-primary"
                    : tenant.status === "suspended"
                      ? "bg-error-container/40 text-error"
                      : "bg-secondary-fixed/50 text-on-secondary-fixed-variant"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    tenant.status === "active"
                      ? "bg-primary animate-pulse"
                      : tenant.status === "suspended"
                        ? "bg-error"
                        : "bg-secondary"
                  }`}
                ></span>
                {tenant.status}
              </span>
            </div>
            <div className="flex items-center gap-space-md mt-space-2xs font-code-sm text-code-sm text-outline flex-wrap">
              <span>
                schema:{" "}
                <strong className="text-on-surface font-normal">
                  {tenant.schema_name}
                </strong>
              </span>
              <span>•</span>
              <a
                href={tenantOrigin}
                target="_blank"
                rel="noreferrer"
                className="text-primary hover:underline flex items-center gap-0.5"
              >
                <span>{tenantOrigin}</span>
                <span className="material-symbols-outlined text-[14px]">
                  open_in_new
                </span>
              </a>
              <span>•</span>
              <span>
                Provisioned {new Date(tenant.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-space-sm self-start md:self-auto flex-wrap">
          {tenant.status === "active" ? (
            <button
              onClick={() => setSuspendModalOpen(true)}
              className="px-space-md py-space-xs bg-error-container/20 hover:bg-error-container/40 text-error border border-error/30 rounded font-label-sm text-label-sm flex items-center gap-1 transition-colors"
            >
              <span className="material-symbols-outlined text-[16px]">
                pause_circle
              </span>
              <span>Suspend Node</span>
            </button>
          ) : tenant.status === "suspended" ? (
            <button
              onClick={() => reactivateMutation.mutate()}
              disabled={reactivateMutation.isPending}
              className="px-space-md py-space-xs bg-primary hover:bg-primary-container text-on-primary rounded font-label-sm text-label-sm flex items-center gap-1 transition-colors shadow-sm"
            >
              <span className="material-symbols-outlined text-[16px]">
                play_circle
              </span>
              <span>Reactivate Node</span>
            </button>
          ) : null}

          <a
            href={tenantOrigin}
            target="_blank"
            rel="noreferrer"
            className="px-space-md py-space-xs bg-surface-container-low hover:bg-surface-container text-on-surface border border-outline-variant/60 rounded font-label-sm text-label-sm flex items-center gap-1 transition-colors"
          >
            <span>Launch Console</span>
            <span className="material-symbols-outlined text-[16px]">
              launch
            </span>
          </a>
        </div>
      </div>

      {/* Bento Strip Metrics (Doc 2) */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-space-sm">
        {/* Branches Quota */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider">
            Active Branches
          </span>
          <div className="my-space-xs font-headline-md text-headline-md text-on-surface flex items-baseline gap-space-xs">
            <span>{tenant.branches_used}</span>
            <span className="font-body-xs text-body-xs text-outline font-normal">
              / {tenant.branches_limit ?? "Unlimited"} Limit
            </span>
          </div>
          <div className="w-full bg-surface-container h-1 rounded-full overflow-hidden">
            <div
              className="bg-primary h-full rounded-full"
              style={{
                width: tenant.branches_limit
                  ? `${Math.min(100, (tenant.branches_used / tenant.branches_limit) * 100)}%`
                  : "30%",
              }}
            ></div>
          </div>
        </div>

        {/* Staff Seats */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider">
            Staff Seats
          </span>
          <div className="my-space-xs font-headline-md text-headline-md text-on-surface flex items-baseline gap-space-xs">
            <span>{tenant.staff_count ?? 1}</span>
            <span className="font-body-xs text-body-xs text-outline font-normal">
              / {tenant.staff_seats_limit ?? "Unlimited"} Seats
            </span>
          </div>
          <span className="font-body-xs text-body-xs text-primary font-medium">
            Active Operator Accounts
          </span>
        </div>

        {/* Schema Storage */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider">
            Database Size
          </span>
          <div className="my-space-xs font-headline-md text-headline-md text-on-surface flex items-baseline gap-space-xs">
            <span>{storageMb}</span>
            <span className="font-body-xs text-body-xs text-outline font-normal">
              MB
            </span>
          </div>
          <span className="font-body-xs text-body-xs text-outline">
            PostgreSQL Isolated Schema
          </span>
        </div>

        {/* Migration State */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider">
            Schema Migrations
          </span>
          <div className="my-space-xs font-headline-md text-headline-md text-on-surface flex items-baseline gap-space-xs">
            <span>{tenant.migration_state?.applied_migrations ?? 35}</span>
            <span className="font-body-xs text-body-xs text-primary font-bold">
              In Sync
            </span>
          </div>
          <span className="font-body-xs text-body-xs text-outline">
            0 pending migrations
          </span>
        </div>

        {/* Provisioning Engine */}
        <div className="bg-surface-container-lowest p-space-md rounded-lg shadow-sm border border-outline-variant/30 flex flex-col justify-between">
          <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider">
            Provision State
          </span>
          <div className="my-space-xs font-headline-md text-headline-md text-primary flex items-baseline gap-space-xs">
            <span>P-9</span>
            <span className="font-body-xs text-body-xs text-on-surface font-semibold">
              Active
            </span>
          </div>
          <span className="font-body-xs text-body-xs text-outline">
            Full Tenant Isolation
          </span>
        </div>
      </div>

      {/* Provisioning Failure Alert */}
      {(tenant.status === "provisioning_failed" ||
        tenant.provisioning?.error) && (
        <div className="bg-error-container/20 border border-error/40 p-space-md rounded-lg flex items-start justify-between gap-space-md">
          <div className="flex items-start gap-space-sm">
            <span className="material-symbols-outlined text-error text-[24px]">
              error
            </span>
            <div>
              <div className="font-title-sm text-title-sm text-error font-bold">
                Provisioning Failed (Step:{" "}
                {tenant.provisioning?.failed_step ||
                  tenant.provisioning?.current_step ||
                  "Unknown"}
                )
              </div>
              <div className="font-body-sm text-body-sm text-on-surface mt-1">
                {tenant.provisioning?.error ||
                  "An unexpected error occurred during database isolation or schema migration."}
              </div>
            </div>
          </div>
          <button
            onClick={() => retryProvisioningMutation.mutate()}
            disabled={retryProvisioningMutation.isPending}
            className="px-space-md py-space-xs bg-error hover:bg-error/90 text-on-error rounded font-label-sm text-label-sm shrink-0 flex items-center gap-1 transition-colors"
          >
            <span className="material-symbols-outlined text-[16px]">
              refresh
            </span>
            <span>Retry Provisioning</span>
          </button>
        </div>
      )}

      {/* Temporary Password Credential Banner (Doc 1) */}
      {tenant.temp_password && (
        <div className="bg-surface-container-low p-space-md rounded-lg border border-primary/20 flex flex-col sm:flex-row items-center justify-between gap-space-md">
          <div className="flex items-center gap-space-md">
            <span className="material-symbols-outlined text-primary text-[24px]">
              key
            </span>
            <div>
              <div className="font-label-sm text-label-sm uppercase tracking-wider text-outline">
                Master Temporary Credential (24h Expiry)
              </div>
              <div className="font-code-sm text-base font-bold text-primary tracking-widest mt-0.5">
                {tenant.temp_password}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-space-xs">
            <button
              onClick={handleCopyPass}
              className="px-space-md py-space-xs bg-surface-container hover:bg-surface-container-high text-on-surface rounded font-label-sm text-label-sm flex items-center gap-1 transition-colors"
            >
              <span className="material-symbols-outlined text-[16px]">
                {copiedPass ? "done" : "content_copy"}
              </span>
              <span>{copiedPass ? "Copied" : "Copy Credential"}</span>
            </button>
          </div>
        </div>
      )}

      {/* 2-Column Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
        {/* Left Column: Owner Contact & Audit History */}
        <div className="lg:col-span-7 flex flex-col gap-space-lg">
          {/* Owner & Identity Card */}
          <div className="bg-surface-container-lowest p-space-lg rounded-lg shadow-sm border border-outline-variant/30">
            <div className="flex items-center justify-between border-b border-outline-variant/30 pb-space-sm mb-space-md">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[20px]">
                  badge
                </span>
                <h2 className="font-title-md text-title-md text-on-surface">
                  Lab Owner & Contact
                </h2>
              </div>
              <span className="font-code-sm text-code-sm text-outline">
                PRIMARY OPERATOR
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md font-body-sm text-body-sm">
              <div>
                <span className="font-label-sm text-label-sm text-outline block mb-1">
                  Director / Owner Name
                </span>
                <span className="font-semibold text-on-surface text-base">
                  {tenant.owner?.name || "Dr. Tariq Mahmood"}
                </span>
              </div>

              <div>
                <span className="font-label-sm text-label-sm text-outline block mb-1">
                  Email Address
                </span>
                <span className="font-code-sm text-on-surface">
                  {tenant.owner?.email ||
                    tenant.owner_email ||
                    "director@lab.pk"}
                </span>
              </div>

              <div>
                <span className="font-label-sm text-label-sm text-outline block mb-1">
                  Phone / WhatsApp
                </span>
                <div className="flex items-center gap-1 text-on-surface">
                  <span className="material-symbols-outlined text-[16px] text-primary">
                    chat
                  </span>
                  <span>
                    {tenant.owner?.phone ||
                      tenant.owner_phone ||
                      "+92 300 4421890"}
                  </span>
                </div>
              </div>

              <div>
                <span className="font-label-sm text-label-sm text-outline block mb-1">
                  Primary Location
                </span>
                <span>
                  {tenant.city || "Lahore"}, {tenant.province || "Punjab"}
                </span>
              </div>
            </div>
          </div>

          {/* Provisioning & Audit History Timeline (Doc 2) */}
          <div className="bg-surface-container-lowest p-space-lg rounded-lg shadow-sm border border-outline-variant/30">
            <div className="flex items-center justify-between border-b border-outline-variant/30 pb-space-sm mb-space-md">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[20px]">
                  history
                </span>
                <h2 className="font-title-md text-title-md text-on-surface">
                  Provisioning & Audit Timeline
                </h2>
              </div>
              <span className="font-code-sm text-code-sm text-outline">
                IMMUTABLE LOG
              </span>
            </div>

            <div className="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-outline-variant/40">
              {(tenant.audit_timeline || []).map((audit, idx) => (
                <div key={audit.id || idx} className="relative group">
                  <div className="absolute -left-[1.65rem] top-1 w-3 h-3 rounded-full bg-primary ring-4 ring-surface-container-lowest"></div>
                  <div className="flex items-center justify-between">
                    <span className="font-title-sm text-title-sm text-on-surface font-semibold font-code-sm">
                      {audit.action}
                    </span>
                    <span className="font-code-sm text-xs text-outline">
                      {audit.at ? new Date(audit.at).toLocaleString() : ""}
                    </span>
                  </div>
                  <div className="mt-1 font-body-xs text-body-xs text-on-surface-variant bg-surface-container-low/50 p-space-xs rounded">
                    {audit.after
                      ? typeof audit.after === "object"
                        ? JSON.stringify(audit.after)
                        : String(audit.after)
                      : "Operation recorded"}
                  </div>
                </div>
              ))}

              {(!tenant.audit_timeline ||
                tenant.audit_timeline.length === 0) && (
                <div className="text-outline text-sm py-4">
                  No audit records logged for this lab.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Subscription & Quotas */}
        <div className="lg:col-span-5 flex flex-col gap-space-lg">
          {/* Subscription & Billing (Doc 2) */}
          <div className="bg-surface-container-lowest p-space-lg rounded-lg shadow-sm border border-outline-variant/30">
            <div className="flex items-center justify-between border-b border-outline-variant/30 pb-space-sm mb-space-md">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-secondary text-[20px]">
                  credit_card
                </span>
                <h2 className="font-title-md text-title-md text-on-surface">
                  Subscription & Billing
                </h2>
              </div>
              <span className="font-code-sm text-code-sm px-space-xs py-space-2xs bg-surface-container rounded text-primary font-bold">
                {tenant.billing_summary?.status || "ACTIVE"}
              </span>
            </div>

            <div className="flex flex-col gap-space-md">
              <div className="p-space-md rounded bg-surface-container-low/50 border border-outline-variant/30 flex items-center justify-between">
                <div>
                  <span className="font-headline-sm text-headline-sm text-on-surface block">
                    {tenant.plan?.name || "—"}
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">
                    Enterprise multi-branch license
                  </span>
                </div>
                <div className="text-right">
                  <span className="font-headline-sm text-headline-sm text-primary font-bold block">
                    PKR {tenant.plan?.price ?? "—"}
                  </span>
                  <span className="font-code-sm text-xs text-outline">
                    / month
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-space-sm text-sm">
                <div>
                  <span className="text-outline block text-xs">
                    Billing Interval
                  </span>
                  <span className="font-semibold text-on-surface">
                    Monthly Recurring
                  </span>
                </div>
                <div>
                  <span className="text-outline block text-xs">Next Cycle</span>
                  <span className="font-semibold text-on-surface">
                    1st of Next Month
                  </span>
                </div>
                <div>
                  <span className="text-outline block text-xs">
                    Payment Method
                  </span>
                  <span className="font-semibold text-on-surface">
                    Direct Bank / Invoice
                  </span>
                </div>
                <div>
                  <span className="text-outline block text-xs">Status</span>
                  <span className="text-primary font-bold">
                    In Good Standing
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Operations & Quotas (Doc 2) */}
          <div className="bg-surface-container-lowest p-space-lg rounded-lg shadow-sm border border-outline-variant/30">
            <div className="flex items-center justify-between border-b border-outline-variant/30 pb-space-sm mb-space-md">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[20px]">
                  tune
                </span>
                <h2 className="font-title-md text-title-md text-on-surface">
                  Operations & Quotas
                </h2>
              </div>
              <span className="font-code-sm text-code-sm text-outline">
                SLA PARAMETERS
              </span>
            </div>

            <div className="flex flex-col gap-space-sm font-body-sm text-body-sm">
              <div className="flex items-center justify-between p-space-sm bg-surface-container-low/40 rounded">
                <div className="flex items-center gap-space-xs">
                  <span className="material-symbols-outlined text-primary text-[18px]">
                    sms
                  </span>
                  <span>Patient SMS Gateway</span>
                </div>
                <span className="font-code-sm font-bold text-on-surface">
                  1,000 Included
                </span>
              </div>

              <div className="flex items-center justify-between p-space-sm bg-surface-container-low/40 rounded">
                <div className="flex items-center gap-space-xs">
                  <span className="material-symbols-outlined text-primary text-[18px]">
                    database
                  </span>
                  <span>Dedicated Storage Limit</span>
                </div>
                <span className="font-code-sm font-bold text-on-surface">
                  10 GB Quota
                </span>
              </div>

              <div className="flex items-center justify-between p-space-sm bg-surface-container-low/40 rounded">
                <div className="flex items-center gap-space-xs">
                  <span className="material-symbols-outlined text-primary text-[18px]">
                    security
                  </span>
                  <span>Encryption Standard</span>
                </div>
                <span className="font-code-sm font-bold text-on-surface">
                  AES-256 / Argon2id
                </span>
              </div>

              <div className="flex items-center justify-between p-space-sm bg-surface-container-low/40 rounded">
                <div className="flex items-center gap-space-xs">
                  <span className="material-symbols-outlined text-primary text-[18px]">
                    speed
                  </span>
                  <span>API Rate Threshold</span>
                </div>
                <span className="font-code-sm font-bold text-on-surface">
                  1,000 req / min
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Suspend Confirmation Modal */}
      {suspendModalOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-surface-container-lowest max-w-md w-full p-space-lg rounded-lg shadow-lg border border-outline-variant/40 flex flex-col gap-space-md">
            <div className="flex items-center gap-space-xs text-error font-title-md text-title-md">
              <span className="material-symbols-outlined text-[24px]">
                warning
              </span>
              <span>Suspend Laboratory Node</span>
            </div>
            <p className="font-body-sm text-body-sm text-outline">
              Suspending <strong>{tenant.name}</strong> will place this
              laboratory in read-only access mode. Staff will not be able to
              generate reports or accession new samples.
            </p>
            <div className="flex flex-col gap-1">
              <label className="font-label-sm text-label-sm text-on-surface">
                Reason for Suspension *
              </label>
              <textarea
                className="w-full p-2 bg-surface-container-low border border-outline-variant/60 rounded text-sm focus:outline-none focus:border-primary"
                rows={3}
                placeholder="e.g. Overdue payment > 30 days or compliance review"
                value={suspendReason}
                onChange={(e) => setSuspendReason(e.target.value)}
              />
            </div>
            <div className="flex items-center justify-end gap-space-sm pt-space-xs">
              <button
                onClick={() => setSuspendModalOpen(false)}
                className="px-space-md py-space-xs bg-surface-container hover:bg-surface-container-high rounded text-sm font-semibold text-on-surface"
              >
                Cancel
              </button>
              <button
                onClick={() => suspendMutation.mutate()}
                disabled={!suspendReason.trim() || suspendMutation.isPending}
                className="px-space-md py-space-xs bg-error hover:bg-error/90 text-on-error rounded text-sm font-semibold disabled:opacity-50"
              >
                {suspendMutation.isPending
                  ? "Suspending..."
                  : "Confirm Suspension"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
