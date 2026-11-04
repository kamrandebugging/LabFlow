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
import { ScreenCatalogViewer } from "./features/screens/ScreenCatalogViewer";

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
        <Route path="/screens" element={<ScreenCatalogViewer />} />
        <Route path="/screens/:screenId" element={<ScreenCatalogViewer />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
