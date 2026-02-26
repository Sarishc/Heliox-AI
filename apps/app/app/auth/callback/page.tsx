"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * OAuth callback fallback.
 * Backend now sets httpOnly cookie and redirects directly to dashboard.
 * This page handles legacy links or direct visits - redirect to dashboard.
 */
export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/");
  }, [router]);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-white border border-gray-200 rounded-lg shadow-sm p-8 text-center">
        <div className="mb-4">
          <div className="inline-block w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
        </div>
        <h1 className="text-xl font-bold text-gray-900 mb-2">Completing Sign-In</h1>
        <p className="text-gray-600">
          Please wait while we log you in...
        </p>
      </div>
    </div>
  );
}
