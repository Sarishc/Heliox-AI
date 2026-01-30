"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { fetchJson, setStoredAccessToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [teamId, setTeamId] = useState("");
  const [showGoogleLogin, setShowGoogleLogin] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  useEffect(() => {
    // Check for OAuth errors in URL
    const errorParam = searchParams.get("error");
    const messageParam = searchParams.get("message");
    
    if (errorParam === "domain_not_allowed") {
      setError("Your email domain is not allowed for this organization. Please contact your administrator.");
    } else if (errorParam === "oauth_failed") {
      setError(`OAuth login failed: ${messageParam || "Unknown error"}`);
    }
  }, [searchParams]);

  const handleLogin = async () => {
    setError(null);
    setSuccess(null);
    try {
      const response = await fetchJson<{ access_token: string }>("/api/v1/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({ username: email, password }).toString(),
      });
      setStoredAccessToken(response.access_token);
      setSuccess("Login successful. Redirecting...");
      setTimeout(() => router.push("/"), 1000);
    } catch (err) {
      setError("Login failed. Check credentials and try again.");
    }
  };

  const handleGoogleLogin = async () => {
    if (!teamId) {
      setError("Please enter your Team ID to login with Google.");
      return;
    }

    setError(null);
    setGoogleLoading(true);

    try {
      const response = await fetchJson<{ auth_url: string; state: string }>(
        "/api/v1/auth/google/start",
        {
          method: "POST",
          body: JSON.stringify({
            team_id: teamId,
            redirect_uri: window.location.origin + "/auth/callback",
          }),
        }
      );

      // Redirect to Google OAuth
      window.location.href = response.auth_url;
    } catch (err: any) {
      setError(err.message || "Failed to start Google login");
      setGoogleLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-white border border-gray-200 rounded-lg shadow-sm p-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Login to Heliox</h1>
        <p className="text-gray-600 mb-6">
          Use your credentials or continue with Google.
        </p>

        {/* Email/Password Login */}
        {!showGoogleLogin ? (
          <div className="space-y-3">
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              placeholder="Email"
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            />
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              placeholder="Password"
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            />
            <button
              onClick={handleLogin}
              className="w-full bg-blue-600 text-white py-2 px-4 rounded-lg font-medium hover:bg-blue-700 transition-colors"
            >
              Login with Email
            </button>

            {/* Divider */}
            <div className="relative my-4">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-300"></div>
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-white text-gray-500">OR</span>
              </div>
            </div>

            {/* Google SSO Button */}
            <button
              onClick={() => setShowGoogleLogin(true)}
              className="w-full flex items-center justify-center gap-3 border border-gray-300 bg-white py-2 px-4 rounded-lg font-medium hover:bg-gray-50 transition-colors"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              Continue with Google
            </button>

            <Link
              href="/signup"
              className="block text-center text-blue-600 hover:text-blue-700 mt-4"
            >
              Need an account? Sign up
            </Link>
          </div>
        ) : (
          /* Google Login with Team ID */
          <div className="space-y-3">
            <p className="text-sm text-gray-600 mb-4">
              Enter your Team ID to login with Google SSO.
            </p>
            <input
              value={teamId}
              onChange={(e) => setTeamId(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              placeholder="Team ID (e.g., abc123...)"
              onKeyDown={(e) => e.key === "Enter" && handleGoogleLogin()}
            />
            <button
              onClick={handleGoogleLogin}
              disabled={googleLoading}
              className="w-full flex items-center justify-center gap-3 bg-blue-600 text-white py-2 px-4 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {googleLoading ? (
                "Redirecting..."
              ) : (
                <>
                  <svg className="w-5 h-5" viewBox="0 0 24 24">
                    <path
                      fill="currentColor"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                  </svg>
                  Continue with Google
                </>
              )}
            </button>
            <button
              onClick={() => setShowGoogleLogin(false)}
              className="w-full text-gray-600 hover:text-gray-900 text-sm"
            >
              ← Back to email login
            </button>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 mt-4">
            <p className="text-red-800 text-sm">{error}</p>
          </div>
        )}
        {success && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-3 mt-4">
            <p className="text-green-800 text-sm">{success}</p>
          </div>
        )}
      </div>
    </div>
  );
}
