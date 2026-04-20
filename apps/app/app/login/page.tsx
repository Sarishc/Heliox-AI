"use client";

import { useRef, useState, useEffect } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import HCaptcha from "@hcaptcha/react-hcaptcha";
import { fetchApi, fetchJson, getApiBaseUrl } from "@/lib/api";

const HCAPTCHA_SITE_KEY =
  process.env.NEXT_PUBLIC_HCAPTCHA_SITE_KEY ||
  (process.env.NODE_ENV === "development"
    ? "10000000-ffff-ffff-ffff-000000000001"
    : "");

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
  const [samlLoading, setSamlLoading] = useState(false);
  const [captchaRequired, setCaptchaRequired] = useState(false);
  const [captchaToken, setCaptchaToken] = useState("");
  const [demoTeamId, setDemoTeamId] = useState<string | null>(null);
  const [demoTeamLoading, setDemoTeamLoading] = useState(false);
  const captchaRef = useRef<HCaptcha>(null);

  const fetchDemoTeamId = async () => {
    // Dev-only: admin key for demo bootstrap. Never used in production builds.
    const adminKey =
      process.env.NODE_ENV === "development"
        ? process.env.NEXT_PUBLIC_DEV_ADMIN_API_KEY
        : undefined;
    if (!adminKey) {
      setError(
        process.env.NODE_ENV === "development"
          ? "NEXT_PUBLIC_DEV_ADMIN_API_KEY not set in .env.local (required for demo)"
          : "Demo not available in production"
      );
      return;
    }
    setDemoTeamLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${getApiBaseUrl()}/api/v1/admin/demo/teams`,
        { headers: { "X-API-Key": adminKey } }
      );
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const id = data.demo_team_id || data.teams?.[0]?.id;
      setDemoTeamId(id || null);
      if (!id) setError("No demo team found. Run demo seed first.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch demo team");
    } finally {
      setDemoTeamLoading(false);
    }
  };

  useEffect(() => {
    // Check for OAuth errors in URL
    const errorParam = searchParams.get("error");
    const messageParam = searchParams.get("message");
    
    if (errorParam === "domain_not_allowed") {
      setError("Your email domain is not allowed for this organization. Please contact your administrator.");
    } else if (errorParam === "oauth_failed") {
      setError(`OAuth login failed: ${messageParam || "Unknown error"}`);
    } else if (errorParam === "saml_failed") {
      setError(`SAML login failed: ${messageParam || "Unknown error"}`);
    }
  }, [searchParams]);

  const handleLogin = async () => {
    setError(null);
    setSuccess(null);
    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/x-www-form-urlencoded",
      };
      if (captchaToken) headers["X-Captcha-Token"] = captchaToken;

      const res = await fetchApi("/api/v1/auth/login", {
        method: "POST",
        headers,
        body: new URLSearchParams({ username: email, password }).toString(),
        skipAuthRedirect: true,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        if (body?.captcha_required || (res.status === 400 && body?.detail?.includes?.("CAPTCHA"))) {
          setCaptchaRequired(true);
          setCaptchaToken("");
          captchaRef.current?.resetCaptcha?.();
          setError("Too many attempts. Please complete the CAPTCHA below.");
          return;
        }
        if (res.status === 429) {
          setError(body?.message || "Too many attempts. Please try again later.");
          return;
        }
        setError("Login failed. Check credentials and try again.");
        return;
      }

      setSuccess("Login successful. Redirecting...");
      const redirect = searchParams.get("redirect") || "/";
      setTimeout(() => router.push(redirect), 500);
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
            redirect_uri: window.location.origin,
          }),
        }
      );
      window.location.href = response.auth_url;
    } catch (err: any) {
      const msg = err.message || "Failed to start Google login";
      setError(
        msg.includes("not configured")
          ? "Google SSO is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to backend/.env — see docs/GOOGLE_OAUTH_SETUP.md"
          : msg
      );
      setGoogleLoading(false);
    }
  };

  const handleSamlLogin = async () => {
    if (!teamId) {
      setError("Please enter your Team ID to login with Okta.");
      return;
    }
    setError(null);
    setSamlLoading(true);
    try {
      const response = await fetchJson<{ auth_url: string; state: string }>(
        "/api/v1/auth/saml/login",
        {
          method: "POST",
          body: JSON.stringify({
            team_id: teamId,
            redirect_uri: window.location.origin,
          }),
        }
      );
      window.location.href = response.auth_url;
    } catch (err: any) {
      setError(err.message || "Failed to start Okta login. Ensure SAML is configured for this team.");
      setSamlLoading(false);
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
            <div>
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                placeholder="Password"
                onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              />
              <div className="mt-1 text-right">
                <Link href="/forgot-password" className="text-xs text-blue-600 hover:underline">
                  Forgot password?
                </Link>
              </div>
            </div>
            {captchaRequired && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                <p className="text-sm text-amber-800 mb-2">
                  Security check: Complete the CAPTCHA to continue.
                </p>
                {HCAPTCHA_SITE_KEY ? (
                  <HCaptcha
                    ref={captchaRef}
                    sitekey={HCAPTCHA_SITE_KEY}
                    onVerify={(token) => setCaptchaToken(token)}
                    onExpire={() => setCaptchaToken("")}
                  />
                ) : (
                  <p className="text-sm text-amber-700">
                    CAPTCHA not configured. Set NEXT_PUBLIC_HCAPTCHA_SITE_KEY.
                  </p>
                )}
              </div>
            )}
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
              placeholder="Team ID (UUID, e.g. from demo seed)"
              onKeyDown={(e) => e.key === "Enter" && handleGoogleLogin()}
            />
            {process.env.NODE_ENV === "development" && (
              <button
                type="button"
                onClick={fetchDemoTeamId}
                disabled={demoTeamLoading}
                className="text-xs text-blue-600 hover:underline disabled:opacity-50"
              >
                {demoTeamLoading ? "Fetching..." : "Get demo Team ID"}
              </button>
            )}
            {demoTeamId && (
              <p className="text-xs text-green-700">
                Demo Team ID: <code className="bg-gray-100 px-1">{demoTeamId}</code>
                <button
                  type="button"
                  onClick={() => setTeamId(demoTeamId)}
                  className="ml-2 text-blue-600 hover:underline"
                >
                  Use this
                </button>
              </p>
            )}
            <button
              onClick={handleGoogleLogin}
              disabled={googleLoading || samlLoading}
              className="w-full flex items-center justify-center gap-3 bg-blue-600 text-white py-2 px-4 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {googleLoading ? "Redirecting..." : (
                <>
                  <svg className="w-5 h-5" viewBox="0 0 24 24">
                    <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  </svg>
                  Continue with Google
                </>
              )}
            </button>
            <button
              onClick={handleSamlLogin}
              disabled={googleLoading || samlLoading}
              className="w-full flex items-center justify-center gap-3 border border-gray-300 bg-white py-2 px-4 rounded-lg font-medium hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {samlLoading ? "Redirecting..." : (
                <>
                  <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 0C5.389 0 0 5.35 0 12s5.35 12 12 12 12-5.35 12-12S18.611 0 12 0zm0 2.4c5.307 0 9.6 4.293 9.6 9.6s-4.293 9.6-9.6 9.6-9.6-4.293-9.6-9.6 4.293-9.6 9.6-9.6zm0 2.4c-3.969 0-7.2 3.231-7.2 7.2s3.231 7.2 7.2 7.2 7.2-3.231 7.2-7.2-3.231-7.2-7.2-7.2z" />
                  </svg>
                  Continue with Okta
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

        {/* Development / Test Help */}
        {process.env.NODE_ENV === "development" && (
          <div className="mt-6 p-4 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-600">
            <p className="font-medium text-gray-700 mb-2">🧪 Test credentials (development)</p>
            <p className="mb-1">
              <strong>Email login:</strong> Sign up at{" "}
              <Link href="/signup" className="text-blue-600 hover:underline">/signup</Link> then{" "}
              <Link href="/login" className="text-blue-600 hover:underline">login</Link> with your credentials.
            </p>
            <p className="mb-1">
              <strong>Google SSO:</strong> Requires GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET in backend env (see docs/GOOGLE_OAUTH_SETUP.md). Use a valid Team ID from demo seed.
            </p>
            <code className="block text-xs bg-gray-100 p-2 rounded mt-1 break-all">
              curl -X POST {getApiBaseUrl() || "http://localhost:8001"}/api/v1/admin/demo/seed -H &quot;X-API-Key: $ADMIN_API_KEY&quot;
            </code>
            <p className="mt-2 text-xs">
              The response includes <code className="bg-gray-100 px-1">demo_team_id</code> — use that as Team ID.
            </p>
            <p className="mt-2 text-xs text-amber-700">
              Backend not running? Run: <code className="bg-gray-100 px-1">cd backend &amp;&amp; uvicorn app.main:app --reload --port 8001</code> or <code className="bg-gray-100 px-1">docker compose up -d</code>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
