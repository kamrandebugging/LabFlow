import { useState } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useNavigate,
  useLocation,
  Link,
} from "react-router-dom";
import { StaffLoginScreen } from "./features/auth/StaffLoginScreen";
import { TwoFactorAuthScreen } from "./features/auth/TwoFactorAuthScreen";
import { ScreenCatalogViewer } from "./features/screens/ScreenCatalogViewer";
import { Shield, Smartphone, CheckCircle, LayoutGrid } from "lucide-react";

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
            Signed in as <span className="font-semibold text-slate-800">{successSession.email}</span>
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
        <Route path="/screens" element={<ScreenCatalogViewer />} />
        <Route path="/screens/:screenId" element={<ScreenCatalogViewer />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
      <ScreenSwitcherBanner />
    </BrowserRouter>
  );
}

export default App;