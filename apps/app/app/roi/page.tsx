"use client";

/**
 * ROI / Savings Dashboard
 * Shows business value and cost optimization impact for Heliox customers.
 * All savings are estimated potential—actual savings depend on implementation.
 */

import { useEffect, useState } from "react";
import {
  DollarSign,
  TrendingDown,
  AlertTriangle,
  BarChart3,
  Loader2,
  PiggyBank,
  Sparkles,
} from "lucide-react";
import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";
import { fetchJson } from "@/lib/api";
import { isDemoMode } from "@/lib/demoData";

const DEMO_ROI: ROIDashboardResponse = {
  start_date: "2026-02-20",
  end_date: "2026-03-22",
  total_spend_usd: 1_620_000,
  estimated_potential_savings_usd: 291_600,
  savings_percent_of_spend: 18.0,
  savings_by_category: [
    { type: "idle_gpu", label: "Idle GPU time", estimated_savings_usd: 142_800, count: 24 },
    { type: "rightsizing", label: "Instance rightsizing", estimated_savings_usd: 89_400, count: 11 },
    { type: "spot_migration", label: "Spot migration", estimated_savings_usd: 59_400, count: 7 },
  ],
  top_recommendations: [
    { title: "Terminate idle training-resnet-v2 job", type: "idle_gpu", estimated_savings_usd: 28_800, severity: "high" },
    { title: "Downsize inference cluster (A100→A10G)", type: "rightsizing", estimated_savings_usd: 41_200, severity: "medium" },
    { title: "Migrate batch workloads to spot", type: "spot_migration", estimated_savings_usd: 59_400, severity: "medium" },
  ],
  provider_breakdown: [
    { provider: "AWS", cost_usd: 832_000, share_percent: 51.4 },
    { provider: "GCP", cost_usd: 498_000, share_percent: 30.7 },
    { provider: "Azure", cost_usd: 290_000, share_percent: 17.9 },
  ],
  anomaly_count: 3,
  recommendation_count: 18,
  disclaimer: "Estimated savings based on 30-day usage patterns. Actual savings depend on workload characteristics and implementation.",
};

interface SavingsByCategory {
  type: string;
  label: string;
  estimated_savings_usd: number;
  count: number;
}

interface TopRecommendation {
  title: string;
  type: string;
  estimated_savings_usd: number;
  severity: string;
}

interface ProviderBreakdown {
  provider: string;
  cost_usd: number;
  share_percent: number;
}

interface ROIDashboardResponse {
  start_date: string;
  end_date: string;
  total_spend_usd: number;
  estimated_potential_savings_usd: number;
  savings_percent_of_spend: number;
  savings_by_category: SavingsByCategory[];
  top_recommendations: TopRecommendation[];
  provider_breakdown: ProviderBreakdown[];
  anomaly_count: number;
  recommendation_count: number;
  disclaimer: string;
}

