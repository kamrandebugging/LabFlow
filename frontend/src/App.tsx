import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useNavigate,
  useLocation,
  useParams,
} from "react-router-dom";
import { useAuthStore } from "./features/auth/authStore";
import { refreshSession } from "./lib/apiClient";
import i18n, { applyDocumentLanguage, isPlatformRoute } from "./i18n";
import { StaffLoginScreen } from "./features/auth/StaffLoginScreen";
import { TenantEnrollScreen } from "./features/auth/TenantEnrollScreen";
import { TwoFactorAuthScreen } from "./features/auth/TwoFactorAuthScreen";
import { PatientListScreen } from "./features/patients/PatientListScreen";
import { RegisterPatientScreen } from "./features/patients/RegisterPatientScreen";
import { PatientDetailsScreen } from "./features/patients/PatientDetailsScreen";
import { PatientEditScreen } from "./features/patients/PatientEditScreen";
import { PatientHistoryScreen } from "./features/patients/PatientHistoryScreen";
import { TestCatalogScreen } from "./features/catalog/TestCatalogScreen";
import { TestPanelsScreen } from "./features/catalog/TestPanelsScreen";
import { InvoicesListScreen } from "./features/billing/InvoicesListScreen";
import { NewInvoiceScreen } from "./features/billing/NewInvoiceScreen";
import { InvoiceDetailScreen } from "./features/billing/InvoiceDetailScreen";
import {
  SampleAccessioningListScreen,
  CollectSampleStep1Screen,
  CollectSampleStep2Screen,
  SampleDetailScreen,
  SampleLabelScreen,
  type SampleCollectionDraft,
} from "./features/samples";
import {
  WorklistScreen,
  ResultEntryScreen,
  ApprovalsQueueScreen,
  ResultDetailScreen,
  AmendResultScreen,
} from "./features/results";
import {
  ReportsListScreen,
  ReportDetailScreen,
  PatientReportAccessScreen,
  LinkExpiredScreen,
  ExceptionsScreen,
} from "./features/reports";
import {
  BranchesScreen,
  TenantSettingsScreen,
  AccountSecurityScreen,
  DataExportScreen,
} from "./features/settings";
import { settingsService } from "./features/settings/settingsService";
import {
  PartnersListScreen,
  PartnerDetailScreen,
  RulesScreen,
  LedgerScreen,
  PartnerDashboardScreen,
  SettlementsScreen,
  SettlementDetailScreen,
} from "./features/partners";
import { ScreenCatalogViewer } from "./features/screens/ScreenCatalogViewer";
import { OwnerDashboardScreen } from "./features/dashboard/OwnerDashboardScreen";
import { ManagerDashboardScreen } from "./features/dashboard/ManagerDashboardScreen";
import { ReceptionistDashboardScreen } from "./features/dashboard/ReceptionistDashboardScreen";
import { TechnicianDashboardScreen } from "./features/dashboard/TechnicianDashboardScreen";
import { PathologistDashboardScreen } from "./features/dashboard/PathologistDashboardScreen";
import { StaffScreen } from "./features/staff";
import {
  canAccessPath,
  isRoleEnabled,
  isUserRole,
  roleHome,
} from "./features/auth/access";
import { TenantLayout } from "./features/layout/TenantLayout";
import {
  AccessControlScreen,
  AuditLogScreen,
  DemoRequestDetailScreen,
  DemoRequestsScreen,
  HealthScreen,
  LabDetailScreen,
  LabsListScreen,
  OverviewScreen,
  PlatformEnrollScreen,
  PlatformGuard,
  PlatformLayout,
  PlatformLoginScreen,
  PlatformTotpScreen,
  ProvisionScreen,
  SettingsScreen,
  SubscriptionDetailScreen,
  SubscriptionsScreen,
  UsersScreen,
} from "./features/platform";
import Hero from "./marketing/Hero";
import TrustStrip from "./marketing/TrustStrip";
import Problem from "./marketing/Problem";
import HowItWorks from "./marketing/HowItWorks";
import Features from "./marketing/Features";
import Security from "./marketing/Security";
import FoundingOffer from "./marketing/FoundingOffer";
import Pricing from "./marketing/Pricing";
import Faq from "./marketing/Faq";
import FinalCta from "./marketing/FinalCta";
import Footer from "./marketing/Footer";

