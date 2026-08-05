import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useImportFolderItems } from './useImportFolderItems'
import * as scanApi from '@/api/scan'
import type { ImportItemListResponse } from '@/types/scan'
import type { ReactNode } from 'react'

// Mock the API module
vi.mock('@/api/scan', () => ({
  fetchImportItems: vi.fn(),
}))

describe('useImportFolderItems', () => {
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

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const mockResponse: ImportItemListResponse = {
    items: [
      {
        id: 1,
        itemType: 'file',
        path: 'Artist/Album/track1.flac',
        directory: 'Artist/Album',
        filename: 'track1.flac',
        album: 'Test Album',
        albumArtist: 'Test Artist',
        artist: 'Test Artist',
        title: 'Track 1',
        trackNumber: 1,
        genre: 'Rock',
        status: 'new',
        firstSeenAt: '2024-01-01T00:00:00Z',
        lastSeenAt: '2024-01-01T00:00:00Z',
      },
      {
        id: 2,
        itemType: 'file',
        path: 'Artist/Album/track2.flac',
        directory: 'Artist/Album',
        filename: 'track2.flac',
        album: 'Test Album',
        albumArtist: 'Test Artist',
        artist: 'Test Artist',
        title: 'Track 2',
        trackNumber: 2,
        genre: 'Rock',
        status: 'new',
        firstSeenAt: '2024-01-01T00:00:00Z',
        lastSeenAt: '2024-01-01T00:00:00Z',
      },
    ],
    total: 2,
    skip: 0,
    limit: 500,
    scanId: 1,
    scanCompletedAt: '2024-01-01T12:00:00Z',
  }

  describe('Query behavior', () => {
    it('should fetch import items successfully', async () => {
      vi.mocked(scanApi.fetchImportItems).mockResolvedValue(mockResponse)

      const { result } = renderHook(
        () => useImportFolderItems('my-library', '/Artist/Album'),
        { wrapper }
      )

      // Initially loading
      expect(result.current.isLoading).toBe(true)

      // Wait for data
      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data).toEqual(mockResponse)
      expect(result.current.data?.items).toHaveLength(2)
    })

    it('should pass pathPrefix parameter to API', async () => {
      vi.mocked(scanApi.fetchImportItems).mockResolvedValue(mockResponse)

      renderHook(() => useImportFolderItems('jazz', '/Artist/Album'), {
        wrapper,
      })

      await waitFor(() => {
        expect(scanApi.fetchImportItems).toHaveBeenCalled()
      })

      expect(scanApi.fetchImportItems).toHaveBeenCalledWith('jazz', {
        pathPrefix: '/Artist/Album',
        itemType: 'file',
        limit: 500,
      })
    })

    it('should filter for file item type only', async () => {
      vi.mocked(scanApi.fetchImportItems).mockResolvedValue(mockResponse)

      renderHook(() => useImportFolderItems('library', '/path'), {
        wrapper,
      })

      await waitFor(() => {
        expect(scanApi.fetchImportItems).toHaveBeenCalled()
      })

      expect(scanApi.fetchImportItems).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          itemType: 'file',
        })
      )
    })

    it('should use default limit of 500', async () => {
      vi.mocked(scanApi.fetchImportItems).mockResolvedValue(mockResponse)

      renderHook(() => useImportFolderItems('library', '/path'), {
        wrapper,
      })

      await waitFor(() => {
        expect(scanApi.fetchImportItems).toHaveBeenCalled()
      })

      expect(scanApi.fetchImportItems).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          limit: 500,
        })
      )
    })

    it('should allow custom limit through options', async () => {
      vi.mocked(scanApi.fetchImportItems).mockResolvedValue(mockResponse)

      renderHook(
        () =>
          useImportFolderItems('library', '/path', {
            limit: 100,
          }),
        { wrapper }
      )

      await waitFor(() => {
        expect(scanApi.fetchImportItems).toHaveBeenCalled()
      })

      expect(scanApi.fetchImportItems).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          limit: 100,
        })
      )
    })
  })

  describe('Query enabling', () => {
    it('should not fetch when slug is empty', async () => {
      const { result } = renderHook(
        () => useImportFolderItems('', '/Artist/Album'),
        { wrapper }
      )

      // Should not be loading because query is disabled
      expect(result.current.isLoading).toBe(false)
      expect(result.current.data).toBeUndefined()
      expect(scanApi.fetchImportItems).not.toHaveBeenCalled()
    })

    it('should not fetch when slug is undefined', async () => {
      const { result } = renderHook(
        () => useImportFolderItems(undefined, '/Artist/Album'),
        { wrapper }
      )

      expect(result.current.isLoading).toBe(false)
      expect(result.current.data).toBeUndefined()
      expect(scanApi.fetchImportItems).not.toHaveBeenCalled()
    })

    it('should not fetch when path is null', async () => {
      const { result } = renderHook(
        () => useImportFolderItems('library', null),
        { wrapper }
      )

      expect(result.current.isLoading).toBe(false)
      expect(result.current.data).toBeUndefined()
      expect(scanApi.fetchImportItems).not.toHaveBeenCalled()
    })

    it('should not fetch when path is undefined', async () => {
      const { result } = renderHook(
        () => useImportFolderItems('library', undefined),
        { wrapper }
      )

      expect(result.current.isLoading).toBe(false)
      expect(result.current.data).toBeUndefined()
      expect(scanApi.fetchImportItems).not.toHaveBeenCalled()
    })

    it('should respect enabled option set to false', async () => {
      const { result } = renderHook(
        () =>
          useImportFolderItems('library', '/path', {
            enabled: false,
          }),
        { wrapper }
      )

      expect(result.current.isLoading).toBe(false)
      expect(result.current.data).toBeUndefined()
      expect(scanApi.fetchImportItems).not.toHaveBeenCalled()
    })

    it('should fetch when enabled option is true', async () => {
      vi.mocked(scanApi.fetchImportItems).mockResolvedValue(mockResponse)

      const { result } = renderHook(
        () =>
          useImportFolderItems('library', '/path', {
            enabled: true,
          }),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(scanApi.fetchImportItems).toHaveBeenCalled()
    })
  })

  describe('Error handling', () => {
    it('should handle API errors', async () => {
      const error = new Error('Network error')
      vi.mocked(scanApi.fetchImportItems).mockRejectedValue(error)

      const { result } = renderHook(
        () => useImportFolderItems('library', '/path'),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error).toEqual(error)
    })
  })

  describe('Query key and caching', () => {
    it('should use correct query key for caching', async () => {
      vi.mocked(scanApi.fetchImportItems).mockResolvedValue(mockResponse)

      renderHook(() => useImportFolderItems('jazz', '/Artist/Album'), {
        wrapper,
      })

      await waitFor(() => {
        const queryData = queryClient.getQueryData([
          'scans',
          'importItems',
          'jazz',
          {
            pathPrefix: '/Artist/Album',
            itemType: 'file',
            limit: 500,
          },
        ])
        expect(queryData).toBeDefined()
      })
    })

    it('should refetch when path changes', async () => {
      const mockResponse2: ImportItemListResponse = {
        ...mockResponse,
        items: [mockResponse.items[0]],
        total: 1,
      }

      vi.mocked(scanApi.fetchImportItems)
        .mockResolvedValueOnce(mockResponse)
        .mockResolvedValueOnce(mockResponse2)

      const { result, rerender } = renderHook(
        ({ path }) => useImportFolderItems('library', path),
        {
          wrapper,
          initialProps: { path: '/path1' as string | null },
        }
      )

      await waitFor(() => {
        expect(result.current.data?.total).toBe(2)
      })

      // Change path
      rerender({ path: '/path2' })

      await waitFor(() => {
        expect(result.current.data?.total).toBe(1)
      })

      expect(scanApi.fetchImportItems).toHaveBeenCalledTimes(2)
    })

    it('should refetch when slug changes', async () => {
      const mockResponse2: ImportItemListResponse = {
        ...mockResponse,
        items: [],
        total: 0,
      }

      vi.mocked(scanApi.fetchImportItems)
        .mockResolvedValueOnce(mockResponse)
        .mockResolvedValueOnce(mockResponse2)

      const { result, rerender } = renderHook(
        ({ slug }) => useImportFolderItems(slug, '/path'),
        {
          wrapper,
          initialProps: { slug: 'library1' },
        }
      )

      await waitFor(() => {
        expect(result.current.data?.total).toBe(2)
      })

      // Change slug
      rerender({ slug: 'library2' })

      await waitFor(() => {
        expect(result.current.data?.total).toBe(0)
      })

      expect(scanApi.fetchImportItems).toHaveBeenCalledTimes(2)
      expect(scanApi.fetchImportItems).toHaveBeenCalledWith('library1', expect.any(Object))
      expect(scanApi.fetchImportItems).toHaveBeenCalledWith('library2', expect.any(Object))
    })
  })

  describe('Response data', () => {
    it('should return scanId when available', async () => {
      vi.mocked(scanApi.fetchImportItems).mockResolvedValue(mockResponse)

      const { result } = renderHook(
        () => useImportFolderItems('library', '/path'),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.scanId).toBe(1)
    })

    it('should return null scanId when folder not scanned', async () => {
      const unscannedResponse: ImportItemListResponse = {
        ...mockResponse,
        items: [],
        total: 0,
        scanId: null,
        scanCompletedAt: null,
      }
      vi.mocked(scanApi.fetchImportItems).mockResolvedValue(unscannedResponse)

      const { result } = renderHook(
        () => useImportFolderItems('library', '/path'),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.scanId).toBeNull()
    })
  })
})
