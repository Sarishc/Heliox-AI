"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { fetchJson } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [emailWarning, setEmailWarning] = useState<string | null>(null);

  const handleSignup = async () => {
    setError(null);
    setSuccess(null);
    setEmailWarning(null);
    try {
      const regResult = await fetchJson<{ email_configured?: boolean }>(
        "/api/v1/auth/register",
        {
          method: "POST",
          body: JSON.stringify({
            email,
            password,
            full_name: fullName,
          }),
        }
      );
      // If email is not configured, warn the user they won't get a verification email
      if (regResult?.email_configured === false) {
        setEmailWarning(
          "Email delivery is not configured on this server. You won't receive a verification email — contact your administrator if verification is required."
        );
      }
      await fetchJson<{ user: { id: string; email: string; full_name: string }; message: string }>(
        "/api/v1/auth/login",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: new URLSearchParams({ username: email, password }).toString(),
        }
      );
      setSuccess("Account created. Redirecting...");
      setTimeout(() => router.push("/"), 500);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Signup failed. Check details and try again.";
      setError(msg);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-white border border-gray-200 rounded-lg shadow-sm p-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Create account</h1>
        <p className="text-gray-600 mb-6">
          Create a Heliox account to manage team settings.
        </p>
        <div className="space-y-3">
          <input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
            placeholder="Full name"
          />
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
            placeholder="Email"
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
            placeholder="Password (min 8 chars)"
          />
          <button
            onClick={handleSignup}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-lg font-medium hover:bg-blue-700 transition-colors"
          >
            Create account
          </button>
          <Link href="/login" className="block text-center text-blue-600 hover:text-blue-700">
            Already have access? Login
          </Link>
        </div>
        {emailWarning && (
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800 mt-4">
            {emailWarning}
          </div>
        )}
        {error && <p className="text-red-600 text-sm mt-4">{error}</p>}
        {success && <p className="text-green-600 text-sm mt-4">{success}</p>}
      </div>
    </div>
  );
}
