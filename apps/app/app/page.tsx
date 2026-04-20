"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Clock,
  RefreshCw,
  Plug,
  TrendingUp,
  Layers,
  Zap,
  ArrowRight,
} from "lucide-react";
import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import { ExecutiveKPIStrip } from "@/components/ui/ExecutiveKPIStrip";
import { EnterpriseTable, EnterpriseColumn } from "@/components/ui/EnterpriseTable";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";

import {
  isDemoMode,
  generateExecutiveKPIs,
  generateTopTeams,
  generateTopModels,
  generateIdleJobs,
} from "@/lib/demoData";

import SpendTrendChart from "@/components/SpendTrendChart";
import CostByModelChart from "@/components/CostByModelChart";
import CostByTeamChart from "@/components/CostByTeamChart";
import ForecastCard from "@/components/ForecastCard";

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

function SectionLabel({
  children,
  badge,
}: {
  children: React.ReactNode;
  badge?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span
          style={{
            fontSize: "11px",
            fontWeight: 700,
            textTransform: "uppercase" as const,
            letterSpacing: "0.08em",
            color: "var(--heliox-text-muted)",
          }}
        >
          {children}
        </span>
        <span
          style={{
            display: "block",
            height: "1px",
            width: "32px",
            background: "var(--border)",
          }}
        />
      </div>
      {badge}
    </div>
  );
}

function SampleBadge() {
  return (
    <div
      className="flex items-center gap-1.5 rounded-full px-2.5 py-1"
      style={{
        background: "rgba(245,158,11,0.08)",
        border: "1px solid rgba(245,158,11,0.2)",
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: "#f59e0b" }} />
      <span style={{ fontSize: "11px", fontWeight: 600, color: "#d97706" }}>
        Sample data
      </span>
    </div>
  );
}

