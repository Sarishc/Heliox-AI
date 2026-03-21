"use client";

/**
 * Executive KPI Strip — Top 0.1% Design
 * Stripe / Datadog / Linear inspired
 */

import { ReactNode } from "react";
import { TrendingUp, TrendingDown, Minus, DollarSign, Server, Cpu, Zap } from "lucide-react";

interface ExecutiveKPI {
  label: string;
  value: string | number;
  unit?: string;
  change?: number;
  changeLabel?: string;
  icon?: ReactNode;
  format?: "currency" | "number" | "percentage" | "custom";
  loading?: boolean;
}

interface ExecutiveKPIStripProps {
  kpis: ExecutiveKPI[];
  className?: string;
}

// Per-card accent palette  (indigo → blue → violet → emerald)
const ACCENTS = [
  {
    border:   "#6366f1",
    iconBg:   "rgba(99, 102, 241, 0.10)",
    iconFg:   "#6366f1",
    deltaBg:  "rgba(99, 102, 241, 0.08)",
    deltaFg:  "#4f46e5",
    icon:     <DollarSign className="h-4 w-4" />,
  },
  {
    border:   "#3b82f6",
    iconBg:   "rgba(59, 130, 246, 0.10)",
    iconFg:   "#3b82f6",
    deltaBg:  "rgba(59, 130, 246, 0.08)",
    deltaFg:  "#2563eb",
    icon:     <Server className="h-4 w-4" />,
  },
  {
    border:   "#8b5cf6",
    iconBg:   "rgba(139, 92, 246, 0.10)",
    iconFg:   "#8b5cf6",
    deltaBg:  "rgba(139, 92, 246, 0.08)",
    deltaFg:  "#7c3aed",
    icon:     <Cpu className="h-4 w-4" />,
  },
  {
    border:   "#10b981",
    iconBg:   "rgba(16, 185, 129, 0.10)",
    iconFg:   "#10b981",
    deltaBg:  "rgba(16, 185, 129, 0.08)",
    deltaFg:  "#059669",
    icon:     <Zap className="h-4 w-4" />,
  },
] as const;

export function ExecutiveKPIStrip({ kpis, className = "" }: ExecutiveKPIStripProps) {
  return (
    <div className={`grid grid-cols-2 gap-4 lg:grid-cols-4 ${className}`}>
      {kpis.map((kpi, index) => (
        <ExecutiveKPICard key={index} {...kpi} accentIndex={index % ACCENTS.length} />
      ))}
    </div>
  );
}

function ExecutiveKPICard({
  label,
  value,
  unit,
  change,
  changeLabel = "vs last period",
  icon,
  format = "custom",
  loading = false,
  accentIndex = 0,
}: ExecutiveKPI & { accentIndex?: number }) {
  const accent = ACCENTS[accentIndex];

  if (loading) {
    return (
      <div
        className="relative overflow-hidden rounded-2xl border bg-card p-5"
        style={{ borderColor: "var(--border)", boxShadow: "var(--shadow-card)" }}
      >
        {/* top accent shimmer */}
        <div
          className="absolute inset-x-0 top-0 h-[3px] opacity-30"
          style={{ background: accent.border }}
        />
        <div className="mt-1 space-y-3">
          <div className="h-3 w-20 animate-pulse rounded bg-muted" />
          <div className="h-8 w-28 animate-pulse rounded-lg bg-muted" />
          <div className="h-3 w-16 animate-pulse rounded bg-muted" />
        </div>
      </div>
    );
  }

  /* ── Format value ─────────────────────── */
  const formattedValue = (() => {
    if (typeof value === "string") return value;
    switch (format) {
      case "currency":
        // Compact: $1.6M or $847k
        if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
        if (value >= 10_000)    return `$${(value / 1_000).toFixed(0)}k`;
        return `$${value.toLocaleString()}`;
      case "number":
        return value.toLocaleString();
      case "percentage":
        return `${value}%`;
      default:
        return value;
    }
  })();

  /* ── Trend ────────────────────────────── */
  const trend =
    change !== undefined ? (change > 0 ? "up" : change < 0 ? "down" : "neutral") : null;
  const TrendIcon =
    trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;

  const trendStyle =
    trend === "up"
      ? { bg: "rgba(16,185,129,0.08)", fg: "#059669" }
      : trend === "down"
      ? { bg: "rgba(239,68,68,0.08)", fg: "#dc2626" }
      : { bg: "var(--muted)", fg: "var(--muted-foreground)" };

  return (
    <div
      className="group relative overflow-hidden rounded-2xl bg-card transition-all duration-200 hover:-translate-y-[1px]"
      style={{
        border: "1px solid var(--border)",
        boxShadow: "var(--shadow-card)",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = "var(--shadow-md)";
        (e.currentTarget as HTMLDivElement).style.borderColor = accent.border + "55";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = "var(--shadow-card)";
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--border)";
      }}
    >
      {/* ── Top colored accent bar ──────── */}
      <div
        className="absolute inset-x-0 top-0 h-[3px]"
        style={{ background: `linear-gradient(90deg, ${accent.border}, ${accent.border}88)` }}
      />

      {/* ── Subtle card tint ────────────── */}
      <div
        className="absolute inset-0 pointer-events-none opacity-40"
        style={{
          background: `radial-gradient(ellipse 80% 60% at 90% 10%, ${accent.iconBg}, transparent)`,
        }}
      />

      <div className="relative px-5 pb-5 pt-5">
        {/* ── Label + Icon row ─────────── */}
        <div className="mb-4 flex items-start justify-between">
          <span
            className="text-[11px] font-semibold uppercase tracking-widest"
            style={{ color: "var(--heliox-text-muted)" }}
          >
            {label}
          </span>

          {/* Icon badge */}
          <div
            className="flex h-8 w-8 items-center justify-center rounded-xl transition-all duration-200 group-hover:scale-105"
            style={{ background: accent.iconBg, color: accent.iconFg }}
          >
            {icon ?? accent.icon}
          </div>
        </div>

        {/* ── Primary value ────────────── */}
        <div className="mb-3 flex items-baseline gap-1">
          <span
            className="font-mono-tabular text-[28px] font-bold leading-none text-foreground"
            style={{ letterSpacing: "-0.03em" }}
          >
            {formattedValue}
          </span>
          {unit && (
            <span
              className="text-sm font-semibold"
              style={{ color: "var(--heliox-text-muted)" }}
            >
              {unit}
            </span>
          )}
        </div>

        {/* ── Delta pill ───────────────── */}
        {change !== undefined && (
          <div className="flex items-center gap-2">
            <span
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold font-mono-tabular"
              style={{ background: trendStyle.bg, color: trendStyle.fg }}
            >
              <TrendIcon className="h-3 w-3" />
              {change > 0 && "+"}
              {change.toFixed(1)}%
            </span>
            <span
              className="text-[11px] font-medium"
              style={{ color: "var(--heliox-text-muted)" }}
            >
              {changeLabel}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
