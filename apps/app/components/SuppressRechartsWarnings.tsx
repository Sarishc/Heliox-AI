"use client";

/**
 * Suppresses the Recharts 3.x ResizeObserver first-render warning:
 * "The width(-1) and height(-1) of chart should be greater than 0"
 * Recharts fires this during render (before useEffect), so we patch
 * console.warn at module-load time rather than in an effect.
 */
if (typeof window !== "undefined") {
  const orig = console.warn.bind(console);
  // eslint-disable-next-line no-console
  console.warn = (...args: unknown[]) => {
    if (
      typeof args[0] === "string" &&
      args[0].includes("width(-1) and height(-1) of chart")
    ) {
      return;
    }
    orig(...args);
  };
}

export function SuppressRechartsWarnings() {
  return null;
}
