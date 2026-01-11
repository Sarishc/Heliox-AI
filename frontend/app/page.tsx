"use client";

import { useState, useEffect } from "react";
import { format, subDays } from "date-fns";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import BetaAccessGate from "@/components/BetaAccessGate";
import DateRangePicker from "@/components/DateRangePicker";
import SpendTrendChart from "@/components/SpendTrendChart";
import CostByModelChart from "@/components/CostByModelChart";
import CostByTeamChart from "@/components/CostByTeamChart";
import HealthStatus from "@/components/HealthStatus";
import ForecastCard from "@/components/ForecastCard";

function DashboardContent() {
  const [startDate, setStartDate] = useState(
    format(subDays(new Date(), 13), "yyyy-MM-dd")
  );
  const [endDate, setEndDate] = useState(format(new Date(), "yyyy-MM-dd"));

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                Heliox Dashboard
              </h1>
              <p className="text-sm text-gray-500 mt-1">
                GPU Cost Analytics & Insights
              </p>
            </div>
            <div className="flex items-center gap-4">
              <Link
                href="/recommendations"
                className="flex items-center gap-2 px-4 py-2 text-blue-600 hover:text-blue-700 font-medium rounded-lg hover:bg-blue-50 transition-colors"
              >
                <Sparkles className="w-4 h-4" />
                Recommendations
              </Link>
              <HealthStatus />
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Date Range Picker */}
        <div className="mb-8">
          <DateRangePicker
            startDate={startDate}
            endDate={endDate}
            onStartDateChange={setStartDate}
            onEndDateChange={setEndDate}
          />
        </div>

        {/* Charts Grid */}
        <div className="space-y-6">
          {/* Spend Trend */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Daily Spend Trend
            </h2>
            <SpendTrendChart startDate={startDate} endDate={endDate} />
          </div>

          {/* Cost by Model and Team - Side by Side on Desktop */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Cost by ML Model
              </h2>
              <CostByModelChart startDate={startDate} endDate={endDate} />
            </div>

            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Cost by Team
              </h2>
              <CostByTeamChart startDate={startDate} endDate={endDate} />
            </div>
          </div>

          {/* Forecast Card */}
          <ForecastCard />
        </div>

        {/* Footer */}
        <footer className="mt-12 text-center text-sm text-gray-500">
          <p>Heliox AI - GPU Cost Management Platform</p>
        </footer>
      </main>
    </div>
  );
}

export default function Dashboard() {
  return (
    <BetaAccessGate>
      <DashboardContent />
    </BetaAccessGate>
  );
}