import {
  fetchTenantContext,
  getSubdomainTenant,
  type TenantContextInfo,
} from "./features/auth/tenantContext";

function HomeScreen(): JSX.Element {
  const user = useAuthStore((state) => state.user);

  // The Owner keeps the full operational dashboard. Every other role gets its
  // own screen; an unknown/missing role never falls through to Owner data.
  if (
    !user ||
    !isUserRole(user.role) ||
    !isRoleEnabled(user.role, user.enabled_roles)
  ) {
    return <Navigate to="/login" replace />;
  }

  switch (user.role) {
    case "owner":
      return <OwnerDashboardScreen />;
    case "manager":
      return <ManagerDashboardScreen />;
    case "reception":
      return <ReceptionistDashboardScreen />;
    case "technician":
      return <TechnicianDashboardScreen />;
    case "pathologist":
      return <PathologistDashboardScreen />;
    default:
      return <Navigate to="/login" replace />;
  }
}

export function StaffLoginWrapper(): JSX.Element {
  const navigate = useNavigate();
  const accessToken = useAuthStore((state) => state.accessToken);
  const user = useAuthStore((state) => state.user);
  const [tenantInfo, setTenantInfo] = useState<TenantContextInfo | null>(() =>
    getSubdomainTenant(),
  );

  useEffect(() => {
    let active = true;
    void fetchTenantContext().then((info) => {
      if (active && info) {
        setTenantInfo(info);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <StaffLoginScreen
      tenantName={tenantInfo?.name}
      nodeId={tenantInfo?.nodeId}
      currentUser={accessToken && user ? user : null}
      onContinue={() => navigate(roleHome(user?.role))}
      onLogInAsSomeoneElse={async () => {
        await useAuthStore.getState().logout();
      }}
      onTotpRequired={(email, challengeToken) => {
        const query = new URLSearchParams({ email });
        if (challengeToken) query.set("challenge", challengeToken);
        navigate(`/login/2fa?${query.toString()}`);
      }}
      onTotpEnrollmentRequired={(session) => {
        useAuthStore.getState().setSession(session.access, session.user);
        navigate("/login/enroll");
      }}
      onSuccess={(session) => {
        useAuthStore.getState().setSession(session.access, session.user);
        navigate(roleHome(session.user?.role));
      }}
    />
  );
}

function TwoFactorAuthWrapper(): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const emailParam = queryParams.get("email") || undefined;
  const challengeParam = queryParams.get("challenge") || undefined;
  const [tenantInfo, setTenantInfo] = useState<TenantContextInfo | null>(() =>
    getSubdomainTenant(),
  );

  useEffect(() => {
    let active = true;
    void fetchTenantContext().then((info) => {
      if (active && info) {
        setTenantInfo(info);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <TwoFactorAuthScreen
      email={emailParam}
      challengeToken={challengeParam}
      tenantName={tenantInfo?.name}
      terminalId={tenantInfo?.terminalId}
      onBack={() => navigate("/login")}
      onSuccess={(session) => {
        useAuthStore.getState().setSession(session.access, session.user);
        navigate(roleHome(session.user?.role));
      }}
    />
  );
}

function PatientListWrapper(): JSX.Element {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const canRegister = canAccessPath(user?.role, "/patients/new");
  return (
    <main className="min-h-screen bg-slate-50">
      <PatientListScreen
        onNewPatient={canRegister ? () => navigate("/patients/new") : undefined}
        onSelectPatient={(id) => navigate(`/patients/${id}`)}
      />
    </main>
  );
}

function RegisterPatientWrapper(): JSX.Element {
  const navigate = useNavigate();
  const [branchId, setBranchId] = useState<string | null>(null);
  const [branchError, setBranchError] = useState<string | null>(null);
  const user = useAuthStore((state) => state.user);

  useEffect(() => {
    let active = true;
    settingsService
      .getBranches()
      .then((branches) => {
        if (!active) return;
        // Register into the caller's own branch when they are branch-scoped;
        // otherwise the main testing branch. The API orders by branch code,
        // so branches[0] is "B02" and is NOT the main branch.
        const preferred =
          branches.find((b) => user?.branch_ids?.includes(b.id)) ??
          branches.find((b) => b.code === "HQ1") ??
          branches[0];
        if (preferred) setBranchId(preferred.id);
        else setBranchError("No active branch is available for registration.");
      })
      .catch(() => {
        if (active) setBranchError("Could not load the branch list.");
      });
    return () => {
      active = false;
    };
  }, [user?.branch_ids]);

  return (
    <main className="min-h-screen bg-slate-50 py-6">
      {branchId ? (
        <RegisterPatientScreen
          branchId={branchId}
          onCancel={() => navigate("/patients")}
          onSuccess={() => navigate("/patients")}
        />
      ) : (
        <div className="max-w-2xl mx-auto p-6 text-sm text-slate-600">
          {branchError ?? "Loading branch…"}
        </div>
      )}
    </main>
  );
}

function PatientDetailsWrapper(): JSX.Element {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const user = useAuthStore((state) => state.user);
  const canManage = canAccessPath(user?.role, `/patients/${id}/edit`);
  const canDelete = user?.role === "owner" || user?.role === "manager";
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <PatientDetailsScreen
        patientId={id || ""}
        canManage={canManage}
        canDelete={canDelete}
        onBack={() => navigate("/patients")}
        onEdit={(patientId) => navigate(`/patients/${patientId}/edit`)}
        onViewHistory={(patientId) =>
          navigate(`/patients/${patientId}/history`)
        }
        onNewVisit={() => navigate("/patients")}
      />
    </main>
  );
}

function PatientEditWrapper(): JSX.Element {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <PatientEditScreen
        patientId={id || ""}
        onBack={() => navigate(`/patients/${id}`)}
        onCancel={() => navigate(`/patients/${id}`)}
        onSuccess={() => navigate(`/patients/${id}`)}
      />
    </main>
  );
}

function PatientHistoryWrapper(): JSX.Element {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <PatientHistoryScreen
        patientId={id || ""}
        onBack={() => navigate(`/patients/${id}`)}
      />
    </main>
  );
}

function TestCatalogWrapper(): JSX.Element {
  const navigate = useNavigate();
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <TestCatalogScreen onSwitchToPanels={() => navigate("/catalog/panels")} />
    </main>
  );
}

function TestPanelsWrapper(): JSX.Element {
  const navigate = useNavigate();
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <TestPanelsScreen onSwitchToTests={() => navigate("/catalog/tests")} />
    </main>
  );
}

function InvoicesListWrapper(): JSX.Element {
  const navigate = useNavigate();
  return (
    <main className="min-h-screen bg-slate-50">
      <InvoicesListScreen
        onNewInvoice={() => navigate("/invoices/new")}
        onSelectInvoice={(id) => navigate(`/invoices/${id}`)}
      />
    </main>
  );
}

function NewInvoiceWrapper(): JSX.Element {
  const navigate = useNavigate();
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <NewInvoiceScreen
        onCancel={() => navigate("/invoices")}
        onSuccess={(inv) => navigate(`/invoices/${inv.id}`)}
        onRegisterPatient={() => navigate("/patients/new")}
      />
    </main>
  );
}

function InvoiceDetailWrapper(): JSX.Element {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <InvoiceDetailScreen
        invoiceId={id || ""}
        onBack={() => navigate("/invoices")}
        onProceedToSamples={(invoice) =>
          navigate(`/samples/collect/step1?invoice_id=${invoice.id}`)
        }
      />
    </main>
  );
}

