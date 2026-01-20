"use client";

import BetaAccessGate from "@/components/BetaAccessGate";
import AppShell from "@/components/AppShell";
import CostByModelChart from "@/components/CostByModelChart";
import CostByTeamChart from "@/components/CostByTeamChart";
import UtilizationHeatmap from "@/components/UtilizationHeatmap";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";

function AnalyticsContent() {
  const { startDate, endDate } = useDashboardFilters();

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Analytics</p>
        <h1 className="text-2xl font-semibold text-slate-900">Spend breakdowns</h1>
        <p className="mt-2 text-sm text-slate-500">
          Drill into model, team, and utilization patterns across the selected window.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <select className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
          <option>Sort by spend</option>
          <option>Sort by job count</option>
          <option>Sort by utilization</option>
        </select>
        <select className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
          <option>Filter: All providers</option>
          <option>AWS</option>
          <option>GCP</option>
          <option>On-prem</option>
        </select>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Cost by Model</h2>
          <CostByModelChart startDate={startDate} endDate={endDate} />
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Cost by Team</h2>
          <CostByTeamChart startDate={startDate} endDate={endDate} />
        </div>
      </div>

      <UtilizationHeatmap />
    </div>
  );
}

export default function AnalyticsPage() {
  return (
    <BetaAccessGate>
      <AppShell>
        <AnalyticsContent />
      </AppShell>
    </BetaAccessGate>
  );
}
