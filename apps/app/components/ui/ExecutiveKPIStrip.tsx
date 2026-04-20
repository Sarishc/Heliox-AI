"use client";

/**
 * Executive KPI Strip — Top 0.1% Design
 * Stripe / Datadog / Linear inspired
 * With inline SVG sparklines (no container sizing issues)
 */

import { ReactNode, useMemo } from "react";
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
  sparkline?: number[];
}

interface ExecutiveKPIStripProps {
  kpis: ExecutiveKPI[];
  className?: string;
}

const ACCENTS = [
  {
    border:     "#6366f1",
    iconBg:     "rgba(99, 102, 241, 0.10)",
    iconFg:     "#6366f1",
    sparkColor: "#6366f1",
    icon:       <DollarSign className="h-4 w-4" />,
  },
  {
    border:     "#3b82f6",
    iconBg:     "rgba(59, 130, 246, 0.10)",
    iconFg:     "#3b82f6",
    sparkColor: "#3b82f6",
    icon:       <Server className="h-4 w-4" />,
  },
  {
    border:     "#8b5cf6",
    iconBg:     "rgba(139, 92, 246, 0.10)",
    iconFg:     "#8b5cf6",
    sparkColor: "#8b5cf6",
    icon:       <Cpu className="h-4 w-4" />,
  },
  {
    border:     "#10b981",
    iconBg:     "rgba(16, 185, 129, 0.10)",
    iconFg:     "#10b981",
    sparkColor: "#10b981",
    icon:       <Zap className="h-4 w-4" />,
  },
] as const;

/** Generate a deterministic sparkline without any randomness side-effects */
function genSparkline(seed: number, trend: "up" | "down" | "neutral", n = 16): number[] {
  const out: number[] = [];
  let v = 60;
  for (let i = 0; i < n; i++) {
    const noise = Math.sin(seed * 3.7 + i * 1.3) * 18 + Math.cos(seed * 1.1 + i * 2.7) * 10;
    const drift = trend === "up" ? i * 2 : trend === "down" ? -i * 1.5 : 0;
    v = Math.max(8, Math.min(100, 60 + noise + drift));
    out.push(Math.round(v));
  }
  return out;
}

/** Inline SVG sparkline — zero container-size warnings */
function Sparkline({ values, color }: { values: number[]; color: string }) {
  const W = 200;
  const H = 40;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const linePath = `M ${pts.join(" L ")}`;
  const areaPath = `M 0,${H} L ${pts.join(" L ")} L ${W},${H} Z`;

  const gradId = `sg-${color.replace("#", "")}`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      style={{ width: "100%", height: "48px", display: "block" }}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.18" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradId})`} />
      <path d={linePath} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function ExecutiveKPIStrip({ kpis, className = "" }: ExecutiveKPIStripProps) {
  return (
    <div className={`grid grid-cols-2 gap-4 lg:grid-cols-4 ${className}`}>
      {kpis.map((kpi, index) => (
        <ExecutiveKPICard key={index} {...kpi} accentIndex={index % ACCENTS.length} seedIndex={index} />
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
  sparkline,
  accentIndex = 0,
  seedIndex = 0,
}: ExecutiveKPI & { accentIndex?: number; seedIndex?: number }) {
  const accent = ACCENTS[accentIndex];

  const trend =
    change !== undefined ? (change > 0 ? "up" : change < 0 ? "down" : "neutral") : "neutral";

  const sparkValues = useMemo(
    () => sparkline ?? genSparkline(seedIndex + 1, trend),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [seedIndex, trend]
  );

  if (loading) {
    return (
      <div
        className="relative overflow-hidden rounded-2xl border bg-card"
        style={{ borderColor: "var(--border)", boxShadow: "var(--shadow-card)" }}
      >
        <div className="absolute inset-x-0 top-0 h-[3px] opacity-30" style={{ background: accent.border }} />
        <div className="p-5 space-y-3">
          <div className="h-3 w-20 animate-pulse rounded bg-muted" />
          <div className="h-8 w-28 animate-pulse rounded-lg bg-muted" />
          <div className="h-3 w-16 animate-pulse rounded bg-muted" />
        </div>
        <div className="h-12 animate-pulse" style={{ background: "var(--muted)", opacity: 0.4 }} />
      </div>
    );
  }

  const formattedValue = (() => {
    if (typeof value === "string") return value;
    switch (format) {
      case "currency":
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
      style={{ border: "1px solid var(--border)", boxShadow: "var(--shadow-card)" }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = "var(--shadow-md)";
        (e.currentTarget as HTMLDivElement).style.borderColor = accent.border + "55";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = "var(--shadow-card)";
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--border)";
      }}
    >
      {/* Top accent bar */}
      <div
        className="absolute inset-x-0 top-0 h-[3px]"
        style={{ background: `linear-gradient(90deg, ${accent.border}, ${accent.border}66)` }}
      />

      {/* Subtle radial tint */}
      <div
        className="absolute inset-0 pointer-events-none opacity-40"
        style={{ background: `radial-gradient(ellipse 80% 60% at 90% 10%, ${accent.iconBg}, transparent)` }}
      />

      {/* Content */}
      <div className="relative px-5 pb-2 pt-5">
        {/* Label + icon */}
        <div className="mb-3 flex items-start justify-between">
          <span
            className="text-[11px] font-semibold uppercase tracking-widest"
            style={{ color: "var(--heliox-text-muted)" }}
          >
            {label}
          </span>
          <div
            className="flex h-8 w-8 items-center justify-center rounded-xl transition-transform duration-200 group-hover:scale-105"
            style={{ background: accent.iconBg, color: accent.iconFg }}
          >
            {icon ?? accent.icon}
          </div>
        </div>

        {/* Value */}
        <div className="mb-2 flex items-baseline gap-1">
          <span
            className="font-mono-tabular text-[28px] font-bold leading-none text-foreground"
            style={{ letterSpacing: "-0.03em" }}
          >
            {formattedValue}
          </span>
          {unit && (
            <span className="text-sm font-semibold" style={{ color: "var(--heliox-text-muted)" }}>
              {unit}
            </span>
          )}
        </div>

        {/* Delta pill */}
        {change !== undefined && (
          <div className="mb-3 flex items-center gap-2">
            <span
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold font-mono-tabular"
              style={{ background: trendStyle.bg, color: trendStyle.fg }}
            >
              <TrendIcon className="h-3 w-3" />
              {change > 0 && "+"}
              {change.toFixed(1)}%
            </span>
            <span className="text-[11px] font-medium" style={{ color: "var(--heliox-text-muted)" }}>
              {changeLabel}
            </span>
          </div>
        )}
      </div>

      {/* Sparkline */}
      <div className="relative" style={{ opacity: 0.75 }}>
        <Sparkline values={sparkValues} color={accent.sparkColor} />
      </div>
    </div>
  );
}
