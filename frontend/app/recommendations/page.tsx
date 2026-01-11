"use client";

import { useEffect, useMemo, useState } from "react";
import { format, subDays } from "date-fns";
import Link from "next/link";
import {
  AlertCircle,
  Download,
  Filter,
  Loader2,
  RefreshCcw,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  LayoutDashboard,
} from "lucide-react";

type Severity = "high" | "medium" | "low";

interface RecommendationEvidence {
  date_range?: { start_date: string; end_date: string };
  job_id?: string;
  job_runtime_hours?: number;
  job_start_time?: string;
  job_end_time?: string;
  total_cost_usd?: number;
  expected_usage_hours?: number;
  actual_usage_hours?: number;
  waste_percentage?: number;
  gpu_type?: string;
  provider?: string;
  team_name?: string;
  model_name?: string;
  metadata?: Record<string, unknown>;
}

interface Recommendation {
  id: string;
  type: string;
  title: string;
  description: string;
  severity: Severity;
  estimated_savings_usd: number;
  evidence: RecommendationEvidence;
  created_at?: string;
}

interface RecommendationResponse {
  recommendations: Recommendation[];
  summary: {
    total?: number;
    by_severity?: Record<string, number>;
    by_type?: Record<string, number>;
    error?: string;
  };
  date_range: { start_date: string; end_date: string };
  total_estimated_savings_usd: number;
}

const severityStyles: Record<
  Severity,
  { badge: string; pill: string; label: string; icon: string }
> = {
  high: {
    badge: "bg-red-100 text-red-800 border-red-200",
    pill: "bg-red-50 text-red-700 border-red-200",
    label: "High",
    icon: "🔴",
  },
  medium: {
    badge: "bg-amber-100 text-amber-800 border-amber-200",
    pill: "bg-amber-50 text-amber-700 border-amber-200",
    label: "Medium",
    icon: "🟡",
  },
  low: {
    badge: "bg-blue-100 text-blue-800 border-blue-200",
    pill: "bg-blue-50 text-blue-700 border-blue-200",
    label: "Low",
    icon: "🔵",
  },
};

import { fetchJson } from "@/lib/api";
import BetaAccessGate from "@/components/BetaAccessGate";

