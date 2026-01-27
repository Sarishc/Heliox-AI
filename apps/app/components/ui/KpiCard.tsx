import { ReactNode } from "react";
import MetricExplainDrawer from "@/components/ui/MetricExplainDrawer";

interface KpiCardProps {
  label: string;
  value: string;
  change?: string;
  icon?: ReactNode;
  helper?: string;
  explain?: {
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
  };
}

export default function KpiCard({ label, value, change, icon, helper, explain }: KpiCardProps) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
            {explain && <MetricExplainDrawer title={label} metric={explain} />}
          </div>
          <p className="mt-2 text-2xl font-semibold text-slate-900">{value}</p>
          {change && <p className="mt-1 text-xs text-emerald-600">{change}</p>}
        </div>
        {icon && <div className="rounded-lg bg-slate-100 p-2 text-slate-600">{icon}</div>}
      </div>
      {helper && <p className="mt-3 text-xs text-slate-500">{helper}</p>}
    </div>
  );
}
