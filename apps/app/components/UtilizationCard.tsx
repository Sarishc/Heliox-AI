"use client";

import { useEffect, useState } from "react";
import { Gauge } from "lucide-react";
import { fetchJson } from "@/lib/api";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";
import Skeleton from "@/components/ui/Skeleton";

interface SavingsSummaryResponse {
  total_spend_usd: number;
  estimated_idle_waste_usd: number;
}

export default function UtilizationCard() {
  const { startDate, endDate } = useDashboardFilters();
  const [utilization, setUtilization] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const summary = await fetchJson<SavingsSummaryResponse>(
          `/api/v1/analytics/savings/summary?start=${startDate}&end=${endDate}`
        );
        if (summary.total_spend_usd <= 0) {
          setUtilization(null);
        } else {
          const wasteRatio = summary.estimated_idle_waste_usd / summary.total_spend_usd;
          const utilizationPct = Math.max(0, Math.min(1, 1 - wasteRatio)) * 100;
          setUtilization(utilizationPct);
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
          <h3 className="mt-1 text-lg font-semibold text-slate-900">GPU Usage Efficiency</h3>
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
