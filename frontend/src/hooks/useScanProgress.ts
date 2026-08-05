import { useEffect, useRef, useState, useCallback } from 'react'
import { getScanProgressSSEUrl } from '@/api/scan'
import type {
  ScanProgressState,
  SSEScanStartedData,
  SSEScanProgressData,
  SSEScanCompletedData,
  SSEScanFailedData,
  SSEScanQueuedData,
  SSEScanBlockedData,
  ScanStatusType,
} from '@/types/scan'

// ============================================================================
// Configuration
// ============================================================================

const INITIAL_RETRY_DELAY = 1000 // 1 second
const MAX_RETRY_DELAY = 30000 // 30 seconds
const RETRY_MULTIPLIER = 2

// ============================================================================
// SSE Data Transformers (snake_case to camelCase)
// ============================================================================

interface RawSSEScanStartedData {
  scan_id: number
  library_slug: string
  started_at: string
}

interface RawSSEScanProgressData {
  scan_id: number
  status: string
  items_total: number
  items_processed: number
  progress_percent: number
  current_file: string | null
  elapsed_seconds: number
}

interface RawSSEScanCompletedData {
  scan_id: number
  status: 'completed'
  items_total: number
  items_processed: number
  new_items: number
  modified_items: number
  deleted_items: number
  completed_at: string
  duration_seconds: number
}

interface RawSSEScanFailedData {
  scan_id: number
  status: 'failed'
  error_message: string
  failed_at: string
}

interface RawSSEScanQueuedData {
  library_slug: string
  queue_position: number
  blocked_by: string[]
}

interface RawSSEScanBlockedData {
  library_slug: string
  blocking_operations: string[]
}

function transformScanStartedData(raw: RawSSEScanStartedData): SSEScanStartedData {
  return {
    scanId: raw.scan_id,
    librarySlug: raw.library_slug,
    startedAt: raw.started_at,
  }
}

function transformScanProgressData(raw: RawSSEScanProgressData): SSEScanProgressData {
  return {
    scanId: raw.scan_id,
    status: raw.status as ScanStatusType,
    itemsTotal: raw.items_total,
    itemsProcessed: raw.items_processed,
    progressPercent: raw.progress_percent,
    currentFile: raw.current_file,
    elapsedSeconds: raw.elapsed_seconds,
  }
}

function transformScanCompletedData(raw: RawSSEScanCompletedData): SSEScanCompletedData {
  return {
    scanId: raw.scan_id,
    status: raw.status,
    itemsTotal: raw.items_total,
    itemsProcessed: raw.items_processed,
    newItems: raw.new_items,
    modifiedItems: raw.modified_items,
    deletedItems: raw.deleted_items,
    completedAt: raw.completed_at,
    durationSeconds: raw.duration_seconds,
  }
}

function transformScanFailedData(raw: RawSSEScanFailedData): SSEScanFailedData {
  return {
    scanId: raw.scan_id,
    status: raw.status,
    errorMessage: raw.error_message,
    failedAt: raw.failed_at,
  }
}

function transformScanQueuedData(raw: RawSSEScanQueuedData): SSEScanQueuedData {
  return {
    librarySlug: raw.library_slug,
    queuePosition: raw.queue_position,
    blockedBy: raw.blocked_by,
  }
}

function transformScanBlockedData(raw: RawSSEScanBlockedData): SSEScanBlockedData {
  return {
    librarySlug: raw.library_slug,
    blockingOperations: raw.blocking_operations,
  }
}

// ============================================================================
// Initial State
// ============================================================================

const initialState: ScanProgressState = {
  isConnected: false,
  isScanning: false,
  isQueued: false,
  isBlocked: false,
  progress: null,
  error: null,
  queuePosition: null,
  blockingOperations: [],
}

// ============================================================================
// Hook Options
// ============================================================================

export interface UseScanProgressOptions {
  /**
   * Whether to enable the SSE connection
   * @default true
   */
  enabled?: boolean
  /**
   * Callback when scan starts
   */
  onScanStarted?: (data: SSEScanStartedData) => void
  /**
   * Callback when scan completes
   */
  onScanCompleted?: (data: SSEScanCompletedData) => void
  /**
   * Callback when scan fails
   */
  onScanFailed?: (data: SSEScanFailedData) => void
  /**
   * Whether to use polling fallback if SSE fails repeatedly
   * @default true
   */
  enablePollingFallback?: boolean
  /**
   * Polling interval in milliseconds (when using fallback)
   * @default 5000
   */
  pollingInterval?: number
}

// ============================================================================
// Main Hook
// ============================================================================

/**
 * Hook for subscribing to real-time scan progress updates via SSE
 *
 * @param slug - Library slug to subscribe to
 * @param options - Hook configuration options
 * @returns Current scan progress state
 */
