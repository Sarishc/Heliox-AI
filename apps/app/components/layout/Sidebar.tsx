"use client";

/**
 * Enterprise Sidebar Component - Grouped & Collapsible
 * Dense, professional navigation with sections
 * Inspired by: Stripe, Datadog, Linear, Snowflake
 */

import { usePathname } from "next/navigation";
import Link from "next/link";
import { ReactNode, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  TrendingUp,
  Zap,
  AlertTriangle,
  Settings,
  BarChart3,
  Sparkles,
  Blocks,
  CreditCard,
  ChevronDown,
  ChevronRight,
  Activity,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: ReactNode;
  badge?: string;
}

interface NavSection {
  title: string;
  items: NavItem[];
  defaultOpen?: boolean;
}

const navigationSections: NavSection[] = [
  {
    title: "CORE",
    defaultOpen: true,
    items: [
      {
        label: "Overview",
        href: "/",
        icon: <LayoutDashboard className="w-4 h-4" />,
      },
      {
        label: "Analytics",
        href: "/analytics",
        icon: <BarChart3 className="w-4 h-4" />,
      },
      {
        label: "Forecasting",
        href: "/forecast",
        icon: <TrendingUp className="w-4 h-4" />,
      },
    ],
  },
  {
    title: "OPTIMIZATION",
    defaultOpen: true,
    items: [
      {
        label: "Proxy",
        href: "/proxy",
        icon: <Zap className="w-4 h-4" />,
      },
      {
        label: "Opportunities",
        href: "/optimization",
        icon: <Sparkles className="w-4 h-4" />,
      },
      {
        label: "Budgets & Alerts",
        href: "/budgets",
        icon: <AlertTriangle className="w-4 h-4" />,
      },
    ],
  },
  {
    title: "PLATFORM",
    defaultOpen: true,
    items: [
      {
        label: "Integrations",
        href: "/settings/integrations",
        icon: <Blocks className="w-4 h-4" />,
      },
      {
        label: "Billing",
        href: "/billing",
        icon: <CreditCard className="w-4 h-4" />,
      },
      {
        label: "Settings",
        href: "/settings",
        icon: <Settings className="w-4 h-4" />,
      },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>(
    navigationSections.reduce((acc, section) => {
      acc[section.title] = section.defaultOpen ?? true;
      return acc;
    }, {} as Record<string, boolean>)
  );

  const isActive = (href: string) => {
    if (href === "/") {
      return pathname === "/";
    }
    return pathname?.startsWith(href);
  };

  const toggleSection = (sectionTitle: string) => {
    setExpandedSections((prev) => ({
      ...prev,
      [sectionTitle]: !prev[sectionTitle],
    }));
  };

  return (
    <aside className="hidden lg:flex lg:flex-col lg:w-64 lg:fixed lg:inset-y-0 bg-heliox-sidebar border-r border-heliox-border">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-heliox-border">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-heliox-primary to-purple-700 flex items-center justify-center shadow-sm">
          <Activity className="w-4 h-4 text-white" />
        </div>
        <div>
          <h1 className="text-base font-bold text-heliox-text tracking-tight">Heliox</h1>
          <p className="text-[11px] text-heliox-text-muted font-medium">GPU Analytics</p>
        </div>
      </div>

      {/* Navigation with Sections */}
      <nav className="flex-1 px-3 py-3 space-y-6 overflow-y-auto">
        {navigationSections.map((section, sectionIndex) => (
          <div key={section.title}>
            {/* Section Header */}
            <button
              onClick={() => toggleSection(section.title)}
              className="
                w-full flex items-center justify-between gap-2 px-3 py-1.5
                text-[11px] font-semibold tracking-widest
                text-heliox-text-secondary
                hover:text-heliox-text transition-colors
                group
              "
            >
              <span>{section.title}</span>
              <motion.div
                animate={{ rotate: expandedSections[section.title] ? 0 : -90 }}
                transition={{ duration: 0.2 }}
              >
                <ChevronDown className="w-3 h-3 opacity-60 group-hover:opacity-100" />
              </motion.div>
            </button>

            {/* Section Items */}
            <AnimatePresence initial={false}>
              {expandedSections[section.title] && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="space-y-0.5 mt-1">
                    {section.items.map((item, itemIndex) => {
                      const active = isActive(item.href);
                      return (
                        <motion.div
                          key={item.href}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{
                            duration: 0.15,
                            delay: itemIndex * 0.03,
                          }}
                        >
                          <Link
                            href={item.href}
                            className={`
                              group flex items-center gap-2.5 px-3 py-2 rounded-md
                              text-[13px] font-medium transition-all duration-150
                              ${
                                active
                                  ? "bg-heliox-primary-muted text-heliox-primary"
                                  : "text-heliox-text-secondary hover:bg-heliox-card-hover hover:text-heliox-text"
                              }
                            `}
                          >
                            <span
                              className={`
                                ${active ? "text-heliox-primary" : "text-heliox-text-muted group-hover:text-heliox-text"}
                                transition-colors
                              `}
                            >
                              {item.icon}
                            </span>
                            <span className="flex-1">{item.label}</span>
                            {item.badge && (
                              <span className="px-1.5 py-0.5 text-[10px] font-bold bg-heliox-primary text-white rounded">
                                {item.badge}
                              </span>
                            )}
                          </Link>
                        </motion.div>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </nav>

      {/* Footer - Status Indicator */}
      <div className="p-3 border-t border-heliox-border">
        <div className="px-3 py-2.5 rounded-lg bg-heliox-bg border border-heliox-border-muted">
          <div className="flex items-center gap-2 mb-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-success-500 animate-pulse" />
            <p className="text-[11px] font-semibold text-heliox-text">All Systems Operational</p>
          </div>
          <p className="text-[11px] text-heliox-text-muted">
            API • Data Sync • Monitoring
          </p>
        </div>
      </div>
    </aside>
  );
}
