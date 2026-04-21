import React, { useEffect, useState, useRef } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, LineChart, Line,
} from "recharts";
import "./superadmin.css";

const API_BASE = import.meta.env.VITE_API_BASE;

function authHeaders() {
  return { Authorization: `Bearer ${localStorage.getItem("token")}` };
}

function fmt(v) {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleDateString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
    });
  } catch { return v; }
}

function fmtDT(v) {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return v; }
}

function fmtISO(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

// ─── Drill Section ────────────────────────────────────────────────────────────
function DrillSection({ title, children }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="sad-drill-section">
      <button className="sad-drill-section-toggle" onClick={() => setOpen((o) => !o)}>
        <span>{title}</span>
        <span className="sad-caret">{open ? "▲" : "▼"}</span>
      </button>
      {open && <div className="sad-drill-section-body">{children}</div>}
    </div>
  );
}

// ─── Drill Table ──────────────────────────────────────────────────────────────
function DrillTable({ cols, rows, emptyMsg }) {
  if (!rows || rows.length === 0) {
    return <p className="sad-empty">{emptyMsg || "No records"}</p>;
  }
  return (
    <div className="sad-table-scroll">
      <table className="sad-table">
        <thead>
          <tr>{cols.map((c) => <th key={c.key}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c.key}>{c.render ? c.render(row) : (row[c.key] ?? "—")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Stat Card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, color }) {
  return (
    <div className="sad-stat-card" style={{ borderTop: `3px solid ${color || "#4f46e5"}` }}>
      <div className="sad-stat-value">{value}</div>
      <div className="sad-stat-label">{label}</div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function SuperAdminDashboard() {
  const navigate = useNavigate();
  const drillRef = useRef(null);

  const [allData, setAllData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Drill
  const [drillUser, setDrillUser] = useState(null);
  const [drillData, setDrillData] = useState(null);
  const [drillLoading, setDrillLoading] = useState(false);
  const [drillError, setDrillError] = useState("");

  // Modals
  const [resetTarget, setResetTarget] = useState(null);
  const [resetPwd, setResetPwd] = useState("");
  const [resetMsg, setResetMsg] = useState("");

  const [validityTarget, setValidityTarget] = useState(null);
  const [validityStart, setValidityStart] = useState("");
  const [validityEnd, setValidityEnd] = useState("");
  const [validityMsg, setValidityMsg] = useState("");

  const [createModal, setCreateModal] = useState(false);
  const [newUser, setNewUser] = useState({ user_id: "", email: "", name: "", role: "admin", temp_password: "" });
  const [createMsg, setCreateMsg] = useState("");

  const [search, setSearch] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await axios.get(`${API_BASE}/api/admin/all-data`, { headers: authHeaders() });
      setAllData(res.data);
    } catch (e) {
      if (e.response?.status === 401 || e.response?.status === 403) {
        localStorage.clear();
        navigate("/superadmin-login");
        return;
      }
      setError(e.response?.data?.detail || "Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleDrill = async (user) => {
    setDrillUser(user);
    setDrillData(null);
    setDrillError("");
    setDrillLoading(true);
    setTimeout(() => drillRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    try {
      const res = await axios.get(
        `${API_BASE}/api/admin/user-drill/${user.admin_id}`,
        { headers: authHeaders() }
      );
      setDrillData(res.data);
    } catch (e) {
      setDrillError(e.response?.data?.detail || "Failed to load user data");
    } finally {
      setDrillLoading(false);
    }
  };

  const handleToggle = async (user) => {
    const action = user.is_active ? "disable" : "enable";
    if (!window.confirm(`${action.charAt(0).toUpperCase() + action.slice(1)} user "${user.user_id}"?`)) return;
    try {
      await axios.post(`${API_BASE}/api/admin/toggle-user`, { target_user_id: user.user_id }, { headers: authHeaders() });
      load();
    } catch (e) { alert(e.response?.data?.detail || "Failed"); }
  };

  const handleResetSubmit = async () => {
    if (resetPwd.length < 6) { setResetMsg("Minimum 6 characters"); return; }
    try {
      const res = await axios.post(`${API_BASE}/api/auth/reset-password`,
        { target_user_id: resetTarget.user_id, new_password: resetPwd },
        { headers: authHeaders() }
      );
      setResetMsg(res.data.message || "Password reset");
      setTimeout(() => { setResetTarget(null); setResetPwd(""); setResetMsg(""); }, 1500);
    } catch (e) { setResetMsg(e.response?.data?.detail || "Failed"); }
  };

  const handleValiditySubmit = async () => {
    try {
      const res = await axios.post(`${API_BASE}/api/admin/set-validity`,
        { target_user_id: validityTarget.user_id, start_date: validityStart || null, end_date: validityEnd || null },
        { headers: authHeaders() }
      );
      setValidityMsg(res.data.message || "Updated");
      setTimeout(() => { setValidityTarget(null); setValidityStart(""); setValidityEnd(""); setValidityMsg(""); load(); }, 1500);
    } catch (e) { setValidityMsg(e.response?.data?.detail || "Failed"); }
  };

  const handleCreateUser = async () => {
    setCreateMsg("");
    try {
      const res = await axios.post(`${API_BASE}/api/auth/create-user`, newUser, { headers: authHeaders() });
      setCreateMsg(`User "${res.data.data.user_id}" created`);
      setNewUser({ user_id: "", email: "", name: "", role: "admin", temp_password: "" });
      load();
      setTimeout(() => { setCreateModal(false); setCreateMsg(""); }, 2000);
    } catch (e) { setCreateMsg(e.response?.data?.detail || "Failed"); }
  };

  const handleExport = (adminId, userName) => {
    const token = localStorage.getItem("token");
    const url = `${API_BASE}/api/admin/export-user/${adminId}?token=${token}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `export_${userName || adminId}_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const logout = () => { localStorage.clear(); navigate("/superadmin-login"); };

  if (loading) return <div className="sad-loading"><div className="sad-spinner" /><p>Loading console...</p></div>;
  if (error) return <div className="sad-error-page">{error} <button onClick={load}>Retry</button></div>;

  const stats = allData?.stats || {};
  const users = allData?.users || [];
  const filteredUsers = search.trim()
    ? users.filter((u) => [u.user_id, u.name, u.email].join(" ").toLowerCase().includes(search.toLowerCase()))
    : users;

  // Chart data derived from users
  const userChartData = users
    .filter((u) => u.role !== "superadmin" && u.role !== "super_admin")
    .slice(0, 20)
    .map((u) => ({
      name: u.user_id,
      farms: u.farms_count || 0,
      entries: u.entry_count || 0,
      eggs: u.egg_count || 0,
    }));

  return (
    <div className="sad-container">
      {/* ── Header ── */}
      <div className="sad-header">
        <div className="sad-header-left">
          <img src="/5.png" alt="logo" className="sad-logo" />
          <div>
            <h1 className="sad-title">Super Admin Console</h1>
            <p className="sad-subtitle">Flockify Enterprise Control Panel</p>
          </div>
        </div>
        <div className="sad-header-right">
          <button className="sad-btn-primary" onClick={() => setCreateModal(true)}>+ Create User</button>
          <button className="sad-btn-logout" onClick={logout}>Logout</button>
        </div>
      </div>

      <div className="sad-body">
        {/* ── Stats Grid ── */}
        <div className="sad-stats-grid">
          <StatCard label="Total Users" value={stats.AdminUsers ?? 0} color="#4f46e5" />
          <StatCard label="Farms" value={stats.Farms ?? 0} color="#0891b2" />
          <StatCard label="Sheds" value={stats.Sheds ?? 0} color="#059669" />
          <StatCard label="Active Batches" value={stats.active_batches ?? 0} color="#d97706" />
          <StatCard label="Daily Entries" value={(stats.DailyEntries ?? 0).toLocaleString()} color="#7c3aed" />
          <StatCard label="Egg Records" value={(stats.EggDailyRecords ?? 0).toLocaleString()} color="#db2777" />
          <StatCard label="Good Eggs" value={(stats.total_good_eggs ?? 0).toLocaleString()} color="#16a34a" />
          <StatCard label="Dispatched" value={(stats.EggDispatchRecords ?? 0).toLocaleString()} color="#dc2626" />
        </div>

        {/* ── Charts ── */}
        {userChartData.length > 0 && (
          <div className="sad-charts-grid">
            <div className="sad-chart-card">
              <h3 className="sad-chart-title">Farms per User</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={userChartData} margin={{ top: 5, right: 10, left: -20, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-35} textAnchor="end" interval={0} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="farms" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="sad-chart-card">
              <h3 className="sad-chart-title">Entries per User</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={userChartData} margin={{ top: 5, right: 10, left: -20, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-35} textAnchor="end" interval={0} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="entries" fill="#0891b2" radius={[4, 4, 0, 0]} name="Daily Entries" />
                  <Bar dataKey="eggs" fill="#059669" radius={[4, 4, 0, 0]} name="Egg Records" />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* ── Users Table ── */}
        <div className="sad-section">
          <div className="sad-section-header">
            <h2 className="sad-section-title">Users ({filteredUsers.length})</h2>
            <input
              className="sad-search"
              type="text"
              placeholder="Search by ID, name, email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="sad-table-scroll">
            <table className="sad-table sad-users-table">
              <thead>
                <tr>
                  <th>User ID</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Farms</th>
                  <th>Status</th>
                  <th>Valid Until</th>
                  <th>Last Login</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((u) => (
                  <tr key={u.admin_id} className={[
                    drillUser?.admin_id === u.admin_id ? "sad-row-active" : "",
                    !u.is_active ? "sad-row-disabled" : "",
                  ].join(" ")}>
                    <td className="sad-mono">{u.user_id}</td>
                    <td>{u.name || "—"}</td>
                    <td>{u.email || "—"}</td>
                    <td><span className={`sad-badge sad-role-${u.role?.replace("_", "")}`}>{u.role}</span></td>
                    <td className="sad-center">{u.farms_count ?? 0}</td>
                    <td>
                      <span className={`sad-badge ${u.is_active ? "sad-active" : "sad-inactive"}`}>
                        {u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td>{fmt(u.end_date)}</td>
                    <td>{fmtDT(u.last_login)}</td>
                    <td className="sad-actions">
                      <button className="sad-btn sad-btn-view" onClick={() => handleDrill(u)}>View</button>
                      <button className={`sad-btn ${u.is_active ? "sad-btn-disable" : "sad-btn-enable"}`} onClick={() => handleToggle(u)}>
                        {u.is_active ? "Disable" : "Enable"}
                      </button>
                      <button className="sad-btn sad-btn-reset" onClick={() => { setResetTarget(u); setResetPwd(""); setResetMsg(""); }}>Reset Pwd</button>
                      <button className="sad-btn sad-btn-validity" onClick={() => {
                        setValidityTarget(u);
                        setValidityStart(u.start_date ? u.start_date.slice(0, 10) : "");
                        setValidityEnd(u.end_date ? u.end_date.slice(0, 10) : "");
                        setValidityMsg("");
                      }}>Validity</button>
                      <button className="sad-btn sad-btn-export" onClick={() => handleExport(u.admin_id, u.user_id)}>
                        ↓ Excel
                      </button>
                    </td>
                  </tr>
                ))}
                {filteredUsers.length === 0 && (
                  <tr><td colSpan="9" className="sad-no-data">No users found</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── Drilldown Panel ── */}
        {drillUser && (
          <div className="sad-drill-panel" ref={drillRef}>
            <div className="sad-drill-header">
              <div className="sad-drill-title-row">
                <div>
                  <h2 className="sad-drill-name">{drillUser.name || drillUser.user_id}</h2>
                  <p className="sad-drill-meta">
                    {drillUser.user_id} &nbsp;·&nbsp; {drillUser.email || "no email"} &nbsp;·&nbsp;
                    <span className={`sad-badge sad-role-${drillUser.role?.replace("_","")}`}>{drillUser.role}</span>
                  </p>
                </div>
                <div className="sad-drill-actions">
                  <button
                    className="sad-btn-excel"
                    onClick={() => handleExport(drillUser.admin_id, drillUser.user_id)}
                  >
                    ↓ Download Full Excel
                  </button>
                  <button className="sad-btn-close-drill" onClick={() => { setDrillUser(null); setDrillData(null); }}>
                    ✕ Close
                  </button>
                </div>
              </div>
              {drillLoading && (
                <div className="sad-drill-loading"><div className="sad-spinner" /> Loading user data...</div>
              )}
              {drillError && <div className="sad-drill-error">{drillError}</div>}
            </div>

            {drillData && !drillLoading && (
              <div className="sad-drill-content">
                {/* Summary chips */}
                <div className="sad-drill-summary">
                  {[
                    ["Farms", drillData.farms?.length ?? 0],
                    ["Sheds", drillData.sheds?.length ?? 0],
                    ["Batches", drillData.batches?.length ?? 0],
                    ["Daily Entries", drillData.entries?.length ?? 0],
                    ["Egg Records", drillData.egg?.length ?? 0],
                    ["Dispatches", drillData.dispatch?.length ?? 0],
                    ["Weekly", drillData.weekly?.length ?? 0],
                  ].map(([k, v]) => (
                    <div key={k} className="sad-drill-chip">
                      <span className="sad-drill-chip-val">{v}</span>
                      <span className="sad-drill-chip-label">{k}</span>
                    </div>
                  ))}
                </div>

                {/* 1. Farms */}
                <DrillSection title={`Farms (${drillData.farms?.length ?? 0})`}>
                  <DrillTable
                    cols={[
                      { key: "farm_id", label: "ID" },
                      { key: "farm_name", label: "Farm Name" },
                      { key: "farm_location", label: "Location" },
                      { key: "created_at", label: "Created", render: (r) => fmt(r.created_at) },
                    ]}
                    rows={drillData.farms}
                    emptyMsg="No farms"
                  />
                </DrillSection>

                {/* 2. Sheds */}
                <DrillSection title={`Sheds (${drillData.sheds?.length ?? 0})`}>
                  <DrillTable
                    cols={[
                      { key: "shed_id", label: "ID" },
                      { key: "farm_name", label: "Farm" },
                      { key: "shed_number", label: "Shed No." },
                      { key: "capacity", label: "Capacity" },
                      { key: "created_at", label: "Created", render: (r) => fmt(r.created_at) },
                    ]}
                    rows={drillData.sheds}
                    emptyMsg="No sheds"
                  />
                </DrillSection>

                {/* 3. Batches */}
                <DrillSection title={`Batches (${drillData.batches?.length ?? 0})`}>
                  <DrillTable
                    cols={[
                      { key: "batch_id", label: "ID" },
                      { key: "farm_name", label: "Farm" },
                      { key: "shed_number", label: "Shed" },
                      { key: "placement_date", label: "Placed", render: (r) => fmtISO(r.placement_date) },
                      { key: "initial_bird_count", label: "Birds" },
                      { key: "is_active", label: "Status", render: (r) => (
                        <span className={`sad-badge ${r.is_active ? "sad-active" : "sad-inactive"}`}>
                          {r.is_active ? "Active" : "Closed"}
                        </span>
                      )},
                    ]}
                    rows={drillData.batches}
                    emptyMsg="No batches"
                  />
                </DrillSection>

                {/* 4. Daily Entries */}
                <DrillSection title={`Daily Entries (${drillData.entries?.length ?? 0})`}>
                  <DrillTable
                    cols={[
                      { key: "entry_date", label: "Date", render: (r) => fmtISO(r.entry_date) },
                      { key: "farm_name", label: "Farm" },
                      { key: "shed_number", label: "Shed" },
                      { key: "mortality", label: "Mortality" },
                      { key: "mortality_reason", label: "Mort. Reason" },
                      { key: "culling", label: "Culling" },
                      { key: "culling_reason", label: "Cull. Reason" },
                      { key: "feed_consumption_kg", label: "Feed (kg)" },
                      { key: "water_consumed_ltrs", label: "Water (L)" },
                      { key: "lighting_hours", label: "Lighting (h)" },
                      { key: "temperature", label: "Temp (°C)" },
                      { key: "medical_attention", label: "Medical", render: (r) => r.medical_attention ? "Yes" : "No" },
                      { key: "medical_notes", label: "Med. Notes" },
                    ]}
                    rows={drillData.entries}
                    emptyMsg="No daily entries"
                  />
                </DrillSection>

                {/* 5. Egg Collection */}
                <DrillSection title={`Egg Collection (${drillData.egg?.length ?? 0})`}>
                  <DrillTable
                    cols={[
                      { key: "entry_date", label: "Date", render: (r) => fmtISO(r.entry_date) },
                      { key: "farm_name", label: "Farm" },
                      { key: "shed_number", label: "Shed" },
                      { key: "good_eggs", label: "Good" },
                      { key: "floor_eggs", label: "Floor" },
                      { key: "broken_cracked_eggs", label: "Broken" },
                      { key: "mishapped_eggs", label: "Mishapped" },
                      { key: "total", label: "Total", render: (r) =>
                        ((r.good_eggs || 0) + (r.floor_eggs || 0) + (r.broken_cracked_eggs || 0) + (r.mishapped_eggs || 0))
                      },
                    ]}
                    rows={drillData.egg}
                    emptyMsg="No egg records"
                  />
                </DrillSection>

                {/* 6. Egg Dispatch */}
                <DrillSection title={`Egg Dispatch (${drillData.dispatch?.length ?? 0})`}>
                  <DrillTable
                    cols={[
                      { key: "dispatch_date", label: "Date", render: (r) => fmtISO(r.dispatch_date || r.entry_date) },
                      { key: "farm_name", label: "Farm" },
                      { key: "shed_number", label: "Shed" },
                      { key: "dispatched_good_eggs", label: "Good Dispatched" },
                      { key: "dispatched_floor_mis_eggs", label: "Floor/Mis Dispatched" },
                      { key: "total_dispatched", label: "Total", render: (r) =>
                        ((r.dispatched_good_eggs || 0) + (r.dispatched_floor_mis_eggs || 0))
                      },
                    ]}
                    rows={drillData.dispatch}
                    emptyMsg="No dispatch records"
                  />
                </DrillSection>

                {/* 7. Weekly Entries */}
                <DrillSection title={`Weekly Entries (${drillData.weekly?.length ?? 0})`}>
                  <DrillTable
                    cols={[
                      { key: "entry_date", label: "Date", render: (r) => fmtISO(r.entry_date) },
                      { key: "farm_name", label: "Farm" },
                      { key: "shed_number", label: "Shed" },
                      { key: "ammonia_level", label: "Ammonia (ppm)" },
                      { key: "avg_bird_weight", label: "Avg Wt (g)" },
                      { key: "weekly_notes", label: "Notes" },
                    ]}
                    rows={drillData.weekly}
                    emptyMsg="No weekly entries"
                  />
                </DrillSection>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Reset Password Modal ── */}
      {resetTarget && (
        <div className="sad-overlay" onClick={() => setResetTarget(null)}>
          <div className="sad-modal" onClick={(e) => e.stopPropagation()}>
            <div className="sad-modal-header">
              <h3>Reset Password — {resetTarget.user_id}</h3>
              <button className="sad-modal-close" onClick={() => setResetTarget(null)}>✕</button>
            </div>
            <div className="sad-modal-body">
              <label className="sad-label">New Temporary Password</label>
              <input className="sad-input" type="text" value={resetPwd}
                onChange={(e) => setResetPwd(e.target.value)} placeholder="Min 6 characters" />
              {resetMsg && <p className={resetMsg.includes("ailed") ? "sad-msg-err" : "sad-msg-ok"}>{resetMsg}</p>}
            </div>
            <div className="sad-modal-footer">
              <button className="sad-btn sad-btn-reset" onClick={handleResetSubmit}>Reset Password</button>
              <button className="sad-btn sad-btn-secondary" onClick={() => setResetTarget(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Set Validity Modal ── */}
      {validityTarget && (
        <div className="sad-overlay" onClick={() => setValidityTarget(null)}>
          <div className="sad-modal" onClick={(e) => e.stopPropagation()}>
            <div className="sad-modal-header">
              <h3>Set Validity — {validityTarget.user_id}</h3>
              <button className="sad-modal-close" onClick={() => setValidityTarget(null)}>✕</button>
            </div>
            <div className="sad-modal-body">
              <label className="sad-label">Start Date (blank = no restriction)</label>
              <input className="sad-input" type="date" value={validityStart} onChange={(e) => setValidityStart(e.target.value)} />
              <label className="sad-label" style={{ marginTop: 12 }}>End Date (blank = unlimited)</label>
              <input className="sad-input" type="date" value={validityEnd} onChange={(e) => setValidityEnd(e.target.value)} />
              {validityMsg && <p className={validityMsg.includes("ailed") ? "sad-msg-err" : "sad-msg-ok"}>{validityMsg}</p>}
            </div>
            <div className="sad-modal-footer">
              <button className="sad-btn sad-btn-validity" onClick={handleValiditySubmit}>Save</button>
              <button className="sad-btn sad-btn-secondary" onClick={() => setValidityTarget(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Create User Modal ── */}
      {createModal && (
        <div className="sad-overlay" onClick={() => setCreateModal(false)}>
          <div className="sad-modal" onClick={(e) => e.stopPropagation()}>
            <div className="sad-modal-header">
              <h3>Create New User</h3>
              <button className="sad-modal-close" onClick={() => setCreateModal(false)}>✕</button>
            </div>
            <div className="sad-modal-body">
              {[
                { key: "user_id", label: "User ID", placeholder: "e.g. john_farm", type: "text" },
                { key: "name", label: "Name", placeholder: "Full name", type: "text" },
                { key: "email", label: "Email (optional)", placeholder: "user@example.com", type: "email" },
                { key: "temp_password", label: "Temp Password", placeholder: "Min 6 chars", type: "text" },
              ].map(({ key, label, placeholder, type }) => (
                <div key={key} style={{ marginBottom: 12 }}>
                  <label className="sad-label">{label}</label>
                  <input className="sad-input" type={type} placeholder={placeholder}
                    value={newUser[key]} onChange={(e) => setNewUser({ ...newUser, [key]: e.target.value })} />
                </div>
              ))}
              <div style={{ marginBottom: 12 }}>
                <label className="sad-label">Role</label>
                <select className="sad-input" value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
                  <option value="admin">Admin</option>
                  <option value="superadmin">Superadmin</option>
                </select>
              </div>
              {createMsg && <p className={createMsg.includes("ailed") ? "sad-msg-err" : "sad-msg-ok"}>{createMsg}</p>}
            </div>
            <div className="sad-modal-footer">
              <button className="sad-btn sad-btn-create" onClick={handleCreateUser}>Create User</button>
              <button className="sad-btn sad-btn-secondary" onClick={() => setCreateModal(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
