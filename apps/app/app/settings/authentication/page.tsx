"use client";

import { useState, useEffect } from "react";
import { fetchJson } from "@/lib/api";

interface SSOSettings {
  team_id: string;
  sso_enabled: boolean;
  sso_enforce_domain: boolean;
  allowed_email_domains: string[] | null;
  google_oauth_configured: boolean;
}

export default function AuthenticationSettingsPage() {
  const [settings, setSettings] = useState<SSOSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>("");
  const [success, setSuccess] = useState<string>("");

  // Form state
  const [ssoEnabled, setSsoEnabled] = useState(false);
  const [enforceDomain, setEnforceDomain] = useState(false);
  const [domains, setDomains] = useState<string>("");

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    setError("");
    try {
      const data = await fetchJson<SSOSettings>("/api/v1/teams/sso/settings");
      setSettings(data);
      setSsoEnabled(data.sso_enabled);
      setEnforceDomain(data.sso_enforce_domain);
      setDomains(data.allowed_email_domains?.join(", ") || "");
    } catch (err: any) {
      setError(err.message || "Failed to load SSO settings");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    setSuccess("");

    try {
      // Parse domains (comma-separated)
      const domainList = domains
        .split(",")
        .map((d) => d.trim())
        .filter((d) => d.length > 0);

      const data = await fetchJson<SSOSettings>("/api/v1/teams/sso/settings", {
        method: "PUT",
        body: JSON.stringify({
          sso_enabled: ssoEnabled,
          sso_enforce_domain: enforceDomain,
          allowed_email_domains: domainList.length > 0 ? domainList : null,
        }),
      });

      setSettings(data);
      setSuccess("SSO settings saved successfully!");
      
      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(""), 3000);
    } catch (err: any) {
      setError(err.message || "Failed to save SSO settings");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="p-8">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">Authentication Settings</h1>
          <div className="text-gray-600">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Authentication Settings</h1>
          <p className="text-gray-600">
            Configure Single Sign-On (SSO) for your team
          </p>
        </div>

        {/* Google OAuth Configuration Status */}
        {!settings?.google_oauth_configured && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
            <div className="flex items-start gap-3">
              <svg
                className="w-5 h-5 text-yellow-600 mt-0.5"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                  clipRule="evenodd"
                />
              </svg>
              <div>
                <h3 className="font-semibold text-yellow-900 mb-1">
                  Google OAuth Not Configured
                </h3>
                <p className="text-sm text-yellow-800">
                  The backend Google OAuth credentials are not configured. Contact your
                  administrator to set up GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the
                  backend environment.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* SSO Settings Form */}
        <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
          <h2 className="text-xl font-bold mb-4">Google SSO Configuration</h2>

          <div className="space-y-6">
            {/* Enable SSO */}
            <div className="flex items-center justify-between pb-4 border-b border-gray-200">
              <div>
                <h3 className="font-semibold text-gray-900">Enable Google SSO</h3>
                <p className="text-sm text-gray-600 mt-1">
                  Allow users to login with their Google accounts
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={ssoEnabled}
                  onChange={(e) => setSsoEnabled(e.target.checked)}
                  className="sr-only peer"
                  disabled={!settings?.google_oauth_configured}
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>

            {/* Enforce Domain Restriction */}
            <div className="flex items-center justify-between pb-4 border-b border-gray-200">
              <div>
                <h3 className="font-semibold text-gray-900">Enforce Domain Restriction</h3>
                <p className="text-sm text-gray-600 mt-1">
                  Only allow users from specific email domains to login via SSO
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={enforceDomain}
                  onChange={(e) => setEnforceDomain(e.target.checked)}
                  className="sr-only peer"
                  disabled={!ssoEnabled}
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>

            {/* Allowed Domains */}
            <div>
              <label className="block font-semibold text-gray-900 mb-2">
                Allowed Email Domains
              </label>
              <input
                type="text"
                value={domains}
                onChange={(e) => setDomains(e.target.value)}
                placeholder="e.g., company.com, example.com"
                disabled={!ssoEnabled || !enforceDomain}
                className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm disabled:bg-gray-100 disabled:text-gray-500"
              />
              <p className="text-sm text-gray-600 mt-2">
                Enter comma-separated domain names. Users with emails from these domains will be
                allowed to login via SSO.
              </p>
              {enforceDomain && (!domains || domains.trim() === "") && (
                <p className="text-sm text-yellow-600 mt-2">
                  ⚠️ Warning: Domain enforcement is enabled but no domains are specified. No users
                  will be able to login via SSO.
                </p>
              )}
            </div>
          </div>

          {/* Save Button */}
          <div className="mt-6 flex items-center justify-between">
            <div>
              {error && (
                <div className="text-red-600 text-sm">{error}</div>
              )}
              {success && (
                <div className="text-green-600 text-sm flex items-center gap-2">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  {success}
                </div>
              )}
            </div>
            <button
              onClick={handleSave}
              disabled={saving || !settings?.google_oauth_configured}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {saving ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </div>

        {/* Info Section */}
        <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h3 className="font-semibold text-blue-900 mb-2">How to use Google SSO</h3>
          <ol className="text-sm text-blue-800 space-y-1 list-decimal list-inside">
            <li>Enable Google SSO above</li>
            <li>Optionally configure allowed email domains</li>
            <li>Share your Team ID with users who should have access</li>
            <li>Users can login at /login by clicking "Continue with Google"</li>
            <li>Users enter the Team ID and authenticate with Google</li>
            <li>If their email domain is allowed, they'll be logged in automatically</li>
          </ol>
          <div className="mt-4 bg-white border border-blue-300 rounded px-3 py-2">
            <div className="text-xs text-blue-700 font-medium mb-1">Your Team ID:</div>
            <div className="font-mono text-sm text-blue-900">{settings?.team_id}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
