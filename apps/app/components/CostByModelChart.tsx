"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { fetchJson } from "@/lib/api";
import MetricExplainDrawer from "@/components/ui/MetricExplainDrawer";
import { isDemoMode, generateDemoCostByModel } from "@/lib/demoData";

interface CostByModelChartProps {
  startDate: string;
  endDate: string;
}

interface ModelCost {
  model_name: string;
  total_cost_usd: number;
  job_count: number;
  runtime_share?: number | null;
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

interface CostByModelResponse {
  items: ModelCost[];
  explain?: MetricExplain;
  point_explain?: Record<string, MetricExplain>;
}

export default function CostByModelChart({
  startDate,
  endDate,
}: CostByModelChartProps) {
  const [data, setData] = useState<ModelCost[]>([]);
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
        setData(generateDemoCostByModel());
        setGlobalExplain(null);
        setPointExplain({});
        setLoading(false);
        return;
      }

      try {
        const url = `/api/v1/analytics/cost/by-model?start=${startDate}&end=${endDate}&include_explain=true`;
        const result = await fetchJson<ModelCost[] | CostByModelResponse>(url);
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
          Connect your cluster to view cost by model
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
          Once you have GPU usage, cost by model will appear here.
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

  const chartData = data.map((item) => ({
    name: item.model_name,
    cost: item.total_cost_usd,
    jobs: item.job_count,
    runtimeShare: item.runtime_share,
    pointExplain: pointExplain[item.model_name],
  }));

  const explain = globalExplain ?? data[0]?.explain;

  return (
    <div>
      {explain && (
        <div className="flex items-center justify-end mb-2">
          <MetricExplainDrawer title="Cost by Model" metric={explain} />
        </div>
      )}
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
            <XAxis
              dataKey="name"
              stroke="hsl(var(--muted-foreground))"
              style={{ fontSize: "11px" }}
              angle={-45}
              textAnchor="end"
              height={80}
            />
            <YAxis
              stroke="hsl(var(--muted-foreground))"
              style={{ fontSize: "12px" }}
              tickFormatter={(value) => `$${value.toLocaleString()}`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "12px",
                boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
              }}
              formatter={(value, name, props) => {
                if (typeof value === "number") {
                  if (name === "cost") {
                    const share = props?.payload?.runtimeShare;
                    const shareLabel = typeof share === "number" ? ` (${(share * 100).toFixed(0)}% runtime)` : "";
                    return [`$${value.toFixed(2)}${shareLabel}`, "Total Cost"];
                  }
                  return [value, "Jobs"];
                }
                return [value ?? "-", name];
              }}
              content={({ active, payload }) => {
                if (!active || !payload || payload.length === 0) return null;
                const point = payload[0]?.payload;
                const pointExplain = point?.pointExplain as MetricExplain | undefined;
                return (
                  <div className="rounded-xl border border-border bg-card p-3 shadow-lg">
                    <p className="font-semibold text-foreground">{point?.name}</p>
                    <p className="text-sm text-muted-foreground">
                      Cost: ${point?.cost?.toFixed?.(2) ?? "-"}
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
              }}
            />
            <Legend />
            <Bar dataKey="cost" fill="hsl(var(--primary))" name="Cost (USD)" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