function SamplesListWrapper(): JSX.Element {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const canCollect = canAccessPath(user?.role, "/samples/collect/step1");
  return (
    <main className="min-h-screen bg-slate-50">
      <SampleAccessioningListScreen
        onSelectSample={(id) => navigate(`/samples/${id}`)}
        onCollectNew={
          canCollect ? () => navigate("/samples/collect/step1") : undefined
        }
        onPrintLabels={(ids) => {
          if (ids[0]) navigate(`/samples/${ids[0]}/label`);
        }}
      />
    </main>
  );
}

function CollectSampleStep1Wrapper(): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const invoiceIdParam = queryParams.get("invoice_id") || undefined;

  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <CollectSampleStep1Screen
        preselectedInvoiceId={invoiceIdParam}
        onCancel={() => navigate("/samples")}
        onContinue={(draft) => {
          navigate("/samples/collect/step2", { state: { draft } });
        }}
      />
    </main>
  );
}

function CollectSampleStep2Wrapper(): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const stateDraft = (
    location.state as { draft?: SampleCollectionDraft } | undefined
  )?.draft;

  if (!stateDraft) {
    return <Navigate to="/samples/collect/step1" replace />;
  }

  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <CollectSampleStep2Screen
        draft={stateDraft}
        onBack={() => navigate("/samples/collect/step1")}
        onConfirmed={(res) => {
          navigate(`/samples/${res.id}/label`);
        }}
      />
    </main>
  );
}

