"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";
import { fetchJson } from "@/lib/api";
import MetricExplainDrawer from "@/components/ui/MetricExplainDrawer";
import { isDemoMode, generateDemoCostByTeam } from "@/lib/demoData";

interface CostByTeamChartProps {
  startDate: string;
  endDate: string;
}

interface TeamCost {
  team_name: string;
  team_id: string;
  total_cost_usd: number;
  job_count: number;
  cost_share?: number | null;
  explain?: MetricExplain;
}

interface MetricExplain {
  value: number | string;
  unit: string;
  window: string;
  confidence: number;
  confidence_reasons: string[];
  explanation: {
    formula: string;
    components: Array<{
      name: string;
      value: number | string;
      unit?: string | null;
      source?: string | null;
    }>;
    assumptions: string[];
  };
}

interface CostByTeamResponse {
  items: TeamCost[];
  explain?: MetricExplain;
  point_explain?: Record<string, MetricExplain>;
}

const COLORS = [
  "hsl(var(--primary))",
  "hsl(262 83% 58%)",
  "hsl(330 81% 60%)",
  "hsl(38 92% 50%)",
  "hsl(160 84% 39%)",
  "hsl(239 84% 67%)",
];

export default function CostByTeamChart({
  startDate,
  endDate,
}: CostByTeamChartProps) {
  const [data, setData] = useState<TeamCost[]>([]);
  const [globalExplain, setGlobalExplain] = useState<MetricExplain | null>(null);
  const [pointExplain, setPointExplain] = useState<Record<string, MetricExplain>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);

      if (isDemoMode()) {
        await new Promise((r) => setTimeout(r, 300));
        setData(generateDemoCostByTeam());
        setGlobalExplain(null);
        setPointExplain({});
        setLoading(false);
        return;
      }

      try {
        const url = `/api/v1/analytics/cost/by-team?start=${startDate}&end=${endDate}&include_explain=true`;
        const result = await fetchJson<TeamCost[] | CostByTeamResponse>(url);
        if (Array.isArray(result)) {
          setData(result);
          setGlobalExplain(null);
          setPointExplain({});
        } else {
          setData(result.items ?? []);
          setGlobalExplain(result.explain ?? null);
          setPointExplain(result.point_explain ?? {});
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load cost data. Please try again later."
        );
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [startDate, endDate]);

  if (loading) {
    return (
      <div className="flex h-80 items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
          <p className="text-sm text-muted-foreground">Loading cost breakdown...</p>
        </div>
      </div>
    );
  }

  if (error && data.length === 0) {
    return (
      <div className="flex h-80 flex-col items-center justify-center rounded-2xl border border-border/60 bg-muted/20 p-8 text-center">
        <p className="mb-2 text-sm font-medium text-foreground">
          Connect your cluster to view cost by team
        </p>
        <p className="mb-4 text-sm text-muted-foreground">
          No cost data for this period. Integrate your GPU provider to get started.
        </p>
        <Link
          href="/settings/integrations"
          className="rounded-xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Connect data source
        </Link>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="flex h-80 flex-col items-center justify-center rounded-2xl border border-border/60 bg-muted/20 p-8 text-center">
        <p className="mb-2 text-sm font-medium text-foreground">
          No cost data for this period
        </p>
        <p className="mb-4 text-sm text-muted-foreground">
          Once you have GPU usage tagged by team, cost by team will appear here.
        </p>
        <Link
          href="/settings/integrations"
          className="rounded-xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Connect data source
        </Link>
      </div>
    );
  }

  // Transform data for chart
  const chartData = data.map((item) => ({
    name: item.team_name,
    value: item.total_cost_usd,
    jobs: item.job_count,
    costShare: item.cost_share,
    pointExplain: pointExplain[item.team_name],
  }));

  const explain = globalExplain ?? data[0]?.explain;

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const point = payload[0]?.payload;
      const pointExplain = point?.pointExplain as MetricExplain | undefined;
      return (
        <div className="rounded-xl border border-border bg-card p-3 shadow-lg">
          <p className="font-semibold text-gray-900">{payload[0].name}</p>
          <p className="text-sm text-gray-600">
            Cost: ${payload[0].value.toFixed(2)}
            {typeof payload[0].payload?.costShare === "number"
              ? ` (${(payload[0].payload.costShare * 100).toFixed(0)}%)`
              : ""}
          </p>
          <p className="text-sm text-gray-600">
            Jobs: {payload[0].payload.jobs}
          </p>
          {pointExplain && (
            <>
              <p className="text-xs text-gray-500 mt-2">
                Formula: {pointExplain.explanation.formula}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                Assumptions: {pointExplain.explanation.assumptions.join("; ")}
              </p>
            </>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div>
      {explain && (
        <div className="flex items-center justify-end mb-2">
          <MetricExplainDrawer title="Cost by Team" metric={explain} />
        </div>
      )}
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={({ name, percent }) => {
                const safePercent = typeof percent === "number" ? percent : 0;
                return `${name} (${(safePercent * 100).toFixed(0)}%)`;
              }}
              outerRadius={90}
              fill="hsl(var(--primary))"
              dataKey="value"
            >
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={COLORS[index % COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

