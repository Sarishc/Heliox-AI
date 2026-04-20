"use client";

import { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { fetchJson } from "@/lib/api";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const [message, setMessage] = useState("");
  const [resendEmail, setResendEmail] = useState("");
  const [resendSent, setResendSent] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("No verification token found. Please use the link from your email.");
      return;
    }

    const verify = async () => {
      try {
        await fetchJson(`/api/v1/auth/verify-email?token=${encodeURIComponent(token)}`, {
          skipAuthRedirect: true,
        });
        setStatus("success");
        setMessage("Your email has been verified. You can now access all features.");
      } catch (err) {
        setStatus("error");
        setMessage(
          err instanceof Error && err.message
            ? err.message
            : "This verification link is invalid or has already been used."
        );
      }
    };

    verify();
  }, [token]);

  const handleResend = async (e: React.FormEvent) => {
    e.preventDefault();
    setResendLoading(true);
    try {
      await fetchApi("/api/v1/auth/resend-verification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: resendEmail }),
        skipAuthRedirect: true,
      });
      setResendSent(true);
    } catch {
      setResendSent(true); // Always show success to prevent enumeration
    } finally {
      setResendLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center gap-2 mb-6">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">H</span>
            </div>
            <span className="font-semibold text-slate-900">Heliox AI</span>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-center space-y-5">
          {status === "pending" && (
            <>
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-blue-100">
                <svg className="w-7 h-7 text-blue-600 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
              </div>
              <h1 className="text-xl font-semibold text-slate-900">Verifying your email…</h1>
            </>
          )}

          {status === "success" && (
            <>
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-emerald-100">
                <svg className="w-7 h-7 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h1 className="text-xl font-semibold text-slate-900">Email verified!</h1>
              <p className="text-sm text-slate-500">{message}</p>
              <Link
                href="/login"
                className="block w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
              >
                Sign in to your account
              </Link>
            </>
          )}

          {status === "error" && (
            <>
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-rose-100">
                <svg className="w-7 h-7 text-rose-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h1 className="text-xl font-semibold text-slate-900">Verification failed</h1>
              <p className="text-sm text-slate-500">{message}</p>

              {!resendSent ? (
                <form onSubmit={handleResend} className="space-y-3 text-left">
                  <p className="text-xs text-slate-500 text-center">
                    Enter your email to get a new verification link:
                  </p>
                  <input
                    type="email"
                    required
                    value={resendEmail}
                    onChange={(e) => setResendEmail(e.target.value)}
                    placeholder="you@company.com"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <button
                    type="submit"
                    disabled={resendLoading || !resendEmail}
                    className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                  >
                    {resendLoading ? "Sending…" : "Resend verification email"}
                  </button>
                </form>
              ) : (
                <p className="text-sm text-emerald-700 bg-emerald-50 rounded-lg p-3">
                  If that address is registered and unverified, a new link has been sent.
                </p>
              )}

              <Link
                href="/login"
                className="block text-sm text-slate-500 hover:text-slate-700"
              >
                Back to sign in
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-50" />}>
      <VerifyEmailContent />
    </Suspense>
  );
}
