import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { platformService } from "./platformService";
import type { DemoRequestItem, DemoRequestStatus } from "./types";

export function DemoRequestDetailScreen() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [lead, setLead] = useState<DemoRequestItem | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<DemoRequestStatus>("new");
  const [notes, setNotes] = useState("");

  const loadLead = async () => {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const res = await platformService.getDemoRequest(id);
      setLead(res);
      setSelectedStatus(res.status);
      setNotes(res.notes || "");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load lead details.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLead();
  }, [id]);

  const handleUpdate = async () => {
    if (!id) return;
    try {
      setSaving(true);
      setSuccess(null);
      setError(null);
      const updated = await platformService.updateDemoRequest(id, {
        status: selectedStatus,
        notes: notes.trim(),
      });
      setLead(updated);
      setSuccess("Lead notes and status updated successfully.");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update lead.");
    } finally {
      setSaving(false);
    }
  };

  const handleConvertToLab = () => {
    if (!lead) return;
    const params = new URLSearchParams({
      name: lead.lab_name,
      owner: lead.contact_person,
      phone: lead.whatsapp,
      demo_id: lead.id,
    });
    navigate(`/platform/tenants/new?${params.toString()}`);
  };

  if (loading) {
    return (
      <div className="p-16 text-center text-outline">
        <span className="inline-block w-8 h-8 border-2 border-primary/20 border-t-primary rounded-full animate-spin mb-3" />
        <p className="font-body-md text-body-md font-semibold">Loading lead dossier...</p>
      </div>
    );
  }

  if (error || !lead) {
    return (
      <div className="p-12 text-center bg-surface-container-lowest rounded shadow-sm max-w-xl mx-auto mt-8">
        <span className="material-symbols-outlined text-error text-[40px] mb-2">error</span>
        <h2 className="font-headline-sm text-headline-sm text-on-surface mb-2">Lead Not Found</h2>
        <p className="font-body-sm text-body-sm text-outline mb-4">{error || "Record could not be retrieved."}</p>
        <Link
          to="/platform/demo-requests"
          className="px-4 py-2 bg-primary text-on-primary font-label-sm text-label-sm rounded hover:bg-primary-container"
        >
          Return to Demo Requests
        </Link>
      </div>
    );
  }

  const cleanPhone = lead.whatsapp.replace(/\D/g, "");

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Utility Nav */}
      <div className="flex flex-wrap items-center justify-between gap-space-sm pb-space-xs">
        <nav className="flex items-center gap-space-xs font-label-sm text-label-sm text-outline">
          <Link to="/platform/demo-requests" className="hover:text-primary transition-colors flex items-center gap-1">
            <span className="material-symbols-outlined text-[16px]">contact_page</span>
            <span>Demo Requests</span>
          </Link>
          <span className="material-symbols-outlined text-[14px]">chevron_right</span>
          <span className="text-on-surface font-semibold">{lead.lab_name}</span>
        </nav>

        <div className="flex items-center gap-space-xs">
          <button
            type="button"
            onClick={() => navigate("/platform/demo-requests")}
            className="h-8 px-space-sm bg-surface-container-low hover:bg-surface-container text-on-surface rounded font-label-sm text-label-sm flex items-center gap-1 transition-colors"
          >
            <span className="material-symbols-outlined text-[16px]">arrow_back</span>
            Back to Inbox
          </button>
          {lead.status !== "converted" && (
            <button
              type="button"
              onClick={handleConvertToLab}
              className="h-8 px-space-md bg-primary hover:bg-primary-container text-on-primary rounded font-label-sm text-label-sm font-bold flex items-center gap-1.5 transition-colors shadow-sm"
            >
              <span className="material-symbols-outlined text-[16px]">domain_add</span>
              <span>Convert to Active Lab</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Header Card */}
      <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col xl:flex-row xl:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-1 min-w-0">
          <div className="flex flex-wrap items-center gap-space-sm">
            <h1 className="font-headline-lg text-headline-lg text-on-surface font-extrabold tracking-tight">
              {lead.lab_name}
            </h1>
            <span className="bg-primary-fixed text-on-primary-fixed px-space-sm py-0.5 rounded font-label-sm text-label-sm font-bold uppercase tracking-wider">
              {lead.status.replace("_", " ")}
            </span>
          </div>
          <p className="font-body-sm text-body-sm text-on-surface-variant">
            Contact Person: <strong>{lead.contact_person}</strong> • Received on{" "}
            {new Date(lead.requested_at).toLocaleDateString("en-PK", {
              day: "numeric",
              month: "long",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        </div>

        {lead.converted_tenant && (
          <div className="p-space-sm bg-primary-fixed/30 border border-primary text-primary-container rounded flex items-center gap-2">
            <span className="material-symbols-outlined text-[20px]">check_circle</span>
            <span className="font-body-sm text-body-sm font-bold">
              Converted to Tenant: {lead.converted_tenant.name} ({lead.converted_tenant.slug})
            </span>
          </div>
        )}
      </div>

      {success && (
        <div className="p-space-md bg-primary-fixed/30 border border-primary text-primary-container rounded flex items-center justify-between font-title-sm text-title-sm font-semibold">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[20px]">check_circle</span>
            <span>{success}</span>
          </div>
          <button onClick={() => setSuccess(null)} className="text-on-surface-variant hover:text-on-surface">
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>
      )}

      {/* Two-Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        {/* Left Column: Contact Card & Notes (7 Cols) */}
        <div className="lg:col-span-7 flex flex-col gap-space-lg">
          {/* Contact & Inquiry */}
          <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
            <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[20px]">person</span>
                <h2 className="font-title-md text-title-md text-on-surface font-bold">
                  Inbound Inquirer Dossier
                </h2>
              </div>
              <a
                href={`https://wa.me/${cleanPhone}`}
                target="_blank"
                rel="noopener noreferrer"
                className="h-8 px-3 bg-primary-container text-on-primary font-label-sm text-label-sm font-bold rounded flex items-center gap-1.5 hover:bg-primary transition-colors shadow-xs"
              >
                <span className="material-symbols-outlined text-[16px]">chat</span>
                <span>Message on WhatsApp</span>
              </a>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-md font-body-sm text-body-sm">
              <div className="p-space-sm bg-surface-container-low rounded flex flex-col gap-1">
                <span className="text-outline font-label-sm text-label-sm">Doctor / Director</span>
                <span className="font-title-sm text-title-sm font-bold text-on-surface">
                  {lead.contact_person}
                </span>
              </div>
              <div className="p-space-sm bg-surface-container-low rounded flex flex-col gap-1">
                <span className="text-outline font-label-sm text-label-sm">WhatsApp Mobile</span>
                <span className="font-code-sm text-code-sm font-bold text-on-surface">
                  {lead.whatsapp}
                </span>
              </div>
            </div>

            <div className="flex flex-col gap-1 mt-2">
              <span className="text-outline font-label-sm text-label-sm font-semibold">
                Original Inbound Requirements & Notes
              </span>
              <div className="p-space-md bg-surface-container-low rounded font-body-sm text-body-sm text-on-surface whitespace-pre-wrap leading-relaxed border border-outline-variant/30">
                {lead.message || "No custom message provided during initial form submission."}
              </div>
            </div>
          </div>

          {/* Qualification Notes */}
          <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
            <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[20px]">edit_note</span>
                <h2 className="font-title-md text-title-md text-on-surface font-bold">
                  Internal Sales & Qualification Notes
                </h2>
              </div>
              <span className="font-code-sm text-code-sm text-outline">Internal use only</span>
            </div>

            <textarea
              rows={4}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Record notes from WhatsApp conversation, test volume expectations, hardware analyzer models, branch requirements..."
              className="w-full p-3 bg-surface-container-low rounded border border-outline-variant/60 font-body-sm text-body-sm text-on-surface focus:outline-none focus:border-primary"
            />

            <div className="flex justify-end">
              <button
                type="button"
                disabled={saving}
                onClick={handleUpdate}
                className="px-space-md h-8 bg-primary text-on-primary font-label-sm text-label-sm font-bold rounded hover:bg-primary-container transition-colors shadow-sm flex items-center gap-1.5"
              >
                {saving && (
                  <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                )}
                <span>Save Lead Notes</span>
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Status & Conversion (5 Cols) */}
        <div className="lg:col-span-5 flex flex-col gap-space-lg">
          {/* Status Pipeline State Machine */}
          <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md">
            <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[20px]">sync</span>
                <h2 className="font-title-md text-title-md text-on-surface font-bold">
                  Pipeline Stage
                </h2>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <label className="font-label-sm text-label-sm text-on-surface font-semibold">
                Lifecycle Status *
              </label>
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value as DemoRequestStatus)}
                className="w-full h-9 bg-surface-container-low px-3 font-title-sm text-title-sm text-on-surface rounded border border-outline-variant/60 focus:outline-none focus:border-primary cursor-pointer"
              >
                <option value="new">NEW (Pending Outreach)</option>
                <option value="contacted">CONTACTED (In Discussion)</option>
                <option value="demo_done">DEMO DONE (Completed Tour)</option>
                <option value="converted">CONVERTED (Active Customer)</option>
                <option value="lost">LOST (Unqualified / Dropped)</option>
              </select>

              <button
                type="button"
                disabled={saving || selectedStatus === lead.status}
                onClick={handleUpdate}
                className="mt-2 w-full h-9 bg-surface-container-high hover:bg-surface-container-highest text-on-surface-variant font-label-sm text-label-sm font-bold rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Update Pipeline Status
              </button>
            </div>
          </div>

          {/* Conversion Action Card */}
          <div className="bg-surface-container-lowest p-space-lg rounded shadow-sm flex flex-col gap-space-md border-2 border-primary/20">
            <div className="flex items-center gap-space-xs text-primary">
              <span className="material-symbols-outlined text-[24px]">rocket_launch</span>
              <h2 className="font-title-md text-title-md font-bold text-on-surface">
                Convert to Operational Tenant
              </h2>
            </div>
            <p className="font-body-xs text-body-xs text-outline leading-relaxed">
              Instantly prefill the LabFlow Provisioning Engine with this lead's facility name, owner contact, and mobile WhatsApp credentials.
            </p>

            <button
              type="button"
              onClick={handleConvertToLab}
              className="w-full h-10 bg-primary text-on-primary font-label-sm text-label-sm font-bold rounded hover:bg-primary-container transition-colors shadow-sm flex items-center justify-center gap-1.5"
            >
              <span className="material-symbols-outlined text-[18px]">domain_add</span>
              <span>Launch Provisioning Flow</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
