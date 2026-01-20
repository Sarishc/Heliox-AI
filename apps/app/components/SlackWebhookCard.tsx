"use client";

import { useEffect, useState } from "react";
import { Slack } from "lucide-react";
import { fetchJson } from "@/lib/api";

interface WebhookResponse {
  team_id: string;
  configured: boolean;
  masked_webhook_url?: string | null;
}

export default function SlackWebhookCard() {
  const [webhook, setWebhook] = useState("");
  const [status, setStatus] = useState<WebhookResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetchJson<WebhookResponse>("/api/v1/alerts/webhook");
        setStatus(response);
      } catch {
        setStatus(null);
      }
    };
    load();
  }, []);

  const saveWebhook = async () => {
    setMessage(null);
    setError(null);
    try {
      const response = await fetchJson<WebhookResponse>("/api/v1/alerts/webhook", {
        method: "POST",
        body: JSON.stringify({ team_id: status?.team_id, slack_webhook_url: webhook }),
      });
      setStatus(response);
      setWebhook("");
      setMessage("Slack webhook saved.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to save webhook. Ensure you are authenticated."
      );
    }
  };

  const clearWebhook = async () => {
    setMessage(null);
    setError(null);
    try {
      await fetchJson("/api/v1/alerts/webhook", { method: "DELETE" });
      setStatus({ team_id: status?.team_id ?? "", configured: false });
      setMessage("Slack webhook removed.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to remove webhook. Ensure you are authenticated."
      );
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Slack alerts</p>
          <h3 className="mt-1 text-lg font-semibold text-slate-900">
            Incident notifications
          </h3>
        </div>
        <div className="rounded-lg bg-slate-100 p-2 text-slate-600">
          <Slack className="h-4 w-4" />
        </div>
      </div>

      <p className="mt-4 text-sm text-slate-500">
        Configure a team-specific Slack webhook to receive anomaly and budget alerts.
      </p>

      {status?.configured && (
        <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
          Webhook configured: {status.masked_webhook_url}
        </div>
      )}

      <div className="mt-4 flex flex-col gap-3">
        <input
          value={webhook}
          onChange={(event) => setWebhook(event.target.value)}
          placeholder="https://hooks.slack.com/services/..."
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        <div className="flex flex-wrap gap-3">
          <button
            onClick={saveWebhook}
            className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-700"
          >
            Save webhook
          </button>
          <button
            onClick={clearWebhook}
            className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            Remove
          </button>
        </div>
      </div>

      {message && <p className="mt-3 text-xs text-emerald-600">{message}</p>}
      {error && <p className="mt-3 text-xs text-rose-600">{error}</p>}
    </div>
  );
}
