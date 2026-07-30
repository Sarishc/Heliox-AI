"use client";

import { useState, useEffect } from "react";
import { fetchJson } from "@/lib/api";

interface SSOSettings {
  team_id: string;
  sso_enabled: boolean;
  sso_enforce_domain: boolean;
  allowed_email_domains: string[] | null;
  google_oauth_configured: boolean;
  saml_configured?: boolean;
}

interface SamlConfig {
  team_id: string;
  idp_entity_id: string;
  idp_sso_url: string;
  enabled: boolean;
  default_role: string;
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

  // SAML config state
  const [samlConfig, setSamlConfig] = useState<SamlConfig | null>(null);
  const [samlEntityId, setSamlEntityId] = useState("");
  const [samlSsoUrl, setSamlSsoUrl] = useState("");
  const [samlCert, setSamlCert] = useState("");
  const [samlEnabled, setSamlEnabled] = useState(true);
  const [samlDefaultRole, setSamlDefaultRole] = useState("viewer");
  const [samlSaving, setSamlSaving] = useState(false);

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
      // Only request the SAML record when settings confirm one exists.
      if (data.team_id && data.saml_configured) {
        try {
          const saml = await fetchJson<SamlConfig>("/api/v1/teams/sso/saml", {
            headers: { "X-Team-Id": data.team_id },
          });
          setSamlConfig(saml);
          setSamlEntityId(saml.idp_entity_id);
          setSamlSsoUrl(saml.idp_sso_url);
          setSamlEnabled(saml.enabled);
          setSamlDefaultRole(saml.default_role);
        } catch {
          setSamlConfig(null);
        }
      } else {
        setSamlConfig(null);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load SSO settings");
    } finally {
      setLoading(false);
    }
  }

  async function handleSamlSave() {
    if (!settings?.team_id) return;
    setSamlSaving(true);
    setError("");
    setSuccess("");
    try {
      await fetchJson("/api/v1/teams/sso/saml", {
        method: "PUT",
        headers: { "X-Team-Id": settings.team_id },
        body: JSON.stringify({
          idp_entity_id: samlEntityId.trim(),
          idp_sso_url: samlSsoUrl.trim(),
          idp_x509_cert: samlCert.trim(),
          enabled: samlEnabled,
          default_role: samlDefaultRole,
        }),
      });
      setSuccess("SAML configuration saved successfully!");
      setTimeout(() => setSuccess(""), 3000);
      await loadSettings();
    } catch (err: any) {
      setError(err.message || "Failed to save SAML config");
    } finally {
      setSamlSaving(false);
    }
  }

  async function handleSamlDelete() {
    if (!settings?.team_id || !confirm("Remove SAML configuration?")) return;
    setSamlSaving(true);
    setError("");
    try {
      await fetchJson("/api/v1/teams/sso/saml", {
        method: "DELETE",
        headers: { "X-Team-Id": settings.team_id },
      });
      setSuccess("SAML configuration removed.");
      setSamlConfig(null);
      setSamlEntityId("");
      setSamlSsoUrl("");
      setSamlCert("");
      await loadSettings();
    } catch (err: any) {
      setError(err.message || "Failed to remove SAML config");
    } finally {
      setSamlSaving(false);
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
        headers: settings?.team_id ? { "X-Team-Id": settings.team_id } : undefined,
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

        {/* SAML / Okta SSO */}
        <div className="mt-8 bg-white rounded-lg shadow border border-gray-200 p-6">
          <h2 className="text-xl font-bold mb-4">SAML / Okta SSO</h2>
          <p className="text-sm text-gray-600 mb-4">
            Configure Okta or another SAML 2.0 IdP for enterprise SSO. Users enter their Team ID on
            the login page and authenticate via your IdP.
          </p>
          {samlConfig && (
            <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
              SAML is configured. New users will be provisioned with role: {samlConfig.default_role}
            </div>
          )}
          <div className="space-y-4">
            <div>
              <label className="block font-medium text-gray-700 mb-1">IdP Entity ID</label>
              <input
                type="text"
                value={samlEntityId}
                onChange={(e) => setSamlEntityId(e.target.value)}
                placeholder="https://dev-123456.okta.com/saml2/sso"
                className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block font-medium text-gray-700 mb-1">IdP SSO URL</label>
              <input
                type="url"
                value={samlSsoUrl}
                onChange={(e) => setSamlSsoUrl(e.target.value)}
                placeholder="https://dev-123456.okta.com/saml2/sso"
                className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block font-medium text-gray-700 mb-1">IdP X.509 Certificate (PEM)</label>
              <textarea
                value={samlCert}
                onChange={(e) => setSamlCert(e.target.value)}
                placeholder="-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
                rows={6}
                className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm font-mono"
              />
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={samlEnabled}
                  onChange={(e) => setSamlEnabled(e.target.checked)}
                  className="rounded"
                />
                <span className="text-sm">Enable SAML login</span>
              </label>
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-600">Default role for new users:</span>
                <select
                  value={samlDefaultRole}
                  onChange={(e) => setSamlDefaultRole(e.target.value)}
                  className="border border-gray-300 rounded px-2 py-1 text-sm"
                >
                  <option value="viewer">Viewer</option>
                  <option value="admin">Admin</option>
                  <option value="owner">Owner</option>
                </select>
              </div>
            </div>
          </div>
          <div className="mt-4 flex gap-3">
            <button
              onClick={handleSamlSave}
              disabled={samlSaving || !samlEntityId.trim() || !samlSsoUrl.trim() || !samlCert.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {samlSaving ? "Saving..." : "Save SAML Config"}
            </button>
            {samlConfig && (
              <button
                onClick={handleSamlDelete}
                disabled={samlSaving}
                className="px-4 py-2 border border-red-300 text-red-700 rounded-lg text-sm hover:bg-red-50 disabled:opacity-50"
              >
                Remove SAML
              </button>
            )}
          </div>
          <div className="mt-4 p-3 bg-gray-50 rounded-lg text-xs text-gray-600">
            <strong>SP Metadata URL:</strong>{" "}
            {typeof window !== "undefined" && settings?.team_id
              ? `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}/api/v1/auth/saml/metadata?team_id=${settings.team_id}`
              : "—"}
          </div>
        </div>

        {/* Info Section */}
        <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h3 className="font-semibold text-blue-900 mb-2">How to use SSO</h3>
          <ol className="text-sm text-blue-800 space-y-1 list-decimal list-inside">
            <li>Enable Google SSO and/or configure SAML/Okta above</li>
            <li>Optionally configure allowed email domains</li>
            <li>Share your Team ID with users who should have access</li>
            <li>Users login at /login: enter Team ID, then "Continue with Google" or "Continue with Okta"</li>
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
