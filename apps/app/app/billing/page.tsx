"use client";

/**
 * Enterprise Billing & Subscriptions Page
 * Premium pricing with modern design
 */

import { useState, useEffect } from "react";
import { 
  Check, 
  CreditCard, 
  TrendingUp, 
  Users, 
  Zap,
  Shield,
  AlertCircle,
  ExternalLink,
  Sparkles,
} from "lucide-react";
import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { fetchJson } from "@/lib/api";
import { isDemoMode } from "@/lib/demoData";

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

function BillingContent() {
  const [plans, setPlans] = useState<PricingPlan[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState<string | null>(null);
  const [error, setError] = useState<string>("");
  const [billingUnavailable, setBillingUnavailable] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError("");
    setBillingUnavailable(false);
    try {
      const [plansData, subData] = await Promise.all([
        fetchJson<PricingPlan[]>("/api/v1/billing/plans"),
        fetchJson<Subscription>("/api/v1/billing/subscription"),
      ]);
      setPlans(plansData);
      setSubscription(subData);
    } catch (err: any) {
      console.error("Failed to load billing data:", err);
      // 503 means Stripe is not configured on this server instance
      if (err.status === 503 || (err.message && err.message.includes("not configured"))) {
        setBillingUnavailable(true);
        setLoading(false);
        return;
      }
      setError(err.message || "Failed to load billing data");
      // Set default mock data for demo purposes
      setPlans([
        {
          plan: "free",
          name: "Free",
          price: 0,
          description: "Perfect for trying out Heliox",
          limits: {
            max_teams: 1,
            max_users: 3,
            max_api_calls_per_day: 1000,
            max_integrations: 1,
            max_gpu_nodes: 10,
            data_retention_days: 30,
          },
          features: {
            integrations_enabled: true,
            forecasting_enabled: false,
            alerts_enabled: true,
            api_access: true,
            custom_reports: false,
            sso_enabled: false,
            priority_support: false,
            white_label: false,
          },
        },
        {
          plan: "starter",
          name: "Starter",
          price: 99,
          description: "For small teams getting started",
          limits: {
            max_teams: 3,
            max_users: 10,
            max_api_calls_per_day: 10000,
            max_integrations: 3,
            max_gpu_nodes: 50,
            data_retention_days: 90,
          },
          features: {
            integrations_enabled: true,
            forecasting_enabled: true,
            alerts_enabled: true,
            api_access: true,
            custom_reports: true,
            sso_enabled: false,
            priority_support: false,
            white_label: false,
          },
        },
        {
          plan: "growth",
          name: "Growth",
          price: 299,
          description: "For scaling teams with complex needs",
          limits: {
            max_teams: 10,
            max_users: 50,
            max_api_calls_per_day: 100000,
            max_integrations: 10,
            max_gpu_nodes: 200,
            data_retention_days: 180,
          },
          features: {
            integrations_enabled: true,
            forecasting_enabled: true,
            alerts_enabled: true,
            api_access: true,
            custom_reports: true,
            sso_enabled: true,
            priority_support: true,
            white_label: false,
          },
        },
        {
          plan: "enterprise",
          name: "Enterprise",
          price: "Custom",
          description: "For large organizations with advanced requirements",
          limits: {
            max_teams: -1,
            max_users: -1,
            max_api_calls_per_day: -1,
            max_integrations: -1,
            max_gpu_nodes: -1,
            data_retention_days: 365,
          },
          features: {
            integrations_enabled: true,
            forecasting_enabled: true,
            alerts_enabled: true,
            api_access: true,
            custom_reports: true,
            sso_enabled: true,
            priority_support: true,
            white_label: true,
          },
        },
      ]);
      setSubscription({
        team_id: "demo",
        plan: "free",
        status: "active",
        stripe_customer_id: "",
        stripe_subscription_id: null,
        current_period_end: null,
        cancel_at_period_end: false,
        limits: {},
        features: {},
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleUpgrade(plan: string) {
    setUpgrading(plan);
    setError("");
    setBillingUnavailable(false);

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

      window.location.href = response.checkout_url;
    } catch (err: any) {
      if (err.status === 503 || (err.message && err.message.includes("not configured"))) {
        setBillingUnavailable(true);
      } else {
        setError(err.message || "Failed to start checkout");
      }
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

      window.open(response.portal_url, "_blank");
    } catch (err: any) {
      setError(err.message || "Failed to open customer portal");
    }
  }

  function formatLimit(value: number): string {
    if (value === -1) return "Unlimited";
    return value.toLocaleString();
  }

  const planOrder = ["free", "starter", "growth", "enterprise"];
  const currentPlanIndex = subscription
    ? planOrder.indexOf(subscription.plan)
    : 0;

  if (billingUnavailable) {
    return (
      <>
        <PageHeader
          title="Billing & Subscriptions"
          description="Subscription management"
          breadcrumbs={[
            { label: "Home", href: "/" },
            { label: "Billing" },
          ]}
        />
        <Card variant="flat" className="mt-6">
          <CardContent className="py-12 text-center">
            <Shield className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-2">
              Billing is not configured
            </h3>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              Payment processing is not set up on this instance. Contact your
              administrator or reach out to{" "}
              <a href="mailto:support@heliox.ai" className="text-brand-600 hover:underline">
                support@heliox.ai
              </a>{" "}
              to enable billing.
            </p>
          </CardContent>
        </Card>
      </>
    );
  }

  return (
    <>
      {/* Page Header */}
      <PageHeader
        title="Billing & Subscriptions"
        description="Choose the perfect plan for your GPU monitoring and optimization needs"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Billing" },
        ]}
      />

      {/* Success/Cancel Messages */}
      {typeof window !== "undefined" && (
        <>
          {new URLSearchParams(window.location.search).get("success") && (
            <Card variant="flat" className="mb-6 border-l-4 border-l-success-500">
              <CardContent className="py-4">
                <div className="flex items-center gap-3">
                  <Check className="w-5 h-5 text-success-600" />
                  <p className="font-medium text-success-900 dark:text-success-100">
                    Subscription upgraded successfully!
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
          {new URLSearchParams(window.location.search).get("canceled") && (
            <Card variant="flat" className="mb-6 border-l-4 border-l-warning-500">
              <CardContent className="py-4">
                <div className="flex items-center gap-3">
                  <AlertCircle className="w-5 h-5 text-warning-600" />
                  <p className="text-warning-900 dark:text-warning-100">
                    Checkout canceled. You can try again anytime.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Error Message */}
      {error && !isDemoMode() && (
        <Card variant="flat" className="mb-6 border-l-4 border-l-danger-500">
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-danger-600" />
              <p className="text-danger-900 dark:text-danger-100">{error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Current Subscription */}
      {subscription && (
        <Card className="mb-8" variant="elevated">
          <CardContent className="p-6">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-4">
                <div className="p-3 rounded-xl bg-brand-50 dark:bg-brand-500/10">
                  <CreditCard className="w-6 h-6 text-brand-600 dark:text-brand-400" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-foreground mb-1">
                    Current Plan
                  </h3>
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-2xl font-bold text-brand-600 dark:text-brand-400 capitalize">
                      {subscription.plan}
                    </span>
                    <Badge
                      variant={
                        subscription.status === "active"
                          ? "success"
                          : subscription.status === "trialing"
                          ? "info"
                          : "danger"
                      }
                    >
                      {subscription.status}
                    </Badge>
                  </div>
                  {subscription.current_period_end && (
                    <p className="text-sm text-muted-foreground">
                      {subscription.cancel_at_period_end ? "Cancels on" : "Renews on"}{" "}
                      {new Date(subscription.current_period_end).toLocaleDateString()}
                    </p>
                  )}
                </div>
              </div>
              {subscription.stripe_subscription_id && (
                <Button
                  variant="outline"
                  onClick={openCustomerPortal}
                  icon={<ExternalLink className="w-4 h-4" />}
                  iconPosition="right"
                >
                  Manage
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Pricing Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
        {plans
          .sort((a, b) => planOrder.indexOf(a.plan) - planOrder.indexOf(b.plan))
          .map((plan) => {
            const isCurrentPlan = subscription?.plan === plan.plan;
            const planIndex = planOrder.indexOf(plan.plan);
            const isUpgrade = currentPlanIndex < planIndex;
            const isPopular = plan.plan === "growth";

            return (
              <Card
                key={plan.plan}
                variant={isPopular ? "elevated" : "default"}
                className={`
                  relative overflow-hidden
                  ${isCurrentPlan ? "ring-2 ring-brand-500" : ""}
                  ${isPopular ? "scale-105" : ""}
                `}
              >
                {/* Popular Badge */}
                {isPopular && (
                  <div className="absolute top-0 right-0 bg-gradient-to-r from-brand-600 to-brand-500 text-white px-3 py-1 text-xs font-bold rounded-bl-lg">
                    <Sparkles className="w-3 h-3 inline mr-1" />
                    POPULAR
                  </div>
                )}

                {/* Current Plan Badge */}
                {isCurrentPlan && (
                  <div className="bg-brand-600 text-white text-center py-2 text-sm font-semibold">
                    ✓ Current Plan
                  </div>
                )}

                <CardContent className="p-6">
                  {/* Plan Name */}
                  <h3 className="text-2xl font-bold text-foreground mb-2">{plan.name}</h3>

                  {/* Price */}
                  <div className="mb-4">
                    {typeof plan.price === "number" ? (
                      <div className="flex items-baseline gap-1">
                        <span className="text-4xl font-bold text-foreground">
                          ${plan.price}
                        </span>
                        <span className="text-muted-foreground">/month</span>
                      </div>
                    ) : (
                      <span className="text-4xl font-bold text-foreground">{plan.price}</span>
                    )}
                  </div>

                  <p className="text-sm text-muted-foreground mb-6 min-h-[40px]">
                    {plan.description}
                  </p>

                  {/* CTA Button */}
                  {plan.plan === "free" ? (
                    <Button
                      variant={isCurrentPlan ? "secondary" : "outline"}
                      fullWidth
                      disabled={isCurrentPlan}
                    >
                      {isCurrentPlan ? "Current Plan" : "Free Forever"}
                    </Button>
                  ) : plan.plan === "enterprise" ? (
                    <Button
                      variant="primary"
                      fullWidth
                      onClick={() => window.location.href = "mailto:sales@heliox.ai"}
                      icon={<ExternalLink className="w-4 h-4" />}
                      iconPosition="right"
                    >
                      Contact Sales
                    </Button>
                  ) : isCurrentPlan ? (
                    <Button variant="secondary" fullWidth disabled>
                      Current Plan
                    </Button>
                  ) : (
                    <Button
                      variant={isUpgrade ? "primary" : "outline"}
                      fullWidth
                      onClick={() => handleUpgrade(plan.plan)}
                      loading={upgrading === plan.plan}
                    >
                      {isUpgrade ? "Upgrade" : "Change Plan"}
                    </Button>
                  )}

                  {/* Limits */}
                  <div className="mt-6 pt-6 border-t border-border space-y-3">
                    <LimitItem icon={<Users />} label="Teams" value={formatLimit(plan.limits.max_teams)} />
                    <LimitItem icon={<Users />} label="Users" value={formatLimit(plan.limits.max_users)} />
                    <LimitItem icon={<Zap />} label="API Calls/day" value={formatLimit(plan.limits.max_api_calls_per_day)} />
                    <LimitItem icon={<TrendingUp />} label="GPU Nodes" value={formatLimit(plan.limits.max_gpu_nodes)} />
                  </div>

                  {/* Features */}
                  <div className="mt-6 pt-6 border-t border-border space-y-2">
                    {plan.features.integrations_enabled && <FeatureItem text="Cloud Integrations" />}
                    {plan.features.forecasting_enabled && <FeatureItem text="Cost Forecasting" />}
                    {plan.features.alerts_enabled && <FeatureItem text="Budget Alerts" />}
                    {plan.features.custom_reports && <FeatureItem text="Custom Reports" />}
                    {plan.features.sso_enabled && <FeatureItem text="SSO Authentication" />}
                    {plan.features.priority_support && <FeatureItem text="Priority Support" />}
                    {plan.features.white_label && <FeatureItem text="White Label" />}
                  </div>
                </CardContent>
              </Card>
            );
          })}
      </div>

      {/* FAQ Section */}
      <Card>
        <CardHeader>
          <CardTitle>Frequently Asked Questions</CardTitle>
          <CardDescription>Everything you need to know about billing</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            <FAQItem
              question="Can I change my plan anytime?"
              answer="Yes, you can upgrade or downgrade your plan at any time. Changes take effect immediately for upgrades, or at the end of your billing period for downgrades."
            />
            <FAQItem
              question="What payment methods do you accept?"
              answer="We accept all major credit cards (Visa, Mastercard, American Express) through Stripe."
            />
            <FAQItem
              question="Is there a free trial?"
              answer="The Free plan is available forever with no credit card required. Paid plans may offer a trial period at checkout."
            />
            <FAQItem
              question="Can I cancel anytime?"
              answer="Yes, you can cancel your subscription at any time. Your access will continue until the end of your billing period."
            />
          </div>
        </CardContent>
      </Card>
    </>
  );
}

function LimitItem({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        <span className="w-4 h-4">{icon}</span>
        <span>{label}:</span>
      </div>
      <span className="font-semibold text-foreground">{value}</span>
    </div>
  );
}

function FeatureItem({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <Check className="w-4 h-4 text-success-600 dark:text-success-500 flex-shrink-0" />
      <span className="text-foreground">{text}</span>
    </div>
  );
}

function FAQItem({ question, answer }: { question: string; answer: string }) {
  return (
    <div>
      <h4 className="font-semibold text-foreground mb-2">{question}</h4>
      <p className="text-sm text-muted-foreground">{answer}</p>
    </div>
  );
}

export default function BillingPage() {
  return (
    <EnterpriseLayout teamName="Demo Team">
      <BillingContent />
    </EnterpriseLayout>
  );
}
