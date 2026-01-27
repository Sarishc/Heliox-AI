"use client";

import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { TrendingUp } from "lucide-react";
import { fetchJson } from "@/lib/api";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";
import Skeleton from "@/components/ui/Skeleton";
import MetricExplainDrawer from "@/components/ui/MetricExplainDrawer";

interface EfficiencyTrend {
  date: string;
  revenue_per_gpu_dollar: number;
  revenue_per_gpu_dollar_smoothed?: number;
}

interface BusinessEfficiencyResponse {
  efficiency_trends: EfficiencyTrend[];
  revenue_per_gpu_dollar_explain?: MetricExplain;
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

export default function CostEfficiencyCard() {
  const { startDate, endDate } = useDashboardFilters();
  const [data, setData] = useState<EfficiencyTrend[]>([]);
  const [explain, setExplain] = useState<MetricExplain | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchJson<BusinessEfficiencyResponse>(
          `/api/v1/analytics/business-efficiency?start=${startDate}&end=${endDate}&window_days=7&include_explain=true`
        );
        setData(result.efficiency_trends ?? []);
        setExplain(result.revenue_per_gpu_dollar_explain ?? null);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Unable to load efficiency data."
        );
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [startDate, endDate]);

  const chartData = useMemo(
    () =>
      data.map((point) => ({
        date: point.date,
        value: point.revenue_per_gpu_dollar_smoothed ?? point.revenue_per_gpu_dollar,
      })),
    [data]
  );

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Cost Efficiency</p>
          <div className="flex items-center gap-2">
            <h3 className="mt-1 text-lg font-semibold text-slate-900">
              Revenue per GPU Dollar
            </h3>
            {explain && (
              <MetricExplainDrawer title="Revenue per GPU Dollar" metric={explain} />
            )}
          </div>
        </div>
        <div className="rounded-lg bg-slate-100 p-2 text-slate-600">
          <TrendingUp className="h-4 w-4" />
        </div>
      </div>

      {loading ? (
        <div className="mt-6 space-y-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : error ? (
        <p className="mt-6 text-sm text-rose-600">{error}</p>
      ) : chartData.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">
          Add business KPI metrics to see cost efficiency trends.
        </p>
      ) : (
        <div className="mt-6 h-48">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <XAxis dataKey="date" hide />
              <YAxis
                tickFormatter={(value) => `$${Number(value).toFixed(0)}`}
                width={50}
              />
              <Tooltip
                formatter={(value) => [`$${Number(value).toFixed(2)}`, "Revenue / $GPU"]}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
