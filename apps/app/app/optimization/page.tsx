"use client";

import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import OptimizationActions from "@/components/OptimizationActions";

function OptimizationContent() {
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Optimization</p>
        <h1 className="text-2xl font-semibold text-slate-900">
          Ranked savings opportunities
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Prioritized recommendations with ROI and risk clarity.
        </p>
      </div>

      <OptimizationActions />
    </div>
  );
}

export default function OptimizationPage() {
  return (
    <EnterpriseLayout>
      <OptimizationContent />
    </EnterpriseLayout>
  );
}
