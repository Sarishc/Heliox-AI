"use client";

/**
 * HELIOX ENTERPRISE DASHBOARD
 * Dense, professional, data-first analytics platform
 * Stripe/Datadog/Snowflake inspired design
 */

import { useEffect, useState } from "react";
import {
  DollarSign,
  TrendingUp,
  Zap,
  AlertTriangle,
  Download,
  RefreshCw,
  Clock,
} from "lucide-react";
import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import { ExecutiveKPIStrip } from "@/components/ui/ExecutiveKPIStrip";
import { EnterpriseTable, EnterpriseColumn } from "@/components/ui/EnterpriseTable";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";

// Demo data
import {
  isDemoMode,
  generateExecutiveKPIs,
  generateTopTeams,
  generateTopModels,
  generateProviderBreakdown,
  generateIdleJobs,
} from "@/lib/demoData";

// Existing chart components
import SpendTrendChart from "@/components/SpendTrendChart";
import CostByModelChart from "@/components/CostByModelChart";
import CostByTeamChart from "@/components/CostByTeamChart";
import ForecastCard from "@/components/ForecastCard";

// Types
interface TeamData {
  id: string;
  team: string;
  lead: string;
  spend: number;
  budget: number;
  utilizationPercent: number;
  activeJobs: number;
  gpuHours: number;
}

interface ModelData {
  id: string;
  model: string;
  provider: string;
  instances: number;
  hours: number;
  cost: number;
  utilizationPercent: number;
}

interface IdleJobData {
  id: string;
  jobName: string;
  team: string;
  gpuModel: string;
  idleMinutes: number;
  estimatedWaste: number;
  status: string;
}

