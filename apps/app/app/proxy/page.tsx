"use client";

import { useState } from "react";
import {
  Zap,
  Copy,
  Check,
  Shield,
  BarChart3,
  Clock,
  Globe,
  AlertTriangle,
  ExternalLink,
  Code2,
} from "lucide-react";
import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

const ENDPOINT = "https://proxy.heliox.ai/v1";

const CODE_EXAMPLES = {
  openai: `import openai

client = openai.OpenAI(
    base_url="${ENDPOINT}",
    api_key="YOUR_OPENAI_API_KEY",
    default_headers={
        "X-Heliox-Team": "YOUR_TEAM_ID",
    }
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)`,
  curl: `curl ${ENDPOINT}/chat/completions \\
  -H "Authorization: Bearer YOUR_OPENAI_API_KEY" \\
  -H "X-Heliox-Team: YOUR_TEAM_ID" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`,
  typescript: `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${ENDPOINT}",
  apiKey: process.env.OPENAI_API_KEY,
  defaultHeaders: {
    "X-Heliox-Team": process.env.HELIOX_TEAM_ID,
  },
});

const response = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Hello!" }],
});`,
};

const FEATURES = [
  {
    icon: <BarChart3 className="h-5 w-5" />,
    title: "Real-time cost tracking",
    description: "Every token counted, attributed to the right team and job automatically.",
    color: "#6366f1",
    bg: "rgba(99,102,241,0.08)",
  },
  {
    icon: <Shield className="h-5 w-5" />,
    title: "Budget enforcement",
    description: "Set hard limits per team or project. Requests blocked when budget is exceeded.",
    color: "#10b981",
    bg: "rgba(16,185,129,0.08)",
  },
  {
    icon: <Clock className="h-5 w-5" />,
    title: "Latency monitoring",
    description: "P50/P95/P99 latency per model. Detect regressions before they impact users.",
    color: "#3b82f6",
    bg: "rgba(59,130,246,0.08)",
  },
  {
    icon: <Globe className="h-5 w-5" />,
    title: "Multi-provider support",
    description: "OpenAI, Anthropic, Azure OpenAI, Cohere, and more — one unified endpoint.",
    color: "#8b5cf6",
    bg: "rgba(139,92,246,0.08)",
  },
  {
    icon: <AlertTriangle className="h-5 w-5" />,
    title: "Anomaly detection",
    description: "Automatic spike detection with Slack/email alerts before runaway costs hit.",
    color: "#f59e0b",
    bg: "rgba(245,158,11,0.08)",
  },
  {
    icon: <Code2 className="h-5 w-5" />,
    title: "Zero code changes",
    description: "Just change your base URL. Compatible with all OpenAI-compatible SDKs.",
    color: "#ec4899",
    bg: "rgba(236,72,153,0.08)",
  },
];

const STATS = [
  { label: "Requests proxied", value: "2.4B+", sub: "this month" },
  { label: "Avg latency overhead", value: "<2ms", sub: "p99" },
  { label: "Uptime SLA", value: "99.99%", sub: "last 90 days" },
  { label: "Providers supported", value: "12", sub: "and growing" },
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
      style={{
        background: copied ? "rgba(16,185,129,0.12)" : "rgba(255,255,255,0.08)",
        color: copied ? "#10b981" : "rgba(255,255,255,0.7)",
        border: `1px solid ${copied ? "rgba(16,185,129,0.3)" : "rgba(255,255,255,0.12)"}`,
      }}
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export default function ProxyPage() {
  const [activeTab, setActiveTab] = useState<"openai" | "curl" | "typescript">("openai");

  return (
    <EnterpriseLayout>
      <PageHeader
        title="Heliox Proxy Gateway"
        description="Drop-in OpenAI-compatible proxy that tracks costs, enforces budgets, and monitors every LLM call across your org."
        breadcrumbs={[{ label: "Proxy" }]}
        actions={
          <a
            href="https://docs.heliox.ai/proxy"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-xl border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
            style={{ borderColor: "var(--border)", color: "var(--foreground)" }}
          >
            <ExternalLink className="h-4 w-4" />
            Docs
          </a>
        }
      />

      {/* Stats bar */}
      <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {STATS.map((stat) => (
          <Card key={stat.label}>
            <CardContent className="pt-5 pb-4">
              <p
                className="text-[11px] font-semibold uppercase tracking-widest mb-1"
                style={{ color: "var(--heliox-text-muted)" }}
              >
                {stat.label}
              </p>
              <p className="text-2xl font-bold text-foreground font-mono-tabular">{stat.value}</p>
              <p className="text-xs mt-0.5" style={{ color: "var(--heliox-text-muted)" }}>
                {stat.sub}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Quick start */}
      <Card className="mb-8">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Quick start</CardTitle>
              <CardDescription>
                Change your <code className="rounded bg-muted px-1 py-0.5 text-xs">base_url</code> — no other code changes needed
              </CardDescription>
            </div>
            <Badge variant="success">OpenAI compatible</Badge>
          </div>
          {/* Tabs */}
          <div className="flex gap-1 mt-4">
            {(["openai", "curl", "typescript"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className="rounded-lg px-3 py-1.5 text-sm font-medium transition-all"
                style={{
                  background: activeTab === tab ? "#6366f1" : "transparent",
                  color: activeTab === tab ? "#fff" : "var(--heliox-text-muted)",
                  border: `1px solid ${activeTab === tab ? "#6366f1" : "var(--border)"}`,
                }}
              >
                {tab === "openai" ? "Python" : tab === "typescript" ? "TypeScript" : "cURL"}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          <div
            className="relative rounded-xl overflow-hidden"
            style={{ background: "#0f0f17", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/8">
              <span className="text-xs font-medium" style={{ color: "rgba(255,255,255,0.4)" }}>
                {activeTab === "openai" ? "example.py" : activeTab === "typescript" ? "example.ts" : "terminal"}
              </span>
              <CopyButton text={CODE_EXAMPLES[activeTab]} />
            </div>
            <pre
              className="overflow-x-auto p-5 text-sm leading-relaxed"
              style={{ color: "#e2e8f0", fontFamily: "var(--font-mono, monospace)" }}
            >
              <code>{CODE_EXAMPLES[activeTab]}</code>
            </pre>
          </div>
        </CardContent>
      </Card>

      {/* Features grid */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-foreground mb-4">What you get</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <Card key={f.title} className="group transition-all duration-200 hover:-translate-y-px">
              <CardContent className="pt-5">
                <div
                  className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl"
                  style={{ background: f.bg, color: f.color }}
                >
                  {f.icon}
                </div>
                <h3 className="font-semibold text-foreground mb-1">{f.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--heliox-text-muted)" }}>
                  {f.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Endpoint card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-indigo-500" />
            Your proxy endpoint
          </CardTitle>
          <CardDescription>Replace your OpenAI base URL with this endpoint</CardDescription>
        </CardHeader>
        <CardContent>
          <div
            className="flex items-center justify-between rounded-xl px-4 py-3"
            style={{ background: "var(--muted)", border: "1px solid var(--border)" }}
          >
            <code className="text-sm font-mono text-foreground">{ENDPOINT}</code>
            <CopyButton text={ENDPOINT} />
          </div>
          <p className="mt-3 text-xs" style={{ color: "var(--heliox-text-muted)" }}>
            Pass your original provider API key via the <code className="rounded bg-muted px-1">Authorization</code> header as usual.
            Add <code className="rounded bg-muted px-1">X-Heliox-Team</code> to attribute costs to your team.
          </p>
        </CardContent>
      </Card>
    </EnterpriseLayout>
  );
}
