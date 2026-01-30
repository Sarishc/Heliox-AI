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

interface EnterpriseLayoutProps {
  children: ReactNode;
  teamName?: string;
}

export function EnterpriseLayout({ children, teamName }: EnterpriseLayoutProps) {
  return (
    <DashboardFiltersProvider>
      <div className="min-h-screen bg-background">
        {/* Sidebar */}
        <Sidebar />

        {/* Main Content */}
        <div className="lg:pl-64">
          {/* Topbar */}
          <Topbar teamName={teamName} />

          {/* Content Area with Page Transition */}
          <main className="p-6 lg:p-8">
            <div className="mx-auto max-w-[1600px]">
              <PageTransition>{children}</PageTransition>
            </div>
          </main>
        </div>
      </div>
    </DashboardFiltersProvider>
  );
}
