"use client";

import { useState, useEffect } from "react";
import { fetchJson } from "@/lib/api";

interface PricingPlan {
  plan: string;
  name: string;
  price: number | string;
  description: string;
  limits: {
    max_teams: number;
    max_users: number;
    max_api_calls_per_day: number;
    max_integrations: number;
    max_gpu_nodes: number;
    data_retention_days: number;
  };
  features: {
    integrations_enabled: boolean;
    forecasting_enabled: boolean;
    alerts_enabled: boolean;
    api_access: boolean;
    custom_reports: boolean;
    sso_enabled: boolean;
    priority_support: boolean;
    white_label: boolean;
  };
}

interface Subscription {
  team_id: string;
  plan: string;
  status: string;
  stripe_customer_id: string;
  stripe_subscription_id: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  limits: any;
  features: any;
}

export default function BillingPage() {
  const [plans, setPlans] = useState<PricingPlan[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState<string | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [plansData, subData] = await Promise.all([
        fetchJson<PricingPlan[]>("/api/v1/billing/plans"),
        fetchJson<Subscription>("/api/v1/billing/subscription"),
      ]);
      setPlans(plansData);
      setSubscription(subData);
    } catch (err: any) {
      setError(err.message || "Failed to load billing data");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpgrade(plan: string) {
    setUpgrading(plan);
    setError("");

    try {
      const response = await fetchJson<{ checkout_url: string }>(
        "/api/v1/billing/create-checkout-session",
        {
          method: "POST",
          body: JSON.stringify({
            plan,
            success_url: `${window.location.origin}/billing?success=true`,
            cancel_url: `${window.location.origin}/billing?canceled=true`,
          }),
        }
      );

      // Redirect to Stripe Checkout
      window.location.href = response.checkout_url;
    } catch (err: any) {
      setError(err.message || "Failed to start checkout");
      setUpgrading(null);
    }
  }

  async function openCustomerPortal() {
    try {
      const response = await fetchJson<{ portal_url: string }>(
        "/api/v1/billing/create-portal-session",
        {
          method: "POST",
          body: JSON.stringify({
            return_url: window.location.href,
          }),
        }
      );

      // Open customer portal in new tab
      window.open(response.portal_url, "_blank");
    } catch (err: any) {
      setError(err.message || "Failed to open customer portal");
    }
  }

  function formatLimit(value: number): string {
    if (value === -1) return "Unlimited";
    return value.toLocaleString();
  }

  if (loading) {
    return (
      <div className="p-8">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">Billing & Subscriptions</h1>
          <div className="text-gray-600">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Billing & Subscriptions</h1>
          <p className="text-gray-600">
            Choose a plan that fits your GPU monitoring needs
          </p>
        </div>

        {/* Current Subscription Status */}
        {subscription && (
          <div className="bg-white rounded-lg shadow p-6 mb-8">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold mb-2">Current Plan</h2>
                <div className="flex items-center gap-4">
                  <div className="text-2xl font-bold text-blue-600 capitalize">
                    {subscription.plan}
                  </div>
                  <span
                    className={`px-3 py-1 rounded-full text-sm font-medium ${
                      subscription.status === "active"
                        ? "bg-green-100 text-green-800"
                        : subscription.status === "trialing"
                        ? "bg-blue-100 text-blue-800"
                        : "bg-red-100 text-red-800"
                    }`}
                  >
                    {subscription.status}
                  </span>
                </div>
                {subscription.current_period_end && (
                  <p className="text-sm text-gray-600 mt-2">
                    {subscription.cancel_at_period_end
                      ? "Cancels on"
                      : "Renews on"}{" "}
                    {new Date(subscription.current_period_end).toLocaleDateString()}
                  </p>
                )}
              </div>
              {subscription.stripe_subscription_id && (
                <button
                  onClick={openCustomerPortal}
                  className="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50 font-medium"
                >
                  Manage Subscription
                </button>
              )}
            </div>
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded p-4 mb-6">
            <p className="text-red-800">{error}</p>
          </div>
        )}

        {/* URL Params Messages */}
        {typeof window !== "undefined" && (
          <>
            {new URLSearchParams(window.location.search).get("success") && (
              <div className="bg-green-50 border border-green-200 rounded p-4 mb-6">
                <p className="text-green-800 font-medium">
                  ✓ Subscription upgraded successfully!
                </p>
              </div>
            )}
            {new URLSearchParams(window.location.search).get("canceled") && (
              <div className="bg-yellow-50 border border-yellow-200 rounded p-4 mb-6">
                <p className="text-yellow-800">
                  Checkout canceled. You can try again anytime.
                </p>
              </div>
            )}
          </>
        )}

        {/* Pricing Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {plans.map((plan) => {
            const isCurrentPlan = subscription?.plan === plan.plan;
            const isUpgrade =
              subscription &&
              ["free", "starter", "growth", "enterprise"].indexOf(subscription.plan) <
                ["free", "starter", "growth", "enterprise"].indexOf(plan.plan);

            return (
              <div
                key={plan.plan}
                className={`bg-white rounded-lg shadow-lg overflow-hidden ${
                  isCurrentPlan ? "ring-2 ring-blue-500" : ""
                }`}
              >
                {isCurrentPlan && (
                  <div className="bg-blue-500 text-white text-center py-1 text-sm font-medium">
                    Current Plan
                  </div>
                )}

                <div className="p-6">
                  {/* Plan Header */}
                  <h3 className="text-2xl font-bold mb-2">{plan.name}</h3>
                  <div className="mb-4">
                    {typeof plan.price === "number" ? (
                      <>
                        <span className="text-4xl font-bold">${plan.price}</span>
                        <span className="text-gray-600">/month</span>
                      </>
                    ) : (
                      <span className="text-4xl font-bold">{plan.price}</span>
                    )}
                  </div>
                  <p className="text-gray-600 text-sm mb-6">{plan.description}</p>

                  {/* Limits */}
                  <div className="space-y-3 mb-6">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600">Teams:</span>
                      <span className="font-medium">{formatLimit(plan.limits.max_teams)}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600">Users:</span>
                      <span className="font-medium">{formatLimit(plan.limits.max_users)}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600">API Calls/day:</span>
                      <span className="font-medium">
                        {formatLimit(plan.limits.max_api_calls_per_day)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600">Integrations:</span>
                      <span className="font-medium">
                        {formatLimit(plan.limits.max_integrations)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600">GPU Nodes:</span>
                      <span className="font-medium">{formatLimit(plan.limits.max_gpu_nodes)}</span>
                    </div>
                  </div>

                  {/* Features */}
                  <div className="space-y-2 mb-6">
                    {plan.features.integrations_enabled && (
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-green-500">✓</span>
                        <span>Cloud Integrations</span>
                      </div>
                    )}
                    {plan.features.forecasting_enabled && (
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-green-500">✓</span>
                        <span>Cost Forecasting</span>
                      </div>
                    )}
                    {plan.features.custom_reports && (
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-green-500">✓</span>
                        <span>Custom Reports</span>
                      </div>
                    )}
                    {plan.features.sso_enabled && (
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-green-500">✓</span>
                        <span>SSO</span>
                      </div>
                    )}
                    {plan.features.priority_support && (
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-green-500">✓</span>
                        <span>Priority Support</span>
                      </div>
                    )}
                    {plan.features.white_label && (
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-green-500">✓</span>
                        <span>White Label</span>
                      </div>
                    )}
                  </div>

                  {/* CTA Button */}
                  {plan.plan === "free" ? (
                    <button
                      disabled={isCurrentPlan}
                      className="w-full px-4 py-2 bg-gray-100 text-gray-600 rounded font-medium cursor-not-allowed"
                    >
                      {isCurrentPlan ? "Current Plan" : "Free Forever"}
                    </button>
                  ) : plan.plan === "enterprise" ? (
                    <a
                      href="mailto:sales@heliox.ai"
                      className="block w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 font-medium text-center"
                    >
                      Contact Sales
                    </a>
                  ) : isCurrentPlan ? (
                    <button
                      disabled
                      className="w-full px-4 py-2 bg-gray-100 text-gray-600 rounded font-medium cursor-not-allowed"
                    >
                      Current Plan
                    </button>
                  ) : (
                    <button
                      onClick={() => handleUpgrade(plan.plan)}
                      disabled={upgrading === plan.plan}
                      className="w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                    >
                      {upgrading === plan.plan
                        ? "Loading..."
                        : isUpgrade
                        ? "Upgrade"
                        : "Downgrade"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* FAQ / Info Section */}
        <div className="mt-12 bg-gray-50 rounded-lg p-6">
          <h2 className="text-xl font-bold mb-4">Frequently Asked Questions</h2>
          <div className="space-y-4">
            <div>
              <h3 className="font-semibold mb-1">Can I change my plan anytime?</h3>
              <p className="text-gray-600 text-sm">
                Yes, you can upgrade or downgrade your plan at any time. Changes take effect immediately for
                upgrades, or at the end of your billing period for downgrades.
              </p>
            </div>
            <div>
              <h3 className="font-semibold mb-1">What payment methods do you accept?</h3>
              <p className="text-gray-600 text-sm">
                We accept all major credit cards (Visa, Mastercard, American Express) through Stripe.
              </p>
            </div>
            <div>
              <h3 className="font-semibold mb-1">Is there a free trial?</h3>
              <p className="text-gray-600 text-sm">
                The Free plan is available forever with no credit card required. Paid plans may offer a trial
                period at checkout.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
