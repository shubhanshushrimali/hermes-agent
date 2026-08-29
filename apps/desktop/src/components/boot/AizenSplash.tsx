/**
 * AizenSplash — boot screen for "Hermes Agent — Aizen Version".
 *
 * Sequence:
 * 1. [0ms]    Dark void screen
 * 2. [200ms]  Manga Aizen avatar fades in (opacity 0→1, scale 0.95→1.0)
 * 3. [600ms]  "Hermes Agent" text appears below
 * 4. [900ms]  "— Aizen Version" slides in from right
 * 5. [1100ms] Audio plays: "Yōkoso, watashi no Soul Society"
 * 6. [3000ms] Fade to main app
 *
 * Audio can be muted in settings. The splash respects prefers-reduced-motion.
 */

import { useEffect, useRef, useState } from 'react'

const assetPath = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`

/** Persisted mute key for the startup sound. */
const MUTE_KEY = 'hermes-aizen-mute-startup'

export function AizenSplash({ onComplete }: { onComplete: () => void }) {
  const [phase, setPhase] = useState(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const reducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  useEffect(() => {
    if (reducedMotion) {
      // Skip animation entirely
      onComplete()
      return
    }

    const timers: ReturnType<typeof setTimeout>[] = []

    timers.push(setTimeout(() => setPhase(1), 200))   // Avatar fades in
    timers.push(setTimeout(() => setPhase(2), 600))   // "Hermes Agent"
    timers.push(setTimeout(() => setPhase(3), 900))   // "— Aizen Version"
    timers.push(setTimeout(() => {
      setPhase(4) // Play audio
      const muted = localStorage.getItem(MUTE_KEY) === '1'
      if (!muted && audioRef.current) {
        audioRef.current.volume = 0.4
        audioRef.current.play().catch(() => {
          // Audio autoplay blocked — silently continue
        })
      }
    }, 1100))
    timers.push(setTimeout(() => setPhase(5), 2800))  // Start fade out
    timers.push(setTimeout(onComplete, 3200))          // Hand off to app

    return () => timers.forEach(clearTimeout)
  }, [onComplete, reducedMotion])

  return (
    <div
      className="fixed inset-0 z-[9999] flex flex-col items-center justify-center"
      style={{
        background: '#0B0D10',
        opacity: phase >= 5 ? 0 : 1,
        transition: 'opacity 400ms ease-out',
      }}
    >
      {/* Aizen avatar */}
      <div
        style={{
          width: 128,
          height: 128,
          borderRadius: '50%',
          overflow: 'hidden',
          opacity: phase >= 1 ? 1 : 0,
          transform: phase >= 1 ? 'scale(1)' : 'scale(0.95)',
          transition: 'opacity 400ms ease-out, transform 400ms ease-out',
          boxShadow: phase >= 2
            ? '0 0 40px rgba(99, 102, 241, 0.15)'
            : 'none',
        }}
      >
        <img
          alt="Aizen"
          src={assetPath('aizen-avatar.jpg')}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      </div>

      {/* Title */}
      <h1
        style={{
          fontFamily: 'Inter, system-ui, sans-serif',
          fontWeight: 600,
          fontSize: 20,
          color: '#E4E4E7',
          marginTop: 24,
          opacity: phase >= 2 ? 1 : 0,
          transform: phase >= 2 ? 'translateY(0)' : 'translateY(8px)',
          transition: 'opacity 300ms ease-out, transform 300ms ease-out',
          letterSpacing: '-0.01em',
        }}
      >
        Hermes Agent
      </h1>

      {/* Subtitle */}
      <p
        style={{
          fontFamily: 'Inter, system-ui, sans-serif',
          fontWeight: 300,
          fontStyle: 'italic',
          fontSize: 14,
          color: '#6366F1',
          marginTop: 6,
          opacity: phase >= 3 ? 1 : 0,
          transform: phase >= 3 ? 'translateX(0)' : 'translateX(12px)',
          transition: 'opacity 300ms ease-out, transform 300ms ease-out',
        }}
      >
        — Aizen Version
      </p>

      {/* Audio element — loaded lazily */}
      <audio ref={audioRef} preload="auto">
        <source src={assetPath('sounds/aizen-yokoso.mp3')} type="audio/mpeg" />
      </audio>
    </div>
  )
}
