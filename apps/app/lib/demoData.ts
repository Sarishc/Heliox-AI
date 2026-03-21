/**
 * DEMO MODE DATA GENERATOR
 * 
 * Generates realistic enterprise-scale mock data for investor demos
 * and product showcases. All data appears production-grade.
 */

export interface DemoConfig {
  monthlySpend: number;
  activeGPUs: number;
  teams: number;
  savingsPercent: number;
}

// Default demo configuration (realistic $2-3M/month company)
const DEFAULT_DEMO_CONFIG: DemoConfig = {
  monthlySpend: 2400000, // $2.4M/month
  activeGPUs: 847,
  teams: 23,
  savingsPercent: 18.5,
};

/**
 * Executive KPIs for top-of-dashboard strip
 */
export function generateExecutiveKPIs(config: DemoConfig = DEFAULT_DEMO_CONFIG) {
  return [
    {
      label: "GPU Spend (MTD)",
      value: config.monthlySpend * 0.67, // 67% through month
      format: "currency" as const,
      change: 12.3,
      changeLabel: "vs last month",
    },
    {
      label: "Active GPUs",
      value: config.activeGPUs,
      format: "number" as const,
      change: -3.2,
      changeLabel: "vs last week",
    },
    {
      label: "Cost per Request",
      value: "$0.0042",
      format: "custom" as const,
      change: -8.7,
      changeLabel: "vs last month",
    },
    {
      label: "Optimization Savings",
      value: config.savingsPercent,
      unit: "%",
      format: "custom" as const,
      change: 2.1,
      changeLabel: "vs last month",
    },
  ];
}

/**
 * Top Teams by GPU Spend (for enterprise table)
 */
export function generateTopTeams() {
  const teams = [
    { name: "ML Research", lead: "Sarah Chen", budget: 850000 },
    { name: "Production AI", lead: "Marcus Williams", budget: 620000 },
    { name: "Computer Vision", lead: "Aisha Patel", budget: 480000 },
    { name: "NLP Platform", lead: "James Rodriguez", budget: 320000 },
    { name: "Data Engineering", lead: "Emily Zhang", budget: 180000 },
    { name: "Experimentation", lead: "David Kim", budget: 145000 },
    { name: "Recommendations", lead: "Lisa Johnson", budget: 98000 },
    { name: "Search Infrastructure", lead: "Tom Anderson", budget: 87000 },
    { name: "Model Serving", lead: "Anna Kowalski", budget: 72000 },
    { name: "QA/Testing", lead: "Robert Singh", budget: 45000 },
  ];

  return teams.map((team, i) => ({
    id: `team-${i}`,
    team: team.name,
    lead: team.lead,
    spend: team.budget * (0.6 + Math.random() * 0.3), // 60-90% of budget used
    budget: team.budget,
    utilizationPercent: Math.floor(65 + Math.random() * 25),
    activeJobs: Math.floor(5 + Math.random() * 45),
    gpuHours: Math.floor(1000 + Math.random() * 8000),
  }));
}

/**
 * Top Models by Cost
 */
export function generateTopModels() {
  const models = [
    { name: "A100 80GB", provider: "AWS", hourlyRate: 32.77 },
    { name: "H100 SXM", provider: "GCP", hourlyRate: 45.00 },
    { name: "A100 40GB", provider: "AWS", hourlyRate: 24.48 },
    { name: "V100 32GB", provider: "Azure", hourlyRate: 18.90 },
    { name: "A10G", provider: "AWS", hourlyRate: 5.22 },
    { name: "T4", provider: "GCP", hourlyRate: 3.47 },
    { name: "L4", provider: "GCP", hourlyRate: 4.12 },
    { name: "RTX 6000", provider: "On-Prem", hourlyRate: 8.50 },
  ];

  return models.map((model, i) => {
    const hours = Math.floor(500 + Math.random() * 8000);
    return {
      id: `model-${i}`,
      model: model.name,
      provider: model.provider,
      instances: Math.floor(10 + Math.random() * 120),
      hours: hours,
      cost: hours * model.hourlyRate,
      utilizationPercent: Math.floor(55 + Math.random() * 35),
    };
  });
}

/**
 * Provider Cost Breakdown
 */
