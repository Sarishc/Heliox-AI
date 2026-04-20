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
}

interface CostByTeamResponse {
  items: TeamCost[];
  explain?: unknown;
  point_explain?: Record<string, unknown>;
}

const COLORS = [
  "#6366f1",
  "#8b5cf6",
  "#ec4899",
  "#f59e0b",
  "#10b981",
  "#3b82f6",
  "#14b8a6",
];

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  const share =
    typeof point?.costShare === "number"
      ? `${(point.costShare * 100).toFixed(1)}%`
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
          fontSize: "13px",
          fontWeight: 600,
          color: "var(--foreground)",
          marginBottom: "6px",
        }}
      >
        {payload[0].name}
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
        ${payload[0].value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        {share && (
          <span
            style={{
              fontSize: "12px",
              fontWeight: 500,
              color: "var(--heliox-text-muted)",
              marginLeft: "6px",
            }}
          >
            ({share})
          </span>
        )}
      </p>
      <p style={{ fontSize: "11px", color: "var(--heliox-text-muted)", marginTop: "3px" }}>
        {point?.jobs ?? 0} jobs
      </p>
    </div>
  );
};

function ChartSkeleton() {
  return (
    <div className="h-80 flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div
          className="animate-pulse rounded-full"
          style={{
            width: "140px",
            height: "140px",
            border: "28px solid var(--muted)",
          }}
        />
        <div className="flex gap-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-1.5">
              <div
                className="h-2.5 w-2.5 rounded-full animate-pulse"
                style={{ background: "var(--muted)" }}
              />
              <div
                className="h-2.5 w-14 rounded animate-pulse"
                style={{ background: "var(--muted)" }}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const renderCustomLegend = (props: any) => {
  const { payload } = props;
  return (
    <div className="flex flex-wrap justify-center gap-x-4 gap-y-2 mt-2">
      {payload?.map((entry: any, i: number) => (
        <div key={i} className="flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 rounded-full shrink-0"
            style={{ background: entry.color }}
          />
          <span style={{ fontSize: "12px", color: "var(--heliox-text-secondary)" }}>
            {entry.value}
          </span>
        </div>
      ))}
    </div>
  );
};

export default function CostByTeamChart({ startDate, endDate }: CostByTeamChartProps) {
  const [data, setData] = useState<TeamCost[]>([]);
  const [loading, setLoading] = useState(true);
  const [showingSample, setShowingSample] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);

      if (isDemoMode()) {
        await new Promise((r) => setTimeout(r, 350));
        setData(generateDemoCostByTeam());
        setShowingSample(false);
        setLoading(false);
        return;
      }

      try {
        const url = `/api/v1/analytics/cost/by-team?start=${startDate}&end=${endDate}`;
        const result = await fetchJson<TeamCost[] | CostByTeamResponse>(url);
        const items = Array.isArray(result) ? result : (result.items ?? []);
        if (items.length > 0) {
          setData(items);
          setShowingSample(false);
        } else {
          setData(generateDemoCostByTeam());
          setShowingSample(true);
        }
      } catch {
        setData(generateDemoCostByTeam());
        setShowingSample(true);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [startDate, endDate]);

  if (loading) return <ChartSkeleton />;

  const chartData = data.map((item) => ({
    name: item.team_name,
    value: item.total_cost_usd,
    jobs: item.job_count,
    costShare: item.cost_share,
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
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="48%"
              innerRadius={60}
              outerRadius={100}
              paddingAngle={2}
              dataKey="value"
              stroke="none"
            >
              {chartData.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={COLORS[index % COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
            <Legend content={renderCustomLegend} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {showingSample && (
        <div className="mt-1 flex items-center justify-between">
          <p style={{ fontSize: "12px", color: "var(--heliox-text-muted)" }}>
            Tag GPU jobs with team metadata to see real allocation
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
