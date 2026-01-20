"use client";

import BetaAccessGate from "@/components/BetaAccessGate";
import AppShell from "@/components/AppShell";
import ForecastCard from "@/components/ForecastCard";
import CapacityRiskCard from "@/components/CapacityRiskCard";

function ForecastContent() {
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Forecast</p>
        <h1 className="text-2xl font-semibold text-slate-900">
          Spend and capacity outlook
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Projection bands and risk signals for upcoming GPU demand.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
        <ForecastCard />
        <CapacityRiskCard />
      </div>
    </div>
  );
}

export default function ForecastPage() {
  return (
    <BetaAccessGate>
      <AppShell>
        <ForecastContent />
      </AppShell>
    </BetaAccessGate>
  );
}
