import { useState, useCallback, useRef, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getBatchUpdateSSEUrl,
  batchUpdateTags,
  transformSSEBatchStartedData,
  transformSSEItemProgressData,
  transformSSEBatchCompletedData,
  transformSSEBatchFailedData,
} from '@/api/batch-tag-editor'
import { scanKeys } from './useScanStatus'
import type {
  TransformationRule,
  BatchTagUpdateState,
  ItemResult,
  SSEBatchStartedData,
  SSEBatchCompletedData,
} from '@/types/batch-tag-editor'

// ============================================================================
// Initial State
// ============================================================================

const initialState: BatchTagUpdateState = {
  isUpdating: false,
  progress: 0,
  itemsProcessed: 0,
  itemsTotal: 0,
  itemsSucceeded: 0,
  itemsFailed: 0,
  error: null,
  isComplete: false,
  results: [],
}

// ============================================================================
// Hook Options
// ============================================================================

export interface UseBatchTagUpdateOptions {
  /**
   * Callback when batch update starts
   */
  onStarted?: (data: SSEBatchStartedData) => void
  /**
   * Callback when batch update completes successfully
   */
  onCompleted?: (data: SSEBatchCompletedData) => void
  /**
   * Callback when batch update fails
   */
  onError?: (error: string) => void
  /**
   * Whether to use SSE for progress updates
   * @default true
   */
  useSSE?: boolean
}

// ============================================================================
// Hook Result
// ============================================================================

export interface UseBatchTagUpdateResult {
  /**
   * Current state of the batch update operation
   */
  state: BatchTagUpdateState
  /**
   * Start the batch update operation
   */
  execute: (slug: string, itemIds: number[], rules: TransformationRule[]) => void
  /**
   * Reset the state to initial values
   */
  reset: () => void
  /**
   * Cancel the current operation (closes SSE connection)
   */
  cancel: () => void
}

// ============================================================================
// Main Hook
// ============================================================================

/**
 * Hook for executing batch tag updates with SSE progress reporting.
 *
 * Supports both SSE-based progress updates and fallback to standard request.
 *
 * @param options - Hook options
 * @returns Batch update state and controls
 */
