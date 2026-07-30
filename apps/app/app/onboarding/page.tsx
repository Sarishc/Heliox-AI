"use client";

/**
 * Production-ready onboarding wizard for new Heliox users.
 * Multi-step flow: Welcome → Create Team → Connect Data (optional) → Alerts (optional) → Complete
 * Role-aware, resumable, and grounded in existing Heliox features.
 */

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Zap,
  Users,
  Cloud,
  Bell,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  ExternalLink,
  Loader2,
} from "lucide-react";
import { fetchJson } from "@/lib/api";
import { AuthShell } from "@/components/auth/AuthShell";

interface OnboardingStatus {
  has_team: boolean;
  has_api_key: boolean;
  has_integration: boolean;
  has_slack_webhook: boolean;
  can_manage: boolean;
  role: string;
}

const STEPS = [
  { id: "welcome", title: "Welcome", icon: Zap },
  { id: "team", title: "Create team", icon: Users },
  { id: "connect", title: "Connect data", icon: Cloud },
  { id: "alerts", title: "Alerts", icon: Bell },
  { id: "complete", title: "You're set", icon: CheckCircle2 },
];

export default function OnboardingPage() {
  const router = useRouter();
  const [stepIndex, setStepIndex] = useState(0);
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);

  // Team creation form
  const [teamName, setTeamName] = useState("");
  const [apiKeyName, setApiKeyName] = useState("Default key");
  const [monthlyBudget, setMonthlyBudget] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [apiKeyDisplay, setApiKeyDisplay] = useState<string | null>(null);

  useEffect(() => {
    loadStatus();
  }, []);

  async function loadStatus() {
    setLoadingStatus(true);
    try {
      const data = await fetchJson<OnboardingStatus>("/api/v1/onboarding/status");
      setStatus(data);
      // If user already has team, skip to connect step or complete
      if (data.has_team) {
        if (!data.has_integration && data.can_manage) setStepIndex(2);
        else if (!data.has_slack_webhook && data.can_manage) setStepIndex(3);
        else setStepIndex(4);
      }
    } catch {
      setStatus(null);
    } finally {
      setLoadingStatus(false);
    }
  }

  const handleCreateTeam = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const payload: {
        team_name: string;
        api_key_name: string;
        monthly_budget_usd?: number;
      } = {
        team_name: teamName.trim(),
        api_key_name: apiKeyName.trim() || "Default key",
      };
      if (monthlyBudget && !isNaN(parseFloat(monthlyBudget))) {
        payload.monthly_budget_usd = parseFloat(monthlyBudget);
      }
      const res = await fetchJson<{ team_id: string; api_key: string; message: string }>(
        "/api/v1/onboarding/welcome",
        { method: "POST", body: JSON.stringify(payload) }
      );
      if (res.api_key) {
        setApiKeyDisplay(res.api_key);
        setShowKeyModal(true);
        await loadStatus();
      } else {
        router.push("/");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create team");
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyModalContinue = () => {
    setShowKeyModal(false);
    setApiKeyDisplay(null);
    setStepIndex(2);
    loadStatus();
  };

  const goNext = () => {
    if (stepIndex < STEPS.length - 1) setStepIndex(stepIndex + 1);
    else router.push("/");
  };

  const goBack = () => {
    if (stepIndex > 0) setStepIndex(stepIndex - 1);
  };

  const currentStep = STEPS[stepIndex];

  if (loadingStatus) {
    return (
      <AuthShell title="Your Heliox workspace is taking shape.">
        <div className="flex items-center gap-3 text-sm text-slate-400" role="status">
          <Loader2 className="h-5 w-5 animate-spin text-violet-400" /> Loading workspace setup…
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      eyebrow="Guided workspace setup"
      title="From account to operational insight in minutes."
      description="Create the workspace boundary, secure an API key, and connect data when your team is ready."
    >
      <div className="w-full">
        {/* Progress */}
        <div className="mb-8 flex items-center justify-between gap-2">
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            const done = i < stepIndex || (i === 1 && status?.has_team);
            const active = i === stepIndex;
            return (
              <div
                key={s.id}
                className={`flex flex-1 items-center ${i < STEPS.length - 1 ? "" : ""}`}
              >
                <div
                  className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                    active
                      ? "bg-violet-600 text-white"
                      : done
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-slate-200 text-slate-500"
                  }`}
                >
                  {done && !active ? (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  ) : (
                    <Icon className="h-3.5 w-3.5" />
                  )}
                  <span className="hidden sm:inline">{s.title}</span>
                </div>
                {i < STEPS.length - 1 && (
                  <div
                    className={`mx-1 h-0.5 flex-1 ${done ? "bg-emerald-300" : "bg-slate-200"}`}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* Card */}
        <div className="rounded-md border border-slate-700 bg-[#11141d] p-6 sm:p-8">
          {currentStep.id === "welcome" && (
            <div className="space-y-6">
              <div>
                <h1 className="text-2xl font-bold text-slate-900">Welcome to Heliox</h1>
                <p className="mt-2 text-slate-600">
                  Heliox helps you optimize GPU costs across cloud providers. In a few steps you’ll
                  have your team set up, API key ready, and optional integrations configured.
                </p>
              </div>
              <ul className="space-y-2 text-sm text-slate-600">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                  Track GPU spend and usage
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                  Connect AWS or GCP for automatic cost import
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                  Get Slack alerts for budgets and anomalies
                </li>
              </ul>
              <div className="flex justify-end">
                <button
                  onClick={goNext}
                  className="auth-primary"
                >
                  Get started
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {currentStep.id === "team" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-slate-900">Create your team</h2>
                <p className="mt-1 text-sm text-slate-600">
                  Your team is the workspace for cost data, API keys, and integrations.
                </p>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Team name
                  </label>
                  <input
                    value={teamName}
                    onChange={(e) => setTeamName(e.target.value)}
                    className="auth-input"
                    placeholder="My Team"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    API key name
                  </label>
                  <input
                    value={apiKeyName}
                    onChange={(e) => setApiKeyName(e.target.value)}
                    className="auth-input"
                    placeholder="Default key"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Monthly budget (USD, optional)
                  </label>
                  <input
                    type="number"
                    value={monthlyBudget}
                    onChange={(e) => setMonthlyBudget(e.target.value)}
                    className="auth-input"
                    placeholder="25000"
                  />
                </div>
              </div>
              {error && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                  {error}
                </div>
              )}
              <div className="flex justify-between">
                <button
                  onClick={goBack}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  <ArrowLeft className="inline h-4 w-4 mr-1" />
                  Back
                </button>
                <button
                  onClick={handleCreateTeam}
                  disabled={submitting || !teamName.trim()}
                  className="auth-primary"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    <>
                      Create team
                      <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {currentStep.id === "connect" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-slate-900">Connect your cloud data</h2>
                <p className="mt-1 text-sm text-slate-600">
                  Import GPU costs from AWS Cost Explorer or GCP BigQuery. You can also skip and add
                  this later in Settings.
                </p>
              </div>
              {status?.has_integration ? (
                <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 flex items-center gap-3">
                  <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
                  <span className="text-sm text-emerald-800">Cloud integration connected</span>
                </div>
              ) : status?.can_manage ? (
                <Link
                  href="/settings/integrations"
                  className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-100"
                >
                  Connect AWS or GCP
                  <ExternalLink className="h-4 w-4 text-slate-400" />
                </Link>
              ) : (
                <p className="text-sm text-slate-500">
                  Ask your team admin to connect a cloud provider in Settings → Integrations.
                </p>
              )}
              <div className="flex justify-between">
                <button
                  onClick={goBack}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  <ArrowLeft className="inline h-4 w-4 mr-1" />
                  Back
                </button>
                <button
                  onClick={goNext}
                  className="auth-primary"
                >
                  {status?.has_integration ? "Next" : "Skip for now"}
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {currentStep.id === "alerts" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold text-slate-900">Set up Slack alerts</h2>
                <p className="mt-1 text-sm text-slate-600">
                  Get notified about budget overruns and cost anomalies. Optional—you can configure
                  this later.
                </p>
              </div>
              {status?.has_slack_webhook ? (
                <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 flex items-center gap-3">
                  <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
                  <span className="text-sm text-emerald-800">Slack webhook configured</span>
                </div>
              ) : status?.can_manage ? (
                <Link
                  href="/alerts"
                  className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-100"
                >
                  Configure Slack webhook
                  <ExternalLink className="h-4 w-4 text-slate-400" />
                </Link>
              ) : (
                <p className="text-sm text-slate-500">
                  Ask your team admin to configure Slack in Alerts.
                </p>
              )}
              <div className="flex justify-between">
                <button
                  onClick={goBack}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  <ArrowLeft className="inline h-4 w-4 mr-1" />
                  Back
                </button>
                <button
                  onClick={goNext}
                  className="auth-primary"
                >
                  {status?.has_slack_webhook ? "Next" : "Skip for now"}
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {currentStep.id === "complete" && (
            <div className="space-y-6">
              <div className="text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100">
                  <CheckCircle2 className="h-8 w-8 text-emerald-600" />
                </div>
                <h2 className="text-xl font-semibold text-slate-900">You're all set</h2>
                <p className="mt-2 text-sm text-slate-600">
                  Your team is ready. Go to the dashboard to explore costs, forecasts, and
                  optimization recommendations.
                </p>
              </div>
              <div className="space-y-2 text-sm text-slate-600">
                <p>Next steps:</p>
                <ul className="list-disc list-inside space-y-1">
                  <li>View your dashboard and enable demo mode if you have no data yet</li>
                  <li>Connect AWS or GCP in Settings → Integrations</li>
                  <li>Configure Slack alerts in Alerts</li>
                </ul>
              </div>
              <div className="flex justify-between">
                <button
                  onClick={goBack}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  <ArrowLeft className="inline h-4 w-4 mr-1" />
                  Back
                </button>
                <button
                  onClick={() => router.push("/")}
                  className="auth-primary"
                >
                  Go to dashboard
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </div>

        <p className="mt-6 text-center">
          <Link href="/login" className="text-sm text-slate-500 hover:text-slate-700">
            Sign out
          </Link>
        </p>
      </div>

      {/* API key modal */}
      {showKeyModal && apiKeyDisplay && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="max-w-md w-full rounded-md border border-slate-700 bg-[#11141d] p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-2">Save your API key</h2>
            <p className="text-sm text-slate-600 mb-4">
              This key is shown only once. Copy it now for CLI and programmatic access. Do not
              store it in the browser.
            </p>
            <div className="bg-slate-100 rounded-lg p-3 mb-4 break-all text-sm font-mono">
              {apiKeyDisplay}
            </div>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(apiKeyDisplay);
                  handleKeyModalContinue();
                }}
                className="auth-primary w-full"
              >
                Copy and continue
              </button>
              <button
                onClick={handleKeyModalContinue}
                className="w-full text-sm text-slate-600 hover:text-slate-900"
              >
                Continue without copying
              </button>
            </div>
          </div>
        </div>
      )}
    </AuthShell>
  );
}
