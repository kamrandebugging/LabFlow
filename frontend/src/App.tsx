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
import { Shield, Smartphone, CheckCircle } from "lucide-react";

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
          <button
            type="button"
            onClick={() => setSuccessSession(null)}
            className="w-full py-2 px-4 rounded-lg bg-teal-700 text-white font-medium hover:bg-teal-800 transition"
          >
            Sign out / Return to Login
          </button>
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
          <button
            type="button"
            onClick={() => {
              setVerifiedSession(false);
              navigate("/login");
            }}
            className="w-full py-2 px-4 rounded-lg bg-teal-700 text-white font-medium hover:bg-teal-800 transition"
          >
            Return to Staff Login
          </button>
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

function ScreenSwitcherBanner(): JSX.Element {
  const location = useLocation();
  const currentPath = location.pathname;

  return (
    <nav
      aria-label="Screen preview switcher"
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-900/90 text-white backdrop-blur-md px-4 py-2 rounded-full shadow-xl flex items-center gap-3 text-xs border border-slate-700"
    >
      <span className="font-semibold text-teal-300 flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        LabFlow Preview
      </span>
      <span className="text-slate-500">|</span>
      <Link
        to="/login"
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-colors ${
          currentPath === "/login" || currentPath === "/"
            ? "bg-teal-600 text-white font-medium"
            : "text-slate-300 hover:text-white"
        }`}
      >
        <Shield className="w-3.5 h-3.5" />
        01: Staff Login
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
        02: 2FA TOTP
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
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
      <ScreenSwitcherBanner />
    </BrowserRouter>
  );
}

export default App;
