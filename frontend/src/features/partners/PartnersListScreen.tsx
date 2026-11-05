/**
 * Screen 36: Referral Partners List (/partners)
 * Visual Spec: frontend/public/screens/36-referral-partners.html
 * Backend: GET, POST /api/v1/referral-partners, DELETE /api/v1/referral-partners/:id
 *
 * Requirements:
 * - List referral partners with search and status filtering
 * - Owner/Manager can create new partner
 * - Owner can delete (soft-delete; surfaces 409 partner_has_ledger_entries blocker)
 * - NO partner login UI (partners have no portal credentials in v1)
 */

import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAuthStore } from "../auth/authStore";
import { PartnerApiError, partnersService } from "./partnersService";
import type { CreatePartnerPayload, ReferralPartner } from "./types";

export const PartnersListScreen: React.FC = () => {
  const user = useAuthStore((state) => state.user);
  const isOwner = user?.role === "owner";
  const canManage = user?.role === "owner" || user?.role === "manager";

  const [partners, setPartners] = useState<ReferralPartner[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<
    "all" | "active" | "inactive"
  >("all");

  // Add Partner Modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [formData, setFormData] = useState<CreatePartnerPayload>({
    name: "",
    organisation: "",
    phone: "",
    email: "",
    is_active: true,
  });
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Delete Action / Confirmation Modal
  const [partnerToDelete, setPartnerToDelete] =
    useState<ReferralPartner | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const fetchPartners = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await partnersService.getPartners();
      setPartners(data);
    } catch (err: unknown) {
      if (err instanceof PartnerApiError) {
        setError(err.message);
      } else {
        setError("Failed to load referral partners.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPartners();
  }, []);

  const handleCreatePartner = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setFormError("Partner name is required.");
      return;
    }

    try {
      setFormSubmitting(true);
      setFormError(null);
      const payload: CreatePartnerPayload = {
        name: formData.name.trim(),
        organisation: formData.organisation?.trim() || null,
        phone: formData.phone?.trim() || null,
        email: formData.email?.trim() || null,
        is_active: formData.is_active ?? true,
      };

      await partnersService.createPartner(payload);
      setShowAddModal(false);
      setFormData({
        name: "",
        organisation: "",
        phone: "",
        email: "",
        is_active: true,
      });
      await fetchPartners();
    } catch (err: unknown) {
      if (err instanceof PartnerApiError) {
        setFormError(err.message);
      } else {
        setFormError("Failed to create partner.");
      }
    } finally {
      setFormSubmitting(false);
    }
  };

  const handleDeletePartner = async () => {
    if (!partnerToDelete) return;

    try {
      setDeleteSubmitting(true);
      setDeleteError(null);
      await partnersService.deletePartner(partnerToDelete.id);
      setPartnerToDelete(null);
      await fetchPartners();
    } catch (err: unknown) {
      if (err instanceof PartnerApiError) {
        if (err.code === "partner_has_ledger_entries") {
          setDeleteError(
            "Partners with ledger history cannot be deleted — financial records are immutable. You can deactivate this partner instead.",
          );
        } else {
          setDeleteError(err.message);
        }
      } else {
        setDeleteError("Failed to delete partner.");
      }
    } finally {
      setDeleteSubmitting(false);
    }
  };

  // Filtered partners
  const filteredPartners = useMemo(() => {
    return partners.filter((p) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch =
        !q ||
        p.name.toLowerCase().includes(q) ||
        (p.organisation && p.organisation.toLowerCase().includes(q)) ||
        (p.phone && p.phone.toLowerCase().includes(q)) ||
        (p.email && p.email.toLowerCase().includes(q));

      const matchesStatus =
        statusFilter === "all" ||
        (statusFilter === "active" && p.is_active) ||
        (statusFilter === "inactive" && !p.is_active);

      return matchesSearch && matchesStatus;
    });
  }, [partners, searchQuery, statusFilter]);

  // Derived metrics
  const totalCount = partners.length;
  const activeCount = partners.filter((p) => p.is_active).length;
  const inactiveCount = totalCount - activeCount;

  return (
    <div className="flex-1 overflow-y-auto bg-slate-50 p-6 flex flex-col gap-6">
      {/* Breadcrumb & Header */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>Management</span>
          <span className="material-symbols-outlined text-[14px]">
            chevron_right
          </span>
          <span className="text-slate-800 font-semibold">
            Referral Partners
          </span>
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Referral Partners
            </h1>
            <p className="text-sm text-slate-600">
              Doctors, clinics, and hospitals that refer patients for clinical
              diagnostics
            </p>
          </div>
          {canManage && (
            <button
              type="button"
              onClick={() => {
                setFormError(null);
                setShowAddModal(true);
              }}
              className="bg-teal-600 hover:bg-teal-700 text-white font-medium text-sm px-4 py-2 rounded-lg flex items-center gap-2 shadow-sm transition-colors self-start sm:self-auto"
            >
              <span className="material-symbols-outlined text-[18px]">add</span>
              <span>+ Add partner</span>
            </button>
          )}
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Total Partners
            </p>
            <p className="text-2xl font-bold text-slate-900 mt-1">
              {totalCount}
            </p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-teal-50 text-teal-700 flex items-center justify-center">
            <span className="material-symbols-outlined text-xl">handshake</span>
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Active Referrals
            </p>
            <p className="text-2xl font-bold text-emerald-700 mt-1">
              {activeCount}
            </p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center">
            <span className="material-symbols-outlined text-xl">
              check_circle
            </span>
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Inactive / Paused
            </p>
            <p className="text-2xl font-bold text-slate-600 mt-1">
              {inactiveCount}
            </p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center">
            <span className="material-symbols-outlined text-xl">
              pause_circle
            </span>
          </div>
        </div>
      </div>

      {/* Filter / Search Toolbar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 flex-1">
          {/* Search box */}
          <div className="relative w-full sm:w-80">
            <span className="material-symbols-outlined absolute left-3 top-2.5 text-slate-400 text-[18px]">
              search
            </span>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name, organisation, phone..."
              className="w-full pl-9 pr-3 py-1.5 text-sm bg-white border border-slate-300 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-teal-600 focus:ring-1 focus:ring-teal-600"
            />
          </div>

          {/* Status filter */}
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-slate-500">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) =>
                setStatusFilter(e.target.value as "all" | "active" | "inactive")
              }
              className="text-xs font-medium bg-white border border-slate-300 rounded-lg py-1.5 px-3 text-slate-700 focus:outline-none focus:border-teal-600 focus:ring-1 focus:ring-teal-600"
            >
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
        </div>

        {/* Counter badge */}
        <div className="text-xs font-medium text-slate-600 bg-slate-100 border border-slate-200 px-2.5 py-1 rounded-md self-start md:self-auto">
          Showing {filteredPartners.length}{" "}
          {filteredPartners.length === 1 ? "partner" : "partners"}
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-xl text-sm flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={fetchPartners}
            className="text-red-700 font-semibold underline text-xs ml-4"
          >
            Retry
          </button>
        </div>
      )}

      {/* Partners Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
        {loading ? (
          <div className="p-12 text-center text-slate-500 text-sm">
            Loading referral partners...
          </div>
        ) : filteredPartners.length === 0 ? (
          <div className="p-12 text-center text-slate-500 flex flex-col items-center gap-2">
            <span className="material-symbols-outlined text-4xl text-slate-400">
              handshake
            </span>
            <p className="font-semibold text-slate-800">
              No referral partners found
            </p>
            <p className="text-xs text-slate-500 max-w-sm">
              {searchQuery || statusFilter !== "all"
                ? "No partners match your current filters. Try resetting the filters."
                : "No referral partners have been registered yet. Click '+ Add partner' above to register a clinic or doctor."}
            </p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <th className="py-3 px-4">Partner Name</th>
                <th className="py-3 px-4">Organisation</th>
                <th className="py-3 px-4">Contact</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {filteredPartners.map((partner) => {
                const initials = partner.name
                  .split(" ")
                  .filter(Boolean)
                  .map((w) => w.charAt(0).toUpperCase())
                  .slice(0, 2)
                  .join("");

                return (
                  <tr
                    key={partner.id}
                    className="hover:bg-slate-50 transition-colors group"
                  >
                    <td className="py-3.5 px-4 font-medium text-slate-900">
                      <div className="flex items-center gap-3">
                        <span className="w-8 h-8 rounded-lg bg-teal-50 text-teal-700 flex items-center justify-center font-bold text-xs shrink-0">
                          {initials || "P"}
                        </span>
                        <div>
                          <Link
                            to={`/partners/${partner.id}`}
                            className="text-slate-900 font-semibold hover:text-teal-700 transition-colors"
                          >
                            {partner.name}
                          </Link>
                          {partner.email && (
                            <div className="text-xs text-slate-500 font-normal">
                              {partner.email}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>

                    <td className="py-3.5 px-4 text-slate-600">
                      {partner.organisation ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
                          {partner.organisation}
                        </span>
                      ) : (
                        <span className="text-slate-400 text-xs">—</span>
                      )}
                    </td>

                    <td className="py-3.5 px-4 text-slate-600 font-mono text-xs">
                      {partner.phone || "—"}
                    </td>

                    <td className="py-3.5 px-4">
                      {partner.is_active ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-600"></span>
                          <span>Active</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
                          <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
                          <span>Inactive</span>
                        </span>
                      )}
                    </td>

                    <td className="py-3.5 px-4 text-right">
                      <div className="inline-flex items-center gap-3">
                        <Link
                          to={`/partners/${partner.id}`}
                          className="text-teal-600 hover:text-teal-800 font-medium text-xs transition-colors"
                        >
                          View details →
                        </Link>
                        {isOwner && (
                          <button
                            type="button"
                            onClick={() => {
                              setDeleteError(null);
                              setPartnerToDelete(partner);
                            }}
                            className="p-1 text-slate-400 hover:text-red-600 rounded transition-colors"
                            title="Delete partner"
                            aria-label={`Delete partner ${partner.name}`}
                          >
                            <span className="material-symbols-outlined text-[18px]">
                              delete
                            </span>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Add Partner Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-md w-full p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900">
                Add Referral Partner
              </h2>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <span className="material-symbols-outlined text-lg">close</span>
              </button>
            </div>

            {formError && (
              <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg text-xs">
                {formError}
              </div>
            )}

            <form onSubmit={handleCreatePartner} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1">
                  Partner Name *
                </label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, name: e.target.value }))
                  }
                  placeholder="e.g. Dr. Farhan Qureshi"
                  className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:outline-none focus:border-teal-600"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1">
                  Organisation / Clinic
                </label>
                <input
                  type="text"
                  value={formData.organisation || ""}
                  onChange={(e) =>
                    setFormData((prev) => ({
                      ...prev,
                      organisation: e.target.value,
                    }))
                  }
                  placeholder="e.g. Al-Shifa Clinic or Shalimar Hospital"
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
                    value={formData.phone || ""}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        phone: e.target.value,
                      }))
                    }
                    placeholder="e.g. +92 300 1234567"
                    className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:outline-none focus:border-teal-600"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1">
                    Email
                  </label>
                  <input
                    type="email"
                    value={formData.email || ""}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        email: e.target.value,
                      }))
                    }
                    placeholder="partner@example.com"
                    className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:outline-none focus:border-teal-600"
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="partner-is-active"
                  checked={formData.is_active ?? true}
                  onChange={(e) =>
                    setFormData((prev) => ({
                      ...prev,
                      is_active: e.target.checked,
                    }))
                  }
                  className="rounded border-slate-300 text-teal-600 focus:ring-teal-500 h-4 w-4"
                />
                <label
                  htmlFor="partner-is-active"
                  className="text-xs text-slate-700 select-none"
                >
                  Active for new accessions &amp; referrals
                </label>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={formSubmitting}
                  className="px-4 py-2 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-700 rounded-lg transition-colors disabled:opacity-50"
                >
                  {formSubmitting ? "Creating..." : "Create Partner"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {partnerToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-3 text-red-600">
              <span className="material-symbols-outlined text-2xl">
                warning
              </span>
              <h3 className="text-base font-bold text-slate-900">
                Delete Referral Partner
              </h3>
            </div>

            <p className="text-xs text-slate-600">
              Are you sure you want to delete{" "}
              <strong className="text-slate-900">{partnerToDelete.name}</strong>
              ?
            </p>

            {deleteError && (
              <div className="bg-amber-50 border border-amber-200 text-amber-900 p-3 rounded-lg text-xs space-y-1">
                <div className="font-semibold flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm text-amber-700">
                    lock
                  </span>
                  <span>Financial Integrity Blocker</span>
                </div>
                <p>{deleteError}</p>
              </div>
            )}

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setPartnerToDelete(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleteSubmitting}
                onClick={handleDeletePartner}
                className="px-4 py-2 text-xs font-semibold text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors disabled:opacity-50"
              >
                {deleteSubmitting ? "Deleting..." : "Confirm Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
