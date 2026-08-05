import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import {
  fetchActivity,
  fetchActivityHistory,
  getActivityStreamUrl,
  transformSSETaskStartedData,
  transformSSETaskProgressData,
  transformSSETaskCompletedData,
  transformSSETaskFailedData,
  clearActivityHistory,
  type ClearHistoryParams,
  type ClearHistoryResponse,
} from '@/api/activity'
import type {
  ActivitySnapshot,
  ActivityHistoryResponse,
  ActivityHistoryParams,
  SSETaskStartedData,
  SSETaskProgressData,
  SSETaskCompletedData,
  SSETaskFailedData,
} from '@/types/activity'

// ============================================================================
// Configuration
// ============================================================================

const INITIAL_RETRY_DELAY = 1000 // 1 second
const MAX_RETRY_DELAY = 30000 // 30 seconds
const RETRY_MULTIPLIER = 2
const POLLING_INTERVAL = 5000 // 5 seconds
const MAX_SSE_FAILURES = 5

// ============================================================================
// Query Keys
// ============================================================================

export const activityKeys = {
  all: ['activity'] as const,
  snapshot: () => [...activityKeys.all, 'snapshot'] as const,
  history: (params: ActivityHistoryParams) => [...activityKeys.all, 'history', params] as const,
}

// ============================================================================
// useActivity Hook - Main activity snapshot with polling
// ============================================================================

export interface UseActivityOptions {
  /**
   * Whether to enable polling
   * @default true
   */
  enabled?: boolean
  /**
   * Polling interval in milliseconds
   * @default 5000
   */
  pollingInterval?: number
}

/**
 * Hook for fetching activity snapshot with 5-second polling fallback.
 * Polling pauses when the tab is hidden.
 */
export function useActivity(options: UseActivityOptions = {}) {
  const { enabled = true, pollingInterval = POLLING_INTERVAL } = options
  const [isTabVisible, setIsTabVisible] = useState(!document.hidden)

  // Track tab visibility
  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsTabVisible(!document.hidden)
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [])

  return useQuery<ActivitySnapshot>({
    queryKey: activityKeys.snapshot(),
    queryFn: fetchActivity,
    enabled: enabled && isTabVisible,
    refetchInterval: isTabVisible ? pollingInterval : false,
    staleTime: 2000, // Consider data stale after 2 seconds
  })
}

// ============================================================================
// useActivityStream Hook - SSE connection management
// ============================================================================

export interface UseActivityStreamOptions {
  /**
   * Whether to enable the SSE connection
   * @default true
   */
  enabled?: boolean
  /**
   * Callback when a task starts
   */
  onTaskStarted?: (data: SSETaskStartedData) => void
  /**
   * Callback when task progress updates
   */
  onTaskProgress?: (data: SSETaskProgressData) => void
  /**
   * Callback when a task completes
   */
  onTaskCompleted?: (data: SSETaskCompletedData) => void
  /**
   * Callback when a task fails
   */
  onTaskFailed?: (data: SSETaskFailedData) => void
}

export interface UseActivityStreamState {
  isConnected: boolean
  isUsingPolling: boolean
  error: string | null
}

/**
 * Hook for subscribing to real-time activity updates via SSE.
 * Automatically invalidates activity queries when events are received.
 * Falls back to polling if SSE connection fails repeatedly.
 */
