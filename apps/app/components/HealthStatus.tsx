"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

export default function HealthStatus() {
  const [status, setStatus] = useState<"healthy" | "unhealthy" | "checking">(
    "checking"
  );

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await fetch(getApiUrl("/health"), {
          // Health checks should be fast, add timeout
          signal: AbortSignal.timeout(5000),
        });
        
        if (response.ok) {
          setStatus("healthy");
        } else {
          setStatus("unhealthy");
        }
      } catch (error) {
        // Network error or timeout
        setStatus("unhealthy");
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000); // Check every 30 seconds

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-50 border border-gray-200">
        <div
          className={`w-2 h-2 rounded-full ${
            status === "healthy"
              ? "bg-green-500 animate-pulse"
              : status === "unhealthy"
              ? "bg-red-500"
              : "bg-yellow-500 animate-pulse"
          }`}
        />
        <span className="text-xs font-medium text-gray-700">
          {status === "healthy"
            ? "API Connected"
            : status === "unhealthy"
            ? "API Offline"
            : "Checking..."}
        </span>
      </div>
    </div>
  );
}

