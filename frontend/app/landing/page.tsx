"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Cpu,
  Shield,
  Sparkles,
} from "lucide-react";
import { fetchApi } from "@/lib/api";

type FormState = {
  name: string;
  email: string;
  company: string;
  role: string;
  source: string;
};

type SubmitState = "idle" | "submitting" | "success" | "error";

const defaultForm: FormState = {
  name: "",
  email: "",
  company: "",
  role: "",
  source: "landing",
};

const features = [
  {
    title: "Forecast GPU spend with confidence",
    description: "Blend historical signals with ML to project usage and costs.",
    icon: <BarChart3 className="w-6 h-6 text-blue-600" />,
  },
  {
    title: "Automatic cost-saving playbooks",
    description:
      "Idle GPU detection, off-hours scheduling, and right-sizing guidance.",
    icon: <Sparkles className="w-6 h-6 text-purple-600" />,
  },
  {
    title: "Team-aware insights",
    description: "Rollups by team, model, and provider for clean chargeback.",
    icon: <Shield className="w-6 h-6 text-emerald-600" />,
  },
];

const pricingTiers = [
  {
    name: "Starter",
    price: "$0",
    blurb: "Fast start with weekly recommendations.",
    cta: "Join waitlist",
  },
  {
    name: "Growth",
    price: "$499/mo",
    blurb: "Daily insights, alerts, and forecasting.",
    cta: "Talk to us",
  },
  {
    name: "Enterprise",
    price: "Custom",
    blurb: "Guardrails, SSO, and dedicated support.",
    cta: "Book demo",
  },
];

const problems = [
  "GPU costs spike overnight and finance asks for answers.",
  "Teams hoard capacity; idle spend hides in shared clusters.",
  "Forecasting next month's bill is still spreadsheets + guesswork.",
];

function track(event: string, payload?: Record<string, unknown>) {
  // Basic analytics-friendly logging for MVP
  // eslint-disable-next-line no-console
  console.log(`[analytics] ${event}`, payload || {});
}

