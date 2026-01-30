"use client";

/**
 * Enterprise Dashboard - Main Overview
 * Premium analytics dashboard with modern design
 */

import { useEffect, useState } from "react";
import {
  DollarSign,
  TrendingUp,
  Zap,
  Users,
  AlertCircle,
  Plus,
  Download,
} from "lucide-react";
import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import { PageHeader } from "@/components/ui/PageHeader";
import { KPI, KPIGrid } from "@/components/ui/KPI";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";

// Reuse existing chart components
import SpendTrendChart from "@/components/SpendTrendChart";
import CostByModelChart from "@/components/CostByModelChart";
import CostByTeamChart from "@/components/CostByTeamChart";
import ForecastCard from "@/components/ForecastCard";
import BudgetStatusCard from "@/components/BudgetStatusCard";
import CostEfficiencyCard from "@/components/CostEfficiencyCard";

interface DashboardData {
  totalSpend: number;
  totalSpendChange: number;
  efficiency: number;
  efficiencyChange: number;
  activeGPUs: number;
  activeGPUsChange: number;
  anomalies: number;
}

function DashboardContent() {
  const { startDate, endDate } = useDashboardFilters();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardData();
  }, [startDate, endDate]);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      // Mock data - replace with actual API calls
      await new Promise(resolve => setTimeout(resolve, 500));
      
      setData({
        totalSpend: 47234.56,
        totalSpendChange: 12.5,
        efficiency: 87.3,
        efficiencyChange: -3.2,
        activeGPUs: 142,
        activeGPUsChange: 8.7,
        anomalies: 3,
      });
    } catch (error) {
      console.error("Failed to load dashboard data:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Page Header */}
      <PageHeader
        title="GPU Cost Command Center"
        description="Real-time analytics, forecasting, and optimization insights for your GPU infrastructure"
        actions={
          <>
            <Button variant="outline" size="sm" icon={<Download className="w-4 h-4" />}>
              Export
            </Button>
            <Button variant="primary" size="sm" icon={<Plus className="w-4 h-4" />}>
              New Integration
            </Button>
          </>
        }
      />

      {/* KPIs */}
      <KPIGrid columns={4} className="mb-8">
        <KPI
          label="Total Spend (MTD)"
          value={loading ? "..." : `$${data?.totalSpend.toLocaleString()}`}
          change={data?.totalSpendChange}
          changeLabel="vs last month"
          icon={<DollarSign className="w-5 h-5" />}
          loading={loading}
        />
        <KPI
          label="Cost Efficiency"
          value={loading ? "..." : `${data?.efficiency}%`}
          change={data?.efficiencyChange}
          changeLabel="vs last month"
          icon={<Zap className="w-5 h-5" />}
          loading={loading}
        />
        <KPI
          label="Active GPUs"
          value={loading ? "..." : data?.activeGPUs}
          change={data?.activeGPUsChange}
          changeLabel="vs last month"
          icon={<Users className="w-5 h-5" />}
          loading={loading}
        />
        <KPI
          label="Cost Anomalies"
          value={loading ? "..." : data?.anomalies}
          changeLabel="detected this week"
          icon={<AlertCircle className="w-5 h-5" />}
          loading={loading}
        />
      </KPIGrid>

      {/* Status Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <BudgetStatusCard />
        <CostEfficiencyCard />
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {/* Spend Trend - 2/3 Width */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle>Daily Spend Trend</CardTitle>
                  <CardDescription>GPU costs over time with forecasts</CardDescription>
                </div>
                <Badge variant="success" size="sm">Live</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <SpendTrendChart startDate={startDate} endDate={endDate} />
            </CardContent>
          </Card>
        </div>

        {/* Forecast - 1/3 Width */}
        <div>
          <ForecastCard />
        </div>
      </div>

      {/* Cost Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Card>
          <CardHeader>
            <CardTitle>Cost by Model</CardTitle>
            <CardDescription>GPU model utilization and spend distribution</CardDescription>
          </CardHeader>
          <CardContent>
            <CostByModelChart startDate={startDate} endDate={endDate} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Cost by Team</CardTitle>
            <CardDescription>Team-level spend breakdown and trends</CardDescription>
          </CardHeader>
          <CardContent>
            <CostByTeamChart startDate={startDate} endDate={endDate} />
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card>
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
          <CardDescription>Common tasks and navigation shortcuts</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <QuickAction
              icon={<TrendingUp className="w-5 h-5" />}
              title="View Forecast"
              description="7-day cost projections"
              href="/forecast"
            />
            <QuickAction
              icon={<Zap className="w-5 h-5" />}
              title="Optimize Costs"
              description="Get recommendations"
              href="/optimization"
            />
            <QuickAction
              icon={<AlertCircle className="w-5 h-5" />}
              title="Set Budget Alert"
              description="Configure thresholds"
              href="/budgets"
            />
            <QuickAction
              icon={<Users className="w-5 h-5" />}
              title="Team Analytics"
              description="Detailed breakdowns"
              href="/analytics"
            />
          </div>
        </CardContent>
      </Card>
    </>
  );
}

export default function DashboardPage() {
  return (
    <EnterpriseLayout teamName="Demo Team">
      <DashboardContent />
    </EnterpriseLayout>
  );
}

function QuickAction({
  icon,
  title,
  description,
  href,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  href: string;
}) {
  return (
    <a
      href={href}
      className="
        flex items-start gap-3 p-4 rounded-lg 
        border border-border hover:border-brand-500 
        hover:bg-brand-50 dark:hover:bg-brand-500/5 
        transition-all duration-200 group
      "
    >
      <div className="
        p-2 rounded-lg bg-brand-50 dark:bg-brand-500/10 
        text-brand-600 dark:text-brand-400 
        group-hover:scale-110 transition-transform
      ">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <h4 className="font-medium text-sm text-foreground mb-0.5 group-hover:text-brand-600 dark:group-hover:text-brand-400">
          {title}
        </h4>
        <p className="text-xs text-muted-foreground line-clamp-1">{description}</p>
      </div>
    </a>
  );
}
