import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import "./FarmDetails.css";
import "./farms.css";

export default function FarmDetails() {
  const { farm_id } = useParams();
  const navigate = useNavigate();



  const [showEditModal, setShowEditModal] = useState(false);
  const [editShed, setEditShed] = useState(null);

  const openEditShedModal = (shed) => {
    setEditShed({ ...shed });  // clone the shed data
    setShowEditModal(true);
  };


  const [farm, setFarm] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [shed, setShed] = useState({
    shed_number: "",
    shed_type: "",
    bird_category: "",
    bird_breed: "",
    initial_bird_count: "",
    area_value: "",
    area_unit: "sqft",
    open_area_value: "",
    open_area_unit: "sqft",
    placement_date: "",
    notes: "",
    // Equipment
    no_of_feeders: "",
    no_of_water_nipples: "",
    // Perch
    perch_angle: "",
    perch_length_value: "",
    perch_length_unit: "ft",
  });

  // Filter State
  const [openMenuShedId, setOpenMenuShedId] = useState(null);
const [showDeleteModal, setShowDeleteModal] = useState(false);
const [shedToDelete, setShedToDelete] = useState(null);


  const [showCullModal, setShowCullModal] = useState(false);

  const API_BASE = import.meta.env.VITE_API_BASE;


  // -------------------------
  // Load farm details
  // -------------------------
const loadFarm = async () => {
  try {
    const token = localStorage.getItem("token");

    if (!token) {
      console.error("No token found");
      return;
    }

    const config = {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    };

    const res = await axios.get(
      `${API_BASE}/api/get_farm_details?farm_id=${farm_id}`,
      config
    );

    setFarm(res.data.data);
    console.log(res.data.data);

  } catch (err) {
    console.error("Failed to load farm details:", err);

    if (err.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
    }

    alert("Failed to load farm details.");
  }
};


  useEffect(() => {
    loadFarm();
  }, [farm_id]);

  // -------------------------
  // HANDLE ADD SHED
  // -------------------------
const handleAddShed = async () => {
  try {
    const token = localStorage.getItem("token");

    await axios.post(
      `${API_BASE}/api/add_shed`,
      {
        farm_id: farm_id, // send in body, not query
        shed_number: shed.shed_number,
        shed_type: shed.shed_type,
        bird_category: shed.bird_category,
        bird_breed: shed.bird_breed,
        initial_bird_count: Number(shed.initial_bird_count),
        area_value: Number(shed.area_value),
        area_unit: shed.area_unit,
        open_area_value: shed.open_area_value ? Number(shed.open_area_value) : null,
        open_area_unit: shed.open_area_unit || "sqft",
        placement_date: shed.placement_date || null,
        notes: shed.notes || null,
        no_of_feeders: shed.no_of_feeders ? Number(shed.no_of_feeders) : null,
        no_of_water_nipples: shed.no_of_water_nipples ? Number(shed.no_of_water_nipples) : null,
        perch_angle: shed.perch_angle ? Number(shed.perch_angle) : null,
        perch_length_value: shed.perch_length_value ? Number(shed.perch_length_value) : null,
        perch_length_unit: shed.perch_length_unit || "ft",
      },
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );

    setShowModal(false);
    loadFarm();

  } catch (err) {
    console.error(err);

    if (err.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
    }

    alert("Failed to add shed");
  }
};



  if (!farm) {
    return (
      <div className="farm-details-page">
        <div style={{ textAlign: "center", marginTop: 40, color: "var(--text-secondary)" }}>
          Loading farm details...
        </div>
      </div>
    );
  }

  // Convert placement date → Date object

  const totalInitialBirds = farm.sheds
    ? farm.sheds.reduce((sum, shed) => sum + (shed.initial_bird_count || 0), 0)
    : 0;
  const totalLiveBirds = farm.metrics?.total_live_birds || 0;

  const openEditBirdCountModal = (shed) => {
    setEditShed(shed);
    setShowEditModal(true);
  };



  const saveEditedShed = async () => {
  try {
    const token = localStorage.getItem("token");

    await axios.post(
      `${API_BASE}/api/edit_shed`,
      editShed,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );

    setShowEditModal(false);
    loadFarm();

  } catch (err) {
    console.error(err);

    if (err.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
      return;
    }

    alert("Failed to update shed");
  }
};

const handleCullBatch = async () => {
  try {
    const token = localStorage.getItem("token");

    const config = {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    };

    const res = await axios.post(
      `${API_BASE}/api/admin/deplete_batch`,
      {
        shed_id: editShed.shed_id,
      },
      config
    );

    alert("Batch successfully depleted.");

    setShowCullModal(false);
    setShowEditModal(false);

    loadFarm();

  } catch (err) {
    console.error(err);

    if (err.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
    }

    alert("Failed to deplete batch.");
  }
};
async function handleDeleteShed(shed_id) {
  try {

    const token = localStorage.getItem("token");

    const res = await axios.delete(
      `${API_BASE}/api/sheds/delete`,
      {
        params: { shed_id },
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );

    if (res.data.status === "success") {
      alert("Shed deleted permanently.");
      window.location.reload();
    } else {
      alert(res.data.message);
    }

  } catch (err) {
    console.error("Delete error:", err);

    if (err.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
      return;
    }

    alert("Something went wrong while deleting this shed.");
  }
}


  return (
    <div className="farm-details-page">
      {/* ------------------ HEADER ------------------ */}
      <header className="farm-details-header">
        <div className="header-left">
          <button className="back-button" onClick={() => navigate("/farms")}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            Back to Farms
          </button>
          <h1 className="page-title">{farm.farm_name}</h1>
        </div>

        <button className="btn-primary" onClick={() => setShowModal(true)}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          Add Shed
        </button>
      </header>



      {/* ------------------ INFO & STATS LAYOUT ------------------ */}
      <div className="farm-info-container">

        {/* LEFT COLUMN: Main Farm Details */}
        <div className="details-card">
          <div className="card-header-bar">
            <h3 className="card-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.6 }}>
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                <polyline points="9 22 9 12 15 12 15 22"></polyline>
              </svg>
              Farm Overview
            </h3>
          </div>

          <div className="card-content">
            {/* 1. Primary: Owner Details */}
            <div className="owner-highlight">
              <div className="owner-name-large">
                {farm.farm_owner_name || "Unknown Owner"}
                <span className="badge-owner">Owner</span>
              </div>

              <div className="contact-grid">
                <div className="contact-item prominent">
                  <svg className="contact-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path>
                  </svg>
                  {farm.farm_owner_phone || "No Phone"}
                </div>
                {farm.farm_owner_email && (
                  <div className="contact-item">
                    <svg className="contact-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="22" y1="2" x2="11" y2="13"></line>
                      <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                    </svg>
                    {farm.farm_owner_email}
                  </div>
                )}
              </div>
            </div>

            {/* 2. Secondary: Supervisor & Location */}
            <div className="secondary-details">
              <div className="detail-group">
                <span className="detail-label">Supervisor</span>
                <div className="detail-value">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--text-muted)" }}>
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                  </svg>
                  {farm.supervisor_name || "N/A"}
                </div>
                <div style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginLeft: 24 }}>
                  {farm.supervisor_phone}
                </div>
              </div>

              <div className="detail-group">
                <span className="detail-label">Location</span>
                <div className="detail-value">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--text-muted)" }}>
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                    <circle cx="12" cy="10" r="3"></circle>
                  </svg>
                  {farm.farm_location || "Unknown"}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Stats / Quick Metrics */}
        <div className="details-card">
          <div className="card-header-bar">
            <h3 className="card-title">Live Metrics</h3>
          </div>
          <div className="metrics-grid">

            <div className="metric-item">
              <span className="metric-label">Total Sheds</span>
              <span className="metric-value">{farm.sheds?.length || 0}</span>
            </div>

            <div className="metric-item">
              <span className="metric-label">Initial Birds Placed</span>
              <span className="metric-value">
                {farm.metrics?.total_initial_birds?.toLocaleString() || "0"}
              </span>
            </div>

            <div className="metric-item">
              <span className="metric-label">Live Birds</span>
              <span className="metric-value" style={{ color: "#16a34a" }}>
                {totalLiveBirds.toLocaleString()}
              </span>
            </div>

          </div>

        </div>

      </div>

      {/* ------------------ SHEDS SECTION ------------------ */}
      <section className="sheds-section">
        <div className="sheds-header-row">
          <h2 className="sheds-title">Sheds & Capacity</h2>
        </div>

        {(!farm.sheds || farm.sheds.length === 0) ? (
          <div className="empty-sheds">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
              <path d="M3 21h18M5 21V7l8-4 8 4v14H5z" />
            </svg>
            <p style={{ fontWeight: 600 }}>No sheds added yet</p>
            <p style={{ fontSize: "0.9rem", color: "var(--text-secondary)" }}>
              Create a shed to manage flock capacity.
            </p>
          </div>
        ) : (
          <div className="shed-list">
            {farm.sheds.map((shed) => {

              // Calculate age
              const placed = shed.placement_date ? new Date(shed.placement_date) : null;
              let weeksSince = null;
              if (placed) {
                const diffMs = new Date() - placed;
                weeksSince = Math.floor(diffMs / (1000 * 60 * 60 * 24 * 7));
              }

              // Status
              let statusClass = shed.active_batch_id ? "badge-active" : "badge-inactive";
              let statusLabel = shed.active_batch_id ? "Active" : "Inactive";

              const p = (shed.shed_type || "").toLowerCase();

              const formattedDate = shed.placement_date
                ? new Date(shed.placement_date).toLocaleDateString('en-GB', {
                  day: 'numeric', month: 'short', year: 'numeric'
                })
                : "Not Set";

              return (
                <div key={shed.shed_id} className="shed-card-modern">

                  {/* --- HEADER --- */}
                  <div className="shed-modern-header">
                    <div className="header-top-row">
                      <div className="shed-identity">
                        <span className="shed-number-display">{shed.shed_number}</span>
                        <div className={`status-badge ${statusClass}`}>
                          {statusLabel}
                        </div>
                      </div>
                      <div className="shed-menu-wrapper">
  
  <button
    className="shed-menu-btn"
    onClick={(e) => {
      e.stopPropagation();
      setOpenMenuShedId(openMenuShedId === shed.shed_id ? null : shed.shed_id);
    }}
  >
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="1"></circle>
      <circle cx="19" cy="12" r="1"></circle>
      <circle cx="5" cy="12" r="1"></circle>
    </svg>
  </button>

  {openMenuShedId === shed.shed_id && (
    <div className="shed-dropdown-menu">
      <div className="shed-dropdown-item" onClick={() => openEditShedModal(shed)}>
        Edit Shed
      </div>
      <div className="shed-dropdown-item" onClick={() => {
        setEditShed(shed);
        setShowCullModal(true);
      }}>
        End Batch / Deplete
      </div>
      <div
  className="shed-dropdown-item danger"
  onClick={() => {
    setShedToDelete(shed);
    setShowDeleteModal(true);
    setOpenMenuShedId(null); // close the dropdown
  }}
>
  Delete Shed
</div>

    </div>
  )}

</div>

                    </div>

                    <div className="shed-tags-row">
                      <span className={`pill-tag pill-${p}`}>
                        {shed.shed_type?.replace("_", " ")}
                      </span>
                      <span className="pill-tag pill-neutral">{shed.bird_category}</span>
                      <span className="pill-tag pill-neutral">{shed.bird_breed}</span>
                    </div>
                  </div>

                  {/* --- SUMMARY ROW --- */}
                  <div className="shed-summary-hero">
                    <div className="hero-stat">
                      <span className="hero-val">{shed.initial_bird_count?.toLocaleString() ?? "0"}</span>
                      <span className="hero-lbl">Birds Placed</span>
                    </div>
                    <div className="hero-divider"></div>
                    <div className="hero-stat">
                      <span className="hero-val hero-live">
                        {shed.final_bird_count?.toLocaleString() ?? "—"}
                      </span>
                      <span className="hero-lbl">Current Birds</span>
                    </div>
                    <div className="hero-divider"></div>
                    <div className="hero-stat">
                      <span className="hero-val">{weeksSince ?? "—"}</span>
                      <span className="hero-lbl">Weeks Old</span>
                    </div>

                  </div>

                  {/* --- DETAILS (VERTICAL SECTIONS) --- */}
                  <div className="shed-details-container">

                    {/* 👉 CAPACITY & AREA */}
                    <div className="detail-section">
                      <h4 className="section-title">Capacity & Area</h4>
                      <div className="detail-row">
                        <span className="d-label">Inside Area</span>
                        <span className="d-value">{shed.area_value ? `${shed.area_value} ${shed.area_unit}` : "—"}</span>
                      </div>
                      {shed.shed_type === "free_range" && (
                        <div className="detail-row">
                          <span className="d-label">Open Area</span>
                          <span className="d-value">{shed.open_area_value ? `${shed.open_area_value} ${shed.open_area_unit}` : "—"}</span>
                        </div>
                      )}
                      <div className="detail-row">
                        <span className="d-label">Placed On</span>
                        <span className="d-value">{formattedDate}</span>
                      </div>
                    </div>

                    {/* 👉 EQUIPMENT */}
                    <div className="detail-section">
                      <h4 className="section-title">Equipment</h4>
                      <div className="detail-row">
                        <span className="d-label">Feeders</span>
                        <span className="d-value">{shed.no_of_feeders ?? "—"}</span>
                      </div>
                      <div className="detail-row">
                        <span className="d-label">Nipples</span>
                        <span className="d-value">{shed.no_of_water_nipples ?? "—"}</span>
                      </div>
                      <div className="detail-row">
                        <span className="d-label">Perch</span>
                        <span className="d-value">
                          {shed.perch_length_value ? `${shed.perch_length_value}${shed.perch_length_unit}` : "—"}
                          {shed.perch_angle ? ` @ ${shed.perch_angle}°` : ""}
                        </span>
                      </div>
                    </div>

                    {/* 👉 EFFICIENCY RATIOS */}
                    <div className="detail-section">
                      <h4 className="section-title">Efficiency Ratios</h4>
                      <div className="detail-row">
                        <span className="d-label">Density (sqft)</span>
                        <span className="d-value">
                          {shed.density_inside ? shed.density_inside.toFixed(2) : "—"}
                        </span>
                      </div>

                      <div className="detail-row">
                        <span className="d-label">Birds / Feeder</span>
                        <span className="d-value">{shed.birds_per_feeder?.toFixed(1) ?? "—"}</span>
                      </div>
                      <div className="detail-row">
                        <span className="d-label">Birds / Nipple</span>
                        <span className="d-value">{shed.birds_per_nipple?.toFixed(1) ?? "—"}</span>
                      </div>
                      <div className="detail-row">
                        <span className="d-label">Birds / ft Perch</span>
                        <span className="d-value">{shed.birds_per_perch_length?.toFixed(1) ?? "—"}</span>
                      </div>
                    </div>

                  </div>

                  {/* Data Entry button — only for active batches */}
                  {shed.active_batch_id && (
                    <div className="shed-data-entry-row">
                      <button
                        className="btn-data-entry"
                        onClick={() =>
                          navigate(`/farm/${farm_id}/shed/${shed.shed_id}/portal`)
                        }
                      >
                        📋 Data Entry
                      </button>
                    </div>
                  )}
                </div>

              );
            })}
          </div>
        )}
      </section>

    {showDeleteModal && shedToDelete && (
  <div className="modal-backdrop">
    <div className="modal-card small-modal">

      <h2 className="modal-title-center">Delete Shed</h2>

      <p className="modal-description">
        Are you sure you want to <b>permanently delete</b> 
        shed <strong>{shedToDelete.shed_number}</strong>?
        <br /><br />
        This will permanently remove:
        <ul>
          <li>All batches</li>
          <li>Daily entries</li>
          <li>Egg collections</li>
          <li>Weekly entries</li>
          <li>Bird stock history</li>
        </ul>
        This action <b>cannot</b> be undone.
      </p>

      <div className="modal-actions-bar">

        <button
          className="btn-secondary"
          onClick={() => setShowDeleteModal(false)}
        >
          Cancel
        </button>

        <button
          className="btn-danger"
          onClick={() => {
            handleDeleteShed(shedToDelete.shed_id);
            setShowDeleteModal(false);
          }}
        >
          Delete Permanently
        </button>

      </div>

    </div>
  </div>
)}



      {showEditModal && editShed && (
        <div className="modal-backdrop">
          <div className="modal-card large-modal">

            <div className="modal-header-strip">
              <h2 className="modal-title-left">Edit Shed</h2>
            </div>

            <div className="modal-form-body">

              {/* SHED IDENTITY */}
              <div className="form-section">
                <div className="section-header">
                  <span className="section-label">Shed Identity</span>
                </div>

                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Shed Number / Name</label>
                    <input
                      className="form-input"
                      value={editShed.shed_number}
                      onChange={(e) =>
                        setEditShed({ ...editShed, shed_number: e.target.value })
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Shed Type</label>
                    <select
                      className="form-input"
                      value={editShed.shed_type}
                      onChange={(e) =>
                        setEditShed({ ...editShed, shed_type: e.target.value })
                      }
                    >
                      <option value="free_range">Free Range</option>
                      <option value="cage_free">Cage Free</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* BIRD DETAILS */}
              <div className="form-section">
                <div className="section-header">
                  <span className="section-label">Bird Details</span>
                </div>

                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Bird Category</label>
                    <select
                      className="form-input"
                      value={editShed.bird_category}
                      onChange={(e) =>
                        setEditShed({ ...editShed, bird_category: e.target.value })
                      }
                    >
                      <option value="broiler">Broiler</option>
                      <option value="layer">Layer</option>
                      <option value="desi">Desi</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Bird Breed</label>
                    <select
                      className="form-input"
                      value={editShed.bird_breed}
                      onChange={(e) =>
                        setEditShed({ ...editShed, bird_breed: e.target.value })
                      }
                    >
                      <option value="Hy-Line">Hy-Line</option>
                      <option value="BV 380">BV 380</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* CAPACITY */}
              <div className="form-section">
                <div className="section-header">
                  <span className="section-label">Capacity</span>
                </div>

                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Initial Bird Count</label>
                    <input
                      type="number"
                      className="form-input"
                      value={editShed.initial_bird_count}
                      onChange={(e) =>
                        setEditShed({ ...editShed, initial_bird_count: Number(e.target.value) })
                      }
                    />
                  </div>


                  <div className="form-group">
                    <label className="form-label">Inside Area</label>
                    <div className="input-group-row">
                      <input
                        type="number"
                        className="form-input"
                        value={editShed.area_value}
                        onChange={(e) =>
                          setEditShed({ ...editShed, area_value: Number(e.target.value) })
                        }
                      />
                      <select
                        className="form-input"
                        value={editShed.area_unit}
                        onChange={(e) =>
                          setEditShed({ ...editShed, area_unit: e.target.value })
                        }
                      >
                        <option value="sqft">sqft</option>
                        <option value="sqm">sqm</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* OPEN AREA (only for free range) */}
                {editShed.shed_type === "free_range" && (
                  <div className="form-group full-width">
                    <label className="form-label">Open Area</label>
                    <div className="input-group-row">
                      <input
                        className="form-input"
                        value={editShed.open_area_value}
                        onChange={(e) =>
                          setEditShed({ ...editShed, open_area_value: Number(e.target.value) })
                        }
                      />

                      <select
                        className="form-input"
                        value={editShed.open_area_unit}
                        onChange={(e) =>
                          setEditShed({ ...editShed, open_area_unit: e.target.value })
                        }
                      >
                        <option value="sqft">sqft</option>
                        <option value="sqm">sqm</option>
                      </select>
                    </div>
                  </div>
                )}
              </div>

              {/* EQUIPMENT */}
              <div className="form-section">
                <div className="section-header">
                  <span className="section-label">Equipment</span>
                </div>

                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Feeders</label>
                    <input
                      type="number"
                      className="form-input"
                      value={editShed.no_of_feeders}
                      onChange={(e) =>
                        setEditShed({ ...editShed, no_of_feeders: Number(e.target.value) })
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Water Nipples</label>
                    <input
                      type="number"
                      className="form-input"
                      value={editShed.no_of_water_nipples}
                      onChange={(e) =>
                        setEditShed({ ...editShed, no_of_water_nipples: Number(e.target.value) })
                      }
                    />
                  </div>
                </div>
              </div>

              {/* PERCH */}
              <div className="form-section">
                <div className="section-header">
                  <span className="section-label">Perch</span>
                </div>

                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Angle</label>
                    <input
                      type="number"
                      className="form-input"
                      value={editShed.perch_angle}
                      onChange={(e) =>
                        setEditShed({ ...editShed, perch_angle: Number(e.target.value) })
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Length</label>
                    <div className="input-group-row">
                      <input
                        type="number"
                        className="form-input"
                        value={editShed.perch_length_value}
                        onChange={(e) =>
                          setEditShed({ ...editShed, perch_length_value: Number(e.target.value) })
                        }
                      />
                      <select
                        className="form-input"
                        value={editShed.perch_length_unit}
                        onChange={(e) =>
                          setEditShed({ ...editShed, perch_length_unit: e.target.value })
                        }
                      >
                        <option value="ft">ft</option>
                        <option value="m">m</option>
                      </select>
                    </div>
                  </div>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Placement Date</label>
                <input
                  type="date"
                  className="form-input"
                  value={editShed.placement_date ?? ""}
                  onChange={(e) =>
                    setEditShed({ ...editShed, placement_date: e.target.value })
                  }
                />
              </div>


              {/* NOTES */}
              <div className="form-section">
                <div className="section-header">
                  <span className="section-label">Notes</span>
                </div>

                <textarea
                  className="form-input"
                  value={editShed.notes}
                  onChange={(e) =>
                    setEditShed({ ...editShed, notes: e.target.value })
                  }
                ></textarea>
              </div>

            </div>

            {/* ACTIONS */}
            <div className="modal-actions-bar">
              <button className="btn-secondary" onClick={() => setShowEditModal(false)}>
                Cancel
              </button>
              <button className="btn-primary" onClick={saveEditedShed}>
                Save Changes
              </button>
            </div>
            
          </div>
        </div>
      )}
      {showCullModal && (
        <div className="modal-backdrop">
          <div className="modal-card small-modal">

            <h2 className="modal-title-center">Confirm Batch Depletion</h2>

            <p className="modal-description">
              Are you sure you want to **end the current flock** for
              <strong> {editShed.shed_number}</strong>?
              <br /><br />
              This action will:
              <ul>
                <li>Mark the batch as <b>depleted</b></li>
                <li>Record the final closing birds</li>
                <li>Reset the shed’s bird count to 0</li>
              </ul>
              This cannot be undone.
            </p>

            <div className="modal-actions-bar">
              <button
                className="btn-secondary"
                onClick={() => setShowCullModal(false)}
              >
                Cancel
              </button>

              <button
                className="btn-danger"
                onClick={handleCullBatch}
              >
                Yes, End Batch
              </button>
            </div>

          </div>
        </div>
      )}





      {/* ------------------ ADD SHED MODAL ------------------ */}
      {showModal && (
        <div className="modal-backdrop">
          <div className="modal-card large-modal">

            {/* Modal Header */}
            <div className="modal-header-strip">
              <h2 className="modal-title-left">Add New Shed</h2>
            </div>

            {/* Modal Body */}
            <div className="modal-form-body">

              {/* SECTION 1: SHED IDENTITY */}
              <div className="form-section">
                <div className="section-header">
                  <svg className="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m8-2a2 2 0 100-4 2 2 0 000 4z" />
                  </svg>
                  <span className="section-label">Shed Identity</span>
                </div>
                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Shed Number / Name <span style={{ color: "red" }}>*</span></label>
                    <input
                      className="form-input"
                      placeholder="e.g. Shed A"
                      value={shed.shed_number}
                      onChange={(e) => setShed({ ...shed, shed_number: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Shed Type</label>
                    <select
                      className="form-input"
                      value={shed.shed_type}
                      onChange={(e) => setShed({ ...shed, shed_type: e.target.value })}
                    >
                      <option value="">Select Type</option>
                      <option value="free_range">Free Range</option>
                      <option value="cage_free">Cage Free</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* SECTION 2: BIRD DETAILS */}
              <div className="form-section">
                <div className="section-header">
                  <svg className="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
                  </svg>
                  <span className="section-label">Bird Details</span>
                </div>
                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Bird Category</label>
                    <select
                      className="form-input"
                      value={shed.bird_category}
                      onChange={(e) => setShed({ ...shed, bird_category: e.target.value })}
                    >
                      <option value="">Select Category</option>
                      <option value="broiler">Broiler</option>
                      <option value="layer">Layer</option>
                      <option value="desi">Desi / Nati</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Bird Breed</label>
                    <select
                      className="form-input"
                      value={shed.bird_breed}
                      onChange={(e) => setShed({ ...shed, bird_breed: e.target.value })}
                    >
                      <option value="">Select Breed</option>
                      <option value="Hy-Line">Hy-Line</option>
                      <option value="BV 380">BV 380</option>
                    </select>
                  </div>

                </div>
              </div>

              {/* SECTION 3: CAPACITY & AREA */}
              <div className="form-section">
                <div className="section-header">
                  <svg className="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                  </svg>
                  <span className="section-label">Capacity & Area</span>
                </div>
                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Initial Bird Count</label>
                    <input
                      type="number"
                      className="form-input"
                      placeholder="e.g. 5000"
                      value={shed.initial_bird_count}
                      min="0"
                      onChange={(e) => setShed({
                        ...shed,
                        initial_bird_count: e.target.value
                      })}
                    />

                  </div>
                  <div className="form-group">
                    <label className="form-label">Area Size</label>
                    <div className="input-group-row">
                      <input
                        type="number"
                        className="form-input"
                        placeholder="e.g. 1200"
                        value={shed.area_value}
                        min="0"
                        onChange={(e) => {
                          const value = Math.max(0, Number(e.target.value));
                          setShed({ ...shed, area_value: value });
                        }}
                      />
                      <select
                        className="form-input"
                        value={shed.area_unit}
                        onChange={(e) => setShed({ ...shed, area_unit: e.target.value })}
                      >
                        <option value="sqft">sqft</option>
                        <option value="sqm">sqm</option>
                      </select>
                    </div>
                  </div>
                  {shed.shed_type === "free_range" && (
                    <div className="form-group full-width">
                      <label className="form-label">Open Area Size (Outside Area)</label>
                      <div className="input-group-row">
                        <input
                          type="number"
                          className="form-input"
                          placeholder="e.g. 2000"
                          value={shed.open_area_value}
                          min="0"
                          onChange={(e) =>
                            setShed({
                              ...shed,
                              open_area_value: Number(e.target.value)
                            })
                          }
                        />

                        <select
                          className="form-input"
                          value={shed.open_area_unit}
                          onChange={(e) =>
                            setShed({ ...shed, open_area_unit: e.target.value })
                          }
                        >
                          <option value="sqft">sqft</option>
                          <option value="sqm">sqm</option>
                        </select>
                      </div>
                    </div>
                  )}


                </div>
              </div>

              {/* SECTION: EQUIPMENT DETAILS */}
              <div className="form-section">
                <div className="section-header">
                  <svg className="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  <span className="section-label">Equipment Details</span>
                </div>
                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Number of Feeders</label>
                    <input
                      type="number"
                      className="form-input"
                      placeholder="e.g. 50"
                      value={shed.no_of_feeders}
                      min="0"
                      step="1"
                      onChange={(e) => {
                        const value = Math.max(0, Number(e.target.value));
                        setShed({ ...shed, no_of_feeders: value });
                      }}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Number of Water Nipples</label>
                    <input
                      type="number"
                      className="form-input"
                      placeholder="e.g. 200"
                      value={shed.no_of_water_nipples}
                      min="0"
                      step="1"
                      onChange={(e) => {
                        const value = Math.max(0, Number(e.target.value));
                        setShed({ ...shed, no_of_water_nipples: value });
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* SECTION: PERCH DETAILS */}
              <div className="form-section">
                <div className="section-header">
                  <svg className="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-5 5-4-4-6 6" />
                  </svg>
                  <span className="section-label">Perch Details</span>
                </div>
                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Perch Angle (°)</label>
                    <input
                      type="number"
                      className="form-input"
                      placeholder="e.g. 45"
                      value={shed.perch_angle}
                      min="0"
                      step="1"
                      onChange={(e) => {
                        const value = Math.max(0, Number(e.target.value));
                        setShed({ ...shed, perch_angle: value });
                      }}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Perch Length</label>
                    <div className="input-group-row">
                      <input
                        type="number"
                        className="form-input"
                        placeholder="e.g. 12"
                        value={shed.perch_length_value}
                        min="0"
                        step="0.1"
                        onChange={(e) => {
                          const value = Math.max(0, Number(e.target.value));
                          setShed({ ...shed, perch_length_value: value });
                        }}
                      />
                      <select
                        className="form-input"
                        value={shed.perch_length_unit}
                        onChange={(e) => setShed({ ...shed, perch_length_unit: e.target.value })}
                      >
                        <option value="ft">ft</option>
                        <option value="m">m</option>
                      </select>
                    </div>
                  </div>
                </div>
              </div>


              {/* SECTION 4: STATUS & NOTES */}
              <div className="form-section">
                <div className="section-header">
                  <svg className="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  <span className="section-label">Placement & Status</span>
                </div>
                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Placement Date</label>
                    <input
                      type="date"
                      className="form-input"
                      value={shed.placement_date}
                      onChange={(e) => setShed({ ...shed, placement_date: e.target.value })}
                    />
                  </div>
                  <div className="form-group full-width">
                    <label className="form-label">Additional Notes</label>
                    <textarea
                      className="form-input"
                      placeholder="Any specific remarks about this shed..."
                      value={shed.notes}
                      onChange={(e) => setShed({ ...shed, notes: e.target.value })}
                    ></textarea>
                  </div>
                </div>
              </div>

            </div>

            {/* Modal Actions */}
            <div className="modal-actions-bar">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleAddShed}>
                Add Shed
              </button>
            </div>

          </div>
        </div>
      )}

    </div>
  );
}