export function generateProviderBreakdown() {
  return [
    {
      id: "aws",
      provider: "AWS",
      region: "us-east-1",
      instances: 342,
      cost: 1240000,
      change: 8.2,
      services: ["EC2", "SageMaker", "EKS"],
    },
    {
      id: "gcp",
      provider: "Google Cloud",
      region: "us-central1",
      instances: 284,
      cost: 890000,
      change: -3.5,
      services: ["Compute Engine", "Vertex AI", "GKE"],
    },
    {
      id: "azure",
      provider: "Azure",
      region: "East US",
      instances: 156,
      cost: 420000,
      change: 15.7,
      services: ["Virtual Machines", "ML Studio", "AKS"],
    },
    {
      id: "onprem",
      provider: "On-Premise",
      region: "Datacenter-1",
      instances: 65,
      cost: 180000,
      change: 0,
      services: ["Internal GPU Cluster"],
    },
  ];
}

/**
 * Idle GPU Jobs (Optimization Insights)
 */
export function generateIdleJobs() {
  const jobs = [
    { name: "training-resnet-v2", team: "ML Research", runtime: 142 },
    { name: "inference-batch-nightly", team: "Production AI", runtime: 89 },
    { name: "data-preprocessing-001", team: "Data Engineering", runtime: 67 },
    { name: "model-eval-baseline", team: "Experimentation", runtime: 45 },
    { name: "feature-extraction-pipeline", team: "Computer Vision", runtime: 38 },
    { name: "embeddings-generation", team: "NLP Platform", runtime: 29 },
  ];

  return jobs.map((job, i) => ({
    id: `job-${i}`,
    jobName: job.name,
    team: job.team,
    gpuModel: ["A100", "H100", "V100", "A10G"][Math.floor(Math.random() * 4)],
    idleMinutes: job.runtime,
    estimatedWaste: Math.floor(job.runtime * (5 + Math.random() * 10)),
    status: i < 2 ? "Critical" : i < 4 ? "Warning" : "Info",
  }));
}

/**
 * Daily Spend Trend (30 days)
 */
export function generateDailySpendTrend(days: number = 30) {
  const baseSpend = 75000; // $75k/day average
  const data = [];
  
  for (let i = 0; i < days; i++) {
    const date = new Date();
    date.setDate(date.getDate() - (days - i));
    
    // Add weekly pattern (lower on weekends)
    const dayOfWeek = date.getDay();
    const weekendFactor = dayOfWeek === 0 || dayOfWeek === 6 ? 0.6 : 1.0;
    
    // Add some realistic variation
    const variation = 0.85 + Math.random() * 0.3;
    const trend = 1 + (i / days) * 0.15; // 15% growth over period
    
    data.push({
      date: date.toISOString().split("T")[0],
      spend: Math.floor(baseSpend * weekendFactor * variation * trend),
      forecast: i > days - 8 ? Math.floor(baseSpend * variation * trend * 1.05) : null,
    });
  }
  
  return data;
}

/**
 * Cost by Hour Heatmap (for utilization analysis)
 */
export function generateHourlyHeatmap() {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const data: Array<{ day: string; hour: number; utilization: number }> = [];
  
  days.forEach((day, dayIndex) => {
    for (let hour = 0; hour < 24; hour++) {
      // Business hours have higher utilization
      const isBusinessHours = hour >= 9 && hour <= 18;
      const isWeekend = dayIndex >= 5;
      
      let baseUtilization = 30;
      if (isBusinessHours && !isWeekend) {
        baseUtilization = 75;
      } else if (isBusinessHours && isWeekend) {
        baseUtilization = 45;
      } else if (!isBusinessHours && !isWeekend) {
        baseUtilization = 50;
      }
      
      data.push({
        day,
        hour,
        utilization: Math.floor(baseUtilization + Math.random() * 15),
      });
    }
  });
  
  return data;
}

/**
 * Forecast Data (7-day prediction)
 */
export function generateForecastData() {
  const baseSpend = 78000;
  const data = [];
  
  for (let i = 0; i < 7; i++) {
    const date = new Date();
    date.setDate(date.getDate() + i + 1);
    
    const dayOfWeek = date.getDay();
    const weekendFactor = dayOfWeek === 0 || dayOfWeek === 6 ? 0.65 : 1.0;
    const trend = 1 + (i / 7) * 0.08;
    
    data.push({
      date: date.toISOString().split("T")[0],
      predicted: Math.floor(baseSpend * weekendFactor * trend),
      lower: Math.floor(baseSpend * weekendFactor * trend * 0.85),
      upper: Math.floor(baseSpend * weekendFactor * trend * 1.15),
      confidence: 85 + Math.floor(Math.random() * 10),
    });
  }
  
  return data;
}

/**
 * Demo forecast in API response shape (for ForecastCard)
 */
