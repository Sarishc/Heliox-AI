"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { fetchJson } from "@/lib/api";
import { Skeleton } from "@/components/ui/Skeleton";
import MetricExplainDrawer from "@/components/ui/MetricExplainDrawer";

interface BudgetStatus {
  percent_used: number;
  predicted_breach_date?: string | null;
  policy: {
    environment: string;
    project?: string | null;
    monthly_budget_usd: number;
  };
  mtd_spend_usd: number;
  forecasted_eom_spend_usd: number;
  explain?: MetricExplain;
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

const formatCurrency = (value: number) =>
  `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

export default function BudgetStatusCard() {
  const [data, setData] = useState<BudgetStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchJson<BudgetStatus[]>("/api/v1/budgets/status?include_explain=true");
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load budget status.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const summary = useMemo(() => {
    if (data.length === 0) {
      return null;
    }
    const sorted = [...data].sort((a, b) => b.percent_used - a.percent_used);
    const top = sorted[0];
    const breach = data
      .map((item) => item.predicted_breach_date)
      .filter(Boolean)
      .sort()[0];
    return { top, breach };
  }, [data]);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Budget guardrails</p>
          <div className="flex items-center gap-2">
            <h3 className="mt-1 text-lg font-semibold text-slate-900">
              Budget used
            </h3>
            {summary?.top?.explain && (
              <MetricExplainDrawer title="Budget used" metric={summary.top.explain} />
            )}
          </div>
        </div>
        <div className="rounded-lg bg-slate-100 p-2 text-slate-600">
          <AlertTriangle className="h-4 w-4" />
        </div>
      </div>

      {loading ? (
        <div className="mt-6 space-y-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-6 w-32" />
        </div>
      ) : error ? (
        <p className="mt-6 text-sm text-rose-600">{error}</p>
      ) : !summary ? (
        <p className="mt-6 text-sm text-slate-500">
          Create a budget policy to monitor spend against targets.
        </p>
      ) : (
        <div className="mt-6 space-y-3">
          <div className="flex items-center justify-between text-sm text-slate-600">
            <span>Highest usage</span>
            <span className="text-base font-semibold text-slate-900">
              {(summary.top.percent_used * 100).toFixed(0)}%
            </span>
          </div>
          {summary.top.explain && (
            <div className="text-xs text-slate-500">
              <span className="mr-2">Explainability</span>
              <span className="text-slate-600">
                Confidence: {(summary.top.explain.confidence * 100).toFixed(0)}%
              </span>
            </div>
          )}
          <div className="flex items-center justify-between text-sm text-slate-600">
            <span>Spend vs budget</span>
            <span className="text-base font-semibold text-slate-900">
              {formatCurrency(summary.top.mtd_spend_usd)} /{" "}
              {formatCurrency(summary.top.policy.monthly_budget_usd)}
            </span>
          </div>
          <div className="text-xs text-slate-500">
            Predicted breach: {summary.breach ?? "none projected"}
          </div>
        </div>
      )}
    </div>
  );
}
