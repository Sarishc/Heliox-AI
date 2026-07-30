"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, Loader2, MailWarning, XCircle } from "lucide-react";
import { AuthField, AuthShell } from "@/components/auth/AuthShell";
import { fetchApi, fetchJson } from "@/lib/api";

function VerifyEmailContent() {
  const token = useSearchParams().get("token") || "";
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [resendLoading, setResendLoading] = useState(false);
  const [resendSent, setResendSent] = useState(false);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("No verification token was found. Use the link from your email or request another.");
      return;
    }
    fetchJson(`/api/v1/auth/verify-email?token=${encodeURIComponent(token)}`, { skipAuthRedirect: true })
      .then(() => {
        setStatus("success");
        setMessage("Your identity is confirmed and your workspace is ready.");
      })
      .catch((caught) => {
        setStatus("error");
        setMessage(caught instanceof Error ? caught.message : "This link is invalid or has already been used.");
      });
  }, [token]);

  async function handleResend(event: React.FormEvent) {
    event.preventDefault();
    setResendLoading(true);
    try {
      await fetchApi("/api/v1/auth/resend-verification", {
        method: "POST",
        body: JSON.stringify({ email }),
        skipAuthRedirect: true,
      });
    } finally {
      setResendLoading(false);
      setResendSent(true);
    }
  }

  return (
    <AuthShell title="Trust starts with verified access." description="Heliox keeps workspace identity, integration credentials, and tenant boundaries explicit from the first session.">
      <div className="text-center">
        {status === "pending" && (
          <>
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-violet-500/30 bg-violet-500/10">
              <Loader2 className="h-6 w-6 animate-spin text-violet-300" />
            </div>
            <h2 className="auth-title mt-6">Verifying your email</h2>
            <p className="auth-subtitle">This should only take a moment.</p>
          </>
        )}
        {status === "success" && (
          <>
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-emerald-500/30 bg-emerald-500/10">
              <CheckCircle2 className="h-6 w-6 text-emerald-400" />
            </div>
            <h2 className="auth-title mt-6">Email verified</h2>
            <p className="auth-subtitle">{message}</p>
            <Link href="/login" className="auth-primary mt-7 w-full">Continue to sign in</Link>
          </>
        )}
        {status === "error" && (
          <>
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-rose-500/30 bg-rose-500/10">
              <XCircle className="h-6 w-6 text-rose-400" />
            </div>
            <h2 className="auth-title mt-6">Verification unavailable</h2>
            <p className="auth-subtitle">{message}</p>
            {!resendSent ? (
              <form onSubmit={handleResend} className="auth-form mt-7 text-left">
                <AuthField id="verification-email" label="Account email">
                  <input id="verification-email" className="auth-input" type="email" required placeholder="you@company.com"
                    value={email} onChange={(event) => setEmail(event.target.value)} />
                </AuthField>
                <button className="auth-primary" type="submit" disabled={resendLoading || !email}>
                  {resendLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <MailWarning className="h-4 w-4" />}
                  {resendLoading ? "Sending…" : "Send a new verification link"}
                </button>
              </form>
            ) : (
              <div className="auth-success mt-7" role="status">If the address is eligible, a fresh verification link is on its way.</div>
            )}
            <Link href="/login" className="auth-link mt-7 inline-block text-xs">Back to sign in</Link>
          </>
        )}
      </div>
    </AuthShell>
  );
}

export default function VerifyEmailPage() {
  return <Suspense fallback={<div className="min-h-screen bg-[#090a10]" />}><VerifyEmailContent /></Suspense>;
}
