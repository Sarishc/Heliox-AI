"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { fetchJson } from "@/lib/api";

export default function OnboardingPage() {
  const router = useRouter();
  const [teamName, setTeamName] = useState("");
  const [apiKeyName, setApiKeyName] = useState("Default key");
  const [monthlyBudget, setMonthlyBudget] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [apiKeyDisplay, setApiKeyDisplay] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    setLoading(true);
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
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );
      if (res.api_key) {
        setApiKeyDisplay(res.api_key);
        setShowKeyModal(true);
        return;
      }
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create team");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-white border border-gray-200 rounded-lg shadow-sm p-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Welcome to Heliox</h1>
        <p className="text-gray-600 mb-6">
          Create your team to get started with GPU cost intelligence.
        </p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Team name</label>
            <input
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              placeholder="My Team"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">API key name</label>
            <input
              value={apiKeyName}
              onChange={(e) => setApiKeyName(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              placeholder="Default key"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Monthly budget (USD, optional)
            </label>
            <input
              type="number"
              value={monthlyBudget}
              onChange={(e) => setMonthlyBudget(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              placeholder="25000"
            />
          </div>
          <button
            onClick={handleSubmit}
            disabled={loading || !teamName.trim()}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Creating..." : "Create team"}
          </button>
          <Link href="/login" className="block text-center text-blue-600 hover:text-blue-700 text-sm">
            Sign out
          </Link>
        </div>
        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-red-800 text-sm">{error}</p>
          </div>
        )}
      </div>

      {showKeyModal && apiKeyDisplay && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-2">Save your API key</h2>
            <p className="text-sm text-gray-600 mb-4">
              This key is shown only once. Copy it now for CLI and programmatic access. Do not store it in the browser.
            </p>
            <div className="bg-gray-100 rounded-md p-3 mb-4 break-all text-sm font-mono">
              {apiKeyDisplay}
            </div>
            <button
              onClick={() => {
                navigator.clipboard.writeText(apiKeyDisplay);
                setShowKeyModal(false);
                setApiKeyDisplay(null);
                router.push("/");
              }}
              className="w-full bg-blue-600 text-white py-2 px-4 rounded-lg font-medium hover:bg-blue-700"
            >
              Copy and continue
            </button>
            <button
              onClick={() => {
                setShowKeyModal(false);
                setApiKeyDisplay(null);
                router.push("/");
              }}
              className="w-full mt-2 text-gray-600 hover:text-gray-900 text-sm"
            >
              Continue without copying
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