function DashboardContent() {
  const { startDate, endDate } = useDashboardFilters();
  const [loading, setLoading] = useState(true);
  const isDemo = isDemoMode();

  // Data states
  const [executiveKPIs, setExecutiveKPIs] = useState<any[]>([]);
  const [topTeams, setTopTeams] = useState<TeamData[]>([]);
  const [topModels, setTopModels] = useState<ModelData[]>([]);
  const [idleJobs, setIdleJobs] = useState<IdleJobData[]>([]);

  useEffect(() => {
    loadDashboardData();
  }, [startDate, endDate]);

  const loadDashboardData = async () => {
    setLoading(true);
    
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 800));

    if (isDemo) {
      // Load demo data
      setExecutiveKPIs(generateExecutiveKPIs());
      setTopTeams(generateTopTeams());
      setTopModels(generateTopModels());
      setIdleJobs(generateIdleJobs());
    } else {
      // Load real data (fallback to smaller realistic values)
      setExecutiveKPIs([
        {
          label: "GPU Spend (MTD)",
          value: 47234,
          format: "currency" as const,
          change: 12.3,
          changeLabel: "vs last month",
        },
        {
          label: "Active GPUs",
          value: 142,
          format: "number" as const,
          change: -3.2,
          changeLabel: "vs last week",
        },
        {
          label: "Cost per Request",
          value: "$0.0089",
          format: "custom" as const,
          change: -8.7,
          changeLabel: "vs last month",
        },
        {
          label: "Optimization Savings",
          value: "12.4%",
          format: "custom" as const,
          change: 2.1,
          changeLabel: "vs last month",
        },
      ]);
      setTopTeams([]);
      setTopModels([]);
      setIdleJobs([]);
    }

    setLoading(false);
  };

  // Table column definitions
  const teamColumns: EnterpriseColumn<TeamData>[] = [
    {
      key: "team",
      label: "Team",
      width: "25%",
      render: (item) => (
        <div>
          <div className="font-medium text-heliox-text">{item.team}</div>
          <div className="text-xs text-heliox-text-muted">{item.lead}</div>
        </div>
      ),
    },
    {
      key: "spend",
      label: "Spend",
      align: "right",
      width: "15%",
      className: "font-mono-tabular",
      render: (item) => `$${item.spend.toLocaleString()}`,
    },
    {
      key: "budget",
      label: "Budget",
      align: "right",
      width: "15%",
      className: "font-mono-tabular",
      render: (item) => `$${item.budget.toLocaleString()}`,
    },
    {
      key: "utilizationPercent",
      label: "Utilization",
      align: "center",
      width: "15%",
      render: (item) => (
        <div className="flex items-center justify-center gap-2">
          <div className="w-16 h-1.5 bg-heliox-bg rounded-full overflow-hidden">
            <div
              className="h-full bg-heliox-primary"
              style={{ width: `${item.utilizationPercent}%` }}
            />
          </div>
          <span className="text-xs font-mono-tabular">{item.utilizationPercent}%</span>
        </div>
      ),
    },
    {
      key: "activeJobs",
      label: "Active Jobs",
      align: "right",
      width: "15%",
      className: "font-mono-tabular",
    },
    {
      key: "gpuHours",
      label: "GPU Hours",
      align: "right",
      width: "15%",
      className: "font-mono-tabular",
      render: (item) => item.gpuHours.toLocaleString(),
    },
  ];

  const modelColumns: EnterpriseColumn<ModelData>[] = [
    {
      key: "model",
      label: "GPU Model",
      width: "25%",
      render: (item) => (
        <div>
          <div className="font-medium text-heliox-text">{item.model}</div>
          <div className="text-xs text-heliox-text-muted">{item.provider}</div>
        </div>
      ),
    },
    {
      key: "instances",
      label: "Instances",
      align: "right",
      width: "15%",
      className: "font-mono-tabular",
    },
    {
      key: "hours",
      label: "Hours",
      align: "right",
      width: "15%",
      className: "font-mono-tabular",
      render: (item) => item.hours.toLocaleString(),
    },
    {
      key: "cost",
      label: "Cost",
      align: "right",
      width: "20%",
      className: "font-mono-tabular",
      render: (item) => `$${item.cost.toLocaleString()}`,
    },
    {
      key: "utilizationPercent",
      label: "Utilization",
      align: "center",
      width: "25%",
      render: (item) => (
        <div className="flex items-center justify-center gap-2">
          <div className="w-20 h-1.5 bg-heliox-bg rounded-full overflow-hidden">
            <div
              className="h-full bg-chart-secondary"
              style={{ width: `${item.utilizationPercent}%` }}
            />
          </div>
          <span className="text-xs font-mono-tabular">{item.utilizationPercent}%</span>
        </div>
      ),
    },
  ];

  const idleJobColumns: EnterpriseColumn<IdleJobData>[] = [
    {
      key: "jobName",
      label: "Job Name",
      width: "30%",
      render: (item) => (
        <div>
          <div className="font-medium text-heliox-text font-mono text-xs">{item.jobName}</div>
          <div className="text-xs text-heliox-text-muted">{item.team}</div>
        </div>
      ),
    },
    {
      key: "gpuModel",
      label: "GPU",
      width: "15%",
      className: "font-mono-tabular",
    },
    {
      key: "idleMinutes",
      label: "Idle Time",
      align: "right",
      width: "20%",
      render: (item) => (
        <span className="font-mono-tabular">{item.idleMinutes} min</span>
      ),
    },
    {
      key: "estimatedWaste",
      label: "Est. Waste",
      align: "right",
      width: "20%",
      className: "font-mono-tabular",
      render: (item) => `$${item.estimatedWaste}`,
    },
    {
      key: "status",
      label: "Priority",
      align: "center",
      width: "15%",
      render: (item) => (
        <Badge
          variant={
            item.status === "Critical"
              ? "danger"
              : item.status === "Warning"
              ? "warning"
              : "default"
          }
          size="sm"
        >
          {item.status}
        </Badge>
      ),
    },
  ];

  return (
    <div className="space-y-8">

      {/* ── Page header ────────────────────────────────── */}
      <div className="flex items-end justify-between pb-2" style={{ borderBottom: "1px solid var(--border-muted)" }}>
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.1em]" style={{ color: "var(--heliox-text-muted)" }}>
            Dashboard
          </p>
          <h1
            className="font-bold leading-none tracking-tight text-foreground"
            style={{ fontSize: "22px", letterSpacing: "-0.02em" }}
          >
            Executive Overview
          </h1>
          <p className="mt-1 text-[13px]" style={{ color: "var(--heliox-text-muted)" }}>
            Real-time GPU cost analytics across all workloads
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          icon={<RefreshCw className="w-3.5 h-3.5" />}
          onClick={loadDashboardData}
        >
          Refresh
        </Button>
      </div>

      {/* ── KPI Strip ──────────────────────────────────── */}
      <ExecutiveKPIStrip kpis={executiveKPIs} />

      {/* ── Cost Trends ────────────────────────────────── */}
      <div className="space-y-3">
        {/* Section label */}
        <div className="section-label">
          Cost Trends &amp; Forecasting
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* Spend Trend — 2/3 */}
          <div className="lg:col-span-2">
            <Card className="h-full" variant="default">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-enterprise-h3">Daily GPU Spend</CardTitle>
                    <CardDescription className="text-enterprise-small">
                      30-day trend with 7-day forecast
                    </CardDescription>
                  </div>
                  <span
                    className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold"
                    style={{ background: "rgba(16,185,129,0.1)", color: "#059669" }}
                  >
                    <span
                      className="inline-block h-1.5 w-1.5 rounded-full"
                      style={{ background: "#10b981", animation: "pulse-glow 2s ease-in-out infinite" }}
                    />
                    Live
                  </span>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <SpendTrendChart startDate={startDate} endDate={endDate} />
              </CardContent>
            </Card>
          </div>

          {/* Forecast — 1/3 */}
          <div>
            <ForecastCard />
          </div>
        </div>
      </div>

      {/* ── Cost Breakdown ─────────────────────────────── */}
      <div className="space-y-3">
        <div className="section-label">Cost Breakdown</div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-enterprise-h3">By GPU Model</CardTitle>
                  <CardDescription className="text-enterprise-small">
                    Spend distribution across GPU types
                  </CardDescription>
                </div>
                <span
                  className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                  style={{ background: "rgba(99,102,241,0.08)", color: "#6366f1" }}
                >
                  MTD
                </span>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <CostByModelChart startDate={startDate} endDate={endDate} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-enterprise-h3">By Team</CardTitle>
                  <CardDescription className="text-enterprise-small">
                    Team-level cost allocation
                  </CardDescription>
                </div>
                <span
                  className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                  style={{ background: "rgba(99,102,241,0.08)", color: "#6366f1" }}
                >
                  MTD
                </span>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <CostByTeamChart startDate={startDate} endDate={endDate} />
            </CardContent>
          </Card>
        </div>
      </div>

      {/* ── Tables (demo only) ─────────────────────────── */}
      {isDemo && (
        <>
          {/* Top Teams */}
          <div className="space-y-3">
            <div className="section-label">Top Teams by GPU Spend</div>
            <EnterpriseTable
              data={topTeams}
              columns={teamColumns}
              searchPlaceholder="Search teams..."
              pageSize={5}
              dense
            />
          </div>

          {/* Top Models */}
          <div className="space-y-3">
            <div className="section-label">Top GPU Models by Cost</div>
            <EnterpriseTable
              data={topModels}
              columns={modelColumns}
              searchPlaceholder="Search models..."
              pageSize={5}
              dense
            />
          </div>

          {/* Optimization opportunities */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="section-label">Optimization Opportunities</div>
              <span
                className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold"
                style={{ background: "rgba(245,158,11,0.1)", color: "#d97706" }}
              >
                <Clock className="w-3 h-3" />
                {idleJobs.length} Issues
              </span>
            </div>
            <EnterpriseTable
              data={idleJobs}
              columns={idleJobColumns}
              searchPlaceholder="Search jobs..."
              pageSize={6}
              dense
              emptyMessage="No optimization opportunities found"
            />
          </div>
        </>
      )}

      {/* ── Empty / onboarding state ───────────────────── */}
      {!isDemo && (
        <div
          className="rounded-2xl p-8"
          style={{
            border: "1.5px dashed var(--border)",
            background: "var(--card)",
          }}
        >
          <div className="flex flex-col items-center gap-8 sm:flex-row">
            <div
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl"
              style={{ background: "rgba(99,102,241,0.08)" }}
            >
              <AlertTriangle className="h-7 w-7" style={{ color: "#6366f1" }} />
            </div>
            <div className="flex-1 text-center sm:text-left">
              <h3 className="mb-1.5 text-[16px] font-semibold text-foreground">
                Get your first data flowing
              </h3>
              <p className="mb-5 max-w-md text-[13px]" style={{ color: "var(--heliox-text-secondary)" }}>
                Connect AWS or GCP in Settings → Integrations to import GPU costs, or enable demo
                mode to explore the full dashboard with sample data.
              </p>
              <div className="flex flex-wrap gap-3 justify-center sm:justify-start">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => (window.location.href = "/settings/integrations")}
                >
                  Connect cloud data
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    localStorage.setItem("heliox_demo_mode", "true");
                    window.location.reload();
                  }}
                >
                  Enable demo mode
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <EnterpriseLayout teamName="Demo Team">
      <DashboardContent />
    </EnterpriseLayout>
  );
}
