/**
 * Developer Delight — Aizen Quotes & Achievements System.
 *
 * Subtle motivational touches that make developers feel world-class
 * while using the agent. Quotes appear as gentle toast notifications
 * at meaningful moments — NOT spammy, NOT distracting.
 *
 * All features are toggleable in settings.
 */

// ---------------------------------------------------------------------------
// Aizen Quotes — triggered at specific milestones
// ---------------------------------------------------------------------------

export interface AizenQuote {
  text: string
  trigger: string
  style: 'warm' | 'success' | 'achievement' | 'info' | 'break'
}

export const AIZEN_QUOTES: AizenQuote[] = [
  // Daily warmth
  {
    text: 'Welcome back. I\'ve been expecting you.',
    trigger: 'first-session',
    style: 'warm',
  },
  // Task success
  {
    text: 'According to plan.',
    trigger: 'task-complete',
    style: 'success',
  },
  // High productivity
  {
    text: 'Your growth... is interesting.',
    trigger: 'productivity-milestone',
    style: 'achievement',
  },
  // Error recovery
  {
    text: 'A minor miscalculation.',
    trigger: 'error-recovered',
    style: 'info',
  },
  // Break reminder
  {
    text: 'Shall we take a moment? Even captains rest.',
    trigger: 'break-reminder',
    style: 'break',
  },
  // Deploy success
  {
    text: 'All things in this world... are now in order.',
    trigger: 'deploy-success',
    style: 'success',
  },
  // New model connected
  {
    text: 'A new power has been unlocked.',
    trigger: 'model-connected',
    style: 'info',
  },
  // Feature discovery
  {
    text: 'You\'re beginning to see it, aren\'t you?',
    trigger: 'feature-discovery',
    style: 'info',
  },
  // Long streak
  {
    text: 'Admirable. Your resolve is unwavering.',
    trigger: 'coding-streak',
    style: 'achievement',
  },
  // Session end
  {
    text: 'Until next time.',
    trigger: 'session-end',
    style: 'warm',
  },
]

// ---------------------------------------------------------------------------
// Achievement Badges
// ---------------------------------------------------------------------------

export interface AizenBadge {
  id: string
  name: string
  description: string
  icon: string        // SVG path or emoji (will be replaced with SVG later)
  criteria: string
  threshold: number
  color: string       // Muted gold for achievements
}

export const AIZEN_BADGES: AizenBadge[] = [
  {
    id: 'first-strike',
    name: 'First Strike',
    description: 'Completed your first agent task',
    icon: '🗡️',
    criteria: 'tasks-completed',
    threshold: 1,
    color: '#C9A84C',
  },
  {
    id: 'shikai',
    name: 'Shikai',
    description: '10 consecutive successful deploys',
    icon: '🎯',
    criteria: 'consecutive-deploys',
    threshold: 10,
    color: '#94A3B8',
  },
  {
    id: 'bankai',
    name: 'Bankai',
    description: '100 tasks completed',
    icon: '⚔️',
    criteria: 'tasks-completed',
    threshold: 100,
    color: '#C9A84C',
  },
  {
    id: 'flash-step',
    name: 'Flash Step',
    description: 'Used 10+ keyboard shortcuts in one session',
    icon: '⚡',
    criteria: 'shortcuts-session',
    threshold: 10,
    color: '#EAB308',
  },
  {
    id: 'scholar',
    name: 'Scholar',
    description: 'Used code review panel 20 times',
    icon: '📖',
    criteria: 'code-reviews',
    threshold: 20,
    color: '#6366F1',
  },
  {
    id: 'night-owl',
    name: 'Night Owl',
    description: 'Coded past midnight 5 times',
    icon: '🌙',
    criteria: 'midnight-sessions',
    threshold: 5,
    color: '#818CF8',
  },
  {
    id: 'streak-7',
    name: 'On Fire',
    description: '7-day coding streak',
    icon: '🔥',
    criteria: 'daily-streak',
    threshold: 7,
    color: '#EF4444',
  },
]

// ---------------------------------------------------------------------------
// Settings keys for toggling delight features
// ---------------------------------------------------------------------------

export const DELIGHT_SETTINGS = {
  QUOTES_ENABLED: 'hermes-aizen-quotes',
  BADGES_ENABLED: 'hermes-aizen-badges',
  STARTUP_SOUND: 'hermes-aizen-startup-sound',
  BREAK_REMINDERS: 'hermes-aizen-break-reminders',
} as const

/** Check if a delight feature is enabled (default: true). */
export function isDelightEnabled(key: string): boolean {
  if (typeof localStorage === 'undefined') return true
  const val = localStorage.getItem(key)
  return val === null || val === '1'
}

/** Toggle a delight feature. */
export function setDelightEnabled(key: string, enabled: boolean): void {
  localStorage.setItem(key, enabled ? '1' : '0')
}