function ROIContent() {
  const { startDate, endDate } = useDashboardFilters();
  const [data, setData] = useState<ROIDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      if (isDemoMode()) {
        setData(DEMO_ROI);
        setLoading(false);
        return;
      }
      try {
        const res = await fetchJson<ROIDashboardResponse>(
          `/api/v1/analytics/roi?start=${startDate}&end=${endDate}&include_anomalies=true`
        );
        setData(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load ROI data");
        setData(null);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [startDate, endDate]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-heliox-primary" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-6">
        <p className="text-sm text-amber-800">
          {error ?? "No ROI data available. Connect integrations and ingest cost data to see savings opportunities."}
        </p>
        <p className="mt-2 text-xs text-amber-700">
          Ensure your team has cost snapshots and usage data for the selected date range.
        </p>
      </div>
    );
  }

  const hasSavings = data.estimated_potential_savings_usd > 0;
  const hasSpend = data.total_spend_usd > 0;

  return (
    <>
      <PageHeader
        title="ROI & Savings"
        description="See how much Heliox can help you save. All figures are estimated potential savings."
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "ROI" },
        ]}
      />

      {/* Hero: Potential Savings */}
      <div className="mb-8 rounded-xl border border-heliox-border bg-gradient-to-br from-heliox-bg to-heliox-card p-6">
        <div className="flex items-center gap-2 text-heliox-text-muted">
          <PiggyBank className="h-5 w-5" />
          <span className="text-sm font-medium">Estimated potential savings this period</span>
        </div>
        <div className="mt-2 text-3xl font-bold text-heliox-text">
          {hasSavings ? (
            <>${data.estimated_potential_savings_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })}</>
          ) : (
            <span className="text-heliox-text-muted">—</span>
          )}
        </div>
        {hasSpend && hasSavings && (
          <p className="mt-1 text-sm text-heliox-text-muted">
            {data.savings_percent_of_spend.toFixed(1)}% of ${data.total_spend_usd.toLocaleString()} total spend
          </p>
        )}
        <p className="mt-3 text-xs text-heliox-text-secondary">{data.disclaimer}</p>
      </div>

      {/* KPI cards */}
      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-heliox-text-muted">
              Total Spend
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <DollarSign className="h-5 w-5 text-heliox-text-muted" />
              <span className="text-2xl font-semibold">
                ${data.total_spend_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </span>
            </div>
            <p className="mt-1 text-xs text-heliox-text-secondary">
              {data.start_date} – {data.end_date}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-heliox-text-muted">
              Potential Savings
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <TrendingDown className="h-5 w-5 text-success-500" />
              <span className="text-2xl font-semibold text-success-600">
                ${data.estimated_potential_savings_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </span>
            </div>
            <p className="mt-1 text-xs text-heliox-text-secondary">
              {data.recommendation_count} opportunity{data.recommendation_count !== 1 ? "s" : ""} identified
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-heliox-text-muted">
              Savings Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">
              {hasSpend ? `${data.savings_percent_of_spend.toFixed(1)}%` : "—"}
            </div>
            <p className="mt-1 text-xs text-heliox-text-secondary">
              Of total spend
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-heliox-text-muted">
              Anomalies
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              <span className="text-2xl font-semibold">{data.anomaly_count}</span>
            </div>
            <p className="mt-1 text-xs text-heliox-text-secondary">
              Spend/utilization signals
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Top waste categories */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Savings by category
            </CardTitle>
            <CardDescription>Estimated potential savings by opportunity type</CardDescription>
          </CardHeader>
          <CardContent>
            {data.savings_by_category.length === 0 ? (
              <p className="py-8 text-center text-sm text-heliox-text-muted">
                No categorized savings yet. Ingest cost and usage data to generate recommendations.
              </p>
            ) : (
              <div className="space-y-3">
                {data.savings_by_category.map((cat) => (
                  <div
                    key={cat.type}
                    className="flex items-center justify-between rounded-lg border border-heliox-border bg-heliox-bg px-4 py-3"
                  >
                    <div>
                      <p className="font-medium text-heliox-text">{cat.label}</p>
                      <p className="text-xs text-heliox-text-muted">
                        {cat.count} opportunity{cat.count !== 1 ? "s" : ""}
                      </p>
                    </div>
                    <span className="font-semibold text-success-600">
                      ${cat.estimated_savings_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top recommendations */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4" />
              Top opportunities
            </CardTitle>
            <CardDescription>Highest-value recommendations</CardDescription>
          </CardHeader>
          <CardContent>
            {data.top_recommendations.length === 0 ? (
              <p className="py-8 text-center text-sm text-heliox-text-muted">
                No recommendations yet. Review the Opportunities page once data is available.
              </p>
            ) : (
              <div className="space-y-3">
                {data.top_recommendations.map((rec, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-lg border border-heliox-border bg-heliox-bg px-4 py-3"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-heliox-text">{rec.title}</p>
                      <div className="mt-1 flex items-center gap-2">
                        <Badge variant="info" size="sm">
                          {rec.type.replace(/_/g, " ")}
                        </Badge>
                        <Badge
                          variant={rec.severity === "high" ? "danger" : rec.severity === "medium" ? "warning" : "default"}
                          size="sm"
                        >
                          {rec.severity}
                        </Badge>
                      </div>
                    </div>
                    <span className="ml-4 font-semibold text-success-600">
                      ${rec.estimated_savings_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Provider breakdown - full width or half */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Cost by provider</CardTitle>
            <CardDescription>Spend distribution across cloud providers</CardDescription>
          </CardHeader>
          <CardContent>
            {data.provider_breakdown.length === 0 ? (
              <p className="py-8 text-center text-sm text-heliox-text-muted">
                No provider data. Connect AWS, GCP, or Azure integrations.
              </p>
            ) : (
              <div className="flex flex-wrap gap-4">
                {data.provider_breakdown.map((p) => (
                  <div
                    key={p.provider}
                    className="rounded-lg border border-heliox-border bg-heliox-bg px-4 py-3 min-w-[140px]"
                  >
                    <p className="text-sm font-medium text-heliox-text">{p.provider}</p>
                    <p className="text-lg font-semibold">${p.cost_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
                    <p className="text-xs text-heliox-text-muted">{p.share_percent.toFixed(1)}% of total</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

export default function ROIPage() {
  return (
    <EnterpriseLayout>
      <ROIContent />
    </EnterpriseLayout>
  );
}
