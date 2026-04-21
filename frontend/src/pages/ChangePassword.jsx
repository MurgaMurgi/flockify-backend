import React, { useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import "./login.css";

export default function ChangePassword() {
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const API_BASE = import.meta.env.VITE_API_BASE;

  const handleSubmit = async () => {
    if (newPassword.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }
    if (newPassword !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      await axios.post(
        `${API_BASE}/api/auth/change-password`,
        { current_password: "", new_password: newPassword },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      const role = localStorage.getItem("user_role");
      if (role === "superadmin" || role === "super_admin") {
        navigate("/superadmin");
      } else {
        navigate("/dashboard");
      }
    } catch (err) {
      const msg =
        err.response?.data?.detail || "Failed to change password.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>Set New Password</h1>
        <p className="subtitle">
          Your account requires a password change before continuing
        </p>

        {error && <div className="login-error">{error}</div>}

        <div className="login-field">
          <label>New Password</label>
          <input
            type="password"
            placeholder="At least 6 characters"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          />
        </div>

        <div className="login-field">
          <label>Confirm Password</label>
          <input
            type="password"
            placeholder="Repeat new password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          />
        </div>

        <button
          className="login-submit-btn"
          onClick={handleSubmit}
          disabled={loading}
        >
          {loading ? "Saving..." : "Set Password & Continue"}
        </button>
      </div>
    </div>
  );
}
