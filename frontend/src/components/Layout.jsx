import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import './Layout.css';

export default function Layout() {
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);

    return (
        <div className="layout-wrapper">
            <Sidebar
                isOpen={isSidebarOpen}
                onClose={() => setIsSidebarOpen(false)}
            />

            <div className="main-content">
                {/* Mobile Header (Visible only on mobile) */}
                <header className="mobile-header">
                    <button
                        className="mobile-menu-btn"
                        onClick={() => setIsSidebarOpen(true)}
                        aria-label="Open menu"
                    >
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <line x1="3" y1="12" x2="21" y2="12"></line>
                            <line x1="3" y1="6" x2="21" y2="6"></line>
                            <line x1="3" y1="18" x2="21" y2="18"></line>
                        </svg>
                    </button>
                    <span className="mobile-logo">Flockify</span>
                    <div style={{ width: 24 }} /> {/* Spacer for centering if needed */}
                </header>

                {/* Page Content */}
                <main className="page-container">
                    <Outlet />
                </main>
            </div>
        </div>
    );
}
