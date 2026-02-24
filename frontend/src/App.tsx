import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useEffect } from "react";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";

// Layout
import AppLayout from "@/components/layout/AppLayout";

// Pages
import LoginPage from "@/pages/LoginPage";
import DocumentsPage from "@/pages/DocumentsPage";
import DocumentDetailPage from "@/pages/DocumentDetailPage";
import RulesetsPage from "@/pages/RulesetsPage";
import JobsPage from "@/pages/JobsPage";
import JobDetailPage from "@/pages/JobDetailPage";
import ReviewPage from "@/pages/ReviewPage";
import AuditPage from "@/pages/AuditPage";
import AdminPage from "@/pages/AdminPage";
import NotFoundPage from "@/pages/NotFoundPage";

// Route guards
import ProtectedRoute from "@/components/routing/ProtectedRoute";
import RoleRoute from "@/components/routing/RoleRoute";

export default function App() {
  const { accessToken, setUser, logout } = useAuthStore();

  // Re-hydrate user profile after page reload.
  useEffect(() => {
    if (!accessToken) return;
    authApi.me().then(setUser).catch(() => logout());
  }, [accessToken, setUser, logout]);

  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected — requires auth */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/documents" replace />} />
            <Route path="documents" element={<DocumentsPage />} />
            <Route path="documents/:id" element={<DocumentDetailPage />} />
            <Route path="rulesets" element={<RulesetsPage />} />
            <Route path="jobs" element={<JobsPage />} />
            <Route path="jobs/:id" element={<JobDetailPage />} />
            <Route path="reviews/:rewriteId" element={<ReviewPage />} />

            {/* ADMIN only routes */}
            <Route element={<RoleRoute roles={["ADMIN"]} />}>
              <Route path="audit" element={<AuditPage />} />
              <Route path="admin/users" element={<AdminPage />} />
            </Route>
          </Route>
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
