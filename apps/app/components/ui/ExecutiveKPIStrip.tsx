"use client";

/**
 * Executive KPI Strip — Top 0.1% Design
 * Stripe / Datadog / Linear inspired
 * With inline SVG sparklines (no container sizing issues)
 */

import { ReactNode, useEffect, useMemo, useState } from "react";
import { useReducedMotion } from "framer-motion";
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
    sparkColor: "#3fb950",
    icon:       <DollarSign className="h-4 w-4" />,
  },
  {
    border:     "#3fb950",
    iconBg:     "rgba(59, 130, 246, 0.10)",
    iconFg:     "#3fb950",
    sparkColor: "#3fb950",
    icon:       <Server className="h-4 w-4" />,
  },
  {
    border:     "#d29922",
    iconBg:     "rgba(139, 92, 246, 0.10)",
    iconFg:     "#d29922",
    sparkColor: "#d29922",
    icon:       <Cpu className="h-4 w-4" />,
  },
  {
    border:     "#f85149",
    iconBg:     "rgba(16, 185, 129, 0.10)",
    iconFg:     "#f85149",
    sparkColor: "#f85149",
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
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      style={{ width: "100%", height: "48px", display: "block" }}
      aria-hidden="true"
    >
      <path d={linePath} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="miter" strokeLinecap="butt" />
    </svg>
  );
}

export function ExecutiveKPIStrip({ kpis, className = "" }: ExecutiveKPIStripProps) {
  return (
    <div className={`grid grid-cols-2 gap-3 lg:grid-cols-4 ${className}`}>
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
  const reduceMotion = useReducedMotion();
  const numericTarget = typeof value === "number" ? value : null;
  const [animatedValue, setAnimatedValue] = useState(numericTarget ?? 0);

  useEffect(() => {
    if (numericTarget === null || reduceMotion) {
      setAnimatedValue(numericTarget ?? 0);
      return;
    }
    let frame = 0;
    const delay = window.setTimeout(() => {
      const startedAt = performance.now();
      const tick = (now: number) => {
        const progress = Math.min(1, (now - startedAt) / 360);
        const eased = 1 - Math.pow(1 - progress, 3);
        setAnimatedValue(numericTarget * eased);
        if (progress < 1) frame = window.requestAnimationFrame(tick);
      };
      frame = window.requestAnimationFrame(tick);
    }, seedIndex * 50);
    return () => {
      window.clearTimeout(delay);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [numericTarget, reduceMotion, seedIndex]);

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
        className="relative overflow-hidden rounded-md border bg-card"
        style={{ borderColor: "var(--border)" }}
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

  const displayValue = numericTarget === null ? value : animatedValue;
  const formattedValue = (() => {
    if (typeof displayValue === "string") return displayValue;
    switch (format) {
      case "currency":
        if (displayValue >= 1_000_000) return `$${(displayValue / 1_000_000).toFixed(1)}M`;
        if (displayValue >= 10_000)    return `$${(displayValue / 1_000).toFixed(0)}k`;
        return `$${Math.round(displayValue).toLocaleString()}`;
      case "number":
        return Math.round(displayValue).toLocaleString();
      case "percentage":
        return `${displayValue.toFixed(1)}%`;
      default:
        return Number.isInteger(numericTarget) ? Math.round(displayValue) : displayValue.toFixed(1);
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
      className="group relative overflow-hidden rounded-md bg-card transition-colors duration-150 hover:bg-muted"
      style={{ border: "1px solid var(--border)" }}
    >
      {/* Top accent bar */}
      <div
        className="absolute inset-y-0 left-0 w-[2px]"
        style={{ background: accent.border }}
      />

      {/* Subtle radial tint */}
      <div
        className="hidden"
      />

      {/* Content */}
      <div className="relative px-3 pb-1 pt-3">
        {/* Label + icon */}
        <div className="mb-2 flex items-start justify-between">
          <span
            className="text-[11px] font-semibold uppercase tracking-widest"
            style={{ color: "var(--heliox-text-muted)" }}
          >
            {label}
          </span>
          <div
            className="flex h-6 w-6 items-center justify-center rounded-sm"
            style={{ background: accent.iconBg, color: accent.iconFg }}
          >
            {icon ?? accent.icon}
          </div>
        </div>

        {/* Value */}
        <div className="mb-2 flex items-baseline gap-1">
          <span
            className="font-mono-tabular text-[24px] font-semibold leading-none text-foreground"
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
