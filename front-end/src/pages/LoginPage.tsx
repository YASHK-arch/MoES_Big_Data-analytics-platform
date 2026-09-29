import React, { useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import {
  ShieldCheck,
  CheckSquare,
  ArrowRight,
  ArrowLeft,
  Building2,
  Lock,
  Mail,
  AlertCircle,
  Loader2,
  UserCheck,
  Key,
  UserPlus,
  Eye,
  EyeOff,
} from "lucide-react";
import { Navbar } from "@/components/layout/Navbar";
import { useAuth } from "@/context/AuthContext";

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isLoading, isAuthenticated, user } = useAuth();

  const [activeTab, setActiveTab] = useState<"OPERATOR" | "CITIZEN">(
    "OPERATOR",
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const from = (location.state as { from?: { pathname?: string } })?.from
    ?.pathname;

  React.useEffect(() => {
    if (isAuthenticated) {
      if (from) {
        navigate(from, { replace: true });
      } else {
        const userRole = (user?.role || "CITIZEN").toUpperCase();
        const destination =
          userRole === "ADMIN"
            ? "/dashboard"
            : userRole === "OPERATOR"
              ? "/admin/queue"
              : "/citizen-dashboard";
        navigate(destination, { replace: true });
      }
    }
  }, [isAuthenticated, user, navigate, from]);

  const handleAutofillOperator = () => {
    setEmail("operator@weather-platform.gov.in");
    setPassword("EmergencyOps2026!");
    setErrorMsg(null);
  };

  const handleAutofillAdmin = () => {
    setEmail("admin@weather-platform.gov.in");
    setPassword("EmergencyAdmin2026!");
    setErrorMsg(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (!email.trim() || !password) {
      setErrorMsg("Please enter both your email/username and password.");
      return;
    }

    try {
      const profile = await login(email.trim(), password);
      const userRole = (profile.role || "").toUpperCase();
      if (from) {
        navigate(from, { replace: true });
      } else {
        const destination =
          userRole === "ADMIN"
            ? "/dashboard"
            : userRole === "OPERATOR"
              ? "/admin/queue"
              : "/citizen-dashboard";
        navigate(destination, { replace: true });
      }
    } catch (err: unknown) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Invalid credentials. Access denied.",
      );
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans antialiased">
      <Navbar />

      <main className="flex-1 flex items-center justify-center p-4 sm:p-6 md:p-8">
        <div className="w-full max-w-xl space-y-6">
          {/* Role Selection Tabs */}
          <div className="flex rounded-2xl bg-slate-200/80 p-1.5 border border-slate-300/60 shadow-2xs">
            <button
              type="button"
              onClick={() => {
                setActiveTab("OPERATOR");
                setErrorMsg(null);
              }}
              className={`flex-1 flex items-center justify-center space-x-2 py-3 px-4 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                activeTab === "OPERATOR"
                  ? "bg-white text-blue-900 shadow-sm border border-slate-200"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <ShieldCheck
                className={`h-4 w-4 ${activeTab === "OPERATOR" ? "text-blue-600" : "text-slate-400"}`}
              />
              <span>Control Room Operator (Admin)</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setActiveTab("CITIZEN");
                setErrorMsg(null);
              }}
              className={`flex-1 flex items-center justify-center space-x-2 py-3 px-4 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                activeTab === "CITIZEN"
                  ? "bg-white text-emerald-900 shadow-sm border border-slate-200"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <UserCheck
                className={`h-4 w-4 ${activeTab === "CITIZEN" ? "text-emerald-600" : "text-slate-400"}`}
              />
              <span>Public Citizen Login</span>
            </button>
          </div>

          {/* Main Container Card */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-xs space-y-6">
            {activeTab === "OPERATOR" ? (
              <>
                {/* Operator Header */}
                <div className="flex items-start space-x-3.5">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600 border border-blue-100 shrink-0">
                    <ShieldCheck className="h-6 w-6" aria-hidden="true" />
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-bold uppercase tracking-wider text-blue-600 bg-blue-50 border border-blue-200/80 px-2.5 py-0.5 rounded-full">
                        Admin / Operator Portal
                      </span>
                    </div>
                    <h1 className="text-xl sm:text-2xl font-black text-slate-900 mt-1">
                      Emergency Operations Login
                    </h1>
                    <p className="text-xs sm:text-sm text-slate-500 font-medium mt-0.5">
                      National DEOC triage queues and disaster command center
                    </p>
                  </div>
                </div>

                {/* Quick Autofill Buttons for Evaluators */}
                <div className="rounded-xl border border-blue-100 bg-blue-50/50 p-3.5 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-blue-900 flex items-center space-x-1.5">
                      <Key className="h-3.5 w-3.5 text-blue-600" />
                      <span>Evaluator Demo Accounts</span>
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={handleAutofillOperator}
                      className="inline-flex items-center space-x-1 px-2.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-[11px] font-bold text-white transition-colors cursor-pointer"
                    >
                      <CheckSquare className="h-3 w-3" />
                      <span>Autofill DEOC Operator</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleAutofillAdmin}
                      className="inline-flex items-center space-x-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-900 text-[11px] font-bold text-white transition-colors cursor-pointer"
                    >
                      <CheckSquare className="h-3 w-3" />
                      <span>Autofill Admin HQ</span>
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <>
                {/* Citizen Header */}
                <div className="flex items-start space-x-3.5">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600 border border-emerald-100 shrink-0">
                    <UserCheck className="h-6 w-6" aria-hidden="true" />
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 border border-emerald-200/80 px-2.5 py-0.5 rounded-full">
                        Citizen Portal
                      </span>
                    </div>
                    <h1 className="text-xl sm:text-2xl font-black text-slate-900 mt-1">
                      Citizen Account Sign In
                    </h1>
                    <p className="text-xs sm:text-sm text-slate-500 font-medium mt-0.5">
                      Access saved home location, proximity disaster alerts, and
                      report history
                    </p>
                  </div>
                </div>
              </>
            )}

            {/* Error Banner */}
            {errorMsg && (
              <div
                role="alert"
                className="flex items-start space-x-2.5 rounded-xl border border-red-200 bg-red-50/90 p-3.5 text-xs text-red-700 animate-in fade-in"
              >
                <AlertCircle
                  className="h-4 w-4 shrink-0 text-red-600 mt-0.5"
                  aria-hidden="true"
                />
                <span className="font-medium leading-relaxed">{errorMsg}</span>
              </div>
            )}

            {/* Unified Login Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-slate-700">
                  {activeTab === "OPERATOR"
                    ? "Operator Email / Username"
                    : "Citizen Email Address"}
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                    <Mail className="h-4 w-4" aria-hidden="true" />
                  </div>
                  <input
                    type="text"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={
                      activeTab === "OPERATOR"
                        ? "operator@weather-platform.gov.in"
                        : "citizen@example.com"
                    }
                    className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-4 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none transition-all"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-slate-700">
                  Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                    <Lock className="h-4 w-4" aria-hidden="true" />
                  </div>
                  <input
                    type={showPassword ? "text" : "password"}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-10 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={
                      showPassword ? "Hide password" : "Show password"
                    }
                    className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 focus:outline-none transition-colors cursor-pointer"
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" aria-hidden="true" />
                    ) : (
                      <Eye className="h-4 w-4" aria-hidden="true" />
                    )}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className={`w-full flex items-center justify-center space-x-2 rounded-xl py-3 px-4 text-xs sm:text-sm font-bold text-white shadow-sm transition-all focus:ring-2 focus:outline-none disabled:opacity-50 cursor-pointer ${
                  activeTab === "OPERATOR"
                    ? "bg-blue-600 hover:bg-blue-700 focus:ring-blue-500/30"
                    : "bg-emerald-600 hover:bg-emerald-700 focus:ring-emerald-500/30"
                }`}
              >
                {isLoading ? (
                  <>
                    <Loader2
                      className="h-4 w-4 animate-spin"
                      aria-hidden="true"
                    />
                    <span>Authenticating...</span>
                  </>
                ) : (
                  <>
                    <span>
                      {activeTab === "OPERATOR"
                        ? "Sign In to Operations Command"
                        : "Sign In as Citizen"}
                    </span>
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </>
                )}
              </button>
            </form>

            {/* Citizen Signup Call-to-Action */}
            {activeTab === "CITIZEN" && (
              <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 text-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-800 flex items-center space-x-1.5">
                    <UserPlus className="h-4 w-4 text-emerald-600" />
                    <span>New Citizen User?</span>
                  </span>
                  <Link
                    to="/signup"
                    className="font-bold text-emerald-700 hover:text-emerald-800 transition-colors"
                  >
                    Create Free Account &rarr;
                  </Link>
                </div>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Register in seconds to receive automatic location-aware flood
                  and storm alerts.
                </p>
              </div>
            )}

            {activeTab === "OPERATOR" && (
              <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 text-xs text-slate-600 space-y-1.5">
                <div className="flex items-center space-x-2 text-slate-900 font-bold">
                  <Building2
                    className="h-4 w-4 text-slate-600"
                    aria-hidden="true"
                  />
                  <span>Restricted Operator Access</span>
                </div>
                <p className="leading-relaxed text-[11px] text-slate-500">
                  Emergency operations accounts are strictly governed.
                  Role-based session tokens are audited in accordance with
                  disaster management protocol.
                </p>
              </div>
            )}

            {/* Back link */}
            <div className="pt-2 border-t border-slate-100 flex justify-center">
              <button
                type="button"
                onClick={() => navigate("/welcome")}
                className="inline-flex items-center space-x-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors cursor-pointer"
              >
                <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Return to Public Home</span>
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
