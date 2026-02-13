import React, { useState, useEffect } from "react";
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

  if (loading) return <p>Loading reports...</p>;

  const sortedReports = [...reports].sort((a, b) => {
    const getTimestamp = (file) =>
      parseInt(file?.fileName?.split("-")[0]) || 0;

    return getTimestamp(b) - getTimestamp(a); // Descending (Newest first)
  });


  return (
    <>
      {
        logModal.open && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-xl w-[80%] h-[80%] flex flex-col">

              {/* Header */}
              <div className="flex justify-between items-center border-b p-4">
                <h2 className="text-xl font-semibold">{logModal.title}</h2>

                <button
                  onClick={() => setLogModal({ open: false, title: "", logs: [] })}
                  className="px-3 py-1 bg-red-500 text-white rounded"
                >
                  Close
                </button>
              </div>

              {/* Scrollable Logs */}
              <div className="flex-1 overflow-auto p-4 font-mono text-sm whitespace-pre-wrap">
                {logModal.logs?.length > 0 ? (
                  logModal.logs.map((log, i) => (
                    <div key={i} className="border-b py-1">
                      {JSON.stringify(log, null, 2)}
                    </div>
                  ))
                ) : (
                  <p>No logs available</p>
                )}
              </div>
            </div>
          </div>
        )
      }

      <DashboardLayout>
        <div className="space-y-6">
          <h1 className="text-3xl font-bold mb-4">All Test Reports</h1>

          {sortedReports.map((report, index) => (
            <Card key={report.fileName || index} className="p-4 space-y-4">
              <h2 className="text-lg font-semibold">
                {report.fileName.substring(0,25) || "Unknown File"}
              </h2>

              <div>
                <strong>Job ID:</strong> {report.jobId || "N/A"}
              </div>

              {/* Loop Tests */}
              {report.parsed?.map((parsedTest, testIndex) => {
                const executedTest = report.executed?.find(
                  (e) => e.test_name === parsedTest.test_name
                );

                return (
                  <div
                    key={testIndex}
                    className="border rounded-lg p-3 bg-muted/30 space-y-2"
                  >
                    <div className="flex justify-between items-center">
                      <h3 className="font-semibold text-primary">
                        {parsedTest.test_name}
                      </h3>

                      <div className="space-x-2">
                        <button
                          className="px-3 py-1 bg-blue-500 text-white rounded text-sm"
                          onClick={() =>
                            setLogModal({
                              open: true,
                              title: `${parsedTest.test_name} - Console Logs`,
                              logs: executedTest?.consoleLogs || [],
                            })
                          }
                        >
                          Console Logs
                        </button>

                        <button
                          className="px-3 py-1 bg-green-500 text-white rounded text-sm"
                          onClick={() =>
                            setLogModal({
                              open: true,
                              title: `${parsedTest.test_name} - Network Logs`,
                              logs: executedTest?.networkLogs || [],
                            })
                          }
                        >
                          Network Logs
                        </button>
                      </div>
                    </div>


                    {/* Parsed Steps */}
                    <div>
                      <p className="font-medium">Parsed Steps:</p>
                      <ul className="list-disc ml-6">
                        {parsedTest.steps?.map((step, stepIndex) => (
                          <li key={stepIndex}>{step}</li>
                        ))}
                      </ul>
                    </div>

                    {/* Executed Steps */}
                    <div>
                      <p className="font-medium">Executed Results:</p>
                      <ul className="list-disc ml-6">
                        {executedTest?.results?.map((result, resIndex) => (
                          <li
                            key={resIndex}
                            className={
                              result.ok === false
                                ? "text-red-500 font-medium"
                                : ""
                            }
                          >
                            {result.step !== undefined
                              ? `Step ${result.step}: `
                              : ""}

                            {result.description || result.action || "navigate"}

                            {result.locator && ` | Locator: ${result.locator}`}

                            {result.validated_text &&
                              ` | Validated: ${result.validated_text}`}

                            {result.error && ` | Error: ${result.error}`}

                            {result.ok !== undefined &&
                              ` | OK: ${result.ok}`}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                );
              })}
            </Card>
          ))}


        </div>
      </DashboardLayout >
    </>
  );
}
