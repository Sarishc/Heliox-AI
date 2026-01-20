"use client";

import { Grid3X3 } from "lucide-react";

export default function UtilizationHeatmap() {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Utilization Heatmap</p>
          <h3 className="mt-1 text-lg font-semibold text-slate-900">
            GPU Hotspots by Hour
          </h3>
        </div>
        <div className="rounded-lg bg-slate-100 p-2 text-slate-600">
          <Grid3X3 className="h-4 w-4" />
        </div>
      </div>
      <div className="mt-6 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
        Ingest GPU utilization telemetry to unlock the heatmap view.
      </div>
    </div>
  );
}
