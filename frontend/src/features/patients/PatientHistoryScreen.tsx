import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Activity,
} from "lucide-react";
import { patientService } from "./patientService";
import type { PatientDetail } from "./types";

interface PatientHistoryScreenProps {
  patientId: string;
  onBack?: () => void;
  service?: typeof patientService;
}

export const PatientHistoryScreen: React.FC<PatientHistoryScreenProps> = ({
  patientId,
  onBack,
  service = patientService,
}) => {
  const [patient, setPatient] = useState<PatientDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
            err instanceof Error ? err.message : "Failed to load history",
          );
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [patientId, service]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[350px] text-slate-500 gap-2">
        <RefreshCw className="w-6 h-6 animate-spin text-teal-600" />
        <span className="text-sm font-medium">
          Loading longitudinal clinical history...
        </span>
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
          Unable to load history
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

  return (
    <div className="max-w-5xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* 1. Header */}
      <div>
        <nav aria-label="Breadcrumb" className="mb-2">
          <ol className="flex items-center space-x-2 text-xs text-slate-500">
            <li>
              <button
                type="button"
                onClick={onBack}
                className="hover:text-slate-800 transition-colors inline-flex items-center gap-1"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Patients</span>
              </button>
            </li>
            <li className="text-slate-300">/</li>
            <li className="font-mono text-slate-700">{patient.mrn}</li>
            <li className="text-slate-300">/</li>
            <li className="font-medium text-slate-900">Clinical History</li>
          </ol>
        </nav>
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-headline">
              Patient History — {patient.name}
            </h1>
            <p className="text-xs text-slate-500 mt-1 flex items-center gap-2">
              <span>{patient.sex === "M" ? "Male" : "Female"}</span>
              <span className="text-slate-300">•</span>
              <span className="font-mono">{patient.phone || "No phone"}</span>
              <span className="text-slate-300">•</span>
              <span>{patient.branch_name || "Main Branch"}</span>
            </p>
          </div>
          <span className="text-xs font-medium text-slate-500 bg-slate-100 px-3 py-1 rounded-full border border-slate-200">
            Audit Ledger Active
          </span>
        </div>
      </div>

      {/* Info notice */}
      <div className="bg-teal-50/50 border border-teal-200/80 rounded-xl p-4 flex items-start gap-3">
        <Activity className="w-5 h-5 text-teal-700 mt-0.5 shrink-0" />
        <div className="text-xs text-slate-600 leading-relaxed">
          <span className="font-semibold text-slate-800">
            Partitioned ledger scope:
          </span>{" "}
          Showing historical visits, sample accession records, and verified
          diagnostic reports for{" "}
          <strong className="text-slate-900 font-mono">{patient.mrn}</strong>.
          Changes to patient demographics are immutably logged in the tenant
          audit vault.
        </div>
      </div>

      {/* Timeline of Clinical Episodes */}
      <div className="space-y-4">
        {/* Registration event */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-teal-600 ring-4 ring-teal-50" />
              <span className="font-semibold text-slate-900 text-sm">
                Patient Registration & Demographic Enrolment
              </span>
            </div>
            <span className="text-xs font-mono text-slate-400">
              {new Date(patient.created_at).toLocaleDateString()}
            </span>
          </div>

          <div className="text-xs text-slate-600 grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <span className="text-slate-400 block text-[11px]">
                System MRN
              </span>
              <span className="font-mono font-medium text-slate-800">
                {patient.mrn}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[11px]">
                Home Branch
              </span>
              <span className="font-medium text-slate-800">
                {patient.branch_name || "Main Branch"}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[11px]">
                ISO 15189 Status
              </span>
              <span className="text-emerald-700 font-medium flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Verified Active
              </span>
            </div>
          </div>
        </div>

        {/* Subsequent visit summary card */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-slate-400" />
              <span className="font-semibold text-slate-900 text-sm">
                Diagnostic Visit Episode
              </span>
            </div>
            <span className="text-xs font-mono text-slate-400">
              {patient.last_visit || "Recent Visit"}
            </span>
          </div>

          <div className="text-xs text-slate-500 italic">
            Samples and reports accessioned during this visit episode are
            recorded under the clinical worklist ledger.
          </div>
        </div>
      </div>
    </div>
  );
};
export default PatientHistoryScreen;
