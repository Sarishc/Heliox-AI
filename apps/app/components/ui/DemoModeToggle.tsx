"use client";

/**
 * Demo Mode Toggle - For Investor Presentations
 * Loads realistic enterprise-scale mock data
 */

import { useState, useEffect } from "react";
import { Sparkles, X } from "lucide-react";
import { isDemoMode, setDemoMode } from "@/lib/demoData";

export function DemoModeToggle() {
  const [isDemo, setIsDemo] = useState(false);
  const [showBanner, setShowBanner] = useState(false);

  useEffect(() => {
    const demoActive = isDemoMode();
    setIsDemo(demoActive);
    setShowBanner(demoActive);
  }, []);

  const handleToggle = () => {
    setDemoMode(!isDemo);
  };

  return (
    <>
      {/* Toggle Button in Topbar */}
      <button
        onClick={handleToggle}
        className={`
          flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium
          transition-all duration-200
          ${
            isDemo
              ? "bg-heliox-primary text-white hover:bg-heliox-primary-hover"
              : "bg-heliox-bg border border-heliox-border text-heliox-text hover:bg-heliox-card"
          }
        `}
        title={isDemo ? "Disable Demo Mode" : "Enable Demo Mode"}
      >
        <Sparkles className="w-4 h-4" />
        <span className="hidden sm:inline">
          {isDemo ? "Demo Active" : "Demo Mode"}
        </span>
      </button>

      {/* Demo Mode Banner */}
      {showBanner && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-gradient-to-r from-heliox-primary to-purple-600 text-white shadow-lg">
          <div className="container mx-auto px-4 py-2 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Sparkles className="w-5 h-5 animate-pulse" />
              <div>
                <div className="font-semibold text-sm">
                  Demo Data Mode Active
                </div>
                <div className="text-xs opacity-90">
                  Showing realistic enterprise-scale metrics • $2.4M monthly spend • 847 GPUs
                </div>
              </div>
            </div>
            <button
              onClick={() => setShowBanner(false)}
              className="p-1 rounded hover:bg-white/20 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
