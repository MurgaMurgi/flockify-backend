import React, { useEffect, useState } from "react";
import "./PreviousBatches.css";
import axios from "axios";
import { useNavigate } from "react-router-dom";

export default function PreviousBatches() {
  const [batches, setBatches] = useState([]);
  const API_BASE = import.meta.env.VITE_API_BASE;

  const navigate = useNavigate();

 useEffect(() => {
  async function fetchBatches() {
    try {
      const token = localStorage.getItem("token");

      if (!token) {
        console.error("No token found");
        return;
      }

      const res = await axios.get(
        `${API_BASE}/api/batches/completed`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      setBatches(res.data.batches || []);
      console.log(res.data.batches);

    } catch (err) {
      console.error("Failed to fetch batches", err);

      if (err.response?.status === 401) {
        localStorage.clear();
        window.location.href = "/";
      }
    }
  }

  fetchBatches();
}, []);

  return (
    <div className="batch-container">
      <h2 className="title">Previous Batches</h2>

      <div className="batch-grid">
        {batches.map((batch) => (
          
          <div
            key={batch.batch_id}
            className="batch-card"
            onClick={() => navigate(`/batch/${batch.batch_id}`)}
            style={{ cursor: "pointer" }}
          >

            <div className="batch-header">
              <h3>Batch #{batch.batch_id}</h3>
            </div>

            <p><strong>Farm:</strong> {batch.farm_name}</p>
            <p><strong>Shed:</strong> {batch.shed_number}</p>

            <p><strong>Bird Category:</strong> {batch.bird_category}</p>
            <p><strong>Breed:</strong> {batch.bird_breed}</p>

            <p><strong>Placed:</strong> {batch.placement_date}</p>
            <p><strong>Depleted:</strong> {batch.depletion_date}</p>

            <p><strong>Initial Birds:</strong> {batch.initial_bird_count}</p>
            <p><strong>Final Birds:</strong> {batch.final_bird_count}</p>

            {batch.notes && (
              <p className="notes"><strong>Notes:</strong> {batch.notes}</p>
            )}
          </div>

        ))}
      </div>
    </div>
  );
}
