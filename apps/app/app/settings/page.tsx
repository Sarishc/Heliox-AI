"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import {
  clearStoredAccessToken,
  clearStoredApiKey,
  fetchJson,
  getStoredAccessToken,
  getStoredApiKey,
  setStoredAccessToken,
  setStoredApiKey,
} from "@/lib/api";

interface MeResponse {
  team_id: string;
  role: string;
  feature_flags: Record<string, boolean>;
}

interface TeamApiKey {
  id: string;
  team_id: string;
  key_name: string;
  is_active: boolean;
  created_at: string;
  last_used_at?: string | null;
}

interface AuditLog {
  id: string;
  team_id: string;
  actor_type: string;
  actor_id?: string | null;
  action: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

interface TeamResponse {
  id: string;
  monthly_budget_usd?: number | null;
}

const RUNWAY_EXPAND_FLAG = "heliox_runway_expand_after_budget";

export default function SettingsPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [token, setToken] = useState("");
  const [keys, setKeys] = useState<TeamApiKey[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [newKeyName, setNewKeyName] = useState("Founder key");
  const [rotationKey, setRotationKey] = useState<string | null>(null);
  const [rotationKeyValue, setRotationKeyValue] = useState<string | null>(null);
  const [teamBudget, setTeamBudget] = useState<number | null>(null);
  const [budgetInput, setBudgetInput] = useState("");
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const existingKey = getStoredApiKey();
    const existingToken = getStoredAccessToken();
    if (existingKey) setApiKey(existingKey);
    if (existingToken) setToken(existingToken);
  }, []);

  useEffect(() => {
    const loadMe = async () => {
      try {
        const result = await fetchJson<MeResponse>("/api/v1/me");
        setMe(result);
        setMeError(null);
      } catch (err) {
        setMe(null);
        setMeError("Unable to load team context. Set API key or access token.");
      }
    };
    loadMe();
  }, [apiKey, token]);

  const teamId = me?.team_id;
  const canManageKeys = me?.role && me.role !== "unknown" && me.role !== "api_key";

  useEffect(() => {
    const loadKeys = async () => {
      if (!teamId || !canManageKeys) {
        setKeys([]);
        return;
      }
      try {
        const result = await fetchJson<TeamApiKey[]>(
          `/api/v1/teams/${teamId}/api-keys`
        );
        setKeys(result);
      } catch (err) {
        setErrorMessage("Unable to load API keys. Ensure you are logged in.");
      }
    };
    loadKeys();
  }, [teamId, canManageKeys]);

  useEffect(() => {
    const loadTeamBudget = async () => {
      if (!teamId || !canManageKeys) {
        setTeamBudget(null);
        setBudgetInput("");
        return;
      }
      try {
        const result = await fetchJson<TeamResponse>(`/api/v1/teams/${teamId}`);
        const budget = result.monthly_budget_usd ?? null;
        setTeamBudget(budget);
        setBudgetInput(budget ? String(budget) : "");
      } catch (err) {
        setTeamBudget(null);
      }
    };
    loadTeamBudget();
  }, [teamId, canManageKeys]);

  useEffect(() => {
    const loadAudit = async () => {
      if (!teamId || !canManageKeys) {
        setAuditLogs([]);
        return;
      }
      try {
        const result = await fetchJson<AuditLog[]>(
          `/api/v1/teams/${teamId}/audit-logs?actions=api_key_created,api_key_revoked,api_key_rotated&limit=50`
        );
        setAuditLogs(result);
      } catch (err) {
        setAuditLogs([]);
      }
    };
    loadAudit();
  }, [teamId, canManageKeys, rotationKeyValue]);

  const handleSaveApiKey = () => {
    if (!apiKey.trim()) return;
    setStoredApiKey(apiKey.trim());
    setInfoMessage("API key saved.");
  };

  const handleSaveToken = () => {
    if (!token.trim()) return;
    setStoredAccessToken(token.trim());
    setInfoMessage("Access token saved.");
  };

  const handleClearApiKey = () => {
    clearStoredApiKey();
    setApiKey("");
  };

  const handleClearToken = () => {
    clearStoredAccessToken();
    setToken("");
  };

  const createApiKey = async () => {
    if (!teamId) return;
    const payload = { team_id: teamId, key_name: newKeyName };
    const response = await fetchJson<{ api_key: string; id: string }>(
      `/api/v1/teams/${teamId}/api-keys`,
      { method: "POST", body: JSON.stringify(payload) }
    );
    setRotationKeyValue(response.api_key);
    setInfoMessage("New API key created. Save it now.");
  };

  const rotateApiKey = async (keyId: string) => {
    if (!teamId) return;
    const payload = { team_id: teamId, key_name: `${newKeyName} (rotated)` };
    const response = await fetchJson<{ api_key: string; id: string }>(
      `/api/v1/teams/${teamId}/api-keys/${keyId}/rotate`,
      { method: "POST", body: JSON.stringify(payload) }
    );
    setRotationKey(keyId);
    setRotationKeyValue(response.api_key);
  };

  const revokeApiKey = async (keyId: string) => {
    if (!teamId) return;
    await fetchJson(`/api/v1/teams/${teamId}/api-keys/${keyId}`, {
      method: "DELETE",
    });
    setInfoMessage("API key revoked.");
  };

  const handleUpdateBudget = async () => {
    if (!teamId) return;
    const parsed = Number(budgetInput);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setErrorMessage("Enter a valid monthly budget.");
      return;
    }
    const result = await fetchJson<TeamResponse>(`/api/v1/teams/${teamId}/budget`, {
      method: "PUT",
      body: JSON.stringify({ monthly_budget_usd: parsed }),
    });
    setTeamBudget(result.monthly_budget_usd ?? parsed);
    setInfoMessage("Monthly budget updated.");
    if (typeof window !== "undefined") {
      localStorage.setItem(RUNWAY_EXPAND_FLAG, "true");
    }
  };

  const sendMockUsage = async () => {
    const payload = {
      metrics: [
        {
          timestamp: new Date().toISOString(),
          provider: "aws",
          gpu_type: "a100",
          gpu_hours: 1.1,
          tags: { env: "demo" },
        },
      ],
    };
    await fetchJson("/api/v1/ingest/usage", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setInfoMessage("Mock usage sent.");
  };

  const sendMockCost = async () => {
    const payload = {
      records: [
        {
          date: new Date().toISOString().slice(0, 10),
          provider: "aws",
          gpu_type: "a100",
          cost_usd: 125.5,
        },
      ],
    };
    await fetchJson("/api/v1/ingest/cost", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setInfoMessage("Mock cost sent.");
  };

  return (
    <AppShell>
      <div className="max-w-5xl space-y-6">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Settings</p>
          <h1 className="text-2xl font-semibold text-slate-900">
            Workspace configuration
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            Manage API access, budgets, and security settings.
          </p>
        </div>

        <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">Team Context</h2>
          <p className="text-sm text-gray-500 mt-1">
            Shows the active team derived from your API key or access token.
          </p>
          {me ? (
            <div className="mt-4 text-sm text-gray-700 space-y-1">
              <div>Team ID: {me.team_id || "—"}</div>
              <div>Role: {me.role}</div>
              <div>Multi-tenant: {String(me.feature_flags.multi_tenant)}</div>
            </div>
          ) : (
            <p className="text-sm text-gray-500 mt-4">{meError}</p>
          )}
        </section>

        <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">Access Token</h2>
          <p className="text-sm text-gray-500 mt-1">
            Required to manage API keys and audit logs.
          </p>
          <div className="mt-4 flex flex-col gap-3">
            <input
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste JWT access token"
              className="border border-gray-300 rounded-md px-3 py-2 text-sm"
            />
            <div className="flex gap-2">
              <button
                onClick={handleSaveToken}
                className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm"
              >
                Save token
              </button>
              <button
                onClick={handleClearToken}
                className="px-4 py-2 border border-gray-300 rounded-md text-sm"
              >
                Clear token
              </button>
              <Link href="/login" className="text-sm text-blue-600 self-center">
                Get token
              </Link>
            </div>
          </div>
        </section>

        <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">API Key</h2>
          <p className="text-sm text-gray-500 mt-1">
            Used for ingestion, analytics, and forecast requests.
          </p>
          <div className="mt-4 flex flex-col gap-3">
            <input
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Paste team API key"
              className="border border-gray-300 rounded-md px-3 py-2 text-sm"
            />
            <div className="flex gap-2">
              <button
                onClick={handleSaveApiKey}
                className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm"
              >
                Save API key
              </button>
              <button
                onClick={handleClearApiKey}
                className="px-4 py-2 border border-gray-300 rounded-md text-sm"
              >
                Clear API key
              </button>
            </div>
          </div>
        </section>

        <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">Monthly Budget</h2>
          <p className="text-sm text-gray-500 mt-1">
            Sets the budget used for runway forecasting.
          </p>
          {canManageKeys ? (
            <div className="mt-4 flex flex-col gap-3">
              <input
                value={budgetInput}
                onChange={(e) => setBudgetInput(e.target.value)}
                placeholder="e.g. 25000"
                className="border border-gray-300 rounded-md px-3 py-2 text-sm"
              />
              <div className="flex items-center gap-3 text-sm text-gray-500">
                <button
                  onClick={handleUpdateBudget}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm"
                >
                  Update budget
                </button>
                <span>
                  Current: {teamBudget ? `$${teamBudget.toLocaleString()}` : "Not set"}
                </span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500 mt-4">
              Login with a user token to manage the team budget.
            </p>
          )}
        </section>

        <section className="bg-white border border-gray-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900">API Key Rotation</h2>
          {canManageKeys ? (
            <>
              <div className="mt-4 flex gap-2">
                <input
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                  placeholder="Key name"
                />
                <button
                  onClick={createApiKey}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm"
                >
                  Create key
                </button>
              </div>
              <div className="mt-4 space-y-2">
                {keys.map((key) => (
                  <div
                    key={key.id}
                    className="flex items-center justify-between border border-gray-200 rounded-md px-3 py-2 text-sm"
                  >
                    <div>
                      <div className="font-medium text-gray-900">{key.key_name}</div>
                      <div className="text-gray-500">
                        {key.is_active ? "Active" : "Revoked"} • {key.id.slice(0, 8)}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => rotateApiKey(key.id)}
                        className="text-blue-600 hover:text-blue-700"
                      >
                        Rotate
                      </button>
                      <button
                        onClick={() => revokeApiKey(key.id)}
                        className="text-red-600 hover:text-red-700"
                      >
                        Revoke
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              {rotationKeyValue && (
                <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-md text-sm">
                  <p className="font-medium text-yellow-800">
                    New API key (save now):
                  </p>
                  <p className="mt-1 text-yellow-900 break-all">{rotationKeyValue}</p>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-gray-500 mt-4">
              Login with a user token to manage keys.
            </p>
          )}
        </section>

        <section className="bg-white border border-gray-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900">API Key Audit Log</h2>
          {auditLogs.length === 0 ? (
            <p className="text-sm text-gray-500 mt-2">No audit events yet.</p>
          ) : (
            <div className="mt-3 space-y-2 text-sm">
              {auditLogs.map((log) => (
                <div key={log.id} className="border border-gray-200 rounded-md p-2">
                  <div className="font-medium text-gray-900">{log.action}</div>
                  <div className="text-gray-500">
                    {new Date(log.created_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="bg-white border border-gray-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900">Ingestion Test</h2>
          <p className="text-sm text-gray-500 mt-1">
            Send mock usage and cost to verify ingestion pipeline.
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={sendMockUsage}
              className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm"
            >
              Send mock usage
            </button>
            <button
              onClick={sendMockCost}
              className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm"
            >
              Send mock cost
            </button>
          </div>
        </section>

        {(infoMessage || errorMessage) && (
          <section className="bg-white border border-gray-200 rounded-lg p-4 text-sm">
            {infoMessage && <p className="text-green-600">{infoMessage}</p>}
            {errorMessage && <p className="text-red-600">{errorMessage}</p>}
          </section>
        )}
      </div>
    </AppShell>
  );
}
