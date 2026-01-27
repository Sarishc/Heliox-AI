"use client";

import { useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import BetaAccessGate from "@/components/BetaAccessGate";
import { fetchJson, getApiUrl } from "@/lib/api";

type ReportSection =
  | "overview_kpis"
  | "daily_spend"
  | "idle_waste"
  | "top_models"
  | "top_recommendations";

interface ReportConfig {
  start_date: string;
  end_date: string;
  filters: {
    environment?: string | null;
    model?: string | null;
    team?: string | null;
  };
  sections: ReportSection[];
}

interface SavedReport {
  id: string;
  team_id: string;
  name: string;
  description?: string | null;
  config: ReportConfig;
  created_at: string;
  updated_at: string;
}

interface ShareResponse {
  share_url: string;
  expires_at: string;
}

const SECTION_OPTIONS: { id: ReportSection; label: string }[] = [
  { id: "overview_kpis", label: "Overview KPIs" },
  { id: "daily_spend", label: "Daily Spend" },
  { id: "idle_waste", label: "Idle Waste" },
  { id: "top_models", label: "Top Models" },
  { id: "top_recommendations", label: "Top Recommendations" },
];

function formatDateInput(date: Date) {
  return date.toISOString().slice(0, 10);
}

function ReportsContent() {
  const [reports, setReports] = useState<SavedReport[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [startDate, setStartDate] = useState(formatDateInput(new Date(Date.now() - 6 * 86400000)));
  const [endDate, setEndDate] = useState(formatDateInput(new Date()));
  const [environment, setEnvironment] = useState("");
  const [modelFilter, setModelFilter] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [sections, setSections] = useState<ReportSection[]>([
    "overview_kpis",
    "daily_spend",
    "idle_waste",
    "top_models",
    "top_recommendations",
  ]);
  const [shareExpiry, setShareExpiry] = useState("7");
  const [shareLink, setShareLink] = useState<string | null>(null);

  const loadReports = async () => {
    setLoading(true);
    try {
      const data = await fetchJson<SavedReport[]>("/api/v1/reports");
      setReports(data);
    } catch {
      setReports([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, []);

  const resetForm = () => {
    setEditingId(null);
    setName("");
    setDescription("");
    setStartDate(formatDateInput(new Date(Date.now() - 6 * 86400000)));
    setEndDate(formatDateInput(new Date()));
    setEnvironment("");
    setModelFilter("");
    setTeamFilter("");
    setSections([
      "overview_kpis",
      "daily_spend",
      "idle_waste",
      "top_models",
      "top_recommendations",
    ]);
  };

  const buildConfig = (): ReportConfig => ({
    start_date: startDate,
    end_date: endDate,
    filters: {
      environment: environment || null,
      model: modelFilter || null,
      team: teamFilter || null,
    },
    sections,
  });

  const handleSave = async () => {
    const payload = {
      name,
      description: description || null,
      config: buildConfig(),
    };
    if (!name.trim()) return;
    if (editingId) {
      await fetchJson(`/api/v1/reports/${editingId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    } else {
      await fetchJson("/api/v1/reports", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    await loadReports();
    resetForm();
  };

  const handleEdit = (report: SavedReport) => {
    setEditingId(report.id);
    setName(report.name);
    setDescription(report.description ?? "");
    setStartDate(report.config.start_date);
    setEndDate(report.config.end_date);
    setEnvironment(report.config.filters.environment ?? "");
    setModelFilter(report.config.filters.model ?? "");
    setTeamFilter(report.config.filters.team ?? "");
    setSections(report.config.sections ?? []);
  };

  const handleDelete = async (reportId: string) => {
    await fetchJson(`/api/v1/reports/${reportId}`, { method: "DELETE" });
    await loadReports();
  };

  const handleRun = async (reportId: string, fileType: "csv" | "pdf") => {
    const run = await fetchJson<{ id: string }>(`/api/v1/reports/${reportId}/run`, {
      method: "POST",
      body: JSON.stringify({ file_type: fileType }),
    });
    window.open(getApiUrl(`/api/v1/reports/runs/${run.id}/download`), "_blank");
  };

  const handleShare = async (reportId: string) => {
    const response = await fetchJson<ShareResponse>(`/api/v1/reports/${reportId}/share`, {
      method: "POST",
      body: JSON.stringify({ expires_in_days: Number(shareExpiry) || undefined }),
    });
    setShareLink(response.share_url);
  };

  const formTitle = useMemo(
    () => (editingId ? "Edit saved report" : "Create a saved report"),
    [editingId]
  );

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Reports</p>
        <h1 className="text-2xl font-semibold text-slate-900">Saved Reports & Exports</h1>
        <p className="mt-2 text-sm text-slate-500">
          Build board-ready reports, export CSV/PDF, and create share links.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">{formTitle}</h2>
          <div className="grid gap-4">
            <input
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              placeholder="Report name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <textarea
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              placeholder="Description (optional)"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
            <div className="grid gap-3 md:grid-cols-2">
              <label className="text-sm text-slate-600">
                Start date
                <input
                  type="date"
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  value={startDate}
                  onChange={(event) => setStartDate(event.target.value)}
                />
              </label>
              <label className="text-sm text-slate-600">
                End date
                <input
                  type="date"
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  value={endDate}
                  onChange={(event) => setEndDate(event.target.value)}
                />
              </label>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <label className="text-sm text-slate-600">
                Environment
                <input
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  placeholder="prod/staging/dev"
                  value={environment}
                  onChange={(event) => setEnvironment(event.target.value)}
                />
              </label>
              <label className="text-sm text-slate-600">
                Model filter
                <input
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  placeholder="Model name"
                  value={modelFilter}
                  onChange={(event) => setModelFilter(event.target.value)}
                />
              </label>
              <label className="text-sm text-slate-600">
                Team filter
                <input
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  placeholder="Team name"
                  value={teamFilter}
                  onChange={(event) => setTeamFilter(event.target.value)}
                />
              </label>
            </div>
            <div>
              <p className="text-sm font-medium text-slate-700">Sections</p>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                {SECTION_OPTIONS.map((section) => (
                  <label key={section.id} className="flex items-center gap-2 text-sm text-slate-600">
                    <input
                      type="checkbox"
                      checked={sections.includes(section.id)}
                      onChange={(event) => {
                        if (event.target.checked) {
                          setSections((prev) => [...prev, section.id]);
                        } else {
                          setSections((prev) => prev.filter((item) => item !== section.id));
                        }
                      }}
                    />
                    {section.label}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white"
                onClick={handleSave}
              >
                {editingId ? "Update report" : "Save report"}
              </button>
              {editingId && (
                <button
                  className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium"
                  onClick={resetForm}
                >
                  Cancel edit
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Share link</h2>
          <div className="space-y-3 text-sm text-slate-600">
            <label className="block">
              Expiry (days)
              <input
                type="number"
                min={1}
                max={90}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={shareExpiry}
                onChange={(event) => setShareExpiry(event.target.value)}
              />
            </label>
            {shareLink ? (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
                <p className="font-semibold text-slate-700">Share URL</p>
                <p className="break-all text-slate-600">{shareLink}</p>
              </div>
            ) : (
              <p className="text-slate-500">Create a share link from a report in the list.</p>
            )}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">Saved reports</h2>
          {loading && <span className="text-sm text-slate-400">Loading...</span>}
        </div>
        <div className="mt-4 space-y-4">
          {reports.map((report) => (
            <div
              key={report.id}
              className="rounded-xl border border-slate-200 bg-slate-50 p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-800">{report.name}</p>
                  <p className="text-xs text-slate-500">{report.description}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs"
                    onClick={() => handleRun(report.id, "csv")}
                  >
                    Export CSV
                  </button>
                  <button
                    className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs"
                    onClick={() => handleRun(report.id, "pdf")}
                  >
                    Export PDF
                  </button>
                  <button
                    className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs text-blue-700"
                    onClick={() => handleShare(report.id)}
                  >
                    Create share link
                  </button>
                  <button
                    className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs"
                    onClick={() => handleEdit(report)}
                  >
                    Edit
                  </button>
                  <button
                    className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs text-rose-700"
                    onClick={() => handleDelete(report.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
              <div className="mt-3 text-xs text-slate-500">
                {report.config.sections.length} sections • {report.config.start_date} to{" "}
                {report.config.end_date}
              </div>
            </div>
          ))}
          {!reports.length && !loading && (
            <div className="text-sm text-slate-500">No saved reports yet.</div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ReportsPage() {
  return (
    <BetaAccessGate>
      <AppShell>
        <ReportsContent />
      </AppShell>
    </BetaAccessGate>
  );
}
