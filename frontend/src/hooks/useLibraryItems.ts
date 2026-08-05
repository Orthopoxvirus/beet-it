import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, useCallback, useRef, useEffect } from 'react'
import {
  getLibraryItems,
  getLibraryAlbumsForPicker,
  previewLibraryItems,
  batchUpdateLibraryItems,
  getBatchUpdateStatus,
  getLibraryBatchUpdateSSEUrl,
  type LibraryItemsParams,
} from '@/api/libraryItems'
import type {
  TransformationRule,
  BatchPreviewResponse,
  ItemPreview,
  TagName,
  ItemResult,
  ItemError,
  SSEBatchStartedData,
  SSEBatchCompletedData,
} from '@/types/batch-tag-editor'

// ============================================================================
// Query Keys
// ============================================================================

export const libraryItemsKeys = {
  all: ['libraryItems'] as const,
  lists: () => [...libraryItemsKeys.all, 'list'] as const,
  list: (slug: string, params: LibraryItemsParams) =>
    [...libraryItemsKeys.lists(), { slug, ...params }] as const,
  albums: () => [...libraryItemsKeys.all, 'albums'] as const,
  albumList: (slug: string) => [...libraryItemsKeys.albums(), slug] as const,
  preview: () => [...libraryItemsKeys.all, 'preview'] as const,
  previewBySlug: (slug: string, itemIds: number[], rules: TransformationRule[]) =>
    [...libraryItemsKeys.preview(), slug, { itemIds, rules }] as const,
  batchUpdateStatus: () => [...libraryItemsKeys.all, 'batchUpdateStatus'] as const,
  status: (slug: string, jobId: string) =>
    [...libraryItemsKeys.batchUpdateStatus(), { slug, jobId }] as const,
}

// ============================================================================
// useLibraryItems - Fetch library items with pagination and filtering
// ============================================================================

export interface UseLibraryItemsOptions {
  album?: string
  /** Fetch items for multiple beets album ids. Preferred over `album`. */
  albumIds?: number[]
  page?: number
  perPage?: number
  enabled?: boolean
}

export function useLibraryItems(
  slug: string | undefined,
  options: UseLibraryItemsOptions = {}
) {
  const { album, albumIds, page = 1, perPage = 100, enabled = true } = options

  const params: LibraryItemsParams = {
    album,
    albumIds,
    page,
    per_page: perPage,
  }

  return useQuery({
    queryKey: libraryItemsKeys.list(slug || '', params),
    queryFn: () => getLibraryItems(slug!, params),
    // Skip when there's no real filter *and* the caller didn't ask for all items.
    // An empty albumIds list is treated as "don't fetch yet" (folder selection
    // clearing), while an absent albumIds is "fetch all".
    enabled: !!slug && enabled && (albumIds === undefined || albumIds.length > 0),
    retry: false,
    staleTime: 30000, // 30 seconds
  })
}

// ============================================================================
// useLibraryAlbumsForPicker - Fetch albums for selection UI
// ============================================================================

export function useLibraryAlbumsForPicker(slug: string | undefined) {
  return useQuery({
    queryKey: libraryItemsKeys.albumList(slug || ''),
    queryFn: () => getLibraryAlbumsForPicker(slug!),
    enabled: !!slug,
    retry: false,
    staleTime: 60000, // 1 minute
  })
}

// ============================================================================
// useLibraryItemsPreview - Preview transformations on library items
// ============================================================================

export interface UseLibraryItemsPreviewOptions {
  enabled?: boolean
}

export interface UseLibraryItemsPreviewResult {
  data: BatchPreviewResponse | undefined
  isLoading: boolean
  isFetching: boolean
  error: Error | null
  previewMap: Map<number, ItemPreview>
  getPreviewValue: (itemId: number, tag: TagName) => string | undefined
  hasChanges: boolean
}

