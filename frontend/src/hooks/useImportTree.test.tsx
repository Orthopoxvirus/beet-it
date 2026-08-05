import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useImportTree, importTreeKeys } from './useImportTree'
import * as importTreeApi from '@/api/import-tree'
import type { ImportTreeResponse } from '@/types/import-tree'
import type { ReactNode } from 'react'

// Mock the API module
vi.mock('@/api/import-tree', () => ({
  fetchImportTree: vi.fn(),
}))

describe('useImportTree', () => {
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

  const mockTreeResponse: ImportTreeResponse = {
    importPath: '/data/import/jazz',
    children: [
      {
        name: 'Miles Davis',
        path: 'Miles Davis',
        isAlbum: false,
        isMultiDiscParent: false,
        children: [
          {
            name: 'Kind of Blue',
            path: 'Miles Davis/Kind of Blue',
            isAlbum: true,
            isMultiDiscParent: false,
            children: [],
            hasSubfolders: false,
          },
        ],
        hasSubfolders: true,
      },
    ],
  }

  describe('Query keys', () => {
    it('should have correct query key structure', () => {
      expect(importTreeKeys.all).toEqual(['import-tree'])
      expect(importTreeKeys.byLibrary('my-library')).toEqual(['import-tree', 'my-library'])
    })
  })

  describe('useImportTree hook', () => {
    it('should fetch import tree data successfully', async () => {
      vi.mocked(importTreeApi.fetchImportTree).mockResolvedValue(mockTreeResponse)

      const { result } = renderHook(() => useImportTree('jazz'), { wrapper })

      // Initially loading
      expect(result.current.isLoading).toBe(true)

      // Wait for data
      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data).toEqual(mockTreeResponse)
      expect(importTreeApi.fetchImportTree).toHaveBeenCalledWith('jazz')
    })

    it('should not fetch when slug is empty', async () => {
      const { result } = renderHook(() => useImportTree(''), { wrapper })

      // Should not be loading because query is disabled
      expect(result.current.isLoading).toBe(false)
      expect(result.current.data).toBeUndefined()
      expect(importTreeApi.fetchImportTree).not.toHaveBeenCalled()
    })

    it('should handle API errors', async () => {
      const error = new Error('Library not found')
      vi.mocked(importTreeApi.fetchImportTree).mockRejectedValue(error)

      const { result } = renderHook(() => useImportTree('nonexistent'), { wrapper })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error).toEqual(error)
    })

    it('should use correct query key for caching', async () => {
      vi.mocked(importTreeApi.fetchImportTree).mockResolvedValue(mockTreeResponse)

      renderHook(() => useImportTree('jazz'), { wrapper })

      await waitFor(() => {
        expect(queryClient.getQueryData(importTreeKeys.byLibrary('jazz'))).toBeDefined()
      })
    })

    it('should refetch when slug changes', async () => {
      const mockTreeResponse2: ImportTreeResponse = {
        importPath: '/data/import/rock',
        children: [],
      }

      vi.mocked(importTreeApi.fetchImportTree)
        .mockResolvedValueOnce(mockTreeResponse)
        .mockResolvedValueOnce(mockTreeResponse2)

      const { result, rerender } = renderHook(
        ({ slug }) => useImportTree(slug),
        {
          wrapper,
          initialProps: { slug: 'jazz' },
        }
      )

      await waitFor(() => {
        expect(result.current.data?.importPath).toBe('/data/import/jazz')
      })

      // Change slug
      rerender({ slug: 'rock' })

      await waitFor(() => {
        expect(result.current.data?.importPath).toBe('/data/import/rock')
      })

      expect(importTreeApi.fetchImportTree).toHaveBeenCalledTimes(2)
      expect(importTreeApi.fetchImportTree).toHaveBeenCalledWith('jazz')
      expect(importTreeApi.fetchImportTree).toHaveBeenCalledWith('rock')
    })

    it('should return empty tree when import path is not configured', async () => {
      const emptyResponse: ImportTreeResponse = {
        importPath: null,
        children: [],
      }
      vi.mocked(importTreeApi.fetchImportTree).mockResolvedValue(emptyResponse)

      const { result } = renderHook(() => useImportTree('empty-library'), { wrapper })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.importPath).toBeNull()
      expect(result.current.data?.children).toEqual([])
    })
  })
})