function SampleDetailWrapper(): JSX.Element {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();

  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <SampleDetailScreen
        sampleId={id || ""}
        onBack={() => navigate("/samples")}
        onPrintLabel={(sampleId) => navigate(`/samples/${sampleId}/label`)}
        onViewPatient={(patientId) => navigate(`/patients/${patientId}`)}
      />
    </main>
  );
}

function SampleLabelWrapper(): JSX.Element {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();

  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <SampleLabelScreen
        sampleId={id || ""}
        onBack={() => navigate(`/samples/${id}`)}
      />
    </main>
  );
}

function WorklistWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <WorklistScreen />
    </main>
  );
}

function ResultEntryWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <ResultEntryScreen />
    </main>
  );
}

function ApprovalsQueueWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <ApprovalsQueueScreen />
    </main>
  );
}

function ResultDetailWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <ResultDetailScreen />
    </main>
  );
}

function AmendResultWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <AmendResultScreen />
    </main>
  );
}

function ReportsListWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <ReportsListScreen />
    </main>
  );
}

function ReportDetailWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <ReportDetailScreen />
    </main>
  );
}

function PatientReportAccessWrapper(): JSX.Element {
  return <PatientReportAccessScreen />;
}

function LinkExpiredWrapper(): JSX.Element {
  return <LinkExpiredScreen />;
}

function ExceptionsWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <ExceptionsScreen />
    </main>
  );
}

function BranchesWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <BranchesScreen />
    </main>
  );
}

function TenantSettingsWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <TenantSettingsScreen />
    </main>
  );
}

function AccountSecurityWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <AccountSecurityScreen />
    </main>
  );
}

function DataExportWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <DataExportScreen />
    </main>
  );
}

function PartnersListWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <PartnersListScreen />
    </main>
  );
}

function PartnerDetailWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <PartnerDetailScreen />
    </main>
  );
}

function RulesWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <RulesScreen />
    </main>
  );
}

function LedgerWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <LedgerScreen />
    </main>
  );
}

function PartnerDashboardWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <PartnerDashboardScreen />
    </main>
  );
}

function SettlementsWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <SettlementsScreen />
    </main>
  );
}

function SettlementDetailWrapper(): JSX.Element {
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <SettlementDetailScreen />
    </main>
  );
}

/**
 * Platform (Super Admin) shell: guard + sidebar around a Phase 1 screen.
 * Host separation is enforced by Caddy; this is the client-side UX guard.
 */
function PlatformShell({ children }: { children: JSX.Element }): JSX.Element {
  return (
    <PlatformGuard>
      <PlatformLayout>{children}</PlatformLayout>
    </PlatformGuard>
  );
}

/**
 * Keeps <html lang/dir> correct as the user moves between the tenant SPA and
 * the apex Platform console. The platform console is English-only forever and
 * must never inherit a tenant's RTL preference.
 */
function DirectionSync(): null {
  const location = useLocation();
  useEffect(() => {
    applyDocumentLanguage(
      isPlatformRoute(location.pathname) ? "en" : i18n.language,
    );
  }, [location.pathname]);
  return null;
}