export default function LandingPage() {
  const [form, setForm] = useState<FormState>(defaultForm);
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    track("landing_view", { source: form.source });
  }, [form.source]);

  const isDisabled = useMemo(
    () =>
      submitState === "submitting" ||
      form.email.trim().length === 0 ||
      !form.email.includes("@"),
    [submitState, form.email]
  );

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSubmitState("submitting");
    track("waitlist_submit_start", { email: form.email, source: form.source });

    try {
      const response = await fetchApi("/api/v1/public/waitlist", {
        method: "POST",
        body: JSON.stringify(form),
      });

      if (response.status === 409) {
        track("waitlist_submit_duplicate", { email: form.email });
        setError("You're already on the list. We'll keep you posted!");
        setSubmitState("error");
        return;
      }

      if (!response.ok) {
        const message = "Something went wrong. Please try again.";
        setError(message);
        setSubmitState("error");
        track("waitlist_submit_error", { status: response.status });
        return;
      }

      setSubmitState("success");
      setForm(defaultForm);
      track("waitlist_submit_success", { email: form.email });
    } catch (err) {
      setError("Network error. Please retry in a moment.");
      setSubmitState("error");
      track("waitlist_submit_network_error", { message: String(err) });
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-white via-blue-50/60 to-white text-gray-900">
      <header className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-14 pb-10">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-4 max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-100 text-blue-800 text-xs font-semibold">
              <Sparkles className="w-4 h-4" />
              GPU Cost Intelligence for AI Teams
            </div>
            <h1 className="text-4xl sm:text-5xl font-bold leading-tight">
              Predictable GPU spend. Confident AI scaling.
            </h1>
            <p className="text-lg text-gray-700">
              Heliox gives finance and ML teams a single pane to forecast spend,
              catch waste, and ship confidently without surprise bills.
            </p>
            <div className="flex flex-wrap gap-3">
              <a
                href="#waitlist"
                onClick={() => track("cta_click", { target: "hero_waitlist" })}
                className="inline-flex items-center gap-2 px-5 py-3 rounded-lg bg-blue-600 text-white font-semibold shadow hover:bg-blue-700 transition-colors"
              >
                Join the waitlist <ArrowRight className="w-4 h-4" />
              </a>
              <a
                href="#pricing"
                onClick={() => track("cta_click", { target: "hero_pricing" })}
                className="inline-flex items-center gap-2 px-5 py-3 rounded-lg border border-gray-300 text-gray-800 font-semibold hover:bg-gray-50 transition-colors"
              >
                See pricing preview
              </a>
            </div>
          </div>
          <div className="w-full max-w-md bg-white border border-gray-200 rounded-xl shadow-sm p-6">
            <div className="flex items-center gap-2 mb-4">
              <Cpu className="w-5 h-5 text-blue-600" />
              <p className="text-sm font-semibold text-gray-800">
                What finance wants to know
              </p>
            </div>
            <ul className="space-y-3 text-sm text-gray-700">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5" />
                Where did yesterday's spike come from?
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5" />
                Which teams/models are wasting GPUs?
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5" />
                What will we spend next month?
              </li>
            </ul>
          </div>
        </div>
      </header>

      <main className="space-y-16 pb-16">
        <section className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="space-y-4">
                <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide">
                  The problem
                </p>
                <h2 className="text-2xl font-bold text-gray-900">
                  GPU costs are volatile, and guesses aren't good enough.
                </h2>
                <p className="text-gray-700">
                  Heliox brings cost, usage, and recommendations into one live
                  view so you can course-correct before month-end.
                </p>
              </div>
              <div className="grid gap-3">
                {problems.map((item) => (
                  <div
                    key={item}
                    className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 bg-gray-50"
                  >
                    <Shield className="w-5 h-5 text-red-500" />
                    <p className="text-sm text-gray-800">{item}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-gradient-to-br from-blue-600 to-indigo-600 text-white rounded-2xl p-8 shadow-lg">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="space-y-3 max-w-3xl">
                <p className="text-xs font-semibold uppercase tracking-wide text-blue-100">
                  The solution
                </p>
                <h2 className="text-3xl font-bold">
                  Forecast, govern, and save before the bill arrives.
                </h2>
                <p className="text-blue-50">
                  Daily forecasts, anomaly detection, and ready-to-run
                  recommendations keep teams on budget without slowing velocity.
                </p>
                <div className="flex flex-wrap gap-2">
                  <span className="px-3 py-1 rounded-full bg-white/10 border border-white/20 text-sm">
                    Budget guardrails
                  </span>
                  <span className="px-3 py-1 rounded-full bg-white/10 border border-white/20 text-sm">
                    ML-powered forecasts
                  </span>
                  <span className="px-3 py-1 rounded-full bg-white/10 border border-white/20 text-sm">
                    Severity-ranked playbooks
                  </span>
                </div>
              </div>
              <a
                href="#waitlist"
                onClick={() => track("cta_click", { target: "solution_waitlist" })}
                className="inline-flex items-center gap-2 px-5 py-3 bg-white text-blue-700 font-semibold rounded-lg shadow hover:bg-blue-50 transition-colors"
              >
                Get early access <ArrowRight className="w-4 h-4" />
              </a>
            </div>
          </div>
        </section>

        <section className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8" id="features">
          <div className="space-y-3 mb-6">
            <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide">
              Features
            </p>
            <h2 className="text-2xl font-bold text-gray-900">
              Built for finance + ML teams
            </h2>
            <p className="text-gray-700">
              Heliox bridges financial accountability with ML velocity.
            </p>
          </div>
          <div className="grid gap-6 md:grid-cols-3">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm"
              >
                <div className="p-2 rounded-md bg-blue-50 w-fit mb-3">
                  {feature.icon}
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                  {feature.title}
                </h3>
                <p className="text-sm text-gray-700">{feature.description}</p>
              </div>
            ))}
          </div>
        </section>

        <section
          className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8"
          id="pricing"
        >
          <div className="space-y-3 mb-6">
            <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide">
              Pricing preview
            </p>
            <h2 className="text-2xl font-bold text-gray-900">
              Start simple, scale securely
            </h2>
            <p className="text-gray-700">
              Early-access pricing designed for quick pilots and governance at
              scale.
            </p>
          </div>
          <div className="grid gap-6 md:grid-cols-3">
            {pricingTiers.map((tier) => (
              <div
                key={tier.name}
                className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm flex flex-col"
              >
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-4 h-4 text-blue-600" />
                  <p className="text-sm font-semibold text-gray-800 uppercase">
                    {tier.name}
                  </p>
                </div>
                <p className="text-3xl font-bold text-gray-900 mb-2">
                  {tier.price}
                </p>
                <p className="text-sm text-gray-700 mb-4 flex-1">{tier.blurb}</p>
                <button
                  onClick={() =>
                    track("cta_click", { target: `pricing_${tier.name}` })
                  }
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 text-gray-800 font-semibold hover:bg-gray-50 transition-colors"
                >
                  {tier.cta}
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </section>

        <section
          className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8"
          id="waitlist"
        >
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8 grid gap-10 lg:grid-cols-2">
            <div className="space-y-4">
              <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide">
                Get on the list
              </p>
              <h2 className="text-3xl font-bold text-gray-900">
                Be first to try Heliox
              </h2>
              <p className="text-gray-700">
                We’re onboarding a handful of teams for early access. Tell us
                where to reach you and we’ll send setup details.
              </p>
              <ul className="space-y-2 text-sm text-gray-700">
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5" />
                  <span>2-week onboarding with dashboards + forecasts.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5" />
                  <span>Hands-on cost playbooks and alerting setup.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5" />
                  <span>No spam. Just readiness updates.</span>
                </li>
              </ul>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-700">
                    Name
                  </label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) =>
                      setForm((prev) => ({ ...prev, name: e.target.value }))
                    }
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="Alex Kim"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-700">
                    Email *
                  </label>
                  <input
                    required
                    type="email"
                    value={form.email}
                    onChange={(e) =>
                      setForm((prev) => ({ ...prev, email: e.target.value }))
                    }
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="alex@company.com"
                  />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-700">
                    Company
                  </label>
                  <input
                    type="text"
                    value={form.company}
                    onChange={(e) =>
                      setForm((prev) => ({ ...prev, company: e.target.value }))
                    }
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="Heliox AI"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-700">
                    Role
                  </label>
                  <input
                    type="text"
                    value={form.role}
                    onChange={(e) =>
                      setForm((prev) => ({ ...prev, role: e.target.value }))
                    }
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="Head of ML"
                  />
                </div>
              </div>

              <input
                type="hidden"
                value={form.source}
                onChange={() => {}}
                readOnly
              />

              {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </div>
              )}

              {submitState === "success" && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                  Thanks! You're on the list. We'll reach out shortly.
                </div>
              )}

              <button
                type="submit"
                disabled={isDisabled}
                className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 text-white font-semibold px-4 py-3 shadow hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-600 transition-colors"
              >
                {submitState === "submitting" ? "Submitting..." : "Join waitlist"}
                <ArrowRight className="w-4 h-4" />
              </button>

              <p className="text-xs text-gray-500">
                We respect your inbox. By joining, you agree to receive product
                updates about Heliox.
              </p>
            </form>
          </div>
        </section>
      </main>
    </div>
  );
}
