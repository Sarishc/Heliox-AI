"use client";

/**
 * Enterprise Analytics Page
 * Detailed cost breakdowns and insights
 */

import { useState } from "react";
import { 
  Download, 
  Filter, 
  TrendingUp, 
  DollarSign,
  Zap,
  Users,
  Calendar,
} from "lucide-react";
import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import { PageHeader } from "@/components/ui/PageHeader";
import { KPI, KPIGrid } from "@/components/ui/KPI";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Dropdown, DropdownItem, DropdownDivider, DropdownLabel } from "@/components/ui/Dropdown";
import { DataTable, Column } from "@/components/ui/DataTable";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";
import { useToast } from "@/components/ui/Toast";

// Existing chart components
import CostByModelChart from "@/components/CostByModelChart";
import CostByTeamChart from "@/components/CostByTeamChart";
import UtilizationHeatmap from "@/components/UtilizationHeatmap";

interface CostBreakdown {
  id: string;
  resource: string;
  provider: string;
  cost: number;
  usage: number;
  trend: number;
  team: string;
}

function AnalyticsContent() {
  const { startDate, endDate } = useDashboardFilters();
  const { showSuccess } = useToast();
  const [sortBy, setSortBy] = useState("spend");
  const [filterProvider, setFilterProvider] = useState("all");

  // Mock data for demonstration
  const mockData: CostBreakdown[] = [
    { id: "1", resource: "A100-80GB", provider: "AWS", cost: 12450, usage: 720, trend: 12.5, team: "ML Research" },
    { id: "2", resource: "V100-32GB", provider: "GCP", cost: 8900, usage: 480, trend: -5.2, team: "Training" },
    { id: "3", resource: "H100-80GB", provider: "AWS", cost: 15600, usage: 360, trend: 24.8, team: "ML Research" },
    { id: "4", resource: "A100-40GB", provider: "Azure", cost: 9200, usage: 600, trend: 8.1, team: "Inference" },
    { id: "5", resource: "T4", provider: "GCP", cost: 2100, usage: 1440, trend: -2.3, team: "Dev" },
  ];

  const tableColumns: Column<CostBreakdown>[] = [
    {
      key: "resource",
      label: "Resource",
      render: (item) => (
        <div>
          <div className="font-medium">{item.resource}</div>
          <div className="text-xs text-muted-foreground">{item.team}</div>
        </div>
      ),
    },
    {
      key: "provider",
      label: "Provider",
      render: (item) => <Badge variant="default" size="sm">{item.provider}</Badge>,
    },
    {
      key: "cost",
      label: "Cost",
      render: (item) => (
        <span className="font-semibold">${item.cost.toLocaleString()}</span>
      ),
    },
    {
      key: "usage",
      label: "Usage (hrs)",
      render: (item) => item.usage.toLocaleString(),
    },
    {
      key: "trend",
      label: "Trend",
      render: (item) => (
        <Badge
          variant={item.trend > 0 ? "danger" : "success"}
          size="sm"
        >
          {item.trend > 0 ? "+" : ""}{item.trend}%
        </Badge>
      ),
    },
  ];

  const handleExport = () => {
    showSuccess("Report exported", "Your analytics report has been downloaded");
  };

  return (
    <>
      {/* Page Header */}
      <PageHeader
        title="Cost Analytics"
        description="Detailed breakdowns, trends, and insights across your GPU infrastructure"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Analytics" },
        ]}
        actions={
          <>
            <Dropdown
              trigger={
                <Button variant="outline" size="sm" icon={<Filter className="w-4 h-4" />}>
                  Filters
                </Button>
              }
            >
              <DropdownLabel>Sort By</DropdownLabel>
              <DropdownItem onClick={() => setSortBy("spend")}>
                Highest Spend
              </DropdownItem>
              <DropdownItem onClick={() => setSortBy("usage")}>
                Most Usage
              </DropdownItem>
              <DropdownItem onClick={() => setSortBy("trend")}>
                Highest Trend
              </DropdownItem>
              <DropdownDivider />
              <DropdownLabel>Provider</DropdownLabel>
              <DropdownItem onClick={() => setFilterProvider("all")}>
                All Providers
              </DropdownItem>
              <DropdownItem onClick={() => setFilterProvider("aws")}>
                AWS
              </DropdownItem>
              <DropdownItem onClick={() => setFilterProvider("gcp")}>
                GCP
              </DropdownItem>
              <DropdownItem onClick={() => setFilterProvider("azure")}>
                Azure
              </DropdownItem>
            </Dropdown>
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
          label="Total Spend"
          value="$48,250"
          change={9.2}
          changeLabel="vs last period"
          icon={<DollarSign className="w-5 h-5" />}
        />
        <KPI
          label="Avg Cost/Hour"
          value="$18.50"
          change={-4.1}
          changeLabel="vs last period"
          icon={<Zap className="w-5 h-5" />}
        />
        <KPI
          label="Active Resources"
          value="156"
          change={12.3}
          changeLabel="vs last period"
          icon={<TrendingUp className="w-5 h-5" />}
        />
        <KPI
          label="Teams"
          value="8"
          changeLabel="total teams"
          icon={<Users className="w-5 h-5" />}
        />
      </KPIGrid>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <Card>
          <CardHeader>
            <CardTitle>Cost by Model</CardTitle>
            <CardDescription>GPU model spend distribution</CardDescription>
          </CardHeader>
          <CardContent>
            <CostByModelChart startDate={startDate} endDate={endDate} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Cost by Team</CardTitle>
            <CardDescription>Team-level cost allocation</CardDescription>
          </CardHeader>
          <CardContent>
            <CostByTeamChart startDate={startDate} endDate={endDate} />
          </CardContent>
        </Card>
      </div>

      {/* Utilization Heatmap */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Utilization Heatmap</CardTitle>
          <CardDescription>Hour-by-hour GPU utilization patterns</CardDescription>
        </CardHeader>
        <CardContent>
          <UtilizationHeatmap />
        </CardContent>
      </Card>

      {/* Detailed Breakdown Table */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle>Resource Breakdown</CardTitle>
              <CardDescription>Detailed cost analysis by resource</CardDescription>
            </div>
            <Badge variant="info" size="sm">
              <Calendar className="w-3 h-3 mr-1" />
              Last 30 days
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <DataTable
            data={mockData}
            columns={tableColumns}
            searchPlaceholder="Search resources..."
            pageSize={5}
          />
        </CardContent>
      </Card>
    </>
  );
}

export default function AnalyticsPage() {
  return (
    <EnterpriseLayout teamName="Demo Team">
      <AnalyticsContent />
    </EnterpriseLayout>
  );
}