export function useBatchTagUpdate(
  options: UseBatchTagUpdateOptions = {}
): UseBatchTagUpdateResult {
  const {
    onStarted,
    onCompleted,
    onError,
    useSSE = true,
  } = options

  const [state, setState] = useState<BatchTagUpdateState>(initialState)
  const queryClient = useQueryClient()

  // Refs for managing lifecycle
  const abortControllerRef = useRef<AbortController | null>(null)
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null)

  // Stable callback refs
  const onStartedRef = useRef(onStarted)
  const onCompletedRef = useRef(onCompleted)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onStartedRef.current = onStarted
    onCompletedRef.current = onCompleted
    onErrorRef.current = onError
  }, [onStarted, onCompleted, onError])

  // Cleanup function
  const cleanup = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    if (readerRef.current) {
      readerRef.current.cancel()
      readerRef.current = null
    }
  }, [])

  // Reset state
  const reset = useCallback(() => {
    cleanup()
    setState(initialState)
  }, [cleanup])

  // Cancel operation
  const cancel = useCallback(() => {
    cleanup()
    setState((prev) => ({
      ...prev,
      isUpdating: false,
      error: 'Operation cancelled',
    }))
  }, [cleanup])

  // Execute batch update with SSE
  const executeWithSSE = useCallback(
    async (slug: string, itemIds: number[], rules: TransformationRule[]) => {
      cleanup()

      const abortController = new AbortController()
      abortControllerRef.current = abortController

      setState({
        ...initialState,
        isUpdating: true,
        itemsTotal: itemIds.length,
      })

      const url = getBatchUpdateSSEUrl(slug)
      const requestBody = JSON.stringify({
        item_ids: itemIds,
        rules: rules,
      })

      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
          },
          body: requestBody,
          signal: abortController.signal,
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
          throw new Error(errorData.detail || `HTTP ${response.status}`)
        }

        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('No response body')
        }
        readerRef.current = reader

        const decoder = new TextDecoder()
        let buffer = ''
        const results: ItemResult[] = []

        while (true) {
          const { done, value } = await reader.read()

          if (done) {
            break
          }

          buffer += decoder.decode(value, { stream: true })

          // Process complete SSE events from buffer
          const lines = buffer.split('\n')
          buffer = lines.pop() || '' // Keep incomplete line in buffer

          let eventType = ''
          let eventData = ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              eventData = line.slice(6)
            } else if (line === '' && eventType && eventData) {
              // Process complete event
              try {
                const rawData = JSON.parse(eventData)

                switch (eventType) {
                  case 'batch_started': {
                    const data = transformSSEBatchStartedData(rawData)
                    setState((prev) => ({
                      ...prev,
                      itemsTotal: data.totalItems,
                    }))
                    onStartedRef.current?.(data)
                    break
                  }

                  case 'item_progress': {
                    const data = transformSSEItemProgressData(rawData)
                    results.push({
                      itemId: data.itemId,
                      status: data.status,
                      error: data.error,
                    })
                    setState((prev) => ({
                      ...prev,
                      progress: data.progressPercent,
                      itemsProcessed: data.itemsProcessed,
                      itemsTotal: data.itemsTotal,
                      itemsSucceeded:
                        data.status === 'success'
                          ? prev.itemsSucceeded + 1
                          : prev.itemsSucceeded,
                      itemsFailed:
                        data.status === 'failed'
                          ? prev.itemsFailed + 1
                          : prev.itemsFailed,
                      results: [...results],
                    }))
                    break
                  }

                  case 'batch_completed': {
                    const data = transformSSEBatchCompletedData(rawData)
                    setState((prev) => ({
                      ...prev,
                      isUpdating: false,
                      isComplete: true,
                      progress: 100,
                      itemsTotal: data.itemsTotal,
                      itemsSucceeded: data.itemsSucceeded,
                      itemsFailed: data.itemsFailed,
                      results: [...results],
                    }))
                    onCompletedRef.current?.(data)
                    // Invalidate import items cache to refresh table
                    queryClient.invalidateQueries({
                      queryKey: [...scanKeys.importItems(), slug],
                      exact: false,
                    })
                    break
                  }

                  case 'batch_failed': {
                    const data = transformSSEBatchFailedData(rawData)
                    setState((prev) => ({
                      ...prev,
                      isUpdating: false,
                      error: data.message,
                      results: [...results],
                    }))
                    onErrorRef.current?.(data.message)
                    break
                  }

                  case 'heartbeat':
                    // Connection is alive, no state update needed
                    break
                }
              } catch (e) {
                console.error('[useBatchTagUpdate] Failed to parse SSE event:', e)
              }

              // Reset for next event
              eventType = ''
              eventData = ''
            }
          }
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          // Cancelled, already handled
          return
        }

        const errorMessage = error instanceof Error ? error.message : 'Unknown error'
        setState((prev) => ({
          ...prev,
          isUpdating: false,
          error: errorMessage,
        }))
        onErrorRef.current?.(errorMessage)
      }
    },
    [cleanup, queryClient]
  )

  // Execute batch update without SSE (fallback)
  const executeWithoutSSE = useCallback(
    async (slug: string, itemIds: number[], rules: TransformationRule[]) => {
      cleanup()

      setState({
        ...initialState,
        isUpdating: true,
        itemsTotal: itemIds.length,
      })

      try {
        const response = await batchUpdateTags(slug, itemIds, rules)

        setState({
          isUpdating: false,
          progress: 100,
          itemsProcessed: response.itemsTotal,
          itemsTotal: response.itemsTotal,
          itemsSucceeded: response.itemsSucceeded,
          itemsFailed: response.itemsFailed,
          error: null,
          isComplete: true,
          results: response.results,
        })

        onCompletedRef.current?.({
          itemsTotal: response.itemsTotal,
          itemsSucceeded: response.itemsSucceeded,
          itemsFailed: response.itemsFailed,
          completedAt: response.completedAt,
          durationSeconds: response.durationSeconds,
        })

        // Invalidate import items cache to refresh table
        queryClient.invalidateQueries({
          queryKey: [...scanKeys.importItems(), slug],
          exact: false,
        })
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error'
        setState((prev) => ({
          ...prev,
          isUpdating: false,
          error: errorMessage,
        }))
        onErrorRef.current?.(errorMessage)
      }
    },
    [cleanup, queryClient]
  )

  // Main execute function
  const execute = useCallback(
    (slug: string, itemIds: number[], rules: TransformationRule[]) => {
      if (useSSE) {
        executeWithSSE(slug, itemIds, rules)
      } else {
        executeWithoutSSE(slug, itemIds, rules)
      }
    },
    [useSSE, executeWithSSE, executeWithoutSSE]
  )

  // Cleanup on unmount
  useEffect(() => {
    return cleanup
  }, [cleanup])

  return {
    state,
    execute,
    reset,
    cancel,
  }
}

export default useBatchTagUpdate
