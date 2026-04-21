import React, { useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import "./login.css";

export default function AdminLogin() {
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const API_BASE = import.meta.env.VITE_API_BASE;

  const handleLogin = async () => {
    if (!userId.trim() || !password.trim()) {
      setError("Please enter your credentials");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await axios.post(`${API_BASE}/api/auth/login`, {
        user_id: userId.trim(),
        password,
      });

      const { access_token, must_change_password, data } = res.data;

      if (data.role !== "superadmin" && data.role !== "super_admin") {
        setError("This login is for Super Admins only.");
        setLoading(false);
        return;
      }

      localStorage.setItem("token", access_token);
      localStorage.setItem("adminUser", JSON.stringify(data));
      localStorage.setItem("user_role", data.role);

      if (must_change_password) {
        navigate("/change-password");
      } else {
        navigate("/superadmin");
      }
    } catch (err) {
      const msg =
        err.response?.data?.detail || "Login failed. Check your credentials.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>Super Admin Login</h1>
        <p className="subtitle">Access enterprise control panel</p>

        {error && <div className="login-error">{error}</div>}

        <div className="login-field">
          <label>User ID or Email</label>
          <input
            type="text"
            placeholder="Super Admin User ID or Email"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
          />
        </div>

        <div className="login-field">
          <label>Password</label>
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
          />
        </div>

        <button
          className="google-login-btn"
          onClick={handleLogin}
          disabled={loading}
        >
          {loading ? "Authenticating..." : "Login"}
        </button>

        <div style={{ marginTop: "16px" }}>
          <button className="switch-login-btn" onClick={() => navigate("/login")}>
            ← Back to User Login
          </button>
        </div>
      </div>
    </div>
  );
}
