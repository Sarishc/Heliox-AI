"use client";

import { useCallback, useEffect, useState } from "react";
import { registerDemoBlockHandler } from "@/lib/api";
import { DemoBlockModal } from "@/components/DemoBlockModal";

/**
 * Mounts invisibly in the root layout. Registers the global demo-block modal
 * handler so fetchApi can trigger it from anywhere without prop-drilling.
 */
export function DemoProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [signupUrl, setSignupUrl] = useState<string | undefined>(undefined);

  const handleDemoBlock = useCallback((url?: string) => {
    setSignupUrl(url);
    setOpen(true);
  }, []);

  useEffect(() => {
    registerDemoBlockHandler(handleDemoBlock);
  }, [handleDemoBlock]);

  return (
    <>
      {children}
      <DemoBlockModal
        open={open}
        onClose={() => setOpen(false)}
        signupUrl={signupUrl}
      />
    </>
  );
}
