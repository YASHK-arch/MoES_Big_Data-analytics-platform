import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/i18n";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { LocationProvider } from "@/context/LocationContext";
import { realtimeService } from "@/services/realtimeService";

// O5: Route-level lazy loading — each page becomes a separate async chunk.
// The tiny spinner is shown while the chunk loads (typically < 100ms on LAN).
const HomePage = lazy(() =>
  import("@/pages/HomePage").then((m) => ({ default: m.HomePage }))
);
const DashboardPage = lazy(() =>
  import("@/pages/DashboardPage").then((m) => ({ default: m.DashboardPage }))
);
const LiveMapPage = lazy(() =>
  import("@/pages/LiveMapPage").then((m) => ({ default: m.LiveMapPage }))
);
const CitizenReportPage = lazy(() =>
  import("@/pages/CitizenReportPage").then((m) => ({
    default: m.CitizenReportPage,
  }))
);
const TrackReportPage = lazy(() =>
  import("@/pages/TrackReportPage").then((m) => ({
    default: m.TrackReportPage,
  }))
);
const IncidentListPage = lazy(() =>
  import("@/pages/IncidentListPage").then((m) => ({
    default: m.IncidentListPage,
  }))
);
const IncidentDetailPage = lazy(() =>
  import("@/pages/IncidentDetailPage").then((m) => ({
    default: m.IncidentDetailPage,
  }))
);
const CitizenDashboardPage = lazy(() =>
  import("@/pages/CitizenDashboardPage").then((m) => ({
    default: m.CitizenDashboardPage,
  }))
);
const NationalMapPage = lazy(() =>
  import("@/pages/NationalMapPage").then((m) => ({
    default: m.NationalMapPage,
  }))
);
const AdminVerificationQueuePage = lazy(() =>
  import("@/pages/AdminVerificationQueuePage").then((m) => ({
    default: m.AdminVerificationQueuePage,
  }))
);
const AdminAuditLogPage = lazy(() =>
  import("@/pages/AdminAuditLogPage").then((m) => ({
    default: m.AdminAuditLogPage,
  }))
);
const AnalyticsPage = lazy(() =>
  import("@/pages/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage }))
);
const LoginPage = lazy(() =>
  import("@/pages/LoginPage").then((m) => ({ default: m.LoginPage }))
);
const SignupPage = lazy(() =>
  import("@/pages/SignupPage").then((m) => ({ default: m.SignupPage }))
);
const MyReportsPage = lazy(() =>
  import("@/pages/MyReportsPage").then((m) => ({ default: m.MyReportsPage }))
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      retry: 1,
    },
  },
});

function PageFallback() {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        height: "100vh",
        background: "#0f172a",
        color: "#94a3b8",
        fontSize: "1rem",
      }}
    >
      Loading…
    </div>
  );
}

export function AuthGate() {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return (
      <Suspense fallback={<PageFallback />}>
        <LoginPage />
      </Suspense>
    );
  }

  const role = (user?.role || "CITIZEN").toUpperCase();
  const destination =
    role === "ADMIN"
      ? "/dashboard"
      : role === "OPERATOR"
        ? "/admin/queue"
        : "/citizen-dashboard";

  return <Navigate to={destination} replace />;
}

export function App() {
  useEffect(() => {
    realtimeService.initialize(queryClient);
    return () => {
      realtimeService.disconnect();
    };
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <LocationProvider>
            <Suspense fallback={<PageFallback />}>
              <Routes>
                <Route path="/" element={<AuthGate />} />
                <Route path="/welcome" element={<HomePage />} />
                <Route
                  path="/citizen-dashboard"
                  element={<CitizenDashboardPage />}
                />
                <Route
                  path="/national-map"
                  element={
                    <ProtectedRoute roles={["CITIZEN", "OPERATOR", "ADMIN"]}>
                      <NationalMapPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/dashboard"
                  element={
                    <ProtectedRoute roles={["CITIZEN", "OPERATOR", "ADMIN"]}>
                      <DashboardPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/incidents"
                  element={
                    <ProtectedRoute roles={["CITIZEN", "OPERATOR", "ADMIN"]}>
                      <IncidentListPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/incidents/:id"
                  element={
                    <ProtectedRoute roles={["CITIZEN", "OPERATOR", "ADMIN"]}>
                      <IncidentDetailPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/live-map"
                  element={
                    <ProtectedRoute roles={["CITIZEN", "OPERATOR", "ADMIN"]}>
                      <LiveMapPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/report"
                  element={
                    <ProtectedRoute roles={["CITIZEN", "ADMIN"]}>
                      <CitizenReportPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/track-report"
                  element={
                    <ProtectedRoute roles={["CITIZEN", "ADMIN"]}>
                      <TrackReportPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/my-reports"
                  element={
                    <ProtectedRoute roles={["CITIZEN", "ADMIN"]}>
                      <MyReportsPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/admin/queue"
                  element={
                    <ProtectedRoute roles={["OPERATOR", "ADMIN"]}>
                      <AdminVerificationQueuePage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/admin/audit-logs"
                  element={
                    <ProtectedRoute roles={["OPERATOR", "ADMIN"]}>
                      <AdminAuditLogPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/verification"
                  element={<Navigate to="/admin/queue" replace />}
                />
                <Route
                  path="/analytics"
                  element={
                    <ProtectedRoute roles={["CITIZEN", "OPERATOR", "ADMIN"]}>
                      <AnalyticsPage />
                    </ProtectedRoute>
                  }
                />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/signup" element={<SignupPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </LocationProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
