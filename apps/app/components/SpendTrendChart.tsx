"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { format, eachDayOfInterval, parseISO } from "date-fns";
import MetricExplainDrawer from "@/components/ui/MetricExplainDrawer";
import { isDemoMode, generateDemoDailySpendBetween } from "@/lib/demoData";

interface SpendTrendChartProps {
  startDate: string;
  endDate: string;
}

interface DailySpend {
  date: string;
  cost: number;
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

export default function SpendTrendChart({
  startDate,
  endDate,
}: SpendTrendChartProps) {
  const [data, setData] = useState<DailySpend[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const loadData = async () => {
      if (isDemoMode()) {
        await new Promise((r) => setTimeout(r, 300));
        if (cancelled) return;
        setData(generateDemoDailySpendBetween(startDate, endDate));
        setLoading(false);
        return;
      }

      try {
        const { fetchJson } = await import("@/lib/api");
        const snapshots = await fetchJson<
          Array<{ date: string; cost_usd: number; provider?: string; gpu_type?: string }>
        >(
          `/api/v1/costs/?start_date=${startDate}&end_date=${endDate}`
        );
        if (cancelled) return;
        const byDate: Record<string, number> = {};
        for (const s of snapshots) {
          const d = s.date;
          byDate[d] = (byDate[d] || 0) + Number(s.cost_usd);
        }
        const days = eachDayOfInterval({
          start: parseISO(startDate),
          end: parseISO(endDate),
        });
        const chartData = days.map((day) => {
          const d = format(day, "yyyy-MM-dd");
          return {
            date: format(day, "MMM dd"),
            cost: byDate[d] ?? 0,
          };
        });
        setData(chartData);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load chart data");
        setData([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadData();
    return () => {
      cancelled = true;
    };
  }, [startDate, endDate]);

  const explain = useMemo<MetricExplain>(
    () => {
      const avgCost =
        data.length > 0
          ? data.reduce((acc, point) => acc + point.cost, 0) / data.length
          : 0;
      return {
        value: Number(avgCost.toFixed(2)),
        unit: "USD",
        window: `${startDate} to ${endDate}`,
        confidence: 0.4,
        confidence_reasons: ["MISSING_TELEMETRY"],
        explanation: {
          formula: "daily_cost = sum(cost_usd) per day; chart shows daily_cost over window",
          components: [
            { name: "days", value: data.length, unit: "days", source: "client" },
            { name: "avg_daily_cost", value: Number(avgCost.toFixed(2)), unit: "USD", source: "client" },
          ],
          assumptions: ["Demo data generated client-side for the selected window."],
        },
      };
    },
    [data, startDate, endDate]
  );

  if (loading) {
    return (
      <div className="flex h-80 items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
          <p className="text-sm text-muted-foreground">Loading spend trend...</p>
        </div>
      </div>
    );
  }

  if (error && data.length === 0) {
    return (
      <div className="flex h-80 flex-col items-center justify-center rounded-2xl border border-border/60 bg-muted/20 p-8 text-center">
        <p className="mb-2 text-sm font-medium text-foreground">
          Connect your cluster to view spend trends
        </p>
        <p className="mb-4 text-sm text-muted-foreground">
          No cost data for this period yet. Integrate your GPU provider to get started.
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
          No spend data for this period
        </p>
        <p className="mb-4 text-sm text-muted-foreground">
          Connect your GPU provider to start tracking costs.
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

  // Calculate max/min ratio for interpretation sentence
  // Only show if we have at least 2 data points and min > 0
  const costs = data.map((d) => d.cost);
  const maxCost = costs.length > 0 ? Math.max(...costs) : 0;
  const minCost = costs.length > 0 ? Math.min(...costs) : 0;
  const shouldShowInterpretation =
    data.length >= 2 && minCost > 0;
  const variationRatio = shouldShowInterpretation
    ? (maxCost / minCost).toFixed(1)
    : null;

  return (
    <div>
      <div className="flex items-center justify-end mb-2">
        <MetricExplainDrawer title="Daily Spend Trend" metric={explain} />
      </div>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
            <XAxis
              dataKey="date"
              stroke="hsl(var(--muted-foreground))"
              style={{ fontSize: "12px" }}
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
              formatter={(value) => {
                if (typeof value === "number") {
                  return [`$${value.toFixed(2)}`, "Cost"];
                }
                return [value ?? "-", "Cost"];
              }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="cost"
              stroke="hsl(var(--primary))"
              strokeWidth={2.5}
              dot={{ fill: "hsl(var(--primary))", r: 4 }}
              activeDot={{ r: 6, fill: "hsl(var(--primary))", strokeWidth: 2 }}
              name="Daily Cost (USD)"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {/* Analytical guidance: shows cost variation to highlight smoothing opportunities */}
      {shouldShowInterpretation && variationRatio && (
        <p className="mt-3 text-sm text-muted-foreground">
          Daily GPU spend varies by up to ~{variationRatio}× over this period,
          suggesting opportunities to smooth usage and reduce peak costs.
        </p>
      )}
      <Link
        href="/recommendations"
        className="mt-3 block text-sm font-medium text-primary hover:underline"
      >
        See recommendations for cost spikes →
      </Link>
    </div>
  );
}

