import React from 'react';
import { NavLink } from 'react-router-dom';
import './Sidebar.css';
import { 
  FiHome, 
  FiBarChart2,
  FiLayers,
  FiGrid,
  FiChevronRight,
  FiArchive 
} from "react-icons/fi";


export default function Sidebar({ isOpen, onClose }) {
    const overlayClass = isOpen ? 'mobile-overlay open' : 'mobile-overlay';
    const sidebarClass = isOpen ? 'sidebar open' : 'sidebar';

    // Admin Info
    const storedAdmin = localStorage.getItem("adminUser");
    const admin = storedAdmin ? JSON.parse(storedAdmin) : null;

    const displayName = admin?.name || "Farm Owner";
    const displayEmail = admin?.email || "";
    const displayPhone = admin?.phone || "";
    
    function logout() {
        localStorage.removeItem("adminUser");
        localStorage.removeItem("token");
        window.location.href = "/login";
    }

    return (
        <>
            {/* MOBILE OVERLAY */}
            <div className={overlayClass} onClick={onClose} />

            {/* SIDEBAR */}
            <aside className={sidebarClass}>

                {/* ⭐ BRAND LOGOS ⭐ */}
                <div className="sidebar-header">
                    <img 
                        src="/5.png"
                        alt="Logo"
                        className="sidebar-logo-chicken"
                    />
                    <img 
                        src="/6.png"
                        alt="Flockify"
                        className="sidebar-logo-text"
                    />
                </div>

                {/* NAVIGATION */}
                <nav className="sidebar-nav">

                    <NavLink
                        to="/dashboard"
                        className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}
                        onClick={onClose}
                    >
                        <FiBarChart2 className="nav-icon" />
                        Dashboard
                    </NavLink>

                    <NavLink
                        to="/farms"
                        className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}
                        onClick={onClose}
                    >
                        <FiHome className="nav-icon" />
                        Farms
                    </NavLink>

                    <NavLink
                        to="/previous-batches"
                        className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}
                        onClick={onClose}
                    >
                        <FiArchive className="nav-icon" />
                        Previous Batches
                    </NavLink>

                </nav>


                {/* FOOTER */}
                <div className="sidebar-footer">
                    <div className="user-avatar"></div>

                    <div className="user-info">
                        <span className="user-name">{displayName}</span>
                        <span className="user-role">{displayEmail}</span>
                        <span className="user-role">{displayPhone}</span>
                    </div>

                    <button className="logout-btn" onClick={logout}>
                        Logout
                    </button>
                </div>

            </aside>
        </>
    );
}
