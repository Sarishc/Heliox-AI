"use client";

import { useEffect, useMemo, useState } from "react";
import BetaAccessGate from "@/components/BetaAccessGate";
import AppShell from "@/components/AppShell";
import { fetchJson } from "@/lib/api";

interface BudgetPolicy {
  id: string;
  environment: "prod" | "staging" | "dev";
  project?: string | null;
  monthly_budget_usd: number;
  alert_thresholds: number[];
  is_enabled: boolean;
}

interface BudgetStatus {
  policy: BudgetPolicy;
  mtd_spend_usd: number;
  percent_used: number;
  forecasted_eom_spend_usd: number;
  predicted_breach_date?: string | null;
}

function BudgetsContent() {
  const [policies, setPolicies] = useState<BudgetPolicy[]>([]);
  const [status, setStatus] = useState<BudgetStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [environment, setEnvironment] = useState<BudgetPolicy["environment"]>("prod");
  const [project, setProject] = useState("");
  const [monthlyBudget, setMonthlyBudget] = useState("");
  const [thresholds, setThresholds] = useState("0.7,0.85,1.0");

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [policiesResponse, statusResponse] = await Promise.all([
        fetchJson<BudgetPolicy[]>("/api/v1/budgets"),
        fetchJson<BudgetStatus[]>("/api/v1/budgets/status"),
      ]);
      setPolicies(policiesResponse);
      setStatus(statusResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load budgets.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleCreate = async () => {
    const payload = {
      environment,
      project: project.trim() || null,
      monthly_budget_usd: Number(monthlyBudget),
      alert_thresholds: thresholds.split(",").map((item) => Number(item.trim())),
      is_enabled: true,
    };
    await fetchJson("/api/v1/budgets", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setProject("");
    setMonthlyBudget("");
    await loadAll();
  };

  const handleToggle = async (policy: BudgetPolicy) => {
    await fetchJson(`/api/v1/budgets/${policy.id}`, {
      method: "PUT",
      body: JSON.stringify({ is_enabled: !policy.is_enabled }),
    });
    await loadAll();
  };

  const statusByPolicy = useMemo(() => {
    const map = new Map<string, BudgetStatus>();
    status.forEach((item) => map.set(item.policy.id, item));
    return map;
  }, [status]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Budgets</p>
        <h1 className="text-2xl font-semibold text-slate-900">
          Budget guardrails
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Define team budgets by environment or project and receive breach warnings.
        </p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Create policy</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <select
            value={environment}
            onChange={(event) => setEnvironment(event.target.value as BudgetPolicy["environment"])}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            <option value="prod">Production</option>
            <option value="staging">Staging</option>
            <option value="dev">Development</option>
          </select>
          <input
            value={project}
            onChange={(event) => setProject(event.target.value)}
            placeholder="Project (optional)"
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
          <input
            value={monthlyBudget}
            onChange={(event) => setMonthlyBudget(event.target.value)}
            placeholder="Monthly budget (USD)"
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
          <input
            value={thresholds}
            onChange={(event) => setThresholds(event.target.value)}
            placeholder="Thresholds (0.7,0.85,1.0)"
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
        </div>
        <button
          onClick={handleCreate}
          className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Create policy
        </button>
      </div>

      <div className="space-y-4">
        {loading ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
            Loading budget policies...
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
            {error}
          </div>
        ) : policies.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
            No budgets configured yet.
          </div>
        ) : (
          policies.map((policy) => {
            const policyStatus = statusByPolicy.get(policy.id);
            return (
              <div
                key={policy.id}
                className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">
                      {policy.environment.toUpperCase()} {policy.project ? `• ${policy.project}` : ""}
                    </h3>
                    <p className="text-sm text-slate-500">
                      Budget: ${policy.monthly_budget_usd.toLocaleString()} • Thresholds:{" "}
                      {policy.alert_thresholds.join(", ")}
                    </p>
                  </div>
                  <button
                    onClick={() => handleToggle(policy)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                      policy.is_enabled
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {policy.is_enabled ? "Enabled" : "Disabled"}
                  </button>
                </div>
                {policyStatus && (
                  <div className="mt-4 grid gap-4 md:grid-cols-3 text-sm text-slate-600">
                    <div>
                      <p className="text-xs uppercase text-slate-400">MTD spend</p>
                      <p className="text-base font-semibold text-slate-900">
                        ${policyStatus.mtd_spend_usd.toLocaleString()}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-slate-400">Used</p>
                      <p className="text-base font-semibold text-slate-900">
                        {(policyStatus.percent_used * 100).toFixed(0)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-slate-400">Predicted breach</p>
                      <p className="text-base font-semibold text-slate-900">
                        {policyStatus.predicted_breach_date ?? "None"}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default function BudgetsPage() {
  return (
    <BetaAccessGate>
      <AppShell>
        <BudgetsContent />
      </AppShell>
    </BetaAccessGate>
  );
}
