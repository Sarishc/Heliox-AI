"use client";

/**
 * Enterprise Layout Component
 * Premium layout with sidebar, topbar, and content area
 */

import { ReactNode } from "react";
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
          <main className="px-6 py-7 lg:px-8 lg:py-8">
            <div className="mx-auto max-w-screen-2xl">
              <PageTransition>{children}</PageTransition>
            </div>
          </main>
        </div>
      </div>
    </DashboardFiltersProvider>
    </TeamGuard>
  );
}
