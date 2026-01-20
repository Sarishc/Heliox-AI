import { ReactNode } from "react";

interface KpiCardProps {
  label: string;
  value: string;
  change?: string;
  icon?: ReactNode;
  helper?: string;
}

export default function KpiCard({ label, value, change, icon, helper }: KpiCardProps) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">{value}</p>
          {change && <p className="mt-1 text-xs text-emerald-600">{change}</p>}
        </div>
        {icon && <div className="rounded-lg bg-slate-100 p-2 text-slate-600">{icon}</div>}
      </div>
      {helper && <p className="mt-3 text-xs text-slate-500">{helper}</p>}
    </div>
  );
}