function DashboardContent() {
  const { startDate, endDate } = useDashboardFilters();
  const [loading, setLoading] = useState(true);
  const isDemo = isDemoMode();

  const [executiveKPIs, setExecutiveKPIs] = useState<any[]>([]);
  const [topTeams, setTopTeams] = useState<TeamData[]>([]);
  const [topModels, setTopModels] = useState<ModelData[]>([]);
  const [idleJobs, setIdleJobs] = useState<IdleJobData[]>([]);
  // hasData tracks whether the real API returned any cost records
  const [hasData, setHasData] = useState<boolean | null>(null);

  useEffect(() => {
    loadDashboardData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startDate, endDate]);

  const loadDashboardData = async () => {
    setLoading(true);
    await new Promise((resolve) => setTimeout(resolve, 600));

    if (isDemo) {
      setExecutiveKPIs(generateExecutiveKPIs());
      setTopTeams(generateTopTeams());
      setTopModels(generateTopModels());
      setIdleJobs(generateIdleJobs());
      setHasData(true);
    } else {
      // Real user: fetch actual data from the API. No sample data fallback.
      try {
        const { fetchJson } = await import("@/lib/api");
        const [kpiData, teamsData, modelsData] = await Promise.allSettled([
          fetchJson<any[]>("/api/v1/costs/kpis"),
          fetchJson<TeamData[]>("/api/v1/costs/top-teams"),
          fetchJson<ModelData[]>("/api/v1/costs/top-models"),
        ]);

        const kpis = kpiData.status === "fulfilled" ? kpiData.value : [];
        const teams = teamsData.status === "fulfilled" ? teamsData.value : [];
        const models = modelsData.status === "fulfilled" ? modelsData.value : [];

        const dataExists = kpis.length > 0 || teams.length > 0 || models.length > 0;
        setHasData(dataExists);

        if (dataExists) {
          setExecutiveKPIs(kpis);
          setTopTeams(teams);
          setTopModels(models);
          setIdleJobs([]);
        }
      } catch {
        // API unavailable — treat as no data
        setHasData(false);
      }
    }

    setLoading(false);
  };

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
      width: "18%",
      render: (item) => (
        <div className="flex items-center justify-center gap-2">
          <div
            className="w-16 h-1.5 rounded-full overflow-hidden"
            style={{ background: "var(--muted)" }}
          >
            <div
              className="h-full rounded-full"
              style={{
                width: `${item.utilizationPercent}%`,
                background:
                  item.utilizationPercent > 85
                    ? "#ef4444"
                    : item.utilizationPercent > 60
                    ? "#f59e0b"
                    : "#6366f1",
              }}
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
      width: "12%",
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
          <div
            className="w-20 h-1.5 rounded-full overflow-hidden"
            style={{ background: "var(--muted)" }}
          >
            <div
              className="h-full rounded-full"
              style={{ width: `${item.utilizationPercent}%`, background: "#8b5cf6" }}
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

  // Non-demo user with no integrations / no data yet
  if (!isDemo && !loading && hasData === false) {
    return (
      <div className="space-y-8">
        <div
          className="flex items-end justify-between pb-4"
          style={{ borderBottom: "1px solid var(--border-muted)" }}
        >
          <div>
            <p
              className="mb-1"
              style={{
                fontSize: "11px",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                color: "var(--heliox-text-muted)",
              }}
            >
              Dashboard
            </p>
            <h1
              className="font-bold leading-none text-foreground"
              style={{ fontSize: "24px", letterSpacing: "-0.025em" }}
            >
              Executive Overview
            </h1>
          </div>
        </div>
        <div className="text-center py-16">
          <Plug
            className="w-12 h-12 mx-auto mb-4"
            style={{ color: "var(--heliox-text-muted)" }}
          />
          <h3 className="text-lg font-semibold text-slate-800 mb-2">No cost data yet</h3>
          <p className="text-slate-500 mb-6">
            Connect a cloud provider to start tracking your AI spending.
          </p>
          <Link
            href="/settings/integrations"
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
          >
            <ArrowRight className="w-4 h-4" />
            Connect cloud provider
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">

      {/* ── Page header ─────────────────────────────────── */}
      <div
        className="flex items-end justify-between pb-4"
        style={{ borderBottom: "1px solid var(--border-muted)" }}
      >
        <div>
          <p
            className="mb-1"
            style={{
              fontSize: "11px",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              color: "var(--heliox-text-muted)",
            }}
          >
            Dashboard
          </p>
          <h1
            className="font-bold leading-none text-foreground"
            style={{ fontSize: "24px", letterSpacing: "-0.025em" }}
          >
            Executive Overview
          </h1>
          <p className="mt-1.5" style={{ fontSize: "13px", color: "var(--heliox-text-muted)" }}>
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

      {/* ── KPI Strip ───────────────────────────────────── */}
      <ExecutiveKPIStrip kpis={executiveKPIs} />

      {/* ── Cost Trends & Forecasting ────────────────────── */}
      <div className="space-y-3">
        <SectionLabel
          badge={
            <span
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1"
              style={{ background: "rgba(16,185,129,0.08)", color: "#059669" }}
            >
              <span
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ background: "#10b981", animation: "pulse-glow 2s ease-in-out infinite" }}
              />
              <span style={{ fontSize: "11px", fontWeight: 600 }}>Live</span>
            </span>
          }
        >
          Cost Trends &amp; Forecasting
        </SectionLabel>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* Spend Trend — 2/3 */}
          <div className="lg:col-span-2">
            <Card className="h-full" variant="default">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-enterprise-h3">Daily GPU Spend</CardTitle>
                    <CardDescription className="text-enterprise-small">
                      30-day trend · actual spend per day
                    </CardDescription>
                  </div>
                  <TrendingUp className="h-4 w-4" style={{ color: "#6366f1", opacity: 0.6 }} />
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

      {/* ── Cost Breakdown ──────────────────────────────── */}
      <div className="space-y-3">
        <SectionLabel>Cost Breakdown</SectionLabel>

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
                  className="rounded-full px-2 py-0.5"
                  style={{
                    background: "rgba(99,102,241,0.08)",
                    color: "#6366f1",
                    fontSize: "10px",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                  }}
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
                  className="rounded-full px-2 py-0.5"
                  style={{
                    background: "rgba(99,102,241,0.08)",
                    color: "#6366f1",
                    fontSize: "10px",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                  }}
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

      {/* ── Top Teams ───────────────────────────────────── */}
      <div className="space-y-3">
        <SectionLabel badge={isDemo ? <SampleBadge /> : undefined}>
          Top Teams by GPU Spend
        </SectionLabel>
        <EnterpriseTable
          data={topTeams}
          columns={teamColumns}
          searchPlaceholder="Search teams…"
          pageSize={5}
          dense
        />
      </div>

      {/* ── Top Models ──────────────────────────────────── */}
      <div className="space-y-3">
        <SectionLabel badge={isDemo ? <SampleBadge /> : undefined}>
          Top GPU Models by Cost
        </SectionLabel>
        <EnterpriseTable
          data={topModels}
          columns={modelColumns}
          searchPlaceholder="Search models…"
          pageSize={5}
          dense
        />
      </div>

      {/* ── Optimization Opportunities ──────────────────── */}
      <div className="space-y-3">
        <SectionLabel
          badge={
            <span
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1"
              style={{ background: "rgba(245,158,11,0.08)", color: "#d97706" }}
            >
              <Clock className="w-3 h-3" />
              <span style={{ fontSize: "11px", fontWeight: 600 }}>
                {idleJobs.length} Issues
                {isDemo && " · Sample"}
              </span>
            </span>
          }
        >
          Optimization Opportunities
        </SectionLabel>
        <EnterpriseTable
          data={idleJobs}
          columns={idleJobColumns}
          searchPlaceholder="Search jobs…"
          pageSize={6}
          dense
          emptyMessage="No optimization opportunities found"
        />
      </div>

      {/* ── Connect data CTA (non-demo only) ────────────── */}
      {!isDemo && (
        <div
          className="rounded-2xl p-6"
          style={{
            background:
              "linear-gradient(135deg, rgba(99,102,241,0.04) 0%, rgba(139,92,246,0.04) 100%)",
            border: "1px solid rgba(99,102,241,0.12)",
          }}
        >
          <div className="flex flex-col items-start gap-6 sm:flex-row sm:items-center">
            <div
              className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl"
              style={{ background: "rgba(99,102,241,0.1)" }}
            >
              <Plug className="h-6 w-6" style={{ color: "#6366f1" }} />
            </div>
            <div className="flex-1">
              <h3
                className="mb-1"
                style={{ fontSize: "16px", fontWeight: 700, color: "var(--foreground)" }}
              >
                Connect your cloud data
              </h3>
              <p
                className="mb-4 max-w-lg"
                style={{
                  fontSize: "13px",
                  color: "var(--heliox-text-secondary)",
                  lineHeight: 1.6,
                }}
              >
                You&apos;re seeing sample data above. Connect AWS, GCP, or Azure to see real GPU
                costs, enable AI forecasting, and unlock optimization recommendations.
              </p>
              <div className="flex flex-wrap gap-3">
                <Button
                  variant="primary"
                  size="sm"
                  icon={<ArrowRight className="w-3.5 h-3.5" />}
                  onClick={() => (window.location.href = "/settings/integrations")}
                >
                  Connect cloud data
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  icon={<Zap className="w-3.5 h-3.5" />}
                  onClick={() => {
                    localStorage.setItem("heliox_demo_mode", "true");
                    window.location.reload();
                  }}
                >
                  Enable demo mode
                </Button>
              </div>
            </div>
            <div className="hidden xl:flex flex-col gap-2.5 shrink-0">
              {[
                { icon: <TrendingUp className="h-3.5 w-3.5" />, label: "AI cost forecasting" },
                { icon: <Layers className="h-3.5 w-3.5" />, label: "GPU utilization analysis" },
                { icon: <Zap className="h-3.5 w-3.5" />, label: "Optimization recommendations" },
              ].map(({ icon, label }) => (
                <div key={label} className="flex items-center gap-2">
                  <span style={{ color: "#6366f1" }}>{icon}</span>
                  <span style={{ fontSize: "12px", color: "var(--heliox-text-secondary)" }}>
                    {label}
                  </span>
                </div>
              ))}
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
