"use client";

import { useState } from "react";
import { fetchJson } from "@/lib/api";

interface AWSFormData {
  name: string;
  aws_access_key_id: string;
  aws_secret_access_key: string;
  aws_region: string;
  linked_account_ids: string;
  cost_allocation_tag_key: string;
  cost_allocation_tag_values: string;
  description: string;
}

interface TestResult {
  valid: boolean;
  account_id?: string;
  caller_arn?: string;
  message: string;
  details?: any;
}

interface Props {
  onSuccess: () => void;
  onCancel: () => void;
}

export default function AWSIntegrationForm({ onSuccess, onCancel }: Props) {
  const [formData, setFormData] = useState<AWSFormData>({
    name: "AWS Production",
    aws_access_key_id: "",
    aws_secret_access_key: "",
    aws_region: "us-east-1",
    linked_account_ids: "",
    cost_allocation_tag_key: "",
    cost_allocation_tag_values: "",
    description: "AWS Cost Explorer integration",
  });

  const [testing, setTesting] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string>("");

  function handleChange(field: keyof AWSFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
    setTestResult(null); // Clear test result when form changes
  }

  async function testCredentials() {
    setTesting(true);
    setError("");
    setTestResult(null);

    try {
      const result = await fetchJson<TestResult>("/api/v1/integrations/aws/test", {
        method: "POST",
        body: JSON.stringify({
          aws_access_key_id: formData.aws_access_key_id,
          aws_secret_access_key: formData.aws_secret_access_key,
          aws_region: formData.aws_region,
          linked_account_ids: formData.linked_account_ids
            .split(",")
            .map((id) => id.trim())
            .filter(Boolean),
          cost_allocation_tag_key: formData.cost_allocation_tag_key || undefined,
          cost_allocation_tag_values: formData.cost_allocation_tag_values
            .split(",")
            .map((v) => v.trim())
            .filter(Boolean),
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
      await fetchJson("/api/v1/integrations/aws/connect", {
        method: "POST",
        body: JSON.stringify({
          name: formData.name,
          description: formData.description,
          provider: "aws",
          config: {
            aws_access_key_id: formData.aws_access_key_id,
            aws_secret_access_key: formData.aws_secret_access_key,
            aws_region: formData.aws_region,
            linked_account_ids: formData.linked_account_ids
              .split(",")
              .map((id) => id.trim())
              .filter(Boolean),
            cost_allocation_tag_key: formData.cost_allocation_tag_key || undefined,
            cost_allocation_tag_values: formData.cost_allocation_tag_values
              .split(",")
              .map((v) => v.trim())
              .filter(Boolean),
          },
          auto_sync_enabled: true,
          sync_interval_minutes: 60,
        }),
      });

      onSuccess();
    } catch (err: any) {
      setError(err.message || "Failed to connect AWS account");
    } finally {
      setConnecting(false);
    }
  }

  const canConnect = testResult?.valid && !connecting;

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Connect AWS Cost Explorer</h2>
          <p className="text-gray-600 text-sm mt-1">
            Import GPU and infrastructure costs from AWS
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
            placeholder="AWS Production"
            className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        {/* AWS Credentials */}
        <div className="space-y-3 border-t pt-4">
          <h3 className="font-semibold text-gray-900">AWS Credentials</h3>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              AWS Access Key ID *
            </label>
            <input
              type="text"
              value={formData.aws_access_key_id}
              onChange={(e) => handleChange("aws_access_key_id", e.target.value)}
              placeholder="AKIA..."
              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              AWS Secret Access Key *
            </label>
            <input
              type="password"
              value={formData.aws_secret_access_key}
              onChange={(e) => handleChange("aws_secret_access_key", e.target.value)}
              placeholder="********"
              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              AWS Region
            </label>
            <select
              value={formData.aws_region}
              onChange={(e) => handleChange("aws_region", e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="us-east-1">US East (N. Virginia)</option>
              <option value="us-west-2">US West (Oregon)</option>
              <option value="eu-west-1">EU (Ireland)</option>
              <option value="ap-southeast-1">Asia Pacific (Singapore)</option>
            </select>
          </div>
        </div>

        {/* Optional Configuration */}
        <details className="border-t pt-4">
          <summary className="font-semibold text-gray-900 cursor-pointer hover:text-blue-600">
            Advanced Configuration (Optional)
          </summary>

          <div className="mt-3 space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Linked Account IDs
              </label>
              <input
                type="text"
                value={formData.linked_account_ids}
                onChange={(e) => handleChange("linked_account_ids", e.target.value)}
                placeholder="123456789012, 987654321098"
                className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
              />
              <p className="text-xs text-gray-500 mt-1">
                Comma-separated AWS account IDs to sync (leave empty for all accounts)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Cost Allocation Tag Key
              </label>
              <input
                type="text"
                value={formData.cost_allocation_tag_key}
                onChange={(e) => handleChange("cost_allocation_tag_key", e.target.value)}
                placeholder="Team"
                className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
              />
              <p className="text-xs text-gray-500 mt-1">
                Tag key for mapping costs to Heliox teams (e.g., "Team", "Department")
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Cost Allocation Tag Values
              </label>
              <input
                type="text"
                value={formData.cost_allocation_tag_values}
                onChange={(e) => handleChange("cost_allocation_tag_values", e.target.value)}
                placeholder="ml-research, data-science"
                className="w-full px-3 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
              />
              <p className="text-xs text-gray-500 mt-1">
                Comma-separated tag values to filter (leave empty for all values)
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
                {testResult.account_id && (
                  <div className="mt-2 text-sm text-gray-700">
                    <p>
                      <strong>Account ID:</strong> {testResult.account_id}
                    </p>
                    {testResult.caller_arn && (
                      <p className="text-xs text-gray-600 mt-1">
                        ARN: {testResult.caller_arn}
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
            disabled={testing || !formData.aws_access_key_id || !formData.aws_secret_access_key}
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
