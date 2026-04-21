import { useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import "./login.css";

const API_BASE = import.meta.env.VITE_API_BASE;

export default function Login() {
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleLogin = async () => {
    if (!userId.trim() || !password.trim()) {
      setError("Please enter your User ID and password");
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

      // Store JWT and user info
      localStorage.setItem("token", access_token);
      localStorage.setItem("adminUser", JSON.stringify(data));
      localStorage.setItem("user_role", data.role);

      // Must change password takes priority
      if (must_change_password) {
        navigate("/change-password");
        return;
      }

      // Route by role
      if (data.role === "superadmin" || data.role === "super_admin") {
        navigate("/superadmin");
      } else {
        navigate("/dashboard");
      }
    } catch (err) {
      setError(
        err.response?.data?.detail || "Login failed. Please check your credentials."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logos">
          <img src="/5.png" alt="Flockify" className="login-logo-chicken" />
          <img src="/6.png" alt="Flockify" className="login-logo-text" />
        </div>
        <h1>Welcome to Flockify</h1>
        <p className="subtitle">Smart farm management, simplified</p>

        {error && <div className="login-error">{error}</div>}

        <div className="login-field">
          <label>User ID or Email</label>
          <input
            type="text"
            placeholder="Enter your User ID or Email"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            autoFocus
          />
        </div>

        <div className="login-field">
          <label>Password</label>
          <input
            type="password"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
          />
        </div>

        <button
          className="login-submit-btn"
          onClick={handleLogin}
          disabled={loading}
        >
          {loading ? "Logging in..." : "Login"}
        </button>

      </div>
    </div>
  );
}
