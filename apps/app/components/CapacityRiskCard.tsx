"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Server } from "lucide-react";
import { fetchJson } from "@/lib/api";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";
import Skeleton from "@/components/ui/Skeleton";

interface ScheduleForecastResponse {
  required_gpus: number;
  utilization_projection: number;
  congestion_probability: number;
}

export default function CapacityRiskCard() {
  const { startDate, endDate } = useDashboardFilters();
  const [data, setData] = useState<ScheduleForecastResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchJson<ScheduleForecastResponse>(
          `/api/v1/schedule/forecast?start_date=${startDate}&end_date=${endDate}`
        );
        setData(response);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load capacity risk.");
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
          <p className="text-xs uppercase tracking-wide text-slate-500">Capacity risk</p>
          <h3 className="mt-1 text-lg font-semibold text-slate-900">
            Scheduling pressure
          </h3>
        </div>
        <div className="rounded-lg bg-slate-100 p-2 text-slate-600">
          <Server className="h-4 w-4" />
        </div>
      </div>

      {loading ? (
        <div className="mt-6 space-y-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-6 w-32" />
        </div>
      ) : error ? (
        <p className="mt-6 text-sm text-rose-600">{error}</p>
      ) : data ? (
        <div className="mt-6 space-y-3">
          <div className="flex items-center justify-between text-sm text-slate-600">
            <span>Required GPUs</span>
            <span className="text-base font-semibold text-slate-900">
              {data.required_gpus}
            </span>
          </div>
          <div className="flex items-center justify-between text-sm text-slate-600">
            <span>Utilization projection</span>
            <span className="text-base font-semibold text-slate-900">
              {(data.utilization_projection * 100).toFixed(0)}%
            </span>
          </div>
          <div className="flex items-center justify-between text-sm text-slate-600">
            <span>Congestion probability</span>
            <span className="inline-flex items-center gap-2 text-base font-semibold text-slate-900">
              {(data.congestion_probability * 100).toFixed(0)}%
              {data.congestion_probability > 0.6 && (
                <AlertTriangle className="h-4 w-4 text-rose-500" />
              )}
            </span>
          </div>
        </div>
      ) : (
        <p className="mt-6 text-sm text-slate-500">
          No scheduling forecast available for the selected window.
        </p>
      )}
    </div>
  );
}
