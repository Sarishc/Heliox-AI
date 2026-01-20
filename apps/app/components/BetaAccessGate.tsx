"use client";

import { useEffect, useState } from "react";
import { Lock } from "lucide-react";
import { hasBetaAccess, verifyBetaAccess } from "@/lib/beta-access";

interface BetaAccessGateProps {
  children: React.ReactNode;
}

export default function BetaAccessGate({ children }: BetaAccessGateProps) {
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [isChecking, setIsChecking] = useState(true);
  const [accessCode, setAccessCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    // Check access on mount
    setIsAuthorized(hasBetaAccess());
    setIsChecking(false);
  }, []);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    // Verify access code
    if (verifyBetaAccess(accessCode.trim())) {
      setIsAuthorized(true);
    } else {
      setError("Invalid access code. Please try again.");
      setAccessCode("");
    }

    setIsSubmitting(false);
  };

  // Show loading state during initial check
  if (isChecking) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  // Show access gate if not authorized
  if (!isAuthorized) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
            <div className="flex flex-col items-center text-center mb-6">
              <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mb-4">
                <Lock className="w-6 h-6 text-blue-600" />
              </div>
              <h1 className="text-2xl font-bold text-gray-900 mb-2">
                Private Beta Access
              </h1>
              <p className="text-gray-600">
                Enter your access code to continue
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  htmlFor="access-code"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  Access Code
                </label>
                <input
                  id="access-code"
                  type="text"
                  value={accessCode}
                  onChange={(e) => setAccessCode(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-center font-mono"
                  placeholder="Enter code"
                  autoFocus
                  disabled={isSubmitting}
                  autoComplete="off"
                />
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <p className="text-sm text-red-600 text-center">{error}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={isSubmitting || !accessCode.trim()}
                className="w-full bg-blue-600 text-white py-2 px-4 rounded-lg font-medium hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isSubmitting ? "Verifying..." : "Continue"}
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  // Render children if authorized
  return <>{children}</>;
}
