import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import {
  useLibraryItems,
  useLibraryAlbumsForPicker,
  useLibraryItemsPreview,
  useLibraryItemsBatchUpdate,
  useBatchUpdateStatus,
  libraryItemsKeys,
} from './useLibraryItems'
import * as libraryItemsApi from '@/api/libraryItems'
import type {
  LibraryItemsResponse,
  LibraryAlbumsResponse,
  LibraryBatchUpdateResponse,
  BatchUpdateStatusResponse,
} from '@/api/libraryItems'
import type { BatchPreviewResponse, TransformationRule } from '@/types/batch-tag-editor'

// Mock the API module
vi.mock('@/api/libraryItems', () => ({
  getLibraryItems: vi.fn(),
  getLibraryAlbumsForPicker: vi.fn(),
  previewLibraryItems: vi.fn(),
  batchUpdateLibraryItems: vi.fn(),
  getBatchUpdateStatus: vi.fn(),
  getLibraryBatchUpdateSSEUrl: vi.fn(() => '/api/v1/libraries/test/library-items/batch-update'),
}))

describe('useLibraryItems hooks', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    queryClient.clear()
  })

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  // ============================================================================
  // Mock Data
  // ============================================================================

  const mockLibraryItemsResponse: LibraryItemsResponse = {
    items: [
      {
        id: 1,
        title: 'Come Together',
        artist: 'The Beatles',
        album: 'Abbey Road',
        album_artist: 'The Beatles',
        album_id: 1,
        track_number: 1,
        disc_number: 1,
        genre: 'Rock',
        path: '/music/Abbey Road/01 - Come Together.mp3',
        duration: 259,
        format: 'MP3',
        bitrate: 320,
      },
      {
        id: 2,
        title: 'Something',
        artist: 'The Beatles',
        album: 'Abbey Road',
        album_artist: 'The Beatles',
        album_id: 1,
        track_number: 2,
        disc_number: 1,
        genre: 'Rock',
        path: '/music/Abbey Road/02 - Something.mp3',
        duration: 183,
        format: 'MP3',
        bitrate: 320,
      },
    ],
    total: 2,
    page: 1,
    per_page: 100,
    album_filter: 'Abbey Road',
  }

  const mockAlbumsResponse: LibraryAlbumsResponse = {
    albums: [
      { id: 1, title: 'Abbey Road', artist: 'The Beatles', track_count: 17 },
      { id: 2, title: 'Dark Side of the Moon', artist: 'Pink Floyd', track_count: 10 },
    ],
    total: 2,
  }

  const mockPreviewResponse: BatchPreviewResponse = {
    previews: [
      { itemId: 1, changes: { album: 'New Album Name' } },
      { itemId: 2, changes: { album: 'New Album Name' } },
    ],
    errors: [],
  }

  const mockBatchUpdateResponse: LibraryBatchUpdateResponse = {
    status: 'completed',
    job_id: 'job-123',
    items_total: 2,
    items_succeeded: 2,
    items_failed: 0,
    albums_to_sync: ['Abbey Road'],
  }

  const mockBatchUpdateStatusResponse: BatchUpdateStatusResponse = {
    job_id: 'job-123',
    status: 'completed',
    started_at: '2026-03-01T10:00:00Z',
    completed_at: '2026-03-01T10:00:05Z',
    file_writes: {
      total: 2,
      succeeded: 2,
      failed: 0,
    },
    beets_updates: [
      { album: 'Abbey Road', status: 'success' },
    ],
  }

  // ============================================================================
  // Query Keys Tests
  // ============================================================================

  describe('libraryItemsKeys', () => {
    it('should have correct base query key', () => {
      expect(libraryItemsKeys.all).toEqual(['libraryItems'])
    })

    it('should generate correct lists key', () => {
      expect(libraryItemsKeys.lists()).toEqual(['libraryItems', 'list'])
    })

    it('should generate correct list key with params', () => {
      const params = { album: 'Abbey Road', page: 1, per_page: 100 }
      expect(libraryItemsKeys.list('test-library', params)).toEqual([
        'libraryItems',
        'list',
        { slug: 'test-library', album: 'Abbey Road', page: 1, per_page: 100 },
      ])
    })

    it('should generate correct albums key', () => {
      expect(libraryItemsKeys.albums()).toEqual(['libraryItems', 'albums'])
    })

    it('should generate correct albumList key', () => {
      expect(libraryItemsKeys.albumList('test-library')).toEqual([
        'libraryItems',
        'albums',
        'test-library',
      ])
    })

    it('should generate correct preview key', () => {
      expect(libraryItemsKeys.preview()).toEqual(['libraryItems', 'preview'])
    })

    it('should generate correct previewBySlug key', () => {
      const itemIds = [1, 2]
      const rules: TransformationRule[] = [{ tag: 'album', mode: 'fixed', value: 'New Album' }]
      expect(libraryItemsKeys.previewBySlug('test-library', itemIds, rules)).toEqual([
        'libraryItems',
        'preview',
        'test-library',
        { itemIds, rules },
      ])
    })

    it('should generate correct batchUpdateStatus key', () => {
      expect(libraryItemsKeys.batchUpdateStatus()).toEqual(['libraryItems', 'batchUpdateStatus'])
    })

    it('should generate correct status key', () => {
      expect(libraryItemsKeys.status('test-library', 'job-123')).toEqual([
        'libraryItems',
        'batchUpdateStatus',
        { slug: 'test-library', jobId: 'job-123' },
      ])
    })
  })

  // ============================================================================
  // useLibraryItems Tests
  // ============================================================================

  describe('useLibraryItems', () => {
    it('should fetch library items', async () => {
      vi.mocked(libraryItemsApi.getLibraryItems).mockResolvedValue(mockLibraryItemsResponse)

      const { result } = renderHook(
        () => useLibraryItems('test-library', { album: 'Abbey Road' }),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(libraryItemsApi.getLibraryItems).toHaveBeenCalledWith('test-library', {
        album: 'Abbey Road',
        page: 1,
        per_page: 100,
      })
      expect(result.current.data).toEqual(mockLibraryItemsResponse)
    })

    it('should not fetch when slug is undefined', async () => {
      vi.mocked(libraryItemsApi.getLibraryItems).mockResolvedValue(mockLibraryItemsResponse)

      renderHook(() => useLibraryItems(undefined), { wrapper })

      // Wait a bit to ensure no fetch occurs
      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(libraryItemsApi.getLibraryItems).not.toHaveBeenCalled()
    })

    it('should not fetch when disabled', async () => {
      vi.mocked(libraryItemsApi.getLibraryItems).mockResolvedValue(mockLibraryItemsResponse)

      renderHook(() => useLibraryItems('test-library', { enabled: false }), { wrapper })

      // Wait a bit to ensure no fetch occurs
      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(libraryItemsApi.getLibraryItems).not.toHaveBeenCalled()
    })

    it('should use default pagination values', async () => {
      vi.mocked(libraryItemsApi.getLibraryItems).mockResolvedValue(mockLibraryItemsResponse)

      const { result } = renderHook(() => useLibraryItems('test-library'), { wrapper })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(libraryItemsApi.getLibraryItems).toHaveBeenCalledWith('test-library', {
        album: undefined,
        page: 1,
        per_page: 100,
      })
    })

    it('should handle fetch errors', async () => {
      const error = new Error('Network error')
      vi.mocked(libraryItemsApi.getLibraryItems).mockRejectedValue(error)

      const { result } = renderHook(() => useLibraryItems('test-library'), { wrapper })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error).toBeDefined()
    })

    it('should respect custom perPage parameter', async () => {
      vi.mocked(libraryItemsApi.getLibraryItems).mockResolvedValue(mockLibraryItemsResponse)

      const { result } = renderHook(
        () => useLibraryItems('test-library', { perPage: 500 }),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(libraryItemsApi.getLibraryItems).toHaveBeenCalledWith('test-library', {
        album: undefined,
        page: 1,
        per_page: 500,
      })
    })
  })

  // ============================================================================
  // useLibraryAlbumsForPicker Tests
  // ============================================================================

  describe('useLibraryAlbumsForPicker', () => {
    it('should fetch albums', async () => {
      vi.mocked(libraryItemsApi.getLibraryAlbumsForPicker).mockResolvedValue(mockAlbumsResponse)

      const { result } = renderHook(() => useLibraryAlbumsForPicker('test-library'), { wrapper })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(libraryItemsApi.getLibraryAlbumsForPicker).toHaveBeenCalledWith('test-library')
      expect(result.current.data).toEqual(mockAlbumsResponse)
    })

    it('should not fetch when slug is undefined', async () => {
      vi.mocked(libraryItemsApi.getLibraryAlbumsForPicker).mockResolvedValue(mockAlbumsResponse)

      renderHook(() => useLibraryAlbumsForPicker(undefined), { wrapper })

      // Wait a bit to ensure no fetch occurs
      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(libraryItemsApi.getLibraryAlbumsForPicker).not.toHaveBeenCalled()
    })

    it('should handle fetch errors', async () => {
      const error = new Error('Database error')
      vi.mocked(libraryItemsApi.getLibraryAlbumsForPicker).mockRejectedValue(error)

      const { result } = renderHook(() => useLibraryAlbumsForPicker('test-library'), { wrapper })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })
    })
  })

  // ============================================================================
  // useLibraryItemsPreview Tests
  // ============================================================================

  describe('useLibraryItemsPreview', () => {
    const mockRules: TransformationRule[] = [
      { tag: 'album', mode: 'fixed', value: 'New Album Name' },
    ]

    it('should fetch preview when conditions are met', async () => {
      vi.mocked(libraryItemsApi.previewLibraryItems).mockResolvedValue(mockPreviewResponse)

      const { result } = renderHook(
        () => useLibraryItemsPreview('test-library', [1, 2], mockRules),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.previewMap.size).toBe(2)
      })

      expect(libraryItemsApi.previewLibraryItems).toHaveBeenCalledWith(
        'test-library',
        [1, 2],
        mockRules
      )
    })

    it('should not fetch when slug is undefined', async () => {
      vi.mocked(libraryItemsApi.previewLibraryItems).mockResolvedValue(mockPreviewResponse)

      renderHook(() => useLibraryItemsPreview(undefined, [1, 2], mockRules), { wrapper })

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(libraryItemsApi.previewLibraryItems).not.toHaveBeenCalled()
    })

    it('should not fetch when itemIds is empty', async () => {
      vi.mocked(libraryItemsApi.previewLibraryItems).mockResolvedValue(mockPreviewResponse)

      renderHook(() => useLibraryItemsPreview('test-library', [], mockRules), { wrapper })

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(libraryItemsApi.previewLibraryItems).not.toHaveBeenCalled()
    })

    it('should not fetch when rules is empty', async () => {
      vi.mocked(libraryItemsApi.previewLibraryItems).mockResolvedValue(mockPreviewResponse)

      renderHook(() => useLibraryItemsPreview('test-library', [1, 2], []), { wrapper })

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(libraryItemsApi.previewLibraryItems).not.toHaveBeenCalled()
    })

    it('should not fetch when disabled', async () => {
      vi.mocked(libraryItemsApi.previewLibraryItems).mockResolvedValue(mockPreviewResponse)

      renderHook(
        () => useLibraryItemsPreview('test-library', [1, 2], mockRules, { enabled: false }),
        { wrapper }
      )

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(libraryItemsApi.previewLibraryItems).not.toHaveBeenCalled()
    })

    it('should return previewMap with item previews', async () => {
      vi.mocked(libraryItemsApi.previewLibraryItems).mockResolvedValue(mockPreviewResponse)

      const { result } = renderHook(
        () => useLibraryItemsPreview('test-library', [1, 2], mockRules),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.previewMap.size).toBe(2)
      })

      expect(result.current.previewMap.get(1)).toEqual({
        itemId: 1,
        changes: { album: 'New Album Name' },
      })
      expect(result.current.previewMap.get(2)).toEqual({
        itemId: 2,
        changes: { album: 'New Album Name' },
      })
    })

    it('should return hasChanges true when previews have changes', async () => {
      vi.mocked(libraryItemsApi.previewLibraryItems).mockResolvedValue(mockPreviewResponse)

      const { result } = renderHook(
        () => useLibraryItemsPreview('test-library', [1, 2], mockRules),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.hasChanges).toBe(true)
      })
    })

    it('should return hasChanges false when no previews', async () => {
      vi.mocked(libraryItemsApi.previewLibraryItems).mockResolvedValue({
        previews: [],
        errors: [],
      })

      const { result } = renderHook(
        () => useLibraryItemsPreview('test-library', [1, 2], mockRules),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.data).toBeDefined()
      })

      expect(result.current.hasChanges).toBe(false)
    })

    it('should provide getPreviewValue helper function', async () => {
      vi.mocked(libraryItemsApi.previewLibraryItems).mockResolvedValue(mockPreviewResponse)

      const { result } = renderHook(
        () => useLibraryItemsPreview('test-library', [1, 2], mockRules),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.previewMap.size).toBe(2)
      })

      expect(result.current.getPreviewValue(1, 'album')).toBe('New Album Name')
      expect(result.current.getPreviewValue(1, 'artist')).toBeUndefined()
      expect(result.current.getPreviewValue(999, 'album')).toBeUndefined()
    })

    it('should handle preview errors', async () => {
      const error = new Error('Invalid regex pattern')
      vi.mocked(libraryItemsApi.previewLibraryItems).mockRejectedValue(error)

      const { result } = renderHook(
        () => useLibraryItemsPreview('test-library', [1, 2], mockRules),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.error).toBeDefined()
      })
    })
  })

  // ============================================================================
  // useLibraryItemsBatchUpdate Tests
  // ============================================================================

  describe('useLibraryItemsBatchUpdate', () => {
    const mockRules: TransformationRule[] = [
      { tag: 'album', mode: 'fixed', value: 'New Album Name' },
    ]

    it('should execute batch update mutation', async () => {
      vi.mocked(libraryItemsApi.batchUpdateLibraryItems).mockResolvedValue(mockBatchUpdateResponse)

      const { result } = renderHook(() => useLibraryItemsBatchUpdate(), { wrapper })

      await act(async () => {
        result.current.mutate({
          slug: 'test-library',
          itemIds: [1, 2],
          rules: mockRules,
        })
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(libraryItemsApi.batchUpdateLibraryItems).toHaveBeenCalledWith(
        'test-library',
        [1, 2],
        mockRules
      )
      expect(result.current.data).toEqual(mockBatchUpdateResponse)
    })

    it('should handle mutation errors', async () => {
      const error = new Error('Write permission denied')
      vi.mocked(libraryItemsApi.batchUpdateLibraryItems).mockRejectedValue(error)

      const { result } = renderHook(() => useLibraryItemsBatchUpdate(), { wrapper })

      await act(async () => {
        result.current.mutate({
          slug: 'test-library',
          itemIds: [1, 2],
          rules: mockRules,
        })
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })
    })

    it('should invalidate queries on success', async () => {
      vi.mocked(libraryItemsApi.batchUpdateLibraryItems).mockResolvedValue(mockBatchUpdateResponse)

      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

      const { result } = renderHook(() => useLibraryItemsBatchUpdate(), { wrapper })

      await act(async () => {
        result.current.mutate({
          slug: 'test-library',
          itemIds: [1, 2],
          rules: mockRules,
        })
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: libraryItemsKeys.lists(),
      })
    })
  })

  // ============================================================================
  // useBatchUpdateStatus Tests
  // ============================================================================

  describe('useBatchUpdateStatus', () => {
    it('should fetch batch update status', async () => {
      vi.mocked(libraryItemsApi.getBatchUpdateStatus).mockResolvedValue(mockBatchUpdateStatusResponse)

      const { result } = renderHook(
        () => useBatchUpdateStatus('test-library', 'job-123'),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(libraryItemsApi.getBatchUpdateStatus).toHaveBeenCalledWith('test-library', 'job-123')
      expect(result.current.data).toEqual(mockBatchUpdateStatusResponse)
    })

    it('should not fetch when slug is undefined', async () => {
      vi.mocked(libraryItemsApi.getBatchUpdateStatus).mockResolvedValue(mockBatchUpdateStatusResponse)

      renderHook(() => useBatchUpdateStatus(undefined, 'job-123'), { wrapper })

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(libraryItemsApi.getBatchUpdateStatus).not.toHaveBeenCalled()
    })

    it('should not fetch when jobId is undefined', async () => {
      vi.mocked(libraryItemsApi.getBatchUpdateStatus).mockResolvedValue(mockBatchUpdateStatusResponse)

      renderHook(() => useBatchUpdateStatus('test-library', undefined), { wrapper })

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(libraryItemsApi.getBatchUpdateStatus).not.toHaveBeenCalled()
    })

    it('should not fetch when disabled', async () => {
      vi.mocked(libraryItemsApi.getBatchUpdateStatus).mockResolvedValue(mockBatchUpdateStatusResponse)

      renderHook(
        () => useBatchUpdateStatus('test-library', 'job-123', { enabled: false }),
        { wrapper }
      )

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(libraryItemsApi.getBatchUpdateStatus).not.toHaveBeenCalled()
    })

    it('should handle status fetch errors', async () => {
      const error = new Error('Job not found')
      vi.mocked(libraryItemsApi.getBatchUpdateStatus).mockRejectedValue(error)

      const { result } = renderHook(
        () => useBatchUpdateStatus('test-library', 'job-123'),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })
    })
  })

  // ============================================================================
  // useLibraryBatchTagUpdate Tests (SSE-based)
  // ============================================================================

  describe('useLibraryBatchTagUpdate', () => {
    const mockRules: TransformationRule[] = [
      { tag: 'album', mode: 'fixed', value: 'New Album Name' },
    ]

    beforeEach(() => {
      // Mock fetch for SSE
      global.fetch = vi.fn()
    })

    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('should initialize with default state', async () => {
      // Import the hook dynamically to test SSE behavior
      const { useLibraryBatchTagUpdate } = await import('./useLibraryItems')

      const { result } = renderHook(() => useLibraryBatchTagUpdate(), { wrapper })

      expect(result.current.state).toEqual({
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
      })
    })

    it('should have execute, reset, and cancel functions', async () => {
      const { useLibraryBatchTagUpdate } = await import('./useLibraryItems')

      const { result } = renderHook(() => useLibraryBatchTagUpdate(), { wrapper })

      expect(typeof result.current.execute).toBe('function')
      expect(typeof result.current.reset).toBe('function')
      expect(typeof result.current.cancel).toBe('function')
    })

    it('should reset state when reset is called', async () => {
      const { useLibraryBatchTagUpdate } = await import('./useLibraryItems')

      const { result } = renderHook(() => useLibraryBatchTagUpdate(), { wrapper })

      act(() => {
        result.current.reset()
      })

      expect(result.current.state.isUpdating).toBe(false)
      expect(result.current.state.progress).toBe(0)
      expect(result.current.state.error).toBeNull()
    })

    it('should call onStarted callback when batch starts', async () => {
      const { useLibraryBatchTagUpdate } = await import('./useLibraryItems')

      const onStarted = vi.fn()

      // Create a mock response that simulates SSE
      const mockResponse = {
        ok: true,
        body: {
          getReader: () => ({
            read: vi
              .fn()
              .mockResolvedValueOnce({
                done: false,
                value: new TextEncoder().encode(
                  'event: batch_started\ndata: {"total_items": 2, "started_at": "2026-03-01T10:00:00Z"}\n\n'
                ),
              })
              .mockResolvedValueOnce({
                done: false,
                value: new TextEncoder().encode(
                  'event: batch_completed\ndata: {"items_total": 2, "items_succeeded": 2, "items_failed": 0, "completed_at": "2026-03-01T10:00:05Z", "duration_seconds": 5}\n\n'
                ),
              })
              .mockResolvedValueOnce({ done: true, value: undefined }),
            cancel: vi.fn(),
          }),
        },
      }

      vi.mocked(global.fetch).mockResolvedValue(mockResponse as unknown as Response)

      const { result } = renderHook(
        () => useLibraryBatchTagUpdate({ onStarted, useSSE: true }),
        { wrapper }
      )

      await act(async () => {
        result.current.execute('test-library', [1, 2], mockRules)
      })

      await waitFor(() => {
        expect(onStarted).toHaveBeenCalled()
      })
    })

    it('should call onCompleted callback when batch completes', async () => {
      const { useLibraryBatchTagUpdate } = await import('./useLibraryItems')

      const onCompleted = vi.fn()

      const mockResponse = {
        ok: true,
        body: {
          getReader: () => ({
            read: vi
              .fn()
              .mockResolvedValueOnce({
                done: false,
                value: new TextEncoder().encode(
                  'event: batch_started\ndata: {"total_items": 2, "started_at": "2026-03-01T10:00:00Z"}\n\n'
                ),
              })
              .mockResolvedValueOnce({
                done: false,
                value: new TextEncoder().encode(
                  'event: batch_completed\ndata: {"items_total": 2, "items_succeeded": 2, "items_failed": 0, "completed_at": "2026-03-01T10:00:05Z", "duration_seconds": 5, "job_id": "job-123", "albums_to_sync": ["Abbey Road"]}\n\n'
                ),
              })
              .mockResolvedValueOnce({ done: true, value: undefined }),
            cancel: vi.fn(),
          }),
        },
      }

      vi.mocked(global.fetch).mockResolvedValue(mockResponse as unknown as Response)

      const { result } = renderHook(
        () => useLibraryBatchTagUpdate({ onCompleted, useSSE: true }),
        { wrapper }
      )

      await act(async () => {
        result.current.execute('test-library', [1, 2], mockRules)
      })

      await waitFor(() => {
        expect(onCompleted).toHaveBeenCalledWith(
          expect.objectContaining({
            itemsTotal: 2,
            itemsSucceeded: 2,
            itemsFailed: 0,
            jobId: 'job-123',
            albumsToSync: ['Abbey Road'],
          })
        )
      })
    })

    it('should call onError callback when batch fails', async () => {
      const { useLibraryBatchTagUpdate } = await import('./useLibraryItems')

      const onError = vi.fn()

      const mockResponse = {
        ok: true,
        body: {
          getReader: () => ({
            read: vi
              .fn()
              .mockResolvedValueOnce({
                done: false,
                value: new TextEncoder().encode(
                  'event: batch_failed\ndata: {"error_code": "WRITE_ERROR", "message": "Permission denied", "failed_at": "2026-03-01T10:00:01Z"}\n\n'
                ),
              })
              .mockResolvedValueOnce({ done: true, value: undefined }),
            cancel: vi.fn(),
          }),
        },
      }

      vi.mocked(global.fetch).mockResolvedValue(mockResponse as unknown as Response)

      const { result } = renderHook(
        () => useLibraryBatchTagUpdate({ onError, useSSE: true }),
        { wrapper }
      )

      await act(async () => {
        result.current.execute('test-library', [1, 2], mockRules)
      })

      await waitFor(() => {
        expect(onError).toHaveBeenCalledWith('Permission denied')
      })
    })

    it('should handle HTTP errors', async () => {
      const { useLibraryBatchTagUpdate } = await import('./useLibraryItems')

      const onError = vi.fn()

      const mockResponse = {
        ok: false,
        status: 500,
        json: vi.fn().mockResolvedValue({ detail: 'Internal server error' }),
      }

      vi.mocked(global.fetch).mockResolvedValue(mockResponse as unknown as Response)

      const { result } = renderHook(
        () => useLibraryBatchTagUpdate({ onError, useSSE: true }),
        { wrapper }
      )

      await act(async () => {
        result.current.execute('test-library', [1, 2], mockRules)
      })

      await waitFor(() => {
        expect(result.current.state.error).toBe('Internal server error')
      })
    })

    it('should use non-SSE mode when useSSE is false', async () => {
      const { useLibraryBatchTagUpdate } = await import('./useLibraryItems')

      vi.mocked(libraryItemsApi.batchUpdateLibraryItems).mockResolvedValue(mockBatchUpdateResponse)

      const onCompleted = vi.fn()

      const { result } = renderHook(
        () => useLibraryBatchTagUpdate({ onCompleted, useSSE: false }),
        { wrapper }
      )

      await act(async () => {
        result.current.execute('test-library', [1, 2], mockRules)
      })

      await waitFor(() => {
        expect(result.current.state.isComplete).toBe(true)
      })

      expect(libraryItemsApi.batchUpdateLibraryItems).toHaveBeenCalledWith(
        'test-library',
        [1, 2],
        mockRules
      )
    })
  })
})
