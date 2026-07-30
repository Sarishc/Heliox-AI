"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Check, Loader2 } from "lucide-react";
import { AuthField, AuthShell } from "@/components/auth/AuthShell";
import { fetchJson } from "@/lib/api";
import { setDemoMode } from "@/lib/demoData";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function SignupPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [emailWarning, setEmailWarning] = useState<string | null>(null);

  const strength = useMemo(() => {
    const checks = [password.length >= 8, /[A-Z]/.test(password), /[0-9]/.test(password), /[^A-Za-z0-9]/.test(password)];
    return { score: checks.filter(Boolean).length, checks };
  }, [password]);
  const errors = {
    name: touched.name && fullName.trim().length < 2 ? "Enter your full name." : null,
    email: touched.email && !EMAIL_PATTERN.test(email) ? "Enter a valid work email." : null,
    password: touched.password && strength.score < 3 ? "Use 8+ characters with a number and uppercase or symbol." : null,
    confirm: touched.confirm && password !== confirm ? "Passwords do not match." : null,
  };
  const valid = fullName.trim().length >= 2 && EMAIL_PATTERN.test(email) && strength.score >= 3 && password === confirm;

  async function handleSignup(event: React.FormEvent) {
    event.preventDefault();
    setTouched({ name: true, email: true, password: true, confirm: true });
    if (!valid) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await fetchJson<{ email_configured?: boolean }>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, full_name: fullName.trim() }),
      });
      if (result.email_configured === false) {
        setEmailWarning("Email delivery is unavailable in this environment. Your workspace was still created.");
      }
      await fetchJson("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username: email, password }).toString(),
      });
      setDemoMode(false, false);
      setSuccess("Workspace created. Preparing your dashboard…");
      window.setTimeout(() => window.location.assign("/onboarding"), 500);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create your account.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Make every GPU dollar explainable." description="Start with a secure workspace, then connect the cloud and workload signals your team already owns.">
      <header className="auth-card-header">
        <p className="auth-eyebrow">Create your workspace</p>
        <h2 className="auth-title mt-3">Start with Heliox</h2>
        <p className="auth-subtitle">No payment method required for local evaluation.</p>
      </header>
      <form className="auth-form" onSubmit={handleSignup} noValidate>
        <AuthField id="full-name" label="Full name" error={errors.name}>
          <input id="full-name" className="auth-input" autoComplete="name" placeholder="Alex Rivera" value={fullName}
            onChange={(event) => setFullName(event.target.value)} onBlur={() => setTouched((value) => ({ ...value, name: true }))}
            aria-invalid={Boolean(errors.name)} />
        </AuthField>
        <AuthField id="signup-email" label="Work email" error={errors.email}>
          <input id="signup-email" className="auth-input" type="email" autoComplete="email" placeholder="alex@company.com" value={email}
            onChange={(event) => setEmail(event.target.value)} onBlur={() => setTouched((value) => ({ ...value, email: true }))}
            aria-invalid={Boolean(errors.email)} />
        </AuthField>
        <AuthField id="new-password" label="Password" error={errors.password}>
          <input id="new-password" className="auth-input" type="password" autoComplete="new-password" placeholder="Create a strong password" value={password}
            onChange={(event) => setPassword(event.target.value)} onBlur={() => setTouched((value) => ({ ...value, password: true }))}
            aria-invalid={Boolean(errors.password)} />
          <div className="mt-2 grid grid-cols-4 gap-1" aria-label={`Password strength ${strength.score} of 4`}>
            {[0, 1, 2, 3].map((part) => <span key={part} className={`h-1 rounded-full ${part < strength.score ? "bg-violet-500" : "bg-slate-800"}`} />)}
          </div>
        </AuthField>
        <AuthField id="confirm-password" label="Confirm password" error={errors.confirm}>
          <input id="confirm-password" className="auth-input" type="password" autoComplete="new-password" placeholder="Repeat your password" value={confirm}
            onChange={(event) => setConfirm(event.target.value)} onBlur={() => setTouched((value) => ({ ...value, confirm: true }))}
            aria-invalid={Boolean(errors.confirm)} />
        </AuthField>
        <div className="flex items-start gap-2 text-[11px] leading-5 text-slate-500">
          <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-400" />
          By continuing, you agree to use Heliox responsibly and protect credentials issued to your workspace.
        </div>
        {emailWarning && <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">{emailWarning}</div>}
        {error && <div className="auth-alert" role="alert">{error}</div>}
        {success && <div className="auth-success" role="status" aria-live="polite">{success}</div>}
        <button className="auth-primary" type="submit" disabled={loading || !valid}>
          {loading && <Loader2 className="h-4 w-4 animate-spin" />}
          {loading ? "Creating workspace…" : "Create workspace"}
        </button>
      </form>
      <p className="mt-8 text-center text-xs text-slate-500">
        Already have access? <Link href="/login" className="auth-link">Sign in</Link>
      </p>
    </AuthShell>
  );
}
