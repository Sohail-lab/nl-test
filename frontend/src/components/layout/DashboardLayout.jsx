import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";

import {
  Plus,
  Settings,
  LogOut,
  Menu,
  X,
  LayoutDashboard,
  Play,
  FileText,
} from "lucide-react";

import { Button } from "../../components/ui/button";

const navItems = [
  { href: "/", label: "Tests", icon: LayoutDashboard },
  // { href: "/create-test", label: "Create Test", icon: Plus },
  // { href: "/test-runs", label: "Test Runs", icon: Play },
  { href: "/reports", label: "Reports", icon: FileText },
  // { href: "/settings", label: "Settings", icon: Settings },
];

export function DashboardLayout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();

  const pathname = location.pathname;
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const handleLogout = () => {
    navigate("/");
  };

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside
        className={`${
          sidebarOpen ? "w-64" : "w-20"
        } bg-sidebar-background border-r border-sidebar-border transition-all duration-300 flex flex-col`}
      >
        {/* Logo */}
        <div className="h-16 border-b border-sidebar-border flex items-center justify-between px-4">
          {sidebarOpen && (
            <h1 className="font-bold text-lg text-sidebar-foreground">
              Automated Tests from Simple Texts
            </h1>
          )}

          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1 hover:bg-sidebar-accent rounded-lg text-sidebar-foreground"
          >
            {sidebarOpen ? (
              <X className="w-5 h-5" />
            ) : (
              <Menu className="w-5 h-5" />
            )}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-6 space-y-2 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;

            return (
              <Link key={item.href} to={item.href}>
                <div
                  className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                    isActive
                      ? "bg-sidebar-primary text-sidebar-primary-foreground"
                      : "text-sidebar-foreground hover:bg-sidebar-accent"
                  }`}
                >
                  <Icon className="w-5 h-5 flex-shrink-0" />

                  {sidebarOpen && (
                    <span className="text-sm font-medium">{item.label}</span>
                  )}
                </div>
              </Link>
            );
          })}
        </nav>

        {/* User Profile & Logout */}
        <div className="border-t border-sidebar-border p-4 space-y-2">
          {sidebarOpen && (
            <div className="px-2 py-2">
              <p className="text-xs font-semibold text-sidebar-foreground">
                {/* Sohail */}
              </p>
              <p className="text-xs text-sidebar-foreground/70">
                {/* sohail@ivp.in */}
              </p>
            </div>
          )}

          <Button
            onClick={handleLogout}
            variant="ghost"
            className="w-full justify-start text-sidebar-foreground hover:bg-sidebar-accent"
          >
            {/* <LogOut className="w-4 h-4" /> */}
            {/* {sidebarOpen && <span className="ml-3 text-sm">Logout</span>} */}
          </Button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-16 border-b border-border bg-card px-8 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-foreground">
            {navItems.find((item) => item.href === pathname)?.label ||
              "Test Page"}
          </h2>

          <div className="flex items-center gap-4">
            <div className="text-right">
              {/* <p className="text-sm font-medium text-foreground">Sohail</p> */}
              <p className="text-xs text-muted-foreground">
                {/* sohail@ivp.in */}
              </p>
            </div>

            <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center">
              {/* <span className="text-sm font-bold text-primary">MS</span> */}
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto">
          <div className="p-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
