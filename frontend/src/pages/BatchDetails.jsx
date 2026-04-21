import React, { useEffect, useState } from "react";
import axios from "axios";
import { useParams } from "react-router-dom";
import "./BatchDetails.css";

export default function BatchDetails() {
  const { batch_id } = useParams();
  const API_BASE = import.meta.env.VITE_API_BASE;


  const [batch, setBatch] = useState(null);
  const [dailyEntries, setDailyEntries] = useState([]);
  const [eggRecords, setEggRecords] = useState([]);
  const [weeklyEntries, setWeeklyEntries] = useState([]);

  const [activeTab, setActiveTab] = useState("daily"); // daily | eggs | weekly

useEffect(() => {
  async function fetchDetails() {
    try {
      const token = localStorage.getItem("token");

      if (!token) {
        localStorage.clear();
        window.location.href = "/";
        return;
      }

      const res = await axios.get(
        `${API_BASE}/api/batches/details?batch_id=${batch_id}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      setBatch(res.data.batch);
      setDailyEntries(res.data.daily_entries || []);
      setEggRecords(res.data.egg_records || []);
      setWeeklyEntries(res.data.weekly_entries || []);

    } catch (err) {
      console.error("Failed to fetch batch details", err.response?.data || err);

      if (err.response?.status === 401) {
        localStorage.clear();
        window.location.href = "/";
      }
    }
  }

  fetchDetails();
}, [batch_id]);


  if (!batch) return <h3>Loading batch details...</h3>;

  // --------------------------
  // ⭐ SUMMARY CALCULATIONS
  // --------------------------

  const totalMortality = dailyEntries.reduce((s, e) => s + (e.mortality || 0), 0);
  const totalCulling = dailyEntries.reduce((s, e) => s + (e.culling || 0), 0);
  const totalFeed = dailyEntries.reduce((s, e) => s + (e.feed_consumption_kg || 0), 0);
  const totalWater = dailyEntries.reduce((s, e) => s + (e.water_consumed_ltrs || 0), 0);

  const totalGoodEggs = eggRecords.reduce((s, e) => s + (e.good_eggs || 0), 0);
  const totalFloorEggs = eggRecords.reduce((s, e) => s + (e.floor_eggs || 0), 0);
  const totalBroken = eggRecords.reduce((s, e) => s + (e.broken_cracked_eggs || 0), 0);
  const totalMishapped = eggRecords.reduce((s, e) => s + (e.mishapped_eggs || 0), 0);

  const totalEggs = totalGoodEggs + totalFloorEggs;
  const totalWastage = totalBroken + totalMishapped;

  const finalWeek = weeklyEntries[weeklyEntries.length - 1];
  const avgBirdWeight = finalWeek?.avg_bird_weight || 0;

  // starting weight approximation
  const startingWeight = 0.04;
  const totalWeightGain =
    batch.final_bird_count * avgBirdWeight -
    batch.initial_bird_count * startingWeight;

  const FCR =
    totalWeightGain > 0
      ? (totalFeed / totalWeightGain).toFixed(2)
      : "N/A";

  return (
    <div className="details-container">

      {/* Header */}
      <h2>Batch #{batch.batch_id} — Details</h2>

      {/* ⭐ SUMMARY CARDS */}


      {/* Batch Info Card */}
      <div className="details-card">
        <p><strong>Farm:</strong> {batch.farm_name}</p>
        <p><strong>Shed:</strong> {batch.shed_number}</p>
        <p><strong>Bird Category:</strong> {batch.bird_category}</p>
        <p><strong>Breed:</strong> {batch.bird_breed}</p>
        <p><strong>Placed on:</strong> {batch.placement_date}</p>
        <p><strong>Depleted on:</strong> {batch.depletion_date}</p>
        <p><strong>Initial Birds:</strong> {batch.initial_bird_count}</p>
        <p><strong>Final Birds:</strong> {batch.final_bird_count}</p>
        {batch.notes && <p><strong>Notes:</strong> {batch.notes}</p>}
      </div>
      <div className="summary-grid">

        <div className="summary-card">
          <h3>Total Mortality</h3>
          <p>{totalMortality}</p>
        </div>

        <div className="summary-card">
          <h3>Total Culling</h3>
          <p>{totalCulling}</p>
        </div>

        <div className="summary-card">
          <h3>Total Eggs</h3>
          <p>{totalEggs}</p>
        </div>

        <div className="summary-card">
          <h3>Total Wastage</h3>
          <p>{totalWastage}</p>
        </div>

        <div className="summary-card">
          <h3>Avg Bird Weight</h3>
          <p>{avgBirdWeight} kg</p>
        </div>

        <div className="summary-card">
          <h3>Feed Consumed</h3>
          <p>{totalFeed} kg</p>
        </div>

        <div className="summary-card">
          <h3>Water Consumed</h3>
          <p>{totalWater} L</p>
        </div>

        <div className="summary-card">
          <h3>FCR</h3>
          <p>{FCR}</p>
        </div>

      </div>
      {/* Tabs */}
      <div className="tabs">
        <button className={activeTab === "daily" ? "active" : ""} onClick={() => setActiveTab("daily")}>
          Daily Entries
        </button>

        <button className={activeTab === "eggs" ? "active" : ""} onClick={() => setActiveTab("eggs")}>
          Egg Collection
        </button>

        <button className={activeTab === "weekly" ? "active" : ""} onClick={() => setActiveTab("weekly")}>
          Weekly Entries
        </button>
      </div>

      {/* TAB CONTENT */}

      {/* DAILY ENTRIES TABLE */}
      {activeTab === "daily" && (
        <table className="excel-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Mortality</th>
              <th>Culling</th>
              <th>Feed (kg)</th>
              <th>Water (L)</th>
              <th>Temp</th>
              <th>Lighting Hrs</th>
              <th>Med Notes</th>
            </tr>
          </thead>
          <tbody>
            {dailyEntries.map((e) => (
              <tr key={e.entry_id}>
                <td>{e.entry_date}</td>
                <td>{e.mortality}</td>
                <td>{e.culling}</td>
                <td>{e.feed_consumption_kg}</td>
                <td>{e.water_consumed_ltrs}</td>
                <td>{e.temperature}</td>
                <td>{e.lighting_hours}</td>
                <td>{e.medical_notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* EGGS TABLE */}
      {activeTab === "eggs" && (
        <table className="excel-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Good Eggs</th>
              <th>Floor Eggs</th>
              <th>Broken</th>
              <th>Mishapped</th>
              <th>Wastage</th>
            </tr>
          </thead>
          <tbody>
            {eggRecords.map((e) => (
              <tr key={e.egg_id}>
                <td>{e.collection_date}</td>
                <td>{e.good_eggs}</td>
                <td>{e.floor_eggs}</td>
                <td>{e.broken_cracked_eggs}</td>
                <td>{e.mishapped_eggs}</td>
                <td>{e.wastage}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* WEEKLY TABLE */}
      {activeTab === "weekly" && (
        <table className="excel-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Avg Weight</th>
              <th>Ammonia</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {weeklyEntries.map((e) => (
              <tr key={e.weekly_id}>
                <td>{e.entry_date}</td>
                <td>{e.avg_bird_weight}</td>
                <td>{e.ammonia_level}</td>
                <td>{e.weekly_notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

    </div>
  );
}