function App(): JSX.Element {
  // Boot gate: the access token is memory-only, so a reload must silently
  // rebuild the session from the httpOnly refresh cookie *before* any
  // protected route (and its first API call) renders.
  const [bootstrapped, setBootstrapped] = useState(false);

  useEffect(() => {
    let active = true;
    const finish = () => {
      if (active) setBootstrapped(true);
    };

    // The apex platform console has its own refresh cookie and session family;
    // restoring the staff session there only produces a spurious 401.
    const isPlatformRoute = window.location.pathname.startsWith("/platform");

    if (useAuthStore.getState().accessToken) {
      finish();
      return () => {
        active = false;
      };
    }

    refreshSession(isPlatformRoute ? "platform" : "staff")
      .then((token) => {
        if (!active) return;
        if (token) return;
        const path = window.location.pathname;
        const isPublicRoute =
          path.startsWith("/login") ||
          path.startsWith("/platform") ||
          path.startsWith("/report-access") ||
          path.startsWith("/link-expired");
        if (!isPublicRoute) {
          window.location.replace("/login?reason=session_expired");
          return;
        }
        finish();
      })
      .catch(() => finish())
      .finally(finish);

    return () => {
      active = false;
    };
  }, []);

  if (!bootstrapped) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 text-sm text-slate-500">
        Restoring session…
      </div>
    );
  }

  return (
    <BrowserRouter>
      <DirectionSync />
      <Routes>
        {/* Unauthenticated Auth & Public Access Routes */}
        <Route path="/login" element={<StaffLoginWrapper />} />
        <Route path="/login/2fa" element={<TwoFactorAuthWrapper />} />
        <Route path="/login/enroll" element={<TenantEnrollScreen />} />
        <Route
          path="/report-access/:token"
          element={<PatientReportAccessWrapper />}
        />
        <Route path="/link-expired" element={<LinkExpiredWrapper />} />

        {/* Authenticated Tenant Shell */}
        <Route element={<TenantLayout />}>
          <Route path="/" element={<HomeScreen />} />
          <Route
            path="/approvals"
            element={<Navigate to="/results/approvals" replace />}
          />
          <Route
            path="/catalog"
            element={<Navigate to="/catalog/tests" replace />}
          />
          <Route
            path="/settings"
            element={<Navigate to="/settings/tenant" replace />}
          />
          <Route path="/patients" element={<PatientListWrapper />} />
          <Route path="/patients/new" element={<RegisterPatientWrapper />} />
          <Route path="/patients/:id" element={<PatientDetailsWrapper />} />
          <Route path="/patients/:id/edit" element={<PatientEditWrapper />} />
          <Route
            path="/patients/:id/history"
            element={<PatientHistoryWrapper />}
          />
          <Route path="/catalog/tests" element={<TestCatalogWrapper />} />
          <Route path="/catalog/panels" element={<TestPanelsWrapper />} />
          <Route path="/settings/tests" element={<TestCatalogWrapper />} />
          <Route path="/settings/panels" element={<TestPanelsWrapper />} />
          <Route path="/invoices" element={<InvoicesListWrapper />} />
          <Route path="/invoices/new" element={<NewInvoiceWrapper />} />
          <Route path="/invoices/:id" element={<InvoiceDetailWrapper />} />

          {/* Samples Management Suite (Screens 16–20) */}
          <Route path="/samples" element={<SamplesListWrapper />} />
          <Route
            path="/samples/collect/step1"
            element={<CollectSampleStep1Wrapper />}
          />
          <Route
            path="/samples/collect/step2"
            element={<CollectSampleStep2Wrapper />}
          />
          <Route
            path="/samples/new"
            element={<Navigate to="/samples/collect/step1" replace />}
          />
          <Route path="/samples/:id" element={<SampleDetailWrapper />} />
          <Route path="/samples/:id/label" element={<SampleLabelWrapper />} />

          {/* Results Management Suite (Screens 21–25) */}
          <Route path="/worklist" element={<WorklistWrapper />} />
          <Route
            path="/results"
            element={<Navigate to="/worklist" replace />}
          />
          <Route
            path="/results/entry/:sampleId"
            element={<ResultEntryWrapper />}
          />
          <Route
            path="/results/approvals"
            element={<ApprovalsQueueWrapper />}
          />
          <Route path="/results/:id/amend" element={<AmendResultWrapper />} />
          <Route path="/results/:id" element={<ResultDetailWrapper />} />

          {/* Reports & Exceptions Suite (Screens 26–30) */}
          <Route path="/reports" element={<ReportsListWrapper />} />
          <Route path="/reports/:id" element={<ReportDetailWrapper />} />
          <Route path="/exceptions" element={<ExceptionsWrapper />} />

          {/* Settings & Referral Partners Suite (Screens 33–37) */}
          <Route path="/settings/branches" element={<BranchesWrapper />} />
          <Route path="/settings/tenant" element={<TenantSettingsWrapper />} />
          <Route
            path="/settings/account"
            element={<AccountSecurityWrapper />}
          />
          <Route path="/settings/exports" element={<DataExportWrapper />} />
          <Route path="/settings/staff" element={<StaffScreen />} />
          <Route path="/partners" element={<PartnersListWrapper />} />
          <Route path="/partners/ledger" element={<LedgerWrapper />} />
          <Route path="/partners/:id/rules" element={<RulesWrapper />} />
          <Route
            path="/partners/:id/dashboard"
            element={<PartnerDashboardWrapper />}
          />
          <Route path="/partners/:id" element={<PartnerDetailWrapper />} />

          {/* Settlements Suite (Screens 41–42) */}
          <Route path="/settlements" element={<SettlementsWrapper />} />
          <Route
            path="/settlements/:id"
            element={<SettlementDetailWrapper />}
          />
        </Route>

        {/* Platform Master Dashboard — Phase 1 (Command & Tenants) */}
        <Route
          path="/platform"
          element={<Navigate to="/platform/overview" replace />}
        />
        <Route path="/platform/login" element={<PlatformLoginScreen />} />
        <Route path="/platform/login/2fa" element={<PlatformTotpScreen />} />
        <Route
          path="/platform/enroll"
          element={
            <PlatformGuard>
              <PlatformEnrollScreen />
            </PlatformGuard>
          }
        />
        <Route
          path="/platform/overview"
          element={
            <PlatformShell>
              <OverviewScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/tenants"
          element={
            <PlatformShell>
              <LabsListScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/tenants/new"
          element={
            <PlatformShell>
              <ProvisionScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/tenants/:id"
          element={
            <PlatformShell>
              <LabDetailScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/subscriptions"
          element={
            <PlatformShell>
              <SubscriptionsScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/subscriptions/:id"
          element={
            <PlatformShell>
              <SubscriptionDetailScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/access"
          element={
            <PlatformShell>
              <AccessControlScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/access/:tenantId"
          element={
            <PlatformShell>
              <AccessControlScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/users"
          element={
            <PlatformShell>
              <UsersScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/demo-requests"
          element={
            <PlatformShell>
              <DemoRequestsScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/demo-requests/:id"
          element={
            <PlatformShell>
              <DemoRequestDetailScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/health"
          element={
            <PlatformShell>
              <HealthScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/audit"
          element={
            <PlatformShell>
              <AuditLogScreen />
            </PlatformShell>
          }
        />
        <Route
          path="/platform/settings"
          element={
            <PlatformShell>
              <SettingsScreen />
            </PlatformShell>
          }
        />

        <Route path="/screens" element={<ScreenCatalogViewer />} />
        <Route path="/screens/:screenId" element={<ScreenCatalogViewer />} />
        {/* TEMPORARY: Hero + TrustStrip + Problem + HowItWorks + Features + Security + FoundingOffer + Pricing + Faq + FinalCta + Footer preview route — will be removed when full marketing page is built */}
        <Route
          path="/hero-preview"
          element={
            <>
              <Hero />
              <TrustStrip />
              <Problem />
              <HowItWorks />
              <Features />
              <Security />
              <FoundingOffer />
              <Pricing />
              <Faq />
              <FinalCta />
              <Footer />
            </>
          }
        />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
