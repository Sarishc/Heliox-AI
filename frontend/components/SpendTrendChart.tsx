"use client";

import { useEffect, useState } from "react";
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

interface SpendTrendChartProps {
  startDate: string;
  endDate: string;
}

interface DailySpend {
  date: string;
  cost: number;
}

export default function SpendTrendChart({
  startDate,
  endDate,
}: SpendTrendChartProps) {
  const [data, setData] = useState<DailySpend[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Generate mock daily spend data
    // In production, this would call: GET /analytics/cost/daily?start=&end=
    const generateMockData = () => {
      try {
        const days = eachDayOfInterval({
          start: parseISO(startDate),
          end: parseISO(endDate),
        });

        const mockData = days.map((day) => ({
          date: format(day, "MMM dd"),
          cost: Math.random() * 2000 + 1000, // Random cost between $1000-$3000
        }));

        setData(mockData);
        setLoading(false);
      } catch (err) {
        setError("Failed to generate chart data");
        setLoading(false);
      }
    };

    setLoading(true);
    // Simulate API delay
    const timer = setTimeout(generateMockData, 500);
    return () => clearTimeout(timer);
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
              formatter={(value: number) => [`$${value.toFixed(2)}`, "Cost"]}
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

