import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { useParams, useNavigate } from "react-router-dom";
import "./DataPortal.css";

const API_BASE = import.meta.env.VITE_API_BASE;

function authHeaders() {
  const token = localStorage.getItem("token");
  return { Authorization: `Bearer ${token}` };
}

// Generate IST date string (YYYY-MM-DD)
function todayIST() {
  return new Date(
    new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" })
  )
    .toISOString()
    .slice(0, 10);
}

// Generate all dates from start to today (inclusive), YYYY-MM-DD
function generateDates(placementDate) {
  const today = todayIST();
  const dates = [];
  const start = new Date(placementDate + "T00:00:00");
  const end = new Date(today + "T00:00:00");
  if (start > end) return [];
  let cur = new Date(start);
  while (cur <= end) {
    dates.push(cur.toISOString().slice(0, 10));
    cur.setDate(cur.getDate() + 1);
  }
  return dates;
}

// Format YYYY-MM-DD → DD/MM/YYYY
function fmtDisplay(d) {
  if (!d) return "";
  const [y, m, day] = d.split("-");
  return `${day}/${m}/${y}`;
}

// Empty row templates
function emptyDaily(date) {
  return {
    entry_date: date,
    mortality: "",
    culling: "",
    culling_reason: "",
    mortality_reason: "",
    feed_consumption_kg: "",
    water_consumed_ltrs: "",
    lighting_hours: "",
    temperature: "",
    medical_attention: false,
    medical_notes: "",
  };
}

function emptyEgg(date) {
  return {
    entry_date: date,
    good_eggs: "",
    floor_eggs: "",
    broken_cracked_eggs: "",
    mishapped_eggs: "",
  };
}

function emptyDispatch(date) {
  return {
    dispatch_date: date,
    dispatched_good_eggs: "",
    dispatched_floor_mis_eggs: "",
  };
}

function emptyWeekly(date) {
  return {
    entry_date: date,
    ammonia_level: "",
    avg_bird_weight: "",
    weekly_notes: "",
  };
}

