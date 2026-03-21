/**
 * KPI (Key Performance Indicator) Component
 * Enterprise-grade metric display with trends and sparklines
 */

import { ReactNode } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Card } from "./Card";

interface KPIProps {
  label: string;
  value: string | number;
  change?: number;
  changeLabel?: string;
  icon?: ReactNode;
  trend?: "up" | "down" | "neutral";
  loading?: boolean;
  description?: string;
  className?: string;
}

export function KPI({
  label,
  value,
  change,
  changeLabel = "vs last period",
  icon,
  trend,
  loading = false,
  description,
  className = "",
}: KPIProps) {
  // Auto-determine trend if not provided
  const determinedTrend = trend || (change !== undefined ? (change > 0 ? "up" : change < 0 ? "down" : "neutral") : "neutral");

  const trendConfig = {
    up: {
      icon: TrendingUp,
      color: "text-success-600 dark:text-success-500",
      bg: "bg-success-50 dark:bg-success-500/10",
    },
    down: {
      icon: TrendingDown,
      color: "text-danger-600 dark:text-danger-500",
      bg: "bg-danger-50 dark:bg-danger-500/10",
    },
    neutral: {
      icon: Minus,
      color: "text-muted-foreground",
      bg: "bg-muted",
    },
  };

  const config = trendConfig[determinedTrend];
  const TrendIcon = config.icon;

  if (loading) {
    return (
      <Card className={className} loading={loading}>
        <div />
      </Card>
    );
  }

  return (
    <Card className={className} hoverable>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            {icon && (
              <div className="p-2 rounded-lg bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400">
                {icon}
              </div>
            )}
            <p className="text-sm font-medium text-muted-foreground">{label}</p>
          </div>

          <div className="flex items-baseline gap-3">
            <h3 className="text-3xl font-bold text-foreground tracking-tight">
              {value}
            </h3>

            {change !== undefined && (
              <div className={`flex items-center gap-1 px-2 py-1 rounded-md ${config.bg}`}>
                <TrendIcon className={`w-3.5 h-3.5 ${config.color}`} />
                <span className={`text-xs font-semibold ${config.color}`}>
                  {Math.abs(change)}%
                </span>
              </div>
            )}
          </div>

          {(changeLabel || description) && (
            <p className="text-xs text-muted-foreground mt-2">
              {changeLabel}
              {description && ` • ${description}`}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}

export function KPIGrid({
  children,
  columns = 4,
  className = "",
}: {
  children: ReactNode;
  columns?: 2 | 3 | 4;
  className?: string;
}) {
  const gridCols = {
    2: "grid-cols-1 md:grid-cols-2",
    3: "grid-cols-1 md:grid-cols-2 lg:grid-cols-3",
    4: "grid-cols-1 md:grid-cols-2 lg:grid-cols-4",
  };

  return (
    <div className={`grid ${gridCols[columns]} gap-4 ${className}`}>
      {children}
    </div>
  );
}
