"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, Loader2 } from "lucide-react";
import { AuthField, AuthShell } from "@/components/auth/AuthShell";
import { fetchJson } from "@/lib/api";

function ResetPasswordForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(token ? null : "This reset link is incomplete. Request a new one.");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const strength = useMemo(() => [password.length >= 8, /[A-Z]/.test(password), /[0-9]/.test(password), /[^A-Za-z0-9]/.test(password)].filter(Boolean).length, [password]);
  const passwordError = touched && strength < 3 ? "Use 8+ characters with a number and uppercase or symbol." : null;
  const confirmError = touched && password !== confirm ? "Passwords do not match." : null;
  const valid = Boolean(token) && strength >= 3 && password === confirm;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (!valid) return;
    setLoading(true);
    setError(null);
    try {
      await fetchJson("/api/v1/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, new_password: password }),
        skipAuthRedirect: true,
      });
      setSuccess(true);
      window.setTimeout(() => router.push("/login"), 2500);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "This reset link is invalid or expired.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Return to your workspace with confidence." description="Strong password requirements and single-use recovery tokens protect every Heliox workspace.">
      {success ? (
        <div className="text-center" role="status" aria-live="polite">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-emerald-500/30 bg-emerald-500/10">
            <CheckCircle2 className="h-6 w-6 text-emerald-400" />
          </div>
          <h2 className="auth-title mt-6">Password updated</h2>
          <p className="auth-subtitle">Your new password is active. Redirecting you to sign in…</p>
          <Link href="/login" className="auth-primary mt-7 w-full">Sign in now</Link>
        </div>
      ) : (
        <>
          <header className="auth-card-header">
            <p className="auth-eyebrow">Secure recovery</p>
            <h2 className="auth-title mt-3">Choose a new password</h2>
            <p className="auth-subtitle">Use a password that is unique to Heliox.</p>
          </header>
          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            <AuthField id="reset-password" label="New password" error={passwordError}>
              <input id="reset-password" className="auth-input" type="password" autoComplete="new-password" autoFocus
                placeholder="Create a strong password" value={password} onChange={(event) => setPassword(event.target.value)}
                onBlur={() => setTouched(true)} aria-invalid={Boolean(passwordError)} />
              <div className="mt-2 grid grid-cols-4 gap-1" aria-label={`Password strength ${strength} of 4`}>
                {[0, 1, 2, 3].map((part) => <span key={part} className={`h-1 rounded-full ${part < strength ? "bg-violet-500" : "bg-slate-800"}`} />)}
              </div>
            </AuthField>
            <AuthField id="reset-confirm" label="Confirm password" error={confirmError}>
              <input id="reset-confirm" className="auth-input" type="password" autoComplete="new-password"
                placeholder="Repeat your password" value={confirm} onChange={(event) => setConfirm(event.target.value)}
                onBlur={() => setTouched(true)} aria-invalid={Boolean(confirmError)} />
            </AuthField>
            {error && <div className="auth-alert" role="alert">{error}{" "}{error.toLowerCase().includes("expired") && <Link className="auth-link" href="/forgot-password">Request a new link</Link>}</div>}
            <button className="auth-primary" type="submit" disabled={loading || !valid}>
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {loading ? "Updating password…" : "Update password"}
            </button>
          </form>
        </>
      )}
      <p className="mt-8 text-center text-xs"><Link href="/login" className="auth-link">Back to sign in</Link></p>
    </AuthShell>
  );
}

export default function ResetPasswordPage() {
  return <Suspense fallback={<div className="min-h-screen bg-[#090a10]" />}><ResetPasswordForm /></Suspense>;
}
