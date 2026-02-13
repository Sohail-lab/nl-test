import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle } from "lucide-react";

export default function LoginPage() {
  const [email, setEmail] = useState("sohail@ivp.in");
  const [password, setPassword] = useState("ivp@123");
  const [error, setError] = useState("");

  const navigate = useNavigate();

  const handleLogin = (e) => {
    e.preventDefault();

    if (!email || !password) {
      setError("Please fill in all fields");
      return;
    }

    if (email && password.length >= 6) {
      navigate("/dashboard");
    } else {
      setError("Invalid credentials");
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-secondary flex items-center justify-center p-4">
      <div className="w-full max-w-md shadow-lg bg-white rounded-lg">
        <div className="p-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold">TestAutomation</h1>
            <p className="mt-2">Automate your web testing</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 p-3 bg-red-100 border border-red-300 rounded-lg">
                <AlertCircle className="w-4 h-4 text-red-500" />
                <p className="text-sm text-red-500">{error}</p>
              </div>
            )}

            <div className="space-y-2">
              <label>Email</label>
              <input
                type="email"
                placeholder="you@ivp.in"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setError("");
                }}
                className="border p-2 w-full rounded"
              />
            </div>

            <div className="space-y-2">
              <label>Password</label>
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setError("");
                }}
                className="border p-2 w-full rounded"
              />
            </div>

            <button className="w-full bg-blue-500 text-white p-2 rounded">
              Sign In
            </button>
          </form>

          <div className="mt-6 text-center">
            <p>
              Don't have an account?{" "}
              <button
                onClick={() => navigate("/signup")}
                className="text-blue-500"
              >
                Sign up
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
