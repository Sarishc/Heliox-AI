"use client";

/**
 * Enterprise Topbar Component
 * Premium top navigation with org selector, search, notifications
 */

import { useState } from "react";
import { Search, Bell, ChevronDown, Moon, Sun, Menu } from "lucide-react";
import { Button } from "../ui/Button";

interface TopbarProps {
  teamName?: string;
  onMenuClick?: () => void;
}

export function Topbar({ teamName = "Demo Team", onMenuClick }: TopbarProps) {
  const [darkMode, setDarkMode] = useState(false);

  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    document.documentElement.classList.toggle("dark");
  };

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-16 items-center justify-between px-6 gap-4">
        {/* Left: Mobile Menu + Search */}
        <div className="flex items-center gap-4 flex-1">
          {/* Mobile menu button */}
          <button
            onClick={onMenuClick}
            className="lg:hidden p-2 rounded-lg hover:bg-muted text-muted-foreground"
          >
            <Menu className="w-5 h-5" />
          </button>

          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search... (⌘K)"
              className="
                w-full pl-10 pr-4 py-2 rounded-lg
                bg-muted border border-transparent
                text-sm text-foreground placeholder:text-muted-foreground
                focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent
                transition-all
              "
            />
          </div>
        </div>

        {/* Right: Org Selector, Notifications, Theme, User */}
        <div className="flex items-center gap-3">
          {/* Organization Selector */}
          <button className="hidden sm:flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted text-sm font-medium text-foreground transition-colors">
            <div className="w-6 h-6 rounded bg-brand-600 flex items-center justify-center text-white text-xs font-bold">
              {teamName.charAt(0)}
            </div>
            <span className="max-w-[120px] truncate">{teamName}</span>
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          </button>

          {/* Dark Mode Toggle */}
          <button
            onClick={toggleDarkMode}
            className="p-2 rounded-lg hover:bg-muted text-muted-foreground transition-colors"
            aria-label="Toggle dark mode"
          >
            {darkMode ? (
              <Sun className="w-5 h-5" />
            ) : (
              <Moon className="w-5 h-5" />
            )}
          </button>

          {/* Notifications */}
          <button className="relative p-2 rounded-lg hover:bg-muted text-muted-foreground transition-colors">
            <Bell className="w-5 h-5" />
            <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-danger-500 rounded-full border-2 border-background" />
          </button>

          {/* User Avatar */}
          <button className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-muted transition-colors">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white text-sm font-semibold">
              U
            </div>
            <ChevronDown className="w-4 h-4 text-muted-foreground hidden sm:block" />
          </button>
        </div>
      </div>
    </header>
  );
}