// ---------------------------------------------------------------------------
// Break reminder logic
// ---------------------------------------------------------------------------

let sessionStartTime: number | null = null

export function startSessionTimer(): void {
  sessionStartTime = Date.now()
}

export function getSessionDurationMinutes(): number {
  if (!sessionStartTime) return 0
  return (Date.now() - sessionStartTime) / 1000 / 60
}

export function shouldShowBreakReminder(): boolean {
  if (!isDelightEnabled(DELIGHT_SETTINGS.BREAK_REMINDERS)) return false
  return getSessionDurationMinutes() >= 120 // 2 hours
}

// ---------------------------------------------------------------------------
// Quote selection
// ---------------------------------------------------------------------------

/** Select an appropriate quote for the given trigger. */
export function getQuoteForTrigger(trigger: string): AizenQuote | null {
  if (!isDelightEnabled(DELIGHT_SETTINGS.QUOTES_ENABLED)) return null
  const candidates = AIZEN_QUOTES.filter(q => q.trigger === trigger)
  if (candidates.length === 0) return null
  return candidates[Math.floor(Math.random() * candidates.length)]
}

// ---------------------------------------------------------------------------
// Badge storage
// ---------------------------------------------------------------------------

const BADGE_STORAGE_KEY = 'hermes-aizen-badges'

export function getEarnedBadges(): string[] {
  try {
    const raw = localStorage.getItem(BADGE_STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function earnBadge(badgeId: string): boolean {
  if (!isDelightEnabled(DELIGHT_SETTINGS.BADGES_ENABLED)) return false
  const earned = getEarnedBadges()
  if (earned.includes(badgeId)) return false
  earned.push(badgeId)
  localStorage.setItem(BADGE_STORAGE_KEY, JSON.stringify(earned))
  return true // Badge was newly earned
}

// ---------------------------------------------------------------------------
// Streak tracking — persists daily coding activity in localStorage
// ---------------------------------------------------------------------------

const STREAK_KEY = 'hermes-aizen-streak'
const STREAK_DATES_KEY = 'hermes-aizen-streak-dates'

interface StreakData {
  /** Current consecutive-day streak. */
  current: number
  /** Longest ever streak. */
  best: number
  /** Last recorded date (YYYY-MM-DD). */
  lastDate: string
}

function todayKey(): string {
  return new Date().toISOString().slice(0, 10) // YYYY-MM-DD
}

/** Load persisted streak data. */
export function getStreakData(): StreakData {
  try {
    const raw = localStorage.getItem(STREAK_KEY)
    return raw ? JSON.parse(raw) : { current: 0, best: 0, lastDate: '' }
  } catch {
    return { current: 0, best: 0, lastDate: '' }
  }
}

/** Record today's session. Updates current streak and best streak. */
export function recordSessionStart(): void {
  startSessionTimer()

  const today = todayKey()
  const data = getStreakData()

  if (data.lastDate === today) {
    // Already recorded today — no-op.
    return
  }

  // Check if yesterday was the last date (consecutive).
  const yesterday = new Date()
  yesterday.setDate(yesterday.getDate() - 1)
  const yesterdayKey = yesterday.toISOString().slice(0, 10)

  if (data.lastDate === yesterdayKey) {
    // Consecutive day — increment streak.
    data.current += 1
  } else if (data.lastDate === '') {
    // First ever session.
    data.current = 1
  } else {
    // Streak broken — reset.
    data.current = 1
  }

  data.best = Math.max(data.best, data.current)
  data.lastDate = today

  try {
    localStorage.setItem(STREAK_KEY, JSON.stringify(data))
  } catch {
    // localStorage full — ignore.
  }

  // Also maintain a rolling log of active dates (last 30).
  try {
    const datesRaw = localStorage.getItem(STREAK_DATES_KEY)
    const dates: string[] = datesRaw ? JSON.parse(datesRaw) : []
    if (!dates.includes(today)) {
      dates.push(today)
      // Keep only the last 30 entries.
      while (dates.length > 30) dates.shift()
      localStorage.setItem(STREAK_DATES_KEY, JSON.stringify(dates))
    }
  } catch {
    // Best effort.
  }

  // Auto-award streak badges.
  if (data.current >= 7) {
    earnBadge('streak-7')
  }

  // Check for midnight coding badge.
  const hour = new Date().getHours()
  if (hour >= 0 && hour < 5) {
    try {
      const midnightKey = 'hermes-aizen-midnight-count'
      const count = parseInt(localStorage.getItem(midnightKey) || '0', 10) + 1
      localStorage.setItem(midnightKey, String(count))
      if (count >= 5) {
        earnBadge('night-owl')
      }
    } catch {
      // Ignore.
    }
  }
}

/** Get the list of active dates (last 30 days). */
export function getActiveDates(): string[] {
  try {
    const raw = localStorage.getItem(STREAK_DATES_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}
