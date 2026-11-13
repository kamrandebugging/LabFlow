import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  Building2,
  Clock,
  Layers,
  MapPin,
  Pencil,
  Percent,
  Plus,
  Power,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { useAuthStore } from "../auth/authStore";
import { settingsService } from "../settings/settingsService";
import type { Branch } from "../settings/types";
import { messageForError } from "../../lib/errors";
import { formatPercent } from "../../lib/format";
import { PartnerApiError, partnersService } from "./partnersService";
import type {
  CreateRulePayload,
  ReferralPartner,
  RevenueShareRule,
  UpdateRulePayload,
} from "./types";

export const RulesScreen: React.FC = () => {
  const { t } = useTranslation(["partners", "common"]);
  const { id } = useParams<{ id: string }>();
  const user = useAuthStore((s) => s.user);
  const isOwner = user?.role === "owner";

  // Data state
  const [partner, setPartner] = useState<ReferralPartner | null>(null);
  const [rules, setRules] = useState<RevenueShareRule[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Modals state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [editingRule, setEditingRule] = useState<RevenueShareRule | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Create form state
  const [createBranchId, setCreateBranchId] = useState<string>("");
  const [createCategory, setCreateCategory] = useState<string>("");
  const [createPercent, setCreatePercent] = useState<string>("10.00");
  const [createEffectiveFrom, setCreateEffectiveFrom] = useState<string>(
    new Date().toISOString().split("T")[0] || "",
  );

  // Edit form state
  const [editPercent, setEditPercent] = useState<string>("");
  const [editEffectiveFrom, setEditEffectiveFrom] = useState<string>(
    new Date().toISOString().split("T")[0] || "",
  );

  const branchMap = useMemo(() => {
    const map = new Map<string, string>();
    branches.forEach((b) => map.set(b.id, b.name));
    return map;
  }, [branches]);

  const fetchData = useCallback(async (): Promise<void> => {
    if (!id) return;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const [partnerData, rulesData, branchesData] = await Promise.all([
        partnersService.getPartner(id),
        partnersService.getPartnerRules(id),
        settingsService.getBranches(false).catch(() => []),
      ]);
      setPartner(partnerData);
      setRules(rulesData);
      setBranches(branchesData);
    } catch (err: unknown) {
      setErrorMsg(
        err instanceof PartnerApiError
          ? messageForError(err, t)
          : t("partners:errors.load_rules"),
      );
    } finally {
      setIsLoading(false);
    }
  }, [id, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Specificity grouping
  const group1Rules = useMemo(
    () => rules.filter((r) => r.branch_id && r.test_category),
    [rules],
  );
  const group2Rules = useMemo(
    () => rules.filter((r) => r.branch_id && !r.test_category),
    [rules],
  );
  const group3Rules = useMemo(
    () => rules.filter((r) => !r.branch_id && r.test_category),
    [rules],
  );
  const group4Rules = useMemo(
    () => rules.filter((r) => !r.branch_id && !r.test_category),
    [rules],
  );

  const activeRulesCount = useMemo(
    () => rules.filter((r) => !r.effective_to).length,
    [rules],
  );

  const openCreateModal = () => {
    setActionError(null);
    setCreateBranchId("");
    setCreateCategory("");
    setCreatePercent("10.00");
    setCreateEffectiveFrom(new Date().toISOString().split("T")[0] || "");
    setIsCreateModalOpen(true);
  };

  const handleCreateRule = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    if (!id) return;
    setActionError(null);
    setIsSubmitting(true);

    try {
      const payload: CreateRulePayload = {
        branch_id: createBranchId.trim() ? createBranchId.trim() : null,
        test_category: createCategory.trim() ? createCategory.trim() : null,
        percent: parseFloat(createPercent).toFixed(2),
        effective_from: createEffectiveFrom,
      };

      await partnersService.createPartnerRule(id, payload);
      setIsCreateModalOpen(false);
      await fetchData();
    } catch (err: unknown) {
      if (err instanceof PartnerApiError) {
        if (err.code === "rule_overlap") {
          setActionError(
            t("partners:errors.rule_overlap_create", {
              branch: createBranchId
                ? branchMap.get(createBranchId) || createBranchId
                : t("partners:rules.all_branches"),
              category: createCategory || t("partners:rules.all_categories"),
            }),
          );
        } else {
          setActionError(messageForError(err, t));
        }
      } else if (err instanceof Error) {
        setActionError(messageForError(err, t));
      } else {
        setActionError(t("partners:errors.create_rule"));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const openEditModal = (rule: RevenueShareRule) => {
    setActionError(null);
    setEditingRule(rule);
    setEditPercent(rule.percent);
    // Suggest tomorrow or today for effective_from
    const today = new Date().toISOString().split("T")[0] || "";
    setEditEffectiveFrom(
      today > rule.effective_from ? today : rule.effective_from,
    );
  };

  const handleUpdateRule = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    if (!editingRule) return;
    setActionError(null);
    setIsSubmitting(true);

    try {
      const payload: UpdateRulePayload = {
        percent: parseFloat(editPercent).toFixed(2),
        effective_from: editEffectiveFrom,
      };

      await partnersService.updatePartnerRule(editingRule.id, payload);
      setEditingRule(null);
      await fetchData();
    } catch (err: unknown) {
      if (err instanceof PartnerApiError) {
        if (err.code === "rule_retroactive") {
          setActionError(t("partners:errors.rule_retroactive"));
        } else if (err.code === "rule_overlap") {
          setActionError(t("partners:errors.rule_overlap_update"));
        } else {
          setActionError(messageForError(err, t));
        }
      } else if (err instanceof Error) {
        setActionError(messageForError(err, t));
      } else {
        setActionError(t("partners:errors.update_rule"));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCloseRule = async (rule: RevenueShareRule): Promise<void> => {
    if (
      !confirm(
        t("partners:rules.retire_confirm", {
          percent: rule.percent,
        }),
      )
    ) {
      return;
    }
    setActionError(null);
    setIsSubmitting(true);
    try {
      // Per RR-3, update rule with effective_from closes old rule
      const today = new Date().toISOString().split("T")[0] || "";
      await partnersService.updatePartnerRule(rule.id, {
        effective_from:
          today > rule.effective_from ? today : rule.effective_from,
        percent: rule.percent,
      });
      await fetchData();
    } catch {
      alert(t("partners:errors.close_rule"));
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderRuleRows = (
    groupRules: RevenueShareRule[],
    groupLabel: string,
  ) => {
    if (groupRules.length === 0) return null;

    return groupRules.map((rule) => {
      const isClosed = Boolean(rule.effective_to);
      const branchName = rule.branch_id
        ? branchMap.get(rule.branch_id) ||
          t("partners:rules.branch_fallback", {
            id: rule.branch_id.slice(0, 8),
          })
        : "—";
      const categoryName = rule.test_category || "—";

      return (
        <tr
          key={rule.id}
          className={`hover:bg-slate-50/70 transition-colors ${
            isClosed ? "opacity-60 bg-slate-50/40" : ""
          }`}
          data-testid={`rule-row-${rule.id}`}
        >
          <td className="py-3.5 px-4 font-medium text-slate-900">
            <div className="flex items-center gap-2">
              {rule.branch_id && (
                <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              )}
              <span>{branchName}</span>
            </div>
          </td>
          <td className="py-3.5 px-4">
            {rule.test_category ? (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-800 border border-slate-200">
                {categoryName}
              </span>
            ) : (
              <span className="text-slate-400 font-mono">—</span>
            )}
          </td>
          <td className="py-3.5 px-4 font-mono font-semibold text-slate-900 text-[13px]">
            {formatPercent(rule.percent)}
          </td>
          <td className="py-3.5 px-4">
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-teal-50 text-teal-700 border border-teal-200">
              {groupLabel}
            </span>
          </td>
          <td className="py-3.5 px-4">
            {isClosed ? (
              <span className="inline-flex items-center gap-1.5 text-slate-500 font-semibold text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
                {t("partners:rules.closed")}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-emerald-600 font-semibold text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-600"></span>
                {t("common:status.active")}
              </span>
            )}
          </td>
          <td className="py-3.5 px-4 text-slate-500 font-mono text-[11px]">
            <div>
              {t("partners:rules.from_prefix")}{" "}
              <bdi dir="ltr">{rule.effective_from}</bdi>
            </div>
            {rule.effective_to && (
              <div className="text-slate-400">
                {t("partners:rules.to_prefix")}{" "}
                <bdi dir="ltr">{rule.effective_to}</bdi>
              </div>
            )}
          </td>
          <td className="py-3.5 px-4 text-end">
            {isOwner && !isClosed && (
              <div className="flex items-center justify-end gap-1.5">
                <button
                  type="button"
                  onClick={() => openEditModal(rule)}
                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-800 transition-colors"
                  title={t("partners:rules.edit_rule_title")}
                  aria-label={t("partners:rules.edit_rule_aria", {
                    id: rule.id,
                  })}
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => handleCloseRule(rule)}
                  className="p-1.5 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-600 transition-colors"
                  title={t("partners:rules.close_rule_title")}
                  aria-label={t("partners:rules.close_rule_aria", {
                    id: rule.id,
                  })}
                >
                  <Power className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </td>
        </tr>
      );
    });
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col selection:bg-teal-100 selection:text-teal-900">
      <main className="flex-1 p-6 md:p-8 max-w-6xl mx-auto w-full space-y-6">
        {/* BREADCRUMBS */}
        <div className="flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-x-2">
            <Link
              to={partner ? `/partners/${partner.id}` : "/partners"}
              className="hover:text-slate-800 transition-colors flex items-center gap-1 font-medium"
            >
              <ArrowLeft className="w-3.5 h-3.5 rtl:rotate-180" />
              <span>{t("partners:nav.partner")}</span>
            </Link>
            <span className="text-slate-300">/</span>
            <span className="font-medium text-slate-700">
              {partner?.name || "..."}
            </span>
            <span className="text-slate-300">/</span>
            <span className="text-slate-900 font-semibold">
              {t("partners:nav.rules")}
            </span>
          </div>
          <div className="text-slate-400 text-[11px] font-mono" dir="ltr">
            {partner ? t("partners:nav.record_id", { id: partner.id }) : ""}
          </div>
        </div>

        {/* ERROR BANNER */}
        {errorMsg && (
          <div className="p-4 bg-red-50 border border-red-200 text-red-800 rounded-xl text-xs flex items-center gap-3">
            <ShieldAlert className="w-4 h-4 text-red-600 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* PARTNER CONTEXT BANNER */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-lg bg-teal-50 border border-teal-100 text-teal-700 flex items-center justify-center font-bold text-lg shrink-0">
              <Building2 className="w-6 h-6 text-teal-600" />
            </div>
            <div>
              <div className="flex items-center gap-2.5 flex-wrap">
                <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                  {partner?.name || t("partners:rules.partner_loading")}
                </h1>
                {partner && (
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                      partner.is_active
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : "bg-slate-100 text-slate-600 border border-slate-200"
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full me-1.5 ${
                        partner.is_active ? "bg-emerald-600" : "bg-slate-400"
                      }`}
                    ></span>
                    {partner.is_active
                      ? t("partners:rules.active_partner")
                      : t("partners:rules.inactive_partner")}
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 mt-1.5 text-xs text-slate-600">
                {partner?.organisation && (
                  <span>
                    <span className="text-slate-500">
                      {t("partners:rules.org_label")}
                    </span>{" "}
                    <span className="font-medium text-slate-800">
                      {partner.organisation}
                    </span>
                  </span>
                )}
                {partner?.phone && (
                  <span>
                    <span className="text-slate-500">
                      {t("partners:rules.phone_label")}
                    </span>{" "}
                    <span className="font-mono font-medium text-slate-800">
                      {partner.phone}
                    </span>
                  </span>
                )}
                <span className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-slate-500">
                    {t("partners:rules.evaluation_label")}
                  </span>
                  <span className="font-medium text-slate-800">
                    {t("partners:rules.evaluation_value")}
                  </span>
                </span>
              </div>
            </div>
          </div>

          {/* Quick links */}
          {partner && (
            <div className="flex items-center gap-2">
              <Link
                to={`/partners/ledger?partner_id=${partner.id}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
              >
                <span>{t("partners:rules.share_ledger")}</span>
              </Link>
              <Link
                to={`/partners/${partner.id}/dashboard`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
              >
                <span>{t("partners:rules.dashboard")}</span>
              </Link>
            </div>
          )}
        </div>

        {/* SECTION HEADER */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-1">
          <div>
            <div className="flex items-baseline gap-3">
              <h2 className="text-lg font-bold text-slate-900 tracking-tight">
                {t("partners:rules.section_title")}
              </h2>
            </div>
            <p className="text-xs text-slate-600 mt-1 max-w-2xl leading-relaxed">
              {t("partners:rules.specificity_note_before")}{" "}
              <code className="font-mono text-[11px] bg-slate-100 text-slate-800 px-1.5 py-0.5 rounded border border-slate-200">
                422 rule_overlap
              </code>
              {t("partners:rules.specificity_note_after")}
            </p>
          </div>

          {isOwner && (
            <div className="shrink-0">
              <button
                type="button"
                onClick={openCreateModal}
                className="inline-flex items-center justify-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-700 rounded-lg shadow-xs transition-colors focus:ring-2 focus:ring-teal-500 focus:ring-offset-1"
              >
                <Plus className="w-4 h-4" />
                <span>{t("partners:rules.new_rule")}</span>
              </button>
            </div>
          )}
        </div>

        {/* SPECIFICITY SPECIFICATION STRIP */}
        <div className="bg-teal-50/60 border border-teal-200/80 rounded-lg p-3 text-xs flex items-center justify-between text-teal-900">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-teal-700 shrink-0" />
            <span>
              <strong className="font-semibold text-teal-950">
                {t("partners:rules.cascade_title")}
              </strong>
              <span className="text-teal-800 ms-1">
                {t("partners:rules.cascade_body")}
              </span>
            </span>
          </div>
          <span className="text-[11px] font-mono text-teal-700 bg-white/70 px-2 py-0.5 rounded border border-teal-200 font-medium hidden md:inline">
            {t("partners:rules.strict_order")}
          </span>
        </div>

        {/* RULES TABLE CARD */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
          {isLoading ? (
            <div className="p-8 text-center text-xs text-slate-500">
              {t("partners:rules.loading")}
            </div>
          ) : rules.length === 0 ? (
            <div className="p-12 text-center text-xs text-slate-500">
              {t("partners:rules.empty")}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-start border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50/80 border-b border-slate-200 text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
                    <th className="py-3 px-4 w-48">
                      {t("partners:rules.branch")}
                    </th>
                    <th className="py-3 px-4 w-44">
                      {t("partners:rules.category")}
                    </th>
                    <th className="py-3 px-4 w-32 font-mono">
                      {t("partners:rules.percent")}
                    </th>
                    <th className="py-3 px-4 w-44">
                      {t("partners:rules.specificity")}
                    </th>
                    <th className="py-3 px-4 w-28">
                      {t("common:labels.status")}
                    </th>
                    <th className="py-3 px-4 w-44">
                      {t("partners:rules.validity")}
                    </th>
                    <th className="py-3 px-4 text-end w-20">
                      {t("common:labels.actions")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {/* GROUP 1: BRANCH + CATEGORY */}
                  {group1Rules.length > 0 && (
                    <>
                      <tr className="bg-slate-100/70 border-t border-b border-slate-200/80 font-semibold text-slate-800">
                        <td colSpan={7} className="py-2 px-4">
                          <div className="flex items-center gap-2">
                            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-teal-600 text-white text-[11px] font-bold">
                              1
                            </span>
                            <span className="text-slate-900 text-xs font-semibold">
                              {t("partners:rules.group1_title")}
                            </span>
                            <span className="text-[11px] font-normal text-slate-500 ms-2">
                              {t("partners:rules.group1_note")}
                            </span>
                          </div>
                        </td>
                      </tr>
                      {renderRuleRows(
                        group1Rules,
                        t("partners:rules.group1_badge"),
                      )}
                    </>
                  )}

                  {/* GROUP 2: BRANCH ONLY */}
                  {group2Rules.length > 0 && (
                    <>
                      <tr className="bg-slate-100/70 border-t border-b border-slate-200/80 font-semibold text-slate-800">
                        <td colSpan={7} className="py-2 px-4">
                          <div className="flex items-center gap-2">
                            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-teal-600 text-white text-[11px] font-bold">
                              2
                            </span>
                            <span className="text-slate-900 text-xs font-semibold">
                              {t("partners:rules.group2_title")}
                            </span>
                            <span className="text-[11px] font-normal text-slate-500 ms-2">
                              {t("partners:rules.group2_note")}
                            </span>
                          </div>
                        </td>
                      </tr>
                      {renderRuleRows(
                        group2Rules,
                        t("partners:rules.group2_badge"),
                      )}
                    </>
                  )}

                  {/* GROUP 3: CATEGORY ONLY */}
                  {group3Rules.length > 0 && (
                    <>
                      <tr className="bg-slate-100/70 border-t border-b border-slate-200/80 font-semibold text-slate-800">
                        <td colSpan={7} className="py-2 px-4">
                          <div className="flex items-center gap-2">
                            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-teal-600 text-white text-[11px] font-bold">
                              3
                            </span>
                            <span className="text-slate-900 text-xs font-semibold">
                              {t("partners:rules.group3_title")}
                            </span>
                            <span className="text-[11px] font-normal text-slate-500 ms-2">
                              {t("partners:rules.group3_note")}
                            </span>
                          </div>
                        </td>
                      </tr>
                      {renderRuleRows(
                        group3Rules,
                        t("partners:rules.group3_badge"),
                      )}
                    </>
                  )}

                  {/* GROUP 4: PARTNER-WIDE FALLBACK */}
                  {group4Rules.length > 0 && (
                    <>
                      <tr className="bg-slate-100/70 border-t border-b border-slate-200/80 font-semibold text-slate-800">
                        <td colSpan={7} className="py-2 px-4">
                          <div className="flex items-center gap-2">
                            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-teal-600 text-white text-[11px] font-bold">
                              4
                            </span>
                            <span className="text-slate-900 text-xs font-semibold">
                              {t("partners:rules.group4_title")}
                            </span>
                            <span className="text-[11px] font-normal text-slate-500 ms-2">
                              {t("partners:rules.group4_note")}
                            </span>
                          </div>
                        </td>
                      </tr>
                      {renderRuleRows(
                        group4Rules,
                        t("partners:rules.group4_badge"),
                      )}
                    </>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* TABLE FOOTER */}
          <div className="p-4 bg-slate-50/90 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
            <div className="text-slate-600 flex items-center gap-2">
              <Percent className="w-4 h-4 text-slate-400 shrink-0" />
              <span>{t("partners:rules.percent_note")}</span>
            </div>
            <div className="text-[11px] font-mono text-slate-500 flex items-center gap-2">
              <span>
                {t("partners:rules.total_active", { n: activeRulesCount })}
              </span>
            </div>
          </div>
        </div>
      </main>

      {/* CREATE RULE MODAL */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg overflow-hidden">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  {t("partners:rules.create_title")}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {t("partners:rules.create_subtitle_before")}{" "}
                  <bdi dir="ltr">{partner?.name}</bdi>
                  {t("partners:rules.create_subtitle_after")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsCreateModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 text-lg p-1"
                aria-label={t("common:actions.close")}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateRule} className="p-5 space-y-4 text-xs">
              {actionError && (
                <div className="p-3 bg-red-50 border border-red-200 text-red-800 rounded-lg flex items-start gap-2">
                  <ShieldAlert className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                  <span>{actionError}</span>
                </div>
              )}

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  {t("partners:rules.branch_optional")}
                </label>
                <select
                  value={createBranchId}
                  onChange={(e) => setCreateBranchId(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-900 focus:bg-white focus:ring-1 focus:ring-teal-600 focus:border-teal-600"
                >
                  <option value="">
                    {t("partners:rules.all_branches_option")}
                  </option>
                  {branches.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name} ({b.code})
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-400 mt-1">
                  {t("partners:rules.branch_hint")}
                </p>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  {t("partners:rules.category_optional")}
                </label>
                <input
                  type="text"
                  value={createCategory}
                  onChange={(e) => setCreateCategory(e.target.value)}
                  placeholder={t("partners:rules.category_placeholder")}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-900 focus:bg-white focus:ring-1 focus:ring-teal-600 focus:border-teal-600"
                />
                <p className="text-[11px] text-slate-400 mt-1">
                  {t("partners:rules.category_hint")}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    {t("partners:rules.share_percent")}
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="100"
                    required
                    value={createPercent}
                    onChange={(e) => setCreatePercent(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-900 focus:bg-white focus:ring-1 focus:ring-teal-600 focus:border-teal-600 font-mono"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    {t("partners:rules.effective_from")}
                  </label>
                  <input
                    type="date"
                    required
                    value={createEffectiveFrom}
                    onChange={(e) => setCreateEffectiveFrom(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-900 focus:bg-white focus:ring-1 focus:ring-teal-600 focus:border-teal-600 font-mono"
                  />
                </div>
              </div>

              <div className="p-3 bg-teal-50/50 rounded-lg border border-teal-100 text-[11px] text-teal-900 flex items-start gap-2">
                <Sparkles className="w-3.5 h-3.5 text-teal-600 shrink-0 mt-0.5" />
                <span>{t("partners:rules.specificity_auto")}</span>
              </div>

              <div className="pt-2 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-4 py-2 border border-slate-200 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  {t("common:actions.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
                >
                  {isSubmitting
                    ? t("partners:rules.creating")
                    : t("partners:rules.save_rule")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT RULE MODAL (RR-3 CLOSE OLD + INSERT NEW) */}
      {editingRule && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg overflow-hidden">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  {t("partners:rules.update_title")}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {t("partners:rules.update_subtitle")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditingRule(null)}
                className="text-slate-400 hover:text-slate-600 text-lg p-1"
                aria-label={t("common:actions.close")}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleUpdateRule} className="p-5 space-y-4 text-xs">
              {actionError && (
                <div className="p-3 bg-red-50 border border-red-200 text-red-800 rounded-lg flex items-start gap-2">
                  <ShieldAlert className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                  <span>{actionError}</span>
                </div>
              )}

              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 space-y-1 text-[11px] text-slate-600">
                <div>
                  <span className="font-semibold text-slate-700">
                    {t("partners:rules.scope")}
                  </span>{" "}
                  {editingRule.branch_id
                    ? branchMap.get(editingRule.branch_id) ||
                      editingRule.branch_id
                    : t("partners:rules.all_branches")}{" "}
                  ·{" "}
                  {editingRule.test_category ||
                    t("partners:rules.all_categories")}
                </div>
                <div>
                  <span className="font-semibold text-slate-700">
                    {t("partners:rules.current_rate")}
                  </span>{" "}
                  {formatPercent(editingRule.percent)} (
                  {t("partners:rules.active_since")}{" "}
                  <bdi dir="ltr">{editingRule.effective_from}</bdi>)
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    {t("partners:rules.new_share_percent")}
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="100"
                    required
                    value={editPercent}
                    onChange={(e) => setEditPercent(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-900 focus:bg-white focus:ring-1 focus:ring-teal-600 focus:border-teal-600 font-mono"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    {t("partners:rules.new_effective_from")}
                  </label>
                  <input
                    type="date"
                    required
                    value={editEffectiveFrom}
                    onChange={(e) => setEditEffectiveFrom(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-900 focus:bg-white focus:ring-1 focus:ring-teal-600 focus:border-teal-600 font-mono"
                  />
                </div>
              </div>

              <div className="p-3 bg-amber-50 rounded-lg border border-amber-200 text-[11px] text-amber-900">
                <span className="font-semibold">
                  {t("partners:rules.immutable_title")}
                </span>{" "}
                {t("partners:rules.immutable_body")}
              </div>

              <div className="pt-2 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setEditingRule(null)}
                  className="px-4 py-2 border border-slate-200 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  {t("common:actions.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
                >
                  {isSubmitting
                    ? t("partners:rules.updating")
                    : t("partners:rules.update_rule")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
