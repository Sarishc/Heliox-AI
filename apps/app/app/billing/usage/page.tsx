"use client";

import { useState, useEffect } from "react";
import { fetchJson } from "@/lib/api";

interface UsageBreakdown {
  event_type: string;
  total_quantity: number;
  unit: string;
}

interface UsageDailySummary {
  date: string;
  api_requests: number;
  ingestion_line_items: number;
  seats: number;
  gpu_nodes: number;
}

interface UsageSummary {
  team_id: string;
  start_date: string;
  end_date: string;
  breakdown: UsageBreakdown[];
  daily_summary: UsageDailySummary[];
  totals: {
    api_requests: number;
    ingestion_line_items: number;
    seats: number;
    gpu_nodes: number;
  };
}

export default function UsagePage() {
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [dateRange, setDateRange] = useState<"30d" | "current_month" | "custom">("30d");

  useEffect(() => {
    loadUsage();
  }, [dateRange]);

  async function loadUsage() {
    setLoading(true);
    setError("");

    try {
      let url = "/api/v1/billing/usage";
      
      if (dateRange === "current_month") {
        url = "/api/v1/billing/usage/current-month";
      } else if (dateRange === "30d") {
        // Default: last 30 days
        const to = new Date();
        const from = new Date();
        from.setDate(from.getDate() - 30);
        url += `?from=${from.toISOString().split("T")[0]}&to=${to.toISOString().split("T")[0]}`;
      }

      const data = await fetchJson<UsageSummary>(url);
      setUsage(data);
    } catch (err: any) {
      setError(err.message || "Failed to load usage data");
    } finally {
      setLoading(false);
    }
  }

  function formatNumber(num: number): string {
    return num.toLocaleString();
  }

  function formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  }

  if (loading) {
    return (
      <div className="p-8">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">Usage & Billing</h1>
          <div className="text-gray-600">Loading usage data...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">Usage & Billing</h1>
          <div className="bg-red-50 border border-red-200 rounded p-4">
            <p className="text-red-800">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!usage) {
    return null;
  }

  return (
    <div className="p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold">Usage & Billing</h1>
            <p className="text-gray-600 mt-1">
              {formatDate(usage.start_date)} - {formatDate(usage.end_date)}
            </p>
          </div>
          
          {/* Date Range Selector */}
          <div className="flex gap-2">
            <button
              onClick={() => setDateRange("30d")}
              className={`px-4 py-2 rounded font-medium ${
                dateRange === "30d"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              }`}
            >
              Last 30 Days
            </button>
            <button
              onClick={() => setDateRange("current_month")}
              className={`px-4 py-2 rounded font-medium ${
                dateRange === "current_month"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              }`}
            >
              Current Month
            </button>
          </div>
        </div>

        {/* Usage Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-600">API Requests</h3>
              <span className="text-2xl">🔌</span>
            </div>
            <div className="text-3xl font-bold text-gray-900">
              {formatNumber(usage.totals.api_requests)}
            </div>
            <div className="text-sm text-gray-500 mt-1">requests</div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-600">Data Ingestion</h3>
              <span className="text-2xl">📊</span>
            </div>
            <div className="text-3xl font-bold text-gray-900">
              {formatNumber(usage.totals.ingestion_line_items)}
            </div>
            <div className="text-sm text-gray-500 mt-1">line items</div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-600">Active Seats</h3>
              <span className="text-2xl">👥</span>
            </div>
            <div className="text-3xl font-bold text-gray-900">
              {formatNumber(usage.totals.seats)}
            </div>
            <div className="text-sm text-gray-500 mt-1">users</div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-600">GPU Nodes</h3>
              <span className="text-2xl">🖥️</span>
            </div>
            <div className="text-3xl font-bold text-gray-900">
              {formatNumber(usage.totals.gpu_nodes)}
            </div>
            <div className="text-sm text-gray-500 mt-1">nodes</div>
          </div>
        </div>

        {/* Daily Usage Chart */}
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-xl font-bold mb-4">Daily Usage Trend</h2>
          
          {usage.daily_summary.length > 0 ? (
            <div className="space-y-4">
              {/* Simple bar chart */}
              <div className="overflow-x-auto">
                <div className="min-w-full">
                  {/* Chart bars */}
                  <div className="flex items-end gap-2 h-64 border-b border-gray-200">
                    {usage.daily_summary.slice(0, 30).reverse().map((day, idx) => {
                      const maxValue = Math.max(
                        ...usage.daily_summary.map((d) => d.api_requests + d.ingestion_line_items)
                      );
                      const totalValue = day.api_requests + day.ingestion_line_items;
                      const heightPercent = maxValue > 0 ? (totalValue / maxValue) * 100 : 0;

                      return (
                        <div
                          key={day.date}
                          className="flex-1 flex flex-col items-center gap-1"
                          title={`${formatDate(day.date)}: ${formatNumber(totalValue)} total`}
                        >
                          <div
                            className="w-full bg-blue-500 rounded-t hover:bg-blue-600 cursor-pointer"
                            style={{ height: `${heightPercent}%`, minHeight: totalValue > 0 ? "4px" : "0" }}
                          />
                          {idx % 3 === 0 && (
                            <div className="text-xs text-gray-500 transform rotate-45 origin-left mt-2">
                              {formatDate(day.date)}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Legend */}
              <div className="flex items-center justify-center gap-6 text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 bg-blue-500 rounded"></div>
                  <span className="text-gray-600">Combined Usage</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              No daily usage data available for this period
            </div>
          )}
        </div>

        {/* Usage Breakdown Table */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-xl font-bold">Daily Breakdown</h2>
          </div>
          
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Date
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    API Requests
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Ingestion
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Seats
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    GPU Nodes
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {usage.daily_summary.length > 0 ? (
                  usage.daily_summary.map((day) => (
                    <tr key={day.date} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {formatDate(day.date)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-900">
                        {formatNumber(day.api_requests)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-900">
                        {formatNumber(day.ingestion_line_items)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-900">
                        {formatNumber(day.seats)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-900">
                        {formatNumber(day.gpu_nodes)}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center text-gray-500">
                      No usage data available
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
