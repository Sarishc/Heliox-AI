"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Loader2, ShieldAlert, Info } from "lucide-react";
import { fetchJson } from "@/lib/api";
import MetricExplainDrawer from "@/components/ui/MetricExplainDrawer";

interface AnomalyItem {
  type: string;
  message: string;
  severity: string;
  probability?: number;
  value?: number;
  baseline_mean?: number;
  baseline_std?: number;
  baseline_window_days?: number;
  spike_std_multiplier?: number;
}

interface AnomalyResponse {
  anomalies: AnomalyItem[];
  breach_probability: number;
  projected_monthly_spend: number;
  budget_usd_monthly?: number | null;
  breach_probability_explain?: MetricExplain;
  point_explain?: Record<string, MetricExplain>;
}

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

const confidenceBadge = (score: number) => {
  if (score >= 0.8) return { label: "High", classes: "bg-emerald-100 text-emerald-700" };
  if (score >= 0.6) return { label: "Med", classes: "bg-amber-100 text-amber-700" };
  return { label: "Low", classes: "bg-rose-100 text-rose-700" };
};

const formatCurrency = (value: number) =>
  `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

export default function AnomalyCard() {
  const [data, setData] = useState<AnomalyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchJson<AnomalyResponse>("/api/v1/anomalies?include_explain=true");
        setData(response);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load anomalies. Please try again."
        );
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 bg-rose-100 rounded-lg">
          <ShieldAlert className="w-5 h-5 text-rose-600" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-slate-900">Anomaly Alerts</h2>
            {data?.breach_probability_explain && (
              <MetricExplainDrawer
                title="Budget breach risk"
                metric={data.breach_probability_explain}
              />
            )}
          </div>
          <p className="text-sm text-slate-500">
            Early warnings on abnormal spend or utilization
          </p>
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-rose-700">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Loading anomalies...</span>
        </div>
      )}

      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-lg p-4 text-sm text-rose-700">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4" />
            <span>{error}</span>
          </div>
        </div>
      )}

      {!loading && !error && data && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            <div className="border border-slate-200 rounded-lg p-3">
              <p className="text-xs text-slate-500">Projected monthly spend</p>
              <p className="text-lg font-semibold text-slate-900">
                {formatCurrency(data.projected_monthly_spend)}
              </p>
            </div>
            <div className="border border-slate-200 rounded-lg p-3">
              <p className="text-xs text-slate-500">Budget breach risk</p>
              <p className="text-lg font-semibold text-slate-900">
                {(data.breach_probability * 100).toFixed(0)}%
              </p>
            </div>
            <div className="border border-slate-200 rounded-lg p-3">
              <p className="text-xs text-slate-500">Budget</p>
              <p className="text-lg font-semibold text-slate-900">
                {data.budget_usd_monthly
                  ? `${formatCurrency(data.budget_usd_monthly)}/mo`
                  : "Not set"}
              </p>
            </div>
          </div>

          {data.anomalies.length === 0 ? (
            <p className="text-sm text-slate-500">
              No anomalies detected in the current window.
            </p>
          ) : (
            <div className="space-y-2 text-sm">
              {data.anomalies.map((item, idx) => (
                <div
                  key={`${item.type}-${idx}`}
                  className="border border-slate-200 rounded-lg p-3"
                >
                  <div className="flex items-center justify-between">
                    <p className="font-medium text-slate-900">{item.type}</p>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      {data.point_explain?.[item.type] && (
                        <span
                          className={`rounded-full px-2 py-0.5 font-semibold ${
                            confidenceBadge(data.point_explain[item.type].confidence).classes
                          }`}
                        >
                          {confidenceBadge(data.point_explain[item.type].confidence).label}
                        </span>
                      )}
                      <span>{item.severity}</span>
                    </div>
                  </div>
                  <p className="text-slate-600 mt-1">{item.message}</p>
                  {data.point_explain?.[item.type] && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                      <span className="relative group inline-flex items-center gap-1 cursor-default">
                        <Info className="h-3.5 w-3.5 text-slate-400" />
                        <span>Explain</span>
                        <span className="absolute left-0 top-6 z-10 hidden w-64 rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600 shadow-lg group-hover:block">
                          <span className="font-semibold text-slate-700">Formula:</span>{" "}
                          {data.point_explain[item.type].explanation.formula}
                          <div className="mt-2">
                            <span className="font-semibold text-slate-700">Inputs:</span>
                            <div className="mt-1 border border-slate-200 rounded-md overflow-hidden">
                              {data.point_explain[item.type].explanation.components.map((component, index) => (
                                <div
                                  key={component.name}
                                  className={`flex items-center justify-between px-2 py-1 ${
                                    index % 2 === 0 ? "bg-slate-50" : "bg-white"
                                  }`}
                                >
                                  <span className="truncate">{component.name}</span>
                                  <span className="ml-2 text-slate-700">
                                    {component.value}
                                    {component.unit ? ` ${component.unit}` : ""}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                          <div className="mt-2">
                            <span className="font-semibold text-slate-700">Assumptions:</span>
                            <div className="mt-1 border border-slate-200 rounded-md overflow-hidden">
                              {data.point_explain[item.type].explanation.assumptions.map((assumption, index) => (
                                <div
                                  key={assumption}
                                  className={`px-2 py-1 ${
                                    index % 2 === 0 ? "bg-slate-50" : "bg-white"
                                  }`}
                                >
                                  {assumption}
                                </div>
                              ))}
                            </div>
                          </div>
                        </span>
                      </span>
                    </div>
                  )}
                  {(item.baseline_mean !== undefined || item.baseline_std !== undefined) && (
                    <p className="text-xs text-slate-500 mt-2">
                      Baseline μ={item.baseline_mean?.toFixed(2) ?? "—"}, σ={item.baseline_std?.toFixed(2) ?? "—"}
                      {item.baseline_window_days ? ` over ${item.baseline_window_days}d` : ""}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
