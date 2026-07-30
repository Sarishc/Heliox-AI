"use client";

import { motion, useReducedMotion } from "framer-motion";
import { BarChart3, ShieldCheck, Sparkles } from "lucide-react";
import { BrandLogo } from "@/components/brand/BrandLogo";

export function AuthShell({
  children,
  eyebrow = "GPU infrastructure intelligence",
  title = "Control compute economics without slowing innovation.",
  description = "Heliox unifies GPU spend, utilization, forecasts, and optimization signals in one operational system.",
}: {
  children: React.ReactNode;
  eyebrow?: string;
  title?: string;
  description?: string;
}) {
  const reduceMotion = useReducedMotion();
  const transition = reduceMotion ? { duration: 0 } : { duration: 0.32, ease: "easeOut" as const };

  return (
    <main className="auth-shell">
      <section className="auth-brand-panel" aria-label="About Heliox">
        <div className="auth-grid" aria-hidden="true" />
        <div className="auth-orb auth-orb-one" aria-hidden="true" />
        <div className="auth-orb auth-orb-two" aria-hidden="true" />
        <motion.div
          className="relative z-10 flex h-full flex-col"
          initial={reduceMotion ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={transition}
        >
          <BrandLogo href="/" />
          <div className="my-auto max-w-xl py-14">
            <p className="auth-eyebrow">{eyebrow}</p>
            <h1 className="auth-brand-title">{title}</h1>
            <p className="auth-brand-copy">{description}</p>
            <div className="mt-10 grid max-w-lg gap-3 sm:grid-cols-3">
              {[
                [BarChart3, "Unified cost telemetry"],
                [Sparkles, "Actionable savings"],
                [ShieldCheck, "Tenant-safe controls"],
              ].map(([Icon, label]) => {
                const FeatureIcon = Icon as typeof BarChart3;
                return (
                  <div className="auth-feature" key={String(label)}>
                    <FeatureIcon className="h-4 w-4 text-violet-300" />
                    <span>{String(label)}</span>
                  </div>
                );
              })}
            </div>
          </div>
          <p className="relative z-10 text-xs text-slate-500">Operational clarity for modern AI teams.</p>
        </motion.div>
      </section>

      <section className="auth-form-panel">
        <motion.div
          className="auth-form-wrap"
          initial={reduceMotion ? false : { opacity: 0, x: 14 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ ...transition, delay: reduceMotion ? 0 : 0.06 }}
        >
          <div className="mb-8 lg:hidden">
            <BrandLogo href="/" />
          </div>
          {children}
        </motion.div>
      </section>
    </main>
  );
}
export function AuthField({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string | null;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="auth-label">{label}</label>
      {children}
      {(error || hint) && (
        <p id={`${id}-message`} className={error ? "auth-field-error" : "auth-field-hint"} role={error ? "alert" : undefined}>
          {error || hint}
        </p>
      )}
    </div>
  );
}
