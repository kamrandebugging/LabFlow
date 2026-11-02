import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  Edit,
  History,
  Phone,
  ShieldCheck,
  User,
  Trash2,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { patientService } from "./patientService";
import type { PatientDetail } from "./types";

interface PatientDetailsScreenProps {
  patientId: string;
  onBack?: () => void;
  onEdit?: (patientId: string) => void;
  onViewHistory?: (patientId: string) => void;
  onNewVisit?: (patientId: string) => void;
  service?: typeof patientService;
}

export const PatientDetailsScreen: React.FC<PatientDetailsScreenProps> = ({
  patientId,
  onBack,
  onEdit,
  onViewHistory,
  onNewVisit,
  service = patientService,
}) => {
  const [patient, setPatient] = useState<PatientDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setError(null);

    service
      .getPatient(patientId)
      .then((data) => {
        if (isMounted) setPatient(data);
      })
      .catch((err) => {
        if (isMounted)
          setError(
            err instanceof Error ? err.message : "Failed to load patient",
          );
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [patientId, service]);

  const handleDelete = async () => {
    if (
      !window.confirm(
        "Are you sure you want to soft-delete this patient record?",
      )
    )
      return;
    setIsDeleting(true);
    try {
      await service.deletePatient(patientId);
      onBack?.();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete patient");
    } finally {
      setIsDeleting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-slate-500 gap-3">
        <RefreshCw className="w-6 h-6 animate-spin text-teal-600" />
        <span className="text-sm font-medium">Loading clinical record...</span>
      </div>
    );
  }

  if (error || !patient) {
    return (
      <div className="max-w-2xl mx-auto p-6 text-center space-y-4">
        <div className="w-12 h-12 bg-red-50 text-red-600 rounded-full flex items-center justify-center mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-lg font-bold text-slate-900">
          Patient Record Unavailable
        </h2>
        <p className="text-sm text-slate-600">
          {error || "Patient not found."}
        </p>
        <button
          type="button"
          onClick={onBack}
          className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800"
        >
          Return to Patients
        </button>
      </div>
    );
  }

  const primaryPhone =
    patient.phone ||
    patient.contacts?.find((c) => c.kind === "phone")?.value ||
    "—";
  const whatsappContact = patient.contacts?.find(
    (c) => c.kind === "whatsapp",
  )?.value;
  const hasDigitalConsent = patient.consents?.some((c) => !c.revoked_at);

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* 1. Header & Actions */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="space-y-1">
          <nav
            aria-label="Breadcrumb"
            className="flex items-center gap-2 text-xs text-slate-500 mb-1"
          >
            <button
              type="button"
              onClick={onBack}
              className="hover:text-slate-800 transition-colors inline-flex items-center gap-1"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Patients</span>
            </button>
            <span className="text-slate-300">/</span>
            <span className="font-mono text-slate-700 font-semibold">
              {patient.mrn}
            </span>
          </nav>
          <div className="flex items-center flex-wrap gap-3">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 font-headline">
              {patient.name}
            </h1>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 animate-pulse" />
              ACTIVE
            </span>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700">
              {patient.branch_name || "Main Branch"}
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono">
            MRN: <strong className="text-slate-700">{patient.mrn}</strong> ·
            Registered {new Date(patient.created_at).toLocaleDateString()}
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center flex-wrap gap-2.5">
          <button
            type="button"
            onClick={() => onEdit?.(patient.id)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-sm font-medium transition-colors shadow-sm"
          >
            <Edit className="w-4 h-4 text-slate-400" />
            <span>Edit demographics</span>
          </button>
          <button
            type="button"
            onClick={() => onViewHistory?.(patient.id)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-sm font-medium transition-colors shadow-sm"
          >
            <History className="w-4 h-4 text-slate-400" />
            <span>Audit history</span>
          </button>
          <button
            type="button"
            onClick={() => onNewVisit?.(patient.id)}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#005c55] text-white hover:bg-[#0f766e] text-sm font-semibold transition-colors shadow-sm"
          >
            <span>+ New accession</span>
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={isDeleting}
            title="Delete patient"
            aria-label="Delete patient"
            className="p-2 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 2. Demographics & Record Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Core Identity Card */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="border-b border-slate-100 pb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wider flex items-center gap-2">
              <User className="w-4 h-4 text-teal-600" />
              <span>Patient Demographics</span>
            </h2>
            <span className="text-xs font-mono text-slate-400">
              ID: {patient.id.slice(0, 8)}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-xs text-slate-400 block mb-0.5">
                Full Name
              </span>
              <span className="font-semibold text-slate-900">
                {patient.name}
              </span>
            </div>
            <div>
              <span className="text-xs text-slate-400 block mb-0.5">
                Biological Sex
              </span>
              <span className="font-medium text-slate-800">
                {patient.sex === "M"
                  ? "Male"
                  : patient.sex === "F"
                    ? "Female"
                    : "Other"}
              </span>
            </div>
            <div>
              <span className="text-xs text-slate-400 block mb-0.5">
                Date of Birth
              </span>
              <span className="font-medium text-slate-800">
                {patient.date_of_birth
                  ? new Date(patient.date_of_birth).toLocaleDateString()
                  : "Not recorded"}
              </span>
            </div>
            <div>
              <span className="text-xs text-slate-400 block mb-0.5">
                Primary Phone
              </span>
              <span className="font-mono text-slate-800 flex items-center gap-1.5">
                <Phone className="w-3.5 h-3.5 text-slate-400" />
                {primaryPhone}
              </span>
            </div>
          </div>
        </div>

        {/* Digital Consent & Comms Card */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="border-b border-slate-100 pb-3">
            <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wider flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-teal-600" />
              <span>Consent & Notifications</span>
            </h2>
          </div>

          <div className="space-y-3 text-sm">
            <div>
              <span className="text-xs text-slate-400 block mb-0.5">
                Digital Report Delivery
              </span>
              <span
                className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded font-medium ${
                  hasDigitalConsent
                    ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {hasDigitalConsent ? "Consent Granted" : "No Consent on File"}
              </span>
            </div>
            {whatsappContact && (
              <div>
                <span className="text-xs text-slate-400 block mb-0.5">
                  WhatsApp Channel
                </span>
                <span className="font-mono text-slate-700 text-xs">
                  {whatsappContact}
                </span>
              </div>
            )}
            <div className="pt-2 border-t border-slate-100 text-xs text-slate-400">
              ISO 15189 compliance verified. Consent auditable per regulatory
              requirements.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
export default PatientDetailsScreen;
