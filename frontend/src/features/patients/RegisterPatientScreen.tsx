import React, { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  Loader2,
  ArrowLeft,
} from "lucide-react";
import { DuplicatePatientError, patientService } from "./patientService";
import type {
  PatientCandidate,
  PatientCreateInput,
  PatientSummary,
} from "./types";

interface RegisterPatientScreenProps {
  branchId?: string;
  onSuccess?: (patient: PatientSummary) => void;
  onCancel?: () => void;
  service?: typeof patientService;
}

export const RegisterPatientScreen: React.FC<RegisterPatientScreenProps> = ({
  branchId = "00000000-0000-0000-0000-000000000001",
  onSuccess,
  onCancel,
  service = patientService,
}) => {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [sex, setSex] = useState<"M" | "F">("M");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [whatsappNumber, setWhatsappNumber] = useState("");
  const [consentReports, setConsentReports] = useState(false);

  const [isLoading, setIsLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [duplicateCandidates, setDuplicateCandidates] = useState<
    PatientCandidate[] | null
  >(null);

  const handleSubmit = async (confirmDuplicate = false) => {
    setFormError(null);

    // Validation
    const trimmedName = name.trim();
    if (trimmedName.length < 2 || trimmedName.length > 120) {
      setFormError("Full name must be between 2 and 120 characters.");
      return;
    }

    const cleanPhone = phone.replace(/[\s\-()+]/g, "");
    if (!/^\d{10,15}$/.test(cleanPhone)) {
      setFormError("Phone number must contain between 10 and 15 digits.");
      return;
    }

    setIsLoading(true);
    try {
      const payload: PatientCreateInput = {
        name: trimmedName,
        phone: cleanPhone,
        sex,
        date_of_birth: dateOfBirth || null,
        branch_id: branchId,
        whatsapp_number: whatsappNumber
          ? whatsappNumber.replace(/[\s\-()+]/g, "")
          : undefined,
        consent_reports: consentReports,
        confirm_duplicate: confirmDuplicate,
      };

      const result = await service.createPatient(payload);
      setDuplicateCandidates(null);
      onSuccess?.(result);
    } catch (err: unknown) {
      if (err instanceof DuplicatePatientError) {
        setDuplicateCandidates(err.candidates);
      } else {
        setFormError(
          err instanceof Error ? err.message : "Failed to register patient.",
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Breadcrumbs & Header */}
      <div>
        <nav aria-label="Breadcrumb" className="mb-2">
          <ol className="flex items-center space-x-2 text-xs text-slate-500">
            <li>
              <button
                type="button"
                onClick={onCancel}
                className="hover:text-slate-800 transition-colors inline-flex items-center gap-1"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Patients</span>
              </button>
            </li>
            <li className="text-slate-300">/</li>
            <li className="font-medium text-slate-900">New registration</li>
          </ol>
        </nav>
        <div className="flex items-baseline justify-between">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-headline">
            Register patient
          </h1>
          <span className="text-xs text-slate-400 font-mono">
            ISO 15189 Demographics
          </span>
        </div>
      </div>

      {/* Duplicate Warning Modal / Banner */}
      {duplicateCandidates && duplicateCandidates.length > 0 && (
        <div
          role="alert"
          data-testid="duplicate-warning-banner"
          className="p-5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 space-y-3 shadow-sm"
        >
          <div className="flex items-center gap-2 font-semibold text-amber-800">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
            <span>Possible Duplicate Patient Detected</span>
          </div>
          <p className="text-xs text-amber-700 leading-relaxed">
            A patient with a matching name and phone number is already
            registered in the laboratory records:
          </p>

          <div className="divide-y divide-amber-200/60 bg-white/70 rounded-lg border border-amber-200/80 p-2 text-xs">
            {duplicateCandidates.map((c) => (
              <div
                key={c.id}
                className="py-2 px-2 flex justify-between items-center"
              >
                <div>
                  <span className="font-semibold text-slate-900">{c.name}</span>
                  <span className="text-slate-500 ml-2">
                    ({c.sex === "M" ? "Male" : "Female"})
                  </span>
                  {c.year_of_birth && (
                    <span className="text-slate-500 ml-1">
                      · YOB {c.year_of_birth}
                    </span>
                  )}
                </div>
                <span className="font-mono bg-amber-100 text-amber-800 px-2 py-0.5 rounded font-medium">
                  {c.mrn}
                </span>
              </div>
            ))}
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setDuplicateCandidates(null)}
              className="px-3.5 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 rounded-lg hover:bg-amber-100/50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => handleSubmit(true)}
              disabled={isLoading}
              className="px-4 py-1.5 text-xs font-semibold bg-amber-700 hover:bg-amber-800 text-white rounded-lg shadow-sm transition-colors flex items-center gap-1.5"
            >
              {isLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>Confirm & Register Anyway</span>
            </button>
          </div>
        </div>
      )}

      {/* General Error Alert */}
      {formError && (
        <div
          role="alert"
          className="flex items-center gap-2 p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm"
        >
          <AlertCircle className="w-5 h-5 text-red-600 shrink-0" />
          <span>{formError}</span>
        </div>
      )}

      {/* Registration Form Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 sm:p-8 shadow-sm">
        <form
          id="patientRegistrationForm"
          onSubmit={(e) => {
            e.preventDefault();
            handleSubmit(false);
          }}
          className="space-y-6"
        >
          {/* SECTION 1: Identity */}
          <div className="space-y-4">
            <div className="border-b border-slate-100 pb-2">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                Patient Demographics
              </h2>
            </div>

            {/* Full Name */}
            <div>
              <label
                htmlFor="fullName"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                Full name <span className="text-red-500">*</span>
              </label>
              <input
                id="fullName"
                name="fullName"
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Muhammad Imran"
                className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
              />
            </div>

            {/* Phone & Sex */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label
                  htmlFor="phoneNumber"
                  className="block text-xs font-semibold text-slate-700 mb-1.5"
                >
                  Phone <span className="text-red-500">*</span>
                </label>
                <input
                  id="phoneNumber"
                  name="phoneNumber"
                  type="tel"
                  required
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="03001234567"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
                />
                <p className="mt-1 text-xs text-slate-400">10-15 digits</p>
              </div>

              <div>
                <span className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Sex <span className="text-red-500">*</span>
                </span>
                <div className="flex items-center space-x-6 h-10 px-1">
                  <label className="inline-flex items-center cursor-pointer select-none">
                    <input
                      type="radio"
                      name="sex"
                      value="M"
                      checked={sex === "M"}
                      onChange={() => setSex("M")}
                      className="w-4 h-4 text-teal-600 border-slate-300 focus:ring-teal-500"
                    />
                    <span className="ml-2 text-sm text-slate-700">Male</span>
                  </label>
                  <label className="inline-flex items-center cursor-pointer select-none">
                    <input
                      type="radio"
                      name="sex"
                      value="F"
                      checked={sex === "F"}
                      onChange={() => setSex("F")}
                      className="w-4 h-4 text-teal-600 border-slate-300 focus:ring-teal-500"
                    />
                    <span className="ml-2 text-sm text-slate-700">Female</span>
                  </label>
                </div>
              </div>
            </div>

            {/* Date of Birth */}
            <div>
              <label
                htmlFor="dateOfBirth"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                Date of birth
              </label>
              <input
                id="dateOfBirth"
                name="dateOfBirth"
                type="date"
                value={dateOfBirth}
                onChange={(e) => setDateOfBirth(e.target.value)}
                className="w-full sm:w-64 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
              />
              <p className="mt-1 text-xs text-slate-400">
                Leave blank if unknown
              </p>
            </div>
          </div>

          {/* SECTION 2: Contact & consent */}
          <div className="space-y-4 pt-2">
            <div className="border-b border-slate-100 pb-2">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                Digital Delivery & Consent
              </h2>
            </div>

            {/* WhatsApp */}
            <div>
              <label
                htmlFor="whatsappNumber"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                WhatsApp number
              </label>
              <input
                id="whatsappNumber"
                name="whatsappNumber"
                type="tel"
                value={whatsappNumber}
                onChange={(e) => setWhatsappNumber(e.target.value)}
                placeholder="+92 300 1234567"
                className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
              />
              <p className="mt-1 text-xs text-slate-400">
                For instant digital lab report delivery
              </p>
            </div>

            {/* Consent checkbox */}
            <div>
              <label className="flex items-start cursor-pointer select-none">
                <input
                  id="consentReports"
                  name="consentReports"
                  type="checkbox"
                  checked={consentReports}
                  onChange={(e) => setConsentReports(e.target.checked)}
                  className="mt-0.5 rounded border-slate-300 text-teal-600 focus:ring-teal-500 h-4 w-4"
                />
                <span className="ml-2.5 text-xs sm:text-sm text-slate-700 leading-snug">
                  Patient consents to receiving reports & critical notifications
                  via WhatsApp / SMS
                </span>
              </label>
            </div>
          </div>

          {/* Footer Actions */}
          <div className="pt-6 border-t border-slate-100 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2.5 rounded-lg border border-slate-300 text-slate-700 bg-white hover:bg-slate-50 text-sm font-medium transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-5 py-2.5 rounded-lg bg-[#005c55] hover:bg-[#0f766e] text-white text-sm font-medium shadow-sm transition-colors flex items-center gap-2 cursor-pointer disabled:opacity-60"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Check className="w-4 h-4" />
              )}
              <span>{isLoading ? "Registering..." : "Register patient"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
export default RegisterPatientScreen;
