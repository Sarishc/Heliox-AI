"use client";

/**
 * Enterprise Sidebar Component
 * Premium navigation inspired by Stripe, Datadog, Vercel
 */

import { usePathname } from "next/navigation";
import Link from "next/link";
import { ReactNode } from "react";
import { motion } from "framer-motion";
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
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: ReactNode;
  badge?: string;
}

const navigation: NavItem[] = [
  {
    label: "Overview",
    href: "/",
    icon: <LayoutDashboard className="w-5 h-5" />,
  },
  {
    label: "Analytics",
    href: "/analytics",
    icon: <BarChart3 className="w-5 h-5" />,
  },
  {
    label: "Forecasting",
    href: "/forecast",
    icon: <TrendingUp className="w-5 h-5" />,
  },
  {
    label: "Optimization",
    href: "/optimization",
    icon: <Sparkles className="w-5 h-5" />,
  },
  {
    label: "Budgets",
    href: "/budgets",
    icon: <AlertTriangle className="w-5 h-5" />,
  },
  {
    label: "Proxy",
    href: "/proxy",
    icon: <Zap className="w-5 h-5" />,
  },
  {
    label: "Integrations",
    href: "/settings/integrations",
    icon: <Blocks className="w-5 h-5" />,
  },
  {
    label: "Billing",
    href: "/billing",
    icon: <CreditCard className="w-5 h-5" />,
    badge: "New",
  },
  {
    label: "Settings",
    href: "/settings",
    icon: <Settings className="w-5 h-5" />,
  },
];

export function Sidebar() {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/") {
      return pathname === "/";
    }
    return pathname?.startsWith(href);
  };

  return (
    <aside className="hidden lg:flex lg:flex-col lg:w-64 lg:fixed lg:inset-y-0 bg-sidebar border-r border-border">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-border">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center">
          <Zap className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-foreground">Heliox</h1>
          <p className="text-xs text-muted-foreground">GPU Analytics</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navigation.map((item, index) => {
          const active = isActive(item.href);
          return (
            <motion.div
              key={item.href}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2, delay: index * 0.05 }}
            >
              <Link
                href={item.href}
                className={`
                  group flex items-center gap-3 px-3 py-2.5 rounded-lg
                  text-sm font-medium transition-all duration-200
                  ${
                    active
                      ? "bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-400"
                      : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-foreground"
                  }
                `}
              >
                <motion.span
                  whileHover={{ scale: 1.1 }}
                  transition={{ duration: 0.2 }}
                  className={`${active ? "text-brand-600 dark:text-brand-400" : "text-muted-foreground group-hover:text-foreground"}`}
                >
                  {item.icon}
                </motion.span>
                <span className="flex-1">{item.label}</span>
                {item.badge && (
                  <motion.span
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ delay: 0.5 }}
                    className="px-2 py-0.5 text-xs font-semibold bg-brand-600 text-white rounded-md"
                  >
                    {item.badge}
                  </motion.span>
                )}
              </Link>
            </motion.div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <div className="px-3 py-2 rounded-lg bg-muted">
          <p className="text-xs font-medium text-foreground">Need help?</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Check our{" "}
            <a href="/docs" className="text-brand-600 hover:underline">
              documentation
            </a>
          </p>
        </div>
      </div>
    </aside>
  );
}
