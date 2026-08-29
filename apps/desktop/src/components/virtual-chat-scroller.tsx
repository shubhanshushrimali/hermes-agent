/**
 * VirtualChatScroller — performant virtual scrolling for long chat threads.
 *
 * Renders only the visible items (plus overscan buffer) instead of the
 * entire conversation. Supports variable-height items via a measurement
 * cache.
 *
 * Part of Phase 3: UI/UX Optimization.
 *
 * Usage:
 *   <VirtualChatScroller
 *     items={messages}
 *     renderItem={(item, index) => <MessageBubble key={item.id} ... />}
 *     estimatedItemHeight={120}
 *   />
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode, UIEvent } from 'react'

interface VirtualChatScrollerProps<T> {
  /** The full list of items to render. */
  items: T[]
  /** Render function for each item. */
  renderItem: (item: T, index: number) => ReactNode
  /** Estimated height per item (used before measurement). */
  estimatedItemHeight?: number
  /** Number of items to render above/below the viewport. */
  overscan?: number
  /** Auto-scroll to bottom when new items arrive. */
  autoScrollToBottom?: boolean
  /** CSS class for the scroll container. */
  className?: string
  /** Callback when user scrolls near the top (for history loading). */
  onNearTop?: () => void
  /** Threshold for onNearTop in px. */
  nearTopThreshold?: number
}

interface MeasuredItem {
  offset: number
  height: number
}

export function VirtualChatScroller<T>({
  items,
  renderItem,
  estimatedItemHeight = 120,
  overscan = 5,
  autoScrollToBottom = true,
  className = '',
  onNearTop,
  nearTopThreshold = 200,
}: VirtualChatScrollerProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null)
  const measureRef = useRef<Map<number, number>>(new Map())
  const [scrollTop, setScrollTop] = useState(0)
  const [containerHeight, setContainerHeight] = useState(0)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const prevItemCount = useRef(items.length)

  // Observe container size
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height)
      }
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // Auto-scroll to bottom when new items arrive
  useEffect(() => {
    if (autoScrollToBottom && isAtBottom && items.length > prevItemCount.current) {
      const container = containerRef.current
      if (container) {
        requestAnimationFrame(() => {
          container.scrollTop = container.scrollHeight
        })
      }
    }
    prevItemCount.current = items.length
  }, [items.length, autoScrollToBottom, isAtBottom])

  // Calculate total height and visible range
  const { totalHeight, visibleRange } = useMemo(() => {
    const measurements = measureRef.current
    let total = 0
    let startIndex = -1
    let endIndex = -1
    const viewportEnd = scrollTop + containerHeight

    for (let i = 0; i < items.length; i++) {
      const height = measurements.get(i) || estimatedItemHeight
      const offset = total

      if (offset + height >= scrollTop && startIndex === -1) {
        startIndex = Math.max(0, i - overscan)
      }
      if (offset <= viewportEnd) {
        endIndex = Math.min(items.length - 1, i + overscan)
      }

      total += height
    }

    if (startIndex === -1) startIndex = 0
    if (endIndex === -1) endIndex = Math.min(items.length - 1, overscan)

    return {
      totalHeight: total,
      visibleRange: { start: startIndex, end: endIndex },
    }
  }, [items.length, scrollTop, containerHeight, estimatedItemHeight, overscan])

  // Calculate offset for the first visible item
  const startOffset = useMemo(() => {
    const measurements = measureRef.current
    let offset = 0
    for (let i = 0; i < visibleRange.start; i++) {
      offset += measurements.get(i) || estimatedItemHeight
    }
    return offset
  }, [visibleRange.start, estimatedItemHeight])

  // Handle scroll
  const handleScroll = useCallback(
    (e: UIEvent<HTMLDivElement>) => {
      const target = e.currentTarget
      const newScrollTop = target.scrollTop
      setScrollTop(newScrollTop)

      // Check if at bottom (with 20px tolerance)
      const atBottom =
        target.scrollHeight - target.scrollTop - target.clientHeight < 20
      setIsAtBottom(atBottom)

      // Near top detection
      if (onNearTop && newScrollTop < nearTopThreshold) {
        onNearTop()
      }
    },
    [onNearTop, nearTopThreshold],
  )

  // Measure rendered items
  const measureItem = useCallback(
    (index: number, el: HTMLDivElement | null) => {
      if (el) {
        const height = el.getBoundingClientRect().height
        if (measureRef.current.get(index) !== height) {
          measureRef.current.set(index, height)
        }
      }
    },
    [],
  )

  // Render visible items
  const visibleItems = useMemo(() => {
    const result: ReactNode[] = []
    for (let i = visibleRange.start; i <= visibleRange.end && i < items.length; i++) {
      result.push(
        <div key={i} ref={el => measureItem(i, el)} data-virtual-index={i}>
          {renderItem(items[i], i)}
        </div>,
      )
    }
    return result
  }, [visibleRange.start, visibleRange.end, items, renderItem, measureItem])

  return (
    <div
      ref={containerRef}
      className={`overflow-y-auto ${className}`}
      onScroll={handleScroll}
      style={{ position: 'relative' }}
    >
      {/* Total height spacer */}
      <div style={{ height: totalHeight, position: 'relative' }}>
        {/* Positioned items */}
        <div style={{ position: 'absolute', top: startOffset, width: '100%' }}>
          {visibleItems}
        </div>
      </div>
    </div>
  )
}

/**
 * Scroll-to-bottom indicator with smooth animation.
 * Shows when user scrolls up in a long conversation.
 */
export function ScrollToBottomFab({
  visible,
  onClick,
  unreadCount = 0,
}: {
  visible: boolean
  onClick: () => void
  unreadCount?: number
}) {
  if (!visible) return null

  return (
    <button
      className="aizen-btn-press aizen-glass fixed bottom-24 right-6 w-10 h-10 rounded-full
                 flex items-center justify-center shadow-lg z-50
                 border border-(--ui-stroke-secondary) transition-transform"
      onClick={onClick}
      aria-label="Scroll to bottom"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <polyline points="6 9 12 15 18 9" />
      </svg>
      {unreadCount > 0 && (
        <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-indigo-500
                       text-[10px] font-medium flex items-center justify-center text-white">
          {unreadCount > 9 ? '9+' : unreadCount}
        </span>
      )}
    </button>
  )
}
