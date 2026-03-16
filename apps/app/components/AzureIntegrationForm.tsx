"use client";

import { useState } from "react";
import { fetchJson } from "@/lib/api";

interface AzureFormData {
  name: string;
  azure_tenant_id: string;
  azure_client_id: string;
  azure_client_secret: string;
  subscription_ids: string;
  description: string;
}

interface TestResult {
  valid: boolean;
  subscription_id?: string;
  subscriptions_count?: number;
  message: string;
  details?: Record<string, unknown>;
}

interface Props {
  onSuccess: () => void;
  onCancel: () => void;
}

export default function AzureIntegrationForm({ onSuccess, onCancel }: Props) {
  const [formData, setFormData] = useState<AzureFormData>({
    name: "Azure Production",
    azure_tenant_id: "",
    azure_client_id: "",
    azure_client_secret: "",
    subscription_ids: "",
    description: "Azure Cost Management integration",
  });

  const [testing, setTesting] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string>("");

  function handleChange(field: keyof AzureFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
    setTestResult(null);
  }

  async function testCredentials() {
    setTesting(true);
    setError("");
    setTestResult(null);

    try {
      const subscriptionIds = formData.subscription_ids
        .split(",")
        .map((id) => id.trim())
        .filter(Boolean);

      const result = await fetchJson<TestResult>("/api/v1/integrations/azure/test", {
        method: "POST",
        body: JSON.stringify({
          azure_tenant_id: formData.azure_tenant_id.trim(),
          azure_client_id: formData.azure_client_id.trim(),
          azure_client_secret: formData.azure_client_secret,
          subscription_ids: subscriptionIds,
        }),
      });

      setTestResult(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to test credentials");
    } finally {
      setTesting(false);
    }
  }

  async function handleConnect() {
    setConnecting(true);
    setError("");

    try {
      const subscriptionIds = formData.subscription_ids
        .split(",")
        .map((id) => id.trim())
        .filter(Boolean);

      await fetchJson("/api/v1/integrations/azure/connect", {
        method: "POST",
        body: JSON.stringify({
          name: formData.name,
          description: formData.description,
          provider: "azure",
          config: {
            azure_tenant_id: formData.azure_tenant_id.trim(),
            azure_client_id: formData.azure_client_id.trim(),
            azure_client_secret: formData.azure_client_secret,
            subscription_ids: subscriptionIds,
          },
          auto_sync_enabled: true,
          sync_interval_minutes: 60,
        }),
      });

      onSuccess();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to connect Azure account");
    } finally {
      setConnecting(false);
    }
  }

  const canConnect = testResult?.valid && !connecting;
  const subscriptionIds = formData.subscription_ids
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean);

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 max-w-3xl mx-auto max-h-[90vh] overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Connect Azure Cost Management</h2>
          <p className="text-gray-600 text-sm mt-1">
            Import GPU and infrastructure costs from Azure Cost Management API
          </p>
        </div>
        <button
          onClick={onCancel}
          className="text-gray-500 hover:text-gray-700"
          title="Close"
        >
          ✕
        </button>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Connection Name *
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) => handleChange("name", e.target.value)}
            placeholder="Azure Production"
            className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        <div className="space-y-3 border-t pt-4">
          <h3 className="font-semibold text-gray-900">Azure App Registration</h3>
          <p className="text-sm text-gray-500">
            Create an app registration in Azure AD with Cost Management Reader role on your
            subscription(s).{" "}
            <a
              href="https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/assign-access-acm-data"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              Learn more
            </a>
          </p>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Tenant ID *
            </label>
            <input
              type="text"
              value={formData.azure_tenant_id}
              onChange={(e) => handleChange("azure_tenant_id", e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Client ID *
            </label>
            <input
              type="text"
              value={formData.azure_client_id}
              onChange={(e) => handleChange("azure_client_id", e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Client Secret *
            </label>
            <input
              type="password"
              value={formData.azure_client_secret}
              onChange={(e) => handleChange("azure_client_secret", e.target.value)}
              placeholder="••••••••••••••••••••"
              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            />
            <p className="text-xs text-gray-500 mt-1">
              App registration client secret (value, not secret ID)
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Subscription ID(s) *
            </label>
            <input
              type="text"
              value={formData.subscription_ids}
              onChange={(e) => handleChange("subscription_ids", e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (comma-separated for multiple)"
              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            />
            <p className="text-xs text-gray-500 mt-1">
              At least one subscription ID. Add Cost Management Reader role at subscription scope.
            </p>
          </div>
        </div>

        <details className="border-t pt-4">
          <summary className="font-semibold text-gray-900 cursor-pointer hover:text-blue-600">
            Advanced (Optional)
          </summary>
          <div className="mt-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => handleChange("description", e.target.value)}
              placeholder="Optional description..."
              rows={2}
              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
            />
          </div>
        </details>

        {testResult && (
          <div
            className={`p-4 rounded border ${
              testResult.valid
                ? "bg-green-50 border-green-200"
                : "bg-red-50 border-red-200"
            }`}
          >
            <div className="flex items-start gap-2">
              <span className="text-2xl">{testResult.valid ? "✓" : "✗"}</span>
              <div className="flex-1">
                <p
                  className={`font-medium ${
                    testResult.valid ? "text-green-800" : "text-red-800"
                  }`}
                >
                  {testResult.message}
                </p>
                {testResult.valid && (
                  <div className="mt-2 text-sm text-gray-700 space-y-1">
                    {testResult.subscription_id && (
                      <p>
                        <strong>Subscription:</strong> {testResult.subscription_id}
                      </p>
                    )}
                    {testResult.subscriptions_count !== undefined && (
                      <p>
                        <strong>Subscriptions:</strong> {testResult.subscriptions_count}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="p-4 rounded border bg-red-50 border-red-200">
            <p className="text-red-800 text-sm">{error}</p>
          </div>
        )}

        <div className="flex gap-3 pt-4 border-t">
          <button
            onClick={testCredentials}
            disabled={
              testing ||
              !formData.azure_tenant_id ||
              !formData.azure_client_id ||
              !formData.azure_client_secret ||
              subscriptionIds.length === 0
            }
            className="px-4 py-2 border border-blue-600 text-blue-600 rounded hover:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {testing ? "Testing..." : "Test Credentials"}
          </button>

          <button
            onClick={handleConnect}
            disabled={!canConnect}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {connecting ? "Connecting..." : "Connect & Sync"}
          </button>

          <button
            onClick={onCancel}
            className="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50 font-medium"
          >
            Cancel
          </button>
        </div>

        <p className="text-xs text-gray-500 text-center">
          Credentials are encrypted at rest and never logged.
        </p>
      </div>
    </div>
  );
}
