/**
 * Crew Panel — Shows which CrewAI agents are active and their progress.
 * Daemon Panel — Monitor/control 24/7 background agents.
 * Cost Dashboard — LiteLLM spend tracking.
 *
 * Desktop origin is the Electron app, not the dashboard, so these calls go
 * through `hermesApi` (same path as git / Cmd+K) rather than `fetch('/')`.
 */

import { useCallback, useEffect, useState } from 'react'

import { hermesApi } from '@/hermes'

async function dashboardJson<T>(
  path: string,
  options?: { method?: string; body?: unknown },
): Promise<T | null> {
  const method = options?.method ?? 'GET'
  try {
    if (typeof window !== 'undefined' && window.hermesDesktop?.api) {
      return await hermesApi<T>({
        path,
        method,
        body: options?.body,
      })
    }
    const res = await fetch(path, {
      method,
      headers: options?.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: options?.body !== undefined ? JSON.stringify(options.body) : undefined,
    })
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

// ============================================================================
// Crew Panel
// ============================================================================

export interface CrewStatus {
  active_crew: string | null
  active_agents: string[]
  available_crews: Record<string, {
    name: string
    description: string
    agents: string[]
  }>
  crewai_available: boolean
}

export interface UseCrewPanelReturn {
  status: CrewStatus | null
  isActive: boolean
  isLoading: boolean
  refresh: () => Promise<void>
  startCrew: (crewName: string, task: string) => Promise<void>
}

export function useCrewPanel(): UseCrewPanelReturn {
  const [status, setStatus] = useState<CrewStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await dashboardJson<CrewStatus>('/api/crew/status')
      if (data) setStatus(data)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const startCrew = useCallback(async (crewName: string, task: string) => {
    await dashboardJson('/api/crew/run', {
      method: 'POST',
      body: { crew: crewName, task },
    })
    await refresh()
  }, [refresh])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return {
    status,
    isActive: !!status?.active_crew,
    isLoading,
    refresh,
    startCrew,
  }
}

// ============================================================================
// Daemon Panel
// ============================================================================

export interface DaemonHealth {
  status: string
  uptime_seconds: number
  uptime_human: string
  jobs_processed: number
  daily_spend_usd: number
  budget_remaining_usd: number
  last_heartbeat: string
  pending_jobs: number
}

export interface DaemonJob {
  id: string
  name: string
  status: string
  prompt: string
  schedule: string
  priority: number
  created_at: string
  result?: string
  error?: string
}

export interface UseDaemonPanelReturn {
  health: DaemonHealth | null
  jobs: DaemonJob[]
  isRunning: boolean
  isLoading: boolean
  refresh: () => Promise<void>
  addJob: (name: string, prompt: string, schedule?: string) => Promise<void>
  addTemplate: (templateName: string, workspace: string) => Promise<void>
  pauseJob: (id: string) => Promise<void>
  resumeJob: (id: string) => Promise<void>
  deleteJob: (id: string) => Promise<void>
  availableTemplates: string[]
}

const DAEMON_TEMPLATES = [
  'repo-watcher', 'log-monitor', 'daily-standup', 'dependency-audit',
]

export function useDaemonPanel(): UseDaemonPanelReturn {
  const [health, setHealth] = useState<DaemonHealth | null>(null)
  const [jobs, setJobs] = useState<DaemonJob[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const [healthData, jobsData] = await Promise.all([
        dashboardJson<DaemonHealth>('/api/daemon/health'),
        dashboardJson<{ jobs?: DaemonJob[] }>('/api/daemon/jobs'),
      ])
      if (healthData) setHealth(healthData)
      if (jobsData) setJobs(jobsData.jobs || [])
    } finally {
      setIsLoading(false)
    }
  }, [])

  const addJob = useCallback(async (name: string, prompt: string, schedule?: string) => {
    await dashboardJson('/api/daemon/jobs', {
      method: 'POST',
      body: { name, prompt, schedule: schedule || '' },
    })
    await refresh()
  }, [refresh])

  const addTemplate = useCallback(async (templateName: string, workspace: string) => {
    await dashboardJson('/api/daemon/jobs/template', {
      method: 'POST',
      body: { template: templateName, workspace },
    })
    await refresh()
  }, [refresh])

  const pauseJob = useCallback(async (id: string) => {
    await dashboardJson(`/api/daemon/jobs/${id}/pause`, { method: 'POST' })
    await refresh()
  }, [refresh])

  const resumeJob = useCallback(async (id: string) => {
    await dashboardJson(`/api/daemon/jobs/${id}/resume`, { method: 'POST' })
    await refresh()
  }, [refresh])

  const deleteJob = useCallback(async (id: string) => {
    await dashboardJson(`/api/daemon/jobs/${id}`, { method: 'DELETE' })
    await refresh()
  }, [refresh])

  useEffect(() => {
    void refresh()
    const interval = setInterval(() => {
      void refresh()
    }, 30_000)
    return () => clearInterval(interval)
  }, [refresh])

  return {
    health,
    jobs,
    isRunning: health?.status === 'running',
    isLoading,
    refresh,
    addJob,
    addTemplate,
    pauseJob,
    resumeJob,
    deleteJob,
    availableTemplates: DAEMON_TEMPLATES,
  }
}

