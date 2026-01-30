"use client";

import { useEffect, useState } from "react";
import { CheckCircle, Clock, ShieldAlert } from "lucide-react";
import { fetchJson } from "@/lib/api";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";
import { Skeleton } from "@/components/ui/Skeleton";
import MetricExplainDrawer from "@/components/ui/MetricExplainDrawer";

interface OptimizationAction {
  action: string;
  rationale: string;
  savings_estimate: number;
  risk_level: "low" | "medium" | "high";
  confidence: "low" | "medium" | "high";
  roi?: number | null;
  payback_period_days?: number | null;
  business_priority_score?: number;
  explain?: MetricExplain;
  roi_explain?: MetricExplain;
}

interface MetricExplain {
  value: number | string;
  unit: string;
  window: string;
  confidence: number;
  confidence_reasons: string[];
  explanation: {
    formula: string;
    components: Array<{
      name: string;
      value: number | string;
      unit?: string | null;
      source?: string | null;
    }>;
    assumptions: string[];
  };
}

const riskStyles = {
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  high: "bg-rose-50 text-rose-700 border-rose-200",
};

export default function OptimizationActions() {
  const { startDate, endDate } = useDashboardFilters();
  const [actions, setActions] = useState<OptimizationAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchJson<OptimizationAction[]>(
          `/api/v1/optimize/roi?start_date=${startDate}&end_date=${endDate}&include_explain=true`
        );
        setActions(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load actions.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [startDate, endDate]);

  if (loading) {
    return (
      <div className="space-y-4">
        {[0, 1, 2].map((index) => (
          <div key={index} className="rounded-2xl border border-slate-200 bg-white p-5">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="mt-3 h-3 w-full" />
            <Skeleton className="mt-2 h-3 w-3/4" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">
        {error}
      </div>
    );
  }

  if (actions.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white px-5 py-6 text-sm text-slate-500">
        No optimization actions found for the selected window.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {actions.map((action, index) => (
        <div
          key={`${action.action}-${index}`}
          className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-slate-900">{action.action}</span>
                <span
                  className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
                    riskStyles[action.risk_level]
                  }`}
                >
                  {action.risk_level.toUpperCase()} risk
                </span>
              </div>
              <p className="text-sm text-slate-600">{action.rationale}</p>
              <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500">
                <span>Confidence: {action.confidence}</span>
                <span className="flex items-center gap-2">
                  ROI: {action.roi ?? "—"}
                  {action.roi_explain && (
                    <MetricExplainDrawer title="ROI" metric={action.roi_explain} />
                  )}
                </span>
                <span>Payback: {action.payback_period_days ?? "—"} days</span>
              </div>
            </div>

            <div className="text-right">
              <p className="text-xs uppercase text-slate-500">Savings / mo</p>
              <div className="flex items-center justify-end gap-2">
                <p className="text-2xl font-semibold text-emerald-600">
                  ${action.savings_estimate.toLocaleString()}
                </p>
                {action.explain && (
                  <MetricExplainDrawer title="Savings estimate" metric={action.explain} />
                )}
              </div>
              <div className="mt-3 flex justify-end gap-2">
                <button className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50">
                  <Clock className="h-3 w-3" />
                  Apply later
                </button>
                <button className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700">
                  <CheckCircle className="h-3 w-3" />
                  Acknowledge
                </button>
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
