"use client";

/**
 * Executive KPI Strip - Stripe/Datadog Style
 * Dense, high-level metrics for C-suite dashboards
 */

import { ReactNode } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

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

export function ExecutiveKPIStrip({ kpis, className = "" }: ExecutiveKPIStripProps) {
  return (
    <div className={`grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6 ${className}`}>
      {kpis.map((kpi, index) => (
        <ExecutiveKPICard key={index} {...kpi} />
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
}: ExecutiveKPI) {
  if (loading) {
    return (
      <div className="card-enterprise p-5">
        <div className="space-y-3">
          <div className="h-4 bg-muted rounded w-24 animate-pulse" />
          <div className="h-8 bg-muted rounded w-32 animate-pulse" />
          <div className="h-3 bg-muted rounded w-20 animate-pulse" />
        </div>
      </div>
    );
  }

  // Format the value based on type
  const formattedValue = (() => {
    if (typeof value === "string") return value;
    
    switch (format) {
      case "currency":
        return `$${value.toLocaleString()}`;
      case "number":
        return value.toLocaleString();
      case "percentage":
        return `${value}%`;
      default:
        return value;
    }
  })();

  // Determine trend
  const trend = change !== undefined ? (change > 0 ? "up" : change < 0 ? "down" : "neutral") : null;
  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;

  return (
    <div className="card-enterprise card-enterprise-hover p-5 transition-all duration-200">
      {/* Label */}
      <div className="flex items-center justify-between mb-3">
        <div className="kpi-label">{label}</div>
        {icon && (
          <div className="text-heliox-text-muted opacity-40">
            {icon}
          </div>
        )}
      </div>

      {/* Value */}
      <div className="mb-2">
        <div className="flex items-baseline gap-1">
          <span className="kpi-value font-mono-tabular text-heliox-text">
            {formattedValue}
          </span>
          {unit && (
            <span className="text-sm text-heliox-text-secondary font-medium">
              {unit}
            </span>
          )}
        </div>
      </div>

      {/* Change Indicator */}
      {change !== undefined && (
        <div className="flex items-center gap-1.5">
          <div
            className={`
              metric-delta text-xs
              ${trend === "up" ? "positive" : trend === "down" ? "negative" : "neutral"}
            `}
          >
            <TrendIcon className="w-3 h-3" />
            <span className="font-mono-tabular">
              {change > 0 && "+"}
              {change.toFixed(1)}%
            </span>
          </div>
          <span className="text-xs text-heliox-text-muted">
            {changeLabel}
          </span>
        </div>
      )}
    </div>
  );
}
