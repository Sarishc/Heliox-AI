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
    <div className="space-y-6">
      {/* Executive KPI Strip - Always at Top */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-enterprise-h2 text-heliox-text">
            Executive Overview
          </h2>
          <Button
            variant="outline"
            size="sm"
            icon={<RefreshCw className="w-4 h-4" />}
            onClick={loadDashboardData}
          >
            Refresh
          </Button>
        </div>
        <ExecutiveKPIStrip kpis={executiveKPIs} />
      </div>

      {/* Cost Trends Section */}
      <div className="grid-enterprise">
        <div className="section-header">Cost Trends & Forecasting</div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Spend Trend - 2/3 */}
          <div className="lg:col-span-2">
            <Card className="h-full">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-enterprise-h3">Daily GPU Spend</CardTitle>
                    <CardDescription className="text-enterprise-small">
                      30-day trend with 7-day forecast
                    </CardDescription>
                  </div>
                  <Badge variant="success" size="sm">
                    Live
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <SpendTrendChart startDate={startDate} endDate={endDate} />
              </CardContent>
            </Card>
          </div>

          {/* Forecast - 1/3 */}
          <div>
            <ForecastCard />
          </div>
        </div>
      </div>

      {/* Cost Breakdown Charts */}
      <div className="grid-enterprise">
        <div className="section-header">Cost Breakdown</div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-enterprise-h3">By GPU Model</CardTitle>
              <CardDescription className="text-enterprise-small">
                Utilization and spend distribution
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              <CostByModelChart startDate={startDate} endDate={endDate} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-enterprise-h3">By Team</CardTitle>
              <CardDescription className="text-enterprise-small">
                Team-level cost allocation
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              <CostByTeamChart startDate={startDate} endDate={endDate} />
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Enterprise Tables Section */}
      {isDemo && (
        <>
          {/* Top Teams Table */}
          <div className="grid-enterprise">
            <div className="section-header">Top Teams by GPU Spend</div>
            <EnterpriseTable
              data={topTeams}
              columns={teamColumns}
              searchPlaceholder="Search teams..."
              pageSize={5}
              dense
            />
          </div>

          {/* Top Models Table */}
          <div className="grid-enterprise">
            <div className="section-header">Top GPU Models by Cost</div>
            <EnterpriseTable
              data={topModels}
              columns={modelColumns}
              searchPlaceholder="Search models..."
              pageSize={5}
              dense
            />
          </div>

          {/* Idle Jobs / Optimization Insights */}
          <div className="grid-enterprise">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="section-header mb-1">Optimization Opportunities</div>
                <p className="text-enterprise-small text-heliox-text-muted">
                  Idle GPU jobs wasting resources
                </p>
              </div>
              <Badge variant="warning" size="sm">
                <Clock className="w-3 h-3 mr-1" />
                {idleJobs.length} Issues
              </Badge>
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

      {/* Call to Action if NOT in demo mode */}
      {!isDemo && (
        <Card className="border-2 border-dashed border-heliox-border">
          <CardContent className="py-12 text-center">
            <AlertTriangle className="w-12 h-12 text-heliox-text-muted mx-auto mb-4" />
            <h3 className="text-enterprise-h2 text-heliox-text mb-2">
              Enable Demo Mode for Full Experience
            </h3>
            <p className="text-enterprise-body text-heliox-text-secondary max-w-md mx-auto mb-6">
              See realistic enterprise-scale data with $2.4M monthly spend, 847 GPUs, and detailed
              team/model breakdowns. Perfect for presentations and demos.
            </p>
            <Button
              variant="primary"
              onClick={() => {
                localStorage.setItem("heliox_demo_mode", "true");
                window.location.reload();
              }}
            >
              Enable Demo Mode
            </Button>
          </CardContent>
        </Card>
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
