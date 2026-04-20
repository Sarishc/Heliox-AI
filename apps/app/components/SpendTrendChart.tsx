"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { format, eachDayOfInterval, parseISO } from "date-fns";
import { isDemoMode, generateDemoDailySpendBetween } from "@/lib/demoData";

interface SpendTrendChartProps {
  startDate: string;
  endDate: string;
}
interface DailySpend {
  date: string;
  cost: number;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const value = payload[0]?.value ?? 0;
  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: "12px",
        boxShadow: "var(--shadow-lg)",
        padding: "10px 14px",
        minWidth: "130px",
      }}
    >
      <p style={{ fontSize: "11px", color: "var(--heliox-text-muted)", marginBottom: "4px" }}>
        {label}
      </p>
      <p
        style={{
          fontSize: "16px",
          fontWeight: 700,
          color: "var(--foreground)",
          fontVariantNumeric: "tabular-nums",
          letterSpacing: "-0.02em",
        }}
      >
        ${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
      </p>
      <p style={{ fontSize: "11px", color: "var(--heliox-text-muted)", marginTop: "2px" }}>
        GPU spend
      </p>
    </div>
  );
};

function ChartSkeleton() {
  const bars = [45, 62, 38, 78, 55, 88, 67, 52, 71, 84, 60, 45, 73, 90, 58, 77, 42, 66, 80, 53];
  return (
    <div className="h-80 flex flex-col justify-end px-2 pt-8 pb-6 gap-3">
      <div className="flex items-end gap-1 flex-1">
        {bars.map((h, i) => (
          <div
            key={i}
            className="flex-1 rounded-t-sm animate-pulse"
            style={{ height: `${h}%`, background: "var(--muted)" }}
          />
        ))}
      </div>
      <div className="flex justify-between">
        {[0, 1, 2, 3].map((i) => (
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

export default function SpendTrendChart({ startDate, endDate }: SpendTrendChartProps) {
  const [data, setData] = useState<DailySpend[]>([]);
  const [loading, setLoading] = useState(true);
  const [showingSample, setShowingSample] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    const loadData = async () => {
      if (isDemoMode()) {
        await new Promise((r) => setTimeout(r, 400));
        if (cancelled) return;
        setData(generateDemoDailySpendBetween(startDate, endDate));
        setShowingSample(false);
        setLoading(false);
        return;
      }

      try {
        const { fetchJson } = await import("@/lib/api");
        const snapshots = await fetchJson<
          Array<{ date: string; cost_usd: number }>
        >(`/api/v1/costs/?start_date=${startDate}&end_date=${endDate}`);
        if (cancelled) return;

        const byDate: Record<string, number> = {};
        for (const s of snapshots) {
          byDate[s.date] = (byDate[s.date] || 0) + Number(s.cost_usd);
        }
        const days = eachDayOfInterval({
          start: parseISO(startDate),
          end: parseISO(endDate),
        });
        const chartData = days.map((day) => {
          const d = format(day, "yyyy-MM-dd");
          return { date: format(day, "MMM d"), cost: byDate[d] ?? 0 };
        });

        const hasRealData = chartData.some((d) => d.cost > 0);
        if (hasRealData) {
          setData(chartData);
          setShowingSample(false);
        } else {
          setData(generateDemoDailySpendBetween(startDate, endDate));
          setShowingSample(true);
        }
      } catch {
        if (cancelled) return;
        setData(generateDemoDailySpendBetween(startDate, endDate));
        setShowingSample(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadData();
    return () => {
      cancelled = true;
    };
  }, [startDate, endDate]);

  if (loading) return <ChartSkeleton />;

  const costs = data.map((d) => d.cost);
  const avg = costs.reduce((a, b) => a + b, 0) / (costs.length || 1);

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
          <AreaChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="spendGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#6366f1" stopOpacity={0.14} />
                <stop offset="70%" stopColor="#6366f1" stopOpacity={0.03} />
                <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>

            <CartesianGrid
              strokeDasharray="3 4"
              stroke="var(--chart-grid)"
              vertical={false}
              strokeOpacity={1}
            />

            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: "var(--heliox-text-muted)" }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
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

            <Tooltip
              content={<CustomTooltip />}
              cursor={{
                stroke: "rgba(99,102,241,0.25)",
                strokeWidth: 1,
                strokeDasharray: "4 4",
              }}
            />

            <ReferenceLine
              y={avg}
              stroke="#6366f1"
              strokeDasharray="5 5"
              strokeOpacity={0.2}
              strokeWidth={1}
            />

            <Area
              type="monotone"
              dataKey="cost"
              stroke="#6366f1"
              strokeWidth={2.5}
              fill="url(#spendGradient)"
              dot={false}
              activeDot={{
                r: 5,
                fill: "#6366f1",
                stroke: "#fff",
                strokeWidth: 2,
              }}
              name="Daily Cost"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 flex items-center justify-between">
        {showingSample ? (
          <>
            <p style={{ fontSize: "12px", color: "var(--heliox-text-muted)" }}>
              Connect your cloud provider to see real cost data
            </p>
            <Link
              href="/settings/integrations"
              style={{ fontSize: "12px", fontWeight: 600, color: "#6366f1" }}
              className="hover:underline shrink-0"
            >
              Connect data →
            </Link>
          </>
        ) : (
          <p style={{ fontSize: "12px", color: "var(--heliox-text-muted)" }}>
            Avg daily spend:{" "}
            <span
              style={{
                fontWeight: 600,
                color: "var(--heliox-text-secondary)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              ${avg.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>
          </p>
        )}
      </div>
    </div>
  );
}