export function useActivityStream(
  options: UseActivityStreamOptions = {}
): UseActivityStreamState {
  const { enabled = true, onTaskStarted, onTaskProgress, onTaskCompleted, onTaskFailed } = options

  const queryClient = useQueryClient()
  const [state, setState] = useState<UseActivityStreamState>({
    isConnected: false,
    isUsingPolling: false,
    error: null,
  })

  // Refs for managing connection lifecycle
  const eventSourceRef = useRef<EventSource | null>(null)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryDelayRef = useRef<number>(INITIAL_RETRY_DELAY)
  const consecutiveErrorsRef = useRef<number>(0)

  // Stable callback refs
  const onTaskStartedRef = useRef(onTaskStarted)
  const onTaskProgressRef = useRef(onTaskProgress)
  const onTaskCompletedRef = useRef(onTaskCompleted)
  const onTaskFailedRef = useRef(onTaskFailed)

  useEffect(() => {
    onTaskStartedRef.current = onTaskStarted
    onTaskProgressRef.current = onTaskProgress
    onTaskCompletedRef.current = onTaskCompleted
    onTaskFailedRef.current = onTaskFailed
  }, [onTaskStarted, onTaskProgress, onTaskCompleted, onTaskFailed])

  // Invalidate activity queries
  const invalidateActivity = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: activityKeys.snapshot() })
  }, [queryClient])

  // Cleanup function
  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
  }, [])

  // Connect to SSE endpoint
  const connect = useCallback(() => {
    if (!enabled) return

    cleanup()

    const url = getActivityStreamUrl()
    console.log('[useActivityStream] Connecting to SSE:', url)

    const eventSource = new EventSource(url)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      console.log('[useActivityStream] Connected')
      setState((prev) => ({ ...prev, isConnected: true, isUsingPolling: false, error: null }))
      retryDelayRef.current = INITIAL_RETRY_DELAY
      consecutiveErrorsRef.current = 0
    }

    eventSource.onerror = () => {
      console.error('[useActivityStream] Connection error')
      setState((prev) => ({ ...prev, isConnected: false }))
      consecutiveErrorsRef.current++

      // Close and schedule retry
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }

      // After several failures, switch to polling fallback
      if (consecutiveErrorsRef.current >= MAX_SSE_FAILURES) {
        console.log('[useActivityStream] Switching to polling fallback after repeated SSE failures')
        setState((prev) => ({
          ...prev,
          isConnected: false,
          isUsingPolling: true,
          error: 'SSE connection failed, using polling fallback',
        }))
        return
      }

      // Schedule reconnect with exponential backoff
      const delay = retryDelayRef.current
      console.log(`[useActivityStream] Reconnecting in ${delay}ms`)

      retryTimeoutRef.current = setTimeout(() => {
        retryDelayRef.current = Math.min(retryDelayRef.current * RETRY_MULTIPLIER, MAX_RETRY_DELAY)
        connect()
      }, delay)
    }

    // Handle task_started event
    eventSource.addEventListener('task_started', (event) => {
      try {
        const rawData = JSON.parse(event.data)
        const data = transformSSETaskStartedData(rawData)
        console.log('[useActivityStream] Task started:', data)

        invalidateActivity()
        onTaskStartedRef.current?.(data)
      } catch (e) {
        console.error('[useActivityStream] Failed to parse task_started event:', e)
      }
    })

    // Handle task_progress event
    eventSource.addEventListener('task_progress', (event) => {
      try {
        const rawData = JSON.parse(event.data)
        const data = transformSSETaskProgressData(rawData)

        invalidateActivity()
        onTaskProgressRef.current?.(data)
      } catch (e) {
        console.error('[useActivityStream] Failed to parse task_progress event:', e)
      }
    })

    // Handle task_completed event
    eventSource.addEventListener('task_completed', (event) => {
      try {
        const rawData = JSON.parse(event.data)
        const data = transformSSETaskCompletedData(rawData)
        console.log('[useActivityStream] Task completed:', data)

        invalidateActivity()
        onTaskCompletedRef.current?.(data)
      } catch (e) {
        console.error('[useActivityStream] Failed to parse task_completed event:', e)
      }
    })

    // Handle task_failed event
    eventSource.addEventListener('task_failed', (event) => {
      try {
        const rawData = JSON.parse(event.data)
        const data = transformSSETaskFailedData(rawData)
        console.log('[useActivityStream] Task failed:', data)

        invalidateActivity()
        onTaskFailedRef.current?.(data)
      } catch (e) {
        console.error('[useActivityStream] Failed to parse task_failed event:', e)
      }
    })

    // Handle heartbeat event (just to confirm connection is alive)
    eventSource.addEventListener('heartbeat', () => {
      // Connection is alive, no action needed
    })
  }, [enabled, cleanup, invalidateActivity])

  // Main effect: connect on mount, cleanup on unmount
  useEffect(() => {
    if (!enabled) {
      cleanup()
      setState({ isConnected: false, isUsingPolling: false, error: null })
      return
    }

    connect()

    return cleanup
  }, [enabled, connect, cleanup])

  return state
}

