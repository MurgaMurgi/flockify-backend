import React, { useEffect, useState, useRef, useCallback } from "react";
import axios from "axios";
import { FileText } from "lucide-react";
import "./dashboard.css";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { FaWarehouse } from "react-icons/fa";
import { FaChartBar } from "react-icons/fa";
import { FaDownload } from "react-icons/fa";



// ← ADD THIS


const API_BASE = import.meta.env.VITE_API_BASE;


export default function ActivityHistory() {
  const [admin, setAdmin] = useState(null);

  const [farms, setFarms] = useState([]);
  const [selectedFarm, setSelectedFarm] = useState("");

  const [sheds, setSheds] = useState([]);
  const [entries, setEntries] = useState({}); // date → shedNo → { daily, egg }

  const [eggSummary, setEggSummary] = useState(null);
  const [waterData, setWaterData] = useState([]);
  const [feedWaterData, setFeedWaterData] = useState([]);
  const [tempWaterMortData, setTempWaterMortData] = useState([]);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editEntry, setEditEntry] = useState(null);
  const [editEggModalOpen, setEditEggModalOpen] = useState(false);
  const [editEggEntry, setEditEggEntry] = useState(null);

  const [globalSummary, setGlobalSummary] = useState(null);
  const [weeklyAmmonia, setWeeklyAmmonia] = useState([]);
  const [dailySummary, setDailySummary] = useState([]);



  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState({});
  const [missingToday, setMissingToday] = useState([]);
  const [birdSummary, setBirdSummary] = useState(null);
  const [byShed, setByShed] = useState([]);
  const [fcrData, setFcrData] = useState([]);

  const [globalProductivity, setGlobalProductivity] = useState([]);
  const [globalFcr, setGlobalFcr] = useState([]);
  const [globalMortCull, setGlobalMortCull] = useState([]);
  const [globalWater, setGlobalWater] = useState([]);
  const [globalFeedWater, setGlobalFeedWater] = useState([]);
  const [globalTempWaterMort, setGlobalTempWaterMort] = useState([]);




  const [productivityData, setProductivityData] = useState([]);

  const [tableSheet, setTableSheet] = useState("daily"); // "daily" | "egg"
  // NEW: Shed filter state
  const [selectedShedFilter, setSelectedShedFilter] = useState("all");
  const [weeklyEntries, setWeeklyEntries] = useState([]);

  // DATE FILTERS
  const [dateMode, setDateMode] = useState("single"); // "single" | "range"
  const [singleDate, setSingleDate] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // NEW
  const [viewMode, setViewMode] = useState("table"); // cards | table

  const [detailsModalOpen, setDetailsModalOpen] = useState(false);
  const [selectedDetails, setSelectedDetails] = useState(null);
  const [mortCullData, setMortCullData] = useState([]);


  const handleOpenDetails = (row) => {
    setSelectedDetails(row);
    setDetailsModalOpen(true);
  };

  const handleCloseDetails = () => {
    setDetailsModalOpen(false);
    setSelectedDetails(null);
  };


  // --------------------------
  // LOAD ADMIN + FARMS
  // --------------------------
  useEffect(() => {
  const token = localStorage.getItem("token");

  if (!token) {
    console.error("No token found. Redirecting to login.");
    return;
  }

  const fetchData = async () => {
    try {

      // 🔐 Headers with JWT
      const config = {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      };

      // Existing loaders (must also use JWT internally)
      await loadFarms();
      await loadMissingToday();
      await loadGlobalAnalytics();

      // ⭐ Global Summary Cards (NO admin_id anymore)
      const summaryRes = await axios.get(
        `${API_BASE}/api/admin/global_summary_cards`,
        config
      );

      setGlobalSummary(summaryRes.data.data);
      console.log("🔥 Global Summary Cards:", summaryRes.data.data);

    } catch (error) {
      console.error("❌ Error in dashboard useEffect:", error);

      if (error.response?.status === 401) {
        console.error("Unauthorized. Clearing session.");
        localStorage.clear();
      }
    }
  };

  fetchData();

}, []);



const loadFarms = async () => {
  try {
    const token = localStorage.getItem("token");

    const res = await axios.get(
      `${API_BASE}/api/admin/farms`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );

    setFarms(res.data.data || []);
    console.log("res.data.data",res.data.data);

  } catch (e) {
    console.error("Farm fetch error", e);
  }
};


  // --------------------------
  // LOAD ENTRIES + SUMMARY
  // --------------------------
  const loadFarmEntries = async (farmId) => {
  if (!farmId) {
    setEntries({});
    setSheds([]);
    setEggSummary(null);
    setBirdSummary(null);
    setByShed([]);
    setWeeklyEntries([]);
    setProductivityData([]);
    setFcrData([]);
    setMortCullData([]);
    setWaterData([]);
    setWeeklyAmmonia([]);
    setDailySummary([]);
    return;
  }

  try {
    setLoading(true);

    const token = localStorage.getItem("token");

    const config = {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    };

    // MAIN FETCH CALLS
    const res = await axios.get(
      `${API_BASE}/api/admin/farm_entries?farm_id=${farmId}`,
      config
    );

    const egg = await axios.get(
      `${API_BASE}/api/admin/farm_egg_summary?farm_id=${farmId}`,
      config
    );

    const birds = await axios.get(
      `${API_BASE}/api/admin/farm_bird_summary?farm_id=${farmId}`,
      config
    );

    const weekly = await axios.get(
      `${API_BASE}/api/admin/farm_weekly_entries?farm_id=${farmId}`,
      config
    );

    const prod = await axios.get(
      `${API_BASE}/api/admin/farm_productivity?farm_id=${farmId}`,
      config
    );

    const fcr = await axios.get(
      `${API_BASE}/api/admin/farm_fcr_weekly?farm_id=${farmId}`,
      config
    );

    const mortCull = await axios.get(
      `${API_BASE}/api/admin/mortality_culling_trend?farm_id=${farmId}`,
      config
    );

    const water = await axios.get(
      `${API_BASE}/api/admin/farm_water_trend?farm_id=${farmId}`,
      config
    );

    const fwc = await axios.get(
      `${API_BASE}/api/admin/feed_water_correlation?farm_id=${farmId}`,
      config
    );

    const twm = await axios.get(
      `${API_BASE}/api/admin/temp_water_mortality?farm_id=${farmId}`,
      config
    );

    const ammonia = await axios.get(
      `${API_BASE}/api/admin/weekly_ammonia_trend?farm_id=${farmId}`,
      config
    );

    const dailySummary = await axios.get(
      `${API_BASE}/api/admin/farm_daily_summary?farm_id=${farmId}`,
      config
    );

    // STORE VALUES
    setDailySummary(dailySummary.data.data || []);
    setWeeklyAmmonia(ammonia.data.data || []);
    setFeedWaterData(fwc.data.data || []);
    setTempWaterMortData(twm.data.data || []);

    setSheds(res.data.sheds || []);
    setEntries(res.data.data || {});
    setEggSummary(egg.data.summary || null);
    setBirdSummary(birds.data.summary || null);
    setByShed(birds.data.by_shed || []);

    setWeeklyEntries(weekly.data.data || []);
    setProductivityData(prod.data.data || []);
    console.log("PROD",prod.data.data);
    setFcrData(fcr.data.data || []);
    setMortCullData(mortCull.data.data || []);
    setWaterData(water.data.data || []);

  } catch (e) {
    console.error("Farm entries error", e);

    if (e.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
    }

  } finally {
    setLoading(false);
  }
};

const loadMissingToday = async () => {
  try {
    const token = localStorage.getItem("token");

    const res = await axios.get(
      `${API_BASE}/api/admin/missing_entries_today`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );

    setMissingToday(res.data.data || []);

  } catch (err) {
    console.error("Missing entries fetch error", err);

    if (err.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
    }
  }
};


  // --------------------------
  // FILTER LOGIC
  // --------------------------
  const filterEntry = (e) => {
    if (searchText) {
      const s = searchText.toLowerCase();
      const content = [
        e.farm_name,
        e.shed_number,
        e.sick_updates,
        e.medical_notes,
        e.culling_reason,
      ]
        .join(" ")
        .toLowerCase();
      if (!content.includes(s)) return false;
    }

    if (dFrom && e.entry_date < dFrom) return false;
    if (dTo && e.entry_date > dTo) return false;

    return true;
  };

  const toggle = (id) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const val = (v, unit = "") =>
    v !== undefined && v !== null ? `${v}${unit}` : "—";

  // --------------------------
  // NEW: TABLE DATA FLATTENER
  // --------------------------
  const getTableData = () => {
    const rows = [];

    Object.entries(entries).forEach(([date, shedMap]) => {
      Object.entries(shedMap).forEach(([shedNo, block]) => {

        // DAILY entries
        (block.daily || []).forEach((e) => {
          rows.push({
            type: "daily",
            shed: e.shed_number || shedNo,
            shed_id: e.shed_id,
            entry_id: e.entry_id,  // 🔥 REQUIRED


            // Date + Time
            date: e.entry_date,
            time: e.created_at,

            // Mortality
            mortality: e.mortality ?? 0,
            mortality_reason: e.mortality_reason ?? "—",

            // Culling
            culling: e.culling ?? 0,
            culling_reason: e.culling_reason ?? "—",

            // Environment Inputs (always clean)
            feed: e.feed_consumption_kg ?? "—",
            water: e.water_consumed_ltrs ?? "—",
            lighting: e.lighting_hours ?? "—",
            temperature: e.temperature ?? "—",

            // Medical
            medical: e.medical_attention ? "Yes" : "No",
            medical_notes: e.medical_notes ?? "—",

            // PDF
            pdf: e.proof_pdf ?? null
          });
        });


        // EGG entries
        (block.egg || []).forEach((egg) => {
          rows.push({
            type: "egg",
            date,
            entry_id: egg.egg_id,       // ⭐ REQUIRED
            shed_id: egg.shed_id,         // ⭐ REQUIRED
            shed: shedNo,
            good: egg.good_eggs,
            floor: egg.floor_eggs,
            broken: egg.broken_cracked_eggs,
            mis: egg.mishapped_eggs,
            pdf: egg.proof_pdf
          });
        });


      });
    });
    weeklyEntries.forEach((w) => {
      rows.push({
        type: "weekly",
        date: w.entry_date,
        shed: w.shed_number,
        ammonia: w.ammonia_level ?? "—",
        weight: w.avg_bird_weight ?? "—",
        notes: w.weekly_notes ?? "—",
        created_at: w.created_at,
        pdf: w.proof_pdf ?? null,
      });
    });

    return rows;
  };



  const getTrendData = () => {
    return productivityData.map((p) => ({
      date: p.date,
      shed: p.shed_number,
      productivity: p.productivity_ratio,
      broken_ratio: p.wastage_ratio,
      floor_mishap_ratio: p.floor_mishap_ratio,
    }));
  };
  // --------------------------
  // NEW: FCR TREND DATA
  // --------------------------
  const getFcrTrend = () => {
    return fcrData.map((f) => ({
      week: "Week " + f.week,
      shed: f.shed_number,
      fcr: f.fcr,
    }));
  };

  const getMortCullTrend = () => {
    return mortCullData.map(d => ({
      date: d.date,
      shed: d.shed,
      mortality: d.mortality_pct,
      culling: d.culling_pct
    }));
  };

  const getWaterTrend = () => {
    return waterData.map((w) => ({
      date: w.date,                    // x-axis
      shed: w.shed_number,             // shed filter
      water_total: w.water_ltrs,       // total water consumed
      birds: w.closing_birds,          // birds count
      water_per_bird: w.water_per_bird // main metric for analysis
    }));
  };

  const getFeedWaterTrend = () => {
    return feedWaterData.map((r) => ({
      date: r.date,
      shed: r.shed_number,
      feed: r.feed_per_bird,
      water: r.water_per_bird,
    }));
  };

  const getTempWaterMortTrend = () => {
    return tempWaterMortData.map((r) => ({
      date: r.date,
      shed: r.shed_number,
      temperature: r.temperature,
      water: r.water_per_bird,
      mortality: r.mortality_pct
    }));
  };
  const getAmmoniaTrend = () => {
    console.log("🔥 Weekly Ammonia Raw Data:", weeklyAmmonia);

    const grouped = {};

    weeklyAmmonia.forEach(a => {
      const key = `${a.date}_${a.shed_number}`;

      // Log each item being processed
      console.log("➡️ Processing:", {
        date: a.date,
        shed: a.shed_number,
        ammonia: a.ammonia_level,
        weight: a.avg_bird_weight
      });

      if (!grouped[key]) {
        grouped[key] = {
          date: a.date,
          shed: a.shed_number,
          ammonia: [],
          weight: [],
        };
      }

      grouped[key].ammonia.push(a.ammonia_level);
      grouped[key].weight.push(a.avg_bird_weight);
    });

    // Log the grouped intermediate output
    console.log("📦 Grouped Data:", grouped);

    const finalData = Object.values(grouped).map(g => ({
      date: g.date,
      shed: g.shed,
      ammonia: g.ammonia.reduce((sum, v) => sum + v, 0) / g.ammonia.length,
      weight: g.weight.reduce((sum, v) => sum + v, 0) / g.weight.length,
    }));

    // Log final chart-ready data
    console.log("✅ Final Ammonia Trend:", finalData);

    return finalData;
  };