export function useLibraryItemsPreview(
  slug: string | undefined,
  itemIds: number[],
  rules: TransformationRule[],
  options: UseLibraryItemsPreviewOptions = {}
): UseLibraryItemsPreviewResult {
  const { enabled = true } = options

  const shouldFetch = Boolean(
    slug &&
    itemIds.length > 0 &&
    rules.length > 0 &&
    enabled
  )

  const query = useQuery({
    queryKey: libraryItemsKeys.previewBySlug(slug || '', itemIds, rules),
    queryFn: () => previewLibraryItems(slug!, itemIds, rules),
    enabled: shouldFetch,
    placeholderData: (previousData) => previousData,
    staleTime: 30000,
    gcTime: 60000,
    retry: false,
  })

  // When shouldFetch is false (e.g. after Reset clears all rules) we return an empty map
  // so stale previews from a prior query do not leak into the UI.
  const previewMap = useMemo(() => {
    const map = new Map<number, ItemPreview>()
    if (shouldFetch && query.data?.previews) {
      for (const preview of query.data.previews) {
        map.set(preview.itemId, preview)
      }
    }
    return map
  }, [shouldFetch, query.data?.previews])

  const getPreviewValue = (itemId: number, tag: TagName): string | undefined => {
    const preview = previewMap.get(itemId)
    return preview?.changes[tag]
  }

  const hasChanges = useMemo(() => {
    if (!shouldFetch || !query.data?.previews) return false
    return query.data.previews.some(
      (preview) => Object.keys(preview.changes).length > 0
    )
  }, [shouldFetch, query.data?.previews])

  return {
    data: query.data,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.error as Error | null,
    previewMap,
    getPreviewValue,
    hasChanges,
  }
}

// ============================================================================
// useLibraryItemsBatchUpdate - Mutation for applying batch updates
// ============================================================================

export function useLibraryItemsBatchUpdate() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      slug,
      itemIds,
      rules,
    }: {
      slug: string
      itemIds: number[]
      rules: TransformationRule[]
    }) => batchUpdateLibraryItems(slug, itemIds, rules),
    onSuccess: (data) => {
      // Invalidate library items cache
      queryClient.invalidateQueries({
        queryKey: libraryItemsKeys.lists(),
      })
      // Return job ID for status polling
      return data
    },
  })
}

// ============================================================================
// useBatchUpdateStatus - Poll for batch update job status
// ============================================================================

export interface UseBatchUpdateStatusOptions {
  enabled?: boolean
  refetchInterval?: number | false
}

export function useBatchUpdateStatus(
  slug: string | undefined,
  jobId: string | undefined,
  options: UseBatchUpdateStatusOptions = {}
) {
  const {
    enabled = true,
    refetchInterval = 2000, // 2 seconds
  } = options

  return useQuery({
    queryKey: libraryItemsKeys.status(slug || '', jobId || ''),
    queryFn: () => getBatchUpdateStatus(slug!, jobId!),
    enabled: !!slug && !!jobId && enabled,
    refetchInterval: (query) => {
      // Stop polling when job completes or fails ('partial' is the backend's
      // terminal state when some albums synced and some failed)
      const status = query.state.data?.status
      if (status === 'completed' || status === 'failed' || status === 'partial') {
        return false
      }
      return refetchInterval
    },
    retry: false,
    staleTime: 0, // Always fetch fresh status
  })
}

// ============================================================================
// useLibraryBatchTagUpdate - SSE-based batch update with progress
// ============================================================================

interface RawItemError {
  code: string
  message: string
  file_path?: string
}

interface RawSSEBatchStartedData {
  total_items: number
  started_at: string
}

interface RawSSEBatchCompletedData {
  items_total: number
  items_succeeded: number
  items_failed: number
  completed_at: string
  duration_seconds: number
  job_id?: string
  albums_to_sync?: string[]
}

function transformItemError(raw: RawItemError): ItemError {
  return {
    code: raw.code,
    message: raw.message,
    file_path: raw.file_path,
  }
}

function transformSSEBatchStartedData(raw: RawSSEBatchStartedData): SSEBatchStartedData {
  return {
    totalItems: raw.total_items,
    startedAt: raw.started_at,
  }
}

function transformSSEBatchCompletedData(raw: RawSSEBatchCompletedData): SSEBatchCompletedData & { jobId?: string; albumsToSync?: string[] } {
  return {
    itemsTotal: raw.items_total,
    itemsSucceeded: raw.items_succeeded,
    itemsFailed: raw.items_failed,
    completedAt: raw.completed_at,
    durationSeconds: raw.duration_seconds,
    jobId: raw.job_id,
    albumsToSync: raw.albums_to_sync,
  }
}

export interface LibraryBatchTagUpdateState {
  isUpdating: boolean
  progress: number
  itemsProcessed: number
  itemsTotal: number
  itemsSucceeded: number
  itemsFailed: number
  error: string | null
  isComplete: boolean
  results: ItemResult[]
  jobId: string | null
  albumsToSync: string[]
}

const initialState: LibraryBatchTagUpdateState = {
  isUpdating: false,
  progress: 0,
  itemsProcessed: 0,
  itemsTotal: 0,
  itemsSucceeded: 0,
  itemsFailed: 0,
  error: null,
  isComplete: false,
  results: [],
  jobId: null,
  albumsToSync: [],
}

