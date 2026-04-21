import { Navigate } from "react-router-dom";

export function RequireAdmin({ children }) {
  const token = localStorage.getItem("token");
  const role = localStorage.getItem("user_role");

  if (!token) return <Navigate to="/login" replace />;

  if (role === "superadmin" || role === "super_admin") {
    return <Navigate to="/superadmin" replace />;
  }

  return children;
}

export function RequireSuperAdmin({ children }) {
  const token = localStorage.getItem("token");
  const role = localStorage.getItem("user_role");

  if (!token) return <Navigate to="/superadmin-login" replace />;

  if (role !== "superadmin" && role !== "super_admin") {
    return <Navigate to="/superadmin-login" replace />;
  }

  return children;
}
