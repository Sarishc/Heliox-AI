"use client";

import { useEffect, useState } from "react";
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

const COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#6366f1"];

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
      try {
        setLoading(true);
        setError(null);

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
        <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-sm">
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
              outerRadius={80}
              fill="#8884d8"
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