function RecommendationsPageContent() {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [summary, setSummary] = useState<
    RecommendationResponse["summary"] | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState(
    format(subDays(new Date(), 13), "yyyy-MM-dd")
  );
  const [endDate, setEndDate] = useState(format(new Date(), "yyyy-MM-dd"));

  // Filters
  const [selectedSeverity, setSelectedSeverity] = useState<Severity | "all">(
    "all"
  );
  const [selectedProvider, setSelectedProvider] = useState<string>("all");
  const [selectedType, setSelectedType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchRecommendations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startDate, endDate]);

  const fetchRecommendations = async () => {
    setLoading(true);
    setError(null);

    try {
      const url = `/api/v1/recommendations?start_date=${startDate}&end_date=${endDate}`;
      const data = await fetchJson<RecommendationResponse>(url);
      setRecommendations(data.recommendations || []);
      setSummary(data.summary || null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load recommendations. Please try again later."
      );
      setRecommendations([]);
      setSummary(null);
    } finally {
      setLoading(false);
    }
  };

  const providers = useMemo(
    () =>
      Array.from(
        new Set(
          recommendations
            .map((r) => r.evidence?.provider || "")
            .filter((provider) => provider)
        )
      ),
    [recommendations]
  );

  const types = useMemo(
    () =>
      Array.from(
        new Set(
          recommendations
            .map((r) => r.type)
            .filter((type) => typeof type === "string" && type.length > 0)
        )
      ),
    [recommendations]
  );

  const filteredRecommendations = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();

    return recommendations.filter((rec) => {
      const matchesSeverity =
        selectedSeverity === "all" || rec.severity === selectedSeverity;
      const provider = rec.evidence?.provider;
      const matchesProvider =
        selectedProvider === "all" || provider === selectedProvider;
      const matchesType =
        selectedType === "all" ||
        rec.type?.toLowerCase() === selectedType.toLowerCase();

      const matchesSearch =
        query.length === 0 ||
        rec.title.toLowerCase().includes(query) ||
        rec.description.toLowerCase().includes(query) ||
        rec.evidence?.team_name?.toLowerCase().includes(query) ||
        rec.evidence?.gpu_type?.toLowerCase().includes(query) ||
        rec.evidence?.provider?.toLowerCase().includes(query);

      return matchesSeverity && matchesProvider && matchesType && matchesSearch;
    });
  }, [
    recommendations,
    searchQuery,
    selectedProvider,
    selectedSeverity,
    selectedType,
  ]);

  const totalSavings = filteredRecommendations.reduce(
    (sum, rec) => sum + rec.estimated_savings_usd,
    0
  );

  const filteredSeverityCounts = filteredRecommendations.reduce(
    (acc, rec) => {
      acc[rec.severity] = (acc[rec.severity] || 0) + 1;
      return acc;
    },
    {} as Record<Severity, number>
  );

  const exportToCSV = () => {
    if (filteredRecommendations.length === 0) return;

    const headers = [
      "Severity",
      "Title",
      "Type",
      "Description",
      "Estimated Savings (USD)",
      "Provider",
      "GPU Type",
      "Team",
    ];

    const rows = filteredRecommendations.map((rec) => [
      rec.severity,
      rec.title,
      rec.type,
      rec.description.replace(/"/g, '""'),
      rec.estimated_savings_usd.toFixed(2),
      rec.evidence?.provider || "N/A",
      rec.evidence?.gpu_type || "N/A",
      rec.evidence?.team_name || "N/A",
    ]);

    const csvContent = [
      headers.join(","),
      ...rows.map((row) => row.map((cell) => `"${cell}"`).join(",")),
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `heliox-recommendations-${new Date()
      .toISOString()
      .split("T")[0]}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  const clearFilters = () => {
    setSelectedSeverity("all");
    setSelectedProvider("all");
    setSelectedType("all");
    setSearchQuery("");
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-blue-600" />
                <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide">
                  Recommendations
                </p>
              </div>
              <h1 className="text-2xl font-bold text-gray-900">
                Cost Optimization Playbook
              </h1>
              <p className="text-sm text-gray-600 mt-1">
                Filters, severity chips, and exportable insights to reduce GPU
                spend.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/"
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
              >
                <LayoutDashboard className="w-4 h-4" />
                Dashboard
              </Link>
              <button
                onClick={fetchRecommendations}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
              >
                <RefreshCcw className="w-4 h-4" />
                Refresh
              </button>
              <button
                onClick={exportToCSV}
                disabled={filteredRecommendations.length === 0}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 col-span-1 md:col-span-2">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-100 rounded-lg">
                <TrendingDown className="w-6 h-6 text-green-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Potential Savings</p>
                <p className="text-2xl font-bold text-gray-900">
                  $
                  {totalSavings.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                  })}
                </p>
                <p className="text-xs text-gray-500">
                  Based on filtered recommendations
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 rounded-lg">
                <ShieldAlert className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Total Recos</p>
                <p className="text-2xl font-bold text-gray-900">
                  {filteredRecommendations.length}
                </p>
                <p className="text-xs text-gray-500">
                  {summary?.total ?? 0} overall in range
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-red-100 rounded-lg">
                <AlertCircle className="w-6 h-6 text-red-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">High Severity</p>
                <p className="text-2xl font-bold text-gray-900">
                  {filteredSeverityCounts.high || 0}
                </p>
                <p className="text-xs text-gray-500">
                  {summary?.by_severity?.high ?? 0} total high
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-2">
                <Filter className="w-5 h-5 text-gray-500" />
                <h2 className="text-lg font-semibold text-gray-900">
                  Filters & Severity Chips
                </h2>
              </div>
              <div className="flex gap-2">
                <div className="text-xs text-gray-500 flex items-center gap-1">
                  <span className="font-medium">Date range:</span>
                  <span>
                    {startDate} → {endDate}
                  </span>
                </div>
                <button
                  onClick={clearFilters}
                  className="text-sm text-blue-600 hover:text-blue-700"
                >
                  Clear filters
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Start date
                </label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  End date
                </label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Provider
                </label>
                <select
                  value={selectedProvider}
                  onChange={(e) => setSelectedProvider(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="all">All providers</option>
                  {providers.map((provider) => (
                    <option key={provider} value={provider}>
                      {provider.toUpperCase()}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Type
                </label>
                <select
                  value={selectedType}
                  onChange={(e) => setSelectedType(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="all">All types</option>
                  {types.map((type) => (
                    <option key={type} value={type}>
                      {type.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="flex flex-wrap gap-2">
                {(["all", "high", "medium", "low"] as const).map((level) => {
                  const isAll = level === "all";
                  const isActive = selectedSeverity === level;
                  const severity =
                    level === "all" ? ("low" as Severity) : (level as Severity);

                  return (
                    <button
                      key={level}
                      onClick={() =>
                        setSelectedSeverity(
                          isAll ? "all" : (level as Severity)
                        )
                      }
                      className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                        isAll
                          ? isActive
                            ? "bg-gray-900 text-white border-gray-900"
                            : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50"
                          : isActive
                          ? severityStyles[severity].pill
                          : "bg-white text-gray-700 border-gray-200 hover:bg-gray-50"
                      }`}
                    >
                      {isAll
                        ? "All severities"
                        : `${severityStyles[severity].icon} ${
                            severityStyles[severity].label
                          }`}
                    </button>
                  );
                })}
              </div>
              <div className="w-full md:w-72">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Search
                </label>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by title, GPU, team..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
            </div>
          </div>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="flex items-center gap-3 text-gray-600">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>Loading recommendations...</span>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="text-lg font-semibold text-red-900 mb-1">
                  Error loading recommendations
                </h3>
                <p className="text-red-700">{error}</p>
                <button
                  onClick={fetchRecommendations}
                  className="mt-3 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                >
                  Try again
                </button>
              </div>
            </div>
          </div>
        )}

        {!loading && !error && (
          <div className="space-y-4">
            {filteredRecommendations.length === 0 ? (
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
                <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                  No recommendations match your filters
                </h3>
                <p className="text-gray-500 mb-4">
                  Try adjusting severity chips or clearing filters to see more
                  options.
                </p>
                <button
                  onClick={clearFilters}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  Reset filters
                </button>
              </div>
            ) : (
              filteredRecommendations.map((rec) => (
                <div
                  key={rec.id}
                  className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3 flex-1">
                      <span className="text-2xl">
                        {severityStyles[rec.severity].icon}
                      </span>
                      <div className="flex-1">
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          <h3 className="text-lg font-semibold text-gray-900">
                            {rec.title}
                          </h3>
                          <span
                            className={`px-2 py-1 rounded-full text-xs font-semibold border ${severityStyles[rec.severity].badge}`}
                          >
                            {severityStyles[rec.severity].label}
                          </span>
                          {rec.type && (
                            <span className="px-2 py-1 rounded-full text-xs font-medium border border-gray-200 bg-gray-50 text-gray-700">
                              {rec.type.replace(/_/g, " ")}
                            </span>
                          )}
                        </div>
                        <p className="text-gray-700 mb-3">{rec.description}</p>
                        <div className="flex flex-wrap items-center gap-4 text-sm text-gray-600">
                          {rec.evidence?.provider && (
                            <span className="flex items-center gap-1">
                              <span className="font-medium">Provider:</span>
                              {rec.evidence.provider.toUpperCase()}
                            </span>
                          )}
                          {rec.evidence?.gpu_type && (
                            <span className="flex items-center gap-1">
                              <span className="font-medium">GPU:</span>
                              {rec.evidence.gpu_type.toUpperCase()}
                            </span>
                          )}
                          {rec.evidence?.team_name && (
                            <span className="flex items-center gap-1">
                              <span className="font-medium">Team:</span>
                              {rec.evidence.team_name}
                            </span>
                          )}
                          {rec.evidence?.job_runtime_hours && (
                            <span className="flex items-center gap-1">
                              <span className="font-medium">Runtime:</span>
                              {rec.evidence.job_runtime_hours.toFixed(1)}h
                            </span>
                          )}
                          {rec.evidence?.waste_percentage !== undefined && (
                            <span className="flex items-center gap-1">
                              <span className="font-medium">Waste:</span>
                              {rec.evidence.waste_percentage?.toFixed(1)}%
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="text-right min-w-[160px]">
                      <p className="text-sm text-gray-500 mb-1">
                        Potential savings
                      </p>
                      <p className="text-2xl font-bold text-green-600">
                        $
                        {rec.estimated_savings_usd.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                        })}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        Based on current usage
                      </p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default function RecommendationsPage() {
  return (
    <BetaAccessGate>
      <RecommendationsPageContent />
    </BetaAccessGate>
  );
}

