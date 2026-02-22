import React, { useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  ChevronRight,
  FileText,
  LayoutDashboard,
  Menu,
  Sparkles,
  X,
} from "lucide-react";

const navItems = [
  { href: "/", label: "Tests", icon: LayoutDashboard },
  { href: "/reports", label: "Reports", icon: FileText },
];

export function DashboardLayout({ children }) {
  const { pathname } = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const activeItem = useMemo(
    () => navItems.find((item) => item.href === pathname),
    [pathname]
  );

  const pageTitle =
    pathname === "/reports" ? "Execution Reports" : "Dashboard";
  const pageSubtitle =
    pathname === "/reports"
      ? "Review test outcomes, network events, and console diagnostics."
      : "Upload test files, execute web tests, and monitor progress in real time.";
  const updatedDate = useMemo(
    () =>
      new Date().toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      }),
    []
  );

  return (
    <div className="relative min-h-screen overflow-hidden text-slate-900">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 -top-28 h-72 w-72 rounded-full bg-sky-200/40 blur-3xl" />
        <div className="absolute right-0 top-8 h-80 w-80 rounded-full bg-cyan-200/30 blur-3xl" />
      </div>

      <div className="relative z-10 flex min-h-screen gap-3 p-3 sm:gap-5 sm:p-5">
        <aside
          className={`${
            sidebarOpen ? "w-72" : "w-20"
          } flex flex-col rounded-3xl border border-sky-100/90 bg-white/90 shadow-[0_20px_50px_rgba(2,132,199,0.12)] backdrop-blur-md transition-all duration-300`}
        >
          <div className="flex h-20 items-center justify-between border-b border-slate-100 px-4">
            <div
              className={`overflow-hidden transition-all duration-300 ${
                sidebarOpen ? "w-52 opacity-100" : "w-0 opacity-0"
              }`}
            >
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-600">
                AI Test Script
              </p>
              <h1 className="text-base font-bold tracking-tight text-slate-900">
                Generation Tool
              </h1>
            </div>

            {/* <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="rounded-xl border border-slate-200 bg-white p-2 text-slate-600 transition hover:border-sky-200 hover:text-sky-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
              aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
            >
              {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button> */}
          </div>

          <nav className="flex-1 space-y-2 overflow-y-auto px-3 py-5">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;

              return (
                <Link
                  key={item.href}
                  to={item.href}
                  className={`group flex items-center gap-3 rounded-2xl px-4 py-3 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 ${
                    isActive
                      ? "bg-gradient-to-r from-sky-500 to-cyan-500 text-white shadow-md"
                      : "text-slate-700 hover:bg-sky-50 hover:text-sky-700"
                  }`}
                >
                  <Icon className="h-5 w-5 flex-shrink-0" />
                  {sidebarOpen && (
                    <>
                      <span className="flex-1 text-sm font-semibold">{item.label}</span>
                      <ChevronRight
                        className={`h-4 w-4 transition ${
                          isActive ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                        }`}
                      />
                    </>
                  )}
                </Link>
              );
            })}
          </nav>

          {/* <div className="border-t border-slate-100 p-4">
            {sidebarOpen ? (
              <div className="rounded-2xl border border-sky-100 bg-gradient-to-br from-sky-50 to-cyan-50 p-3">
                <p className="mb-1 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-sky-700">
                  <Sparkles className="h-3.5 w-3.5" />
                  Workspace
                </p>
                <p className="text-xs leading-relaxed text-slate-600">
                  Design tests from simple text, execute in one click, and inspect
                  live status with structured reports.
                </p>
              </div>
            ) : (
              <div className="flex justify-center">
                <Sparkles className="h-5 w-5 text-sky-600" />
              </div>
            )}
          </div> */}
        </aside>

        <div className="min-w-0 flex-1">
          <div className="flex h-full flex-col overflow-hidden rounded-3xl border border-sky-100/90 bg-white/85 shadow-[0_20px_45px_rgba(14,116,144,0.12)] backdrop-blur-sm">
            <header className="border-b border-slate-100/90 bg-white/95 px-5 py-4 sm:px-8">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-600">
                    {activeItem?.label || "Tests"}
                  </p>
                  <h2 className="text-2xl font-bold tracking-tight text-slate-900">
                    {pageTitle}
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">{pageSubtitle}</p>
                </div>

                {/* <div className="inline-flex items-center gap-2 self-start rounded-full border border-sky-100 bg-sky-50 px-3 py-1.5 text-xs font-semibold text-sky-700 sm:self-auto">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-500" />
                  Updated {updatedDate}
                </div> */}
              </div>
            </header>

            <main className="flex-1 overflow-auto">
              <div className="mx-auto w-full max-w-[1200px] p-4 sm:p-8">{children}</div>
            </main>
          </div>
        </div>
      </div>
    </div>
  );
}
