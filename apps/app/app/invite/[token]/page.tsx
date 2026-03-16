"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchApi, getApiUrl } from "@/lib/api";

interface InviteInfo {
  valid: boolean;
  team_name: string;
  team_id: string;
  email: string;
  role: string;
  expires_at: string;
  inviter_name: string | null;
}

export default function InviteAcceptPage({
  params,
}: {
  params: { token: string };
}) {
  const router = useRouter();
  const token = typeof params.token === "string" ? params.token : params.token?.[0] ?? "";
  const [invite, setInvite] = useState<InviteInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");

  useEffect(() => {
    const load = async () => {
      if (!token) {
        setError("Invalid invite link");
        setLoading(false);
        return;
      }
      try {
        const url = getApiUrl(`/api/v1/invite/${token}`);
        const res = await fetch(url, { credentials: "include" });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          setError(body?.detail ?? "Invite not found or expired");
          setLoading(false);
          return;
        }
        const data = (await res.json()) as InviteInfo;
        setInvite(data);
        setFullName(data.email.split("@")[0]);
      } catch {
        setError("Unable to load invite");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [token]);

  const handleAccept = async () => {
    if (!invite || !token) return;
    setAccepting(true);
    setError(null);
    try {
      const body: { email: string; password?: string; full_name?: string } = {
        email: invite.email,
      };
      if (password) {
        body.password = password;
        body.full_name = fullName || invite.email.split("@")[0];
      }
      const res = await fetchApi(
        `/api/v1/invite/${token}/accept`,
        {
          method: "POST",
          body: JSON.stringify(body),
          skipAuthRedirect: true,
        }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const msg = typeof data?.detail === "string" ? data.detail : JSON.stringify(data?.detail ?? "Failed to accept invite");
        if (msg.includes("log in first")) {
          setError("This email already has an account. Please log in first, then return to this page to accept the invite.");
          return;
        }
        if (msg.includes("Password required")) {
          setError("Create an account by entering a password below.");
          return;
        }
        throw new Error(msg);
      }
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept invite");
    } finally {
      setAccepting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <p className="text-slate-500">Loading invite...</p>
      </div>
    );
  }

  if (error && !invite) {
    return (
      <div className="min-h-screen bg-slate-50 px-6 py-16 text-center">
        <h1 className="text-2xl font-semibold text-slate-900">Invite unavailable</h1>
        <p className="mt-2 text-sm text-slate-500">{error}</p>
        <a href="/login" className="mt-4 inline-block text-blue-600 hover:underline">
          Go to login
        </a>
      </div>
    );
  }

  if (!invite) return null;

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-xs uppercase tracking-wide text-slate-500">Team invite</p>
        <h1 className="text-xl font-semibold text-slate-900 mt-1">
          Join {invite.team_name}
        </h1>
        {invite.inviter_name && (
          <p className="text-sm text-slate-500 mt-1">
            {invite.inviter_name} invited you as <strong>{invite.role}</strong>
          </p>
        )}
        <p className="text-sm text-slate-600 mt-3">
          You&apos;ll join as <strong>{invite.role}</strong>. Email: {invite.email}
        </p>

        <div className="mt-6 space-y-4">
          <p className="text-sm text-slate-600">
            If you&apos;re logged in with matching email, click Accept. Otherwise enter a password to create an account.
          </p>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Password (required for new accounts)
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min 8 characters — leave empty if already logged in"
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
              minLength={8}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Full name (optional)
            </label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your name"
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
            />
          </div>
          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}
          <button
            onClick={handleAccept}
            disabled={accepting}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {accepting ? "Accepting..." : "Accept invite"}
          </button>
        </div>

        <p className="mt-4 text-xs text-slate-500">
          Already have an account?{" "}
          <a href="/login" className="text-blue-600 hover:underline">
            Log in
          </a>{" "}
          then return here to accept.
        </p>
      </div>
    </div>
  );
}
