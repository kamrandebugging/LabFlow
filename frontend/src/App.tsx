import { useEffect } from "react";
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
import { StaffLoginScreen } from "./features/auth/StaffLoginScreen";
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
import { ScreenCatalogViewer } from "./features/screens/ScreenCatalogViewer";
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

function StaffLoginWrapper(): JSX.Element {
  const navigate = useNavigate();

  return (
    <StaffLoginScreen
      onTotpRequired={(email) => {
        navigate(`/login/2fa?email=${encodeURIComponent(email)}`);
      }}
      onSuccess={(session) => {
        useAuthStore.getState().setSession(session.access, session.user);
        navigate("/invoices");
      }}
    />
  );
}

function TwoFactorAuthWrapper(): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const emailParam = queryParams.get("email") || "owner@labflow.app";

  return (
    <TwoFactorAuthScreen
      email={emailParam}
      onBack={() => navigate("/login")}
      onSuccess={(session) => {
        useAuthStore.getState().setSession(session.access, session.user);
        navigate("/invoices");
      }}
    />
  );
}

function PatientListWrapper(): JSX.Element {
  const navigate = useNavigate();
  return (
    <main className="min-h-screen bg-slate-50">
      <PatientListScreen
        onNewPatient={() => navigate("/patients/new")}
        onSelectPatient={(id) => navigate(`/patients/${id}`)}
      />
    </main>
  );
}

function RegisterPatientWrapper(): JSX.Element {
  const navigate = useNavigate();
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <RegisterPatientScreen
        onCancel={() => navigate("/patients")}
        onSuccess={() => navigate("/patients")}
      />
    </main>
  );
}

function PatientDetailsWrapper(): JSX.Element {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <PatientDetailsScreen
        patientId={id || ""}
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
        onProceedToSamples={() => navigate("/samples")}
      />
    </main>
  );
}

function SamplesListWrapper(): JSX.Element {
  const navigate = useNavigate();
  return (
    <main className="min-h-screen bg-slate-50">
      <SampleAccessioningListScreen
        onSelectSample={(id) => navigate(`/samples/${id}`)}
        onCollectNew={() => navigate("/samples/collect/step1")}
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

  // Fallback demo draft if navigated directly
  const fallbackDraft: SampleCollectionDraft = {
    invoice_id: "00000000-0000-0000-0000-000000000011",
    patient_id: "00000000-0000-0000-0000-000000000001",
    patient_name: "Muhammad Imran",
    patient_mrn: "MRN-2026-00417",
    branch_id: "96f2a138-334e-490c-9dd3-805dd45022f0",
    branch_name: "Main Reference Lab (Lahore)",
    selected_item_ids: ["item-01", "item-02"],
    test_labels: ["Complete Blood Count (CBC)", "Glycated Hemoglobin (HbA1c)"],
    tubes_required: [
      {
        type: "Lavender top (EDTA)",
        color: "#7e22ce",
        specimen: "Whole Blood",
        count: 1,
      },
      {
        type: "Grey top (Fluoride)",
        color: "#64748b",
        specimen: "Fluoride Plasma",
        count: 1,
      },
    ],
    collected_at: new Date().toISOString(),
    collected_by: "phleb.amna@labflow.pk",
    notes: "Specimen drawn per standard phlebotomy protocol.",
  };

  return (
    <main className="min-h-screen bg-slate-50 py-6">
      <CollectSampleStep2Screen
        draft={stateDraft || fallbackDraft}
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

function App(): JSX.Element {
  useEffect(() => {
    // Attempt silent session restore via httpOnly refresh cookie on application mount
    fetch("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.access && data?.user) {
          useAuthStore.getState().setSession(data.access, data.user);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<StaffLoginWrapper />} />
        <Route path="/login/2fa" element={<TwoFactorAuthWrapper />} />
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
          path="/results/entry/:sampleId"
          element={<ResultEntryWrapper />}
        />
        <Route path="/results/approvals" element={<ApprovalsQueueWrapper />} />
        <Route path="/results/:id/amend" element={<AmendResultWrapper />} />
        <Route path="/results/:id" element={<ResultDetailWrapper />} />

        {/* Reports & Exceptions Suite (Screens 26–30) */}
        <Route path="/reports" element={<ReportsListWrapper />} />
        <Route path="/reports/:id" element={<ReportDetailWrapper />} />
        <Route
          path="/report-access/:token"
          element={<PatientReportAccessWrapper />}
        />
        <Route path="/link-expired" element={<LinkExpiredWrapper />} />
        <Route path="/exceptions" element={<ExceptionsWrapper />} />

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
