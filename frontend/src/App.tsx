import { useState } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useNavigate,
  useLocation,
  useParams,
  Link,
} from "react-router-dom";
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
import {
  Shield,
  Smartphone,
  CheckCircle,
  LayoutGrid,
  Users,
  UserPlus,
  FlaskConical,
  Layers,
  Receipt,
} from "lucide-react";

function StaffLoginWrapper(): JSX.Element {
  const navigate = useNavigate();
  const [successSession, setSuccessSession] = useState<{
    token: string;
    email: string;
  } | null>(null);

  if (successSession) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
        <div className="bg-white rounded-xl shadow-md border border-slate-100 p-8 max-w-md w-full text-center">
          <div className="w-12 h-12 bg-teal-50 text-teal-600 rounded-full flex items-center justify-center mx-auto mb-4">
            <CheckCircle className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-bold text-slate-900 mb-2">
            Authentication Successful
          </h2>
          <p className="text-sm text-slate-600 mb-4">
            Signed in as{" "}
            <span className="font-semibold text-slate-800">
              {successSession.email}
            </span>
          </p>
          <div className="p-3 bg-slate-50 rounded text-xs font-mono text-slate-600 text-left overflow-x-auto mb-6">
            In-memory access token stored securely (Doc 07 §5.2).
          </div>
          <div className="flex flex-col gap-2">
            <Link
              to="/screens"
              className="w-full py-2 px-4 rounded-lg bg-slate-900 text-white font-medium hover:bg-slate-800 transition flex items-center justify-center gap-2 text-sm"
            >
              <LayoutGrid className="w-4 h-4" />
              Open All 43 Screens Master Catalog
            </Link>
            <button
              type="button"
              onClick={() => setSuccessSession(null)}
              className="w-full py-2 px-4 rounded-lg bg-teal-700 text-white font-medium hover:bg-teal-800 transition text-sm"
            >
              Sign out / Return to Login
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <StaffLoginScreen
      onTotpRequired={(email) => {
        navigate(`/login/2fa?email=${encodeURIComponent(email)}`);
      }}
      onSuccess={(session) => {
        setSuccessSession({
          token: session.access,
          email: session.user.email || session.user.name,
        });
      }}
    />
  );
}

function TwoFactorAuthWrapper(): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const emailParam = queryParams.get("email") || "ali.raza@citylab.pk";
  const [verifiedSession, setVerifiedSession] = useState<boolean>(false);

  if (verifiedSession) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
        <div className="bg-white rounded-xl shadow-md border border-slate-100 p-8 max-w-md w-full text-center">
          <div className="w-12 h-12 bg-teal-50 text-teal-600 rounded-full flex items-center justify-center mx-auto mb-4">
            <CheckCircle className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-bold text-slate-900 mb-2">
            2FA Verified Successfully
          </h2>
          <p className="text-sm text-slate-600 mb-6">
            Clinical session verified for{" "}
            <span className="font-semibold text-slate-800">{emailParam}</span>
          </p>
          <div className="flex flex-col gap-2">
            <Link
              to="/screens"
              className="w-full py-2 px-4 rounded-lg bg-slate-900 text-white font-medium hover:bg-slate-800 transition flex items-center justify-center gap-2 text-sm"
            >
              <LayoutGrid className="w-4 h-4" />
              Open All 43 Screens Master Catalog
            </Link>
            <button
              type="button"
              onClick={() => {
                setVerifiedSession(false);
                navigate("/login");
              }}
              className="w-full py-2 px-4 rounded-lg bg-teal-700 text-white font-medium hover:bg-teal-800 transition text-sm"
            >
              Return to Staff Login
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <TwoFactorAuthScreen
      email={emailParam}
      onBack={() => navigate("/login")}
      onSuccess={() => setVerifiedSession(true)}
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

function ScreenSwitcherBanner(): JSX.Element | null {
  const location = useLocation();
  const currentPath = location.pathname;

  // If already on /screens, keep it compact or hide to avoid obstruction
  if (currentPath.startsWith("/screens")) {
    return null;
  }

  return (
    <nav
      aria-label="Screen preview switcher"
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-900/95 text-white backdrop-blur-md px-4 py-2 rounded-full shadow-2xl flex items-center gap-3 text-xs border border-slate-700"
    >
      <span className="font-semibold text-teal-300 flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        LabFlow Preview
      </span>
      <span className="text-slate-600">|</span>
      <Link
        to="/login"
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-colors ${
          currentPath === "/login" || currentPath === "/"
            ? "bg-teal-600 text-white font-medium"
            : "text-slate-300 hover:text-white"
        }`}
      >
        <Shield className="w-3.5 h-3.5" />
        01: Login (React)
      </Link>
      <Link
        to="/login/2fa"
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-colors ${
          currentPath === "/login/2fa"
            ? "bg-teal-600 text-white font-medium"
            : "text-slate-300 hover:text-white"
        }`}
      >
        <Smartphone className="w-3.5 h-3.5" />
        02: 2FA (React)
      </Link>
      <span className="text-slate-600">|</span>
      <Link
        to="/patients"
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-colors ${
          currentPath === "/patients"
            ? "bg-teal-600 text-white font-medium"
            : "text-slate-300 hover:text-white"
        }`}
      >
        <Users className="w-3.5 h-3.5" />
        08: Patients
      </Link>
      <Link
        to="/patients/new"
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-colors ${
          currentPath === "/patients/new"
            ? "bg-teal-600 text-white font-medium"
            : "text-slate-300 hover:text-white"
        }`}
      >
        <UserPlus className="w-3.5 h-3.5" />
        09: Register
      </Link>
      <span className="text-slate-600">|</span>
      <Link
        to="/catalog/tests"
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-colors ${
          currentPath === "/catalog/tests" || currentPath === "/settings/tests"
            ? "bg-teal-600 text-white font-medium"
            : "text-slate-300 hover:text-white"
        }`}
      >
        <FlaskConical className="w-3.5 h-3.5" />
        31: Tests
      </Link>
      <Link
        to="/catalog/panels"
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-colors ${
          currentPath === "/catalog/panels" ||
          currentPath === "/settings/panels"
            ? "bg-indigo-600 text-white font-medium"
            : "text-slate-300 hover:text-white"
        }`}
      >
        <Layers className="w-3.5 h-3.5" />
        32: Panels
      </Link>
      <span className="text-slate-600">|</span>
      <Link
        to="/invoices"
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-colors ${
          currentPath.startsWith("/invoices")
            ? "bg-teal-600 text-white font-medium"
            : "text-slate-300 hover:text-white"
        }`}
      >
        <Receipt className="w-3.5 h-3.5" />
        13: Invoices
      </Link>
      <span className="text-slate-600">|</span>
      <Link
        to="/screens"
        className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-700 hover:bg-emerald-600 text-white font-semibold shadow-sm transition-colors"
      >
        <LayoutGrid className="w-3.5 h-3.5" />
        All 43 Screens Catalog
      </Link>
    </nav>
  );
}

function App(): JSX.Element {
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
      <ScreenSwitcherBanner />
    </BrowserRouter>
  );
}

export default App;
