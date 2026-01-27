"use client";

import { useEffect, useState } from "react";
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
      try {
        setLoading(true);
        setError(null);

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
          <p className="text-sm text-gray-500">Unable to load cost data</p>
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="h-80 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-500 mb-2">📊 No data available</p>
          <p className="text-sm text-gray-400">
            No costs found for the selected period
          </p>
        </div>
      </div>
    );
  }

  // Transform data for chart
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
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="name"
              stroke="#6b7280"
              style={{ fontSize: "11px" }}
              angle={-45}
              textAnchor="end"
              height={80}
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
                  <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-sm">
                    <p className="font-semibold text-gray-900">{point?.name}</p>
                    <p className="text-sm text-gray-600">
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
            <Bar dataKey="cost" fill="#3b82f6" name="Cost (USD)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

