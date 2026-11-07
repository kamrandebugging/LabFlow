import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { platformService } from "./platformService";
import { TotpConfirmModal } from "./TotpConfirmModal";
import type {
  SubscriptionDetailData,
  SubscriptionPaymentRecord,
  TenantPlan,
} from "./types";

export function SubscriptionDetailScreen() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const [sub, setSub] = useState<SubscriptionDetailData | null>(null);
  const [payments, setPayments] = useState<SubscriptionPaymentRecord[]>([]);
  const [availablePlans, setAvailablePlans] = useState<TenantPlan[]>([]);

  // Mark Paid form state
  const [paymentMethod, setPaymentMethod] = useState("Bank Transfer (Raast / IBFT)");
  const [reference, setReference] = useState("");
  const [amount, setAmount] = useState("");
  const [notes, setNotes] = useState("");
  const [markPaidModalOpen, setMarkPaidModalOpen] = useState(false);
  const [markPaidLoading, setMarkPaidLoading] = useState(false);
  const [markPaidError, setMarkPaidError] = useState<string | null>(null);

  // Change Plan state
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [changePlanModalOpen, setChangePlanModalOpen] = useState(false);
  const [changePlanLoading, setChangePlanLoading] = useState(false);
  const [changePlanError, setChangePlanError] = useState<string | null>(null);

  const loadDetail = async () => {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const res = await platformService.getSubscription(id);
      setSub(res.subscription);
      setPayments(res.payments);
      setAvailablePlans(res.available_plans);
      setSelectedPlanId(res.subscription.plan_id);
      setAmount(res.subscription.plan_price);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load subscription.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDetail();
  }, [id]);

  const handleMarkPaid = async (totpCode: string) => {
    if (!id) return;
    if (!reference.trim()) {
      setMarkPaidError("Transaction reference number is required.");
      return;
    }
    if (!amount || parseFloat(amount) <= 0) {
      setMarkPaidError("Please enter a valid payment amount.");
      return;
    }

    try {
      setMarkPaidLoading(true);
      setMarkPaidError(null);
      const res = await platformService.markSubscriptionPaid(
        id,
        {
          method: paymentMethod,
          reference: reference.trim(),
          amount: amount.trim(),
          notes: notes.trim(),
        },
        totpCode
      );
      setMarkPaidModalOpen(false);
      setActionSuccess(res.detail || "Payment recorded and subscription refreshed.");
      setReference("");
      setNotes("");
      loadDetail();
    } catch (e: unknown) {
      setMarkPaidError(e instanceof Error ? e.message : "Payment recording failed.");
    } finally {
      setMarkPaidLoading(false);
    }
  };

  const handleChangePlan = async (totpCode: string) => {
    if (!id || !selectedPlanId) return;
    try {
      setChangePlanLoading(true);
      setChangePlanError(null);
      const res = await platformService.changeSubscriptionPlan(id, selectedPlanId, totpCode);
      setChangePlanModalOpen(false);
      setActionSuccess(res.detail || "Plan changed successfully.");
      loadDetail();
    } catch (e: unknown) {
      setChangePlanError(e instanceof Error ? e.message : "Plan change failed.");
    } finally {
      setChangePlanLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="p-16 text-center text-outline">
        <span className="inline-block w-8 h-8 border-2 border-primary/20 border-t-primary rounded-full animate-spin mb-3" />
        <p className="font-body-md text-body-md font-semibold">Loading subscription record...</p>
      </div>
    );
  }

  if (error || !sub) {
    return (
      <div className="p-12 text-center bg-surface-container-lowest rounded shadow-sm max-w-xl mx-auto mt-8">
        <span className="material-symbols-outlined text-error text-[40px] mb-2">error</span>
        <h2 className="font-headline-sm text-headline-sm text-on-surface mb-2">Unable to Load Subscription</h2>
        <p className="font-body-sm text-body-sm text-outline mb-4">{error || "Record not found."}</p>
        <Link
          to="/platform/subscriptions"
          className="px-4 py-2 bg-primary text-on-primary font-label-sm text-label-sm rounded hover:bg-primary-container"
        >
          Return to Subscriptions
        </Link>
      </div>
    );
  }

  const isOverdue = sub.status === "past_due";

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Context Header & Actions */}
      <div className="flex flex-col gap-space-sm bg-surface-container-lowest p-space-lg rounded shadow-sm">
        <div className="flex items-center justify-between flex-wrap gap-space-sm">
          <div className="flex items-center gap-space-xs text-outline font-code-sm text-code-sm">
            <Link to="/platform/subscriptions" className="hover:text-primary transition-colors">
              Subscriptions
            </Link>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="text-on-surface font-semibold">{sub.tenant_name}</span>
          </div>

          <div className="flex items-center gap-space-xs">
            <button
              onClick={() => navigate("/platform/subscriptions")}
              className="h-8 px-space-sm bg-surface-container-low hover:bg-surface-container text-on-surface rounded font-label-sm text-label-sm flex items-center gap-1 transition-colors"
            >
              <span className="material-symbols-outlined text-[16px]">arrow_back</span>
              Back to Subscriptions
            </button>
            <Link
              to={`/platform/tenants/${sub.tenant_id}`}
              className="h-8 px-space-sm bg-surface-container-high hover:bg-surface-container-highest text-on-surface-variant rounded font-label-sm text-label-sm flex items-center gap-1 transition-colors"
            >
              <span className="material-symbols-outlined text-[16px]">domain</span>
              View Lab Detail
            </Link>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-space-md pt-space-xs border-t border-surface-container">
          <div className="flex flex-wrap items-center gap-space-sm">
            <h1 className="font-headline-lg text-headline-lg text-on-surface font-extrabold tracking-tight">
              Subscription Management — {sub.tenant_name}
            </h1>
            <span className="bg-surface-container-high text-primary font-label-sm text-label-sm uppercase px-space-sm py-space-2xs rounded font-bold">
              {sub.plan_name}
            </span>
            {isOverdue ? (
              <span className="bg-error-container text-on-error-container font-label-sm text-label-sm uppercase px-space-sm py-space-2xs rounded font-bold flex items-center gap-space-2xs">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-error" />
                OVERDUE
              </span>
            ) : sub.status === "active" ? (
              <span className="bg-primary-fixed text-on-primary-fixed font-label-sm text-label-sm uppercase px-space-sm py-space-2xs rounded font-bold flex items-center gap-space-2xs">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary" />
                ACTIVE / CURRENT
              </span>
            ) : (
              <span className="bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm uppercase px-space-sm py-space-2xs rounded font-bold">
                {sub.status}
              </span>
            )}
            {sub.is_founding && (
              <span className="bg-secondary-container text-on-secondary-fixed font-code-sm text-xs px-2 py-0.5 rounded font-extrabold uppercase">
                Founding Member 10
              </span>
            )}
          </div>
        </div>
      </div>

      {actionSuccess && (
        <div className="p-space-md bg-primary-fixed/30 border border-primary text-primary-container rounded flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[20px]">check_circle</span>
            <span className="font-title-sm text-title-sm font-semibold">{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} className="text-on-surface-variant hover:text-on-surface">
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>
      )}

      {/* Main Top Grid: Section A (Overview) & Section B (Mark Paid Clinical Console) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        {/* Section A: Overview & Quota Utilization (7 Columns) */}
        <div className="lg:col-span-7 flex flex-col gap-space-md bg-surface-container-lowest p-space-lg rounded shadow-sm">
          <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
            <div className="flex items-center gap-space-xs text-on-surface font-title-md text-title-md font-bold">
              <span className="material-symbols-outlined text-primary text-[20px]">receipt_long</span>
              <span>Billing License Details</span>
            </div>
            <span className="font-code-sm text-code-sm text-outline font-semibold uppercase">
              Manual Clearing Rail
            </span>
          </div>

          <div className="bg-surface-container-low p-space-md rounded flex flex-col gap-space-xs">
            <span className="font-label-sm text-label-sm text-outline uppercase tracking-wider">
              Subscription Cost
            </span>
            <div className="flex items-baseline gap-space-xs">
              <span className="font-headline-lg text-headline-lg text-on-surface font-extrabold tracking-tight">
                PKR {parseFloat(sub.plan_price).toLocaleString()}
              </span>
              <span className="font-body-sm text-body-sm text-outline capitalize">
                / {sub.billing_cycle}
              </span>
            </div>
            <span className="font-body-xs text-body-xs text-primary font-semibold">
              {sub.plan_name} Contract Rate
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-md font-body-sm text-body-sm">
            <div className="flex flex-col gap-1 p-space-sm bg-surface-container-low/50 rounded">
              <span className="text-outline font-label-sm text-label-sm">Billing Cycle</span>
              <span className="font-title-sm text-title-sm font-semibold text-on-surface capitalize">
                {sub.billing_cycle}
              </span>
            </div>
            <div className="flex flex-col gap-1 p-space-sm bg-surface-container-low/50 rounded">
              <span className="text-outline font-label-sm text-label-sm">Next Invoice Due</span>
              <span className={`font-title-sm text-title-sm font-semibold ${isOverdue ? "text-error" : "text-on-surface"}`}>
                {sub.next_due
                  ? new Date(sub.next_due).toLocaleDateString("en-PK", {
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                    })
                  : sub.is_lifetime
                  ? "Perpetual License (No Renewal)"
                  : "N/A"}
              </span>
            </div>
            <div className="flex flex-col gap-1 p-space-sm bg-surface-container-low/50 rounded">
              <span className="text-outline font-label-sm text-label-sm">Tenant Identifier</span>
              <span className="font-code-sm text-code-sm font-bold text-on-surface">{sub.tenant_slug}</span>
            </div>
            <div className="flex flex-col gap-1 p-space-sm bg-surface-container-low/50 rounded">
              <span className="text-outline font-label-sm text-label-sm">Clearing Settlement Protocol</span>
              <span className="font-code-sm text-code-sm text-on-surface">Raast / IBFT / Easypaisa</span>
            </div>
          </div>
        </div>

        {/* Section B: Mark Paid / Manual Settlement Panel (5 Columns) */}
        <div className="lg:col-span-5 bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
          <div className="flex items-start justify-between pb-space-xs border-b border-surface-container">
            <div className="flex items-center gap-space-xs">
              <span className="material-symbols-outlined text-primary text-[20px]">add_card</span>
              <h2 className="font-title-md text-title-md text-on-surface font-bold">
                Record Payment (Mark Paid)
              </h2>
            </div>
            <span className="font-code-sm text-code-sm bg-primary-fixed text-primary px-1.5 py-0.5 rounded font-bold uppercase">
              TOTP Gated
            </span>
          </div>

          <p className="font-body-xs text-body-xs text-outline">
            Record manual Pakistani bank transfer, Raast IBFT, Easypaisa, or JazzCash clearance. This creates an immutable audit record and advances the next billing date.
          </p>

          <div className="flex flex-col gap-space-sm">
            <div className="flex flex-col gap-1">
              <label className="font-label-sm text-label-sm text-on-surface font-semibold">
                Payment Rail / Method *
              </label>
              <select
                className="w-full h-9 bg-surface-container-low px-2 font-body-sm text-body-sm text-on-surface rounded border border-outline-variant/60 focus:outline-none focus:border-primary cursor-pointer"
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value)}
              >
                <option value="Bank Transfer (Raast / IBFT)">Bank Transfer (Raast / IBFT)</option>
                <option value="Easypaisa">Easypaisa Mobile Account</option>
                <option value="JazzCash">JazzCash Mobile Account</option>
                <option value="Direct Cash Deposit">Direct Bank Branch Cash Deposit</option>
                <option value="Pay Order / Cheque">Pay Order / Bank Cheque</option>
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="font-label-sm text-label-sm text-on-surface font-semibold">
                Transaction Reference # *
              </label>
              <input
                type="text"
                className="w-full h-9 bg-surface-container-low px-3 font-code-sm text-code-sm text-on-surface rounded border border-outline-variant/60 focus:outline-none focus:border-primary placeholder:text-outline"
                placeholder="e.g. RAAST-84910284 or FT24091928"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="font-label-sm text-label-sm text-on-surface font-semibold">
                Cleared Amount (PKR) *
              </label>
              <input
                type="number"
                step="0.01"
                className="w-full h-9 bg-surface-container-low px-3 font-code-sm text-code-sm font-bold text-on-surface rounded border border-outline-variant/60 focus:outline-none focus:border-primary"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="font-label-sm text-label-sm text-on-surface font-semibold flex items-center justify-between">
                <span>Internal Notes</span>
                {parseFloat(amount || "0") !== parseFloat(sub.plan_price) && (
                  <span className="text-error font-body-xs font-semibold">
                    * Required when amount differs from plan price
                  </span>
                )}
              </label>
              <textarea
                className="w-full p-2 bg-surface-container-low font-body-sm text-body-sm text-on-surface rounded border border-outline-variant/60 focus:outline-none focus:border-primary placeholder:text-outline"
                rows={2}
                placeholder="e.g. Verified with Meezan Bank statement. Cleared in full."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>

            <button
              type="button"
              onClick={() => {
                setMarkPaidError(null);
                if (!reference.trim()) {
                  setMarkPaidError("Transaction reference number is required.");
                  return;
                }
                setMarkPaidModalOpen(true);
              }}
              className="w-full mt-2 h-9 bg-primary text-on-primary font-label-sm text-label-sm font-bold rounded hover:bg-primary-container transition-colors shadow-sm flex items-center justify-center gap-1.5"
            >
              <span className="material-symbols-outlined text-[18px]">verified</span>
              <span>Record Payment & Clear Overdue</span>
            </button>
          </div>
        </div>
      </div>

      {/* Section C: Change Subscription Plan Tier */}
      <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
        <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
          <div className="flex items-center gap-space-xs">
            <span className="material-symbols-outlined text-primary text-[20px]">upgrade</span>
            <h2 className="font-title-md text-title-md text-on-surface font-bold">
              Change Plan Tier & Contract Quota
            </h2>
          </div>
          <span className="font-code-sm text-code-sm text-outline">
            Current Tier: <strong className="text-primary">{sub.plan_name}</strong>
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-space-md">
          {availablePlans.map((plan) => {
            const isSelected = selectedPlanId === plan.id;
            const isCurrent = sub.plan_id === plan.id;

            return (
              <label
                key={plan.id}
                className={`p-space-md rounded border-2 cursor-pointer transition-all flex flex-col justify-between ${
                  isSelected
                    ? "border-primary bg-primary-container/5"
                    : "border-outline-variant/40 hover:border-outline-variant bg-surface-container-low/40"
                }`}
              >
                <div className="flex flex-col gap-1">
                  <div className="flex items-center justify-between">
                    <span className="font-title-sm text-title-sm font-bold text-on-surface">
                      {plan.name}
                    </span>
                    <input
                      type="radio"
                      name="planSelect"
                      checked={isSelected}
                      onChange={() => setSelectedPlanId(plan.id)}
                      className="accent-primary w-4 h-4"
                    />
                  </div>
                  <div className="flex items-baseline gap-1 my-1">
                    <span className="font-headline-md text-headline-md font-extrabold text-inverse-surface">
                      PKR {parseFloat(plan.price).toLocaleString()}
                    </span>
                  </div>
                  <div className="font-body-xs text-body-xs text-outline space-y-0.5 mt-1">
                    <div>Branches: {plan.max_branches ?? "Unlimited"}</div>
                    <div>Staff Seats: {plan.max_staff ?? "Unlimited"}</div>
                  </div>
                </div>

                {isCurrent && (
                  <span className="mt-3 px-2 py-0.5 bg-surface-container-high text-primary font-code-sm text-[11px] font-bold rounded text-center">
                    Current Enrolled Tier
                  </span>
                )}
              </label>
            );
          })}
        </div>

        <div className="flex justify-end pt-space-xs">
          <button
            type="button"
            disabled={selectedPlanId === sub.plan_id}
            onClick={() => {
              setChangePlanError(null);
              setChangePlanModalOpen(true);
            }}
            className="px-space-lg h-9 bg-primary text-on-primary font-label-sm text-label-sm font-bold rounded hover:bg-primary-container transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm flex items-center gap-1.5"
          >
            <span className="material-symbols-outlined text-[18px]">published_with_changes</span>
            <span>Apply Tier Change</span>
          </button>
        </div>
      </div>

      {/* Section D: Historical Ledger & Transaction Archive */}
      <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
        <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
          <div className="flex items-center gap-space-xs">
            <span className="material-symbols-outlined text-primary text-[20px]">history</span>
            <h2 className="font-title-md text-title-md text-on-surface font-bold">
              Payment Ledger & Audit Trail
            </h2>
          </div>
          <span className="font-code-sm text-code-sm text-outline">
            {payments.length} Recorded Payment Entries
          </span>
        </div>

        {payments.length === 0 ? (
          <div className="p-8 text-center text-outline bg-surface-container-low/30 rounded">
            <p className="font-body-sm text-body-sm">
              No manual payments recorded yet for this laboratory node.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-container-low h-9 font-label-sm text-label-sm text-outline uppercase tracking-wider">
                  <th className="px-3 py-1">Cleared Date</th>
                  <th className="px-3 py-1">Rail / Method</th>
                  <th className="px-3 py-1">Reference Number</th>
                  <th className="px-3 py-1 text-right">Amount (PKR)</th>
                  <th className="px-3 py-1">Audited By</th>
                  <th className="px-3 py-1">Notes</th>
                  <th className="px-3 py-1 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-high font-body-sm text-body-sm text-on-surface">
                {payments.map((p) => (
                  <tr key={p.id} className="h-10 hover:bg-surface-container-low transition-colors">
                    <td className="px-3 py-1.5 font-code-sm">{p.paid_date}</td>
                    <td className="px-3 py-1.5 font-medium">{p.method}</td>
                    <td className="px-3 py-1.5 font-code-sm text-on-surface-variant font-bold">
                      {p.reference}
                    </td>
                    <td className="px-3 py-1.5 text-right font-code-sm font-bold tabular-nums">
                      {parseFloat(p.amount).toLocaleString()}
                    </td>
                    <td className="px-3 py-1.5 font-code-sm text-outline">{p.recorded_by}</td>
                    <td className="px-3 py-1.5 text-outline text-body-xs">{p.notes || "—"}</td>
                    <td className="px-3 py-1.5 text-center">
                      <span className="px-1.5 py-0.5 bg-primary-fixed text-on-primary-fixed font-code-sm text-[11px] font-bold uppercase rounded">
                        VERIFIED
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* TOTP Modals */}
      <TotpConfirmModal
        isOpen={markPaidModalOpen}
        title="Authorize Payment Recording"
        description={`You are recording a manual payment of PKR ${parseFloat(amount || "0").toLocaleString()} for ${sub.tenant_name} via ${paymentMethod} (${reference}). Enter your 6-digit TOTP code to authorize.`}
        confirmLabel="Record Payment"
        isLoading={markPaidLoading}
        error={markPaidError}
        onConfirm={handleMarkPaid}
        onCancel={() => setMarkPaidModalOpen(false)}
      />

      <TotpConfirmModal
        isOpen={changePlanModalOpen}
        title="Authorize Plan Modification"
        description={`You are changing the subscription tier of ${sub.tenant_name} to "${availablePlans.find((p) => p.id === selectedPlanId)?.name}". Enter your 6-digit TOTP code to authorize.`}
        confirmLabel="Confirm Plan Change"
        isLoading={changePlanLoading}
        error={changePlanError}
        onConfirm={handleChangePlan}
        onCancel={() => setChangePlanModalOpen(false)}
      />
    </div>
  );
}
