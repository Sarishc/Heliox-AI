"use client";

import { useEffect, useState } from "react";
import { Wallet, TrendingDown, TrendingUp, Sparkles } from "lucide-react";
import { fetchJson } from "@/lib/api";
import { useDashboardFilters } from "@/components/DashboardFiltersContext";
import KpiCard from "@/components/ui/KpiCard";
import Skeleton from "@/components/ui/Skeleton";

interface SavingsSummaryResponse {
  start_date: string;
  end_date: string;
  total_spend_usd: number;
  estimated_idle_waste_usd: number;
  recommended_savings_usd: number;
}

interface ForecastResponse {
  forecast: Array<{ date: string; value: number }>;
}

const formatCurrency = (value: number) =>
  `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

export default function ExecutiveKpis() {
  const { startDate, endDate } = useDashboardFilters();
  const [summary, setSummary] = useState<SavingsSummaryResponse | null>(null);
  const [nextMonthSpend, setNextMonthSpend] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchKpis = async () => {
      setLoading(true);
      setError(null);
      try {
        const summaryResponse = await fetchJson<SavingsSummaryResponse>(
          `/api/v1/analytics/savings/summary?start=${startDate}&end=${endDate}`
        );
        setSummary(summaryResponse);

        const forecast = await fetchJson<ForecastResponse>(
          `/api/v1/forecast/spend?horizon_days=30`
        );
        const totalForecast = forecast.forecast.reduce(
          (acc, point) => acc + point.value,
          0
        );
        setNextMonthSpend(totalForecast);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Unable to load KPI summary."
        );
      } finally {
        setLoading(false);
      }
    };

    fetchKpis();
  }, [startDate, endDate]);

  if (loading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="rounded-2xl border border-slate-200 bg-white px-5 py-4">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="mt-3 h-7 w-32" />
            <Skeleton className="mt-4 h-3 w-24" />
          </div>
        ))}
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">
        {error ?? "Unable to load KPI summary. Please try again later."}
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <KpiCard
        label="Current Period Spend"
        value={formatCurrency(summary.total_spend_usd)}
        helper="Tracked spend for selected window."
        icon={<Wallet className="h-4 w-4" />}
      />
      <KpiCard
        label="Idle Waste"
        value={formatCurrency(summary.estimated_idle_waste_usd)}
        helper="Estimated spend on idle capacity."
        icon={<TrendingDown className="h-4 w-4" />}
      />
      <KpiCard
        label="Forecasted Next-Month Spend"
        value={nextMonthSpend ? formatCurrency(nextMonthSpend) : "—"}
        helper="Model-based projection for next 30 days."
        icon={<TrendingUp className="h-4 w-4" />}
      />
      <KpiCard
        label="Savings Opportunity"
        value={formatCurrency(summary.recommended_savings_usd)}
        helper="Estimated savings from top actions."
        icon={<Sparkles className="h-4 w-4" />}
      />
    </div>
  );
}