export interface UseLibraryBatchTagUpdateOptions {
  onStarted?: (data: SSEBatchStartedData) => void
  onCompleted?: (data: SSEBatchCompletedData & { jobId?: string; albumsToSync?: string[] }) => void
  onError?: (error: string) => void
  useSSE?: boolean
}

export interface UseLibraryBatchTagUpdateResult {
  state: LibraryBatchTagUpdateState
  execute: (slug: string, itemIds: number[], rules: TransformationRule[]) => void
  reset: () => void
  cancel: () => void
}

export function useLibraryBatchTagUpdate(
  options: UseLibraryBatchTagUpdateOptions = {}
): UseLibraryBatchTagUpdateResult {
  // Default to the JSON path: the /library-items/batch-update backend
  // route returns plain JSON regardless of the Accept header, so going
  // through executeWithSSE just reads the JSON body, never matches an
  // event line, and gets stuck in isUpdating: true forever ("Applying…"
  // spinner that never resolves). SSE here was vestigial; opt-in only.
  const {
    onStarted,
    onCompleted,
    onError,
    useSSE = false,
  } = options

  const [state, setState] = useState<LibraryBatchTagUpdateState>(initialState)
  const queryClient = useQueryClient()

  const abortControllerRef = useRef<AbortController | null>(null)
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null)

  const onStartedRef = useRef(onStarted)
  const onCompletedRef = useRef(onCompleted)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onStartedRef.current = onStarted
    onCompletedRef.current = onCompleted
    onErrorRef.current = onError
  }, [onStarted, onCompleted, onError])

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

  const reset = useCallback(() => {
    cleanup()
    setState(initialState)
  }, [cleanup])

  const cancel = useCallback(() => {
    cleanup()
    setState((prev) => ({
      ...prev,
      isUpdating: false,
      error: 'Operation cancelled',
    }))
  }, [cleanup])

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

      const url = getLibraryBatchUpdateSSEUrl(slug)
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

          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          let eventType = ''
          let eventData = ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              eventData = line.slice(6)
            } else if (line === '' && eventType && eventData) {
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
                    const data = {
                      itemId: rawData.item_id,
                      status: rawData.status,
                      itemsProcessed: rawData.items_processed,
                      itemsTotal: rawData.items_total,
                      progressPercent: rawData.progress_percent,
                      error: rawData.error ? transformItemError(rawData.error) : undefined,
                    }
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
                      jobId: data.jobId || null,
                      albumsToSync: data.albumsToSync || [],
                    }))
                    onCompletedRef.current?.(data)
                    // Invalidate library items cache
                    queryClient.invalidateQueries({
                      queryKey: libraryItemsKeys.lists(),
                    })
                    break
                  }

                  case 'batch_failed': {
                    const data = {
                      errorCode: rawData.error_code,
                      message: rawData.message,
                      failedAt: rawData.failed_at,
                    }
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
                    break
                }
              } catch (e) {
                console.error('[useLibraryBatchTagUpdate] Failed to parse SSE event:', e)
              }

              eventType = ''
              eventData = ''
            }
          }
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
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

  const executeWithoutSSE = useCallback(
    async (slug: string, itemIds: number[], rules: TransformationRule[]) => {
      cleanup()

      setState({
        ...initialState,
        isUpdating: true,
        itemsTotal: itemIds.length,
      })

      try {
        const response = await batchUpdateLibraryItems(slug, itemIds, rules)

        // Surface per-item failures so the form can render them; otherwise
        // a "0 succeeded, 1 failed" line dangles with no clue what broke.
        const mappedResults: ItemResult[] = (response.results ?? []).map(
          (raw) => ({
            itemId: raw.item_id,
            status: raw.status,
            changesApplied: raw.changes_applied
              ? (raw.changes_applied as ItemResult['changesApplied'])
              : undefined,
            error: raw.error
              ? {
                  code: raw.error.code,
                  message: raw.error.message,
                  file_path: raw.error.file_path ?? undefined,
                }
              : undefined,
          })
        )

        setState({
          isUpdating: false,
          progress: 100,
          itemsProcessed: response.items_total,
          itemsTotal: response.items_total,
          itemsSucceeded: response.items_succeeded,
          itemsFailed: response.items_failed,
          error: null,
          isComplete: true,
          results: mappedResults,
          jobId: response.job_id,
          albumsToSync: response.albums_to_sync,
        })

        onCompletedRef.current?.({
          itemsTotal: response.items_total,
          itemsSucceeded: response.items_succeeded,
          itemsFailed: response.items_failed,
          completedAt: new Date().toISOString(),
          durationSeconds: 0,
          jobId: response.job_id,
          albumsToSync: response.albums_to_sync,
        })

        queryClient.invalidateQueries({
          queryKey: libraryItemsKeys.lists(),
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
