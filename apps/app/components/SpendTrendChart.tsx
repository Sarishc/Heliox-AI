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
      <div className="h-80 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-80 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 mb-2">⚠️ {error}</p>
          <p className="text-sm text-gray-500">Please try again later</p>
        </div>
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
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="date"
              stroke="#6b7280"
              style={{ fontSize: "12px" }}
            />
            <YAxis
              stroke="#6b7280"
              style={{ fontSize: "12px" }}
              tickFormatter={(value) => `$${value.toLocaleString()}`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#fff",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
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
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ fill: "#3b82f6", r: 4 }}
              activeDot={{ r: 6 }}
              name="Daily Cost (USD)"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {/* Analytical guidance: shows cost variation to highlight smoothing opportunities */}
      {shouldShowInterpretation && variationRatio && (
        <p className="text-sm text-gray-500 mt-3">
          Daily GPU spend varies by up to ~{variationRatio}× over this period,
          suggesting opportunities to smooth usage and reduce peak costs.
        </p>
      )}
      {/* CTA link: guides users from observation (chart) → diagnosis (recommendations) → action */}
      <Link
        href="/recommendations"
        className="text-sm text-blue-600 hover:text-blue-700 hover:underline mt-3 block"
      >
        See recommendations for cost spikes →
      </Link>
    </div>
  );
}

