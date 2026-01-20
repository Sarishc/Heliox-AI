"use client";

import { createContext, useContext, useMemo, useState } from "react";
import { format, subDays } from "date-fns";

type EnvironmentFilter = "prod" | "staging" | "dev";

interface DashboardFiltersContextValue {
  startDate: string;
  endDate: string;
  environment: EnvironmentFilter;
  setStartDate: (value: string) => void;
  setEndDate: (value: string) => void;
  setEnvironment: (value: EnvironmentFilter) => void;
}

const DashboardFiltersContext = createContext<DashboardFiltersContextValue | null>(
  null
);

export function DashboardFiltersProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [startDate, setStartDate] = useState(
    format(subDays(new Date(), 29), "yyyy-MM-dd")
  );
  const [endDate, setEndDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [environment, setEnvironment] = useState<EnvironmentFilter>("prod");

  const value = useMemo(
    () => ({
      startDate,
      endDate,
      environment,
      setStartDate,
      setEndDate,
      setEnvironment,
    }),
    [startDate, endDate, environment]
  );

  return (
    <DashboardFiltersContext.Provider value={value}>
      {children}
    </DashboardFiltersContext.Provider>
  );
}

export function useDashboardFilters() {
  const context = useContext(DashboardFiltersContext);
  if (!context) {
    throw new Error("useDashboardFilters must be used within DashboardFiltersProvider");
  }
  return context;
}
