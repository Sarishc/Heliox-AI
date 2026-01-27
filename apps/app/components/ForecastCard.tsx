"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  TrendingUp,
  Calendar,
  AlertCircle,
  Sparkles,
  Loader2,
  Wallet,
} from "lucide-react";
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  AreaChart,
  ReferenceArea,
} from "recharts";

interface ForecastData {
  provider: string | null;
  gpu_type: string | null;
  horizon_days: number;
  forecast_method: string;
  historical: Array<{ date: string; value: number }>;
  forecast: Array<{
    date: string;
    value: number;
    lower_bound: number;
    upper_bound: number;
  }>;
  metadata: {
    historical_data_points: number;
    forecast_generated_at: string;
  };
  explain?: MetricExplain;
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

import { fetchJson, getApiBaseUrl } from "@/lib/api";
import MetricExplainDrawer from "@/components/ui/MetricExplainDrawer";

const formatLabel = (value: string) => {
  const date = new Date(value);
  return `${date.getMonth() + 1}/${date.getDate()}`;
};

const RUNWAY_EXPAND_FLAG = "heliox_runway_expand_after_budget";

interface RunwayBreakdownItem {
  job_type: string;
  model_name: string;
  environment: string;
  total_cost: number;
  share_of_total: number;
}

interface RunwayResponse {
  monthly_burn: number;
  runway_days: number | null;
  budget_risk_score: number;
  forecast_method: string;
  budget_usd_monthly: number;
  breakdown: RunwayBreakdownItem[];
}

const formatCurrency = (value: number) =>
  `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

export default function ForecastCard() {
  const apiBaseUrl = getApiBaseUrl();
  const [forecastData, setForecastData] = useState<ForecastData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [horizonDays, setHorizonDays] = useState(7);
  const [runway, setRunway] = useState<RunwayResponse | null>(null);
  const [runwayError, setRunwayError] = useState<string | null>(null);
  const [topN, setTopN] = useState<number | "all">("all");
  const [runwayExpanded, setRunwayExpanded] = useState(false);
  const [budgetMissing, setBudgetMissing] = useState(false);

  useEffect(() => {
    fetchForecast();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [horizonDays]);

  useEffect(() => {
    if (!runwayExpanded) {
      return;
    }
    fetchRunway();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topN, runwayExpanded]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const shouldExpand = localStorage.getItem(RUNWAY_EXPAND_FLAG);
    if (shouldExpand) {
      localStorage.removeItem(RUNWAY_EXPAND_FLAG);
      setRunwayExpanded(true);
    }
  }, []);

  const fetchForecast = async () => {
    setLoading(true);
    setError(null);

    try {
      const url = `/api/v1/forecast/spend?horizon_days=${horizonDays}&include_explain=true`;
      const data = await fetchJson<ForecastData>(url);
      setForecastData(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load forecast. Please try again later."
      );
      setForecastData(null);
    } finally {
      setLoading(false);
    }
  };

  const fetchRunway = async () => {
    setRunwayError(null);
    try {
      const topParam = topN === "all" ? "" : `&top_n=${topN}`;
      const data = await fetchJson<RunwayResponse>(
        `/api/v1/finance/runway?method=ets${topParam}`
      );
      setRunway(data);
      setBudgetMissing(false);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Unable to load runway forecast. Set a team budget first.";
      setRunway(null);
      setRunwayError(message);
      setBudgetMissing(message.toLowerCase().includes("budget"));
    }
  };

  const chartData = useMemo(() => {
    if (!forecastData) return [];

    const historical = forecastData.historical.slice(-14).map((point) => ({
      label: formatLabel(point.date),
      date: point.date,
      historical: point.value,
      forecast: null,
      lower: null,
      upper: null,
      segment: "historical",
    }));

    const forecast = forecastData.forecast.map((point) => ({
      label: formatLabel(point.date),
      date: point.date,
      historical: null,
      forecast: point.value,
      lower: point.lower_bound,
      upper: point.upper_bound,
      segment: "forecast",
    }));

    return [...historical, ...forecast];
  }, [forecastData]);

  const forecastStartLabel = forecastData?.forecast?.[0]
    ? formatLabel(forecastData.forecast[0].date)
    : undefined;
  const forecastEndLabel = forecastData?.forecast?.[forecastData.forecast.length - 1]
    ? formatLabel(forecastData.forecast[forecastData.forecast.length - 1].date)
    : undefined;

  const hasData =
    chartData.length > 0 &&
    (forecastData?.historical.length || 0) > 0 &&
    (forecastData?.forecast.length || 0) > 0;

  const nextWeekForecast =
    forecastData?.forecast[
      Math.min(6, Math.max(0, (forecastData?.forecast.length || 1) - 1))
    ]?.value;

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-purple-100 rounded-lg">
            <TrendingUp className="w-5 h-5 text-purple-600" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-purple-600" />
              <p className="text-xs font-semibold text-purple-700 uppercase tracking-wide">
                Historical vs. Forecast
              </p>
              {forecastData?.explain && (
                <MetricExplainDrawer
                  title="Forecasted spend"
                  metric={forecastData.explain}
                />
              )}
            </div>
            <h2 className="text-lg font-semibold text-gray-900">
              Cost Forecasting
            </h2>
            <p className="text-sm text-gray-500">
              {loading ? "Loading..." : `${horizonDays}-day prediction`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {[7, 14, 30].map((days) => (
            <button
              key={days}
              onClick={() => setHorizonDays(days)}
              className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${
                horizonDays === days
                  ? "bg-purple-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {days}d
            </button>
          ))}
          <button
            onClick={fetchForecast}
            className="px-3 py-1.5 rounded-lg text-sm font-medium border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="flex items-center gap-2 text-purple-700">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span>Loading forecast...</span>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-6 h-6 text-red-600 flex-shrink-0" />
            <div>
              <h3 className="text-lg font-semibold text-red-900 mb-1">
                Error Loading Forecast
              </h3>
              <p className="text-red-700">{error}</p>
              <button
                onClick={fetchForecast}
                className="mt-3 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
              >
                Try Again
              </button>
            </div>
          </div>
        </div>
      )}

      {!loading && !error && !hasData && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
          <p className="text-gray-700 font-medium mb-2">
            No forecast data available
          </p>
          <p className="text-sm text-gray-500">
            Generate historical usage first, then retry.
          </p>
          <button
            onClick={fetchForecast}
            className="mt-4 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && hasData && forecastData && (
        <>
          <div className="mb-6">
            <div className="flex items-center gap-2 text-sm text-gray-600 mb-2">
              <Calendar className="w-4 h-4" />
              <span>
                Updated {new Date(forecastData.metadata.forecast_generated_at).toLocaleDateString()}
              </span>
            </div>
            <ResponsiveContainer width="100%" height={320}>
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient
                    id="confidenceGradient"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop offset="5%" stopColor="#c084fc" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#c084fc" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 12 }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "white",
                    border: "1px solid #e5e7eb",
                    borderRadius: "0.5rem",
                  }}
                  formatter={(value: unknown, name?: string) => {
                    const label = name ?? "Value";
                    if (value === null || value === undefined) {
                      return ["N/A", label];
                    }
                    return [`$${Number(value).toLocaleString()}`, label];
                  }}
                  labelFormatter={(label) => `Date: ${label}`}
                />
                <Legend />

                {forecastStartLabel && forecastEndLabel && (
                  <ReferenceArea
                    x1={forecastStartLabel}
                    x2={forecastEndLabel}
                    fill="#f5f3ff"
                    fillOpacity={0.6}
                    stroke="#c4b5fd"
                    strokeOpacity={0.4}
                  />
                )}

                <Area
                  type="monotone"
                  dataKey="upper"
                  stroke="none"
                  fill="url(#confidenceGradient)"
                  name="Confidence Upper"
                  activeDot={false}
                  connectNulls
                />
                <Area
                  type="monotone"
                  dataKey="lower"
                  stroke="none"
                  fill="white"
                  name="Confidence Lower"
                  activeDot={false}
                  connectNulls
                />

                <Line
                  type="monotone"
                  dataKey="historical"
                  stroke="#7c3aed"
                  strokeWidth={3}
                  dot={{ r: 4 }}
                  name="Historical"
                  connectNulls
                />

                <Line
                  type="monotone"
                  dataKey="forecast"
                  stroke="#c084fc"
                  strokeWidth={3}
                  strokeDasharray="5 5"
                  dot={{ r: 4 }}
                  name="Forecast"
                  connectNulls
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="p-3 bg-purple-50 rounded-lg">
              <p className="text-xs text-purple-600 font-medium mb-1">Method</p>
              <p className="text-sm font-semibold text-gray-900">
                {forecastData.forecast_method === "moving_average"
                  ? "Moving Avg"
                  : "LightGBM"}
              </p>
            </div>

            <div className="p-3 bg-purple-50 rounded-lg">
              <p className="text-xs text-purple-600 font-medium mb-1">
                Data Points
              </p>
              <p className="text-sm font-semibold text-gray-900">
                {forecastData.metadata.historical_data_points}
              </p>
            </div>

            <div className="p-3 bg-purple-50 rounded-lg">
              <p className="text-xs text-purple-600 font-medium mb-1">
                Last Value
              </p>
              <p className="text-sm font-semibold text-gray-900">
                $
                {forecastData.historical[
                  forecastData.historical.length - 1
                ]?.value.toLocaleString()}
              </p>
            </div>

            <div className="p-3 bg-purple-50 rounded-lg">
              <p className="text-xs text-purple-600 font-medium mb-1">
                Forecast (Day {horizonDays})
              </p>
              <p className="text-sm font-semibold text-gray-900">
                $
                {nextWeekForecast?.toLocaleString(undefined, {
                  maximumFractionDigits: 0,
                }) ?? "—"}
              </p>
            </div>
          </div>

          <div className="text-center">
            <p className="text-sm text-gray-600">
              View{" "}
              <a
                href={`${apiBaseUrl}/docs`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-purple-600 hover:text-purple-700 font-medium"
              >
                API docs
              </a>{" "}
              for more options
            </p>
          </div>

          <div className="mt-8 border-t border-gray-200 pt-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
              <div className="flex items-center gap-2">
                <Wallet className="w-4 h-4 text-emerald-600" />
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-gray-900">
                      Runway Forecast
                    </p>
                    {runway && !runwayError && !budgetMissing && (
                      <span className="text-xs text-gray-400">
                        {`${formatCurrency(runway.budget_usd_monthly)}/mo`}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500">
                    Budget burn and top cost drivers
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <button
                  onClick={() => setRunwayExpanded((prev) => !prev)}
                  className="px-3 py-1 border border-gray-200 rounded-md text-xs text-gray-600 hover:bg-gray-50"
                >
                  {runwayExpanded ? "Hide runway" : "Show runway"}
                </button>
                {runwayExpanded && !budgetMissing && (
                  <div className="flex items-center gap-2">
                    <span>Top items</span>
                    <select
                      value={topN}
                      onChange={(e) =>
                        setTopN(
                          e.target.value === "all" ? "all" : Number(e.target.value)
                        )
                      }
                      className="border border-gray-200 rounded-md text-xs px-2 py-1"
                    >
                      <option value="all">All</option>
                      <option value="3">3</option>
                      <option value="5">5</option>
                      <option value="10">10</option>
                    </select>
                  </div>
                )}
              </div>
            </div>

            {runwayExpanded && budgetMissing && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-700 mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <span>Set a monthly budget to enable runway forecasts.</span>
                <Link
                  href="/settings"
                  className="inline-flex items-center justify-center px-3 py-1.5 rounded-md bg-amber-100 text-amber-800 text-xs font-medium hover:bg-amber-200"
                >
                  Set budget in Settings
                </Link>
              </div>
            )}

            {runwayExpanded && runwayError && !budgetMissing && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700 mb-4">
                {runwayError}
              </div>
            )}

            {runwayExpanded && !runwayError && runway && (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
                  <div className="border border-gray-200 rounded-md p-3">
                    <p className="text-xs text-gray-500">Monthly burn</p>
                    <p className="text-lg font-semibold text-gray-900">
                      {formatCurrency(runway.monthly_burn)}
                    </p>
                  </div>
                  <div className="border border-gray-200 rounded-md p-3">
                    <p className="text-xs text-gray-500">Runway</p>
                    <p className="text-lg font-semibold text-gray-900">
                      {runway.runway_days !== null
                        ? `${runway.runway_days} days`
                        : "Not available"}
                    </p>
                  </div>
                  <div className="border border-gray-200 rounded-md p-3">
                    <p className="text-xs text-gray-500">Budget risk</p>
                    <p className="text-lg font-semibold text-gray-900">
                      {(runway.budget_risk_score * 100).toFixed(0)}%
                    </p>
                  </div>
                </div>

                {runway.breakdown.length === 0 ? (
                  <p className="text-sm text-gray-500">
                    No job breakdown available for this period.
                  </p>
                ) : (
                  <div className="space-y-2 text-sm">
                    {runway.breakdown.map((item) => (
                      <div
                        key={`${item.job_type}-${item.model_name}-${item.environment}`}
                        className="flex items-center justify-between border border-gray-200 rounded-md px-3 py-2"
                      >
                        <div>
                          <div className="font-medium text-gray-900">
                            {item.job_type} • {item.model_name}
                          </div>
                          <div className="text-gray-500">{item.environment}</div>
                        </div>
                        <div className="text-right">
                          <div className="font-medium text-gray-900">
                            {formatCurrency(item.total_cost)}
                          </div>
                          <div className="text-gray-500">
                            {(item.share_of_total * 100).toFixed(1)}%
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

