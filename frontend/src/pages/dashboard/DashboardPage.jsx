import React, { useState, useRef, useEffect } from "react";
import { DashboardLayout } from "../../components/layout/DashboardLayout";
import { Card } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";

const API = "http://localhost:4000";

export default function DashboardPage() {
  const [file, setFile] = useState(null);
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null); // pending, running, completed, failed
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(null); // Progress tracking
  const fileInputRef = useRef();
  const pollIntervalRef = useRef(null);

  // Poll job status and progress every 500ms
  useEffect(() => {
    if (!jobId) return;

    const pollStatus = async () => {
      try {
        // Poll job status
        const statusRes = await fetch(`${API}/jobs/${jobId}`);
        if (statusRes.ok) {
          const statusData = await statusRes.json();
          setJobStatus(statusData.status);

          // Poll progress
          try {
            const progressRes = await fetch(`${API}/jobs-progress/${jobId}`);
            if (progressRes.ok) {
              const progressData = await progressRes.json();
              setProgress(progressData);
            }
          } catch (e) {
            // Progress might not be available yet
          }

          if (statusData.status === 'completed' || statusData.status === 'failed') {
            // Job is done, fetch result
            try {
              const resultRes = await fetch(`${API}/jobs-result/${jobId}`);
              if (resultRes.ok) {
                const resultData = await resultRes.json();
                setResult(resultData);
                setLoading(false);
                if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
              }
            } catch (e) {
              console.error('Failed to fetch result:', e);
              setLoading(false);
            }
          }
        }
      } catch (e) {
        console.error('Failed to poll status:', e);
      }
    };

    // Poll immediately and then every 500ms for faster updates
    pollStatus();
    pollIntervalRef.current = setInterval(pollStatus, 500);

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [jobId]);

  // Handle file selection via input or drop
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

  // Handle stopping the test
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
      console.error('Failed to send stop signal:', e);
      setMessage("Error sending stop signal.");
    }
  };

  // Handle file upload and execution
  const handleUpload = async () => {
    if (!file) return setMessage("Please select an Excel file first!");
    if (!websiteUrl) return setMessage("Please enter a website URL!");

    const formData = new FormData();
    formData.append("testFile", file);
    formData.append("websiteUrl", websiteUrl);

    setLoading(true);
    setMessage("");
    setJobId(null);
    setJobStatus(null);
    setResult(null);

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
        setMessage(`Error: ${data.error || 'Unknown error'}`);
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
    setMessage("");
    setLoading(false);
  };

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold">Upload Test Excel</h2>

        {/* Upload Form */}
        {!jobId && (
          <Card className="p-6 flex flex-col gap-4 items-start">
            {/* Website URL */}
            <Input
              placeholder="Enter website URL (e.g., https://example.com)"
              value={websiteUrl}
              onChange={(e) => setWebsiteUrl(e.target.value)}
              className="w-full"
            />

            {/* File input with drag & drop */}
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              className="w-full border-2 border-dashed border-gray-300 rounded p-6 text-center cursor-pointer hover:border-blue-600"
              onClick={() => fileInputRef.current.click()}
            >
              {file ? (
                <p>Selected file: <strong>{file.name}</strong></p>
              ) : (
                <p>Drag & drop an Excel file here or click to select</p>
              )}
              <input
                type="file"
                accept=".xls,.xlsx"
                ref={fileInputRef}
                onChange={handleFileChange}
                className="hidden"
              />
            </div>

            {/* Upload Button */}
            <Button
              onClick={handleUpload}
              disabled={loading}
              className="bg-blue-600 text-white mt-2"
            >
              {loading ? "Uploading..." : "Upload & Execute"}
            </Button>

            {/* Message */}
            {message && (
              <p className={`mt-2 font-medium ${message.includes('Error') ? 'text-red-600' : 'text-green-600'}`}>
                {message}
              </p>
            )}
          </Card>
        )}

        {/* Stop Button (during execution) */}
        {jobId && jobStatus === 'running' && (
          <div className="flex gap-2">
            <Button
              onClick={handleStop}
              className="bg-red-600 hover:bg-red-700 text-white"
            >
              ⏹ Stop Test
            </Button>
            <Button
              onClick={resetForm}
              className="bg-gray-500 hover:bg-gray-600 text-white"
            >
              Reset
            </Button>
          </div>
        )}

        {/* Job Status Card */}
        {jobId && (
          <Card className="p-6 flex flex-col gap-4">
            <h3 className="text-lg font-bold">Job Status</h3>
            <div className="space-y-2">
              <p>
                <strong>Job ID:</strong> <code className="bg-gray-100 px-2 py-1 rounded">{jobId}</code>
              </p>
              <p>
                <strong>Status:</strong>{" "}
                <span className={`px-2 py-1 rounded font-medium ${
                  jobStatus === 'completed' ? 'bg-green-100 text-green-800' :
                  jobStatus === 'failed' ? 'bg-red-100 text-red-800' :
                  jobStatus === 'running' ? 'bg-blue-100 text-blue-800' :
                  'bg-gray-100 text-gray-800'
                }`}>
                  {jobStatus || 'pending'}
                </span>
              </p>
            </div>

            {jobStatus !== 'completed' && jobStatus !== 'failed' && (
              <div className="mt-4 p-4 bg-blue-50 rounded border border-blue-200">
                <h4 className="font-bold mb-3 text-blue-900">Execution Progress</h4>
                
                {progress && (
                  <div className="space-y-3">
                    <div className="text-sm">
                      <p className="font-semibold">Progress: {progress.currentStep}/{progress.totalSteps} steps</p>
                      <div className="w-full bg-gray-300 rounded-full h-2 mt-1">
                        <div 
                          className="bg-blue-600 h-2 rounded-full transition-all"
                          style={{width: `${progress.totalSteps > 0 ? (progress.currentStep / progress.totalSteps * 100) : 0}%`}}
                        ></div>
                      </div>
                    </div>

                    {progress.completedSteps && progress.completedSteps.length > 0 && (
                      <div>
                        <p className="text-sm font-semibold text-green-700">✓ Completed ({progress.completedSteps.length}):</p>
                        <div className="bg-white rounded p-2 text-xs max-h-32 overflow-y-auto">
                          {progress.completedSteps.map((s, i) => (
                            <div key={i} className="text-green-600">
                              Step {s.step}: {s.description || s.action}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {progress.failedSteps && progress.failedSteps.length > 0 && (
                      <div>
                        <p className="text-sm font-semibold text-red-700">✗ Failed ({progress.failedSteps.length}):</p>
                        <div className="bg-white rounded p-2 text-xs max-h-32 overflow-y-auto">
                          {progress.failedSteps.map((s, i) => (
                            <div key={i} className="text-red-600">
                              Step {s.step + 1}: {s.description || s.action} - {s.error?.slice(0, 50)}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {progress.totalSteps > (progress.completedSteps?.length || 0) + (progress.failedSteps?.length || 0) && (
                      <div>
                        <p className="text-sm font-semibold text-gray-700">Currently Executing:</p>
                        <div className="bg-blue-50 p-2 rounded border border-blue-200 text-xs text-blue-900">
                          <p className="font-semibold">Step {progress.currentStep + 1}/{progress.totalSteps}</p>
                          <p className="mt-1">{progress.currentDescription || 'Processing...'}</p>
                        </div>
                        <p className="text-xs text-gray-600 mt-2">
                          Waiting for {progress.totalSteps - ((progress.completedSteps?.length || 0) + (progress.failedSteps?.length || 0))} more steps...
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {!progress && (
                  <div className="flex items-center gap-2">
                    <div className="animate-spin w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full"></div>
                    <span className="text-sm">Initializing execution...</span>
                  </div>
                )}
              </div>
            )}

            {/* Results */}
            {result && (
              <div className="mt-4 p-4 bg-gray-50 rounded border border-gray-200">
                <h4 className="font-bold mb-2 text-lg">Test Results</h4>
                {result.success ? (
                  <div className="space-y-3 text-sm">
                    {result.executed && Array.isArray(result.executed) && (
                      <div>
                        <p className="font-semibold text-blue-800 mb-3">
                          Test Cases: {result.executed.length}
                        </p>
                        
                        <div className="space-y-2">
                          {result.executed.map((testCase, testIdx) => {
                            const testPassed = testCase.results && testCase.results.every(r => r.ok !== false);
                            const totalSteps = testCase.results ? testCase.results.length : 0;
                            const passedSteps = testCase.results ? testCase.results.filter(r => r.ok).length : 0;
                            
                            return (
                              <details key={testIdx} className="bg-white rounded border border-gray-300 overflow-hidden">
                                <summary className={`p-3 cursor-pointer font-semibold text-sm flex justify-between items-center hover:bg-gray-100 ${
                                  testPassed ? 'text-green-700 bg-green-50' : 'text-red-700 bg-red-50'
                                }`}>
                                  <span className="flex-1">
                                    {testPassed ? '✓' : '✗'} {testCase.test_name}
                                  </span>
                                  <span className="text-xs text-gray-600 font-normal">
                                    {passedSteps}/{totalSteps} steps passed
                                  </span>
                                </summary>
                                
                                <div className="p-4 border-t border-gray-200 space-y-2 max-h-96 overflow-y-auto">
                                  {testCase.results && testCase.results.map((step, stepIdx) => (
                                    <div key={stepIdx} className={`text-xs p-2 rounded border-l-4 ${
                                      step.ok ? 'border-green-500 bg-green-50 text-green-800' : 'border-red-500 bg-red-50 text-red-800'
                                    }`}>
                                      <div className="font-semibold">
                                        Step {step.step + 1}: {step.description || step.action}
                                      </div>
                                      {step.action && (
                                        <div className="text-xs text-gray-600 mt-1">
                                          Action: <strong>{step.action}</strong>
                                          {step.value && ` | Value: ${String(step.value).substring(0, 40)}`}
                                        </div>
                                      )}
                                      {step.error && (
                                        <div className="text-xs mt-1 font-mono bg-red-100 p-1 rounded">
                                          Error: {step.error}
                                        </div>
                                      )}
                                      {step.locator && (
                                        <div className="text-xs mt-1 font-mono bg-gray-100 p-1 rounded">
                                          Locator ({step.type}): {String(step.locator).substring(0, 60)}...
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
                      <div className="mt-4 pt-4 border-t border-gray-300">
                        <p className="font-semibold text-blue-800 mb-2">Parsed Test Cases:</p>
                        <details>
                          <summary className="cursor-pointer text-xs text-gray-600 hover:text-gray-800">View Details</summary>
                          <pre className="bg-white p-2 rounded text-xs overflow-auto max-h-48 border border-gray-300 mt-1">
                            {JSON.stringify(result.parsed, null, 2)}
                          </pre>
                        </details>
                      </div>
                    )}
                  </div>
                ) : (
                  <div>
                    <p className="text-red-700 font-semibold">✗ Processing failed</p>
                    <p className="text-sm mt-1 text-red-600">{result.error || 'Unknown error'}</p>
                  </div>
                )}
              </div>
            )}

            {/* Reset Button */}
            <Button onClick={resetForm} className="bg-gray-600 text-white mt-4">
              Start New Job
            </Button>
          </Card>
        )}
      </div>
    </DashboardLayout>
  );
}
