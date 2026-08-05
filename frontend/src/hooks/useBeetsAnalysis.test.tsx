import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  useAnalyzeAlbum,
  useBeetsAnalysisCache,
  useAnalysisQueue,
  useAnalyzeFolder,
  useAutoAnalyzeSetting,
  useSetAutoAnalyzeSetting,
  beetsAnalysisKeys,
} from './useBeetsAnalysis'
import * as beetsImportApi from '@/api/beets-import'
import type {
  AnalyzeAlbumResponse,
  AnalyzeQueueResponse,
  AnalyzeFolderResponse,
  AutoAnalyzeSettingResponse,
} from '@/types/beets-import'
import type { ReactNode } from 'react'

// Mock the API module
vi.mock('@/api/beets-import', () => ({
  analyzeAlbum: vi.fn(),
  getCacheStatus: vi.fn(),
  addManualCandidate: vi.fn(),
  getAnalyzeQueue: vi.fn(),
  analyzeFolder: vi.fn(),
  getAutoAnalyzeSetting: vi.fn(),
  setAutoAnalyzeSetting: vi.fn(),
}))

describe('useBeetsAnalysis', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
        mutations: {
          retry: false,
        },
      },
    })
    vi.clearAllMocks()
  })

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const mockAnalysisResponse: AnalyzeAlbumResponse = {
    album_path: '/import/test-album',
    local_album: {
      path: '/import/test-album',
      artist: 'Test Artist',
      album: 'Test Album',
      tracks: [
        {
          path: '/import/test-album/01-track.flac',
          title: 'Track 1',
          track_num: 1,
          length: 180,
        },
      ],
    },
    candidates: [
      {
        source: 'MusicBrainz',
        source_id: 'mb-123',
        similarity: 0.95,
        artist: 'Test Artist',
        album: 'Test Album',
        year: 2023,
        label: 'Test Label',
        country: 'US',
        media: 'CD',
        tracks: [],
        changes: [],
        track_changes: [],
      },
    ],
    analyzed_at: '2024-01-15T10:30:00Z',
  }

  describe('Query keys', () => {
    it('should have correct base query key', () => {
      expect(beetsAnalysisKeys.all).toEqual(['beets-analysis'])
    })

    it('should generate correct library-scoped key', () => {
      expect(beetsAnalysisKeys.byLibrary('my-library')).toEqual([
        'beets-analysis',
        'my-library',
      ])
    })

    it('should generate correct album-scoped key', () => {
      expect(beetsAnalysisKeys.byAlbum('my-library', '/import/album')).toEqual([
        'beets-analysis',
        'my-library',
        '/import/album',
      ])
    })

    it('should generate correct analysis-queue key', () => {
      expect(beetsAnalysisKeys.analysisQueue('my-library')).toEqual([
        'beets-analysis',
        'my-library',
        'analysis-queue',
      ])
    })

    it('should generate correct auto-analyze-setting key', () => {
      expect(beetsAnalysisKeys.autoAnalyzeSetting('my-library')).toEqual([
        'beets-analysis',
        'my-library',
        'auto-analyze-setting',
      ])
    })
  })

  describe('useAnalyzeAlbum', () => {
    it('should call API with correct parameters', async () => {
      vi.mocked(beetsImportApi.analyzeAlbum).mockResolvedValue(mockAnalysisResponse)

      const { result } = renderHook(() => useAnalyzeAlbum('my-library'), {
        wrapper,
      })

      await act(async () => {
        await result.current.mutateAsync({ albumPath: '/import/test-album' })
      })

      expect(beetsImportApi.analyzeAlbum).toHaveBeenCalledWith(
        'my-library',
        '/import/test-album',
        false
      )
    })

    it('should return analysis data on success', async () => {
      vi.mocked(beetsImportApi.analyzeAlbum).mockResolvedValue(mockAnalysisResponse)

      const { result } = renderHook(() => useAnalyzeAlbum('my-library'), {
        wrapper,
      })

      let data: AnalyzeAlbumResponse | undefined

      await act(async () => {
        data = await result.current.mutateAsync({ albumPath: '/import/test-album' })
      })

      expect(data).toEqual(mockAnalysisResponse)
    })

    it('should cache result on success', async () => {
      vi.mocked(beetsImportApi.analyzeAlbum).mockResolvedValue(mockAnalysisResponse)

      const { result } = renderHook(() => useAnalyzeAlbum('my-library'), {
        wrapper,
      })

      await act(async () => {
        await result.current.mutateAsync({ albumPath: '/import/test-album' })
      })

      // Check that data is cached
      const cachedData = queryClient.getQueryData<AnalyzeAlbumResponse>(
        beetsAnalysisKeys.byAlbum('my-library', '/import/test-album')
      )

      expect(cachedData).toEqual(mockAnalysisResponse)
    })

    it('should handle API errors', async () => {
      const error = new Error('Analysis failed')
      vi.mocked(beetsImportApi.analyzeAlbum).mockRejectedValue(error)

      const { result } = renderHook(() => useAnalyzeAlbum('my-library'), {
        wrapper,
      })

      await expect(
        act(async () => {
          await result.current.mutateAsync({ albumPath: '/import/test-album' })
        })
      ).rejects.toThrow('Analysis failed')
    })

    it('should track loading state during mutation', async () => {
      vi.mocked(beetsImportApi.analyzeAlbum).mockImplementation(
        () =>
          new Promise((resolve) => setTimeout(() => resolve(mockAnalysisResponse), 100))
      )

      const { result } = renderHook(() => useAnalyzeAlbum('my-library'), {
        wrapper,
      })

      // Initially not loading
      expect(result.current.isPending).toBe(false)

      // Start mutation
      act(() => {
        result.current.mutate({ albumPath: '/import/test-album' })
      })

      // Should be loading
      await waitFor(() => {
        expect(result.current.isPending).toBe(true)
      })

      // Wait for completion
      await waitFor(() => {
        expect(result.current.isPending).toBe(false)
      })
    })
  })

  describe('useBeetsAnalysisCache', () => {
    beforeEach(async () => {
      // Pre-populate cache with test data
      queryClient.setQueryData(
        beetsAnalysisKeys.byAlbum('my-library', '/import/test-album'),
        mockAnalysisResponse
      )
    })

    describe('getCached', () => {
      it('should return cached data if available', () => {
        const { result } = renderHook(() => useBeetsAnalysisCache('my-library'), {
          wrapper,
        })

        const cached = result.current.getCached('/import/test-album')
        expect(cached).toEqual(mockAnalysisResponse)
      })

      it('should return undefined if no cached data', () => {
        const { result } = renderHook(() => useBeetsAnalysisCache('my-library'), {
          wrapper,
        })

        const cached = result.current.getCached('/import/nonexistent')
        expect(cached).toBeUndefined()
      })
    })

    describe('hasCached', () => {
      it('should return true if data is cached', () => {
        const { result } = renderHook(() => useBeetsAnalysisCache('my-library'), {
          wrapper,
        })

        expect(result.current.hasCached('/import/test-album')).toBe(true)
      })

      it('should return false if data is not cached', () => {
        const { result } = renderHook(() => useBeetsAnalysisCache('my-library'), {
          wrapper,
        })

        expect(result.current.hasCached('/import/nonexistent')).toBe(false)
      })
    })

    describe('invalidate', () => {
      it('should remove cached data for specific album', () => {
        const { result } = renderHook(() => useBeetsAnalysisCache('my-library'), {
          wrapper,
        })

        // Verify data exists
        expect(result.current.hasCached('/import/test-album')).toBe(true)

        // Invalidate
        act(() => {
          result.current.invalidate('/import/test-album')
        })

        // Verify data is removed
        expect(result.current.hasCached('/import/test-album')).toBe(false)
      })
    })

    describe('invalidateAll', () => {
      it('should remove all cached data for library', () => {
        // Add more cached data
        queryClient.setQueryData(
          beetsAnalysisKeys.byAlbum('my-library', '/import/album-2'),
          { ...mockAnalysisResponse, album_path: '/import/album-2' }
        )

        const { result } = renderHook(() => useBeetsAnalysisCache('my-library'), {
          wrapper,
        })

        // Verify data exists
        expect(result.current.hasCached('/import/test-album')).toBe(true)
        expect(result.current.hasCached('/import/album-2')).toBe(true)

        // Invalidate all
        act(() => {
          result.current.invalidateAll()
        })

        // Verify all data is removed
        expect(result.current.hasCached('/import/test-album')).toBe(false)
        expect(result.current.hasCached('/import/album-2')).toBe(false)
      })
    })
  })

  describe('useAnalysisQueue', () => {
    const mockQueueResponse: AnalyzeQueueResponse = {
      queueDepth: 3,
      activeCount: 2,
      maxConcurrent: 2,
      queuedItems: [
        { albumPath: '/import/album-1', position: 1, queuedAt: '2026-02-28T10:30:00Z' },
        { albumPath: '/import/album-2', position: 2, queuedAt: '2026-02-28T10:30:05Z' },
        { albumPath: '/import/album-3', position: 3, queuedAt: '2026-02-28T10:30:10Z' },
      ],
      activeItems: [
        { albumPath: '/import/album-4', jobId: 'job-1', startedAt: '2026-02-28T10:29:55Z' },
        { albumPath: '/import/album-5', jobId: 'job-2', startedAt: '2026-02-28T10:29:58Z' },
      ],
    }

    it('should fetch queue status', async () => {
      vi.mocked(beetsImportApi.getAnalyzeQueue).mockResolvedValue(mockQueueResponse)

      const { result } = renderHook(() => useAnalysisQueue('my-library'), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data).toEqual(mockQueueResponse)
      expect(beetsImportApi.getAnalyzeQueue).toHaveBeenCalledWith('my-library')
    })

    it('should return queue depth and counts', async () => {
      vi.mocked(beetsImportApi.getAnalyzeQueue).mockResolvedValue(mockQueueResponse)

      const { result } = renderHook(() => useAnalysisQueue('my-library'), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.queueDepth).toBe(3)
      expect(result.current.data?.activeCount).toBe(2)
      expect(result.current.data?.maxConcurrent).toBe(2)
    })

    it('should return queued and active items', async () => {
      vi.mocked(beetsImportApi.getAnalyzeQueue).mockResolvedValue(mockQueueResponse)

      const { result } = renderHook(() => useAnalysisQueue('my-library'), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.queuedItems).toHaveLength(3)
      expect(result.current.data?.activeItems).toHaveLength(2)
    })

    it('should handle errors', async () => {
      const error = new Error('Failed to fetch queue')
      vi.mocked(beetsImportApi.getAnalyzeQueue).mockRejectedValue(error)

      const { result } = renderHook(() => useAnalysisQueue('my-library', { refetchInterval: false }), {
        wrapper,
      })

      await waitFor(
        () => {
          expect(result.current.isError).toBe(true)
        },
        { timeout: 5000 }
      )

      expect(result.current.error?.message).toBe('Failed to fetch queue')
    })
  })

  describe('useAnalyzeFolder', () => {
    const mockFolderResponse: AnalyzeFolderResponse = {
      enqueued: 15,
      dispatched: 2,
      alreadyCached: 8,
      alreadyQueued: 3,
      total: 28,
      message: 'Enqueued 15 albums for analysis',
    }

    it('should call API with correct parameters', async () => {
      vi.mocked(beetsImportApi.analyzeFolder).mockResolvedValue(mockFolderResponse)

      const { result } = renderHook(() => useAnalyzeFolder('my-library'), {
        wrapper,
      })

      await act(async () => {
        await result.current.mutateAsync({ force: false })
      })

      expect(beetsImportApi.analyzeFolder).toHaveBeenCalledWith('my-library', false)
    })

    it('should return folder analysis summary', async () => {
      vi.mocked(beetsImportApi.analyzeFolder).mockResolvedValue(mockFolderResponse)

      const { result } = renderHook(() => useAnalyzeFolder('my-library'), {
        wrapper,
      })

      let data: AnalyzeFolderResponse | undefined

      await act(async () => {
        data = await result.current.mutateAsync({ force: false })
      })

      expect(data?.enqueued).toBe(15)
      expect(data?.dispatched).toBe(2)
      expect(data?.alreadyCached).toBe(8)
      expect(data?.message).toBe('Enqueued 15 albums for analysis')
    })

    it('should support force flag', async () => {
      vi.mocked(beetsImportApi.analyzeFolder).mockResolvedValue(mockFolderResponse)

      const { result } = renderHook(() => useAnalyzeFolder('my-library'), {
        wrapper,
      })

      await act(async () => {
        await result.current.mutateAsync({ force: true })
      })

      expect(beetsImportApi.analyzeFolder).toHaveBeenCalledWith('my-library', true)
    })

    it('should handle errors', async () => {
      const error = new Error('Analysis failed')
      vi.mocked(beetsImportApi.analyzeFolder).mockRejectedValue(error)

      const { result } = renderHook(() => useAnalyzeFolder('my-library'), {
        wrapper,
      })

      await expect(
        act(async () => {
          await result.current.mutateAsync({ force: false })
        })
      ).rejects.toThrow('Analysis failed')
    })
  })

  describe('useAutoAnalyzeSetting', () => {
    const mockSettingResponse: AutoAnalyzeSettingResponse = {
      autoAnalyzeAfterScan: true,
    }

    it('should fetch auto-analyze setting', async () => {
      vi.mocked(beetsImportApi.getAutoAnalyzeSetting).mockResolvedValue(mockSettingResponse)

      const { result } = renderHook(() => useAutoAnalyzeSetting('my-library'), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.autoAnalyzeAfterScan).toBe(true)
      expect(beetsImportApi.getAutoAnalyzeSetting).toHaveBeenCalledWith('my-library')
    })

    it('should return false by default when disabled', async () => {
      vi.mocked(beetsImportApi.getAutoAnalyzeSetting).mockResolvedValue({
        autoAnalyzeAfterScan: false,
      })

      const { result } = renderHook(() => useAutoAnalyzeSetting('my-library'), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.autoAnalyzeAfterScan).toBe(false)
    })
  })

  describe('useSetAutoAnalyzeSetting', () => {
    it('should update auto-analyze setting', async () => {
      const mockResponse: AutoAnalyzeSettingResponse = {
        autoAnalyzeAfterScan: true,
        message: 'Auto-analyze after scan enabled',
      }
      vi.mocked(beetsImportApi.setAutoAnalyzeSetting).mockResolvedValue(mockResponse)

      const { result } = renderHook(() => useSetAutoAnalyzeSetting('my-library'), {
        wrapper,
      })

      await act(async () => {
        await result.current.mutateAsync(true)
      })

      expect(beetsImportApi.setAutoAnalyzeSetting).toHaveBeenCalledWith('my-library', true)
    })

    it('should update cached setting on success', async () => {
      const mockResponse: AutoAnalyzeSettingResponse = {
        autoAnalyzeAfterScan: true,
        message: 'Auto-analyze after scan enabled',
      }
      vi.mocked(beetsImportApi.setAutoAnalyzeSetting).mockResolvedValue(mockResponse)

      const { result } = renderHook(() => useSetAutoAnalyzeSetting('my-library'), {
        wrapper,
      })

      await act(async () => {
        await result.current.mutateAsync(true)
      })

      // Check that the setting is cached
      const cachedData = queryClient.getQueryData<AutoAnalyzeSettingResponse>(
        beetsAnalysisKeys.autoAnalyzeSetting('my-library')
      )
      expect(cachedData?.autoAnalyzeAfterScan).toBe(true)
    })

    it('should handle disable', async () => {
      const mockResponse: AutoAnalyzeSettingResponse = {
        autoAnalyzeAfterScan: false,
        message: 'Auto-analyze after scan disabled',
      }
      vi.mocked(beetsImportApi.setAutoAnalyzeSetting).mockResolvedValue(mockResponse)

      const { result } = renderHook(() => useSetAutoAnalyzeSetting('my-library'), {
        wrapper,
      })

      await act(async () => {
        await result.current.mutateAsync(false)
      })

      expect(beetsImportApi.setAutoAnalyzeSetting).toHaveBeenCalledWith('my-library', false)
    })
  })
})
