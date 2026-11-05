/**
 * Screen 37: Referral Partner Detail (/partners/:id)
 * Visual Spec: frontend/public/screens/37-partner-detail.html
 * Backend:
 * - GET /api/v1/referral-partners/:id
 * - PATCH /api/v1/referral-partners/:id
 * - GET /api/v1/referral-partners/:id/dashboard
 * - GET /api/v1/referral-partners/:id/rules
 *
 * Requirements:
 * - Displays partner profile, contact info, and status
 * - Displays live dashboard metrics directly from backend (ytd_earned, ytd_settled, pending_total, last 6 settlements)
 * - Displays read-only revenue share rules and links to upcoming Screen 38
 * - Links to upcoming Screen 41 (Settlement History)
 * - NO partner portal login or invite UI (v1 has no partner credentials)
 */

import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuthStore } from "../auth/authStore";
import { PartnerApiError, partnersService } from "./partnersService";
import type {
  PartnerDashboardData,
  ReferralPartner,
  RevenueShareRule,
  UpdatePartnerPayload,
} from "./types";

export const PartnerDetailScreen: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const user = useAuthStore((state) => state.user);
  const canEdit = user?.role === "owner" || user?.role === "manager";

  const [partner, setPartner] = useState<ReferralPartner | null>(null);
  const [dashboard, setDashboard] = useState<PartnerDashboardData | null>(null);
  const [rules, setRules] = useState<RevenueShareRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit Partner Modal
  const [showEditModal, setShowEditModal] = useState(false);
  const [editForm, setEditForm] = useState<UpdatePartnerPayload>({});
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Status toggle
  const [togglingStatus, setTogglingStatus] = useState(false);

  const fetchPartnerData = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const [partnerRes, dashboardRes, rulesRes] = await Promise.all([
        partnersService.getPartner(id),
        partnersService.getPartnerDashboard(id),
        partnersService.getPartnerRules(id),
      ]);
      setPartner(partnerRes);
      setDashboard(dashboardRes);
      setRules(rulesRes);
    } catch (err: unknown) {
      if (err instanceof PartnerApiError) {
        setError(err.message);
      } else {
        setError("Failed to load partner information.");
      }
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchPartnerData();
  }, [fetchPartnerData]);

  const handleOpenEdit = () => {
    if (!partner) return;
    setEditForm({
      name: partner.name,
      organisation: partner.organisation || "",
      phone: partner.phone || "",
      email: partner.email || "",
      is_active: partner.is_active,
    });
    setEditError(null);
    setShowEditModal(true);
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !partner) return;
    if (!editForm.name?.trim()) {
      setEditError("Partner name is required.");
      return;
    }

    try {
      setEditSubmitting(true);
      setEditError(null);
      const updated = await partnersService.updatePartner(id, {
        name: editForm.name.trim(),
        organisation: editForm.organisation?.trim() || null,
        phone: editForm.phone?.trim() || null,
        email: editForm.email?.trim() || null,
        is_active: editForm.is_active,
      });
      setPartner(updated);
      setShowEditModal(false);
    } catch (err: unknown) {
      if (err instanceof PartnerApiError) {
        setEditError(err.message);
      } else {
        setEditError("Failed to update partner details.");
      }
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleToggleActive = async () => {
    if (!id || !partner || togglingStatus) return;
    try {
      setTogglingStatus(true);
      const updated = await partnersService.updatePartner(id, {
        is_active: !partner.is_active,
      });
      setPartner(updated);
    } catch (err: unknown) {
      if (err instanceof PartnerApiError) {
        setError(err.message);
      } else {
        setError("Failed to change partner status.");
      }
    } finally {
      setTogglingStatus(false);
    }
  };

  if (loading) {
    return (
      <div className="flex-1 p-8 text-center text-slate-500 text-sm">
        Loading partner details...
      </div>
    );
  }

  if (error || !partner) {
    return (
      <div className="flex-1 p-8 flex flex-col items-center justify-center gap-4">
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-xl text-sm max-w-md w-full text-center">
          {error || "Referral partner not found."}
        </div>
        <Link
          to="/partners"
          className="text-teal-600 hover:text-teal-800 text-sm font-semibold flex items-center gap-1"
        >
          <span className="material-symbols-outlined text-base">
            arrow_back
          </span>
          <span>Back to Partners List</span>
        </Link>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto bg-slate-50 p-6 flex flex-col gap-6">
      {/* Navigation Breadcrumb */}
      <nav className="flex items-center justify-between text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <Link
            to="/partners"
            className="hover:text-slate-900 transition-colors"
          >
            Management
          </Link>
          <span className="material-symbols-outlined text-[14px]">
            chevron_right
          </span>
          <Link
            to="/partners"
            className="hover:text-slate-900 transition-colors"
          >
            Referral Partners
          </Link>
          <span className="material-symbols-outlined text-[14px]">
            chevron_right
          </span>
          <span className="text-slate-900 font-semibold">{partner.name}</span>
        </div>
        <span className="text-[11px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
          Partner Record
        </span>
      </nav>

      {/* Profile Header Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-5">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center flex-wrap gap-2.5">
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                {partner.name}
              </h1>

              {partner.organisation && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-slate-100 text-slate-800 border border-slate-200">
                  {partner.organisation}
                </span>
              )}

              <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-50 text-slate-600 border border-slate-200">
                {partner.id.substring(0, 8)}
              </span>

              {partner.is_active ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-600"></span>
                  <span>Active</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
                  <span>Inactive</span>
                </span>
              )}
            </div>

            <p className="text-xs text-slate-500">
              Registered on {new Date(partner.created_at).toLocaleDateString()}
            </p>
          </div>

          {/* Action buttons */}
          {canEdit && (
            <div className="flex flex-col items-start md:items-end gap-1.5 shrink-0">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleOpenEdit}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 text-slate-700 bg-white hover:bg-slate-50 transition-colors shadow-sm"
                >
                  <span className="material-symbols-outlined text-sm">
                    edit
                  </span>
                  <span>Edit</span>
                </button>

                <button
                  type="button"
                  disabled={togglingStatus}
                  onClick={handleToggleActive}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors shadow-sm ${
                    partner.is_active
                      ? "border-red-200 text-red-600 bg-white hover:bg-red-50"
                      : "border-emerald-200 text-emerald-700 bg-white hover:bg-emerald-50"
                  }`}
                >
                  <span className="material-symbols-outlined text-sm">
                    {partner.is_active ? "block" : "check_circle"}
                  </span>
                  <span>{partner.is_active ? "Deactivate" : "Activate"}</span>
                </button>
              </div>
              <span className="text-[11px] text-slate-500 text-left md:text-right max-w-xs leading-tight">
                Partners with ledger history can be deactivated, preserving
                immutable financial audits.
              </span>
            </div>
          )}
        </div>

        {/* Contact Details Grid */}
        <div className="border-t border-slate-100 pt-4 grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 space-y-1">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
              Phone Contact
            </span>
            <div className="font-semibold text-slate-900 font-mono">
              {partner.phone || "—"}
            </div>
          </div>

          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 space-y-1">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
              Email Address
            </span>
            <div className="font-semibold text-slate-900 truncate">
              {partner.email || "—"}
            </div>
          </div>

          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 space-y-1">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
              Affiliated Organisation
            </span>
            <div className="font-semibold text-slate-900 truncate">
              {partner.organisation || "Independent Referral"}
            </div>
          </div>
        </div>
      </div>

      {/* Financial Position Dashboard */}
      {dashboard && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-bold text-slate-900 tracking-tight">
                Referral Financial Position
              </h2>
              <p className="text-xs text-slate-500">
                Real-time commission accruals and settlement history derived
                from tenant ledger
              </p>
            </div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-100 text-slate-600 text-xs font-medium border border-slate-200 self-start sm:self-auto">
              <span className="material-symbols-outlined text-xs">
                lock_clock
              </span>
              <span>Ledger Verified</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-lg border border-slate-200 bg-slate-50/50 flex flex-col justify-between">
              <div className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
                Total Accrued (YTD)
              </div>
              <div className="text-2xl font-bold text-slate-900 font-mono my-2">
                PKR {dashboard.ytd_earned}
              </div>
              <div className="text-xs text-slate-500 font-medium">
                Accumulated partner revenue share
              </div>
            </div>

            <div className="p-4 rounded-lg border border-slate-200 bg-slate-50/50 flex flex-col justify-between">
              <div className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
                Settled to Date (YTD)
              </div>
              <div className="text-2xl font-bold text-emerald-700 font-mono my-2">
                PKR {dashboard.ytd_settled}
              </div>
              <div className="text-xs text-slate-500 font-medium">
                Fully paid and disbursed to partner
              </div>
            </div>

            <div className="p-4 rounded-lg border border-slate-200 bg-slate-50/50 flex flex-col justify-between">
              <div className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
                Pending Balance
              </div>
              <div className="text-2xl font-bold text-teal-700 font-mono my-2">
                PKR {dashboard.pending_total}
              </div>
              <div className="text-xs text-slate-500 font-medium">
                Awaiting upcoming settlement cycle
              </div>
            </div>
          </div>

          {/* Recent Settlements List */}
          <div className="pt-2">
            <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
              Recent Settlements
            </h3>
            {dashboard.last_6_settlements.length === 0 ? (
              <p className="text-xs text-slate-500 bg-slate-50 p-4 rounded-lg border border-slate-100">
                No past settlements recorded for this partner yet.
              </p>
            ) : (
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase">
                    <tr>
                      <th className="py-2.5 px-3">Period</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3 text-right">Settled Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {dashboard.last_6_settlements.map((s) => (
                      <tr key={s.id} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-medium text-slate-800">
                          {s.period}
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="capitalize px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                            {s.status}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono font-semibold text-slate-900">
                          PKR {s.total}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Revenue Share Rules Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">
              Configured Revenue Share Rules
            </h2>
            <p className="text-xs text-slate-500">
              Active commission percentage rules applied during billing
              accession creation
            </p>
          </div>
          <div className="text-xs font-medium text-slate-600 bg-slate-100 border border-slate-200 px-2.5 py-1 rounded-md self-start sm:self-auto">
            {rules.length} {rules.length === 1 ? "rule" : "rules"} active
          </div>
        </div>

        {rules.length === 0 ? (
          <div className="p-8 text-center text-slate-500 bg-slate-50 rounded-lg border border-slate-100 flex flex-col items-center gap-1.5">
            <span className="material-symbols-outlined text-3xl text-slate-400">
              tune
            </span>
            <p className="font-semibold text-slate-700 text-xs">
              No specific rules configured
            </p>
            <p className="text-[11px] text-slate-500">
              When no specific rule matches, the standard tenant fallback
              percentage applies.
            </p>
          </div>
        ) : (
          <div className="border border-slate-200 rounded-lg overflow-hidden">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase">
                <tr>
                  <th className="py-2.5 px-3">Category</th>
                  <th className="py-2.5 px-3">Commission %</th>
                  <th className="py-2.5 px-3">Effective From</th>
                  <th className="py-2.5 px-3">Effective To</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rules.map((rule) => (
                  <tr key={rule.id} className="hover:bg-slate-50">
                    <td className="py-2.5 px-3 font-medium text-slate-800">
                      {rule.test_category || "All Categories (General)"}
                    </td>
                    <td className="py-2.5 px-3 font-mono font-semibold text-teal-700">
                      {rule.percent}%
                    </td>
                    <td className="py-2.5 px-3 text-slate-600">
                      {rule.effective_from}
                    </td>
                    <td className="py-2.5 px-3 text-slate-600">
                      {rule.effective_to || "Indefinite"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="bg-teal-50 border border-teal-200 p-3.5 rounded-lg flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-teal-800">
            <span className="material-symbols-outlined text-teal-600">
              info
            </span>
            <span>
              Detailed rule authoring, category buckets, and historical rate
              versioning are managed in Screen 38 (Rules Editor).
            </span>
          </div>
          <span className="text-xs font-semibold text-teal-700 bg-teal-100 px-2 py-0.5 rounded shrink-0">
            Upcoming Screen 38
          </span>
        </div>
      </div>

      {/* Settlement History Link Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-slate-900">
            Settlement History &amp; Disbursements
          </h2>
          <p className="text-xs text-slate-500">
            Monthly payout batching, PDF statements, and WhatsApp delivery
            dispatch are handled in Settlement History.
          </p>
        </div>
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 text-xs font-semibold border border-slate-200 self-start sm:self-auto shrink-0">
          <span className="material-symbols-outlined text-sm">history</span>
          <span>Upcoming Screen 41</span>
        </div>
      </div>

      {/* Edit Partner Modal */}
      {showEditModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-md w-full p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900">
                Edit Referral Partner
              </h2>
              <button
                type="button"
                onClick={() => setShowEditModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <span className="material-symbols-outlined text-lg">close</span>
              </button>
            </div>

            {editError && (
              <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg text-xs">
                {editError}
              </div>
            )}

            <form onSubmit={handleSaveEdit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1">
                  Partner Name *
                </label>
                <input
                  type="text"
                  required
                  value={editForm.name || ""}
                  onChange={(e) =>
                    setEditForm((prev) => ({ ...prev, name: e.target.value }))
                  }
                  className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:outline-none focus:border-teal-600"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1">
                  Organisation / Clinic
                </label>
                <input
                  type="text"
                  value={editForm.organisation || ""}
                  onChange={(e) =>
                    setEditForm((prev) => ({
                      ...prev,
                      organisation: e.target.value,
                    }))
                  }
                  className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:outline-none focus:border-teal-600"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1">
                    Phone
                  </label>
                  <input
                    type="text"
                    value={editForm.phone || ""}
                    onChange={(e) =>
                      setEditForm((prev) => ({
                        ...prev,
                        phone: e.target.value,
                      }))
                    }
                    className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:outline-none focus:border-teal-600"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1">
                    Email
                  </label>
                  <input
                    type="email"
                    value={editForm.email || ""}
                    onChange={(e) =>
                      setEditForm((prev) => ({
                        ...prev,
                        email: e.target.value,
                      }))
                    }
                    className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:outline-none focus:border-teal-600"
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="edit-partner-active"
                  checked={editForm.is_active ?? true}
                  onChange={(e) =>
                    setEditForm((prev) => ({
                      ...prev,
                      is_active: e.target.checked,
                    }))
                  }
                  className="rounded border-slate-300 text-teal-600 focus:ring-teal-500 h-4 w-4"
                />
                <label
                  htmlFor="edit-partner-active"
                  className="text-xs text-slate-700 select-none"
                >
                  Active for new accessions &amp; referrals
                </label>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowEditModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editSubmitting}
                  className="px-4 py-2 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-700 rounded-lg transition-colors disabled:opacity-50"
                >
                  {editSubmitting ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
