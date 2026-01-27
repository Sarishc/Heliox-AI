"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  FileText,
  LayoutGrid,
  Settings,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import DateRangePicker from "@/components/DateRangePicker";
import { bootstrapDevApiKey, fetchJson } from "@/lib/api";
import {
  DashboardFiltersProvider,
  useDashboardFilters,
} from "@/components/DashboardFiltersContext";

const navItems = [
  { label: "Overview", href: "/", icon: LayoutGrid },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
  { label: "Optimization", href: "/optimization", icon: Sparkles },
  { label: "Forecast", href: "/forecast", icon: TrendingUp },
  { label: "Budgets", href: "/budgets", icon: AlertTriangle },
  { label: "Alerts", href: "/alerts", icon: Sparkles },
  { label: "Reports", href: "/reports", icon: FileText },
  { label: "Settings", href: "/settings", icon: Settings },
];

interface TeamResponse {
  id: string;
  name: string;
}

interface MeResponse {
  team_id: string;
  role: string;
  feature_flags: Record<string, boolean>;
}

function AppShellContent({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { startDate, endDate, setStartDate, setEndDate, environment, setEnvironment } =
    useDashboardFilters();
  const [teamName, setTeamName] = useState<string>("Team");
  const [teamId, setTeamId] = useState<string | null>(null);

  useEffect(() => {
    const loadTeam = async () => {
      try {
        await bootstrapDevApiKey();
        const me = await fetchJson<MeResponse>("/api/v1/me");
        setTeamId(me.team_id);
        const team = await fetchJson<TeamResponse>(`/api/v1/teams/${me.team_id}`);
        setTeamName(team.name || "Team");
      } catch {
        setTeamName("Team");
      }
    };
    loadTeam();
  }, []);

  const activeHref = useMemo(() => {
    if (pathname === "/") return "/";
    return navItems.find((item) => pathname?.startsWith(item.href))?.href ?? "/";
  }, [pathname]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="flex">
        <aside className="hidden lg:flex lg:w-64 lg:flex-col lg:border-r lg:border-slate-200 lg:bg-white">
          <div className="px-6 py-5 border-b border-slate-100">
            <div className="flex items-center gap-2 text-lg font-semibold">
              <Activity className="h-5 w-5 text-blue-600" />
              Heliox
            </div>
            <p className="text-xs text-slate-500 mt-1">GPU Cost Intelligence</p>
          </div>
          <nav className="flex-1 px-3 py-4 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeHref === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-blue-50 text-blue-700"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="px-6 py-4 border-t border-slate-100 text-xs text-slate-500">
            Version 0.9 • Private beta
          </div>
        </aside>

        <div className="flex-1">
          <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
            <div className="flex flex-wrap items-center gap-4 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="text-sm text-slate-500">Team</div>
                <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm font-medium text-slate-700">
                  <span>{teamName}</span>
                  {teamId && (
                    <span className="text-xs text-slate-400">• {teamId.slice(0, 6)}</span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-500">Env</span>
                <select
                  value={environment}
                  onChange={(event) =>
                    setEnvironment(event.target.value as "prod" | "staging" | "dev")
                  }
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="prod">Production</option>
                  <option value="staging">Staging</option>
                  <option value="dev">Development</option>
                </select>
              </div>

              <div className="ml-auto min-w-[260px]">
                <DateRangePicker
                  startDate={startDate}
                  endDate={endDate}
                  onStartDateChange={setStartDate}
                  onEndDateChange={setEndDate}
                />
              </div>
            </div>
          </header>

          <main className="px-6 py-6">{children}</main>
        </div>
      </div>
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <DashboardFiltersProvider>
      <AppShellContent>{children}</AppShellContent>
    </DashboardFiltersProvider>
  );
}
