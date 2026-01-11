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

interface CostByModelChartProps {
  startDate: string;
  endDate: string;
}

interface ModelCost {
  model_name: string;
  total_cost_usd: number;
  job_count: number;
}

export default function CostByModelChart({
  startDate,
  endDate,
}: CostByModelChartProps) {
  const [data, setData] = useState<ModelCost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);

        const url = `/api/v1/analytics/cost/by-model?start=${startDate}&end=${endDate}`;
        const result = await fetchJson<ModelCost[]>(url);
        setData(result);
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
  }));

  return (
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
            formatter={(value: number, name: string) => {
              if (name === "cost") return [`$${value.toFixed(2)}`, "Total Cost"];
              return [value, "Jobs"];
            }}
          />
          <Legend />
          <Bar dataKey="cost" fill="#3b82f6" name="Cost (USD)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

