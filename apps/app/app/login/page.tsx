"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import HCaptcha from "@hcaptcha/react-hcaptcha";
import { Loader2, LockKeyhole, Mail } from "lucide-react";
import { AuthField, AuthShell } from "@/components/auth/AuthShell";
import { fetchApi, fetchJson } from "@/lib/api";
import { setDemoMode } from "@/lib/demoData";

const HCAPTCHA_SITE_KEY =
  process.env.NEXT_PUBLIC_HCAPTCHA_SITE_KEY ||
  (process.env.NODE_ENV === "development" ? "10000000-ffff-ffff-ffff-000000000001" : "");
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function GoogleIcon() {
  return (
    <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09A6.9 6.9 0 015.49 12c0-.73.13-1.43.35-2.09V7.07H2.18A11 11 0 001 12c0 1.78.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A10.7 10.7 0 0012 1C7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  );
}

function LoginPageContent() {
  const searchParams = useSearchParams();
  const captchaRef = useRef<HCaptcha>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [teamId, setTeamId] = useState("");
  const [emailTouched, setEmailTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ssoMode, setSsoMode] = useState(false);
  const [ssoLoading, setSsoLoading] = useState<"google" | "saml" | null>(null);
  const [captchaRequired, setCaptchaRequired] = useState(false);
  const [captchaToken, setCaptchaToken] = useState("");

  const emailError = emailTouched && !EMAIL_PATTERN.test(email) ? "Enter a valid work email." : null;

  useEffect(() => {
    const kind = searchParams.get("error");
    const message = searchParams.get("message");
    if (kind === "domain_not_allowed") setError("Your email domain is not permitted for this organization.");
    if (kind === "oauth_failed") setError(`Google sign-in failed: ${message || "Please try again."}`);
    if (kind === "saml_failed") setError(`SSO sign-in failed: ${message || "Please try again."}`);
  }, [searchParams]);

  async function handleLogin(event?: React.FormEvent) {
    event?.preventDefault();
    setEmailTouched(true);
    if (!EMAIL_PATTERN.test(email) || !password) return;
    setError(null);
    setSuccess(null);
    setLoading(true);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/x-www-form-urlencoded" };
      if (captchaToken) headers["X-Captcha-Token"] = captchaToken;
      const response = await fetchApi("/api/v1/auth/login", {
        method: "POST",
        headers,
        body: new URLSearchParams({ username: email, password }).toString(),
        skipAuthRedirect: true,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        if (body?.captcha_required || (response.status === 400 && body?.detail?.includes?.("CAPTCHA"))) {
          setCaptchaRequired(true);
          setCaptchaToken("");
          captchaRef.current?.resetCaptcha?.();
          setError("Complete the security check to continue.");
        } else if (response.status === 429) {
          setError(body?.detail || "Too many attempts. Try again shortly.");
        } else {
          setError("Email or password is incorrect.");
        }
        return;
      }
      setDemoMode(false, false);
      setSuccess("Authenticated. Opening your workspace…");
      const redirect = searchParams.get("redirect") || "/";
      window.setTimeout(() => window.location.assign(redirect), 350);
    } catch {
      setError("Unable to reach Heliox. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSso(provider: "google" | "saml") {
    if (!teamId.trim()) {
      setError("Enter your organization Team ID to continue with SSO.");
      return;
    }
    setError(null);
    setSsoLoading(provider);
    try {
      const endpoint = provider === "google" ? "/api/v1/auth/google/start" : "/api/v1/auth/saml/login";
      const result = await fetchJson<{ auth_url: string }>(endpoint, {
        method: "POST",
        body: JSON.stringify({ team_id: teamId.trim(), redirect_uri: window.location.origin }),
      });
      window.location.assign(result.auth_url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start SSO.");
      setSsoLoading(null);
    }
  }

  return (
    <AuthShell>
      <header className="auth-card-header">
        <p className="auth-eyebrow">Secure workspace access</p>
        <h2 className="auth-title mt-3">Welcome back</h2>
        <p className="auth-subtitle">Sign in to inspect spend, utilization, and savings opportunities.</p>
      </header>

      {!ssoMode ? (
        <form className="auth-form" onSubmit={handleLogin} noValidate>
          <AuthField id="email" label="Work email" error={emailError}>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-600" />
              <input id="email" className="auth-input auth-input-with-icon" type="email" autoComplete="email" placeholder="you@company.com"
                value={email} onChange={(event) => setEmail(event.target.value)} onBlur={() => setEmailTouched(true)}
                aria-invalid={Boolean(emailError)} aria-describedby={emailError ? "email-message" : undefined} />
            </div>
          </AuthField>
          <AuthField id="password" label="Password">
            <div className="relative">
              <LockKeyhole className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-600" />
              <input id="password" className="auth-input auth-input-with-icon" type="password" autoComplete="current-password" placeholder="Enter your password"
                value={password} onChange={(event) => setPassword(event.target.value)} />
            </div>
          </AuthField>
          <div className="-mt-2 text-right">
            <Link href="/forgot-password" className="auth-link text-xs">Forgot password?</Link>
          </div>
          {captchaRequired && (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3">
              <p className="mb-2 text-xs text-amber-200">Security verification</p>
              {HCAPTCHA_SITE_KEY ? (
                <HCaptcha ref={captchaRef} sitekey={HCAPTCHA_SITE_KEY} onVerify={setCaptchaToken} onExpire={() => setCaptchaToken("")} />
              ) : <p className="text-xs text-amber-200">CAPTCHA is not configured.</p>}
            </div>
          )}
          {error && <div role="alert" className="auth-alert">{error}</div>}
          {success && <div role="status" aria-live="polite" className="auth-success">{success}</div>}
          <button className="auth-primary" type="submit" disabled={loading || Boolean(emailError) || !email || !password || (captchaRequired && !captchaToken)}>
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {loading ? "Signing in…" : "Sign in"}
          </button>
          <div className="auth-divider">or</div>
          <button className="auth-secondary" type="button" onClick={() => setSsoMode(true)}>
            <GoogleIcon /> Continue with Google or SSO
          </button>
        </form>
      ) : (
        <div className="auth-form">
          <AuthField id="team-id" label="Organization Team ID" hint="Your administrator can find this in Settings → Authentication.">
            <input id="team-id" className="auth-input" value={teamId} onChange={(event) => setTeamId(event.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000" autoComplete="organization" />
          </AuthField>
          {error && <div role="alert" className="auth-alert">{error}</div>}
          <button className="auth-primary" type="button" onClick={() => handleSso("google")} disabled={Boolean(ssoLoading)}>
            {ssoLoading === "google" ? <Loader2 className="h-4 w-4 animate-spin" /> : <GoogleIcon />}
            Continue with Google
          </button>
          <button className="auth-secondary" type="button" onClick={() => handleSso("saml")} disabled={Boolean(ssoLoading)}>
            {ssoLoading === "saml" && <Loader2 className="h-4 w-4 animate-spin" />}
            Continue with enterprise SSO
          </button>
          <button className="auth-link text-left text-xs" type="button" onClick={() => { setSsoMode(false); setError(null); }}>
            ← Back to email sign in
          </button>
        </div>
      )}

      <p className="mt-8 text-center text-xs text-slate-500">
        New to Heliox? <Link href="/signup" className="auth-link">Create an account</Link>
      </p>
    </AuthShell>
  );
}

export default function LoginPage() {
  return <Suspense fallback={<div className="min-h-screen bg-[#090a10]" />}><LoginPageContent /></Suspense>;
}
