"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Loader2, ShieldAlert } from "lucide-react";
import { fetchJson } from "@/lib/api";

interface AnomalyItem {
  type: string;
  message: string;
  severity: string;
  probability?: number;
  value?: number;
  baseline_mean?: number;
  baseline_std?: number;
}

interface AnomalyResponse {
  anomalies: AnomalyItem[];
  breach_probability: number;
  projected_monthly_spend: number;
  budget_usd_monthly?: number | null;
}

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
        const response = await fetchJson<AnomalyResponse>("/api/v1/anomalies");
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
          <h2 className="text-lg font-semibold text-slate-900">Anomaly Alerts</h2>
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
                    <span className="text-xs text-slate-500">
                      {item.severity}
                    </span>
                  </div>
                  <p className="text-slate-600 mt-1">{item.message}</p>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