export default function DataPortal() {
  const { farm_id, shed_id } = useParams();
  const navigate = useNavigate();

  const [batch, setBatch] = useState(null);
  const [dates, setDates] = useState([]);
  const [activeTab, setActiveTab] = useState("daily");

  const [dailyRows, setDailyRows] = useState({});
  const [eggRows, setEggRows] = useState({});
  const [dispatchRows, setDispatchRows] = useState({});
  const [weeklyRows, setWeeklyRows] = useState({});

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [error, setError] = useState("");

  const farmId = parseInt(farm_id);
  const shedId = parseInt(shed_id);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const token = localStorage.getItem("token");
      if (!token) { navigate("/login"); return; }

      const [batchRes, dailyRes, eggRes, dispatchRes, weeklyRes] = await Promise.all([
        axios.get(`${API_BASE}/api/admin/shed/active-batch?shed_id=${shedId}`, { headers: authHeaders() }),
        axios.get(`${API_BASE}/api/admin/shed/daily-entries?shed_id=${shedId}`, { headers: authHeaders() }),
        axios.get(`${API_BASE}/api/admin/shed/egg-entries?shed_id=${shedId}`, { headers: authHeaders() }),
        axios.get(`${API_BASE}/api/admin/shed/dispatch-entries?shed_id=${shedId}`, { headers: authHeaders() }),
        axios.get(`${API_BASE}/api/admin/shed/weekly-entries?shed_id=${shedId}`, { headers: authHeaders() }),
      ]);

      const batchData = batchRes.data.data;
      setBatch(batchData);

      const allDates = generateDates(batchData.placement_date);
      setDates(allDates);

      // Build daily rows indexed by date
      const dMap = {};
      allDates.forEach((d) => { dMap[d] = emptyDaily(d); });
      (dailyRes.data.data || []).forEach((r) => {
        if (dMap[r.entry_date]) {
          dMap[r.entry_date] = {
            entry_date: r.entry_date,
            mortality: r.mortality ?? "",
            culling: r.culling ?? "",
            culling_reason: r.culling_reason ?? "",
            mortality_reason: r.mortality_reason ?? "",
            feed_consumption_kg: r.feed_consumption_kg ?? "",
            water_consumed_ltrs: r.water_consumed_ltrs ?? "",
            lighting_hours: r.lighting_hours ?? "",
            temperature: r.temperature ?? "",
            medical_attention: r.medical_attention ?? false,
            medical_notes: r.medical_notes ?? "",
          };
        }
      });
      setDailyRows(dMap);

      // Egg rows
      const eMap = {};
      allDates.forEach((d) => { eMap[d] = emptyEgg(d); });
      (eggRes.data.data || []).forEach((r) => {
        if (eMap[r.entry_date]) {
          eMap[r.entry_date] = {
            entry_date: r.entry_date,
            good_eggs: r.good_eggs ?? "",
            floor_eggs: r.floor_eggs ?? "",
            broken_cracked_eggs: r.broken_cracked_eggs ?? "",
            mishapped_eggs: r.mishapped_eggs ?? "",
          };
        }
      });
      setEggRows(eMap);

      // Dispatch rows
      const dspMap = {};
      allDates.forEach((d) => { dspMap[d] = emptyDispatch(d); });
      (dispatchRes.data.data || []).forEach((r) => {
        if (dspMap[r.entry_date]) {
          dspMap[r.entry_date] = {
            dispatch_date: r.entry_date,
            dispatched_good_eggs: r.dispatched_good_eggs ?? "",
            dispatched_floor_mis_eggs: r.dispatched_floor_mis_eggs ?? "",
          };
        }
      });
      setDispatchRows(dspMap);

      // Weekly rows
      const wMap = {};
      allDates.forEach((d) => { wMap[d] = emptyWeekly(d); });
      (weeklyRes.data.data || []).forEach((r) => {
        if (wMap[r.entry_date]) {
          wMap[r.entry_date] = {
            entry_date: r.entry_date,
            ammonia_level: r.ammonia_level ?? "",
            avg_bird_weight: r.avg_bird_weight ?? "",
            weekly_notes: r.weekly_notes ?? "",
          };
        }
      });
      setWeeklyRows(wMap);
    } catch (e) {
      if (e.response?.status === 401) { navigate("/login"); return; }
      if (e.response?.status === 404) {
        setError("No active batch found for this shed. Please create a batch first.");
      } else {
        setError(e.response?.data?.detail || "Failed to load data");
      }
    } finally {
      setLoading(false);
    }
  }, [shedId, navigate]);

  useEffect(() => { load(); }, [load]);

  // Cumulative egg availability for dispatch tab
  function getEggAvailableUpTo(date) {
    let collected = 0;
    let dispatched = 0;
    for (const d of dates) {
      const eg = eggRows[d];
      if (eg) {
        collected += (parseInt(eg.good_eggs) || 0) + (parseInt(eg.floor_eggs) || 0);
      }
      const dsp = dispatchRows[d];
      if (dsp) {
        dispatched +=
          (parseInt(dsp.dispatched_good_eggs) || 0) +
          (parseInt(dsp.dispatched_floor_mis_eggs) || 0);
      }
      if (d === date) break;
    }
    return Math.max(0, collected - dispatched);
  }

  const updateDaily = (date, field, value) => {
    setDailyRows((prev) => ({
      ...prev,
      [date]: { ...prev[date], [field]: value },
    }));
  };

  const updateEgg = (date, field, value) => {
    setEggRows((prev) => ({
      ...prev,
      [date]: { ...prev[date], [field]: value },
    }));
  };

  const updateDispatch = (date, field, value) => {
    setDispatchRows((prev) => ({
      ...prev,
      [date]: { ...prev[date], [field]: value },
    }));
  };

  const updateWeekly = (date, field, value) => {
    setWeeklyRows((prev) => ({
      ...prev,
      [date]: { ...prev[date], [field]: value },
    }));
  };

  const saveAll = async () => {
    setSaving(true);
    setSaveMsg("");
    try {
      const toNum = (v) => (v === "" || v === null || v === undefined ? null : parseFloat(v));
      const toInt = (v) => (v === "" || v === null || v === undefined ? 0 : parseInt(v) || 0);

      const dailyPayload = {
        farm_id: farmId,
        shed_id: shedId,
        rows: dates.map((d) => {
          const r = dailyRows[d] || emptyDaily(d);
          return {
            entry_date: d,
            mortality: toInt(r.mortality),
            culling: toInt(r.culling),
            culling_reason: r.culling_reason || null,
            mortality_reason: r.mortality_reason || null,
            feed_consumption_kg: toNum(r.feed_consumption_kg),
            water_consumed_ltrs: toNum(r.water_consumed_ltrs),
            lighting_hours: toNum(r.lighting_hours),
            temperature: toNum(r.temperature),
            medical_attention: !!r.medical_attention,
            medical_notes: r.medical_notes || null,
          };
        }),
      };

      const eggPayload = {
        farm_id: farmId,
        shed_id: shedId,
        rows: dates.map((d) => {
          const r = eggRows[d] || emptyEgg(d);
          return {
            entry_date: d,
            good_eggs: toInt(r.good_eggs),
            floor_eggs: toInt(r.floor_eggs),
            broken_cracked_eggs: toInt(r.broken_cracked_eggs),
            mishapped_eggs: toInt(r.mishapped_eggs),
          };
        }),
      };

      const dispatchPayload = {
        farm_id: farmId,
        shed_id: shedId,
        rows: dates
          .map((d) => {
            const r = dispatchRows[d] || emptyDispatch(d);
            return {
              dispatch_date: d,
              dispatched_good_eggs: toInt(r.dispatched_good_eggs),
              dispatched_floor_mis_eggs: toInt(r.dispatched_floor_mis_eggs),
            };
          })
          .filter((r) => r.dispatched_good_eggs > 0 || r.dispatched_floor_mis_eggs > 0),
      };

      const weeklyPayload = {
        farm_id: farmId,
        shed_id: shedId,
        rows: dates.map((d) => {
          const r = weeklyRows[d] || emptyWeekly(d);
          return {
            entry_date: d,
            ammonia_level: toNum(r.ammonia_level),
            avg_bird_weight: toNum(r.avg_bird_weight),
            weekly_notes: r.weekly_notes || null,
          };
        }),
      };

      const h = authHeaders();
      const [dr, er, dsr, wr] = await Promise.all([
        axios.post(`${API_BASE}/api/daily-entry/bulk`, dailyPayload, { headers: h }),
        axios.post(`${API_BASE}/api/egg-entry/bulk`, eggPayload, { headers: h }),
        dispatchPayload.rows.length > 0
          ? axios.post(`${API_BASE}/api/egg-dispatch/bulk`, dispatchPayload, { headers: h })
          : Promise.resolve({ data: { inserted: 0, updated: 0 } }),
        axios.post(`${API_BASE}/api/weekly-entry/bulk`, weeklyPayload, { headers: h }),
      ]);

      const total =
        (dr.data.total || 0) +
        (er.data.total || 0) +
        (dsr.data.total || 0) +
        (wr.data.total || 0);

      setSaveMsg(`Saved successfully — ${total} records updated`);
      setTimeout(() => setSaveMsg(""), 4000);
      load();
    } catch (e) {
      setSaveMsg(e.response?.data?.detail || "Save failed. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="dp-loading">
        <div className="dp-spinner" />
        <p>Loading data portal...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dp-error-page">
        <p>{error}</p>
        <button onClick={() => navigate(-1)} className="dp-back-btn">
          ← Go Back
        </button>
      </div>
    );
  }

  const tabs = [
    { key: "daily", label: "Daily Entry" },
    { key: "egg", label: "Egg Collection" },
    { key: "dispatch", label: "Egg Dispatch" },
    { key: "weekly", label: "Weekly Entry" },
  ];

  return (
    <div className="dp-container">
      {/* Top Bar */}
      <div className="dp-topbar">
        <div className="dp-topbar-left">
          <button className="dp-back-btn" onClick={() => navigate(-1)}>
            ← Back
          </button>
          <div>
            <h1 className="dp-heading">
              Data Portal — Shed {batch?.shed_number}
            </h1>
            <p className="dp-subheading">
              {batch?.farm_name} &nbsp;|&nbsp; Placement:{" "}
              {fmtDisplay(batch?.placement_date)} &nbsp;|&nbsp; Birds:{" "}
              {batch?.initial_bird_count?.toLocaleString()}
            </p>
          </div>
        </div>
        <div className="dp-topbar-right">
          {saveMsg && (
            <span
              className={saveMsg.includes("failed") || saveMsg.includes("Failed") ? "dp-save-err" : "dp-save-ok"}
            >
              {saveMsg}
            </span>
          )}
          <button className="dp-save-btn" onClick={saveAll} disabled={saving}>
            {saving ? "Saving..." : "Save All"}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="dp-tabs">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`dp-tab ${activeTab === t.key ? "dp-tab-active" : ""}`}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Table Area */}
      <div className="dp-table-wrap">
        {activeTab === "daily" && (
          <table className="dp-table">
            <thead>
              <tr>
                <th className="dp-th-date">Date</th>
                <th>Mortality</th>
                <th>Culling</th>
                <th>Feed (kg)</th>
                <th>Water (L)</th>
                <th>Temp (°C)</th>
                <th>Lighting (h)</th>
                <th>Mort. Reason</th>
                <th>Cull. Reason</th>
                <th>Med. Notes</th>
              </tr>
            </thead>
            <tbody>
              {dates.map((d) => {
                const r = dailyRows[d] || emptyDaily(d);
                const isToday = d === todayIST();
                return (
                  <tr key={d} className={isToday ? "dp-row-today" : ""}>
                    <td className="dp-cell-date">{fmtDisplay(d)}</td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="dp-input dp-input-sm"
                        value={r.mortality}
                        onChange={(e) => updateDaily(d, "mortality", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="dp-input dp-input-sm"
                        value={r.culling}
                        onChange={(e) => updateDaily(d, "culling", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        className="dp-input dp-input-md"
                        value={r.feed_consumption_kg}
                        onChange={(e) => updateDaily(d, "feed_consumption_kg", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        step="0.1"
                        className="dp-input dp-input-md"
                        value={r.water_consumed_ltrs}
                        onChange={(e) => updateDaily(d, "water_consumed_ltrs", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.1"
                        className="dp-input dp-input-sm"
                        value={r.temperature}
                        onChange={(e) => updateDaily(d, "temperature", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        max="24"
                        step="0.5"
                        className="dp-input dp-input-sm"
                        value={r.lighting_hours}
                        onChange={(e) => updateDaily(d, "lighting_hours", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        className="dp-input dp-input-lg"
                        value={r.mortality_reason}
                        onChange={(e) => updateDaily(d, "mortality_reason", e.target.value)}
                        placeholder="—"
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        className="dp-input dp-input-lg"
                        value={r.culling_reason}
                        onChange={(e) => updateDaily(d, "culling_reason", e.target.value)}
                        placeholder="—"
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        className="dp-input dp-input-lg"
                        value={r.medical_notes}
                        onChange={(e) => updateDaily(d, "medical_notes", e.target.value)}
                        placeholder="—"
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {activeTab === "egg" && (
          <table className="dp-table">
            <thead>
              <tr>
                <th className="dp-th-date">Date</th>
                <th>Good Eggs</th>
                <th>Floor Eggs</th>
                <th>Broken</th>
                <th>Mishapped</th>
                <th className="dp-th-calc">Total Collected</th>
              </tr>
            </thead>
            <tbody>
              {dates.map((d) => {
                const r = eggRows[d] || emptyEgg(d);
                const isToday = d === todayIST();
                const total =
                  (parseInt(r.good_eggs) || 0) +
                  (parseInt(r.floor_eggs) || 0);
                return (
                  <tr key={d} className={isToday ? "dp-row-today" : ""}>
                    <td className="dp-cell-date">{fmtDisplay(d)}</td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="dp-input dp-input-md"
                        value={r.good_eggs}
                        onChange={(e) => updateEgg(d, "good_eggs", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="dp-input dp-input-md"
                        value={r.floor_eggs}
                        onChange={(e) => updateEgg(d, "floor_eggs", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="dp-input dp-input-md"
                        value={r.broken_cracked_eggs}
                        onChange={(e) => updateEgg(d, "broken_cracked_eggs", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="dp-input dp-input-md"
                        value={r.mishapped_eggs}
                        onChange={(e) => updateEgg(d, "mishapped_eggs", e.target.value)}
                      />
                    </td>
                    <td className="dp-cell-calc">{total > 0 ? total : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {activeTab === "dispatch" && (
          <table className="dp-table">
            <thead>
              <tr>
                <th className="dp-th-date">Date</th>
                <th className="dp-th-avail">Eggs Available</th>
                <th>Dispatch Good</th>
                <th>Dispatch Floor/Mis</th>
                <th className="dp-th-calc">Total Dispatched</th>
              </tr>
            </thead>
            <tbody>
              {dates.map((d) => {
                const r = dispatchRows[d] || emptyDispatch(d);
                const isToday = d === todayIST();
                const available = getEggAvailableUpTo(d);
                const total =
                  (parseInt(r.dispatched_good_eggs) || 0) +
                  (parseInt(r.dispatched_floor_mis_eggs) || 0);
                return (
                  <tr key={d} className={isToday ? "dp-row-today" : ""}>
                    <td className="dp-cell-date">{fmtDisplay(d)}</td>
                    <td className="dp-cell-avail">
                      <span className={available > 0 ? "dp-avail-pos" : "dp-avail-zero"}>
                        {available.toLocaleString()}
                      </span>
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="dp-input dp-input-md"
                        value={r.dispatched_good_eggs}
                        onChange={(e) => updateDispatch(d, "dispatched_good_eggs", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        className="dp-input dp-input-md"
                        value={r.dispatched_floor_mis_eggs}
                        onChange={(e) => updateDispatch(d, "dispatched_floor_mis_eggs", e.target.value)}
                      />
                    </td>
                    <td className="dp-cell-calc">{total > 0 ? total : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {activeTab === "weekly" && (
          <table className="dp-table">
            <thead>
              <tr>
                <th className="dp-th-date">Date</th>
                <th>Ammonia (ppm)</th>
                <th>Avg Bird Wt (kg)</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {dates.map((d) => {
                const r = weeklyRows[d] || emptyWeekly(d);
                const isToday = d === todayIST();
                return (
                  <tr key={d} className={isToday ? "dp-row-today" : ""}>
                    <td className="dp-cell-date">{fmtDisplay(d)}</td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        step="0.1"
                        className="dp-input dp-input-md"
                        value={r.ammonia_level}
                        onChange={(e) => updateWeekly(d, "ammonia_level", e.target.value)}
                        placeholder="—"
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        className="dp-input dp-input-md"
                        value={r.avg_bird_weight}
                        onChange={(e) => updateWeekly(d, "avg_bird_weight", e.target.value)}
                        placeholder="—"
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        className="dp-input dp-input-xl"
                        value={r.weekly_notes}
                        onChange={(e) => updateWeekly(d, "weekly_notes", e.target.value)}
                        placeholder="—"
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Floating Save Button */}
      <div className="dp-float-save">
        <button className="dp-save-btn" onClick={saveAll} disabled={saving}>
          {saving ? "Saving..." : "Save All"}
        </button>
      </div>
    </div>
  );
}
