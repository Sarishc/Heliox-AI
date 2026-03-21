"use client";

import BetaAccessGate from "@/components/BetaAccessGate";
import AppShell from "@/components/AppShell";
import AnomalyCard from "@/components/AnomalyCard";
import SlackWebhookCard from "@/components/SlackWebhookCard";
import EmailAlertsCard from "@/components/EmailAlertsCard";
import BudgetEventsList from "@/components/BudgetEventsList";

function AlertsContent() {
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Alerts</p>
        <h1 className="text-2xl font-semibold text-slate-900">
          Proactive risk monitoring
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Configure Slack and email notifications. Review anomaly signals and budget events.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
        <AnomalyCard />
        <div className="space-y-6">
          <SlackWebhookCard />
          <EmailAlertsCard />
        </div>
      </div>

      <BudgetEventsList />
    </div>
  );
}

export default function AlertsPage() {
  return (
    <BetaAccessGate>
      <AppShell>
        <AlertsContent />
      </AppShell>
    </BetaAccessGate>
  );
}
