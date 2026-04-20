"use client";

/**
 * Enterprise Integrations Page
 * Cloud provider integrations management
 */

import { useState, useEffect } from "react";
import {
  Plus,
  RefreshCw,
  Trash2,
  CheckCircle,
  XCircle,
  AlertCircle,
  ExternalLink,
  Settings as SettingsIcon,
  Cloud,
} from "lucide-react";
import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { fetchJson } from "@/lib/api";
import { isDemoMode } from "@/lib/demoData";

// Existing forms
import AWSIntegrationForm from "@/components/AWSIntegrationForm";
import AzureIntegrationForm from "@/components/AzureIntegrationForm";
import GCPIntegrationForm from "@/components/GCPIntegrationForm";

interface AvailableIntegration {
  provider: string;
  display_name: string;
  description: string;
  enabled: boolean;
  config_schema: any;
}

interface IntegrationConnection {
  id: string;
  team_id: string;
  provider: string;
  name: string;
  description?: string;
  config: Record<string, any>;
  status: string;
  last_error?: string;
  last_sync_at?: string;
  last_successful_sync_at?: string;
  auto_sync_enabled: boolean;
  sync_interval_minutes: number;
  created_at: string;
  updated_at: string;
}

function IntegrationsContent() {
  const [available, setAvailable] = useState<AvailableIntegration[]>([]);
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<Record<string, boolean>>({});
  const [showAWSForm, setShowAWSForm] = useState(false);
  const [showAzureForm, setShowAzureForm] = useState(false);
  const [showGCPForm, setShowGCPForm] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const { showSuccess, showError, showInfo } = useToast();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [availableData, connectionsResponse] = await Promise.all([
        fetchJson<AvailableIntegration[]>("/api/v1/integrations/available"),
        fetchJson<{ connections?: IntegrationConnection[]; total?: number }>("/api/v1/integrations"),
      ]);
      setAvailable(availableData);
      setConnections(connectionsResponse?.connections ?? []);
    } catch (err: any) {
      console.error("Failed to load integrations:", err);
      if (!isDemoMode()) showError("Failed to load", err.message || "Could not load integrations");
      // Set mock data for demo
      setAvailable([
        {
          provider: "aws_cost_explorer",
          display_name: "AWS Cost Explorer",
          description: "Import costs from AWS Cost Explorer API",
          enabled: true,
          config_schema: {},
        },
        {
          provider: "gcp_billing_bigquery",
          display_name: "GCP BigQuery",
          description: "Import costs from GCP BigQuery billing export",
          enabled: true,
          config_schema: {},
        },
      ]);
      setConnections([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleSync(connectionId: string) {
    setSyncing((prev) => ({ ...prev, [connectionId]: true }));
    showInfo("Sync started", "Integration sync is now running...");
    
    try {
      await fetchJson(`/api/v1/integrations/${connectionId}/sync`, {
        method: "POST",
      });
      showSuccess("Sync complete", "Integration data has been updated");
      await loadData();
    } catch (err: any) {
      showError("Sync failed", err.message || "Could not sync integration");
    } finally {
      setSyncing((prev) => ({ ...prev, [connectionId]: false }));
    }
  }

  async function handleDelete(connectionId: string) {
    try {
      await fetchJson(`/api/v1/integrations/${connectionId}`, {
        method: "DELETE",
      });
      showSuccess("Integration removed", "The integration has been deleted");
      await loadData();
    } catch (err: any) {
      showError("Delete failed", err.message || "Could not delete integration");
    } finally {
      setDeleteConfirm(null);
    }
  }

  return (
    <>
      {/* Page Header */}
      <PageHeader
        title="Integrations"
        description="Connect cloud providers to automatically import cost data"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Settings", href: "/settings" },
          { label: "Integrations" },
        ]}
      />

      {/* Available Integrations */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Available Integrations</CardTitle>
          <CardDescription>Connect to cloud providers and data sources</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {available.map((integration) => (
              <IntegrationCard
                key={integration.provider}
                integration={integration}
                isConnected={connections.some((c) => c.provider === integration.provider)}
                onConnect={() => {
                  if (integration.provider === "aws" || integration.provider === "aws_cost_explorer") {
                    setShowAWSForm(true);
                  } else if (integration.provider === "azure") {
                    setShowAzureForm(true);
                  } else if (integration.provider === "gcp_billing_bigquery") {
                    setShowGCPForm(true);
                  } else {
                    showInfo("Coming soon", "This integration is not yet available");
                  }
                }}
              />
            ))}

            <IntegrationCard
              integration={{
                provider: "kubernetes",
                display_name: "Kubernetes",
                description: "Monitor GPU usage from Kubernetes clusters",
                enabled: false,
                config_schema: {},
              }}
              isConnected={false}
              comingSoon
            />
            <IntegrationCard
              integration={{
                provider: "datadog",
                display_name: "Datadog",
                description: "Import metrics from Datadog monitoring",
                enabled: false,
                config_schema: {},
              }}
              isConnected={false}
              comingSoon
            />
          </div>
        </CardContent>
      </Card>

      {/* Active Connections */}
      <Card>
        <CardHeader>
          <CardTitle>Active Connections</CardTitle>
          <CardDescription>
            {connections.length} integration{connections.length !== 1 ? "s" : ""} configured
          </CardDescription>
        </CardHeader>
        <CardContent>
          {connections.length === 0 ? (
            <div className="text-center py-12">
              <Cloud className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-foreground mb-2">
                No integrations yet
              </h3>
              <p className="text-sm text-muted-foreground mb-6">
                Connect a cloud provider to start importing cost data
              </p>
              <Button variant="primary" icon={<Plus className="w-4 h-4" />}>
                Add Integration
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {connections.map((connection) => (
                <ConnectionCard
                  key={connection.id}
                  connection={connection}
                  onSync={() => handleSync(connection.id)}
                  onDelete={() => setDeleteConfirm(connection.id)}
                  syncing={syncing[connection.id]}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* AWS Form Modal */}
      <Modal
        isOpen={showAWSForm}
        onClose={() => setShowAWSForm(false)}
        title="Connect AWS Cost Explorer"
        description="Import your AWS billing data"
        size="lg"
      >
        <AWSIntegrationForm
          onSuccess={() => {
            setShowAWSForm(false);
            loadData();
            showSuccess("AWS connected", "Your AWS integration is now active");
          }}
          onCancel={() => setShowAWSForm(false)}
        />
      </Modal>

      {/* Azure Form Modal */}
      <Modal
        isOpen={showAzureForm}
        onClose={() => setShowAzureForm(false)}
        title="Connect Azure Cost Management"
        description="Import your Azure billing data"
        size="lg"
      >
        <AzureIntegrationForm
          onSuccess={() => {
            setShowAzureForm(false);
            loadData();
            showSuccess("Azure connected", "Your Azure integration is now active");
          }}
          onCancel={() => setShowAzureForm(false)}
        />
      </Modal>

      {/* GCP Form Modal */}
      <Modal
        isOpen={showGCPForm}
        onClose={() => setShowGCPForm(false)}
        title="Connect GCP BigQuery"
        description="Import your GCP billing data"
        size="lg"
      >
        <GCPIntegrationForm
          onSuccess={() => {
            setShowGCPForm(false);
            loadData();
            showSuccess("GCP connected", "Your GCP integration is now active");
          }}
          onCancel={() => setShowGCPForm(false)}
        />
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={deleteConfirm !== null}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={() => deleteConfirm && handleDelete(deleteConfirm)}
        title="Remove Integration"
        message="Are you sure you want to remove this integration? Historical data will be preserved, but new data will no longer be imported."
        confirmText="Remove"
        variant="danger"
      />
    </>
  );
}

function IntegrationCard({
  integration,
  isConnected,
  onConnect,
  comingSoon = false,
}: {
  integration: AvailableIntegration;
  isConnected: boolean;
  onConnect?: () => void;
  comingSoon?: boolean;
}) {
  const providerLogos: Record<string, string> = {
    aws: "☁️",
    aws_cost_explorer: "☁️",
    gcp_billing_bigquery: "🌐",
    azure: "🔷",
    azure_cost_management: "🔷",
    kubernetes: "☸️",
    datadog: "🐕",
  };

  return (
    <Card
      variant={isConnected ? "elevated" : "default"}
      className={`${isConnected ? "ring-2 ring-brand-500" : ""}`}
    >
      <CardContent className="p-6">
        <div className="flex items-start justify-between mb-4">
          <div className="text-3xl">
            {providerLogos[integration.provider as keyof typeof providerLogos] || "🔌"}
          </div>
          {isConnected ? (
            <Badge variant="success" size="sm">
              <CheckCircle className="w-3 h-3 mr-1" />
              Connected
            </Badge>
          ) : comingSoon ? (
            <Badge variant="default" size="sm">
              Coming Soon
            </Badge>
          ) : (
            <Badge variant="default" size="sm">
              Available
            </Badge>
          )}
        </div>

        <h3 className="font-semibold text-foreground mb-2">
          {integration.display_name}
        </h3>
        <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
          {integration.description}
        </p>

        {!isConnected && !comingSoon && (
          <Button
            variant="outline"
            size="sm"
            fullWidth
            onClick={onConnect}
            icon={<Plus className="w-4 h-4" />}
          >
            Connect
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function ConnectionCard({
  connection,
  onSync,
  onDelete,
  syncing,
}: {
  connection: IntegrationConnection;
  onSync: () => void;
  onDelete: () => void;
  syncing?: boolean;
}) {
  const statusConfig = {
    active: { icon: CheckCircle, color: "success", text: "Active" },
    error: { icon: XCircle, color: "danger", text: "Error" },
    syncing: { icon: RefreshCw, color: "info", text: "Syncing" },
  } as const;

  const status = syncing ? "syncing" : connection.status === "active" ? "active" : "error";
  const { icon: StatusIcon, color, text } = statusConfig[status];

  return (
    <div className="flex items-start gap-4 p-4 rounded-lg border border-border hover:bg-muted/50 transition-colors">
      <div className="p-3 rounded-lg bg-brand-50 dark:bg-brand-500/10">
        <Cloud className="w-6 h-6 text-brand-600 dark:text-brand-400" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between mb-2">
          <div>
            <h4 className="font-semibold text-foreground">{connection.name}</h4>
            {connection.description && (
              <p className="text-sm text-muted-foreground mt-0.5">
                {connection.description}
              </p>
            )}
          </div>
          <Badge variant={color as any} size="sm">
            <StatusIcon className="w-3 h-3 mr-1" />
            {text}
          </Badge>
        </div>

        <div className="flex items-center gap-4 text-xs text-muted-foreground mb-3">
          {connection.last_successful_sync_at ? (
            <span>
              Last synced: {new Date(connection.last_successful_sync_at).toLocaleString()}
            </span>
          ) : (
            <span>Never synced</span>
          )}
          {connection.auto_sync_enabled && (
            <span className="flex items-center gap-1">
              <RefreshCw className="w-3 h-3" />
              Auto-sync every {connection.sync_interval_minutes} min
            </span>
          )}
        </div>

        {connection.last_error && (
          <div className="flex items-start gap-2 p-2 rounded bg-danger-50 dark:bg-danger-500/10 mb-3">
            <AlertCircle className="w-4 h-4 text-danger-600 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-danger-900 dark:text-danger-100">
              {connection.last_error}
            </p>
          </div>
        )}

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onSync}
            loading={syncing}
            icon={<RefreshCw className="w-4 h-4" />}
          >
            Sync Now
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<SettingsIcon className="w-4 h-4" />}
          >
            Configure
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onDelete}
            icon={<Trash2 className="w-4 h-4" />}
          >
            Remove
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function IntegrationsPage() {
  return (
    <EnterpriseLayout teamName="Demo Team">
      <IntegrationsContent />
    </EnterpriseLayout>
  );
}
