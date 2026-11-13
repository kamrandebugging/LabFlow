import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  Loader2,
  ArrowLeft,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
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
  const { t } = useTranslation(["patients", "common"]);
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
      setFormError(t("patients:register.validation.name"));
      return;
    }

    const cleanPhone = phone.replace(/[\s\-()+]/g, "");
    if (!/^\d{10,15}$/.test(cleanPhone)) {
      setFormError(t("patients:validation.phone"));
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
          err && typeof err === "object" && ("code" in err || "status" in err)
            ? messageForError(err, t)
            : t("patients:register.errors.failed"),
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
        <nav aria-label={t("patients:breadcrumb_aria")} className="mb-2">
          <ol className="flex items-center gap-x-2 text-xs text-slate-500">
            <li>
              <button
                type="button"
                onClick={onCancel}
                className="hover:text-slate-800 transition-colors inline-flex items-center gap-1"
              >
                <ArrowLeft className="w-3.5 h-3.5 rtl:rotate-180" />
                <span>{t("common:nav.patients")}</span>
              </button>
            </li>
            <li className="text-slate-300">/</li>
            <li className="font-medium text-slate-900">
              {t("patients:register.breadcrumb_new")}
            </li>
          </ol>
        </nav>
        <div className="flex items-baseline justify-between">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-headline">
            {t("patients:register.title")}
          </h1>
          <span className="text-xs text-slate-400 font-mono">
            {t("patients:register.iso_badge")}
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
            <span>{t("patients:register.duplicate.title")}</span>
          </div>
          <p className="text-xs text-amber-700 leading-relaxed">
            {t("patients:register.duplicate.body")}
          </p>

          <div className="divide-y divide-amber-200/60 bg-white/70 rounded-lg border border-amber-200/80 p-2 text-xs">
            {duplicateCandidates.map((c) => (
              <div
                key={c.id}
                className="py-2 px-2 flex justify-between items-center"
              >
                <div>
                  <span className="font-semibold text-slate-900">{c.name}</span>
                  <span className="text-slate-500 ms-2">
                    (
                    {c.sex === "M"
                      ? t("patients:sex.male")
                      : t("patients:sex.female")}
                    )
                  </span>
                  {c.year_of_birth && (
                    <span className="text-slate-500 ms-1">
                      ·{" "}
                      {t("patients:register.duplicate.yob", {
                        year: c.year_of_birth,
                      })}
                    </span>
                  )}
                </div>
                <span
                  dir="ltr"
                  className="font-mono bg-amber-100 text-amber-800 px-2 py-0.5 rounded font-medium"
                >
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
              {t("common:actions.cancel")}
            </button>
            <button
              type="button"
              onClick={() => handleSubmit(true)}
              disabled={isLoading}
              className="px-4 py-1.5 text-xs font-semibold bg-amber-700 hover:bg-amber-800 text-white rounded-lg shadow-sm transition-colors flex items-center gap-1.5"
            >
              {isLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>{t("patients:register.duplicate.confirm")}</span>
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
                {t("patients:demographics")}
              </h2>
            </div>

            {/* Full Name */}
            <div>
              <label
                htmlFor="fullName"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                {t("patients:field_full_name")}{" "}
                <span className="text-red-500">*</span>
              </label>
              <input
                id="fullName"
                name="fullName"
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("patients:register.full_name_placeholder")}
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
                  {t("common:labels.phone")}{" "}
                  <span className="text-red-500">*</span>
                </label>
                <input
                  id="phoneNumber"
                  name="phoneNumber"
                  type="tel"
                  dir="ltr"
                  required
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder={t("patients:register.phone_placeholder")}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
                />
                <p className="mt-1 text-xs text-slate-400">
                  {t("patients:register.phone_hint")}
                </p>
              </div>

              <div>
                <span className="block text-xs font-semibold text-slate-700 mb-1.5">
                  {t("common:labels.sex")}{" "}
                  <span className="text-red-500">*</span>
                </span>
                <div className="flex items-center gap-x-6 h-10 px-1">
                  <label className="inline-flex items-center cursor-pointer select-none">
                    <input
                      type="radio"
                      name="sex"
                      value="M"
                      checked={sex === "M"}
                      onChange={() => setSex("M")}
                      className="w-4 h-4 text-teal-600 border-slate-300 focus:ring-teal-500"
                    />
                    <span className="ms-2 text-sm text-slate-700">
                      {t("patients:sex.male")}
                    </span>
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
                    <span className="ms-2 text-sm text-slate-700">
                      {t("patients:sex.female")}
                    </span>
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
                {t("common:labels.dob")}
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
                {t("patients:register.dob_hint")}
              </p>
            </div>
          </div>

          {/* SECTION 2: Contact & consent */}
          <div className="space-y-4 pt-2">
            <div className="border-b border-slate-100 pb-2">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                {t("patients:register.section_delivery")}
              </h2>
            </div>

            {/* WhatsApp */}
            <div>
              <label
                htmlFor="whatsappNumber"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                {t("patients:register.whatsapp")}
              </label>
              <input
                id="whatsappNumber"
                name="whatsappNumber"
                type="tel"
                dir="ltr"
                value={whatsappNumber}
                onChange={(e) => setWhatsappNumber(e.target.value)}
                placeholder={t("patients:register.whatsapp_placeholder")}
                className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
              />
              <p className="mt-1 text-xs text-slate-400">
                {t("patients:register.whatsapp_hint")}
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
                <span className="ms-2.5 text-xs sm:text-sm text-slate-700 leading-snug">
                  {t("patients:register.consent")}
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
              {t("common:actions.cancel")}
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
              <span>
                {isLoading
                  ? t("patients:register.registering")
                  : t("patients:register.title")}
              </span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
export default RegisterPatientScreen;
