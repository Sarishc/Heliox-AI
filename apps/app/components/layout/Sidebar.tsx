"use client";

/**
 * Enterprise Sidebar — Top 0.1% Design
 * Linear / Stripe / Datadog inspired
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
  PiggyBank,
} from "lucide-react";
import { BrandMark } from "@/components/brand/BrandLogo";

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
    title: "Core",
    defaultOpen: true,
    items: [
      { label: "Overview",     href: "/",          icon: <LayoutDashboard className="h-[15px] w-[15px]" /> },
      { label: "Analytics",    href: "/analytics", icon: <BarChart3       className="h-[15px] w-[15px]" /> },
      { label: "ROI & Savings",href: "/roi",        icon: <PiggyBank       className="h-[15px] w-[15px]" /> },
      { label: "Forecasting",  href: "/forecast",  icon: <TrendingUp      className="h-[15px] w-[15px]" /> },
    ],
  },
  {
    title: "Optimization",
    defaultOpen: true,
    items: [
      { label: "Proxy",           href: "/proxy",        icon: <Zap          className="h-[15px] w-[15px]" /> },
      { label: "Opportunities",   href: "/optimization", icon: <Sparkles     className="h-[15px] w-[15px]" /> },
      { label: "Budgets & Alerts",href: "/budgets",      icon: <AlertTriangle className="h-[15px] w-[15px]" /> },
    ],
  },
  {
    title: "Platform",
    defaultOpen: true,
    items: [
      { label: "Integrations", href: "/settings/integrations", icon: <Blocks     className="h-[15px] w-[15px]" /> },
      { label: "Billing",      href: "/billing",               icon: <CreditCard  className="h-[15px] w-[15px]" /> },
      { label: "Settings",     href: "/settings",              icon: <Settings    className="h-[15px] w-[15px]" /> },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>(
    navigationSections.reduce((acc, s) => ({ ...acc, [s.title]: s.defaultOpen ?? true }), {})
  );

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname?.startsWith(href);

  const toggleSection = (title: string) =>
    setExpandedSections((prev) => ({ ...prev, [title]: !prev[title] }));

  return (
    <aside
      className="hidden lg:flex lg:flex-col lg:w-64 lg:fixed lg:inset-y-0"
      style={{
        background: "var(--sidebar)",
        borderRight: "1px solid var(--border)",
      }}
    >
      {/* ── Logo ─────────────────────────── */}
      <div
        className="flex items-center gap-2.5 px-4 py-3"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <BrandMark className="h-7 w-7 shrink-0" />
        <div className="min-w-0">
          <p className="text-[14px] font-semibold tracking-[-0.04em] text-foreground">heliox<span className="ml-0.5 text-violet-400">.</span></p>
          <p className="text-[10px] font-medium text-muted-foreground">Infrastructure Intelligence</p>
        </div>
      </div>

      {/* ── Nav ──────────────────────────── */}
      <nav className="flex-1 overflow-y-auto px-2 py-3" style={{ scrollbarWidth: "none" }}>
        <div className="space-y-3">
          {navigationSections.map((section) => (
            <div key={section.title}>
              {/* Section label */}
              <button
                onClick={() => toggleSection(section.title)}
                className="group mb-1 flex w-full items-center justify-between px-2 py-1"
              >
                <span
                  className="text-[10px] font-bold uppercase tracking-[0.1em]"
                  style={{ color: "var(--heliox-text-muted)" }}
                >
                  {section.title}
                </span>
                <motion.span
                  animate={{ rotate: expandedSections[section.title] ? 0 : -90 }}
                  transition={{ duration: 0.18 }}
                  className="opacity-40 group-hover:opacity-70"
                >
                  <ChevronDown className="h-3 w-3 text-muted-foreground" />
                </motion.span>
              </button>

              {/* Nav items */}
              <AnimatePresence initial={false}>
                {expandedSections[section.title] && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.18 }}
                    className="overflow-hidden"
                  >
                    <div className="space-y-[2px]">
                      {section.items.map((item, i) => {
                        const active = isActive(item.href);
                        return (
                          <motion.div
                            key={item.href}
                            initial={{ opacity: 0, x: -6 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ duration: 0.12, delay: i * 0.025 }}
                          >
                            <Link
                              href={item.href}
                              className="group relative flex items-center gap-2 rounded-sm px-2.5 py-[6px] text-[12px] font-medium transition-colors duration-150"
                              style={
                                active
                                  ? {
                                      background: "rgba(99,102,241,0.08)",
                                      color: "#a5b4fc",
                                    }
                                  : {
                                      color: "var(--heliox-text-secondary)",
                                    }
                              }
                              onMouseEnter={(e) => {
                                if (!active) {
                                  (e.currentTarget as HTMLAnchorElement).style.background =
                                    "var(--muted)";
                                  (e.currentTarget as HTMLAnchorElement).style.color =
                                    "var(--foreground)";
                                }
                              }}
                              onMouseLeave={(e) => {
                                if (!active) {
                                  (e.currentTarget as HTMLAnchorElement).style.background =
                                    "transparent";
                                  (e.currentTarget as HTMLAnchorElement).style.color =
                                    "var(--heliox-text-secondary)";
                                }
                              }}
                            >
                              {/* Active left indicator */}
                              {active && (
                                <motion.span
                                  layoutId="sidebar-active-indicator"
                                  className="absolute left-0 inset-y-[5px] w-[2px]"
                                  style={{ background: "#8b5cf6" }}
                                  transition={{ type: "spring", stiffness: 460, damping: 38 }}
                                />
                              )}

                              <span
                                style={{
                                  color: active ? "#6366f1" : "var(--heliox-text-muted)",
                                }}
                              >
                                {item.icon}
                              </span>
                              <span className="flex-1 leading-none">{item.label}</span>
                              {item.badge && (
                                <span
                                  className="rounded-md px-1.5 py-0.5 text-[10px] font-bold text-white"
                                  style={{ background: "#6366f1" }}
                                >
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
        </div>
      </nav>

      {/* ── Status footer ────────────────── */}
      <div
        className="px-3 py-3"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <div
          className="rounded-sm px-2.5 py-2"
          style={{
            background: "rgba(16,185,129,0.06)",
            border: "1px solid rgba(16,185,129,0.15)",
          }}
        >
          <div className="mb-0.5 flex items-center gap-2">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{
                background: "var(--ops-healthy)",
              }}
            />
            <p className="text-[11px] font-semibold text-foreground">All Systems Operational</p>
          </div>
          <p className="pl-[14px] text-[10px]" style={{ color: "var(--heliox-text-muted)" }}>
            Checked 30s ago · API · Sync
          </p>
        </div>
      </div>
    </aside>
  );
}
