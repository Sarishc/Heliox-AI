"use client";

import { useState } from "react";
import Link from "next/link";
import { fetchJson } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await fetchJson("/api/v1/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
        skipAuthRedirect: true,
      });
      setSubmitted(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      // 503 = email delivery not configured — must surface this, not fake success
      if (msg.toLowerCase().includes("not configured") || msg.toLowerCase().includes("contact support")) {
        setError(msg);
      } else {
        // For any other error (404, network, etc.) show generic success to prevent email enumeration
        setSubmitted(true);
      }
    } finally {
      setLoading(false);
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
          <h1 className="text-2xl font-semibold text-slate-900">
            {submitted ? "Check your inbox" : "Reset your password"}
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            {submitted
              ? `We sent a password reset link to ${email}. Check your spam folder if you don't see it.`
              : "Enter your account email and we'll send you a reset link."}
          </p>
        </div>

        {!submitted ? (
          <form
            onSubmit={handleSubmit}
            className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 space-y-5"
          >
            {error && (
              <div className="rounded-lg bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-700">
                {error}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Email address
              </label>
              <input
                type="email"
                required
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <button
              type="submit"
              disabled={loading || !email}
              className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Sending…" : "Send reset link"}
            </button>

            <p className="text-center text-sm text-slate-500">
              Remember your password?{" "}
              <Link href="/login" className="text-blue-600 hover:underline font-medium">
                Sign in
              </Link>
            </p>
          </form>
        ) : (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-center space-y-5">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-emerald-100">
              <svg className="w-7 h-7 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <p className="text-sm text-slate-600">
              The link expires in 60 minutes. If you don't receive it, check your spam folder or{" "}
              <button
                onClick={() => { setSubmitted(false); setEmail(""); }}
                className="text-blue-600 hover:underline font-medium"
              >
                try again
              </button>
              .
            </p>
            <Link
              href="/login"
              className="block w-full rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors text-center"
            >
              Back to sign in
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
