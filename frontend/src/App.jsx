import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import "./globals.css";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/dashboard/DashboardPage";
import ReportsPage from "./pages/reports/ReportsPage";

export default function App() {
  return (
    <Routes>
      {/* <Route path="/" element={<LoginPage />} /> */}
      {/* <Route path="/dashboard" element={<DashboardPage />} /> */}
      <Route path="/" element={<DashboardPage />} />
      <Route path="/reports" element={<ReportsPage />} />
    </Routes>
  );
}