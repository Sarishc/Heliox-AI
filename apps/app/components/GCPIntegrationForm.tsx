"use client";

import { useState } from "react";
import { fetchJson } from "@/lib/api";

interface GCPFormData {
  name: string;
  gcp_project_id: string;
  bigquery_dataset: string;
  billing_export_table: string;
  service_account_json: string;
  label_key_for_team: string;
  description: string;
}

interface TestResult {
  valid: boolean;
  project_id?: string;
  dataset?: string;
  table?: string;
  table_rows?: number;
  service_account?: string;
  message: string;
  details?: any;
}

interface Props {
  onSuccess: () => void;
  onCancel: () => void;
}

export default function GCPIntegrationForm({ onSuccess, onCancel }: Props) {
  const [formData, setFormData] = useState<GCPFormData>({
    name: "GCP Production",
    gcp_project_id: "",
    bigquery_dataset: "billing_export",
    billing_export_table: "gcp_billing_export_v1",
    service_account_json: "",
    label_key_for_team: "",
    description: "GCP BigQuery billing export",
  });

  const [testing, setTesting] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string>("");

  function handleChange(field: keyof GCPFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
    setTestResult(null); // Clear test result when form changes
  }

  async function testCredentials() {
    setTesting(true);
    setError("");
    setTestResult(null);

    try {
      // Parse and validate JSON
      let saJson: any;
      try {
        saJson = JSON.parse(formData.service_account_json);
      } catch (e) {
        throw new Error("Invalid JSON format in service account key");
      }

      const result = await fetchJson<TestResult>("/api/v1/integrations/gcp/test", {
        method: "POST",
        body: JSON.stringify({
          gcp_project_id: formData.gcp_project_id,
          bigquery_dataset: formData.bigquery_dataset,
          billing_export_table: formData.billing_export_table,
          service_account_json: saJson,
          label_key_for_team: formData.label_key_for_team || undefined,
        }),
      });

      setTestResult(result);
    } catch (err: any) {
      setError(err.message || "Failed to test credentials");
    } finally {
      setTesting(false);
    }
  }

  async function handleConnect() {
    setConnecting(true);
    setError("");

    try {
      // Parse service account JSON
      let saJson: any;
      try {
        saJson = JSON.parse(formData.service_account_json);
      } catch (e) {
        throw new Error("Invalid JSON format in service account key");
      }

      await fetchJson("/api/v1/integrations/gcp/connect", {
        method: "POST",
        body: JSON.stringify({
          name: formData.name,
          description: formData.description,
          provider: "gcp_billing_bigquery",
          config: {
            gcp_project_id: formData.gcp_project_id,
            bigquery_dataset: formData.bigquery_dataset,
            billing_export_table: formData.billing_export_table,
            service_account_json: saJson,
            label_key_for_team: formData.label_key_for_team || undefined,
          },
          auto_sync_enabled: true,
          sync_interval_minutes: 60,
        }),
      });

      onSuccess();
    } catch (err: any) {
      setError(err.message || "Failed to connect GCP account");
    } finally {
      setConnecting(false);
    }
  }

  const canConnect = testResult?.valid && !connecting;

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 max-w-3xl mx-auto max-h-[90vh] overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Connect GCP BigQuery Billing</h2>
          <p className="text-gray-600 text-sm mt-1">
            Import GPU and infrastructure costs from BigQuery billing export
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
        {/* Connection Name */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Connection Name *
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) => handleChange("name", e.target.value)}
            placeholder="GCP Production"
            className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        {/* GCP Configuration */}
        <div className="space-y-3 border-t pt-4">
          <h3 className="font-semibold text-gray-900">BigQuery Configuration</h3>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              GCP Project ID *
            </label>
            <input
              type="text"
              value={formData.gcp_project_id}
              onChange={(e) => handleChange("gcp_project_id", e.target.value)}
              placeholder="my-project-123"
              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            />
            <p className="text-xs text-gray-500 mt-1">
              The GCP project where your BigQuery billing export is located
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              BigQuery Dataset *
            </label>
            <input
              type="text"
              value={formData.bigquery_dataset}
              onChange={(e) => handleChange("bigquery_dataset", e.target.value)}
              placeholder="billing_export"
              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            />
            <p className="text-xs text-gray-500 mt-1">
              The BigQuery dataset containing your billing export table
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Billing Export Table
            </label>
            <input
              type="text"
              value={formData.billing_export_table}
              onChange={(e) => handleChange("billing_export_table", e.target.value)}
              placeholder="gcp_billing_export_v1"
              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            />
            <p className="text-xs text-gray-500 mt-1">
              Default: gcp_billing_export_v1 (or gcp_billing_export_resource_v1)
            </p>
          </div>
        </div>

        {/* Service Account JSON */}
        <div className="border-t pt-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Service Account JSON Key *
          </label>
          <textarea
            value={formData.service_account_json}
            onChange={(e) => handleChange("service_account_json", e.target.value)}
            placeholder='{"type": "service_account", "project_id": "...", "private_key_id": "...", ...}'
            rows={8}
            className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-xs"
          />
          <p className="text-xs text-gray-500 mt-1">
            Paste the entire JSON key file downloaded from GCP Console
          </p>
        </div>

        {/* Optional Configuration */}
        <details className="border-t pt-4">
          <summary className="font-semibold text-gray-900 cursor-pointer hover:text-blue-600">
            Advanced Configuration (Optional)
          </summary>

          <div className="mt-3 space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Label Key for Team Mapping
              </label>
              <input
                type="text"
                value={formData.label_key_for_team}
                onChange={(e) => handleChange("label_key_for_team", e.target.value)}
                placeholder="team"
                className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
              />
              <p className="text-xs text-gray-500 mt-1">
                GCP label key to map costs to Heliox teams (e.g., "team", "department")
              </p>
            </div>

            <div>
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
          </div>
        </details>

        {/* Test Result */}
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
                <p className={`font-medium ${testResult.valid ? "text-green-800" : "text-red-800"}`}>
                  {testResult.message}
                </p>
                {testResult.valid && (
                  <div className="mt-2 text-sm text-gray-700 space-y-1">
                    <p>
                      <strong>Project:</strong> {testResult.project_id}
                    </p>
                    <p>
                      <strong>Dataset:</strong> {testResult.dataset}
                    </p>
                    <p>
                      <strong>Table:</strong> {testResult.table}
                    </p>
                    {testResult.table_rows !== undefined && (
                      <p>
                        <strong>Rows:</strong> {testResult.table_rows.toLocaleString()}
                      </p>
                    )}
                    {testResult.service_account && (
                      <p className="text-xs text-gray-600 mt-1">
                        Service Account: {testResult.service_account}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="p-4 rounded border bg-red-50 border-red-200">
            <p className="text-red-800 text-sm">{error}</p>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3 pt-4 border-t">
          <button
            onClick={testCredentials}
            disabled={
              testing ||
              !formData.gcp_project_id ||
              !formData.bigquery_dataset ||
              !formData.service_account_json
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
          Service account key is encrypted at rest and never logged.
        </p>
      </div>
    </div>
  );
}
