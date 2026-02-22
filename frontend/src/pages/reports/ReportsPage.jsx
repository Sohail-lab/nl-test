import React, { useEffect, useState } from "react";
import { FileJson2, Loader2, Network, TerminalSquare, X } from "lucide-react";
import { DashboardLayout } from "../../components/layout/DashboardLayout";
import { Card } from "../../components/ui/card";

export default function ReportsPage() {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [logModal, setLogModal] = useState({
    open: false,
    title: "",
    logs: [],
  });

  useEffect(() => {
    const fetchReports = async () => {
      setLoading(true);
      try {
        const res = await fetch("http://localhost:4000/reports");
        const data = await res.json();
        console.log("Fetched reports:", data);
        setReports(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error("Failed to fetch reports:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchReports();
  }, []);

  const sortedReports = [...reports].sort((a, b) => {
    const getTimestamp = (file) => parseInt(file?.fileName?.split("-")[0]) || 0;
    return getTimestamp(b) - getTimestamp(a);
  });

  const closeLogModal = () => setLogModal({ open: false, title: "", logs: [] });

  return (
    <>
      {logModal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/45 p-4 backdrop-blur-sm">
          <div className="flex h-[85vh] w-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl">
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white/95 px-5 py-4 backdrop-blur">
              <h2 className="pr-4 text-lg font-bold text-slate-900">{logModal.title}</h2>
              <button
                onClick={closeLogModal}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-rose-200 hover:bg-rose-50 hover:text-rose-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
              >
                <X className="h-4 w-4" />
                Close
              </button>
            </div>

            <div className="flex-1 space-y-2 overflow-auto bg-slate-50 p-5 font-mono text-xs text-slate-700">
              {logModal.logs?.length > 0 ? (
                logModal.logs.map((log, i) => (
                  <pre
                    key={i}
                    className="overflow-x-auto rounded-xl border border-slate-200 bg-white p-3 leading-relaxed"
                  >
                    {JSON.stringify(log, null, 2)}
                  </pre>
                ))
              ) : (
                <p className="rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-600">
                  No logs available.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <DashboardLayout>
        <div className="space-y-6">
          <section className="rounded-3xl border border-sky-100 bg-gradient-to-r from-sky-50 via-cyan-50 to-blue-50 p-6 shadow-sm">
            <p className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-wide text-sky-700">
              <FileJson2 className="h-3.5 w-3.5" />
              JSON Reports
            </p>
            <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900">
              All Test Reports
            </h1>
            <p className="mt-2 text-sm text-slate-600">
              Inspect parsed test steps, executed outcomes, console logs, and
              captured network traces for each run.
            </p>
          </section>

          {loading && (
            <Card className="p-10">
              <div className="flex items-center justify-center gap-3 text-slate-600">
                <Loader2 className="h-5 w-5 animate-spin text-sky-600" />
                Loading reports...
              </div>
            </Card>
          )}

          {!loading && sortedReports.length === 0 && (
            <Card className="p-10 text-center">
              <p className="text-sm font-semibold text-slate-700">
                No reports found.
              </p>
              <p className="mt-1 text-sm text-slate-500">
                Execute a test job from the Tests page to generate reports.
              </p>
            </Card>
          )}

          {!loading &&
            sortedReports.map((report, index) => (
              <Card key={report.fileName || index} className="space-y-5 p-5 sm:p-6">
                <div className="flex flex-col gap-3 border-b border-slate-100 pb-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="space-y-1">
                    <h2 className="text-lg font-bold text-slate-900">
                      {report.fileName?.substring(0, 42) || "Unknown File"}
                    </h2>
                    <p className="text-xs text-slate-500">
                      Report #{index + 1}
                    </p>
                  </div>

                  <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700">
                    Job ID: {report.jobId || "N/A"}
                  </div>
                </div>

                {report.parsed?.map((parsedTest, testIndex) => {
                  const executedTest = report.executed?.find(
                    (e) => e.test_name === parsedTest.test_name
                  );

                  return (
                    <div
                      key={testIndex}
                      className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/70 p-4"
                    >
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <h3 className="text-base font-bold text-slate-900">
                          {parsedTest.test_name}
                        </h3>

                        <div className="flex flex-wrap gap-2">
                          <button
                            className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-semibold text-sky-700 transition hover:bg-sky-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
                            onClick={() =>
                              setLogModal({
                                open: true,
                                title: `${parsedTest.test_name} - Console Logs`,
                                logs: executedTest?.consoleLogs || [],
                              })
                            }
                          >
                            <TerminalSquare className="h-3.5 w-3.5" />
                            Console Logs
                          </button>

                          <button
                            className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 transition hover:bg-emerald-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
                            onClick={() =>
                              setLogModal({
                                open: true,
                                title: `${parsedTest.test_name} - Network Logs`,
                                logs: executedTest?.networkLogs || [],
                              })
                            }
                          >
                            <Network className="h-3.5 w-3.5" />
                            Network Logs
                          </button>
                        </div>
                      </div>

                      <div>
                        <p className="mb-2 text-sm font-semibold text-slate-700">
                          Parsed Steps
                        </p>
                        <ol className="space-y-1 rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-700">
                          {parsedTest.steps?.length > 0 ? (
                            parsedTest.steps.map((step, stepIndex) => (
                              <li key={stepIndex} className="list-decimal list-inside">
                                {step}
                              </li>
                            ))
                          ) : (
                            <li className="list-none text-slate-500">
                              No parsed steps available.
                            </li>
                          )}
                        </ol>
                      </div>

                      <div>
                        <p className="mb-2 text-sm font-semibold text-slate-700">
                          Executed Results
                        </p>
                        <ul className="space-y-1 rounded-xl border border-slate-200 bg-white p-3 text-sm">
                          {executedTest?.results?.length > 0 ? (
                            executedTest.results.map((result, resIndex) => (
                              <li
                                key={resIndex}
                                className={`rounded-md px-2 py-1 ${
                                  result.ok === false
                                    ? "bg-rose-50 text-rose-700"
                                    : "bg-emerald-50 text-emerald-700"
                                }`}
                              >
                                {result.step !== undefined ? `Step ${result.step}: ` : ""}
                                {result.description || result.action || "navigate"}
                                {result.locator && ` | Locator: ${result.locator}`}
                                {result.validated_text &&
                                  ` | Validated: ${result.validated_text}`}
                                {result.error && ` | Error: ${result.error}`}
                                {result.ok !== undefined && ` | OK: ${result.ok}`}
                              </li>
                            ))
                          ) : (
                            <li className="rounded-md bg-slate-100 px-2 py-1 text-slate-500">
                              No execution results available.
                            </li>
                          )}
                        </ul>
                      </div>
                    </div>
                  );
                })}
              </Card>
            ))}
        </div>
      </DashboardLayout>
    </>
  );
}
