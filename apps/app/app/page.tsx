"use client";

import BetaAccessGate from "@/components/BetaAccessGate";
import AppShell from "@/components/AppShell";
import ExecutiveKpis from "@/components/ExecutiveKpis";
import SpendTrendChart from "@/components/SpendTrendChart";
import CostByModelChart from "@/components/CostByModelChart";
import CostByTeamChart from "@/components/CostByTeamChart";
import ForecastCard from "@/components/ForecastCard";
import AnomalyCard from "@/components/AnomalyCard";
import UtilizationCard from "@/components/UtilizationCard";
import CostEfficiencyCard from "@/components/CostEfficiencyCard";
import BudgetStatusCard from "@/components/BudgetStatusCard";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";

function DashboardContent() {
  const { startDate, endDate } = useDashboardFilters();

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">
          Executive overview
        </p>
        <h1 className="text-2xl font-semibold text-slate-900">
          GPU Cost Command Center
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Monitor spend, efficiency, and savings opportunities in one view.
        </p>
      </div>

      <ExecutiveKpis />

      <div className="grid gap-6 md:grid-cols-2">
        <BudgetStatusCard />
        <CostEfficiencyCard />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Spend vs budget
            </p>
            <h2 className="text-lg font-semibold text-slate-900">
              Daily Spend Trend
            </h2>
          </div>
          <SpendTrendChart startDate={startDate} endDate={endDate} />
        </div>
        <UtilizationCard />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <AnomalyCard />
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-2">
            Cost efficiency notes
          </h2>
          <p className="text-sm text-slate-500">
            Pair business KPIs with cost data to surface ROI signals per GPU dollar.
          </p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">
            Cost by ML Model
          </h2>
          <CostByModelChart startDate={startDate} endDate={endDate} />
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">
            Cost by Team
          </h2>
          <CostByTeamChart startDate={startDate} endDate={endDate} />
        </div>
      </div>

      <ForecastCard />
    </div>
  );
}

export default function Dashboard() {
  return (
    <BetaAccessGate>
      <AppShell>
        <DashboardContent />
      </AppShell>
    </BetaAccessGate>
  );
}