export function useScanProgress(
  slug: string | undefined,
  options: UseScanProgressOptions = {}
): ScanProgressState {
  const {
    enabled = true,
    onScanStarted,
    onScanCompleted,
    onScanFailed,
    enablePollingFallback = true,
    pollingInterval = 5000,
  } = options

  const [state, setState] = useState<ScanProgressState>(initialState)

  // Refs for managing connection lifecycle
  const eventSourceRef = useRef<EventSource | null>(null)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryDelayRef = useRef<number>(INITIAL_RETRY_DELAY)
  const consecutiveErrorsRef = useRef<number>(0)
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const isUsingPollingRef = useRef<boolean>(false)

  // Stable callback refs
  const onScanStartedRef = useRef(onScanStarted)
  const onScanCompletedRef = useRef(onScanCompleted)
  const onScanFailedRef = useRef(onScanFailed)

  useEffect(() => {
    onScanStartedRef.current = onScanStarted
    onScanCompletedRef.current = onScanCompleted
    onScanFailedRef.current = onScanFailed
  }, [onScanStarted, onScanCompleted, onScanFailed])

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
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
  }, [])

  // Start polling fallback
  const startPollingFallback = useCallback(async () => {
    if (!slug || isUsingPollingRef.current) return

    isUsingPollingRef.current = true
    console.log('[useScanProgress] Starting polling fallback for', slug)

    const pollStatus = async () => {
      try {
        const response = await fetch(getScanProgressSSEUrl(slug).replace('/progress', '/status'))
        if (response.ok) {
          const data = await response.json()
          // Transform and update state from status endpoint
          if (data.current_scan) {
            setState((prev) => ({
              ...prev,
              isConnected: true,
              isScanning: true,
              isQueued: false,
              isBlocked: false,
              progress: {
                libraryId: 0,
                librarySlug: slug,
                scanId: data.current_scan.id,
                status: data.current_scan.status,
                itemsProcessed: data.current_scan.items_processed,
                itemsTotal: data.current_scan.items_total,
                percentage: data.current_scan.progress_percent || 0,
                currentFile: data.current_scan.current_file,
                startedAt: data.current_scan.started_at,
                elapsedSeconds: null,
              },
              error: null,
              queuePosition: null,
              blockingOperations: [],
            }))
          } else if (data.queued_scans > 0) {
            setState((prev) => ({
              ...prev,
              isConnected: true,
              isScanning: false,
              isQueued: true,
              isBlocked: data.blocking_operations?.length > 0,
              progress: null,
              error: null,
              queuePosition: data.queued_scans,
              blockingOperations: data.blocking_operations || [],
            }))
          } else {
            setState((prev) => ({
              ...prev,
              isConnected: true,
              isScanning: false,
              isQueued: false,
              isBlocked: false,
              progress: null,
              error: null,
              queuePosition: null,
              blockingOperations: [],
            }))
          }
        }
      } catch (error) {
        console.error('[useScanProgress] Polling error:', error)
      }
    }

    // Poll immediately then set interval
    await pollStatus()
    pollingIntervalRef.current = setInterval(pollStatus, pollingInterval)
  }, [slug, pollingInterval])

  // Connect to SSE endpoint
  const connect = useCallback(() => {
    if (!slug || !enabled) return

    cleanup()

    const url = getScanProgressSSEUrl(slug)
    console.log('[useScanProgress] Connecting to SSE:', url)

    const eventSource = new EventSource(url)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      console.log('[useScanProgress] Connected')
      setState((prev) => ({ ...prev, isConnected: true, error: null }))
      retryDelayRef.current = INITIAL_RETRY_DELAY
      consecutiveErrorsRef.current = 0
      isUsingPollingRef.current = false
    }

    eventSource.onerror = (event) => {
      console.error('[useScanProgress] Connection error:', event)
      setState((prev) => ({ ...prev, isConnected: false }))
      consecutiveErrorsRef.current++

      // Close and schedule retry
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }

      // After several failures, switch to polling fallback
      if (enablePollingFallback && consecutiveErrorsRef.current >= 5) {
        console.log('[useScanProgress] Switching to polling fallback after repeated SSE failures')
        startPollingFallback()
        return
      }

      // Schedule reconnect with exponential backoff
      const delay = retryDelayRef.current
      console.log(`[useScanProgress] Reconnecting in ${delay}ms`)

      retryTimeoutRef.current = setTimeout(() => {
        retryDelayRef.current = Math.min(retryDelayRef.current * RETRY_MULTIPLIER, MAX_RETRY_DELAY)
        connect()
      }, delay)
    }

    // Handle scan_started event
    eventSource.addEventListener('scan_started', (event) => {
      try {
        const rawData = JSON.parse(event.data) as RawSSEScanStartedData
        const data = transformScanStartedData(rawData)
        console.log('[useScanProgress] Scan started:', data)

        setState((prev) => ({
          ...prev,
          isScanning: true,
          isQueued: false,
          isBlocked: false,
          progress: {
            libraryId: 0,
            librarySlug: data.librarySlug,
            scanId: data.scanId,
            status: 'scanning',
            itemsProcessed: 0,
            itemsTotal: 0,
            percentage: 0,
            currentFile: null,
            startedAt: data.startedAt,
            elapsedSeconds: 0,
          },
          error: null,
          queuePosition: null,
          blockingOperations: [],
        }))

        onScanStartedRef.current?.(data)
      } catch (e) {
        console.error('[useScanProgress] Failed to parse scan_started event:', e)
      }
    })

    // Handle scan_progress event
    eventSource.addEventListener('scan_progress', (event) => {
      try {
        const rawData = JSON.parse(event.data) as RawSSEScanProgressData
        const data = transformScanProgressData(rawData)

        setState((prev) => ({
          ...prev,
          isScanning: true,
          isQueued: false,
          isBlocked: false,
          progress: prev.progress
            ? {
                ...prev.progress,
                status: data.status,
                itemsProcessed: data.itemsProcessed,
                itemsTotal: data.itemsTotal,
                percentage: data.progressPercent,
                currentFile: data.currentFile,
                elapsedSeconds: data.elapsedSeconds,
              }
            : {
                libraryId: 0,
                librarySlug: slug,
                scanId: data.scanId,
                status: data.status,
                itemsProcessed: data.itemsProcessed,
                itemsTotal: data.itemsTotal,
                percentage: data.progressPercent,
                currentFile: data.currentFile,
                startedAt: null,
                elapsedSeconds: data.elapsedSeconds,
              },
          error: null,
        }))
      } catch (e) {
        console.error('[useScanProgress] Failed to parse scan_progress event:', e)
      }
    })

    // Handle scan_completed event
    eventSource.addEventListener('scan_completed', (event) => {
      try {
        const rawData = JSON.parse(event.data) as RawSSEScanCompletedData
        const data = transformScanCompletedData(rawData)
        console.log('[useScanProgress] Scan completed:', data)

        setState((prev) => ({
          ...prev,
          isScanning: false,
          isQueued: false,
          isBlocked: false,
          progress: null,
          error: null,
          queuePosition: null,
          blockingOperations: [],
        }))

        onScanCompletedRef.current?.(data)
      } catch (e) {
        console.error('[useScanProgress] Failed to parse scan_completed event:', e)
      }
    })

    // Handle scan_failed event
    eventSource.addEventListener('scan_failed', (event) => {
      try {
        const rawData = JSON.parse(event.data) as RawSSEScanFailedData
        const data = transformScanFailedData(rawData)
        console.log('[useScanProgress] Scan failed:', data)

        setState((prev) => ({
          ...prev,
          isScanning: false,
          isQueued: false,
          isBlocked: false,
          progress: null,
          error: data.errorMessage,
          queuePosition: null,
          blockingOperations: [],
        }))

        onScanFailedRef.current?.(data)
      } catch (e) {
        console.error('[useScanProgress] Failed to parse scan_failed event:', e)
      }
    })

    // Handle scan_queued event
    eventSource.addEventListener('scan_queued', (event) => {
      try {
        const rawData = JSON.parse(event.data) as RawSSEScanQueuedData
        const data = transformScanQueuedData(rawData)
        console.log('[useScanProgress] Scan queued:', data)

        setState((prev) => ({
          ...prev,
          isScanning: false,
          isQueued: true,
          isBlocked: data.blockedBy.length > 0,
          progress: null,
          error: null,
          queuePosition: data.queuePosition,
          blockingOperations: data.blockedBy,
        }))
      } catch (e) {
        console.error('[useScanProgress] Failed to parse scan_queued event:', e)
      }
    })

    // Handle scan_blocked event
    eventSource.addEventListener('scan_blocked', (event) => {
      try {
        const rawData = JSON.parse(event.data) as RawSSEScanBlockedData
        const data = transformScanBlockedData(rawData)
        console.log('[useScanProgress] Scan blocked:', data)

        setState((prev) => ({
          ...prev,
          isScanning: false,
          isQueued: prev.isQueued,
          isBlocked: true,
          progress: null,
          error: null,
          blockingOperations: data.blockingOperations,
        }))
      } catch (e) {
        console.error('[useScanProgress] Failed to parse scan_blocked event:', e)
      }
    })

    // Handle heartbeat event (just to confirm connection is alive)
    eventSource.addEventListener('heartbeat', () => {
      // Connection is alive, no state update needed
    })
  }, [slug, enabled, cleanup, enablePollingFallback, startPollingFallback])

  // Main effect: connect on mount, cleanup on unmount
  useEffect(() => {
    if (!slug || !enabled) {
      cleanup()
      setState(initialState)
      return
    }

    connect()

    return cleanup
  }, [slug, enabled, connect, cleanup])

  return state
}

export default useScanProgress
