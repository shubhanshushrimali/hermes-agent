import { atom } from 'nanostores'

import { hermesApi } from '@/hermes'

export interface SpendCapState {
  remainingUsd: number | null
  totalTodayUsd: number
  exhausted: boolean
}

const INITIAL: SpendCapState = { remainingUsd: null, totalTodayUsd: 0, exhausted: false }

export const $spendCap = atom<SpendCapState>(INITIAL)

let pollTimer: number | null = null

interface CostDashboardPayload {
  budget_remaining_usd?: number
  total_today_usd?: number
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function applySpendDashboard(data: CostDashboardPayload | null | undefined): SpendCapState {
  const remaining = asNumber(data?.budget_remaining_usd)
  const total = asNumber(data?.total_today_usd) ?? 0
  const exhausted = remaining !== null && remaining <= 0 && total > 0
  const next: SpendCapState = { remainingUsd: remaining, totalTodayUsd: total, exhausted }
  $spendCap.set(next)
  return next
}

export function clearSpendCap(): void {
  $spendCap.set(INITIAL)
}

export async function refreshSpendCap(): Promise<SpendCapState> {
  try {
    if (typeof window === 'undefined' || !window.hermesDesktop?.api) {
      return $spendCap.get()
    }

    const data = await hermesApi<CostDashboardPayload>({ path: '/api/cost/dashboard', method: 'GET' })
    return applySpendDashboard(data)
  } catch {
    return $spendCap.get()
  }
}

export function startSpendCapPolling(): () => void {
  void refreshSpendCap()

  if (pollTimer !== null) {
    return stopSpendCapPolling
  }

  pollTimer = window.setInterval(() => {
    void refreshSpendCap()
  }, 12_000)

  return stopSpendCapPolling
}

export function stopSpendCapPolling(): void {
  if (pollTimer === null) {
    return
  }

  window.clearInterval(pollTimer)
  pollTimer = null
}
