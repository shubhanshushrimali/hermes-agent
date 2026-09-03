import { describe, expect, it } from 'vitest'

import { applySpendDashboard, clearSpendCap, $spendCap } from './spend-cap'

describe('spend cap dashboard', () => {
  it('marks exhausted when remaining is 0 and spend is positive', () => {
    const next = applySpendDashboard({ budget_remaining_usd: 0, total_today_usd: 4.2 })

    expect(next.exhausted).toBe(true)
    expect($spendCap.get().exhausted).toBe(true)
    clearSpendCap()
    expect($spendCap.get().exhausted).toBe(false)
  })

  it('does not treat a zero-spend day as a cap hit', () => {
    expect(applySpendDashboard({ budget_remaining_usd: 0, total_today_usd: 0 }).exhausted).toBe(false)
    expect(applySpendDashboard({ budget_remaining_usd: 8, total_today_usd: 2 }).exhausted).toBe(false)
  })
})
