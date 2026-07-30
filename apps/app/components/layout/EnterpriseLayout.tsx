"use client";

/**
 * Enterprise Layout Component
 * Premium layout with sidebar, topbar, and content area
 */

import { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { DashboardFiltersProvider } from "../DashboardFiltersContext";
import { PageTransition } from "../ui/PageTransition";
import { TeamGuard } from "../TeamGuard";

interface EnterpriseLayoutProps {
  children: ReactNode;
  teamName?: string;
}

export function EnterpriseLayout({ children, teamName }: EnterpriseLayoutProps) {
  const pathname = usePathname();
  const pageName =
    pathname === "/"
      ? "Overview"
      : pathname
          .split("/")
          .filter(Boolean)
          .map((part) => part.replace(/-/g, " "))
          .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
          .join(" / ");

  return (
    <TeamGuard>
      <DashboardFiltersProvider>
        <div className="min-h-screen bg-background">
        {/* Sidebar */}
        <Sidebar />

        {/* Main Content */}
        <div className="lg:pl-64">
          {/* Topbar */}
          <Topbar teamName={teamName} />

          {/* Content Area with Page Transition */}
          <main className="px-4 py-4 lg:px-5 lg:py-4">
            <div className="mx-auto max-w-screen-2xl">
              <div className="ops-breadcrumb mb-2">
                Heliox <span aria-hidden="true">/</span> <strong>{pageName}</strong>
              </div>
              <PageTransition>{children}</PageTransition>
            </div>
          </main>
        </div>
      </div>
    </DashboardFiltersProvider>
    </TeamGuard>
  );
}
