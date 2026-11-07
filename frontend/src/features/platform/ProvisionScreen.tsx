import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { platformService } from "./platformService";
import type { ProvisionTenantPayload } from "./types";
import { slugProblem } from "./types";

export function ProvisionScreen(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Form Fields
  const [labName, setLabName] = useState("");
  const [slug, setSlug] = useState("");
  const [city, setCity] = useState("Lahore");
  const [province, setProvince] = useState("Punjab");
  const [ownerName, setOwnerName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerPhone, setOwnerPhone] = useState("");
  const [selectedPlanId, setSelectedPlanId] = useState<string>("");
  const [branchQuota, setBranchQuota] = useState<string>("3");
  const [staffSeats, setStaffSeats] = useState<number>(10);
  const [enabledRoles, setEnabledRoles] = useState<string[]>([
    "owner",
    "manager",
    "receptionist",
    "technician",
    "pathologist",
  ]);

  // Master Temp Credential (Doc 1)
  const [tempPass, setTempPass] = useState<string>("");
  const [copiedPass, setCopiedPass] = useState<boolean>(false);

  // Field validation and API errors
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);

  // Generate random temp password matching LBF-XXXX-XX#
  const generateNewPassword = () => {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    let p1 = "";
    for (let i = 0; i < 4; i++) p1 += chars.charAt(Math.floor(Math.random() * chars.length));
    let p2 = "";
    for (let i = 0; i < 2; i++) p2 += chars.charAt(Math.floor(Math.random() * chars.length));
    setTempPass(`LBF-${p1}-${p2}#`);
  };

  useEffect(() => {
    generateNewPassword();
  }, []);

  // Fetch real platform plans from API
  const { data: plansData, isLoading: plansLoading } = useQuery({
    queryKey: ["platform", "plans"],
    queryFn: () => platformService.listPlans(),
  });

  const plans = plansData?.plans || [];

  // Pre-select "Growth" plan by default
  useEffect(() => {
    if (plans.length > 0 && !selectedPlanId) {
      const growth = plans.find((p) => p.name.toLowerCase().includes("growth"));
      if (growth) {
        setSelectedPlanId(growth.id);
      } else if (plans[0]) {
        setSelectedPlanId(plans[0].id);
      }
    }
  }, [plans, selectedPlanId]);

  // Auto-sync slug from labName if user hasn't edited slug manually
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);
  const handleLabNameChange = (val: string) => {
    setLabName(val);
    if (!slugManuallyEdited) {
      const generated = val
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "")
        .slice(0, 14);
      setSlug(generated);
    }
  };

  const handleSlugChange = (val: string) => {
    setSlugManuallyEdited(true);
    setSlug(val.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 20));
  };

  const toggleRole = (role: string) => {
    if (role === "owner") return; // Immutable
    setEnabledRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]
    );
  };

  const handleCopyPass = () => {
    navigator.clipboard.writeText(tempPass);
    setCopiedPass(true);
    setTimeout(() => setCopiedPass(false), 2000);
  };

  // Provision Mutation
  const provisionMutation = useMutation({
    mutationFn: (payload: ProvisionTenantPayload) =>
      platformService.provisionTenant(payload),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["platform", "tenants"] });
      queryClient.invalidateQueries({ queryKey: ["platform", "metrics"] });
      navigate(`/platform/tenants/${data.id}`);
    },
    onError: (err: any) => {
      if (err.problem?.errors) {
        const errors: Record<string, string> = {};
        for (const [k, v] of Object.entries(err.problem.errors)) {
          errors[k] = Array.isArray(v) ? v[0] : String(v);
        }
        setFieldErrors(errors);
      } else {
        setGeneralError(err.message || "Failed to provision tenant.");
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFieldErrors({});
    setGeneralError(null);

    const errors: Record<string, string> = {};
    if (!labName.trim()) {
      errors.name = "Laboratory name is required.";
    }
    const slugErr = slugProblem(slug);
    if (slugErr) {
      errors.slug = slugErr;
    }
    if (!ownerName.trim()) {
      errors.owner_name = "Primary administrator name is required.";
    }
    if (!ownerEmail.trim() || !ownerEmail.includes("@")) {
      errors.owner_email = "Valid administrator work email is required.";
    }
    if (!selectedPlanId) {
      errors.plan_id = "Please select a subscription tier.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    const payload: ProvisionTenantPayload = {
      name: labName.trim(),
      slug: slug.trim(),
      plan_id: selectedPlanId,
      owner_name: ownerName.trim(),
      owner_email: ownerEmail.trim().toLowerCase(),
      city: city.trim(),
      province: province.trim(),
      phone: ownerPhone.trim() || "+92 300 0000000",
      whatsapp: ownerPhone.trim() || "+92 300 0000000",
      staff_seats: staffSeats,
      branch_count: branchQuota === "Unlimited" ? 99 : Number(branchQuota),
      enabled_roles: enabledRoles,
    };

    provisionMutation.mutate(payload);
  };

  const selectedPlan = plans.find((p) => p.id === selectedPlanId);

  return (
    <div className="flex flex-col w-full gap-space-lg max-w-7xl mx-auto pb-24">
      {/* Provisioning Header & Meta Strip */}
      <div className="flex flex-col gap-space-xs mb-space-sm">
        {/* Breadcrumb & Status Pill */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-space-xs text-outline font-label-sm text-label-sm">
            <Link
              to="/platform/tenants"
              className="hover:text-primary transition-colors flex items-center gap-1"
            >
              <span className="material-symbols-outlined text-[16px]">biotech</span>
              <span>Labs</span>
            </Link>
            <span className="text-outline-variant font-code-sm">/</span>
            <span className="text-on-surface font-title-sm text-title-sm">
              New Lab Provisioning
            </span>
          </div>
          <div className="flex items-center gap-space-sm">
            <span className="inline-flex items-center gap-space-xs px-space-sm py-space-2xs rounded bg-surface-container-high text-on-surface-variant font-code-sm text-code-sm font-semibold">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
              INFRA READY: REGION PK-ISB-01
            </span>
            <span className="font-code-sm text-code-sm text-outline">SCHEMA ENGINE v4.2</span>
          </div>
        </div>

        {/* Title and Subtitle Hierarchy */}
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-space-md pt-space-xs">
          <div>
            <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight">
              Provision a new lab — grant access
            </h1>
            <p className="font-body-md text-body-md text-on-surface-variant mt-space-2xs max-w-3xl">
              Initialize an isolated tenant database, configure staff quotas, and issue primary administrator credentials.
            </p>
          </div>
          <div className="flex items-center gap-space-sm bg-surface-container-low px-space-md py-space-xs rounded border border-outline-variant/30">
            <span className="material-symbols-outlined text-primary text-[18px]">verified_user</span>
            <span className="font-label-sm text-label-sm text-on-surface font-medium">
              Auto-sandboxed Multi-Tenant Cluster
            </span>
          </div>
        </div>
      </div>

      {generalError && (
        <div className="p-space-md bg-error-container/20 border border-error/30 rounded text-error text-sm">
          {generalError}
        </div>
      )}

      {/* Form Grid: 2 Columns (8 Cols left, 4 Cols right) */}
      <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
        {/* Left Column: Form Sections (8 Cols) */}
        <div className="lg:col-span-8 flex flex-col gap-space-lg">
          {/* Section 1: Lab Information */}
          <section className="bg-surface-container-lowest p-space-xl rounded-lg shadow-sm border border-outline-variant/30 space-y-space-md">
            <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-sm">
                <span className="flex items-center justify-center w-7 h-7 rounded bg-primary-container text-on-primary font-headline-sm text-headline-sm">
                  1
                </span>
                <div>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">
                    Lab Information
                  </h2>
                  <p className="font-body-xs text-body-xs text-outline">
                    Laboratory legal entity name, operating zone, and routing subdomain
                  </p>
                </div>
              </div>
              <span className="material-symbols-outlined text-outline">domain</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md pt-space-xs">
              <div className="space-y-space-2xs md:col-span-2">
                <label className="block font-label-sm text-label-sm text-on-surface uppercase tracking-wider">
                  Laboratory Entity Display Name <span className="text-error">*</span>
                </label>
                <input
                  className="w-full h-9 px-space-sm bg-surface-container-lowest text-on-surface font-body-sm text-body-sm rounded outline-none border border-outline-variant focus:border-primary focus:ring-1 focus:ring-primary"
                  placeholder="e.g. Al-Razi Diagnostic Centre Lahore"
                  type="text"
                  value={labName}
                  onChange={(e) => handleLabNameChange(e.target.value)}
                />
                {fieldErrors.name && (
                  <span className="text-xs text-error block">{fieldErrors.name}</span>
                )}
                <span className="font-body-xs text-body-xs text-outline">
                  Registered name as recognized by healthcare regulatory bodies
                </span>
              </div>

              <div className="space-y-space-2xs">
                <label className="block font-label-sm text-label-sm text-on-surface uppercase tracking-wider">
                  City / Location <span className="text-error">*</span>
                </label>
                <select
                  className="w-full h-9 px-space-sm bg-surface-container-lowest text-on-surface font-body-sm text-body-sm rounded outline-none border border-outline-variant focus:border-primary focus:ring-1 focus:ring-primary cursor-pointer"
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                >
                  <option value="Lahore">Lahore (Punjab Zone A)</option>
                  <option value="Islamabad">Islamabad (Capital Hub)</option>
                  <option value="Rawalpindi">Rawalpindi (Punjab North)</option>
                  <option value="Karachi">Karachi (Sindh Zone A)</option>
                  <option value="Peshawar">Peshawar (KPK Northern)</option>
                  <option value="Faisalabad">Faisalabad (Punjab Central)</option>
                  <option value="Multan">Multan (Punjab South)</option>
                  <option value="Quetta">Quetta (Balochistan)</option>
                </select>
              </div>

              <div className="space-y-space-2xs">
                <label className="block font-label-sm text-label-sm text-on-surface uppercase tracking-wider">
                  Province / Territory <span className="text-error">*</span>
                </label>
                <select
                  className="w-full h-9 px-space-sm bg-surface-container-lowest text-on-surface font-body-sm text-body-sm rounded outline-none border border-outline-variant focus:border-primary focus:ring-1 focus:ring-primary cursor-pointer"
                  value={province}
                  onChange={(e) => setProvince(e.target.value)}
                >
                  <option value="Punjab">Punjab</option>
                  <option value="Sindh">Sindh</option>
                  <option value="ICT">Islamabad Capital Territory</option>
                  <option value="Khyber Pakhtunkhwa">Khyber Pakhtunkhwa</option>
                  <option value="Balochistan">Balochistan</option>
                </select>
              </div>

              <div className="space-y-space-2xs md:col-span-2">
                <label className="block font-label-sm text-label-sm text-on-surface uppercase tracking-wider">
                  Tenant Subdomain Route <span className="text-error">*</span>
                </label>
                <div className="flex items-center h-9 bg-surface-container-low rounded border border-outline-variant focus-within:border-primary focus-within:ring-1 focus-within:ring-primary overflow-hidden">
                  <input
                    className="h-full px-space-sm bg-surface-container-lowest text-on-surface font-body-sm text-body-sm outline-none flex-1 border-r border-outline-variant font-code-sm"
                    type="text"
                    value={slug}
                    onChange={(e) => handleSlugChange(e.target.value)}
                    placeholder="e.g. alrazi"
                  />
                  <span className="px-space-sm font-code-sm text-code-sm text-on-surface-variant font-semibold select-none bg-surface-container">
                    .labflow.app
                  </span>
                </div>
                {fieldErrors.slug && (
                  <span className="text-xs text-error block">{fieldErrors.slug}</span>
                )}
                <span className="font-body-xs text-body-xs text-outline">
                  Isolated database schema suffix: <strong className="text-on-surface font-normal">tenant_{slug || "..."}</strong>
                </span>
              </div>
            </div>
          </section>

          {/* Section 2: Owner Contact & Superadmin Access */}
          <section className="bg-surface-container-lowest p-space-xl rounded-lg shadow-sm border border-outline-variant/30 space-y-space-md">
            <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-sm">
                <span className="flex items-center justify-center w-7 h-7 rounded bg-primary-container text-on-primary font-headline-sm text-headline-sm">
                  2
                </span>
                <div>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">
                    Superadmin Access
                  </h2>
                  <p className="font-body-xs text-body-xs text-outline">
                    Primary administrator profile, contact channels, and temporary credential
                  </p>
                </div>
              </div>
              <span className="material-symbols-outlined text-outline">badge</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md pt-space-xs">
              <div className="space-y-space-2xs md:col-span-1">
                <label className="block font-label-sm text-label-sm text-on-surface uppercase tracking-wider">
                  Primary Owner Name <span className="text-error">*</span>
                </label>
                <input
                  className="w-full h-9 px-space-sm bg-surface-container-lowest text-on-surface font-body-sm text-body-sm rounded outline-none border border-outline-variant focus:border-primary focus:ring-1 focus:ring-primary"
                  placeholder="e.g. Dr. Salman Tariq"
                  type="text"
                  value={ownerName}
                  onChange={(e) => setOwnerName(e.target.value)}
                />
                {fieldErrors.owner_name && (
                  <span className="text-xs text-error block">{fieldErrors.owner_name}</span>
                )}
              </div>

              <div className="space-y-space-2xs md:col-span-1">
                <label className="block font-label-sm text-label-sm text-on-surface uppercase tracking-wider">
                  Owner WhatsApp / GSM
                </label>
                <div className="relative">
                  <span className="material-symbols-outlined absolute left-space-xs top-1/2 -translate-y-1/2 text-primary text-[18px]">
                    chat
                  </span>
                  <input
                    className="w-full h-9 pl-8 pr-space-sm bg-surface-container-lowest text-on-surface font-body-sm text-body-sm rounded outline-none border border-outline-variant focus:border-primary focus:ring-1 focus:ring-primary font-code-sm"
                    placeholder="+92 300 1234567"
                    type="tel"
                    value={ownerPhone}
                    onChange={(e) => setOwnerPhone(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-space-2xs md:col-span-1">
                <label className="block font-label-sm text-label-sm text-on-surface uppercase tracking-wider">
                  Superadmin Email <span className="text-error">*</span>
                </label>
                <div className="relative">
                  <span className="material-symbols-outlined absolute left-space-xs top-1/2 -translate-y-1/2 text-outline text-[18px]">
                    mail
                  </span>
                  <input
                    className="w-full h-9 pl-8 pr-2 bg-surface-container-lowest text-on-surface font-body-sm text-body-sm rounded outline-none border border-outline-variant focus:border-primary focus:ring-1 focus:ring-primary font-code-sm"
                    placeholder="owner@lab.pk"
                    type="email"
                    value={ownerEmail}
                    onChange={(e) => setOwnerEmail(e.target.value)}
                  />
                </div>
                {fieldErrors.owner_email && (
                  <span className="text-xs text-error block">{fieldErrors.owner_email}</span>
                )}
              </div>
            </div>

            {/* Master Temp Password Block (Doc 1) */}
            <div className="flex flex-col gap-space-2xs bg-surface-container-low p-space-md rounded border border-outline-variant/60 mt-space-md">
              <div className="flex items-center justify-between">
                <label className="font-label-sm text-label-sm text-on-surface font-bold uppercase tracking-wider">
                  Master Temporary Credential
                </label>
                <span className="font-body-xs text-body-xs text-error font-medium">
                  Expires in 24h
                </span>
              </div>
              <div className="flex items-center justify-between gap-space-sm my-1">
                <span className="font-code-sm text-base text-primary font-bold tracking-widest">
                  {tempPass}
                </span>
                <div className="flex items-center gap-space-xs">
                  <button
                    type="button"
                    onClick={generateNewPassword}
                    className="px-space-xs py-space-2xs bg-surface-container hover:bg-surface-container-high rounded text-xs text-on-surface flex items-center gap-1 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[14px]">refresh</span>
                    <span>Regenerate</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleCopyPass}
                    className="px-space-xs py-space-2xs bg-surface-container hover:bg-surface-container-high rounded text-xs text-on-surface flex items-center gap-1 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[14px]">
                      {copiedPass ? "done" : "content_copy"}
                    </span>
                    <span>{copiedPass ? "Copied" : "Copy"}</span>
                  </button>
                </div>
              </div>
              <span className="font-body-xs text-body-xs text-outline">
                Forced password change is enforced upon primary operator access.
              </span>
            </div>
          </section>

          {/* Section 3: Subscription Tier & SLA */}
          <section className="bg-surface-container-lowest p-space-xl rounded-lg shadow-sm border border-outline-variant/30 space-y-space-md">
            <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-sm">
                <span className="flex items-center justify-center w-7 h-7 rounded bg-primary-container text-on-primary font-headline-sm text-headline-sm">
                  3
                </span>
                <div>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">
                    Subscription Tier &amp; SLA
                  </h2>
                  <p className="font-body-xs text-body-xs text-outline">
                    Select the commercial license tier and synchronization pipeline
                  </p>
                </div>
              </div>
              <span className="material-symbols-outlined text-outline">loyalty</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md pt-space-xs">
              {plansLoading ? (
                <div className="col-span-2 text-center py-4 text-outline">Loading plans...</div>
              ) : (
                plans.map((p) => {
                  const isSelected = selectedPlanId === p.id;
                  const isGrowth = p.name.toLowerCase().includes("growth");
                  const isLifetime = p.name.toLowerCase().includes("lifetime");

                  return (
                    <label
                      key={p.id}
                      onClick={() => setSelectedPlanId(p.id)}
                      className={`relative flex flex-col p-space-md rounded cursor-pointer transition-all border ${
                        isSelected
                          ? "bg-surface-container-lowest border-2 border-primary ring-1 ring-primary/20 shadow-sm"
                          : "bg-surface-container-low border-outline-variant/60 hover:bg-surface-container"
                      }`}
                    >
                      <input
                        type="radio"
                        name="subscription_tier"
                        value={p.id}
                        checked={isSelected}
                        onChange={() => setSelectedPlanId(p.id)}
                        className="sr-only"
                      />
                      <div className="flex items-center justify-between mb-space-2xs">
                        <div className="flex items-center gap-space-xs">
                          <span className="font-headline-sm text-headline-sm text-on-surface">
                            {p.name}
                          </span>
                          {isGrowth && (
                            <span className="px-space-xs py-space-2xs bg-primary text-on-primary font-code-sm text-[10px] uppercase rounded font-bold">
                              Recommended
                            </span>
                          )}
                        </div>
                        <span
                          className={`material-symbols-outlined text-[20px] ${
                            isSelected ? "text-primary" : "text-outline"
                          }`}
                        >
                          {isSelected ? "radio_button_checked" : "radio_button_unchecked"}
                        </span>
                      </div>

                      <div className="flex items-baseline gap-space-2xs mb-space-xs">
                        <span className="font-headline-md text-headline-md font-extrabold text-primary">
                          PKR {Number(p.price).toLocaleString()}
                        </span>
                        <span className="font-body-xs text-body-xs text-outline">
                          {isLifetime ? "one-time" : "/ monthly"}
                        </span>
                      </div>

                      <p className="font-body-xs text-body-xs text-on-surface-variant flex items-center gap-space-2xs">
                        <span className="material-symbols-outlined text-[16px] text-primary">
                          check_circle
                        </span>
                        <span>
                          {p.max_branches ? `Up to ${p.max_branches} branch(es)` : "Unlimited branches"}
                          {p.max_staff ? `, ${p.max_staff} staff seats` : ", unlimited staff seats"}
                        </span>
                      </p>
                    </label>
                  );
                })
              )}
            </div>
            {fieldErrors.plan_id && (
              <span className="text-xs text-error block">{fieldErrors.plan_id}</span>
            )}
          </section>

          {/* Section 4: Resource Allocations & Quotas */}
          <section className="bg-surface-container-lowest p-space-xl rounded-lg shadow-sm border border-outline-variant/30 space-y-space-md">
            <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-sm">
                <span className="flex items-center justify-center w-7 h-7 rounded bg-primary-container text-on-primary font-headline-sm text-headline-sm">
                  4
                </span>
                <div>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">
                    Resource Allocations &amp; Quotas
                  </h2>
                  <p className="font-body-xs text-body-xs text-outline">
                    Hardware node concurrency, branches limit, and SMS quotas
                  </p>
                </div>
              </div>
              <span className="material-symbols-outlined text-outline">tune</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md pt-space-xs">
              <div className="space-y-space-2xs">
                <label className="block font-label-sm text-label-sm text-on-surface uppercase tracking-wider">
                  Branches Allowed
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {["1", "3", "Unlimited"].map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setBranchQuota(opt)}
                      className={`h-9 rounded font-label-sm text-label-sm font-semibold transition-colors border ${
                        branchQuota === opt
                          ? "bg-primary text-on-primary border-primary shadow-xs"
                          : "bg-surface-container-low text-on-surface border-outline-variant/60 hover:bg-surface-container"
                      }`}
                    >
                      {opt} {opt === "1" ? "Branch" : opt === "3" ? "Branches" : ""}
                    </button>
                  ))}
                </div>
                <span className="font-body-xs text-body-xs text-outline block">
                  Synced to public branch counter
                </span>
              </div>

              <div className="space-y-space-2xs">
                <label className="block font-label-sm text-label-sm text-on-surface uppercase tracking-wider">
                  Staff Seat Pool
                </label>
                <div className="flex items-center h-9 border border-outline-variant rounded overflow-hidden bg-surface-container-lowest">
                  <button
                    type="button"
                    onClick={() => setStaffSeats((prev) => Math.max(1, prev - 1))}
                    className="w-9 h-full flex items-center justify-center bg-surface-container-low hover:bg-surface-container text-on-surface transition-colors select-none"
                  >
                    <span className="material-symbols-outlined text-[18px]">remove</span>
                  </button>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={staffSeats}
                    onChange={(e) => setStaffSeats(Number(e.target.value) || 1)}
                    className="flex-1 h-full text-center font-code-sm text-code-sm font-bold bg-transparent text-on-surface outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setStaffSeats((prev) => Math.min(100, prev + 1))}
                    className="w-9 h-full flex items-center justify-center bg-surface-container-low hover:bg-surface-container text-on-surface transition-colors select-none"
                  >
                    <span className="material-symbols-outlined text-[18px]">add</span>
                  </button>
                </div>
                <span className="font-body-xs text-body-xs text-outline block">
                  Simultaneous operator accounts (1–100)
                </span>
              </div>

              {/* SMS Credit Quota Display (Doc 1) */}
              <div className="md:col-span-2 flex flex-col gap-space-2xs bg-surface-container-low/50 p-space-sm rounded border border-outline-variant/40 mt-1">
                <div className="flex items-center justify-between">
                  <span className="font-label-sm text-label-sm text-on-surface-variant font-bold uppercase tracking-wider">
                    Initial Patient SMS Quota
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">
                    Branded sender ID: LABFLW
                  </span>
                </div>
                <div className="h-9 px-space-sm bg-surface-container-lowest rounded flex items-center justify-between border border-outline-variant/60">
                  <span className="font-code-sm text-code-sm font-bold text-primary">
                    1,000 Free SMS
                  </span>
                  <span className="material-symbols-outlined text-primary text-[18px]">sms</span>
                </div>
              </div>
            </div>
          </section>

          {/* Section 5: Role Permissions Enabled */}
          <section className="bg-surface-container-lowest p-space-xl rounded-lg shadow-sm border border-outline-variant/30 space-y-space-md">
            <div className="flex items-center justify-between pb-space-xs border-b border-surface-container">
              <div className="flex items-center gap-space-sm">
                <span className="flex items-center justify-center w-7 h-7 rounded bg-primary-container text-on-primary font-headline-sm text-headline-sm">
                  5
                </span>
                <div>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">
                    Role Permissions Enabled
                  </h2>
                  <p className="font-body-xs text-body-xs text-outline">
                    Initial security roles activated inside the tenant cluster
                  </p>
                </div>
              </div>
              <span className="material-symbols-outlined text-outline">security</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-sm pt-space-xs">
              <label className="flex items-start gap-space-sm p-space-sm bg-surface-container-low rounded border border-outline-variant/40 cursor-not-allowed">
                <input
                  type="checkbox"
                  checked
                  disabled
                  className="mt-0.5 w-4 h-4 rounded text-primary accent-primary"
                />
                <div className="flex flex-col">
                  <span className="font-title-sm text-title-sm text-on-surface flex items-center gap-1 font-semibold">
                    Owner / Managing Director
                    <span className="font-code-sm text-xs text-primary font-bold">(IMMUTABLE)</span>
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">
                    Full system orchestration, fiscal logs, audit access
                  </span>
                </div>
              </label>

              <label className="flex items-start gap-space-sm p-space-sm bg-surface-container-low rounded border border-outline-variant/40 cursor-pointer hover:bg-surface-container">
                <input
                  type="checkbox"
                  checked={enabledRoles.includes("manager")}
                  onChange={() => toggleRole("manager")}
                  className="mt-0.5 w-4 h-4 rounded text-primary accent-primary"
                />
                <div className="flex flex-col">
                  <span className="font-title-sm text-title-sm text-on-surface font-semibold">
                    Branch Manager
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">
                    Daily cashier balancing, shift rosters, reorder alerts
                  </span>
                </div>
              </label>

              <label className="flex items-start gap-space-sm p-space-sm bg-surface-container-low rounded border border-outline-variant/40 cursor-pointer hover:bg-surface-container">
                <input
                  type="checkbox"
                  checked={enabledRoles.includes("receptionist")}
                  onChange={() => toggleRole("receptionist")}
                  className="mt-0.5 w-4 h-4 rounded text-primary accent-primary"
                />
                <div className="flex flex-col">
                  <span className="font-title-sm text-title-sm text-on-surface font-semibold">
                    Receptionist / Phlebotomist
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">
                    Patient registration, barcode printing, vacutainer draw tags
                  </span>
                </div>
              </label>

              <label className="flex items-start gap-space-sm p-space-sm bg-surface-container-low rounded border border-outline-variant/40 cursor-pointer hover:bg-surface-container">
                <input
                  type="checkbox"
                  checked={enabledRoles.includes("technician")}
                  onChange={() => toggleRole("technician")}
                  className="mt-0.5 w-4 h-4 rounded text-primary accent-primary"
                />
                <div className="flex flex-col">
                  <span className="font-title-sm text-title-sm text-on-surface font-semibold">
                    Lab Technician
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">
                    Worklist processing, machine result entry, internal calibration
                  </span>
                </div>
              </label>

              <label className="flex items-start gap-space-sm p-space-sm bg-surface-container-low rounded border border-outline-variant/40 cursor-pointer hover:bg-surface-container md:col-span-2">
                <input
                  type="checkbox"
                  checked={enabledRoles.includes("pathologist")}
                  onChange={() => toggleRole("pathologist")}
                  className="mt-0.5 w-4 h-4 rounded text-primary accent-primary"
                />
                <div className="flex flex-col">
                  <span className="font-title-sm text-title-sm text-on-surface font-semibold">
                    Consultant Pathologist
                  </span>
                  <span className="font-body-xs text-body-xs text-outline">
                    Verification & electronic signing of hematology, histology, micro and PCR reports
                  </span>
                </div>
              </label>
            </div>
          </section>
        </div>

        {/* Right Column: Facility Summary Dossier (4 Cols) */}
        <div className="lg:col-span-4 flex flex-col gap-space-lg">
          <div className="bg-surface-container-lowest p-space-lg rounded-lg shadow-sm border-t-4 border-t-primary border-x border-b border-outline-variant/30 space-y-space-md sticky top-20">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[20px]">verified</span>
                <span className="font-title-sm text-title-sm text-on-surface uppercase tracking-wider font-bold">
                  Tenant Spec
                </span>
              </div>
              <span className="px-space-xs py-space-2xs bg-primary/10 text-primary font-code-sm text-code-sm font-bold rounded">
                PRE-FLIGHT
              </span>
            </div>

            {/* Visual Token Preview */}
            <div className="bg-surface-container-low p-space-md rounded flex items-center gap-space-md">
              <div className="w-12 h-12 rounded bg-primary-container text-on-primary flex items-center justify-center font-headline-md text-headline-md font-bold shadow-sm">
                LF
              </div>
              <div className="flex flex-col min-w-0">
                <div className="font-title-sm text-title-sm text-on-surface truncate font-bold">
                  {labName || "Lab Entity Preview"}
                </div>
                <div className="flex items-center gap-space-2xs font-code-sm text-code-sm text-primary truncate">
                  <span className="material-symbols-outlined text-[14px]">link</span>
                  <span>{slug || "slug"}.labflow.app</span>
                </div>
              </div>
            </div>

            {/* Metrics Specification Table */}
            <div className="space-y-space-xs text-body-sm font-body-sm divide-y divide-outline-variant/20">
              <div className="flex items-center justify-between py-space-2xs">
                <span className="text-outline font-label-sm text-label-sm uppercase">
                  Datacenter
                </span>
                <span className="text-on-surface font-semibold font-code-sm text-code-sm">
                  PK-ISB-01 (Islamabad)
                </span>
              </div>
              <div className="flex items-center justify-between py-space-2xs">
                <span className="text-outline font-label-sm text-label-sm uppercase">
                  Location
                </span>
                <span className="text-on-surface font-medium truncate max-w-[170px]">
                  {city}, {province}
                </span>
              </div>
              <div className="flex items-center justify-between py-space-2xs">
                <span className="text-outline font-label-sm text-label-sm uppercase">
                  Administrator
                </span>
                <span className="text-on-surface font-medium truncate max-w-[170px]">
                  {ownerName || "--"}
                </span>
              </div>
              <div className="flex items-center justify-between py-space-2xs">
                <span className="text-outline font-label-sm text-label-sm uppercase">
                  Target Tier
                </span>
                <span className="text-primary font-bold">
                  {selectedPlan?.name || "Growth"} (PKR {selectedPlan?.price || "5,999"}/mo)
                </span>
              </div>
              <div className="flex items-center justify-between py-space-2xs">
                <span className="text-outline font-label-sm text-label-sm uppercase">
                  Branch Capacity
                </span>
                <span className="text-on-surface font-semibold">
                  {branchQuota} {branchQuota === "1" ? "Branch" : "Branches"}
                </span>
              </div>
              <div className="flex items-center justify-between py-space-2xs">
                <span className="text-outline font-label-sm text-label-sm uppercase">
                  Staff Quota
                </span>
                <span className="text-on-surface font-semibold">{staffSeats} Logins</span>
              </div>
              <div className="flex items-center justify-between py-space-2xs">
                <span className="text-outline font-label-sm text-label-sm uppercase">
                  Schema Engine
                </span>
                <span className="font-code-sm text-code-sm text-primary">tenant_{slug || "..."}</span>
              </div>
            </div>

            {/* Security Notice */}
            <div className="p-space-sm bg-surface-container rounded space-y-space-2xs">
              <div className="flex items-center gap-space-2xs text-secondary font-label-sm text-label-sm font-bold">
                <span className="material-symbols-outlined text-[16px]">info</span>
                <span>Automated Onboarding Sequence</span>
              </div>
              <p className="font-body-xs text-body-xs text-on-surface-variant leading-relaxed">
                Clicking <strong className="text-on-surface">Create Lab</strong> provisions an isolated database tenant, issues master credentials, and configures laboratory barcode numbering templates.
              </p>
            </div>
          </div>
        </div>

        {/* Sticky Bottom Action Execution Bar (Doc 6) */}
        <div className="fixed bottom-0 left-64 right-0 z-30 bg-surface-container-lowest/95 backdrop-blur border-t border-outline-variant/60 shadow-lg p-space-md flex flex-col sm:flex-row items-center justify-between gap-space-md px-space-xl">
          <div className="flex items-center gap-space-sm text-body-sm font-body-sm text-on-surface-variant">
            <span className="w-2.5 h-2.5 rounded-full bg-primary animate-ping"></span>
            <span className="font-medium text-on-surface">
              CLUSTER PK-ISB-01 // TENANT SCHEMA:{" "}
              <strong className="text-primary font-code-sm font-bold">tenant_{slug || "slug"}</strong>
            </span>
          </div>

          <div className="flex items-center gap-space-md w-full sm:w-auto justify-end">
            <button
              type="button"
              onClick={() => navigate("/platform/tenants")}
              className="h-9 px-space-lg bg-surface-container-low hover:bg-surface-container text-on-surface rounded font-label-sm text-label-sm transition-colors border border-outline-variant/40"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={provisionMutation.isPending}
              className="h-9 px-space-xl bg-primary hover:bg-primary-container text-on-primary rounded font-label-sm text-label-sm flex items-center gap-space-sm shadow transition-all active:scale-[0.98] disabled:opacity-50 font-bold"
            >
              <span className="material-symbols-outlined text-[18px]">verified</span>
              <span>
                {provisionMutation.isPending
                  ? "Provisioning Tenant..."
                  : "Create Lab & Grant Access"}
              </span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
