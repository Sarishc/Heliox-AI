"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { setStoredAccessToken } from "@/lib/api";

export default function AuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    // Get token and team_id from URL params
    const token = searchParams.get("token");
    const teamId = searchParams.get("team_id");

    if (token) {
      // Store token in localStorage
      setStoredAccessToken(token);

      // Redirect to dashboard
      setTimeout(() => {
        router.push("/");
      }, 1000);
    } else {
      // No token, redirect to login with error
      router.push("/login?error=oauth_failed&message=No token received");
    }
  }, [router, searchParams]);

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