export function generateDemoForecastApiResponse(horizonDays: number = 7) {
  const historicalDays = 14;
  const historical: Array<{ date: string; value: number }> = [];
  const forecast: Array<{ date: string; value: number; lower_bound: number; upper_bound: number }> = [];
  const baseSpend = 82000;

  for (let i = -historicalDays; i < 0; i++) {
    const date = new Date();
    date.setDate(date.getDate() + i);
    const d = date.toISOString().split("T")[0];
    const dayOfWeek = date.getDay();
    const weekendFactor = dayOfWeek === 0 || dayOfWeek === 6 ? 0.6 : 1.0;
    historical.push({
      date: d,
      value: Math.floor(baseSpend * weekendFactor * (0.9 + Math.random() * 0.2)),
    });
  }

  for (let i = 0; i < horizonDays; i++) {
    const date = new Date();
    date.setDate(date.getDate() + i);
    const d = date.toISOString().split("T")[0];
    const dayOfWeek = date.getDay();
    const weekendFactor = dayOfWeek === 0 || dayOfWeek === 6 ? 0.65 : 1.0;
    const val = Math.floor(baseSpend * weekendFactor * (1 + (i / horizonDays) * 0.06));
    forecast.push({
      date: d,
      value: val,
      lower_bound: Math.floor(val * 0.88),
      upper_bound: Math.floor(val * 1.14),
    });
  }

  return {
    provider: null,
    gpu_type: null,
    horizon_days: horizonDays,
    forecast_method: "moving_average",
    historical,
    forecast,
    metadata: {
      historical_data_points: historical.length,
      forecast_generated_at: new Date().toISOString(),
    },
  };
}

/**
 * Demo daily spend for SpendTrendChart (returns { date: "MMM dd", cost } for chart)
 */
export function generateDemoDailySpendBetween(startDate: string, endDate: string) {
  const result: Array<{ date: string; cost: number }> = [];
  const start = new Date(startDate);
  const end = new Date(endDate);
  const baseSpend = 72000;
  let d = new Date(start);

  while (d <= end) {
    const dayOfWeek = d.getDay();
    const weekendFactor = dayOfWeek === 0 || dayOfWeek === 6 ? 0.62 : 1.0;
    result.push({
      date: d.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      cost: Math.floor(baseSpend * weekendFactor * (0.88 + Math.random() * 0.24)),
    });
    d.setDate(d.getDate() + 1);
    d = new Date(d);
  }
  return result;
}

/**
 * Demo cost by model for CostByModelChart (API shape: model_name, total_cost_usd, job_count, runtime_share)
 */
export function generateDemoCostByModel() {
  const models = [
    { name: "A100 80GB", cost: 124000 },
    { name: "H100 SXM", cost: 98000 },
    { name: "A100 40GB", cost: 72000 },
    { name: "V100 32GB", cost: 45000 },
    { name: "A10G", cost: 32000 },
    { name: "L4", cost: 18000 },
    { name: "T4", cost: 12000 },
  ];
  const total = models.reduce((s, m) => s + m.cost, 0);
  return models.map((m) => {
    const cost = m.cost + Math.floor(Math.random() * m.cost * 0.1);
    return {
      model_name: m.name,
      total_cost_usd: cost,
      job_count: Math.floor(20 + Math.random() * 80),
      runtime_share: cost / total,
      explain: undefined,
    };
  });
}

/**
 * Demo cost by team for CostByTeamChart (API shape: team_name, team_id, total_cost_usd, job_count, cost_share)
 */
export function generateDemoCostByTeam() {
  const teams = [
    { name: "ML Research", value: 420000 },
    { name: "Production AI", value: 280000 },
    { name: "Computer Vision", value: 195000 },
    { name: "NLP Platform", value: 145000 },
    { name: "Data Engineering", value: 98000 },
    { name: "Experimentation", value: 72000 },
  ];
  const total = teams.reduce((s, t) => s + t.value, 0);
  return teams.map((t, i) => {
    const value = t.value + Math.floor(Math.random() * t.value * 0.08);
    return {
      team_name: t.name,
      team_id: `team-${i + 1}`,
      total_cost_usd: value,
      job_count: Math.floor(15 + Math.random() * 60),
      cost_share: value / total,
      explain: undefined,
    };
  });
}

/**
 * Check if demo mode is active
 */
export function isDemoMode(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem("heliox_demo_mode") === "true";
}

/**
 * Enable/disable demo mode
 */
export function setDemoMode(enabled: boolean) {
  if (typeof window === "undefined") return;
  
  if (enabled) {
    localStorage.setItem("heliox_demo_mode", "true");
  } else {
    localStorage.removeItem("heliox_demo_mode");
  }
  
  // Reload to apply changes
  window.location.reload();
}
