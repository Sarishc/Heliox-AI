"use client";

import { useState } from "react";
import { Info } from "lucide-react";

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

const confidenceLabel = (score: number) => {
  if (score >= 0.8) return { label: "High", tone: "bg-emerald-100 text-emerald-700" };
  if (score >= 0.6) return { label: "Medium", tone: "bg-amber-100 text-amber-700" };
  return { label: "Low", tone: "bg-rose-100 text-rose-700" };
};

export default function MetricExplainDrawer({
  title,
  metric,
}: {
  title: string;
  metric: MetricExplain;
}) {
  const [open, setOpen] = useState(false);
  const confidence = confidenceLabel(metric.confidence);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700"
        type="button"
      >
        <Info className="h-3.5 w-3.5" />
        Explain
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="w-full max-w-xl rounded-2xl bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
              <div>
                <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
                <p className="text-xs text-slate-500">Window: {metric.window}</p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-sm text-slate-500 hover:text-slate-700"
                type="button"
              >
                Close
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div className="flex items-center justify-between text-sm">
                <div>
                  <span className="text-slate-500">Confidence</span>
                </div>
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${confidence.tone}`}>
                  {confidence.label} ({metric.confidence.toFixed(2)})
                </span>
              </div>
              {metric.confidence_reasons.length > 0 && (
                <div className="text-xs text-slate-500">
                  Reasons: {metric.confidence_reasons.join(", ")}
                </div>
              )}
              <div>
                <p className="text-sm font-semibold text-slate-900">Formula</p>
                <p className="text-sm text-slate-600">{metric.explanation.formula}</p>
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-900">Inputs</p>
                <ul className="mt-2 space-y-1 text-sm text-slate-600">
                  {metric.explanation.components.map((component) => (
                    <li key={component.name}>
                      {component.name}: {component.value} {component.unit ?? ""}
                      {component.source ? ` (${component.source})` : ""}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-900">Assumptions</p>
                <ul className="mt-2 space-y-1 text-sm text-slate-600">
                  {metric.explanation.assumptions.map((assumption) => (
                    <li key={assumption}>{assumption}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