// ============================================================================
// Cost Dashboard
// ============================================================================

export interface CostData {
  total_today_usd: number
  budget_remaining_usd: number
  by_model: Record<string, number>
  by_intent: Record<string, number>
  last_7_days: { date: string; cost: number }[]
}

export interface UseCostDashboardReturn {
  data: CostData | null
  isLoading: boolean
  refresh: () => Promise<void>
  setBudget: (maxUsd: number) => Promise<void>
}

export function useCostDashboard(): UseCostDashboardReturn {
  const [data, setData] = useState<CostData | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const next = await dashboardJson<CostData>('/api/cost/dashboard')
      if (next) setData(next)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const setBudget = useCallback(async (maxUsd: number) => {
    await dashboardJson('/api/cost/budget', {
      method: 'POST',
      body: { max_daily_usd: maxUsd },
    })
    await refresh()
  }, [refresh])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { data, isLoading, refresh, setBudget }
}

// ============================================================================
// Recipes / MCP Apps / Graph — dashboard FastAPI, same origin as git
// ============================================================================

export interface RecipeListItem {
  name: string
  description?: string
}

export function useRecipesPanel() {
  const [recipes, setRecipes] = useState<RecipeListItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [running, setRunning] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<string>('')
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setError('')
    try {
      const data = await dashboardJson<{ ok?: boolean; recipes?: RecipeListItem[] }>('/api/recipes')
      setRecipes(Array.isArray(data?.recipes) ? data.recipes : [])
    } catch (e) {
      setError(String(e))
    } finally {
      setIsLoading(false)
    }
  }, [])

  const runRecipe = useCallback(async (name: string, extra?: Record<string, unknown>) => {
    setRunning(name)
    setError('')
    setLastResult('')
    try {
      const data = await dashboardJson<{ ok?: boolean; result?: unknown; detail?: string }>(
        `/api/recipes/${encodeURIComponent(name)}/run`,
        { method: 'POST', body: extra ?? {} },
      )
      setLastResult(JSON.stringify(data?.result ?? data ?? {}, null, 2))
    } catch (e) {
      setError(String(e))
    } finally {
      setRunning(null)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { recipes, isLoading, running, lastResult, error, refresh, runRecipe }
}

export interface McpAppListItem {
  id: string
  name?: string
  type?: string
  description?: string
}

export function useMcpAppsPanel() {
  const [apps, setApps] = useState<McpAppListItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setError('')
    try {
      const data = await dashboardJson<{ ok?: boolean; apps?: McpAppListItem[] }>('/api/mcp/apps')
      setApps(Array.isArray(data?.apps) ? data.apps : [])
    } catch (e) {
      setError(String(e))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { apps, isLoading, error, refresh }
}

export interface GraphIndexResult {
  status?: string
  nodes?: number
  edges?: number
  files?: number
  backend?: string
  warnings?: string[]
}

export function useGraphPanel(workspace: string) {
  const [result, setResult] = useState<GraphIndexResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const indexWorkspace = useCallback(async (force = false) => {
    if (!workspace.trim()) {
      setError('Open a workspace first')
      return
    }
    setIsLoading(true)
    setError('')
    try {
      const data = await dashboardJson<GraphIndexResult>('/api/graph/index', {
        method: 'POST',
        body: { workspace_path: workspace, force },
      })
      if (!data) {
        setError('Graph index failed')
        return
      }
      setResult(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setIsLoading(false)
    }
  }, [workspace])

  return { result, isLoading, error, indexWorkspace }
}

