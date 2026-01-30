"use client";

/**
 * Enterprise Forecast Page
 * Cost predictions and capacity planning
 */

import { useState } from "react";
import {
  TrendingUp,
  AlertTriangle,
  DollarSign,
  Calendar,
  Target,
  Sparkles,
  Download,
  Settings as SettingsIcon,
} from "lucide-react";
import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import { PageHeader } from "@/components/ui/PageHeader";
import { KPI, KPIGrid } from "@/components/ui/KPI";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";

// Existing components
import ForecastCard from "@/components/ForecastCard";
import CapacityRiskCard from "@/components/CapacityRiskCard";

function ForecastContent() {
  const { showSuccess, showInfo } = useToast();
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [forecastDays, setForecastDays] = useState(7);

  const handleExport = () => {
    showSuccess("Forecast exported", "Your forecast data has been downloaded as CSV");
  };

  const handleSaveSettings = () => {
    showInfo("Settings saved", `Forecast period updated to ${forecastDays} days`);
    setShowSettingsModal(false);
  };

  return (
    <>
      {/* Page Header */}
      <PageHeader
        title="Cost Forecasting"
        description="AI-powered predictions and capacity planning for your GPU infrastructure"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Forecasting" },
        ]}
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              icon={<SettingsIcon className="w-4 h-4" />}
              onClick={() => setShowSettingsModal(true)}
            >
              Settings
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={<Download className="w-4 h-4" />}
              onClick={handleExport}
            >
              Export
            </Button>
          </>
        }
      />

      {/* KPIs */}
      <KPIGrid columns={4} className="mb-8">
        <KPI
          label="7-Day Forecast"
          value="$52,180"
          change={8.2}
          changeLabel="vs current trend"
          icon={<TrendingUp className="w-5 h-5" />}
          trend="up"
        />
        <KPI
          label="Confidence"
          value="94%"
          changeLabel="high accuracy"
          icon={<Target className="w-5 h-5" />}
        />
        <KPI
          label="Capacity Risk"
          value="Medium"
          changeLabel="3 alerts detected"
          icon={<AlertTriangle className="w-5 h-5" />}
        />
        <KPI
          label="Potential Savings"
          value="$4,200"
          change={-12.5}
          changeLabel="with optimization"
          icon={<DollarSign className="w-5 h-5" />}
          trend="down"
        />
      </KPIGrid>

      {/* Forecast Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Main Forecast - 2/3 width */}
        <div className="lg:col-span-2">
          <ForecastCard />
        </div>

        {/* Capacity Risk - 1/3 width */}
        <div>
          <CapacityRiskCard />
        </div>
      </div>

      {/* Insights & Recommendations */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between">
              <div>
                <CardTitle>Key Insights</CardTitle>
                <CardDescription>AI-generated forecast analysis</CardDescription>
              </div>
              <Badge variant="brand" size="sm">
                <Sparkles className="w-3 h-3 mr-1" />
                AI
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <InsightItem
                type="warning"
                title="Peak demand expected"
                description="Thursday shows 40% increase in predicted GPU usage"
              />
              <InsightItem
                type="success"
                title="Weekend optimization opportunity"
                description="Idle capacity could save $1,200 with auto-scaling"
              />
              <InsightItem
                type="info"
                title="Training workloads increasing"
                description="ML Research team forecast to grow 15% next week"
              />
              <InsightItem
                type="danger"
                title="Budget threshold approaching"
                description="Monthly spend may exceed budget by 8% if trend continues"
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recommendations</CardTitle>
            <CardDescription>Actions to optimize costs</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <RecommendationItem
                priority="high"
                title="Enable auto-scaling"
                savings="$1,200/week"
                description="Automatically scale down during low usage periods"
              />
              <RecommendationItem
                priority="medium"
                title="Switch to spot instances"
                savings="$800/week"
                description="Use spot for training workloads with checkpointing"
              />
              <RecommendationItem
                priority="low"
                title="Optimize cache hit rate"
                savings="$300/week"
                description="Tune LLM proxy cache settings for better efficiency"
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Forecast Timeline */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle>Forecast Timeline</CardTitle>
              <CardDescription>Day-by-day breakdown for the next {forecastDays} days</CardDescription>
            </div>
            <Badge variant="default" size="sm">
              <Calendar className="w-3 h-3 mr-1" />
              {forecastDays} days
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-border">
                <tr>
                  <th className="text-left py-3 px-4 text-sm font-semibold text-foreground">Day</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-foreground">Predicted Cost</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-foreground">GPU Hours</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-foreground">Confidence</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-foreground">Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {Array.from({ length: forecastDays }, (_, i) => {
                  const date = new Date();
                  date.setDate(date.getDate() + i + 1);
                  return (
                    <tr key={i} className="hover:bg-muted/50">
                      <td className="py-3 px-4 text-sm text-foreground">
                        {date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}
                      </td>
                      <td className="text-right py-3 px-4 text-sm font-semibold text-foreground">
                        ${(7000 + Math.random() * 2000).toFixed(0)}
                      </td>
                      <td className="text-right py-3 px-4 text-sm text-muted-foreground">
                        {(400 + Math.random() * 100).toFixed(0)}
                      </td>
                      <td className="text-right py-3 px-4 text-sm text-muted-foreground">
                        {(90 + Math.random() * 8).toFixed(0)}%
                      </td>
                      <td className="text-right py-3 px-4">
                        <Badge
                          variant={i % 4 === 0 ? "warning" : "success"}
                          size="sm"
                        >
                          {i % 4 === 0 ? "Medium" : "Low"}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Settings Modal */}
      <Modal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        title="Forecast Settings"
        description="Configure forecast parameters"
        footer={
          <>
            <Button variant="outline" onClick={() => setShowSettingsModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleSaveSettings}>
              Save Settings
            </Button>
          </>
        }
      >
        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Forecast Period (days)
            </label>
            <input
              type="number"
              value={forecastDays}
              onChange={(e) => setForecastDays(parseInt(e.target.value))}
              min="1"
              max="30"
              className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            <p className="text-sm text-muted-foreground mt-1">
              Number of days to forecast (1-30)
            </p>
          </div>

          <div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="rounded border-border"
                defaultChecked
              />
              <span className="text-sm text-foreground">
                Enable AI-powered insights
              </span>
            </label>
          </div>

          <div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="rounded border-border"
                defaultChecked
              />
              <span className="text-sm text-foreground">
                Include capacity risk analysis
              </span>
            </label>
          </div>
        </div>
      </Modal>
    </>
  );
}

function InsightItem({
  type,
  title,
  description,
}: {
  type: "success" | "warning" | "info" | "danger";
  title: string;
  description: string;
}) {
  const config = {
    success: { color: "text-success-600", bg: "bg-success-50 dark:bg-success-500/10" },
    warning: { color: "text-warning-600", bg: "bg-warning-50 dark:bg-warning-500/10" },
    info: { color: "text-info-600", bg: "bg-info-50 dark:bg-info-500/10" },
    danger: { color: "text-danger-600", bg: "bg-danger-50 dark:bg-danger-500/10" },
  };

  return (
    <div className={`flex items-start gap-3 p-3 rounded-lg ${config[type].bg}`}>
      <div className={`w-2 h-2 rounded-full mt-1.5 ${config[type].color}`} style={{ backgroundColor: 'currentColor' }} />
      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
    </div>
  );
}

function RecommendationItem({
  priority,
  title,
  savings,
  description,
}: {
  priority: "high" | "medium" | "low";
  title: string;
  savings: string;
  description: string;
}) {
  const priorityColors = {
    high: "danger",
    medium: "warning",
    low: "info",
  } as const;

  return (
    <div className="flex items-start gap-3 p-3 rounded-lg border border-border hover:bg-muted/50 transition-colors">
      <Badge variant={priorityColors[priority]} size="sm">
        {priority}
      </Badge>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <p className="font-medium text-sm text-foreground">{title}</p>
          <span className="text-sm font-semibold text-success-600">{savings}</span>
        </div>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}

export default function ForecastPage() {
  return (
    <EnterpriseLayout teamName="Demo Team">
      <ForecastContent />
    </EnterpriseLayout>
  );
}
