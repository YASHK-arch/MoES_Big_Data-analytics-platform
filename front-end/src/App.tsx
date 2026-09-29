import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/i18n";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { LocationProvider } from "@/context/LocationContext";
import { realtimeService } from "@/services/realtimeService";
import { HomePage } from "@/pages/HomePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { LiveMapPage } from "@/pages/LiveMapPage";
import { CitizenReportPage } from "@/pages/CitizenReportPage";
import { TrackReportPage } from "@/pages/TrackReportPage";
import { IncidentListPage } from "@/pages/IncidentListPage";
import { IncidentDetailPage } from "@/pages/IncidentDetailPage";
import { CitizenDashboardPage } from "@/pages/CitizenDashboardPage";
import { NationalMapPage } from "@/pages/NationalMapPage";
import { AdminVerificationQueuePage } from "@/pages/AdminVerificationQueuePage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { LoginPage } from "@/pages/LoginPage";
import { SignupPage } from "@/pages/SignupPage";
import { MyReportsPage } from "@/pages/MyReportsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      retry: 1,
    },
  },
});

export function AuthGate() {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <LoginPage />;
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
          </LocationProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
