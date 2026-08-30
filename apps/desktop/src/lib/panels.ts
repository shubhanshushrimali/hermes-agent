/**
 * Crew Panel — Shows which CrewAI agents are active and their progress.
 * Daemon Panel — Monitor/control 24/7 background agents.
 * Cost Dashboard — LiteLLM spend tracking.
 */

import { useState, useCallback, useEffect } from 'react';

// ============================================================================
// Crew Panel
// ============================================================================

export interface CrewStatus {
  active_crew: string | null;
  active_agents: string[];
  available_crews: Record<string, {
    name: string;
    description: string;
    agents: string[];
  }>;
  crewai_available: boolean;
}

export interface UseCrewPanelReturn {
  status: CrewStatus | null;
  isActive: boolean;
  refresh: () => Promise<void>;
  startCrew: (crewName: string, task: string) => Promise<void>;
}

export function useCrewPanel(): UseCrewPanelReturn {
  const [status, setStatus] = useState<CrewStatus | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/crew/status');
      if (res.ok) setStatus(await res.json());
    } catch { /* ignore */ }
  }, []);

  const startCrew = useCallback(async (crewName: string, task: string) => {
    await fetch('/api/crew/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ crew: crewName, task }),
    });
    await refresh();
  }, [refresh]);

  useEffect(() => { refresh(); }, [refresh]);

  return {
    status,
    isActive: !!status?.active_crew,
    refresh,
    startCrew,
  };
}

// ============================================================================
// Daemon Panel
// ============================================================================

export interface DaemonHealth {
  status: string;
  uptime_seconds: number;
  uptime_human: string;
  jobs_processed: number;
  daily_spend_usd: number;
  budget_remaining_usd: number;
  last_heartbeat: string;
  pending_jobs: number;
}

export interface DaemonJob {
  id: string;
  name: string;
  status: string;
  prompt: string;
  schedule: string;
  priority: number;
  created_at: string;
  result?: string;
  error?: string;
}

export interface UseDaemonPanelReturn {
  health: DaemonHealth | null;
  jobs: DaemonJob[];
  isRunning: boolean;
  refresh: () => Promise<void>;
  addJob: (name: string, prompt: string, schedule?: string) => Promise<void>;
  addTemplate: (templateName: string, workspace: string) => Promise<void>;
  pauseJob: (id: string) => Promise<void>;
  resumeJob: (id: string) => Promise<void>;
  deleteJob: (id: string) => Promise<void>;
  availableTemplates: string[];
}

const DAEMON_TEMPLATES = [
  'repo-watcher', 'log-monitor', 'daily-standup', 'dependency-audit'
];

export function useDaemonPanel(): UseDaemonPanelReturn {
  const [health, setHealth] = useState<DaemonHealth | null>(null);
  const [jobs, setJobs] = useState<DaemonJob[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [healthRes, jobsRes] = await Promise.all([
        fetch('/api/daemon/health'),
        fetch('/api/daemon/jobs'),
      ]);
      if (healthRes.ok) setHealth(await healthRes.json());
      if (jobsRes.ok) {
        const data = await jobsRes.json();
        setJobs(data.jobs || []);
      }
    } catch { /* ignore */ }
  }, []);

  const addJob = useCallback(async (name: string, prompt: string, schedule?: string) => {
    await fetch('/api/daemon/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, prompt, schedule: schedule || '' }),
    });
    await refresh();
  }, [refresh]);

  const addTemplate = useCallback(async (templateName: string, workspace: string) => {
    await fetch('/api/daemon/jobs/template', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template: templateName, workspace }),
    });
    await refresh();
  }, [refresh]);

  const pauseJob = useCallback(async (id: string) => {
    await fetch(`/api/daemon/jobs/${id}/pause`, { method: 'POST' });
    await refresh();
  }, [refresh]);

  const resumeJob = useCallback(async (id: string) => {
    await fetch(`/api/daemon/jobs/${id}/resume`, { method: 'POST' });
    await refresh();
  }, [refresh]);

  const deleteJob = useCallback(async (id: string) => {
    await fetch(`/api/daemon/jobs/${id}`, { method: 'DELETE' });
    await refresh();
  }, [refresh]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000); // Refresh every 30s.
    return () => clearInterval(interval);
  }, [refresh]);

  return {
    health, jobs,
    isRunning: health?.status === 'running',
    refresh, addJob, addTemplate, pauseJob, resumeJob, deleteJob,
    availableTemplates: DAEMON_TEMPLATES,
  };
}

// ============================================================================
// Cost Dashboard
// ============================================================================

export interface CostData {
  total_today_usd: number;
  budget_remaining_usd: number;
  by_model: Record<string, number>;
  by_intent: Record<string, number>;
  last_7_days: { date: string; cost: number }[];
}

export interface UseCostDashboardReturn {
  data: CostData | null;
  refresh: () => Promise<void>;
  setBudget: (maxUsd: number) => Promise<void>;
}

export function useCostDashboard(): UseCostDashboardReturn {
  const [data, setData] = useState<CostData | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/cost/dashboard');
      if (res.ok) setData(await res.json());
    } catch { /* ignore */ }
  }, []);

  const setBudget = useCallback(async (maxUsd: number) => {
    await fetch('/api/cost/budget', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_daily_usd: maxUsd }),
    });
    await refresh();
  }, [refresh]);

  useEffect(() => { refresh(); }, [refresh]);

  return { data, refresh, setBudget };
}
