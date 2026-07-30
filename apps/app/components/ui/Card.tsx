/**
 * Enterprise Card Component
 * Premium card design with variants, hover states, and loading
 */

import { ReactNode } from "react";
import { motion } from "framer-motion";

interface CardProps {
  children: ReactNode;
  className?: string;
  variant?: "default" | "bordered" | "elevated" | "flat";
  padding?: "none" | "sm" | "md" | "lg";
  hoverable?: boolean;
  loading?: boolean;
}

export function Card({
  children,
  className = "",
  variant = "default",
  padding = "md",
  hoverable = false,
  loading = false,
}: CardProps) {
  const variantStyles = {
    default: "rounded-md border border-border bg-card",
    bordered: "rounded-md border border-border bg-card",
    elevated: "rounded-md border border-border bg-card",
    flat: "rounded-md border border-border bg-muted",
  };

  const paddingStyles = {
    none: "",
    sm: "p-3",
    md: "p-4",
    lg: "p-5",
  };

  const hoverStyles = hoverable
    ? "transition-colors duration-150 hover:bg-muted cursor-pointer"
    : "";

  if (loading) {
    return (
      <div
        className={`
          ${variantStyles[variant]}
          ${paddingStyles[padding]}
          animate-pulse
          ${className}
        `}
      >
        <div className="space-y-3">
          <div className="h-4 bg-muted rounded w-3/4"></div>
          <div className="h-8 bg-muted rounded w-1/2"></div>
          <div className="h-3 bg-muted rounded w-full"></div>
        </div>
      </div>
    );
  }

  const MotionDiv = hoverable ? motion.div : "div";

  return (
    <MotionDiv
      {...(hoverable
        ? {
            transition: { duration: 0.15 },
          }
        : {})}
      className={`
        ${variantStyles[variant]}
        ${paddingStyles[padding]}
        ${hoverStyles}
        transition-colors
        ${className}
      `}
    >
      {children}
    </MotionDiv>
  );
}

export function CardHeader({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`-mx-4 -mt-4 mb-3 border-b border-border px-3 py-2 ${className}`}>
      {children}
    </div>
  );
}

export function CardTitle({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h3 className={`text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground ${className}`}>
      {children}
    </h3>
  );
}

export function CardDescription({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p className={`text-[11px] text-muted-foreground mt-0.5 ${className}`}>
      {children}
    </p>
  );
}

export function CardContent({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={className}>{children}</div>;
}

export function CardFooter({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`mt-6 pt-4 border-t border-border ${className}`}>
      {children}
    </div>
  );
}
