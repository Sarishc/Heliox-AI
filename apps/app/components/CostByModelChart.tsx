"use client";

import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";
import Link from "next/link";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { fetchJson } from "@/lib/api";
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
}

interface CostByModelResponse {
  items: ModelCost[];
  explain?: unknown;
  point_explain?: Record<string, unknown>;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  const share =
    typeof point?.runtimeShare === "number"
      ? `${(point.runtimeShare * 100).toFixed(0)}% runtime`
      : null;
  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: "12px",
        boxShadow: "var(--shadow-lg)",
        padding: "10px 14px",
        minWidth: "150px",
      }}
    >
      <p
        style={{
          fontSize: "12px",
          fontWeight: 600,
          color: "var(--foreground)",
          marginBottom: "6px",
        }}
      >
        {label}
      </p>
      <p
        style={{
          fontSize: "15px",
          fontWeight: 700,
          color: "var(--foreground)",
          fontVariantNumeric: "tabular-nums",
          letterSpacing: "-0.02em",
        }}
      >
        ${payload[0]?.value?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
      </p>
      {share && (
        <p style={{ fontSize: "11px", color: "var(--heliox-text-muted)", marginTop: "3px" }}>
          {share}
        </p>
      )}
      <p style={{ fontSize: "11px", color: "var(--heliox-text-muted)", marginTop: "2px" }}>
        {point?.jobs ?? 0} jobs
      </p>
    </div>
  );
};

function ChartSkeleton() {
  const heights = [85, 60, 75, 45, 90, 50];
  return (
    <div className="h-80 flex flex-col justify-end px-8 pt-8 pb-12 gap-3">
      <div className="flex items-end gap-4 flex-1">
        {heights.map((h, i) => (
          <div
            key={i}
            className="flex-1 rounded-t-md animate-pulse"
            style={{ height: `${h}%`, background: "var(--muted)" }}
          />
        ))}
      </div>
      <div className="flex justify-between px-2">
        {heights.map((_, i) => (
          <div
            key={i}
            className="h-2.5 w-10 rounded animate-pulse"
            style={{ background: "var(--muted)" }}
          />
        ))}
      </div>
    </div>
  );
}

export default function CostByModelChart({ startDate, endDate }: CostByModelChartProps) {
  const reduceMotion = useReducedMotion();
  const [data, setData] = useState<ModelCost[]>([]);
  const [loading, setLoading] = useState(true);
  const [showingSample, setShowingSample] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);

      if (isDemoMode()) {
        await new Promise((r) => setTimeout(r, 350));
        setData(generateDemoCostByModel());
        setShowingSample(false);
        setLoading(false);
        return;
      }

      try {
        const url = `/api/v1/analytics/cost/by-model?start=${startDate}&end=${endDate}`;
        const result = await fetchJson<ModelCost[] | CostByModelResponse>(url);
        const items = Array.isArray(result) ? result : (result.items ?? []);
        if (items.length > 0) {
          setData(items);
          setShowingSample(false);
        } else {
          setData(generateDemoCostByModel());
          setShowingSample(true);
        }
      } catch {
        setData(generateDemoCostByModel());
        setShowingSample(true);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [startDate, endDate]);

  if (loading) return <ChartSkeleton />;

  const chartData = data.slice(0, 8).map((item) => ({
    name: item.model_name.length > 10 ? item.model_name.slice(0, 10) + "…" : item.model_name,
    fullName: item.model_name,
    cost: item.total_cost_usd,
    jobs: item.job_count,
    runtimeShare: item.runtime_share,
  }));

  return (
    <div className="relative">
      {showingSample && (
        <div
          className="absolute top-0 right-0 z-10 flex items-center gap-1.5 rounded-full px-2.5 py-1"
          style={{
            background: "rgba(245,158,11,0.08)",
            border: "1px solid rgba(245,158,11,0.2)",
          }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: "#f59e0b" }}
          />
          <span style={{ fontSize: "11px", fontWeight: 600, color: "#d97706" }}>
            Sample data
          </span>
        </div>
      )}

      <div>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={chartData} margin={{ top: 8, right: 4, bottom: 32, left: 0 }}>
            <CartesianGrid
              strokeDasharray="3 4"
              stroke="var(--chart-grid)"
              vertical={false}
              strokeOpacity={1}
            />

            <XAxis
              dataKey="name"
              tick={{ fontSize: 11, fill: "var(--heliox-text-muted)" }}
              axisLine={false}
              tickLine={false}
              angle={-35}
              textAnchor="end"
              height={52}
            />

            <YAxis
              tick={{ fontSize: 11, fill: "var(--heliox-text-muted)" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) =>
                v >= 1_000_000
                  ? `$${(v / 1_000_000).toFixed(1)}M`
                  : v >= 1_000
                  ? `$${(v / 1_000).toFixed(0)}k`
                  : `$${v}`
              }
              width={52}
            />

            <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(99,102,241,0.04)" }} />

            <Bar
              dataKey="cost"
              radius={[2, 2, 0, 0]}
              maxBarSize={44}
              name="Cost (USD)"
              isAnimationActive={!reduceMotion}
              animationDuration={360}
              animationEasing="ease-out"
            >
              {chartData.map((_, index) => (
                <Cell key={`cell-${index}`} fill="#6366f1" stroke="#818cf8" strokeWidth={1} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {showingSample && (
        <div className="mt-1 flex items-center justify-between">
          <p style={{ fontSize: "12px", color: "var(--heliox-text-muted)" }}>
            Connect GPU workloads to see cost breakdown by model
          </p>
          <Link
            href="/settings/integrations"
            style={{ fontSize: "12px", fontWeight: 600, color: "#6366f1" }}
            className="hover:underline shrink-0"
          >
            Connect data →
          </Link>
        </div>
      )}
    </div>
  );
}
