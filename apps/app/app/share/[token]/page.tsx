"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

interface SharedReportResponse {
  id: string;
  name: string;
  description?: string | null;
  generated_at?: string | null;
  config: {
    start_date: string;
    end_date: string;
    sections: string[];
  };
  data: Record<string, any>;
}

export default function SharedReportPage({ params }: { params: { token: string } }) {
  const [report, setReport] = useState<SharedReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadReport = async () => {
      try {
        const response = await fetch(getApiUrl(`/share/${params.token}`));
        if (!response.ok) {
          setError("This share link is unavailable.");
          return;
        }
        const payload = (await response.json()) as SharedReportResponse;
        setReport(payload);
      } catch {
        setError("Unable to load shared report.");
      }
    };
    loadReport();
  }, [params.token]);

  if (error) {
    return (
      <div className="min-h-screen bg-slate-50 px-6 py-16 text-center">
        <h1 className="text-2xl font-semibold text-slate-900">Report unavailable</h1>
        <p className="mt-2 text-sm text-slate-500">{error}</p>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="min-h-screen bg-slate-50 px-6 py-16 text-center text-sm text-slate-500">
        Loading report...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 px-6 py-10">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-xs uppercase tracking-wide text-slate-500">Shared report</p>
          <h1 className="text-2xl font-semibold text-slate-900">{report.name}</h1>
          {report.description && (
            <p className="mt-2 text-sm text-slate-500">{report.description}</p>
          )}
          <div className="mt-4 text-xs text-slate-500">
            {report.config.start_date} to {report.config.end_date}
          </div>
        </div>

        {report.data.overview_kpis && (
          <div className="grid gap-4 md:grid-cols-3">
            {Object.entries(report.data.overview_kpis).map(([key, value]) => (
              <div
                key={key}
                className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <p className="text-xs uppercase tracking-wide text-slate-500">
                  {key.replace(/_/g, " ")}
                </p>
                <p className="mt-2 text-lg font-semibold text-slate-900">{value}</p>
              </div>
            ))}
          </div>
        )}

        {report.data.daily_spend && (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">Daily Spend</h2>
            <div className="mt-4 space-y-2 text-sm text-slate-600">
              {report.data.daily_spend.map((row: any) => (
                <div key={row.date} className="flex justify-between">
                  <span>{row.date}</span>
                  <span>${row.spend_usd}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {report.data.top_models && (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">Top Models</h2>
            <div className="mt-4 space-y-2 text-sm text-slate-600">
              {report.data.top_models.map((row: any) => (
                <div key={row.model_name} className="flex justify-between">
                  <span>{row.model_name}</span>
                  <span>${row.total_cost_usd}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {report.data.top_recommendations && (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">Top Recommendations</h2>
            <div className="mt-4 space-y-3 text-sm text-slate-600">
              {report.data.top_recommendations.map((row: any) => (
                <div key={row.title} className="rounded-lg border border-slate-200 p-3">
                  <p className="font-medium text-slate-800">{row.title}</p>
                  <p className="text-xs text-slate-500">
                    {row.type} • ${row.estimated_savings_usd}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
