"use client";

import { useEffect, useState } from "react";
import { Mail } from "lucide-react";
import { fetchJson } from "@/lib/api";
import { isDemoMode } from "@/lib/demoData";

interface MeResponse {
  team_id: string;
  role: string;
}

interface EmailAlertsResponse {
  team_id: string;
  enabled: boolean;
  recipient_count: number;
  masked_recipients?: string | null;
}

export default function EmailAlertsCard() {
  const [teamId, setTeamId] = useState<string | null>(null);
  const [recipients, setRecipients] = useState("");
  const [status, setStatus] = useState<EmailAlertsResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      if (isDemoMode()) {
        setTeamId("demo-team");
        setStatus({ team_id: "demo-team", enabled: true, recipient_count: 3, masked_recipients: "a***@acme.com, f***@acme.com, +1 more" });
        return;
      }
      try {
        const me = await fetchJson<MeResponse>("/api/v1/me");
        setTeamId(me.team_id);
        if (me.team_id) {
          const res = await fetchJson<EmailAlertsResponse>(
            `/api/v1/alerts/email?team_id=${me.team_id}`
          );
          setStatus(res);
        }
      } catch {
        setTeamId(null);
        setStatus(null);
      }
    };
    load();
  }, []);

  const saveEmailAlerts = async () => {
    if (!teamId) return;
    setMessage(null);
    setError(null);
    const trimmed = recipients.trim();
    if (!trimmed) {
      setError("Enter at least one email address.");
      return;
    }
    try {
      const response = await fetchJson<EmailAlertsResponse>("/api/v1/alerts/email", {
        method: "POST",
        body: JSON.stringify({
          team_id: teamId,
          enable_email: true,
          email_recipients: trimmed,
        }),
      });
      setStatus(response);
      setRecipients("");
      setMessage("Email alerts saved. Recipients will receive budget, anomaly, and summary notifications.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to save email alerts. Ensure you are authenticated."
      );
    }
  };

  const clearEmailAlerts = async () => {
    if (!teamId) return;
    setMessage(null);
    setError(null);
    try {
      await fetchJson(`/api/v1/alerts/email?team_id=${teamId}`, { method: "DELETE" });
      setStatus({
        team_id: teamId,
        enabled: false,
        recipient_count: 0,
        masked_recipients: null,
      });
      setRecipients("");
      setMessage("Email alerts disabled.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to remove email alerts. Ensure you are authenticated."
      );
    }
  };

  if (!teamId) return null;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Email alerts</p>
          <h3 className="mt-1 text-lg font-semibold text-slate-900">
            Budget & anomaly notifications
          </h3>
        </div>
        <div className="rounded-lg bg-slate-100 p-2 text-slate-600">
          <Mail className="h-4 w-4" />
        </div>
      </div>

      <p className="mt-4 text-sm text-slate-500">
        Receive budget, burn rate, anomaly, idle spend, and weekly summary alerts by email.
        Add comma-separated addresses.
      </p>

      {status?.enabled && status.recipient_count > 0 && (
        <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
          {status.recipient_count} recipient(s) configured: {status.masked_recipients}
        </div>
      )}

      <div className="mt-4 flex flex-col gap-3">
        <input
          value={recipients}
          onChange={(e) => setRecipients(e.target.value)}
          placeholder="alerts@example.com, finance@example.com"
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        <div className="flex flex-wrap gap-3">
          <button
            onClick={saveEmailAlerts}
            className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-700"
          >
            Save email alerts
          </button>
          {status?.enabled && (
            <button
              onClick={clearEmailAlerts}
              className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              Disable
            </button>
          )}
        </div>
      </div>

      {message && <p className="mt-3 text-xs text-emerald-600">{message}</p>}
      {error && <p className="mt-3 text-xs text-rose-600">{error}</p>}
    </div>
  );
}
