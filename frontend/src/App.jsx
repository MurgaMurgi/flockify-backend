import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import { RequireAdmin, RequireSuperAdmin } from "./components/ProtectedRoute";
import Dashboard from "./pages/dashboard";
import Farms from "./pages/farms";
import Login from "./pages/login";
import FarmDetails from "./pages/FarmDetails";
import SuperAdminLogin from "./pages/SuperAdminLogin";
import SuperAdminDashboard from "./pages/SuperAdminDashboard";
import PreviousBatches from "./pages/PreviousBatches";
import BatchDetails from "./pages/BatchDetails";
import DataPortal from "./pages/DataPortal";
import ChangePassword from "./pages/ChangePassword";

function App() {
  return (
    <Routes>
      {/* Default → login */}
      <Route path="/" element={<Navigate to="/login" replace />} />

      {/* Separate login pages */}
      <Route path="/login" element={<Login />} />
      <Route path="/superadmin-login" element={<SuperAdminLogin />} />
      <Route path="/change-password" element={<ChangePassword />} />

      {/* Legacy admin_login → superadmin-login */}
      <Route path="/admin_login" element={<Navigate to="/superadmin-login" replace />} />
      {/* Legacy super-admin-dashboard → superadmin */}
      <Route path="/super-admin-dashboard" element={<Navigate to="/superadmin" replace />} />

      {/* Super Admin panel — protected: superadmin role only */}
      <Route
        path="/superadmin"
        element={
          <RequireSuperAdmin>
            <SuperAdminDashboard />
          </RequireSuperAdmin>
        }
      />

      {/* Data Portal — protected: admin role */}
      <Route
        path="/farm/:farm_id/shed/:shed_id/portal"
        element={
          <RequireAdmin>
            <DataPortal />
          </RequireAdmin>
        }
      />

      {/* Admin routes inside sidebar layout — protected: admin role */}
      <Route
        element={
          <RequireAdmin>
            <Layout />
          </RequireAdmin>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/farms" element={<Farms />} />
        <Route path="/farm/:farm_id" element={<FarmDetails />} />
        <Route path="/batch/:batch_id" element={<BatchDetails />} />
        <Route path="/previous-batches" element={<PreviousBatches />} />
      </Route>
    </Routes>
  );
}

export default App;