// ============================================================================
// useActivityCount Hook - Derived hook for badge counts
// ============================================================================

export type ActivitySeverity = 'failed' | 'active' | 'succeeded' | 'queued' | 'none'

export interface ActivityCount {
  active: number
  queued: number
  failed: number
  succeeded: number
  total: number
  /** Highest-severity status currently present; drives badge color. */
  severity: ActivitySeverity
  /** Count to display on the badge (matches the chosen severity). */
  badgeCount: number
}

/**
 * Derived hook that returns activity counts plus the highest-severity
 * status currently present. Severity ordering (high → low):
 * failed → active → succeeded → queued → none.
 */
export function useActivityCount(): ActivityCount {
  const { data } = useActivity()

  return useMemo(() => {
    if (!data) {
      return {
        active: 0,
        queued: 0,
        failed: 0,
        succeeded: 0,
        total: 0,
        severity: 'none',
        badgeCount: 0,
      }
    }

    const active = data.counts.active
    const queued = data.counts.queued
    const recent = data.recentCompletions ?? []
    const failed = recent.filter((t) => t.status === 'failed').length
    const succeeded = recent.filter((t) => t.status === 'completed').length

    let severity: ActivitySeverity = 'none'
    let badgeCount = 0
    if (failed > 0) {
      severity = 'failed'
      badgeCount = failed
    } else if (active > 0) {
      severity = 'active'
      badgeCount = active
    } else if (succeeded > 0) {
      severity = 'succeeded'
      badgeCount = succeeded
    } else if (queued > 0) {
      severity = 'queued'
      badgeCount = queued
    }

    return {
      active,
      queued,
      failed,
      succeeded,
      total: active + queued,
      severity,
      badgeCount,
    }
  }, [data])
}

/**
 * Tailwind classes for each severity — used by the Sidebar nav badge.
 */
export const ACTIVITY_BADGE_CLASSES: Record<Exclude<ActivitySeverity, 'none'>, string> = {
  failed: 'bg-destructive text-destructive-foreground',
  active: 'bg-blue-500 text-white animate-pulse',
  succeeded: 'bg-emerald-500 text-white',
  queued: 'bg-secondary text-secondary-foreground',
}

// ============================================================================
// useActivityHistory Hook - Paginated history with filters
// ============================================================================

export interface UseActivityHistoryOptions {
  /**
   * Whether to enable the query
   * @default true
   */
  enabled?: boolean
}

/**
 * Hook for fetching paginated activity history with filters.
 */
export function useActivityHistory(
  params: ActivityHistoryParams = {},
  options: UseActivityHistoryOptions = {}
) {
  const { enabled = true } = options

  return useQuery<ActivityHistoryResponse>({
    queryKey: activityKeys.history(params),
    queryFn: () => fetchActivityHistory(params),
    enabled,
  })
}

// ============================================================================
// useClearActivityHistory Hook - Mutation for clearing history
// ============================================================================

export interface UseClearActivityHistoryOptions {
  /**
   * Callback on successful deletion
   */
  onSuccess?: (data: ClearHistoryResponse) => void
  /**
   * Callback on deletion failure
   */
  onError?: (error: Error) => void
}

/**
 * Hook for clearing activity history records.
 * Automatically invalidates activity queries after successful deletion.
 */
export function useClearActivityHistory(options: UseClearActivityHistoryOptions = {}) {
  const { onSuccess, onError } = options
  const queryClient = useQueryClient()

  return useMutation<ClearHistoryResponse, Error, ClearHistoryParams>({
    mutationFn: (params: ClearHistoryParams) => clearActivityHistory(params),
    onSuccess: (data) => {
      // Invalidate all activity queries to refresh the list
      queryClient.invalidateQueries({ queryKey: activityKeys.all })
      onSuccess?.(data)
    },
    onError: (error) => {
      onError?.(error)
    },
  })
}
