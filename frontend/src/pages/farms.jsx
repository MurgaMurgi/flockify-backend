import React, { useState, useEffect } from "react";
import axios from "axios";
import "./farms.css";
import { useNavigate } from "react-router-dom";



export default function Farms() {
  const [farms, setFarms] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({
    farm_name: "",
    farm_owner_name: "",
    farm_owner_phone: "",
    farm_owner_email: "",
    supervisor_name: "",
    supervisor_phone: "",
    farm_location: "",
  });

  const [searchTerm, setSearchTerm] = useState("");
  const filteredFarms = farms.filter((farm) => {
    const q = searchTerm.toLowerCase();
    return (
      farm.farm_name.toLowerCase().includes(q) ||
      farm.supervisor_name.toLowerCase().includes(q) ||
      farm.supervisor_phone.toLowerCase().includes(q) ||
      farm.farm_location.toLowerCase().includes(q)
    );
  });
  const [editingFarmId, setEditingFarmId] = useState(null);



  const navigate = useNavigate();
  const API_BASE = import.meta.env.VITE_API_BASE;

  const admin = JSON.parse(localStorage.getItem("admin"));

  // -------------------------
  // Fetch farms on page load
  // -------------------------
  const loadFarms = async () => {
  try {
    const token = localStorage.getItem("token");

    const res = await axios.get(
      `${API_BASE}/api/farms`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );

    setFarms(res.data.data);
    console.log(res.data.data);

  } catch (err) {
    console.error("Failed to load farms:", err);

    if (err.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
    }
  }
};


  useEffect(() => {
    loadFarms();
  }, []);

  // -------------------------
  // Handle Add Farm Submit
  // -------------------------
const handleSave = async () => {
  try {
    const token = localStorage.getItem("token");

    const config = {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    };

    if (editingFarmId) {
      // EDIT MODE
      await axios.put(
        `${API_BASE}/api/update_farm?farm_id=${editingFarmId}`,
        form,
        config
      );
    } else {
      // ADD MODE
      await axios.post(
        `${API_BASE}/api/add_farm`,
        form,
        config
      );
    }

    setShowModal(false);
    loadFarms();
    setEditingFarmId(null);

    setForm({
      farm_name: "",
      farm_owner_name: "",
      farm_owner_phone: "",
      farm_owner_email: "",
      supervisor_name: "",
      supervisor_phone: "",
      farm_location: "",
    });

  } catch (e) {
    console.error(e);

    if (e.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
    }

    alert("Failed to save farm.");
  }
};



const handleDelete = async (farm_id) => {
  if (!window.confirm("Are you sure you want to delete this farm?")) return;

  try {
    const token = localStorage.getItem("token");

    await axios.delete(
      `${API_BASE}/api/delete_farm?farm_id=${farm_id}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );

    loadFarms(); // refresh list

  } catch (e) {
    console.error(e);

    if (e.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
    }

    alert("Failed to delete farm.");
  }
};



  return (
    <div className="farms-wrapper">
      <header className="farms-header">
        <h1 className="farms-title">Farms</h1>
        <button className="btn-primary" onClick={() => setShowModal(true)}>
          + Add New Farm
        </button>
      </header>
      <div className="farm-search-bar">
        <div className="search-input-wrapper">
          <svg className="search-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            className="search-input"
            placeholder="Search farms..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <section className="farms-content">
        {farms.length === 0 ? (
          <div className="empty-state-card">
            <div className="empty-icon">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                <polyline points="9 22 9 12 15 12 15 22"></polyline>
              </svg>
            </div>
            <p className="empty-text">No farms added yet</p>
            <p className="empty-subtext">Get started by adding your first farm to the dashboard.</p>
          </div>
        ) : (
          <div className="farm-list">
            {filteredFarms.map((farm) => (
              <div
                key={farm.farm_id}
                className="farm-card"
                onClick={(e) => {
                  if (e.target.closest(".action-btn")) {
                    return;
                  }
                  navigate(`/farm/${farm.farm_id}`);
                }}
              >
                {/* ---------- Card Header ---------- */}
                <div className="farm-card-header">
                  <h3 className="farm-name">{farm.farm_name}</h3>
                  <div className="card-actions">
                    <button
                      className="action-btn edit-hover"
                      title="Edit Farm"
                      onClick={() => {
                        setForm({
                          farm_name: farm.farm_name || "",
                          farm_owner_name: farm.farm_owner_name || "",
                          farm_owner_phone: farm.farm_owner_phone || "",
                          farm_owner_email: farm.farm_owner_email || "",
                          supervisor_name: farm.supervisor_name || "",
                          supervisor_phone: farm.supervisor_phone || "",
                          farm_location: farm.farm_location || "",
                        });
                        setEditingFarmId(farm.farm_id);
                        setShowModal(true);
                      }}
                    >
                      <svg
                        className="action-icon"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
                        />
                      </svg>
                    </button>
                    <button
                      className="action-btn delete-hover"
                      title="Delete Farm"
                      onClick={() => handleDelete(farm.farm_id)}
                    >
                      <svg
                        className="action-icon"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                        />
                      </svg>
                    </button>
                  </div>
                </div>

                {/* ---------- Card Body ---------- */}
                <div className="card-body">
                  {/* Primary Info: Farm Owner */}
                  <div className="owner-section">
                    <span className="owner-label">Farm Owner</span>
                    <span className="owner-name">
                      {farm.farm_owner_name || "—"}
                    </span>
                    <div className="owner-detail">
                      <svg
                        className="info-icon"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"
                        />
                      </svg>
                      {farm.farm_owner_phone || "No phone"}
                    </div>
                    {farm.farm_owner_email && (
                      <div className="owner-detail">
                        <svg
                          className="info-icon"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                          />
                        </svg>
                        {farm.farm_owner_email}
                      </div>
                    )}
                  </div>

                  {/* Secondary Info: Supervisor & Location */}
                  <div className="secondary-info">
                    <div className="info-row">
                      <svg
                        className="info-icon"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                        />
                      </svg>
                      <span>
                        Supervisor: {farm.supervisor_name || "N/A"}
                      </span>
                    </div>

                    <div className="info-row">
                      <svg
                        className="info-icon"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                        />
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                        />
                      </svg>
                      <span>{farm.farm_location || "Unknown"}</span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

        )}
      </section>

      {/* Add Farm Modal */}
      {showModal && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <h2 className="modal-title">
              {editingFarmId ? "Edit Farm" : "Add New Farm"}
            </h2>

            <div className="form-stack">

              {/* 🔹 Farm Name */}
              <div className="form-group">
                <label className="form-label">Farm Name</label>
                <input
                  className="form-input"
                  placeholder="e.g. Green Valley Ranch"
                  value={form.farm_name}
                  onChange={(e) => setForm({ ...form, farm_name: e.target.value })}
                  autoFocus
                />
              </div>

              {/* 🔹 Farm Owner Name */}
              <div className="form-group">
                <label className="form-label">Farm Owner Name</label>
                <input
                  className="form-input"
                  placeholder="e.g. John Doe"
                  value={form.farm_owner_name}
                  onChange={(e) =>
                    setForm({ ...form, farm_owner_name: e.target.value })
                  }
                />
              </div>

              {/* 🔹 Farm Owner Phone */}
              <div className="form-group">
                <label className="form-label">Farm Owner Phone</label>
                <input
                  className="form-input"
                  type="tel"
                  placeholder="+91 9876543210"
                  value={form.farm_owner_phone}
                  onChange={(e) =>
                    setForm({ ...form, farm_owner_phone: e.target.value })
                  }
                />
              </div>

              {/* 🔹 Farm Owner Email */}
              <div className="form-group">
                <label className="form-label">Farm Owner Email</label>
                <input
                  className="form-input"
                  type="email"
                  placeholder="owner@example.com"
                  value={form.farm_owner_email}
                  onChange={(e) =>
                    setForm({ ...form, farm_owner_email: e.target.value })
                  }
                />
              </div>

              {/* 🔹 Supervisor Name */}
              <div className="form-group">
                <label className="form-label">Supervisor Name</label>
                <input
                  className="form-input"
                  placeholder="e.g. Michael Scott"
                  value={form.supervisor_name}
                  onChange={(e) =>
                    setForm({ ...form, supervisor_name: e.target.value })
                  }
                />
              </div>

              {/* 🔹 Supervisor Phone */}
              <div className="form-group">
                <label className="form-label">Supervisor WhatsApp</label>
                <input
                  className="form-input"
                  type="tel"
                  placeholder="+91 90000 00000"
                  value={form.supervisor_phone}
                  onChange={(e) =>
                    setForm({ ...form, supervisor_phone: e.target.value })
                  }
                />
              </div>

              {/* 🔹 Farm Location */}
              <div className="form-group">
                <label className="form-label">Location</label>
                <input
                  className="form-input"
                  placeholder="e.g. Karjat - Pune"
                  value={form.farm_location}
                  onChange={(e) =>
                    setForm({ ...form, farm_location: e.target.value })
                  }
                />
              </div>
            </div>

            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleSave}>
                {editingFarmId ? "Save Changes" : "Save Farm"}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
