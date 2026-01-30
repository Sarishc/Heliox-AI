"use client";

import { useEffect, useState } from "react";
import { Gauge } from "lucide-react";
import { fetchJson } from "@/lib/api";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";
import { Skeleton } from "@/components/ui/Skeleton";
import MetricExplainDrawer from "@/components/ui/MetricExplainDrawer";

interface SavingsSummaryResponse {
  total_spend_usd: number;
  estimated_idle_waste_usd: number;
  total_spend_explain?: MetricExplain;
  idle_waste_explain?: MetricExplain;
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

export default function UtilizationCard() {
  const { startDate, endDate } = useDashboardFilters();
  const [utilization, setUtilization] = useState<number | null>(null);
  const [explain, setExplain] = useState<MetricExplain | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const summary = await fetchJson<SavingsSummaryResponse>(
          `/api/v1/analytics/savings/summary?start=${startDate}&end=${endDate}&include_explain=true`
        );
        if (summary.total_spend_usd <= 0) {
          setUtilization(null);
        } else {
          const wasteRatio = summary.estimated_idle_waste_usd / summary.total_spend_usd;
          const utilizationPct = Math.max(0, Math.min(1, 1 - wasteRatio)) * 100;
          setUtilization(utilizationPct);
          if (summary.total_spend_explain && summary.idle_waste_explain) {
            const confidence = Math.min(
              summary.total_spend_explain.confidence,
              summary.idle_waste_explain.confidence
            );
            setExplain({
              value: Number(utilizationPct.toFixed(2)),
              unit: "percent",
              window: summary.total_spend_explain.window,
              confidence,
              confidence_reasons: [
                ...summary.total_spend_explain.confidence_reasons,
                ...summary.idle_waste_explain.confidence_reasons,
              ],
              explanation: {
                formula: "utilization = 1 - (idle_waste / total_spend)",
                components: [
                  {
                    name: "total_spend",
                    value: summary.total_spend_usd.toFixed(2),
                    unit: "USD",
                    source: "cost_snapshots",
                  },
                  {
                    name: "idle_waste",
                    value: summary.estimated_idle_waste_usd.toFixed(2),
                    unit: "USD",
                    source: "usage_snapshots",
                  },
                ],
                assumptions: ["Idle waste derived from expected vs actual usage."],
              },
            });
          } else {
            setExplain(null);
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load utilization.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [startDate, endDate]);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Utilization</p>
          <div className="flex items-center gap-2">
            <h3 className="mt-1 text-lg font-semibold text-slate-900">GPU Usage Efficiency</h3>
            {explain && <MetricExplainDrawer title="GPU Usage Efficiency" metric={explain} />}
          </div>
        </div>
        <div className="rounded-lg bg-slate-100 p-2 text-slate-600">
          <Gauge className="h-4 w-4" />
        </div>
      </div>

      {loading ? (
        <div className="mt-6 space-y-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-2 w-full" />
        </div>
      ) : error ? (
        <p className="mt-6 text-sm text-rose-600">{error}</p>
      ) : utilization === null ? (
        <p className="mt-6 text-sm text-slate-500">
          No utilization data yet. Ingest usage snapshots to unlock efficiency insights.
        </p>
      ) : (
        <div className="mt-6">
          <div className="flex items-baseline justify-between text-sm text-slate-500">
            <span>Estimated utilization</span>
            <span className="text-lg font-semibold text-slate-900">
              {utilization.toFixed(0)}%
            </span>
          </div>
          <div className="mt-3 h-2 rounded-full bg-slate-100">
            <div
              className="h-2 rounded-full bg-blue-500"
              style={{ width: `${utilization}%` }}
            />
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Based on idle waste vs. total spend.
          </p>
        </div>
      )}
    </div>
  );
}
