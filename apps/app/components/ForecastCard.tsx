"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  TrendingUp,
  Calendar,
  Sparkles,
  Loader2,
  Wallet,
  BarChart3,
  ArrowRight,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
  ReferenceArea,
} from "recharts";

interface ForecastData {
  error?: string;
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
}

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

import { fetchJson, getApiBaseUrl } from "@/lib/api";
import MetricExplainDrawer from "@/components/ui/MetricExplainDrawer";
import { isDemoMode, generateDemoForecastApiResponse } from "@/lib/demoData";

const formatLabel = (value: string) => {
  const date = new Date(value);
  return `${date.getMonth() + 1}/${date.getDate()}`;
};

const formatCurrency = (value: number) =>
  `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

const CustomForecastTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const historical = payload.find((p: any) => p.dataKey === "historical");
  const forecast = payload.find((p: any) => p.dataKey === "forecast");
  const val = historical?.value ?? forecast?.value;
  if (!val) return null;
  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: "12px",
        boxShadow: "var(--shadow-lg)",
        padding: "10px 14px",
        minWidth: "130px",
      }}
    >
      <p style={{ fontSize: "11px", color: "var(--heliox-text-muted)", marginBottom: "4px" }}>
        {label}
      </p>
      <p
        style={{
          fontSize: "15px",
          fontWeight: 700,
          color: "var(--foreground)",
          fontVariantNumeric: "tabular-nums",
          letterSpacing: "-0.02em",
        }}
      >
        ${Number(val).toLocaleString(undefined, { maximumFractionDigits: 0 })}
      </p>
      <p style={{ fontSize: "11px", color: "var(--heliox-text-muted)", marginTop: "2px" }}>
        {historical ? "Historical" : "Forecast"}
      </p>
    </div>
  );
};

const RUNWAY_EXPAND_FLAG = "heliox_runway_expand_after_budget";

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
    if (!runwayExpanded) return;
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

    if (isDemoMode()) {
      await new Promise((r) => setTimeout(r, 400));
      setForecastData(generateDemoForecastApiResponse(horizonDays) as ForecastData);
      setLoading(false);
      return;
    }

    try {
      const data = await fetchJson<ForecastData>(
        `/api/v1/forecast/spend?horizon_days=${horizonDays}&allow_empty=true`
      );
      setForecastData(data);
      setError(data.error || null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load forecast."
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
        err instanceof Error ? err.message : "Unable to load runway forecast.";
      setRunway(null);
      setRunwayError(message);
      setBudgetMissing(message.toLowerCase().includes("budget"));
    }
  };

  const chartData = useMemo(() => {
    if (!forecastData) return [];
    const historical = forecastData.historical.slice(-14).map((p) => ({
      label: formatLabel(p.date),
      date: p.date,
      historical: p.value,
      forecast: null as number | null,
      lower: null as number | null,
      upper: null as number | null,
    }));
    const forecast = forecastData.forecast.map((p) => ({
      label: formatLabel(p.date),
      date: p.date,
      historical: null as number | null,
      forecast: p.value,
      lower: p.lower_bound,
      upper: p.upper_bound,
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

  const nextDayForecast =
    forecastData?.forecast[Math.min(horizonDays - 1, (forecastData?.forecast.length || 1) - 1)]?.value;
  const lastHistorical = forecastData?.historical[forecastData.historical.length - 1]?.value;

  const trend =
    nextDayForecast !== undefined && lastHistorical !== undefined
      ? ((nextDayForecast - lastHistorical) / lastHistorical) * 100
      : null;

  return (
    <div
      className="rounded-2xl p-6"
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        boxShadow: "var(--shadow-card)",
      }}
    >
      {/* ── Header ─────────────────────── */}
      <div className="mb-5 flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
            style={{ background: "rgba(99,102,241,0.1)" }}
          >
            <TrendingUp className="h-5 w-5" style={{ color: "#6366f1" }} />
          </div>
          <div>
            <div className="flex items-center gap-1.5 mb-0.5">
              <Sparkles className="h-3.5 w-3.5" style={{ color: "#6366f1" }} />
              <span
                style={{
                  fontSize: "10px",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  color: "#6366f1",
                }}
              >
                AI Forecast
              </span>
            </div>
            <h2
              style={{
                fontSize: "15px",
                fontWeight: 700,
                color: "var(--foreground)",
                letterSpacing: "-0.01em",
              }}
            >
              Cost Forecasting
            </h2>
          </div>
        </div>

        {/* Horizon selector */}
        <div className="flex items-center gap-1">
          {[7, 14, 30].map((days) => (
            <button
              key={days}
              onClick={() => setHorizonDays(days)}
              style={{
                fontSize: "12px",
                fontWeight: 600,
                padding: "4px 10px",
                borderRadius: "8px",
                border: "none",
                cursor: "pointer",
                transition: "all 0.15s",
                background:
                  horizonDays === days ? "#6366f1" : "var(--muted)",
                color:
                  horizonDays === days ? "#fff" : "var(--heliox-text-secondary)",
              }}
            >
              {days}d
            </button>
          ))}
        </div>
      </div>

      {/* ── Loading ─────────────────────── */}
      {loading && (
        <div className="flex h-60 items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <Loader2
              className="h-6 w-6 animate-spin"
              style={{ color: "#6366f1" }}
            />
            <p style={{ fontSize: "13px", color: "var(--heliox-text-muted)" }}>
              Generating forecast…
            </p>
          </div>
        </div>
      )}

      {/* ── Empty / Error state ─────────── */}
      {!loading && (error || !hasData) && (
        <div
          className="rounded-xl p-6 text-center"
          style={{
            background: "rgba(99,102,241,0.04)",
            border: "1px solid rgba(99,102,241,0.1)",
          }}
        >
          <div
            className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl"
            style={{ background: "rgba(99,102,241,0.1)" }}
          >
            <BarChart3 className="h-6 w-6" style={{ color: "#6366f1" }} />
          </div>
          <h3
            style={{
              fontSize: "14px",
              fontWeight: 700,
              color: "var(--foreground)",
              marginBottom: "6px",
            }}
          >
            Unlock cost forecasting
          </h3>
          <p
            style={{
              fontSize: "12px",
              color: "var(--heliox-text-muted)",
              maxWidth: "240px",
              margin: "0 auto 16px",
              lineHeight: 1.5,
            }}
          >
            Collect 7+ days of GPU spend data to enable AI-powered cost predictions.
          </p>
          <div className="flex flex-col items-center gap-2">
            <Link
              href="/settings/integrations"
              className="inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
              style={{ background: "#6366f1", fontSize: "13px" }}
            >
              Connect data source
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            {error && (
              <button
                onClick={fetchForecast}
                className="inline-flex items-center gap-1.5 rounded-xl px-4 py-2 transition-colors"
                style={{
                  fontSize: "13px",
                  color: "var(--heliox-text-secondary)",
                  background: "var(--muted)",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Try again
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Chart ──────────────────────── */}
      {!loading && !error && hasData && forecastData && (
        <>
          {/* Updated at */}
          <div
            className="mb-4 flex items-center gap-1.5"
            style={{ color: "var(--heliox-text-muted)" }}
          >
            <Calendar className="h-3.5 w-3.5" />
            <span style={{ fontSize: "11px" }}>
              Updated{" "}
              {new Date(forecastData.metadata.forecast_generated_at).toLocaleDateString()}
            </span>
          </div>

          {/* Area chart */}
          <div className="mb-5">
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="fcHistGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#7c3aed" stopOpacity={0.15} />
                    <stop offset="100%" stopColor="#7c3aed" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="fcForeGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#c084fc" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="#c084fc" stopOpacity={0} />
                  </linearGradient>
                </defs>

                <CartesianGrid
                  strokeDasharray="3 4"
                  stroke="var(--chart-grid)"
                  vertical={false}
                />

                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 10, fill: "var(--heliox-text-muted)" }}
                  axisLine={false}
                  tickLine={false}
                  interval="preserveStartEnd"
                />

                <YAxis
                  tick={{ fontSize: 10, fill: "var(--heliox-text-muted)" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) =>
                    v >= 1_000_000
                      ? `$${(v / 1_000_000).toFixed(1)}M`
                      : v >= 1_000
                      ? `$${(v / 1_000).toFixed(0)}k`
                      : `$${v}`
                  }
                  width={44}
                />

                <Tooltip
                  content={<CustomForecastTooltip />}
                  cursor={{
                    stroke: "rgba(99,102,241,0.2)",
                    strokeWidth: 1,
                    strokeDasharray: "4 4",
                  }}
                />

                {forecastStartLabel && forecastEndLabel && (
                  <ReferenceArea
                    x1={forecastStartLabel}
                    x2={forecastEndLabel}
                    fill="rgba(196,181,253,0.08)"
                    stroke="rgba(196,181,253,0.2)"
                    strokeWidth={1}
                  />
                )}

                {/* Confidence band upper */}
                <Area
                  type="monotone"
                  dataKey="upper"
                  stroke="none"
                  fill="#f5f3ff"
                  fillOpacity={0.6}
                  name="Upper bound"
                  activeDot={false}
                  connectNulls
                  legendType="none"
                />
                {/* Confidence band lower (whites it out) */}
                <Area
                  type="monotone"
                  dataKey="lower"
                  stroke="none"
                  fill="var(--card)"
                  name="Lower bound"
                  activeDot={false}
                  connectNulls
                  legendType="none"
                />

                {/* Historical line */}
                <Area
                  type="monotone"
                  dataKey="historical"
                  stroke="#7c3aed"
                  strokeWidth={2.5}
                  fill="url(#fcHistGrad)"
                  dot={false}
                  activeDot={{ r: 4, fill: "#7c3aed", stroke: "#fff", strokeWidth: 2 }}
                  name="Historical"
                  connectNulls
                />

                {/* Forecast line */}
                <Area
                  type="monotone"
                  dataKey="forecast"
                  stroke="#c084fc"
                  strokeWidth={2.5}
                  strokeDasharray="6 4"
                  fill="url(#fcForeGrad)"
                  dot={false}
                  activeDot={{ r: 4, fill: "#c084fc", stroke: "#fff", strokeWidth: 2 }}
                  name="Forecast"
                  connectNulls
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Legend */}
          <div className="mb-5 flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-6 rounded" style={{ background: "#7c3aed" }} />
              <span style={{ fontSize: "11px", color: "var(--heliox-text-muted)" }}>Historical</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className="inline-block h-0.5 w-6 rounded"
                style={{
                  background: "#c084fc",
                  borderTop: "2px dashed #c084fc",
                  height: "2px",
                }}
              />
              <span style={{ fontSize: "11px", color: "var(--heliox-text-muted)" }}>Forecast</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className="inline-block h-3 w-3 rounded-sm"
                style={{ background: "rgba(196,181,253,0.3)", border: "1px solid rgba(196,181,253,0.4)" }}
              />
              <span style={{ fontSize: "11px", color: "var(--heliox-text-muted)" }}>Confidence</span>
            </div>
          </div>

          {/* ── Stats grid ──────────────── */}
          <div className="mb-5 grid grid-cols-2 gap-2">
            {[
              {
                label: "Method",
                value:
                  forecastData.forecast_method === "moving_average"
                    ? "Moving Avg"
                    : forecastData.forecast_method === "lightgbm"
                    ? "LightGBM"
                    : forecastData.forecast_method,
              },
              {
                label: "Data points",
                value: forecastData.metadata.historical_data_points.toString(),
              },
              {
                label: "Last actual",
                value: lastHistorical
                  ? `$${lastHistorical.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                  : "—",
              },
              {
                label: `Day ${horizonDays} forecast`,
                value: nextDayForecast
                  ? `$${nextDayForecast.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                  : "—",
                accent:
                  trend !== null
                    ? trend > 5
                      ? { color: "#ef4444", bg: "rgba(239,68,68,0.06)" }
                      : trend < -5
                      ? { color: "#10b981", bg: "rgba(16,185,129,0.06)" }
                      : undefined
                    : undefined,
              },
            ].map(({ label, value, accent }) => (
              <div
                key={label}
                className="rounded-xl p-3"
                style={{
                  background: accent?.bg ?? "rgba(99,102,241,0.04)",
                  border: `1px solid ${accent ? accent.color + "22" : "rgba(99,102,241,0.1)"}`,
                }}
              >
                <p
                  style={{
                    fontSize: "10px",
                    fontWeight: 600,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    color: accent?.color ?? "#6366f1",
                    marginBottom: "4px",
                  }}
                >
                  {label}
                </p>
                <p
                  style={{
                    fontSize: "14px",
                    fontWeight: 700,
                    color: "var(--foreground)",
                    fontVariantNumeric: "tabular-nums",
                    letterSpacing: "-0.01em",
                  }}
                >
                  {value}
                </p>
              </div>
            ))}
          </div>

          {/* ── Runway section ──────────── */}
          <div
            className="rounded-xl"
            style={{
              border: "1px solid var(--border)",
              overflow: "hidden",
            }}
          >
            {/* Runway header */}
            <button
              onClick={() => setRunwayExpanded((p) => !p)}
              className="flex w-full items-center justify-between p-4 transition-colors"
              style={{ background: "var(--muted)", cursor: "pointer", border: "none" }}
              onMouseEnter={(e) =>
                ((e.currentTarget as HTMLButtonElement).style.background = "var(--muted)")
              }
            >
              <div className="flex items-center gap-2.5">
                <Wallet className="h-4 w-4" style={{ color: "#10b981" }} />
                <div className="text-left">
                  <p
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "var(--foreground)",
                    }}
                  >
                    Runway Forecast
                  </p>
                  <p style={{ fontSize: "11px", color: "var(--heliox-text-muted)" }}>
                    Budget burn &amp; top cost drivers
                  </p>
                </div>
              </div>
              {runwayExpanded ? (
                <ChevronUp className="h-4 w-4" style={{ color: "var(--heliox-text-muted)" }} />
              ) : (
                <ChevronDown className="h-4 w-4" style={{ color: "var(--heliox-text-muted)" }} />
              )}
            </button>

            {/* Runway content */}
            {runwayExpanded && (
              <div className="p-4">
                {/* Budget missing */}
                {budgetMissing && (
                  <div
                    className="mb-4 flex items-center justify-between gap-3 rounded-xl p-3"
                    style={{
                      background: "rgba(245,158,11,0.06)",
                      border: "1px solid rgba(245,158,11,0.2)",
                    }}
                  >
                    <p style={{ fontSize: "13px", color: "#d97706" }}>
                      Set a monthly budget to enable runway forecasts.
                    </p>
                    <Link
                      href="/settings"
                      className="shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold"
                      style={{
                        background: "rgba(245,158,11,0.12)",
                        color: "#d97706",
                        fontSize: "12px",
                      }}
                    >
                      Set budget
                    </Link>
                  </div>
                )}

                {/* Runway error (not budget) */}
                {runwayError && !budgetMissing && (
                  <div
                    className="mb-4 rounded-xl p-3"
                    style={{
                      background: "rgba(239,68,68,0.06)",
                      border: "1px solid rgba(239,68,68,0.2)",
                    }}
                  >
                    <p style={{ fontSize: "13px", color: "#dc2626" }}>{runwayError}</p>
                  </div>
                )}

                {/* Top N selector */}
                {!budgetMissing && (
                  <div className="mb-4 flex items-center justify-between">
                    <p style={{ fontSize: "12px", color: "var(--heliox-text-muted)" }}>
                      Top cost drivers
                    </p>
                    <select
                      value={topN}
                      onChange={(e) =>
                        setTopN(e.target.value === "all" ? "all" : Number(e.target.value))
                      }
                      style={{
                        fontSize: "12px",
                        color: "var(--foreground)",
                        background: "var(--card)",
                        border: "1px solid var(--border)",
                        borderRadius: "8px",
                        padding: "4px 8px",
                        cursor: "pointer",
                      }}
                    >
                      <option value="all">All</option>
                      <option value="3">Top 3</option>
                      <option value="5">Top 5</option>
                      <option value="10">Top 10</option>
                    </select>
                  </div>
                )}

                {/* Runway stats */}
                {!runwayError && runway && (
                  <>
                    <div className="mb-4 grid grid-cols-3 gap-2">
                      {[
                        { label: "Monthly burn", value: formatCurrency(runway.monthly_burn) },
                        {
                          label: "Runway",
                          value:
                            runway.runway_days !== null
                              ? `${runway.runway_days}d`
                              : "—",
                        },
                        {
                          label: "Budget risk",
                          value: `${(runway.budget_risk_score * 100).toFixed(0)}%`,
                          accent:
                            runway.budget_risk_score > 0.7
                              ? { color: "#ef4444" }
                              : runway.budget_risk_score > 0.4
                              ? { color: "#f59e0b" }
                              : { color: "#10b981" },
                        },
                      ].map(({ label, value, accent }) => (
                        <div
                          key={label}
                          className="rounded-xl p-3 text-center"
                          style={{
                            background: "var(--muted)",
                            border: "1px solid var(--border)",
                          }}
                        >
                          <p
                            style={{
                              fontSize: "10px",
                              color: "var(--heliox-text-muted)",
                              marginBottom: "4px",
                            }}
                          >
                            {label}
                          </p>
                          <p
                            style={{
                              fontSize: "15px",
                              fontWeight: 700,
                              color: accent?.color ?? "var(--foreground)",
                              fontVariantNumeric: "tabular-nums",
                            }}
                          >
                            {value}
                          </p>
                        </div>
                      ))}
                    </div>

                    {/* Breakdown */}
                    {runway.breakdown.length > 0 && (
                      <div className="space-y-2">
                        {runway.breakdown.map((item) => (
                          <div
                            key={`${item.job_type}-${item.model_name}`}
                            className="flex items-center justify-between rounded-xl px-3 py-2.5"
                            style={{
                              border: "1px solid var(--border)",
                              background: "var(--card)",
                            }}
                          >
                            <div>
                              <p
                                style={{
                                  fontSize: "13px",
                                  fontWeight: 600,
                                  color: "var(--foreground)",
                                }}
                              >
                                {item.job_type} · {item.model_name}
                              </p>
                              <p
                                style={{
                                  fontSize: "11px",
                                  color: "var(--heliox-text-muted)",
                                }}
                              >
                                {item.environment}
                              </p>
                            </div>
                            <div className="text-right">
                              <p
                                style={{
                                  fontSize: "13px",
                                  fontWeight: 700,
                                  color: "var(--foreground)",
                                  fontVariantNumeric: "tabular-nums",
                                }}
                              >
                                {formatCurrency(item.total_cost)}
                              </p>
                              <p
                                style={{
                                  fontSize: "11px",
                                  color: "var(--heliox-text-muted)",
                                }}
                              >
                                {(item.share_of_total * 100).toFixed(1)}%
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
