"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, Loader2, Mail } from "lucide-react";
import { AuthField, AuthShell } from "@/components/auth/AuthShell";
import { fetchJson } from "@/lib/api";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [touched, setTouched] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const emailError = touched && !EMAIL_PATTERN.test(email) ? "Enter a valid account email." : null;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (!EMAIL_PATTERN.test(email)) return;
    setLoading(true);
    setError(null);
    try {
      await fetchJson("/api/v1/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
        skipAuthRedirect: true,
      });
      setSubmitted(true);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "";
      if (message.toLowerCase().includes("not configured") || message.toLowerCase().includes("contact support")) setError(message);
      else setSubmitted(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Secure recovery without support tickets." description="Heliox recovery links are single-use, time-limited, and never reveal whether an address belongs to an account.">
      {!submitted ? (
        <>
          <header className="auth-card-header">
            <p className="auth-eyebrow">Account recovery</p>
            <h2 className="auth-title mt-3">Reset your password</h2>
            <p className="auth-subtitle">We’ll send a secure, time-limited link to your account email.</p>
          </header>
          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            <AuthField id="recovery-email" label="Account email" error={emailError}>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-600" />
                <input id="recovery-email" className="auth-input auth-input-with-icon" type="email" autoComplete="email" autoFocus
                  placeholder="you@company.com" value={email} onChange={(event) => setEmail(event.target.value)}
                  onBlur={() => setTouched(true)} aria-invalid={Boolean(emailError)} />
              </div>
            </AuthField>
            {error && <div className="auth-alert" role="alert">{error}</div>}
            <button className="auth-primary" type="submit" disabled={loading || !EMAIL_PATTERN.test(email)}>
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {loading ? "Sending secure link…" : "Send reset link"}
            </button>
          </form>
        </>
      ) : (
        <div className="text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-emerald-500/30 bg-emerald-500/10">
            <CheckCircle2 className="h-6 w-6 text-emerald-400" />
          </div>
          <h2 className="auth-title mt-6">Check your inbox</h2>
          <p className="auth-subtitle">If an account exists for <strong className="text-slate-300">{email}</strong>, its reset link is on the way.</p>
          <button className="auth-secondary mt-7 w-full" type="button" onClick={() => { setSubmitted(false); setEmail(""); }}>
            Try another email
          </button>
        </div>
      )}
      <Link href="/login" className="auth-link mt-8 flex items-center justify-center gap-2 text-xs">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to sign in
      </Link>
    </AuthShell>
  );
}
