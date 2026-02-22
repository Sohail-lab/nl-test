import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  CheckCircle2,
  Clock3,
  FileSpreadsheet,
  Globe,
  Loader2,
  PlayCircle,
  RefreshCcw,
  StopCircle,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { DashboardLayout } from "../../components/layout/DashboardLayout";
import { Card } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";

const API = "http://localhost:4000";

export default function DashboardPage() {
  const [file, setFile] = useState(null);
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(null);
  const [savedUrls, setSavedUrls] = useState([]);
  const [savedUrlsLoading, setSavedUrlsLoading] = useState(false);
  const [saveUrlModalOpen, setSaveUrlModalOpen] = useState(false);
  const [saveUrlName, setSaveUrlName] = useState("");
  const [savingUrl, setSavingUrl] = useState(false);
  const [selectedSavedName, setSelectedSavedName] = useState("");
  const fileInputRef = useRef();
  const pollIntervalRef = useRef(null);

  const normalizeHttpUrl = (value) => {
    try {
      const parsed = new URL(String(value || "").trim());
      if (!["http:", "https:"].includes(parsed.protocol)) return null;
      return parsed.toString();
    } catch {
      return null;
    }
  };

  const loadSavedUrls = async () => {
    setSavedUrlsLoading(true);
    try {
      const res = await fetch(`${API}/saved-urls`);
      const data = await res.json();
      if (res.ok && Array.isArray(data.savedUrls)) {
        setSavedUrls(data.savedUrls);
      } else {
        setSavedUrls([]);
      }
    } catch (e) {
      console.error("Failed to load saved URLs:", e);
      setSavedUrls([]);
    } finally {
      setSavedUrlsLoading(false);
    }
  };

  useEffect(() => {
    loadSavedUrls();
  }, []);

  useEffect(() => {
    if (!jobId) return;

    const pollStatus = async () => {
      try {
        const statusRes = await fetch(`${API}/jobs/${jobId}`);
        if (statusRes.ok) {
          const statusData = await statusRes.json();
          setJobStatus(statusData.status);

          try {
            const progressRes = await fetch(`${API}/jobs-progress/${jobId}`);
            if (progressRes.ok) {
              const progressData = await progressRes.json();
              setProgress(progressData);
            }
          } catch {
            // Progress can be unavailable at startup.
          }

          if (statusData.status === "completed" || statusData.status === "failed") {
            try {
              const resultRes = await fetch(`${API}/jobs-result/${jobId}`);
              if (resultRes.ok) {
                const resultData = await resultRes.json();
                setResult(resultData);
                setLoading(false);
                if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
              }
            } catch (e) {
              console.error("Failed to fetch result:", e);
              setLoading(false);
            }
          }
        }
      } catch (e) {
        console.error("Failed to poll status:", e);
      }
    };

    pollStatus();
    pollIntervalRef.current = setInterval(pollStatus, 500);

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [jobId]);

  useEffect(() => {
    if (!selectedSavedName) return;
    const exists = savedUrls.some((entry) => entry.name === selectedSavedName);
    if (!exists) setSelectedSavedName("");
  }, [savedUrls, selectedSavedName]);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) setFile(selectedFile);
    setMessage("");
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) setFile(droppedFile);
    setMessage("");
  };

  const handleDragOver = (e) => e.preventDefault();

  const handleImportSavedUrl = (name) => {
    setSelectedSavedName(name);
    const selected = savedUrls.find((entry) => entry.name === name);
    if (!selected) return;
    setWebsiteUrl(selected.url);
    setMessage(`Imported URL: ${selected.name}`);
  };

  const openSaveUrlModal = () => {
    if (!normalizeHttpUrl(websiteUrl)) {
      setMessage("Error: Enter a valid http(s) URL before saving.");
      return;
    }
    setSaveUrlName("");
    setSaveUrlModalOpen(true);
  };

  const closeSaveUrlModal = () => {
    if (savingUrl) return;
    setSaveUrlModalOpen(false);
    setSaveUrlName("");
  };

  const handleSaveUrl = async () => {
    const normalizedWebsiteUrl = normalizeHttpUrl(websiteUrl);
    if (!normalizedWebsiteUrl) {
      setMessage("Error: Enter a valid http(s) URL before saving.");
      return;
    }

    const trimmedName = saveUrlName.trim();
    if (!trimmedName) {
      setMessage("Error: URL name is required.");
      return;
    }

    setSavingUrl(true);
    try {
      const res = await fetch(`${API}/saved-urls`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: trimmedName,
          url: normalizedWebsiteUrl,
        }),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMessage(`Error: ${data.error || "Failed to save URL."}`);
        return;
      }

      setSaveUrlModalOpen(false);
      setSaveUrlName("");
      setSelectedSavedName(trimmedName);
      setMessage(`Saved URL: ${trimmedName}`);
      await loadSavedUrls();
    } catch (e) {
      console.error("Failed to save URL:", e);
      setMessage("Error: Failed to save URL.");
    } finally {
      setSavingUrl(false);
    }
  };

  const handleStop = async () => {
    if (!jobId) return;

    try {
      const res = await fetch(`${API}/jobs-stop/${jobId}`, {
        method: "POST",
      });

      if (res.ok) {
        setMessage("Stop signal sent. Test will stop at the next step.");
      } else {
        setMessage("Failed to send stop signal.");
      }
    } catch (e) {
      console.error("Failed to send stop signal:", e);
      setMessage("Error sending stop signal.");
    }
  };

  const handleUpload = async () => {
    if (!file) return setMessage("Please select an Excel file first.");
    if (!websiteUrl) return setMessage("Please enter a website URL.");

    const formData = new FormData();
    formData.append("testFile", file);
    formData.append("websiteUrl", websiteUrl);

    setLoading(true);
    setMessage("");
    setJobId(null);
    setJobStatus(null);
    setResult(null);
    setProgress(null);

    try {
      const res = await fetch(`${API}/upload-test`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (res.ok && data.jobId) {
        setJobId(data.jobId);
        setJobStatus("pending");
        setMessage(`Job created: ${data.jobId}. Processing...`);
      } else {
        setLoading(false);
        setMessage(`Error: ${data.error || "Unknown error"}`);
      }
    } catch (err) {
      console.error(err);
      setLoading(false);
      setMessage("Upload failed. Try again.");
    }
  };

  const resetForm = () => {
    setFile(null);
    setWebsiteUrl("");
    setJobId(null);
    setJobStatus(null);
    setResult(null);
    setProgress(null);
    setMessage("");
    setLoading(false);
    setSelectedSavedName("");
    setSaveUrlModalOpen(false);
    setSaveUrlName("");
    setSavingUrl(false);
  };

  const statusTone = {
    completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    failed: "bg-rose-50 text-rose-700 border-rose-200",
    running: "bg-sky-50 text-sky-700 border-sky-200",
    pending: "bg-slate-100 text-slate-700 border-slate-200",
  };
  const isTerminalStatus = jobStatus === "completed" || jobStatus === "failed";
  const completedCount = progress?.completedSteps?.length || 0;
  const failedCount = progress?.failedSteps?.length || 0;
  const completionPercent =
    progress?.totalSteps > 0
      ? Math.round((progress.currentStep / progress.totalSteps) * 100)
      : 0;
  const remainingSteps = progress
    ? Math.max(progress.totalSteps - (completedCount + failedCount), 0)
    : 0;
  const isMessageError = /error|failed/i.test(message);

  return (
    <>
      {saveUrlModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/45 p-4 backdrop-blur-sm"
          onClick={closeSaveUrlModal}
        >
          <div
            className="w-full max-w-lg rounded-3xl border border-slate-200 bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <h2 className="text-lg font-bold text-slate-900">Save Target URL</h2>
              <button
                onClick={closeSaveUrlModal}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-rose-200 hover:bg-rose-50 hover:text-rose-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
                disabled={savingUrl}
              >
                Close
              </button>
            </div>

            <div className="space-y-4 p-5">
              <div>
                <label className="mb-2 block text-sm font-semibold text-slate-700">
                  URL
                </label>
                <Input
                  value={normalizeHttpUrl(websiteUrl) || websiteUrl}
                  readOnly
                  className="bg-slate-100 text-slate-600"
                />
              </div>

              <div>
                <label className="mb-2 block text-sm font-semibold text-slate-700">
                  URL Name
                </label>
                <Input
                  placeholder="Example: UAT, Staging, Production"
                  value={saveUrlName}
                  onChange={(e) => setSaveUrlName(e.target.value)}
                  autoFocus
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 border-t border-slate-200 bg-slate-50/60 px-5 py-4">
              <Button variant="outline" onClick={closeSaveUrlModal} disabled={savingUrl}>
                Cancel
              </Button>
              <Button onClick={handleSaveUrl} disabled={savingUrl}>
                {savingUrl ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  "Save URL"
                )}
              </Button>
            </div>
          </div>
        </div>
      )}

      <DashboardLayout>
      <div className="mx-auto max-w-5xl space-y-6">
        <section className="rounded-3xl border border-sky-100 bg-gradient-to-r from-sky-50 via-cyan-50 to-blue-50 p-6 shadow-sm">
          <p className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-wide text-sky-700">
            <Activity className="h-3.5 w-3.5" />
            Test Orchestration
          </p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900">
            Launch Web Automation from Excel Scenarios
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Provide your target website and upload an Excel suite. The system will
            execute your workflow and stream job progress, step outcomes, and final
            diagnostics here.
          </p>
        </section>

        {!jobId && (
          <Card className="p-6 sm:p-8">
            <div className="space-y-6">
              <div>
                <label className="mb-2 inline-flex items-center gap-2 text-sm font-semibold text-slate-700">
                  <Globe className="h-4 w-4 text-sky-600" />
                  Target Website URL
                </label>
                <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-3 sm:p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                    <div className="min-w-0 flex-1">
                      <Input
                        placeholder="https://example.com"
                        value={websiteUrl}
                        onChange={(e) => {
                          setWebsiteUrl(e.target.value);
                          setSelectedSavedName("");
                        }}
                        className="w-full"
                      />
                    </div>

                    <div className="flex flex-col gap-3 sm:flex-row lg:w-auto">
                      <Select
                        value={selectedSavedName || undefined}
                        onValueChange={handleImportSavedUrl}
                        disabled={savedUrlsLoading || savedUrls.length === 0}
                      >
                        <SelectTrigger className="w-full min-w-[220px] bg-white sm:w-[240px]">
                          <SelectValue
                            placeholder={
                              savedUrlsLoading
                                ? "Loading saved URLs..."
                                : "Import saved URL"
                            }
                          />
                        </SelectTrigger>
                        <SelectContent>
                          {savedUrls.map((entry) => (
                            <SelectItem key={entry.name} value={entry.name}>
                              {entry.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>

                      <Button
                        variant="outline"
                        onClick={openSaveUrlModal}
                        disabled={!websiteUrl || savingUrl}
                        className="min-w-32"
                      >
                        Save URL
                      </Button>
                    </div>
                  </div>

                  <p className="mt-2 text-xs font-semibold text-slate-500">
                    {savedUrlsLoading
                      ? "Loading saved URLs..."
                      : savedUrls.length > 0
                      ? `${savedUrls.length} saved URL${savedUrls.length === 1 ? "" : "s"} available`
                      : "No saved URLs yet. Save one to import quickly later."}
                  </p>
                </div>
              </div>

              <div>
                <label className="mb-2 inline-flex items-center gap-2 text-sm font-semibold text-slate-700">
                  <FileSpreadsheet className="h-4 w-4 text-sky-600" />
                  Excel Test File
                </label>
                <div
                  onDrop={handleDrop}
                  onDragOver={handleDragOver}
                  onClick={() => fileInputRef.current.click()}
                  className="cursor-pointer rounded-2xl border-2 border-dashed border-sky-200 bg-sky-50/50 p-8 text-center transition hover:border-sky-400 hover:bg-sky-50"
                >
                  <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-white text-sky-600 shadow-sm">
                    <UploadCloud className="h-6 w-6" />
                  </div>
                  {file ? (
                    <p className="text-sm font-semibold text-slate-800">
                      Selected file: <span className="text-sky-700">{file.name}</span>
                    </p>
                  ) : (
                    <p className="text-sm text-slate-600">
                      Drag and drop an Excel file here, or click to select.
                    </p>
                  )}

                  <input
                    type="file"
                    accept=".xls,.xlsx"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    className="hidden"
                  />
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={handleUpload} disabled={loading} className="min-w-44">
                  {loading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <PlayCircle className="h-4 w-4" />
                      Upload & Execute
                    </>
                  )}
                </Button>

                {message && (
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${
                      isMessageError
                        ? "bg-rose-50 text-rose-700"
                        : "bg-emerald-50 text-emerald-700"
                    }`}
                  >
                    {message}
                  </span>
                )}
              </div>
            </div>
          </Card>
        )}

        {jobId && (
          <Card className="overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/60 p-6">
              <div>
                <h3 className="text-lg font-bold text-slate-900">Live Job Status</h3>
                <p className="text-sm text-slate-600">
                  Track run state, progress, and detailed step results.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {jobStatus === "running" && (
                  <Button onClick={handleStop} variant="destructive">
                    <StopCircle className="h-4 w-4" />
                    Stop Test
                  </Button>
                )}
                <Button onClick={resetForm} variant="outline">
                  <RefreshCcw className="h-4 w-4" />
                  Start New Job
                </Button>
              </div>
            </div>

            <div className="space-y-6 p-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Job ID
                  </p>
                  <code className="mt-2 block rounded-lg bg-slate-100 px-3 py-2 text-sm font-semibold text-slate-800">
                    {jobId}
                  </code>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Status
                  </p>
                  <span
                    className={`mt-2 inline-flex rounded-full border px-3 py-1 text-sm font-semibold ${
                      statusTone[jobStatus] || statusTone.pending
                    }`}
                  >
                    {jobStatus || "pending"}
                  </span>
                </div>
              </div>

              {!isTerminalStatus && (
                <div className="rounded-2xl border border-sky-200 bg-sky-50/60 p-5">
                  <h4 className="mb-3 text-base font-bold text-slate-900">
                    Execution Progress
                  </h4>

                  {progress ? (
                    <div className="space-y-4">
                      <div>
                        <div className="flex items-center justify-between text-sm font-semibold text-slate-700">
                          <span>
                            Step {progress.currentStep}/{progress.totalSteps}
                          </span>
                          <span>{completionPercent}%</span>
                        </div>
                        <div className="mt-2 h-2.5 w-full rounded-full bg-slate-200">
                          <div
                            className="h-2.5 rounded-full bg-gradient-to-r from-sky-500 to-cyan-500 transition-all"
                            style={{ width: `${completionPercent}%` }}
                          />
                        </div>
                      </div>

                      {progress.completedSteps && progress.completedSteps.length > 0 && (
                        <div>
                          <p className="mb-2 inline-flex items-center gap-2 text-sm font-semibold text-emerald-700">
                            <CheckCircle2 className="h-4 w-4" />
                            Completed ({progress.completedSteps.length})
                          </p>
                          <div className="max-h-36 space-y-1 overflow-y-auto rounded-xl border border-emerald-200 bg-white p-2 text-xs">
                            {progress.completedSteps.map((s, i) => (
                              <div key={i} className="rounded-md bg-emerald-50 px-2 py-1 text-emerald-700">
                                Step {s.step}: {s.description || s.action}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {progress.failedSteps && progress.failedSteps.length > 0 && (
                        <div>
                          <p className="mb-2 inline-flex items-center gap-2 text-sm font-semibold text-rose-700">
                            <XCircle className="h-4 w-4" />
                            Failed ({progress.failedSteps.length})
                          </p>
                          <div className="max-h-36 space-y-1 overflow-y-auto rounded-xl border border-rose-200 bg-white p-2 text-xs">
                            {progress.failedSteps.map((s, i) => (
                              <div key={i} className="rounded-md bg-rose-50 px-2 py-1 text-rose-700">
                                Step {s.step + 1}: {s.description || s.action} -{" "}
                                {s.error?.slice(0, 50)}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {progress.totalSteps > completedCount + failedCount && (
                        <div className="rounded-xl border border-sky-200 bg-white p-3">
                          <p className="text-sm font-semibold text-slate-800">
                            Currently Executing
                          </p>
                          <p className="mt-1 text-xs font-semibold text-sky-700">
                            Step {progress.currentStep + 1}/{progress.totalSteps}
                          </p>
                          <p className="mt-1 text-sm text-slate-600">
                            {progress.currentDescription || "Processing..."}
                          </p>
                          <p className="mt-2 text-xs text-slate-500">
                            Waiting for {remainingSteps} more steps...
                          </p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-2 text-sm text-slate-700">
                      <Loader2 className="h-4 w-4 animate-spin text-sky-600" />
                      Initializing execution...
                    </div>
                  )}
                </div>
              )}

              {result && (
                <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-5">
                  <h4 className="mb-3 text-lg font-bold text-slate-900">Test Results</h4>
                  {result.success ? (
                    <div className="space-y-4 text-sm">
                      {result.executed && Array.isArray(result.executed) && (
                        <div>
                          <p className="mb-3 text-sm font-semibold text-sky-800">
                            Test Cases: {result.executed.length}
                          </p>

                          <div className="space-y-2">
                            {result.executed.map((testCase, testIdx) => {
                              const testPassed =
                                testCase.results &&
                                testCase.results.every((r) => r.ok !== false);
                              const totalSteps = testCase.results
                                ? testCase.results.length
                                : 0;
                              const passedSteps = testCase.results
                                ? testCase.results.filter((r) => r.ok).length
                                : 0;

                              return (
                                <details
                                  key={testIdx}
                                  className="overflow-hidden rounded-xl border border-slate-200 bg-white"
                                >
                                  <summary
                                    className={`flex cursor-pointer items-center justify-between gap-3 p-3 text-sm font-semibold ${
                                      testPassed
                                        ? "bg-emerald-50 text-emerald-700"
                                        : "bg-rose-50 text-rose-700"
                                    }`}
                                  >
                                    <span className="inline-flex items-center gap-2">
                                      {testPassed ? (
                                        <CheckCircle2 className="h-4 w-4" />
                                      ) : (
                                        <XCircle className="h-4 w-4" />
                                      )}
                                      {testCase.test_name}
                                    </span>
                                    <span className="text-xs font-medium text-slate-600">
                                      {passedSteps}/{totalSteps} steps passed
                                    </span>
                                  </summary>

                                  <div className="max-h-96 space-y-2 overflow-y-auto border-t border-slate-200 p-4">
                                    {testCase.results &&
                                      testCase.results.map((step, stepIdx) => (
                                        <div
                                          key={stepIdx}
                                          className={`rounded-lg border-l-4 p-2 text-xs ${
                                            step.ok
                                              ? "border-emerald-500 bg-emerald-50 text-emerald-800"
                                              : "border-rose-500 bg-rose-50 text-rose-800"
                                          }`}
                                        >
                                          <div className="font-semibold">
                                            Step {step.step + 1}:{" "}
                                            {step.description || step.action}
                                          </div>
                                          {step.action && (
                                            <div className="mt-1 text-slate-700">
                                              Action: <strong>{step.action}</strong>
                                              {step.value &&
                                                ` | Value: ${String(step.value).substring(0, 40)}`}
                                            </div>
                                          )}
                                          {step.error && (
                                            <div className="mt-1 rounded bg-rose-100 p-1 font-mono text-rose-700">
                                              Error: {step.error}
                                            </div>
                                          )}
                                          {step.locator && (
                                            <div className="mt-1 rounded bg-slate-100 p-1 font-mono text-slate-700">
                                              Locator ({step.type}):{" "}
                                              {String(step.locator).substring(0, 60)}...
                                            </div>
                                          )}
                                        </div>
                                      ))}
                                  </div>
                                </details>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {result.parsed && (
                        <div className="border-t border-slate-200 pt-4">
                          <p className="mb-2 text-sm font-semibold text-sky-800">
                            Parsed Test Cases
                          </p>
                          <details>
                            <summary className="cursor-pointer text-xs font-semibold text-slate-600 hover:text-slate-800">
                              View Parsed JSON
                            </summary>
                            <pre className="mt-2 max-h-56 overflow-auto rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-700">
                              {JSON.stringify(result.parsed, null, 2)}
                            </pre>
                          </details>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div>
                      <p className="inline-flex items-center gap-2 text-sm font-semibold text-rose-700">
                        <XCircle className="h-4 w-4" />
                        Processing failed
                      </p>
                      <p className="mt-1 text-sm text-rose-600">
                        {result.error || "Unknown error"}
                      </p>
                    </div>
                  )}
                </div>
              )}

              {message && (
                <div
                  className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ${
                    isMessageError
                      ? "bg-rose-50 text-rose-700"
                      : "bg-emerald-50 text-emerald-700"
                  }`}
                >
                  <Clock3 className="h-3.5 w-3.5" />
                  {message}
                </div>
              )}
            </div>
          </Card>
        )}
      </div>
      </DashboardLayout>
    </>
  );
}
