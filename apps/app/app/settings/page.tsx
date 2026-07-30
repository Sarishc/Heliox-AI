"use client";

import { useEffect, useMemo, useState } from "react";
import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import { fetchJson } from "@/lib/api";

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

interface TeamInvite {
  id: string;
  team_id: string;
  email: string;
  role: string;
  invited_by_user_id: string | null;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
}

interface TeamInviteCreateResponse {
  id: string;
  team_id: string;
  email: string;
  role: string;
  expires_at: string;
  invite_link: string;
  created_at: string;
}

const RUNWAY_EXPAND_FLAG = "heliox_runway_expand_after_budget";

export default function SettingsPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [keys, setKeys] = useState<TeamApiKey[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [newKeyName, setNewKeyName] = useState("Founder key");
  const [rotationKey, setRotationKey] = useState<string | null>(null);
  const [rotationKeyValue, setRotationKeyValue] = useState<string | null>(null);
  const [teamBudget, setTeamBudget] = useState<number | null>(null);
  const [budgetInput, setBudgetInput] = useState("");
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [invites, setInvites] = useState<TeamInvite[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"viewer" | "admin">("viewer");
  const [createdInviteLink, setCreatedInviteLink] = useState<string | null>(null);

  useEffect(() => {
    const loadMe = async () => {
      try {
        const result = await fetchJson<MeResponse>("/api/v1/me");
        setMe(result);
        setMeError(null);
      } catch (err) {
        setMe(null);
        setMeError("Unable to load team context. Please log in.");
      }
    };
    loadMe();
  }, []);

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
    const loadInvites = async () => {
      if (!teamId || !canManageKeys) {
        setInvites([]);
        return;
      }
      try {
        const result = await fetchJson<TeamInvite[]>(
          `/api/v1/teams/${teamId}/invites`
        );
        setInvites(result);
      } catch {
        setInvites([]);
      }
    };
    loadInvites();
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

  const createApiKey = async () => {
    if (!teamId) return;
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      const payload = { team_id: teamId, key_name: newKeyName };
      const response = await fetchJson<{ api_key: string; id: string }>(
        `/api/v1/teams/${teamId}/api-keys`,
        { method: "POST", body: JSON.stringify(payload) }
      );
      setRotationKeyValue(response.api_key);
      setInfoMessage("New API key created. Save it now.");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to create API key");
    }
  };

  const rotateApiKey = async (keyId: string) => {
    if (!teamId) return;
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      const payload = { team_id: teamId, key_name: `${newKeyName} (rotated)` };
      const response = await fetchJson<{ api_key: string; id: string }>(
        `/api/v1/teams/${teamId}/api-keys/${keyId}/rotate`,
        { method: "POST", body: JSON.stringify(payload) }
      );
      setRotationKey(keyId);
      setRotationKeyValue(response.api_key);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to rotate API key");
    }
  };

  const createInvite = async () => {
    if (!teamId || !inviteEmail.trim()) return;
    setErrorMessage(null);
    setInfoMessage(null);
    setCreatedInviteLink(null);
    try {
      const result = await fetchJson<TeamInviteCreateResponse>(
        `/api/v1/teams/${teamId}/invites`,
        { method: "POST", body: JSON.stringify({ email: inviteEmail.trim().toLowerCase(), role: inviteRole }) }
      );
      setCreatedInviteLink(result.invite_link);
      setInviteEmail("");
      setInfoMessage("Invite created. Copy the link and share it with your teammate.");
      const updated = await fetchJson<TeamInvite[]>(`/api/v1/teams/${teamId}/invites`);
      setInvites(updated);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to create invite");
    }
  };

  const revokeInvite = async (inviteId: string) => {
    if (!teamId) return;
    try {
      await fetchJson(`/api/v1/teams/${teamId}/invites/${inviteId}`, { method: "DELETE" });
      setInfoMessage("Invite revoked.");
      const updated = await fetchJson<TeamInvite[]>(`/api/v1/teams/${teamId}/invites`);
      setInvites(updated);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to revoke invite");
    }
  };

  const copyInviteLink = (link: string) => {
    navigator.clipboard.writeText(link);
    setInfoMessage("Invite link copied to clipboard.");
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
    <EnterpriseLayout>
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
            Shows the active team from your session (cookie-based auth).
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
          <h2 className="text-lg font-semibold text-gray-900">Team Invites</h2>
          <p className="text-sm text-gray-500 mt-1">
            Invite teammates by email. They receive a link to join your team.
          </p>
          {canManageKeys ? (
            <>
              <div className="mt-4 flex flex-wrap gap-2 items-center">
                <input
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="teammate@company.com"
                  className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                  type="email"
                />
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as "viewer" | "admin")}
                  className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                >
                  <option value="viewer">Viewer</option>
                  <option value="admin">Admin</option>
                </select>
                <button
                  onClick={createInvite}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm"
                >
                  Create invite
                </button>
              </div>
              {createdInviteLink && (
                <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-md text-sm">
                  <p className="font-medium text-amber-800">Invite link (share with your teammate):</p>
                  <div className="mt-2 flex gap-2 items-center">
                    <code className="flex-1 break-all text-amber-900">{createdInviteLink}</code>
                    <button
                      onClick={() => copyInviteLink(createdInviteLink)}
                      className="px-2 py-1 bg-amber-100 text-amber-800 rounded text-xs whitespace-nowrap"
                    >
                      Copy
                    </button>
                  </div>
                </div>
              )}
              <div className="mt-4 space-y-2">
                <p className="text-sm font-medium text-gray-700">Pending invites</p>
                {invites.length === 0 ? (
                  <p className="text-sm text-gray-500">No pending invites.</p>
                ) : (
                  invites.map((inv) => (
                    <div
                      key={inv.id}
                      className="flex items-center justify-between border border-gray-200 rounded-md px-3 py-2 text-sm"
                    >
                      <div>
                        <span className="font-medium text-gray-900">{inv.email}</span>
                        <span className="text-gray-500 ml-2">({inv.role})</span>
                      </div>
                      <button
                        onClick={() => revokeInvite(inv.id)}
                        className="text-red-600 hover:text-red-700"
                      >
                        Revoke
                      </button>
                    </div>
                  ))
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-500 mt-4">
              Owner or admin can invite teammates.
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
    </EnterpriseLayout>
  );
}