const loadGlobalAnalytics = async () => {
  try {
    setLoading(true);

    const token = localStorage.getItem("token");

    if (!token) {
      localStorage.clear();
      window.location.href = "/";
      return;
    }

    const config = {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    };

    const [
      prod,
      fcr,
      mortCull,
      water,
      feedWater,
      tempWaterMort,
    ] = await Promise.all([
      axios.get(`${API_BASE}/api/admin/global_productivity`, config),
      axios.get(`${API_BASE}/api/admin/global_fcr_weekly`, config),
      axios.get(`${API_BASE}/api/admin/global_mortality_culling`, config),
      axios.get(`${API_BASE}/api/admin/global_water_trend`, config),
      axios.get(`${API_BASE}/api/admin/global_feed_water_correlation`, config),
      axios.get(`${API_BASE}/api/admin/global_temp_water_mortality`, config),
    ]);

    setGlobalProductivity(prod.data.data || []);
    setGlobalFcr(fcr.data.data || []);
    setGlobalMortCull(mortCull.data.data || []);
    setGlobalWater(water.data.data || []);
    setGlobalFeedWater(feedWater.data.data || []);
    setGlobalTempWaterMort(tempWaterMort.data.data || []);

    console.log("Loaded Global Analytics");

  } catch (e) {
    console.error("Global analytics error:", e.response?.data || e);

    if (e.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
    }
  } finally {
    setLoading(false);
  }
};



  const getGlobalProductivityTrend = () => {
    return globalProductivity.map((p) => ({
      date: p.date,
      shed: p.shed_number,
      productivity: p.productivity_ratio,
      broken_ratio: p.wastage_ratio,
      floor_mishap_ratio: p.floor_mishap_ratio,
    }));
  };

  const getGlobalFcrTrend = () => {
    return globalFcr.map((f) => ({
      week: "Week " + f.week,
      shed: f.shed_number,
      fcr: f.fcr,
    }));
  };

  const getGlobalMortCullTrend = () => {
    return globalMortCull.map((d) => ({
      date: d.date,
      shed: d.shed,
      mortality: d.mortality_pct,
      culling: d.culling_pct,
    }));
  };

  const getGlobalWaterTrend = () => {
    return globalWater.map((w) => ({
      date: w.date,
      shed: w.shed_number,
      water_per_bird: w.water_per_bird,
      water_total: w.water_ltrs,
    }));
  };

  const getGlobalFeedWaterTrend = () => {
    return globalFeedWater.map((r) => ({
      date: r.date,
      shed: r.shed_number,
      feed: r.feed_per_bird,
      water: r.water_per_bird,
    }));
  };

  const getGlobalTempWaterMortTrend = () => {
    return globalTempWaterMort.map((r) => ({
      date: r.date,
      shed: r.shed_number,
      temperature: r.temperature,
      water: r.water_per_bird,
      mortality: r.mortality_pct,
    }));
  };

  const handleOpenEdit = (row) => {
    console.log("EDIT ROW:", row); // you will now see shed_id here
    setEditEntry({ ...row });
    setEditModalOpen(true);
  };

  const handleCloseEdit = () => {
    setEditModalOpen(false);
    setEditEntry(null);
  };

  const handleOpenEggEdit = (row) => {
    setEditEggEntry(row);
    setEditEggModalOpen(true);
  };

  const handleCloseEggEdit = () => {
    setEditEggModalOpen(false);
    setEditEggEntry(null);
  };

  const handleEggEditSubmit = async () => {
  try {
    console.log("🐣 SUBMITTING EGG EDIT...");

    const token = localStorage.getItem("token");

    if (!token) {
      localStorage.clear();
      window.location.href = "/";
      return;
    }

    const payload = {
      egg_id: editEggEntry.entry_id,
      shed_id: editEggEntry.shed_id,
      date: editEggEntry.date,
      good: editEggEntry.good,
      floor: editEggEntry.floor,
      broken: editEggEntry.broken,
      mis: editEggEntry.mis,
    };

    const res = await axios.post(
      `${API_BASE}/api/admin/update_egg_entry`,
      payload,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );

    console.log("✅ API Response:", res.data);

    alert("Egg entry updated successfully!");
    handleCloseEggEdit();
    loadFarmEntries(selectedFarm);

  } catch (err) {
    console.error("❌ Error updating egg entry:", err.response?.data || err);

    if (err.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/";
    }

    alert("Failed to update entry.");
  }
};


  const cleanExportRow = (row) => {
    if (row.type === "daily") {
      return {
        sheet: "daily",
        date: row.date,
        shed: row.shed,
        mortality: row.mortality,
        culling: row.culling,
        feed_kg: row.feed,
        water_ltrs: row.water,
        lighting_hrs: row.lighting,
        temperature_c: row.temperature,
      };
    }

    if (row.type === "egg") {
      return {
        sheet: "egg",
        date: row.date,
        shed: row.shed,
        good_eggs: row.good,
        floor_eggs: row.floor,
        broken_eggs: row.broken,
        mishapped_eggs: row.mis,
      };
    }

    if (row.type === "weekly") {
      return {
        sheet: "weekly",
        date: row.entry_date,
        shed: row.shed_number,
        ammonia_ppm: row.ammonia_level,
        weight_g: row.avg_bird_weight,
      };
    }
  };

  const downloadExcelMultiSheet = (rows) => {
    const cleaned = rows.map(cleanExportRow);

    // Split by type
    const dailyRows = cleaned.filter(r => r.sheet === "daily");
    const eggRows = cleaned.filter(r => r.sheet === "egg");
    const weeklyRows = cleaned.filter(r => r.sheet === "weekly");

    const buildSheet = (name, rows) => {
      if (rows.length === 0) return `=== SHEET: ${name} (empty) ===\n\n`;

      const headers = Object.keys(rows[0]);
      const body = rows
        .map(r => headers.map(h => r[h] ?? "").join("\t"))
        .join("\n");

      return `=== SHEET: ${name} ===\n${headers.join("\t")}\n${body}\n\n`;
    };

    const finalContent =
      buildSheet("Daily Entries", dailyRows) +
      buildSheet("Egg Collection", eggRows) +
      buildSheet("Weekly Reports", weeklyRows);

    const blob = new Blob(
      [finalContent],
      { type: "application/vnd.ms-excel;charset=utf-8;" }
    );
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = "farm_multisheet.xls";
    link.click();
  };



  const exportCSV = (data, filename) => {
    if (!data || data.length === 0) {
      alert("No data available to export.");
      return;
    }

    const csvRows = [];

    // extract headers
    const headers = Object.keys(data[0]);
    csvRows.push(headers.join(","));

    // extract values
    data.forEach((row) => {
      const values = headers.map((h) =>
        row[h] !== null && row[h] !== undefined ? row[h] : ""
      );
      csvRows.push(values.join(","));
    });

    // generate CSV blob
    const blob = new Blob([csvRows.join("\n")], { type: "text/csv" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename + ".csv";
    link.click();
  };
  const dailyRows = getTableData().filter((r) => r.type === "daily");
  const eggRows = getTableData().filter((r) => r.type === "egg");
  const weeklyRows = getTableData().filter((r) => r.type === "weekly");

  const filterByDate = (rowDate) => {
    const d = new Date(rowDate);

    if (dateMode === "single" && singleDate) {
      const sel = new Date(singleDate);
      return (
        d.getFullYear() === sel.getFullYear() &&
        d.getMonth() === sel.getMonth() &&
        d.getDate() === sel.getDate()
      );
    }

    if (dateMode === "range" && (dateFrom || dateTo)) {
      const from = dateFrom ? new Date(dateFrom) : null;
      const to = dateTo ? new Date(dateTo) : null;
      if (from && d < from) return false;
      if (to && d > to) return false;
    }

    return true;
  };
  const getFilteredDaily = () =>
    getTableData()
      .filter((r) => r.type === "daily")
      .filter((r) => filterByDate(r.date));

  const getFilteredEgg = () =>
    getTableData()
      .filter((r) => r.type === "egg")
      .filter((r) => filterByDate(r.date));

  const getFilteredWeekly = () =>
    weeklyEntries.filter((w) => filterByDate(w.entry_date));


  const exportDaily = () => {
    exportCSV(getFilteredDaily(), "daily_filtered");
  };

  const exportEgg = () => {
    exportCSV(getFilteredEgg(), "egg_filtered");
  };

  const exportWeekly = () => {
    exportCSV(getFilteredWeekly(), "weekly_filtered");
  };


  const [showExportMenu, setShowExportMenu] = useState(false);

  // ── DATA ENTRY state ──
  const [isDataEntryMode, setIsDataEntryMode] = useState(false);
  const deTableRef = useRef(null);
  const [deSelectedShed, setDeSelectedShed] = useState("");
  const [deBatch, setDeBatch] = useState(null);
  const [deDates, setDeDates] = useState([]);
  const [deDailyRows, setDeDailyRows] = useState({});
  const [deEggRows, setDeEggRows] = useState({});
  const [deDispatchRows, setDeDispatchRows] = useState({});
  const [deWeeklyRows, setDeWeeklyRows] = useState({});
  const [deTab, setDeTab] = useState("daily");
  const [deLoading, setDeLoading] = useState(false);
  const [deSaving, setDeSaving] = useState(false);
  const [deSaveMsg, setDeSaveMsg] = useState("");
  const [deBatchError, setDeBatchError] = useState("");

  const filteredData = getTableData(); // respects date + shed filters

  const filterDailySummary = (records) => {
    return records
      // ⭐ SHED FILTER
      .filter((d) =>
        selectedShedFilter === "all"
          ? true
          : String(d.shed_number).trim() === String(selectedShedFilter).trim()
      )

      // ⭐ DATE FILTER
      .filter((d) => {
        const rowDate = new Date(d.entry_date);

        // Single date mode
        if (dateMode === "single" && singleDate) {
          const sel = new Date(singleDate);
          return (
            rowDate.getFullYear() === sel.getFullYear() &&
            rowDate.getMonth() === sel.getMonth() &&
            rowDate.getDate() === sel.getDate()
          );
        }

        // Range mode
        if (dateMode === "range" && (dateFrom || dateTo)) {
          const from = dateFrom ? new Date(dateFrom) : null;
          const to = dateTo ? new Date(dateTo) : null;

          if (from && rowDate < from) return false;
          if (to && rowDate > to) return false;
        }

        return true;
      });
  };

  // ── DATA ENTRY helpers ──
  const deEmptyDaily = (d) => ({
    entry_date: d, mortality: "", culling: "", culling_reason: "",
    mortality_reason: "", feed_consumption_kg: "", water_consumed_ltrs: "",
    lighting_hours: "", temperature: "", medical_attention: false, medical_notes: "",
  });
  const deEmptyEgg = (d) => ({
    entry_date: d, good_eggs: "", floor_eggs: "", broken_cracked_eggs: "", mishapped_eggs: "",
  });
  const deEmptyDispatch = (d) => ({
    dispatch_date: d, dispatched_good_eggs: "", dispatched_floor_mis_eggs: "",
  });
  const deEmptyWeekly = (d) => ({
    entry_date: d, ammonia_level: "", avg_bird_weight: "", weekly_notes: "",
  });

  const deTodayIST = () =>
    new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }))
      .toISOString().slice(0, 10);

  const deGenerateDates = (placementDate) => {
    const today = deTodayIST();
    const dates = [];
    const cur = new Date(placementDate + "T00:00:00");
    const end = new Date(today + "T00:00:00");
    if (cur > end) return [];
    while (cur <= end) {
      dates.push(cur.toISOString().slice(0, 10));
      cur.setDate(cur.getDate() + 1);
    }
    return dates;
  };

  const deFmt = (iso) => {
    if (!iso) return "";
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y}`;
  };

  const loadDataEntry = async (shedId) => {
    if (!shedId) return;
    setDeLoading(true);
    setDeBatch(null);
    setDeDates([]);
    setDeBatchError("");
    try {
      const token = localStorage.getItem("token");
      const cfg = { headers: { Authorization: `Bearer ${token}` } };
      const [batchRes, dailyRes, eggRes, dispRes, weeklyRes] = await Promise.all([
        axios.get(`${API_BASE}/api/admin/shed/active-batch?shed_id=${shedId}`, cfg),
        axios.get(`${API_BASE}/api/admin/shed/daily-entries?shed_id=${shedId}`, cfg),
        axios.get(`${API_BASE}/api/admin/shed/egg-entries?shed_id=${shedId}`, cfg),
        axios.get(`${API_BASE}/api/admin/shed/dispatch-entries?shed_id=${shedId}`, cfg),
        axios.get(`${API_BASE}/api/admin/shed/weekly-entries?shed_id=${shedId}`, cfg),
      ]);
      const batchData = batchRes.data.data;
      setDeBatch(batchData);
      const allDates = deGenerateDates(batchData.placement_date);
      setDeDates(allDates);

      const dMap = {};
      allDates.forEach((d) => { dMap[d] = deEmptyDaily(d); });
      (dailyRes.data.data || []).forEach((r) => {
        if (dMap[r.entry_date]) dMap[r.entry_date] = {
          entry_date: r.entry_date, mortality: r.mortality ?? "", culling: r.culling ?? "",
          culling_reason: r.culling_reason ?? "", mortality_reason: r.mortality_reason ?? "",
          feed_consumption_kg: r.feed_consumption_kg ?? "", water_consumed_ltrs: r.water_consumed_ltrs ?? "",
          lighting_hours: r.lighting_hours ?? "", temperature: r.temperature ?? "",
          medical_attention: r.medical_attention ?? false, medical_notes: r.medical_notes ?? "",
        };
      });
      setDeDailyRows(dMap);

      const eMap = {};
      allDates.forEach((d) => { eMap[d] = deEmptyEgg(d); });
      (eggRes.data.data || []).forEach((r) => {
        if (eMap[r.entry_date]) eMap[r.entry_date] = {
          entry_date: r.entry_date, good_eggs: r.good_eggs ?? "", floor_eggs: r.floor_eggs ?? "",
          broken_cracked_eggs: r.broken_cracked_eggs ?? "", mishapped_eggs: r.mishapped_eggs ?? "",
        };
      });
      setDeEggRows(eMap);

      const dispMap = {};
      allDates.forEach((d) => { dispMap[d] = deEmptyDispatch(d); });
      (dispRes.data.data || []).forEach((r) => {
        const key = r.entry_date || r.dispatch_date;
        if (dispMap[key]) dispMap[key] = {
          dispatch_date: key,
          dispatched_good_eggs: r.dispatched_good_eggs ?? "",
          dispatched_floor_mis_eggs: r.dispatched_floor_mis_eggs ?? "",
        };
      });
      setDeDispatchRows(dispMap);

      const wMap = {};
      allDates.forEach((d) => { wMap[d] = deEmptyWeekly(d); });
      (weeklyRes.data.data || []).forEach((r) => {
        if (wMap[r.entry_date]) wMap[r.entry_date] = {
          entry_date: r.entry_date, ammonia_level: r.ammonia_level ?? "",
          avg_bird_weight: r.avg_bird_weight ?? "", weekly_notes: r.weekly_notes ?? "",
        };
      });
      setDeWeeklyRows(wMap);
    } catch (err) {
      if (err.response?.status === 404) {
        setDeBatchError("No active batch found for this shed.");
      } else {
        setDeBatchError(err.response?.data?.detail || "Failed to load data.");
      }
    } finally {
      setDeLoading(false);
    }
  };

  const deEggAvailableUpTo = (date) => {
    let collected = 0, dispatched = 0;
    for (const d of deDates) {
      const eg = deEggRows[d];
      if (eg) collected += (parseInt(eg.good_eggs) || 0) + (parseInt(eg.floor_eggs) || 0);
      const dsp = deDispatchRows[d];
      if (dsp) dispatched += (parseInt(dsp.dispatched_good_eggs) || 0) + (parseInt(dsp.dispatched_floor_mis_eggs) || 0);
      if (d === date) break;
    }
    return Math.max(0, collected - dispatched);
  };

  const saveAllDataEntry = async () => {
    if (!deBatch || !deSelectedShed) return;
    setDeSaving(true);
    setDeSaveMsg("");
    try {
      const token = localStorage.getItem("token");
      const cfg = { headers: { Authorization: `Bearer ${token}` } };
      const farmId = parseInt(selectedFarm);
      const shedId = parseInt(deSelectedShed);
      const toNum = (v) => (v === "" || v == null ? null : parseFloat(v));
      const toInt = (v) => (v === "" || v == null ? 0 : parseInt(v) || 0);

      const dailyPayload = { farm_id: farmId, shed_id: shedId, rows: deDates.map((d) => {
        const r = deDailyRows[d] || deEmptyDaily(d);
        return { entry_date: d, mortality: toInt(r.mortality), culling: toInt(r.culling),
          culling_reason: r.culling_reason || null, mortality_reason: r.mortality_reason || null,
          feed_consumption_kg: toNum(r.feed_consumption_kg), water_consumed_ltrs: toNum(r.water_consumed_ltrs),
          lighting_hours: toNum(r.lighting_hours), temperature: toNum(r.temperature),
          medical_attention: !!r.medical_attention, medical_notes: r.medical_notes || null };
      })};

      const eggPayload = { farm_id: farmId, shed_id: shedId, rows: deDates.map((d) => {
        const r = deEggRows[d] || deEmptyEgg(d);
        return { entry_date: d, good_eggs: toInt(r.good_eggs), floor_eggs: toInt(r.floor_eggs),
          broken_cracked_eggs: toInt(r.broken_cracked_eggs), mishapped_eggs: toInt(r.mishapped_eggs) };
      })};

      const dispatchRows2 = deDates.map((d) => {
        const r = deDispatchRows[d] || deEmptyDispatch(d);
        return { dispatch_date: d, dispatched_good_eggs: toInt(r.dispatched_good_eggs),
          dispatched_floor_mis_eggs: toInt(r.dispatched_floor_mis_eggs) };
      }).filter((r) => r.dispatched_good_eggs > 0 || r.dispatched_floor_mis_eggs > 0);
      const dispatchPayload = { farm_id: farmId, shed_id: shedId, rows: dispatchRows2 };

      const weeklyPayload = { farm_id: farmId, shed_id: shedId, rows: deDates.map((d) => {
        const r = deWeeklyRows[d] || deEmptyWeekly(d);
        return { entry_date: d, ammonia_level: toNum(r.ammonia_level),
          avg_bird_weight: toNum(r.avg_bird_weight), weekly_notes: r.weekly_notes || null };
      })};

      const [dr, er, dsr, wr] = await Promise.all([
        axios.post(`${API_BASE}/api/daily-entry/bulk`, dailyPayload, cfg),
        axios.post(`${API_BASE}/api/egg-entry/bulk`, eggPayload, cfg),
        dispatchRows2.length > 0
          ? axios.post(`${API_BASE}/api/egg-dispatch/bulk`, dispatchPayload, cfg)
          : Promise.resolve({ data: { total: 0 } }),
        axios.post(`${API_BASE}/api/weekly-entry/bulk`, weeklyPayload, cfg),
      ]);
      const total = (dr.data.total || 0) + (er.data.total || 0) + (dsr.data.total || 0) + (wr.data.total || 0);
      setDeSaveMsg(`Saved successfully — ${total} records updated`);
      setTimeout(() => setDeSaveMsg(""), 4000);
      await loadDataEntry(deSelectedShed);
    } catch (err) {
      setDeSaveMsg(err.response?.data?.detail || "Save failed. Please try again.");
    } finally {
      setDeSaving(false);
    }
  };

  const handleGridKeyDown = useCallback((e) => {
    const el = e.target;
    if (!el.matches("input, select, textarea")) return;
    const r = parseInt(el.dataset.r ?? "-1");
    const c = parseInt(el.dataset.c ?? "-1");
    if (isNaN(r) || isNaN(c) || r < 0 || c < 0) return;

    let nr = r, nc = c;
    if (e.key === "Enter" || e.key === "ArrowDown") { nr = r + 1; e.preventDefault(); }
    else if (e.key === "ArrowUp") { nr = r - 1; e.preventDefault(); }
    else if (e.key === "Tab" && !e.shiftKey) { nc = c + 1; e.preventDefault(); }
    else if (e.key === "Tab" && e.shiftKey) { nc = c - 1; e.preventDefault(); }
    else if (e.key === "ArrowRight") {
      if (el.selectionStart === el.value.length) { nc = c + 1; e.preventDefault(); }
      else return;
    } else if (e.key === "ArrowLeft") {
      if (el.selectionStart === 0) { nc = c - 1; e.preventDefault(); }
      else return;
    } else return;

    // Wrap column to next/prev row
    const tbl = deTableRef.current;
    if (!tbl) return;
    let next = tbl.querySelector(`[data-r="${nr}"][data-c="${nc}"]`);
    if (!next && nc > c) { nr = r + 1; nc = 0; next = tbl.querySelector(`[data-r="${nr}"][data-c="${nc}"]`); }
    if (!next && nc < c) {
      nr = r - 1;
      const lastInRow = tbl.querySelectorAll(`[data-r="${nr}"]`);
      if (lastInRow.length) { next = lastInRow[lastInRow.length - 1]; }
    }
    if (next) { next.focus(); next.select?.(); }
  }, []);

  return (
    <div className="dashboard-container">
      {/* 1. HEADER */}
      <div className="dashboard-header">
        <h1 className="page-title">Enterprise Dashboard</h1>
        <p className="page-subtitle">
          Real-time overview of farm operations, stock, and daily reports.
        </p>
      </div>



      {/* 2. FARM CARDS + FILTERS */}
      <div className="toolbar-container">
        <div className="farm-selector-grid">
          {farms.map((f) => (
            <div
              key={f.farm_id}
              className={`farm-select-card ${selectedFarm === f.farm_id.toString() ? "active" : ""}`}
              onClick={() => {
                setSelectedFarm(f.farm_id.toString());
                loadFarmEntries(f.farm_id.toString());
              }}
            >
          <div className="fsc-icon">
          <FaWarehouse size={22} />   {/* 🔥 Replaced emoji */}
        </div>
              <div className="fsc-name">{f.farm_name}</div>
            </div>
          ))}
        </div>
      </div>

      {!selectedFarm && (
        <>


          {globalSummary && (
            <div className="global-stats-grid">

              {/* CARD 1 - Farms + Sheds */}
              <div className="stats-card">
                <h4>Active Farms & Sheds</h4>
                <div className="stats-value dual">
                  <span>{globalSummary.farms}</span>
                  <span>{globalSummary.sheds}</span>
                </div>
                <div className="stats-label dual">
                  <span>Farms</span>
                  <span>Sheds</span>
                </div>
              </div>

              {/* CARD 2 - Total Birds */}
              <div className="stats-card">
                <h4>Total Birds</h4>
                <p className="stats-value">{globalSummary.total_birds}</p>
              </div>

              {/* CARD 3 - Good vs Floor+Mishap Eggs */}
              <div className="stats-card">
                <h4>Egg Collection (Good vs Lower Grade)</h4>
                <div className="stats-value dual">
                  <span>{globalSummary.good_eggs}</span>
                  <span>{globalSummary.floor_mishap_eggs}</span>
                </div>
                <div className="stats-label dual">
                  <span>Good</span>
                  <span>Floor + Mishap</span>
                </div>
              </div>

              {/* CARD 4 - Total Egg Stock */}
              <div className="stats-card">
                <h4>Total Egg Stock</h4>
                <p className="stats-value">{globalSummary.total_egg_stock}</p>
              </div>

            </div>
          )}




          {/* ---------------------------------- */}
          {/* 1️⃣ SHOW MISSING ENTRY OVERVIEW     */}
          {/* ---------------------------------- */}
          <div className="missing-entries-container">
            <div className="missing-header">
              <h3>Daily Entry Overview</h3>
              <p>These sheds have not added their daily updates today.</p>
            </div>

            {missingToday.length === 0 ? (
              <div style={{ color: "var(--success)" }}>
                ✔ Excellent! All sheds have submitted entries today.
              </div>
            ) : (
              <div className="missing-list">
                {missingToday.map((m, idx) => (
                  <div key={idx} className="missing-pill">
                    {m.farm_name} • Shed {m.shed_number}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ---------------------------------- */}
          {/* 2️⃣ GLOBAL ANALYTICS FOR ALL FARMS  */}
          {/* ---------------------------------- */}
          <div className="analytics-section">
            <div className="analytics-header">
              <h2>🌍 All Farms – Combined Analytics</h2>
            </div>

            {/* PRODUCTIVITY */}
            <div className="chart-card">
              <h3>Global Productivity Trend</h3>
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={getGlobalProductivityTrend()} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                  <XAxis
                    dataKey="date"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                    cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                  />
                  <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                  <Line type="monotone" dataKey="productivity" name="Productivity" stroke="#10B981" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                  <Line type="monotone" dataKey="broken_ratio" name="Broken Ratio" stroke="#EF4444" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                  <Line type="monotone" dataKey="floor_mishap_ratio" name="Floor+Mishap Ratio" stroke="#F59E0B" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* FCR */}
            <div className="chart-card">
              <h3>Global Weekly FCR</h3>
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={getGlobalFcrTrend()} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                  <XAxis
                    dataKey="week"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                    cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                  />
                  <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                  <Line type="monotone" dataKey="fcr" name="FCR" stroke="#8B5CF6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* MORTALITY */}
            <div className="chart-card">
              <h3>Global Mortality & Culling %</h3>
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={getGlobalMortCullTrend()} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                  <XAxis
                    dataKey="date"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                    cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                  />
                  <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                  <Line type="monotone" dataKey="mortality" name="Mortality %" stroke="#EF4444" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                  <Line type="monotone" dataKey="culling" name="Culling %" stroke="#F59E0B" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* WATER */}
            <div className="chart-card">
              <h3>Global Water Consumption Per Bird</h3>
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={getGlobalWaterTrend()} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                  <XAxis
                    dataKey="date"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                    cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                  />
                  <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                  <Line type="monotone" dataKey="water_per_bird" name="Water/Bird" stroke="#3B82F6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                  <Line type="monotone" dataKey="water_total" name="Total Water" stroke="#10B981" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* FEED vs WATER */}
            <div className="chart-card">
              <h3>Global Feed vs Water Correlation</h3>
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={getGlobalFeedWaterTrend()} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                  <XAxis
                    dataKey="date"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                    cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                  />
                  <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                  <Line type="monotone" dataKey="feed" name="Feed/Bird" stroke="#10B981" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                  <Line type="monotone" dataKey="water" name="Water/Bird" stroke="#3B82F6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* TEMP–WATER–MORTALITY */}
            <div className="chart-card">
              <h3>Global Temperature vs Water vs Mortality</h3>
              <ResponsiveContainer width="100%" height={380}>
                <LineChart data={getGlobalTempWaterMortTrend()} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                  <XAxis
                    dataKey="date"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#6B7280", fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                    cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                  />
                  <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                  <Line type="monotone" dataKey="temperature" name="Temp" stroke="#EF4444" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                  <Line type="monotone" dataKey="water" name="Water/Bird" stroke="#3B82F6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                  <Line type="monotone" dataKey="mortality" name="Mort %" stroke="#8B5CF6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}


      {/* DATE DISPLAY */}
      {selectedFarm && (
        <div className="current-date-display">
          Current Status
        </div>

      )}

      {/* SUMMARY CARDS */}
      {selectedFarm && (birdSummary || eggSummary) && (
        <div className="summary-section">
          {/* Bird Summary */}
          {birdSummary && (
            <div className="summary-card">
              <div className="summary-title">
                <span>🐦 Bird Stock Summary</span>
              </div>
              <div className="summary-grid">
                <div className="stat-item">
                  <span className="stat-label">Placed Birds</span>
                  <span className="stat-value large">{birdSummary.total_opening}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Current   Birds</span>
                  <span className="stat-value large">{birdSummary.total_closing}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Mortality</span>
                  <span className="stat-value danger">
                    {byShed.reduce((acc, s) => acc + (s.mortality || 0), 0)}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Culling</span>
                  <span className="stat-value danger">
                    {byShed.reduce((acc, s) => acc + (s.culling || 0), 0)}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Egg Summary */}
          {eggSummary && (
            <div className="summary-card">
              <div className="summary-title">
                <span>🥚 Egg Production Summary</span>
              </div>
              <div className="summary-grid three-col">
                <div className="stat-item">
                  <span className="stat-label">Good Collected</span>
                  <span className="stat-value">{eggSummary.collected_good_total}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Floor / Mis</span>
                  <span className="stat-value">{eggSummary.collected_floor_mis_total}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Broken / Wastage</span>
                  <span className="stat-value danger">{eggSummary.collected_wastage_total}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Good Dispatched</span>
                  <span className="stat-value">{eggSummary.dispatched_good_total}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Floor Dispatched</span>
                  <span className="stat-value">{eggSummary.dispatched_floor_mis_total}</span>
                </div>
                {/* Current Available Good */}
                <div className="stat-item">
                  <span className="stat-label">Available Good Eggs</span>
                  <span className="stat-value">
                    {eggSummary.closing_good}
                  </span>
                </div>

                {/* Current Available Floor + Mishapped */}
                <div className="stat-item">
                  <span className="stat-label">Available Floor/Mishapped</span>
                  <span className="stat-value">
                    {eggSummary.closing_floor_mis}
                  </span>
                </div>

                {/* Total Stock */}
                <div className="stat-item">
                  <span className="stat-label">Total Available Stock</span>
                  <span className="stat-value large">
                    {eggSummary.closing_good + eggSummary.closing_floor_mis}
                  </span>
                </div>

              </div>
            </div>
          )}
        </div>
      )}

  

      
      {selectedFarm && viewMode === "table" && (
  <>

   <div className="analytics-button-wrapper">
<button
  className="analytics-btn"
  onClick={() => setViewMode("analytics")}
>
  <FaChartBar size={18} style={{ marginRight: "6px" }} />
  Visualize Data
</button>
    </div>
    {/* EXPORT MENU */}
    <div className="export-wrapper">
<button
  className="export-main-btn"
  onClick={() => setShowExportMenu(!showExportMenu)}
>
  <FaDownload className="export-icon" />
  Export
</button>

      {showExportMenu && (
        <div className="export-menu">
          <div className="export-section-title">Full Dataset</div>
          <button onClick={() => downloadExcelMultiSheet(filteredData)}>
            Excel (Multi-Sheet)
          </button>

          <div className="divider"></div>

          <div className="export-section-title">Individual Sheets</div>
          <button onClick={exportDaily}>Daily Entries</button>
          <button onClick={exportEgg}>Egg Entries</button>
          <button onClick={exportWeekly}>Weekly Entries</button>
        </div>
      )}
    </div>

    {/* DATA ENTRY BUTTON */}
    <div className="export-wrapper">
      <button
        className={`export-main-btn de-mode-btn${isDataEntryMode ? " de-mode-btn-active" : ""}`}
        onClick={() => {
          setIsDataEntryMode((v) => !v);
          if (!isDataEntryMode) setTableSheet("daily");
        }}
      >
        ✏️ {isDataEntryMode ? "Exit Data Entry" : "Data Entry"}
      </button>
    </div>

  </>
)}






      {/* -------------------------- */}
      {/* NEW: TABLE VIEW SECTION   */}
      {/* -------------------------- */}
      {selectedFarm && viewMode === "table" && (
        <div className="table-wrapper">

          {/* ── DATA ENTRY BANNER ── */}
          {isDataEntryMode && (
            <div className="de-banner">
              <div className="de-banner-left">
                <span className="de-banner-label">✏️ Data Entry Mode</span>
                {!deSelectedShed && <span className="de-banner-loading">← Select a shed below to begin</span>}
                {deBatch && (
                  <span className="de-banner-batch">
                    {deBatch.batch_name || `Batch #${deBatch.batch_id}`} &nbsp;|&nbsp;
                    Placement: {deFmt(deBatch.placement_date)} &nbsp;|&nbsp;
                    Birds: {deBatch.initial_bird_count?.toLocaleString()}
                  </span>
                )}
                {deLoading && <span className="de-banner-loading">Loading...</span>}
                {deBatchError && <span className="de-banner-err">{deBatchError}</span>}
              </div>
              <div className="de-banner-right">
                {deSaveMsg && (
                  <span className={deSaveMsg.includes("failed") || deSaveMsg.includes("Failed") ? "de-save-err" : "de-save-ok"}>
                    {deSaveMsg}
                  </span>
                )}
                {deBatch && (
                  <button className="de-save-btn" onClick={saveAllDataEntry} disabled={deSaving}>
                    {deSaving ? "Saving..." : "💾 Save All"}
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="date-filter-section">

            {/* Toggle Single Date / Range */}
            <div className="date-mode-toggle">
              <button
                className={dateMode === "single" ? "active" : ""}
                onClick={() => setDateMode("single")}
              >
                Single Date
              </button>
              <button
                className={dateMode === "range" ? "active" : ""}
                onClick={() => setDateMode("range")}
              >
                Date Range
              </button>
            </div>

            {/* SINGLE DATE FILTER */}
            {dateMode === "single" && (
              <div className="date-single-picker">
                <label>Select Date:</label>
                <input
                  type="date"
                  value={singleDate}
                  onChange={(e) => setSingleDate(e.target.value)}
                />
                {singleDate && (
                  <button className="clear-btn" onClick={() => setSingleDate("")}>
                    Clear
                  </button>
                )}
              </div>
            )}

            {/* RANGE FILTER */}
            {dateMode === "range" && (
              <div className="date-range-picker">
                <div>
                  <label>From:</label>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                  />
                </div>

                <div>
                  <label>To:</label>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                  />
                </div>

                {(dateFrom || dateTo) && (
                  <button
                    className="clear-btn"
                    onClick={() => {
                      setDateFrom("");
                      setDateTo("");
                    }}
                  >
                    Clear
                  </button>
                )}
              </div>
            )}

          </div>


          {/* Shed Filter */}
          <div className="shed-filter-wrapper">
            <label className="shed-filter-label">Select Shed:</label>

            <select
              className="shed-filter"
              value={selectedShedFilter}
              onChange={(e) => {
                const shedNum = e.target.value;
                setSelectedShedFilter(shedNum);
                if (isDataEntryMode) {
                  if (shedNum === "all") {
                    setDeSelectedShed("");
                    setDeBatch(null);
                    setDeDates([]);
                    setDeBatchError("");
                  } else {
                    const shed = sheds.find((s) => String(s.shed_number) === String(shedNum));
                    if (shed) {
                      setDeSelectedShed(String(shed.shed_id));
                      setDeBatchError("");
                      loadDataEntry(shed.shed_id);
                    }
                  }
                }
              }}
            >
              <option value="all">All Sheds</option>
              {sheds.map((s) => (
                <option key={s.shed_id} value={s.shed_number}>
                  Shed {s.shed_number}
                </option>
              ))}
            </select>
          </div>

          {/* Sheet Tabs */}
          <div className="table-tabs">
            <button
              className={tableSheet === "dailySummary" ? "active" : ""}
              onClick={() => setTableSheet("dailySummary")}
            >
              Daily Summary
            </button>
            <button
              className={tableSheet === "daily" ? "active" : ""}
              onClick={() => setTableSheet("daily")}
            >
              Daily Entry Sheet
            </button>
            <button
              className={tableSheet === "egg" ? "active" : ""}
              onClick={() => setTableSheet("egg")}
            >
              Egg Collection Sheet
            </button>
            <button
              className={tableSheet === "dispatch" ? "active" : ""}
              onClick={() => setTableSheet("dispatch")}
            >
              Egg Dispatch Sheet
            </button>
            <button
              className={tableSheet === "weekly" ? "active" : ""}
              onClick={() => setTableSheet("weekly")}
            >
              Weekly Entry Sheet
            </button>
          </div>

          {/* ---------------- DAILY SUMMARY NEW TAB ---------------- */}
          {tableSheet === "dailySummary" && (
            <div className="daily-summary-tab">

              {filterDailySummary(dailySummary).length === 0 && (
                <p className="empty-state">No daily summary records found.</p>
              )}

              <div className="daily-summary-grid">
                {filterDailySummary(dailySummary).map((d, index) => {
                  const formattedDate = new Date(d.entry_date).toLocaleDateString(
                    "en-GB",
                    { day: "2-digit", month: "short", year: "2-digit" }
                  );

                  return (
                    <div key={index} className="ds-card-modern">

                      {/* Header: Title + Badges */}
                      <div className="ds-header-modern">
                        <div className="ds-title-group">
                          <span className="ds-shed-id">Shed {d.shed_number}</span>
                          <span className="ds-date-meta">{formattedDate}</span>
                        </div>

                        <div className="ds-badge-stack">
                          <div className={`ds-status-badge ${d.mortality > 0 ? 'status-danger' : 'status-neutral'}`}>
                            Mort: {d.mortality}
                          </div>
                          <div className={`ds-status-badge ${d.culling > 0 ? 'status-warning' : 'status-neutral'}`}>
                            Cull: {d.culling}
                          </div>
                        </div>
                      </div>

                      {/* Core Metrics Grid */}
                      <div className="ds-metrics-grid">

                        <div className="ds-metric-chip">
                          <span className="chip-label">Feed</span>
                          <span className="chip-value">{d.feed_total} <small>kg</small></span>
                        </div>

                        <div className="ds-metric-chip">
                          <span className="chip-label">Water</span>
                          <span className="chip-value">{d.water_total} <small>L</small></span>
                        </div>

                        <div className="ds-metric-chip">
                          <span className="chip-label">Temp</span>
                          <span className="chip-value">{d.temp_min}° - {d.temp_max}°</span>
                        </div>

                        <div className="ds-metric-chip">
                          <span className="chip-label">Light</span>
                          <span className="chip-value">{d.lighting_total} <small>hrs</small></span>
                        </div>

                      </div>

                      {/* Logic for Separator */}
                      {(d.medical_attention || (d.proofs && d.proofs.length > 0)) && (
                        <div className="ds-divider"></div>
                      )}

                      {/* Medical Block */}
                      {d.medical_attention && (
                        <div className="ds-info-block medical-block">
                          <div className="block-header">
                            <span className="block-icon">💊</span>
                            <span className="block-title">Medical Attention Needed</span>
                          </div>
                          {d.medical_notes && d.medical_notes.length > 0 && (
                            <div className="block-content">
                              {d.medical_notes.join(", ")}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Proofs Block */}
                      {d.proofs && d.proofs.length > 0 && (
                        <div className="ds-info-block proof-block">
                          <div className="block-header">
                            <span className="block-icon">📎</span>
                            <span className="block-title">Attachments</span>
                          </div>
                          <div className="proof-list">
                            {d.proofs.map((p, i) => (
                              <a
                                key={i}
                                className="proof-link"
                                href={`${API_BASE}/${p}`}
                                target="_blank"
                                rel="noreferrer"
                              >
                                View Proof {i + 1}
                              </a>
                            ))}
                          </div>
                        </div>
                      )}

                    </div>
                  );
                })}
              </div>
            </div>
          )}




          {/* ---------------- WEEKLY ENTRY SHEET (EDIT MODE) ---------------- */}
          {tableSheet === "weekly" && isDataEntryMode && deBatch && (
            <div className="de-table-wrap" ref={deTableRef} onKeyDown={handleGridKeyDown}>
              <table className="de-table">
                <thead>
                  <tr>
                    <th className="de-th-date">Date</th>
                    <th>Ammonia (ppm)</th>
                    <th>Avg Bird Wt (g)</th>
                    <th>Weekly Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {deDates.map((d, ri) => {
                    const r = deWeeklyRows[d] || deEmptyWeekly(d);
                    const isToday = d === deTodayIST();
                    const upd = (field, val) => setDeWeeklyRows((p) => ({ ...p, [d]: { ...p[d], [field]: val } }));
                    return (
                      <tr key={d} className={isToday ? "de-row-today" : ""}>
                        <td className="de-td-date">{deFmt(d)}{isToday && <span className="de-today-badge">Today</span>}</td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={0} value={r.ammonia_level} onChange={(e) => upd("ammonia_level", e.target.value)} /></td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={1} value={r.avg_bird_weight} onChange={(e) => upd("avg_bird_weight", e.target.value)} /></td>
                        <td><input className="de-input de-input-wide" type="text" data-r={ri} data-c={2} value={r.weekly_notes} onChange={(e) => upd("weekly_notes", e.target.value)} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* ---------------- WEEKLY ENTRY SHEET (READ MODE) ---------------- */}
          {tableSheet === "weekly" && !(isDataEntryMode && deBatch) && (
            <div className="table-container">
              <table className="enterprise-table weekly-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Shed</th>
                    <th>Ammonia (ppm)</th>
                    <th>Avg Bird Weight (g)</th>
                    <th>Notes</th>
                    <th>Created At</th>
                    <th>Proof</th>
                  </tr>
                </thead>

                <tbody>
                  {weeklyEntries
                    // --------------------
                    // SHED FILTER
                    // --------------------
                    .filter((w) =>
                      selectedShedFilter === "all"
                        ? true
                        : String(w.shed_number).trim() ===
                        String(selectedShedFilter).trim()
                    )

                    // --------------------
                    // DATE FILTER (single + range)
                    // --------------------
                    .filter((w) => {
                      const rowDate = new Date(w.entry_date);

                      // Single date mode
                      if (dateMode === "single" && singleDate) {
                        const sel = new Date(singleDate);
                        return (
                          rowDate.getFullYear() === sel.getFullYear() &&
                          rowDate.getMonth() === sel.getMonth() &&
                          rowDate.getDate() === sel.getDate()
                        );
                      }

                      // Range mode
                      if (dateMode === "range" && (dateFrom || dateTo)) {
                        const from = dateFrom ? new Date(dateFrom) : null;
                        const to = dateTo ? new Date(dateTo) : null;
                        if (from && rowDate < from) return false;
                        if (to && rowDate > to) return false;
                      }

                      return true;
                    })

                    // --------------------
                    // RENDER ROWS
                    // --------------------
                    .map((w, idx) => (
                      <tr key={idx}>
                        <td>
                          {new Date(w.entry_date).toLocaleDateString("en-GB", {
                            day: "2-digit",
                            month: "short",
                            year: "2-digit",
                          })}
                        </td>

                        <td>
                          <span className="shed-pill">{w.shed_number}</span>
                        </td>

                        <td>{w.ammonia_level ?? "—"}</td>
                        <td>{w.avg_bird_weight ?? "—"}</td>
                        <td>{w.weekly_notes || "—"}</td>

                        <td>
                          {new Date(w.created_at).toLocaleTimeString("en-GB", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </td>

                        <td>
                          {w.proof_pdf ? (
                            <a
                              href={`${API_BASE}/${w.proof_pdf}`}
                              target="_blank"
                              className="btn-icon-link"
                            >
                              PDF
                            </a>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}

                  {/* -------------------- */}
                  {/* EMPTY STATE */}
                  {/* -------------------- */}
                  {weeklyEntries.length === 0 && (
                    <tr>
                      <td colSpan="7" className="text-center py-8 text-muted">
                        No weekly entries found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* ---------------- DAILY ENTRY SHEET (EDIT MODE) ---------------- */}
          {tableSheet === "daily" && isDataEntryMode && deBatch && (
            <div className="de-table-wrap" ref={deTableRef} onKeyDown={handleGridKeyDown}>
              <table className="de-table">
                <thead>
                  <tr>
                    <th className="de-th-date">Date</th>
                    <th>Mortality</th>
                    <th>Mort. Reason</th>
                    <th>Culling</th>
                    <th>Cull. Reason</th>
                    <th>Feed (kg)</th>
                    <th>Water (L)</th>
                    <th>Lighting (h)</th>
                    <th>Temp (°C)</th>
                    <th>Medical</th>
                    <th>Med. Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {deDates.map((d, ri) => {
                    const r = deDailyRows[d] || deEmptyDaily(d);
                    const isToday = d === deTodayIST();
                    const upd = (field, val) => setDeDailyRows((p) => ({ ...p, [d]: { ...p[d], [field]: val } }));
                    return (
                      <tr key={d} className={isToday ? "de-row-today" : ""}>
                        <td className="de-td-date">{deFmt(d)}{isToday && <span className="de-today-badge">Today</span>}</td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={0} value={r.mortality} onChange={(e) => upd("mortality", e.target.value)} /></td>
                        <td><input className="de-input de-input-text" type="text" data-r={ri} data-c={1} value={r.mortality_reason} onChange={(e) => upd("mortality_reason", e.target.value)} /></td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={2} value={r.culling} onChange={(e) => upd("culling", e.target.value)} /></td>
                        <td><input className="de-input de-input-text" type="text" data-r={ri} data-c={3} value={r.culling_reason} onChange={(e) => upd("culling_reason", e.target.value)} /></td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={4} value={r.feed_consumption_kg} onChange={(e) => upd("feed_consumption_kg", e.target.value)} /></td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={5} value={r.water_consumed_ltrs} onChange={(e) => upd("water_consumed_ltrs", e.target.value)} /></td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={6} value={r.lighting_hours} onChange={(e) => upd("lighting_hours", e.target.value)} /></td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={7} value={r.temperature} onChange={(e) => upd("temperature", e.target.value)} /></td>
                        <td style={{ textAlign: "center" }}>
                          <input type="checkbox" data-r={ri} data-c={8} checked={!!r.medical_attention} onChange={(e) => upd("medical_attention", e.target.checked)} style={{ width: 16, height: 16, cursor: "pointer" }} />
                        </td>
                        <td><input className="de-input de-input-text" type="text" data-r={ri} data-c={9} value={r.medical_notes} disabled={!r.medical_attention} onChange={(e) => upd("medical_notes", e.target.value)} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* ---------------- DAILY ENTRY SHEET (READ MODE) ---------------- */}
          {tableSheet === "daily" && !(isDataEntryMode && deBatch) && (
            <div className="table-container">
              <table className="enterprise-table daily-table">
                <thead>
                  <tr>
                    <th>Date & Time</th>
                    <th>Shed</th>
                    <th>Mortality</th>
                    <th>Culling</th>
                    <th>Feed (kg)</th>
                    <th>Water (Ltrs)</th>
                    <th>Lighting (hrs)</th>
                    <th>Temp (°C)</th>
                    <th>Medical</th>
                    <th>Details</th>
                    <th>Proof</th>
                  </tr>
                </thead>

                <tbody>
                  {getTableData()
                    .filter((r) => r.type === "daily")

                    // SHED FILTER
                    .filter((r) =>
                      selectedShedFilter === "all"
                        ? true
                        : String(r.shed).trim() === String(selectedShedFilter).trim()
                    )

                    // DATE FILTER
                    .filter((r) => {
                      const rowDate = new Date(r.date);

                      if (dateMode === "single" && singleDate) {
                        const sel = new Date(singleDate);
                        return (
                          rowDate.getFullYear() === sel.getFullYear() &&
                          rowDate.getMonth() === sel.getMonth() &&
                          rowDate.getDate() === sel.getDate()
                        );
                      }

                      if (dateMode === "range" && (dateFrom || dateTo)) {
                        const from = dateFrom ? new Date(dateFrom) : null;
                        const to = dateTo ? new Date(dateTo) : null;

                        if (from && rowDate < from) return false;
                        if (to && rowDate > to) return false;
                      }

                      return true;
                    })

                    // RENDER ROWS
                    .map((row, index) => (
                      <tr key={index}>
                        {/* Date + Time */}
                        <td>
                          <div className="date-time-cell">
                            <span className="date-part">
                              {new Date(row.date).toLocaleDateString("en-GB", {
                                day: "2-digit",
                                month: "short",
                                year: "2-digit",
                              })}
                            </span>
                            <span className="time-part">
                              {row.time
                                ? new Date(row.time).toLocaleTimeString("en-GB", {
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })
                                : "—"}
                            </span>
                          </div>
                        </td>

                        {/* Shed */}
                        <td><span className="shed-pill">{row.shed}</span></td>

                        {/* Mortality */}
                        <td className={row.mortality > 0 ? "text-danger-soft" : "text-muted"}>
                          {row.mortality ?? "—"}
                        </td>

                        {/* Culling */}
                        <td className={row.culling > 0 ? "text-danger-soft" : "text-muted"}>
                          {row.culling ?? "—"}
                        </td>

                        {/* Feed */}
                        <td>{row.feed ?? "—"}</td>

                        {/* Water */}
                        <td>{row.water ?? "—"}</td>

                        {/* Lighting */}
                        <td>{row.lighting ?? "—"}</td>

                        {/* Temperature */}
                        <td>{row.temperature ? `${row.temperature}°` : "—"}</td>

                        {/* Medical Yes/No */}
                        <td>
                          <span
                            className={`status-badge ${row.medical === "Yes" ? "status-yes" : "status-no"}`}
                          >
                            {row.medical}
                          </span>
                        </td>

                        {/* DETAILS BUTTON */}
                        <td className="action-cell">
                          <button
                            className="view-details-btn"
                            onClick={() => handleOpenDetails(row)}
                          >
                            View
                          </button>

                          <button
                            className="edit-btn"
                            onClick={() => handleOpenEdit(row)}
                          >
                            Edit
                          </button>
                        </td>


                        {/* PDF */}
                        <td>
                          {row.pdf ? (
                            <a
                              href={`${API_BASE}/${row.pdf}`}
                              target="_blank"
                              className="btn-icon-link"
                            >
                              PDF
                            </a>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}

                  {/* NO ROWS */}
                  {getTableData()
                    .filter((r) => r.type === "daily")
                    .filter((r) =>
                      selectedShedFilter === "all"
                        ? true
                        : String(r.shed).trim() === String(selectedShedFilter).trim()
                    )
                    .filter((r) => {
                      const rowDate = new Date(r.date);

                      if (dateMode === "single" && singleDate) {
                        const sel = new Date(singleDate);
                        return (
                          rowDate.getFullYear() === sel.getFullYear() &&
                          rowDate.getMonth() === sel.getMonth() &&
                          rowDate.getDate() === sel.getDate()
                        );
                      }

                      if (dateMode === "range" && (dateFrom || dateTo)) {
                        const from = dateFrom ? new Date(dateFrom) : null;
                        const to = dateTo ? new Date(dateTo) : null;
                        if (from && rowDate < from) return false;
                        if (to && rowDate > to) return false;
                      }

                      return true;
                    }).length === 0 && (
                      <tr>
                        <td colSpan="12" className="text-center py-8 text-muted">
                          No daily entries found.
                        </td>
                      </tr>
                    )}
                </tbody>
              </table>
            </div>
          )}
          {detailsModalOpen && selectedDetails && (
            <div className="modal-overlay">
              <div className="modal-card">
                <h3>Daily Entry Details</h3>

                <div className="modal-section">
                  <strong>Mortality:</strong> {selectedDetails.mortality}
                </div>

                <div className="modal-section">
                  <strong>Mortality Reason:</strong><br />
                  {selectedDetails.mortality_reason || "—"}
                </div>

                <div className="modal-section">
                  <strong>Culling:</strong> {selectedDetails.culling}
                </div>

                <div className="modal-section">
                  <strong>Culling Reason:</strong><br />
                  {selectedDetails.culling_reason || "—"}
                </div>

                <div className="modal-section">
                  <strong>Medical Attention:</strong> {selectedDetails.medical}
                </div>

                <div className="modal-section">
                  <strong>Medical Notes:</strong><br />
                  {selectedDetails.medical_notes || "—"}
                </div>

                <button className="modal-close-btn" onClick={handleCloseDetails}>
                  Close
                </button>
              </div>
            </div>
          )}
          {editModalOpen && editEntry && (
            <div className="modal-overlay">
              <div className="modal-card">
                <h3>Edit Daily Entry</h3>

                <div className="modal-section">
                  <label>Mortality</label>
                  <input
                    type="number"
                    value={editEntry.mortality}
                    onChange={(e) =>
                      setEditEntry({ ...editEntry, mortality: e.target.value })
                    }
                  />
                </div>

                <div className="modal-section">
                  <label>Mortality Reason</label>
                  <textarea
                    value={editEntry.mortality_reason}
                    onChange={(e) =>
                      setEditEntry({ ...editEntry, mortality_reason: e.target.value })
                    }
                  />
                </div>

                <div className="modal-section">
                  <label>Culling</label>
                  <input
                    type="number"
                    value={editEntry.culling}
                    onChange={(e) =>
                      setEditEntry({ ...editEntry, culling: e.target.value })
                    }
                  />
                </div>

                <div className="modal-section">
                  <label>Culling Reason</label>
                  <textarea
                    value={editEntry.culling_reason}
                    onChange={(e) =>
                      setEditEntry({ ...editEntry, culling_reason: e.target.value })
                    }
                  />
                </div>

                <div className="modal-section">
                  <label>Feed (kg)</label>
                  <input
                    type="number"
                    value={editEntry.feed}
                    onChange={(e) =>
                      setEditEntry({ ...editEntry, feed: e.target.value })
                    }
                  />
                </div>

                <div className="modal-section">
                  <label>Water (Ltrs)</label>
                  <input
                    type="number"
                    value={editEntry.water}
                    onChange={(e) =>
                      setEditEntry({ ...editEntry, water: e.target.value })
                    }
                  />
                </div>

                <div className="modal-section">
                  <label>Lighting (hrs)</label>
                  <input
                    type="number"
                    value={editEntry.lighting}
                    onChange={(e) =>
                      setEditEntry({ ...editEntry, lighting: e.target.value })
                    }
                  />
                </div>

                <div className="modal-section">
                  <label>Temperature (°C)</label>
                  <input
                    type="number"
                    value={editEntry.temperature}
                    onChange={(e) =>
                      setEditEntry({ ...editEntry, temperature: e.target.value })
                    }
                  />
                </div>

               <button
  className="modal-save-btn"
  onClick={async () => {
    try {
      const token = localStorage.getItem("token");

      if (!token) {
        localStorage.clear();
        window.location.href = "/";
        return;
      }

      await axios.post(
        `${API_BASE}/api/admin/update_daily_entry`,
        {
          ...editEntry,
          entry_id: editEntry.entry_id,
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      handleCloseEdit();
      loadFarmEntries(selectedFarm);

    } catch (err) {
      console.error("Update daily entry error:", err.response?.data || err);

      if (err.response?.status === 401) {
        localStorage.clear();
        window.location.href = "/";
      }
    }
  }}
>
  Save Changes
</button>


                <button className="modal-close-btn" onClick={handleCloseEdit}>
                  Cancel
                </button>
              </div>
            </div>
          )}





          {/* ---------------- EGG COLLECTION SHEET (EDIT MODE) ---------------- */}
          {tableSheet === "egg" && isDataEntryMode && deBatch && (
            <div className="de-table-wrap" ref={deTableRef} onKeyDown={handleGridKeyDown}>
              <table className="de-table">
                <thead>
                  <tr>
                    <th className="de-th-date">Date</th>
                    <th>Good Eggs</th>
                    <th>Floor Eggs</th>
                    <th>Broken Eggs</th>
                    <th>Mishapped</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {deDates.map((d, ri) => {
                    const r = deEggRows[d] || deEmptyEgg(d);
                    const isToday = d === deTodayIST();
                    const total = (parseInt(r.good_eggs)||0)+(parseInt(r.floor_eggs)||0)+(parseInt(r.broken_cracked_eggs)||0)+(parseInt(r.mishapped_eggs)||0);
                    const upd = (field, val) => setDeEggRows((p) => ({ ...p, [d]: { ...p[d], [field]: val } }));
                    return (
                      <tr key={d} className={isToday ? "de-row-today" : ""}>
                        <td className="de-td-date">{deFmt(d)}{isToday && <span className="de-today-badge">Today</span>}</td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={0} value={r.good_eggs} onChange={(e) => upd("good_eggs", e.target.value)} /></td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={1} value={r.floor_eggs} onChange={(e) => upd("floor_eggs", e.target.value)} /></td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={2} value={r.broken_cracked_eggs} onChange={(e) => upd("broken_cracked_eggs", e.target.value)} /></td>
                        <td><input className="de-input" type="number" data-r={ri} data-c={3} value={r.mishapped_eggs} onChange={(e) => upd("mishapped_eggs", e.target.value)} /></td>
                        <td className="de-td-calc">{total > 0 ? total.toLocaleString() : ""}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* ---------------- EGG COLLECTION SHEET (READ MODE) ---------------- */}
          {tableSheet === "egg" && !(isDataEntryMode && deBatch) && (
            <div className="table-container">
              <table className="enterprise-table egg-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Shed</th>
                    <th>Good</th>
                    <th>Floor</th>
                    <th>Broken</th>
                    <th>Mishapped</th>
                    <th>Edit</th>

                    <th>Proof</th>
                  </tr>
                </thead>

                <tbody>
                  {getTableData()
                    .filter((r) => r.type === "egg")

                    // --------------------
                    // SHED FILTER
                    // --------------------
                    .filter((r) =>
                      selectedShedFilter === "all"
                        ? true
                        : String(r.shed).trim() === String(selectedShedFilter).trim()
                    )

                    // --------------------
                    // DATE FILTER (single + range)
                    // --------------------
                    .filter((r) => {
                      const rowDate = new Date(r.date);

                      // ---- Single Date Mode ----
                      if (dateMode === "single" && singleDate) {
                        const sel = new Date(singleDate);
                        return (
                          rowDate.getFullYear() === sel.getFullYear() &&
                          rowDate.getMonth() === sel.getMonth() &&
                          rowDate.getDate() === sel.getDate()
                        );
                      }

                      // ---- Range Mode ----
                      if (dateMode === "range" && (dateFrom || dateTo)) {
                        const from = dateFrom ? new Date(dateFrom) : null;
                        const to = dateTo ? new Date(dateTo) : null;

                        if (from && rowDate < from) return false;
                        if (to && rowDate > to) return false;
                      }

                      return true;
                    })

                    // --------------------
                    // RENDER ROWS
                    // --------------------
                    .map((row, index) => (
                      <tr key={index}>
                        <td>
                          {new Date(row.date).toLocaleDateString("en-GB", {
                            day: "2-digit",
                            month: "short",
                            year: "2-digit",
                          })}
                        </td>

                        <td>
                          <span className="shed-pill">Shed {row.shed}</span>
                        </td>

                        <td className="td-good">{row.good ?? "—"}</td>
                        <td className="td-floor">{row.floor ?? "—"}</td>
                        <td className="td-broken">{row.broken ?? "—"}</td>
                        <td className="td-mis">{row.mis ?? "—"}</td>
                        <td>
                          <button
                            className="edit-btn"
                            onClick={() => handleOpenEggEdit(row)}
                          >
                            Edit
                          </button>
                        </td>



                        <td>
                          {row.pdf ? (
                            <a
                              href={`${API_BASE}/${row.pdf}`}
                              target="_blank"
                              className="btn-icon-link"
                            >
                              PDF
                            </a>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}

                  {/* -------------------- */}
                  {/* EMPTY STATE */}
                  {/* -------------------- */}
                  {getTableData()
                    .filter((r) => r.type === "egg")
                    .filter((r) =>
                      selectedShedFilter === "all"
                        ? true
                        : String(r.shed).trim() === String(selectedShedFilter).trim()
                    )
                    .filter((r) => {
                      const rowDate = new Date(r.date);

                      if (dateMode === "single" && singleDate) {
                        const sel = new Date(singleDate);
                        return (
                          rowDate.getFullYear() === sel.getFullYear() &&
                          rowDate.getMonth() === sel.getMonth() &&
                          rowDate.getDate() === sel.getDate()
                        );
                      }

                      if (dateMode === "range" && (dateFrom || dateTo)) {
                        const from = dateFrom ? new Date(dateFrom) : null;
                        const to = dateTo ? new Date(dateTo) : null;
                        if (from && rowDate < from) return false;
                        if (to && rowDate > to) return false;
                      }

                      return true;
                    }).length === 0 && (
                      <tr>
                        <td colSpan="8" className="text-center py-8 text-muted">
                          No egg collections found.
                        </td>
                      </tr>
                    )}
                </tbody>
              </table>
            </div>
          )}

          {/* ---------------- EGG DISPATCH SHEET ----------------*/}
          {tableSheet === "dispatch" && (
            <div className="de-table-wrap" ref={deTableRef} onKeyDown={handleGridKeyDown}>
              {isDataEntryMode && deBatch && (() => {
                let totalCollected = 0, totalDispatched = 0;
                deDates.forEach((d) => {
                  const eg = deEggRows[d];
                  if (eg) totalCollected += (parseInt(eg.good_eggs)||0) + (parseInt(eg.floor_eggs)||0);
                  const dsp = deDispatchRows[d];
                  if (dsp) totalDispatched += (parseInt(dsp.dispatched_good_eggs)||0) + (parseInt(dsp.dispatched_floor_mis_eggs)||0);
                });
                return (
                  <div className="de-avail-banner">
                    <span>Total Collected: <strong>{totalCollected.toLocaleString()}</strong></span>
                    <span>Total Dispatched: <strong>{totalDispatched.toLocaleString()}</strong></span>
                    <span className="de-avail-highlight">Available Stock: <strong>{Math.max(0, totalCollected - totalDispatched).toLocaleString()}</strong></span>
                  </div>
                );
              })()}
              {isDataEntryMode && deBatch ? (
                <table className="de-table">
                  <thead>
                    <tr>
                      <th className="de-th-date">Date</th>
                      <th>Good Dispatched</th>
                      <th>Floor/Mis Dispatched</th>
                      <th>Eggs Available</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deDates.map((d, ri) => {
                      const r = deDispatchRows[d] || deEmptyDispatch(d);
                      const isToday = d === deTodayIST();
                      const avail = deEggAvailableUpTo(d);
                      const upd = (field, val) => setDeDispatchRows((p) => ({ ...p, [d]: { ...p[d], [field]: val } }));
                      return (
                        <tr key={d} className={isToday ? "de-row-today" : ""}>
                          <td className="de-td-date">{deFmt(d)}{isToday && <span className="de-today-badge">Today</span>}</td>
                          <td><input className="de-input" type="number" data-r={ri} data-c={0} value={r.dispatched_good_eggs} onChange={(e) => upd("dispatched_good_eggs", e.target.value)} /></td>
                          <td><input className="de-input" type="number" data-r={ri} data-c={1} value={r.dispatched_floor_mis_eggs} onChange={(e) => upd("dispatched_floor_mis_eggs", e.target.value)} /></td>
                          <td className="de-td-avail">{avail.toLocaleString()}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div className="de-empty-state">Enable Data Entry mode and select a shed to view dispatch entries.</div>
              )}
            </div>
          )}

          {editEggModalOpen && editEggEntry && (
            <div className="modal-overlay">
              <div className="modal-card">
                <h3>Edit Egg Entry</h3>

                <div className="modal-input-group">
                  <label>Good Eggs</label>
                  <input
                    type="number"
                    value={editEggEntry.good}
                    onChange={(e) =>
                      setEditEggEntry({ ...editEggEntry, good: Number(e.target.value) })
                    }
                  />
                </div>

                <div className="modal-input-group">
                  <label>Floor Eggs</label>
                  <input
                    type="number"
                    value={editEggEntry.floor}
                    onChange={(e) =>
                      setEditEggEntry({ ...editEggEntry, floor: Number(e.target.value) })
                    }
                  />
                </div>

                <div className="modal-input-group">
                  <label>Broken Eggs</label>
                  <input
                    type="number"
                    value={editEggEntry.broken}
                    onChange={(e) =>
                      setEditEggEntry({ ...editEggEntry, broken: Number(e.target.value) })
                    }
                  />
                </div>

                <div className="modal-input-group">
                  <label>Mishapped Eggs</label>
                  <input
                    type="number"
                    value={editEggEntry.mis}
                    onChange={(e) =>
                      setEditEggEntry({ ...editEggEntry, mis: Number(e.target.value) })
                    }
                  />
                </div>

                <div className="modal-btn-row">
                  <button className="modal-save-btn" onClick={handleEggEditSubmit}>
                    Save Changes
                  </button>
                  <button className="modal-close-btn" onClick={handleCloseEggEdit}>
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}


        </div>
      )}


      {selectedFarm && viewMode === "analytics" && (
        <div className="analytics-section">
          <div className="analytics-header">
            <h2>📊 Farm Productivity & Wastage Trends</h2>
            <button
              className="back-btn"
              onClick={() => setViewMode("table")}
            >
              ← Back to Table View
            </button>
          </div>

          {/* SHED FILTER */}
          <div className="shed-filter-wrapper analytics-filter">
            <label>Select Shed:</label>
            <select
              value={selectedShedFilter}
              onChange={(e) => setSelectedShedFilter(e.target.value)}
            >
              <option value="all">All Sheds</option>
              {sheds.map((s) => (
                <option key={s.shed_id} value={s.shed_number}>
                  Shed {s.shed_number}
                </option>
              ))}
            </select>
          </div>

          {/* PRODUCTIVITY */}
          <div className="chart-card">
            <h3>Daily Productivity Trend</h3>
            <ResponsiveContainer width="100%" height={350}>
              <LineChart
                data={getTrendData().filter((d) =>
                  selectedShedFilter === "all" ? true : d.shed === selectedShedFilter
                )}
                margin={{ top: 20, right: 30, left: 0, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis
                  dataKey="date"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                  dy={10}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                  cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                />
                <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                <Line type="monotone" dataKey="productivity" name="Productivity Ratio" stroke="#10B981" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                <Line type="monotone" dataKey="broken_ratio" name="Broken Egg Ratio" stroke="#EF4444" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                <Line type="monotone" dataKey="floor_mishap_ratio" name="Floor + Mishap Ratio" stroke="#F59E0B" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="analytics-info">
            <p>✔ <strong>Productivity Ratio</strong> = Good Eggs / Closing Birds</p>
            <p>✔ <strong>Broken Ratio</strong> = Broken Eggs / Closing Birds</p>
            <p>✔ <strong>Floor + Mishap Ratio</strong> = (Floor + Mishap) / Closing Birds</p>
          </div>

          {/* FCR */}
          <div className="chart-card">
            <h3>Weekly FCR Trend</h3>
            <ResponsiveContainer width="100%" height={350}>
              <LineChart
                data={getFcrTrend().filter((d) =>
                  selectedShedFilter === "all" ? true : d.shed === selectedShedFilter
                )}
                margin={{ top: 20, right: 30, left: 0, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis
                  dataKey="week"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                  dy={10}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                  cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                />
                <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                <Line type="monotone" dataKey="fcr" name="Feed Conversion Ratio (FCR)" stroke="#8B5CF6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="analytics-info">
            <p>✔ <strong>FCR</strong> = Total Feed (kg) / Total Weight Gain (kg)</p>
            <p>✔ Lower FCR = more efficient birds</p>
            <p>✔ FCR is calculated weekly using your Weekly Entries + Daily Feed</p>
          </div>

          {/* MORTALITY */}
          <div className="chart-card">
            <h3>Daily Mortality & Culling % Trend</h3>
            <ResponsiveContainer width="100%" height={350}>
              <LineChart
                data={getMortCullTrend().filter((d) =>
                  selectedShedFilter === "all" ? true : d.shed === selectedShedFilter
                )}
                margin={{ top: 20, right: 30, left: 0, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis
                  dataKey="date"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                  dy={10}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                  cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                />
                <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                <Line type="monotone" dataKey="mortality" name="Mortality %" stroke="#EF4444" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                <Line type="monotone" dataKey="culling" name="Culling %" stroke="#F59E0B" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="analytics-info">
            <p>✔ <strong>Mortality %</strong> = Daily Mortality / Closing Birds × 100</p>
            <p>✔ <strong>Culling %</strong> = Daily Culling / Closing Birds × 100</p>
            <p>✔ Useful to detect stress, heat, disease & management issues.</p>
          </div>

          {/* WATER */}
          <div className="chart-card">
            <h3>Daily Water Consumption Per Bird</h3>
            <ResponsiveContainer width="100%" height={350}>
              <LineChart
                data={getWaterTrend().filter((d) =>
                  selectedShedFilter === "all" ? true : d.shed === selectedShedFilter
                )}
                margin={{ top: 20, right: 30, left: 0, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis
                  dataKey="date"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                  dy={10}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                  cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                />
                <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                <Line type="monotone" dataKey="water_per_bird" name="Water Per Bird (Ltrs)" stroke="#3B82F6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                <Line type="monotone" dataKey="water_total" name="Total Water (Ltrs)" stroke="#10B981" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="analytics-info">
            <p>✔ <strong>Water Per Bird (Ltrs)</strong> = Daily water intake per bird.</p>
            <p>✔ Stable trend = consistent bird health and feed activity.</p>
            <p>✔ Sudden drop → disease, stress, feed rejection, nipple blockage.</p>
            <p>✔ Sudden spike → heat stress, water leakage, loose droppings.</p>
          </div>

          {/* FEED vs WATER */}
          <div className="chart-card">
            <h3>Feed vs Water Consumption Trend</h3>
            <ResponsiveContainer width="100%" height={350}>
              <LineChart
                data={getFeedWaterTrend().filter((d) =>
                  selectedShedFilter === "all" ? true : d.shed === selectedShedFilter
                )}
                margin={{ top: 20, right: 30, left: 0, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis
                  dataKey="date"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                  dy={10}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                  cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                />
                <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                <Line type="monotone" dataKey="feed" name="Feed per Bird (kg)" stroke="#10B981" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                <Line type="monotone" dataKey="water" name="Water per Bird (L)" stroke="#3B82F6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="analytics-info">
            <p>✔ <strong>Feed per Bird (kg)</strong> = Total Feed Given ÷ Closing Birds.</p>
            <p>✔ <strong>Water per Bird (Ltrs)</strong> = Daily drinking water ÷ Closing Birds.</p>
            <p>✔ These two metrics are strongly linked — when feed intake rises, water intake also rises.</p>
            <p>✔ <strong>Divergence (Feed drops, Water constant)</strong> → Feed rejection, stress, toxin issue.</p>
            <p>✔ <strong>Spike in Water but Feed same</strong> → Heat stress or water leakage.</p>
            <p>✔ <strong>Perfect trend:</strong> both lines rising smoothly together.</p>
          </div>

          {/* AMMONIA TREND */}
          <div className="chart-card">
            <h3>Weekly Ammonia vs Bird Weight Trend</h3>

            <ResponsiveContainer width="100%" height={350}>
              <LineChart data={getAmmoniaTrend()}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="shed" />
                <YAxis />
                <Tooltip />
                <Legend />

                <Line
                  type="monotone"
                  dataKey="ammonia"
                  name="Ammonia (ppm)"
                  stroke="#EF4444"
                  strokeWidth={3}
                  dot={{ r: 4 }}
                  activeDot={{ r: 6 }}
                />

                <Line
                  type="monotone"
                  dataKey="weight"
                  name="Avg Bird Weight (g)"
                  stroke="#10B981"
                  strokeWidth={3}
                  dot={{ r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>





          {/* TEMP–WATER–MORTALITY */}
          <div className="chart-card">
            <h3>Temperature vs Water vs Mortality Trend</h3>
            <ResponsiveContainer width="100%" height={380}>
              <LineChart
                data={getTempWaterMortTrend().filter((d) =>
                  selectedShedFilter === "all" ? true : d.shed === selectedShedFilter
                )}
                margin={{ top: 20, right: 30, left: 0, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis
                  dataKey="date"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                  dy={10}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#6B7280", fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: "#fff", border: "none", borderRadius: "8px", boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)" }}
                  cursor={{ stroke: "#9CA3AF", strokeWidth: 1, strokeDasharray: "4 4" }}
                />
                <Legend wrapperStyle={{ paddingTop: "20px" }} iconType="circle" />
                <Line type="monotone" dataKey="temperature" name="Temperature (°C)" stroke="#EF4444" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                <Line type="monotone" dataKey="water" name="Water per Bird (L)" stroke="#3B82F6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
                <Line type="monotone" dataKey="mortality" name="Mortality %" stroke="#8B5CF6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6, strokeWidth: 0 }} animationDuration={1500} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}




      {/* MISSING TODAY */}

    </div>
  );
}
