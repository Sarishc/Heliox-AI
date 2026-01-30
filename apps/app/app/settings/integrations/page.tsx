"use client";

import { useState, useEffect } from "react";
import { fetchJson } from "@/lib/api";

interface AvailableIntegration {
  provider: string;
  display_name: string;
  description: string;
  enabled: boolean;
  config_schema: any;
}

interface IntegrationConnection {
  id: string;
  team_id: string;
  provider: string;
  name: string;
  description?: string;
  config: Record<string, any>;
  status: string;
  last_error?: string;
  last_sync_at?: string;
  last_successful_sync_at?: string;
  auto_sync_enabled: boolean;
  sync_interval_minutes: number;
  created_at: string;
  updated_at: string;
}

interface SyncRun {
  id: string;
  connection_id: string;
  started_at: string;
  finished_at?: string;
  status: string;
  error?: string;
  metrics?: Record<string, any>;
  triggered_by: string;
}

export default function IntegrationsPage() {
  const [available, setAvailable] = useState<AvailableIntegration[]>([]);
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<Record<string, boolean>>({});

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [availableData, connectionsData] = await Promise.all([
        fetchJson<AvailableIntegration[]>("/api/v1/integrations/available"),
        fetchJson<{ connections: IntegrationConnection[] }>("/api/v1/integrations"),
      ]);
      setAvailable(availableData);
      setConnections(connectionsData.connections);
    } catch (error) {
      console.error("Failed to load integrations:", error);
    } finally {
      setLoading(false);
    }
  }

  async function triggerSync(connectionId: string) {
    setSyncing((prev) => ({ ...prev, [connectionId]: true }));
    try {
      await fetchJson<SyncRun>(`/api/v1/integrations/${connectionId}/sync`, {
        method: "POST",
      });
      // Reload connections to get updated sync time
      setTimeout(() => loadData(), 1000);
    } catch (error) {
      console.error("Sync failed:", error);
      alert("Failed to trigger sync. See console for details.");
    } finally {
      setSyncing((prev) => ({ ...prev, [connectionId]: false }));
    }
  }

  function getProviderIcon(provider: string): string {
    const icons: Record<string, string> = {
      aws: "☁️",
      gcp: "🌐",
      azure: "💠",
      stripe: "💳",
      sso_google: "🔐",
      sso_okta: "🔑",
      slack: "💬",
    };
    return icons[provider] || "🔌";
  }

  function getStatusBadge(status: string) {
    const badges: Record<string, { bg: string; text: string; label: string }> = {
      active: { bg: "bg-green-100", text: "text-green-800", label: "Active" },
      error: { bg: "bg-red-100", text: "text-red-800", label: "Error" },
      disabled: { bg: "bg-gray-100", text: "text-gray-800", label: "Disabled" },
      pending: { bg: "bg-yellow-100", text: "text-yellow-800", label: "Pending" },
    };
    const badge = badges[status] || badges.pending;
    return (
      <span className={`px-2 py-1 rounded text-xs font-medium ${badge.bg} ${badge.text}`}>
        {badge.label}
      </span>
    );
  }

  function formatDate(dateString?: string): string {
    if (!dateString) return "Never";
    const date = new Date(dateString);
    return date.toLocaleString();
  }

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Integrations</h1>
        <div className="text-gray-500">Loading integrations...</div>
      </div>
    );
  }

  const connectedProviders = new Set(connections.map((c) => c.provider));

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-2">Integrations</h1>
        <p className="text-gray-600">
          Connect external services to automatically sync GPU costs and usage data.
        </p>
      </div>

      {/* Available Integrations */}
      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-4">Available Integrations</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {available.map((integration) => {
            const isConnected = connectedProviders.has(integration.provider);
            const isEnabled = integration.enabled;

            return (
              <div
                key={integration.provider}
                className={`border rounded-lg p-4 ${
                  isEnabled ? "border-gray-200" : "border-gray-100 bg-gray-50"
                }`}
              >
                <div className="flex items-start gap-3 mb-3">
                  <span className="text-3xl">{getProviderIcon(integration.provider)}</span>
                  <div className="flex-1">
                    <h3 className="font-semibold text-lg">{integration.display_name}</h3>
                    <p className="text-sm text-gray-600">{integration.description}</p>
                  </div>
                </div>

                {isConnected ? (
                  <div className="flex items-center gap-2">
                    <span className="text-green-600 text-sm font-medium">✓ Connected</span>
                  </div>
                ) : isEnabled ? (
                  <button
                    className="w-full mt-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition"
                    onClick={() => alert("Connect modal coming soon")}
                  >
                    Connect
                  </button>
                ) : (
                  <div className="mt-2 text-center">
                    <span className="text-sm text-gray-500 italic">Coming soon</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Connected Integrations */}
      {connections.length > 0 && (
        <section>
          <h2 className="text-xl font-semibold mb-4">Connected Integrations</h2>
          <div className="space-y-4">
            {connections.map((connection) => (
              <div key={connection.id} className="border rounded-lg p-4 bg-white">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{getProviderIcon(connection.provider)}</span>
                    <div>
                      <h3 className="font-semibold">{connection.name}</h3>
                      {connection.description && (
                        <p className="text-sm text-gray-600">{connection.description}</p>
                      )}
                    </div>
                  </div>
                  {getStatusBadge(connection.status)}
                </div>

                <div className="grid grid-cols-2 gap-4 mb-3 text-sm">
                  <div>
                    <span className="text-gray-600">Last Sync:</span>
                    <div className="font-medium">{formatDate(connection.last_sync_at)}</div>
                  </div>
                  <div>
                    <span className="text-gray-600">Last Successful:</span>
                    <div className="font-medium">
                      {formatDate(connection.last_successful_sync_at)}
                    </div>
                  </div>
                  <div>
                    <span className="text-gray-600">Auto-sync:</span>
                    <div className="font-medium">
                      {connection.auto_sync_enabled
                        ? `Every ${connection.sync_interval_minutes} min`
                        : "Disabled"}
                    </div>
                  </div>
                  <div>
                    <span className="text-gray-600">Provider:</span>
                    <div className="font-medium capitalize">{connection.provider}</div>
                  </div>
                </div>

                {connection.last_error && (
                  <div className="mb-3 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-800">
                    <strong>Error:</strong> {connection.last_error}
                  </div>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={() => triggerSync(connection.id)}
                    disabled={syncing[connection.id]}
                    className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition text-sm font-medium"
                  >
                    {syncing[connection.id] ? "Syncing..." : "Sync Now"}
                  </button>
                  <button
                    className="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50 transition text-sm font-medium"
                    onClick={() => alert("Edit coming soon")}
                  >
                    Edit
                  </button>
                  <button
                    className="px-4 py-2 border border-red-300 text-red-600 rounded hover:bg-red-50 transition text-sm font-medium"
                    onClick={() => alert("Delete coming soon")}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {connections.length === 0 && (
        <div className="text-center py-12 border-2 border-dashed border-gray-300 rounded-lg">
          <p className="text-gray-600 mb-4">No integrations connected yet.</p>
          <p className="text-sm text-gray-500">
            Connect an integration above to automatically sync your GPU costs.
          </p>
        </div>
      )}
    </div>
  );
}
