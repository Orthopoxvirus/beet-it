/**
 * Integration tests for the BeetsImportPanel component.
 *
 * Tests the integration between AlbumListCard, CandidateDetailsCard,
 * and the analysis workflow with mocked API calls and hooks.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import BeetsImportPanel from '../BeetsImportPanel'
import type { ImportTreeResponse, ImportFolderNode } from '@/types/import-tree'
import type { AnalyzeAlbumResponse, AnalyzeFolderResponse, AnalyzeQueueResponse } from '@/types/beets-import'
import type { ReactNode } from 'react'

// ============================================================================
// Mocks
// ============================================================================

// Mock the hooks
vi.mock('@/hooks/useImportTree', () => ({
  useImportTree: vi.fn(),
  useDeleteImportFolder: vi.fn(() => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn().mockResolvedValue({ status: 'deleted' }),
    isPending: false,
  })),
}))

vi.mock('@/hooks/useBeetsAnalysis', () => ({
  useAnalyzeAlbum: vi.fn(),
  useBeetsAnalysisCache: vi.fn(),
  useCacheStatus: vi.fn(),
  useAddManualCandidate: vi.fn(),
  useAnalysisQueue: vi.fn(),
  useAnalyzeFolder: vi.fn(),
  beetsAnalysisKeys: {
    all: ['beets-analysis'],
    byLibrary: (slug: string) => ['beets-analysis', slug],
    byAlbum: (slug: string, path: string) => ['beets-analysis', slug, path],
    cacheStatus: (slug: string) => ['beets-analysis', slug, 'cache-status'],
    analysisQueue: (slug: string) => ['beets-analysis', slug, 'analysis-queue'],
  },
}))

// Keep the real API module (notably BeetsImportApiError) but stub startImport so
// tests can drive the 409 ALBUM_ALREADY_EXISTS duplicate-album flow.
vi.mock('@/api/beets-import', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/beets-import')>()
  return { ...actual, startImport: vi.fn() }
})

// ============================================================================
// Test Data
// ============================================================================

const createMockAlbumNode = (
  overrides: Partial<ImportFolderNode> = {}
): ImportFolderNode => ({
  name: 'Test Album',
  path: '/import/Test Album',
  isAlbum: true,
  isMultiDiscParent: false,
  children: [],
  hasSubfolders: false,
  ...overrides,
})

// node.path is RELATIVE to importPath; absolute paths are built by BeetsImportPanel
// as `${importBasePath}/${node.path}`, so this yields the expected absolute
// paths "/import/Album 1", "/import/Album 2", "/import/Album 3".
const mockImportTree: ImportTreeResponse = {
  importPath: '/import',
  children: [
    createMockAlbumNode({
      name: 'Album 1',
      path: 'Album 1',
    }),
    createMockAlbumNode({
      name: 'Album 2',
      path: 'Album 2',
    }),
    createMockAlbumNode({
      name: 'Album 3',
      path: 'Album 3',
    }),
  ],
}

const mockAnalysisResponse: AnalyzeAlbumResponse = {
  albumPath: '/import/Album 1',
  localAlbum: {
    path: '/import/Album 1',
    artist: 'Test Artist',
    album: 'Album 1',
    tracks: [
      { path: '/import/Album 1/01.flac', title: 'Track 1', trackNum: 1, length: 180 },
      { path: '/import/Album 1/02.flac', title: 'Track 2', trackNum: 2, length: 200 },
    ],
  },
  candidates: [
    {
      source: 'MusicBrainz',
      sourceId: 'mb-123',
      similarity: 0.95,
      artist: 'Test Artist',
      album: 'Album 1',
      year: 2023,
      label: 'Test Label',
      country: 'US',
      media: 'CD',
      tracks: [],
      changes: [],
      trackChanges: [],
    },
  ],
  analyzedAt: '2024-01-15T10:30:00Z',
}

// ============================================================================
// Test Setup
// ============================================================================

describe('BeetsImportPanel', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const setupDefaultMocks = async () => {
    const { useImportTree } = await import('@/hooks/useImportTree')
    vi.mocked(useImportTree).mockReturnValue({
      data: mockImportTree,
      isLoading: false,
      error: null,
      isSuccess: true,
      isError: false,
    } as any)

    const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate } = await import(
      '@/hooks/useBeetsAnalysis'
    )

    const mockMutateAsync = vi.fn().mockResolvedValue(mockAnalysisResponse)
    vi.mocked(useAnalyzeAlbum).mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: mockMutateAsync,
      isPending: false,
      isSuccess: false,
      isError: false,
      error: null,
      data: undefined,
      reset: vi.fn(),
    } as any)

    vi.mocked(useBeetsAnalysisCache).mockReturnValue({
      getCached: vi.fn().mockReturnValue(undefined),
      hasCached: vi.fn().mockReturnValue(false),
      invalidate: vi.fn(),
      invalidateAll: vi.fn(),
    })

    vi.mocked(useCacheStatus).mockReturnValue({
      data: { cacheStatus: {} },
      isLoading: false,
      error: null,
      isSuccess: true,
      isError: false,
    } as any)

    vi.mocked(useAddManualCandidate).mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
      isSuccess: false,
      isError: false,
      error: null,
      data: undefined,
      reset: vi.fn(),
    } as any)

    const { useAnalysisQueue, useAnalyzeFolder } = await import('@/hooks/useBeetsAnalysis')

    vi.mocked(useAnalysisQueue).mockReturnValue({
      data: { queueDepth: 0, activeCount: 0, maxConcurrent: 2, queuedItems: [], activeItems: [] },
      isLoading: false,
      isSuccess: true,
      isError: false,
      error: null,
    } as any)

    vi.mocked(useAnalyzeFolder).mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
      isSuccess: false,
      isError: false,
      error: null,
    } as any)
  }

  const renderPanel = () => {
    return render(<BeetsImportPanel librarySlug="test-library" />, { wrapper })
  }

  // ============================================================================
  // Album List Integration
  // ============================================================================

  describe('Album List Integration', () => {
    it('should display albums from import tree', async () => {
      await setupDefaultMocks()

      renderPanel()

      await waitFor(() => {
        expect(screen.getByText('Album 1')).toBeInTheDocument()
        expect(screen.getByText('Album 2')).toBeInTheDocument()
        expect(screen.getByText('Album 3')).toBeInTheDocument()
      })
    })

    it('should show loading state while fetching albums', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
        isSuccess: false,
        isError: false,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate } = await import(
        '@/hooks/useBeetsAnalysis'
      )
      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)
      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)

      const { container } = renderPanel()

      // Should show loading skeleton
      const skeletons = container.querySelectorAll('.animate-pulse')
      expect(skeletons.length).toBeGreaterThan(0)
    })

    it('should show error state when album loading fails', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: new Error('Failed to load albums'),
        isSuccess: false,
        isError: true,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate } = await import(
        '@/hooks/useBeetsAnalysis'
      )
      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)
      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)

      renderPanel()

      expect(screen.getByText('Failed to load albums')).toBeInTheDocument()
    })

    it('should show empty state when no albums found', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: { importPath: '/import', children: [] },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate } = await import(
        '@/hooks/useBeetsAnalysis'
      )
      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)
      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)

      renderPanel()

      expect(
        screen.getByText('No album folders found in the import directory.')
      ).toBeInTheDocument()
    })
  })

  // ============================================================================
  // Album Selection Flow
  // ============================================================================

  describe('Album Selection Flow', () => {
    it('should update candidate details when album is selected', async () => {
      await setupDefaultMocks()

      const { useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate } = await import(
        '@/hooks/useBeetsAnalysis'
      )

      // Return cached data for Album 1
      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockImplementation((path) =>
          path === '/import/Album 1' ? mockAnalysisResponse : undefined
        ),
        hasCached: vi.fn().mockImplementation((path) => path === '/import/Album 1'),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: { '/import/Album 1': true } },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)

      renderPanel()

      // Click on Album 1
      const album1 = await screen.findByText('Album 1')
      fireEvent.click(album1)

      // Should show analysis data in details card
      await waitFor(() => {
        expect(screen.getByText('/import/Album 1')).toBeInTheDocument()
        expect(screen.getByText('MusicBrainz')).toBeInTheDocument()
        expect(screen.getByText('95.0%')).toBeInTheDocument()
      })
    })

    it('should highlight selected album', async () => {
      await setupDefaultMocks()

      renderPanel()

      // Click on Album 2
      const album2 = await screen.findByText('Album 2')
      fireEvent.click(album2)

      // Find all album rows
      const albumRows = screen.getAllByRole('button')
      const album2Row = albumRows.find((row) => row.textContent?.includes('Album 2'))

      expect(album2Row).toHaveAttribute('aria-selected', 'true')
    })

    it('should show empty details when album without cached data is selected', async () => {
      await setupDefaultMocks()

      renderPanel()

      // Click on Album 2 (no cached data)
      const album2 = await screen.findByText('Album 2')
      fireEvent.click(album2)

      // Should show empty state in details card
      await waitFor(() => {
        expect(screen.getByText('No Album Selected')).toBeInTheDocument()
      })
    })
  })

  // ============================================================================
  // Analysis Trigger Flow
  // ============================================================================

  describe('Analysis Trigger Flow', () => {
    it('should trigger analysis when disc icon is clicked', async () => {
      await setupDefaultMocks()

      const { useAnalyzeAlbum } = await import('@/hooks/useBeetsAnalysis')
      const mockMutateAsync = vi.fn().mockResolvedValue(mockAnalysisResponse)
      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as any)

      renderPanel()

      // Wait for albums to load
      await waitFor(() => {
        expect(screen.getByText('Album 1')).toBeInTheDocument()
      })

      // Click on the first analyze button
      const analyzeButtons = screen.getAllByRole('button', { name: 'Analyze album' })
      fireEvent.click(analyzeButtons[0])

      // Should call mutateAsync with the album path and force flag
      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({ albumPath: '/import/Album 1', force: false })
      })
    })

    it('folder analyze re-analyzes every album in the folder with force, even already-analyzed ones', async () => {
      const folderTree: ImportTreeResponse = {
        importPath: '/import',
        children: [
          createMockAlbumNode({ name: 'Album A', path: 'Artist One/Album A' }),
          createMockAlbumNode({ name: 'Album B', path: 'Artist One/Album B' }),
        ],
      }

      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: folderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const {
        useAnalyzeAlbum,
        useBeetsAnalysisCache,
        useCacheStatus,
        useAddManualCandidate,
        useAnalysisQueue,
        useAnalyzeFolder,
      } = await import('@/hooks/useBeetsAnalysis')

      const mockMutateAsync = vi.fn().mockResolvedValue(mockAnalysisResponse)
      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as any)

      const mockInvalidate = vi.fn()
      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: mockInvalidate,
        invalidateAll: vi.fn(),
      })

      // Both albums already analyzed on the backend — folder analyze must still
      // re-run them (force), not skip them as the previous behaviour did.
      vi.mocked(useCacheStatus).mockReturnValue({
        data: {
          cacheStatus: {
            '/import/Artist One/Album A': true,
            '/import/Artist One/Album B': true,
          },
        },
        isLoading: false,
      } as any)

      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        reset: vi.fn(),
      } as any)

      vi.mocked(useAnalysisQueue).mockReturnValue({
        data: { queueDepth: 0, activeCount: 0, maxConcurrent: 2, queuedItems: [], activeItems: [] },
        isLoading: false,
      } as any)

      vi.mocked(useAnalyzeFolder).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)

      renderPanel()

      await waitFor(() => {
        expect(screen.getByTestId('album-folder-analyze-button')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByTestId('album-folder-analyze-button'))

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledTimes(2)
      })
      expect(mockMutateAsync).toHaveBeenCalledWith({
        albumPath: '/import/Artist One/Album A',
        force: true,
      })
      expect(mockMutateAsync).toHaveBeenCalledWith({
        albumPath: '/import/Artist One/Album B',
        force: true,
      })
      // Stale cached results are dropped first, mirroring the per-album disc.
      expect(mockInvalidate).toHaveBeenCalledWith('/import/Artist One/Album A')
      expect(mockInvalidate).toHaveBeenCalledWith('/import/Artist One/Album B')
    })

    it('folder analyze skips albums already analyzing or queued', async () => {
      const folderTree: ImportTreeResponse = {
        importPath: '/import',
        children: [
          createMockAlbumNode({ name: 'Album A', path: 'Artist One/Album A' }),
          createMockAlbumNode({ name: 'Album B', path: 'Artist One/Album B' }),
        ],
      }

      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: folderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const {
        useAnalyzeAlbum,
        useBeetsAnalysisCache,
        useCacheStatus,
        useAddManualCandidate,
        useAnalysisQueue,
        useAnalyzeFolder,
      } = await import('@/hooks/useBeetsAnalysis')

      const mockMutateAsync = vi.fn().mockResolvedValue(mockAnalysisResponse)
      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as any)

      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })

      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)

      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        reset: vi.fn(),
      } as any)

      // Album A is actively analyzing, Album B is queued — both must be skipped.
      vi.mocked(useAnalysisQueue).mockReturnValue({
        data: {
          queueDepth: 1,
          activeCount: 1,
          maxConcurrent: 2,
          queuedItems: [{ albumPath: '/import/Artist One/Album B', position: 1 }],
          activeItems: [{ albumPath: '/import/Artist One/Album A' }],
        },
        isLoading: false,
      } as any)

      vi.mocked(useAnalyzeFolder).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)

      renderPanel()

      await waitFor(() => {
        expect(screen.getByTestId('album-folder-analyze-button')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByTestId('album-folder-analyze-button'))

      // Neither album is re-enqueued while in flight.
      await waitFor(() => {
        expect(screen.getByTestId('album-folder-analyze-button')).toBeInTheDocument()
      })
      expect(mockMutateAsync).not.toHaveBeenCalled()
    })

    it('shows an analyzing spinner on every folder album the instant folder analyze is clicked', async () => {
      const folderTree: ImportTreeResponse = {
        importPath: '/import',
        children: [
          createMockAlbumNode({ name: 'Album A', path: 'Artist One/Album A' }),
          createMockAlbumNode({ name: 'Album B', path: 'Artist One/Album B' }),
        ],
      }

      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: folderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const {
        useAnalyzeAlbum,
        useBeetsAnalysisCache,
        useCacheStatus,
        useAddManualCandidate,
        useAnalysisQueue,
        useAnalyzeFolder,
      } = await import('@/hooks/useBeetsAnalysis')

      // Never resolves: the spinner must come from optimistic state, not from
      // the mutation settling or the (idle) queue poll.
      const mockMutateAsync = vi.fn().mockImplementation(() => new Promise(() => {}))
      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as any)

      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })

      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)

      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        reset: vi.fn(),
      } as any)

      // Queue reports no activity — proving the spinner is optimistic, not poll-driven.
      vi.mocked(useAnalysisQueue).mockReturnValue({
        data: { queueDepth: 0, activeCount: 0, maxConcurrent: 2, queuedItems: [], activeItems: [] },
        isLoading: false,
      } as any)

      vi.mocked(useAnalyzeFolder).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)

      renderPanel()

      await waitFor(() => {
        expect(screen.getByTestId('album-folder-analyze-button')).toBeInTheDocument()
      })
      // No spinners before the click.
      expect(screen.queryAllByLabelText('Analyzing...')).toHaveLength(0)

      fireEvent.click(screen.getByTestId('album-folder-analyze-button'))

      // Both album rows light up immediately.
      await waitFor(() => {
        expect(screen.getAllByLabelText('Analyzing...')).toHaveLength(2)
      })
      expect(mockMutateAsync).toHaveBeenCalledTimes(2)
    })

    it('should show analysis results after analysis completes', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate } = await import(
        '@/hooks/useBeetsAnalysis'
      )

      const mockMutateAsync = vi.fn().mockResolvedValue(mockAnalysisResponse)
      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as any)

      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)

      renderPanel()

      // Wait for albums to load
      await waitFor(() => {
        expect(screen.getByText('Album 1')).toBeInTheDocument()
      })

      // Click on the first analyze button
      const analyzeButtons = screen.getAllByRole('button', { name: 'Analyze album' })

      await act(async () => {
        fireEvent.click(analyzeButtons[0])
        // Wait for mutation to complete
        await mockMutateAsync({ albumPath: '/import/Album 1', force: false })
      })

      // Should display analysis results
      await waitFor(() => {
        expect(screen.getByText('MusicBrainz')).toBeInTheDocument()
      })
    })

    it('should auto-select album when analysis is triggered', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate } = await import(
        '@/hooks/useBeetsAnalysis'
      )

      // Return a promise that doesn't resolve immediately
      let resolvePromise: (value: AnalyzeAlbumResponse) => void
      const mockMutateAsync = vi.fn().mockImplementation(
        () =>
          new Promise<AnalyzeAlbumResponse>((resolve) => {
            resolvePromise = resolve
          })
      )

      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as any)

      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)

      renderPanel()

      // Wait for albums to load
      await waitFor(() => {
        expect(screen.getByText('Album 1')).toBeInTheDocument()
      })

      // Click on the first analyze button
      const analyzeButtons = screen.getAllByRole('button', { name: 'Analyze album' })
      fireEvent.click(analyzeButtons[0])

      // Album 1 should now be selected (aria-selected=true)
      await waitFor(() => {
        const albumRows = screen.getAllByRole('button')
        const album1Row = albumRows.find((row) => row.textContent?.includes('Album 1'))
        expect(album1Row).toHaveAttribute('aria-selected', 'true')
      })

      // Resolve the promise to complete the test
      await act(async () => {
        resolvePromise!(mockAnalysisResponse)
      })
    })

    it('should show analysis error in details card', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate } = await import(
        '@/hooks/useBeetsAnalysis'
      )

      const mockMutateAsync = vi.fn().mockRejectedValue(new Error('Analysis failed'))
      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as any)

      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)

      renderPanel()

      // Wait for albums to load
      await waitFor(() => {
        expect(screen.getByText('Album 1')).toBeInTheDocument()
      })

      // Click on the first analyze button
      const analyzeButtons = screen.getAllByRole('button', { name: 'Analyze album' })

      await act(async () => {
        fireEvent.click(analyzeButtons[0])
        // Wait for error to propagate
        await new Promise((resolve) => setTimeout(resolve, 0))
      })

      // Should show error in details card
      await waitFor(() => {
        expect(screen.getByText('Analysis Failed')).toBeInTheDocument()
        expect(screen.getByText('Analysis failed')).toBeInTheDocument()
      })
    })
  })

  // ============================================================================
  // Re-analysis Flow
  // ============================================================================

  describe('Re-analysis Flow', () => {
    it('should invalidate cache and re-analyze when clicking disc on analyzed album', async () => {
      await setupDefaultMocks()

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus } = await import(
        '@/hooks/useBeetsAnalysis'
      )

      const mockMutateAsync = vi.fn().mockResolvedValue(mockAnalysisResponse)
      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as any)

      const mockInvalidate = vi.fn()
      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockImplementation((path) =>
          path === '/import/Album 1' ? mockAnalysisResponse : undefined
        ),
        hasCached: vi.fn().mockImplementation((path) => path === '/import/Album 1'),
        invalidate: mockInvalidate,
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: { '/import/Album 1': true } },
        isLoading: false,
      } as any)

      renderPanel()

      // Wait for albums to load
      await waitFor(() => {
        expect(screen.getByText('Album 1')).toBeInTheDocument()
      })

      // Click on re-analyze button for Album 1 (which has cached data)
      const reanalyzeButton = screen.getByRole('button', { name: 'Re-analyze album' })
      fireEvent.click(reanalyzeButton)

      // Should invalidate cache
      await waitFor(() => {
        expect(mockInvalidate).toHaveBeenCalledWith('/import/Album 1')
      })

      // Should call mutateAsync with force=true since it was cached
      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({ albumPath: '/import/Album 1', force: true })
      })
    })
  })

  // ============================================================================
  // Backend Cache Stage Derivation
  // ============================================================================

  describe('Backend Cache Stage Derivation', () => {
    it('should show backend-cached albums as analyzed even without local cache', async () => {
      // Simulates returning to the page: local TanStack cache is empty but
      // the backend still has analysis results for Album 2.
      await setupDefaultMocks()

      const { useCacheStatus } = await import('@/hooks/useBeetsAnalysis')
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: { '/import/Album 2': true } },
        isLoading: false,
      } as any)

      renderPanel()

      await waitFor(() => {
        expect(screen.getByText('Album 2')).toBeInTheDocument()
      })

      // Album 2 shows as analyzed (re-analyze label); Albums 1 and 3 do not
      expect(screen.getAllByRole('button', { name: 'Re-analyze album' })).toHaveLength(1)
      expect(screen.getAllByRole('button', { name: 'Analyze album' })).toHaveLength(2)
    })
  })

  // ============================================================================
  // Album Deletion
  // ============================================================================

  describe('Album Deletion', () => {
    it('should delete an album via the trash icon using the import-root-relative path', async () => {
      await setupDefaultMocks()

      const { useDeleteImportFolder } = await import('@/hooks/useImportTree')
      const mockDeleteMutateAsync = vi.fn().mockResolvedValue({ status: 'deleted' })
      vi.mocked(useDeleteImportFolder).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockDeleteMutateAsync,
        isPending: false,
      } as any)

      renderPanel()

      await waitFor(() => {
        expect(screen.getByText('Album 1')).toBeInTheDocument()
      })

      // Open the confirmation dialog for Album 1 and confirm
      fireEvent.click(screen.getAllByTestId('album-delete-button')[0])
      fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

      // The mutation receives the path relative to the import root
      await waitFor(() => {
        expect(mockDeleteMutateAsync).toHaveBeenCalledWith('Album 1')
      })
    })

    it('should delete the incoming album from the duplicate dialog', async () => {
      await setupDefaultMocks()

      // Mark Album 1 as backend-cached so the panel auto-loads its analysis
      // (mockAnalysisResponse) once selected, exposing the Import button.
      const { useCacheStatus } = await import('@/hooks/useBeetsAnalysis')
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: { '/import/Album 1': true } },
        isLoading: false,
      } as any)

      const { useDeleteImportFolder } = await import('@/hooks/useImportTree')
      const mockDeleteMutateAsync = vi.fn().mockResolvedValue({ status: 'deleted' })
      vi.mocked(useDeleteImportFolder).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockDeleteMutateAsync,
        isPending: false,
      } as any)

      // Importing returns 409 ALBUM_ALREADY_EXISTS, which opens the dialog.
      const { startImport, BeetsImportApiError } = await import('@/api/beets-import')
      vi.mocked(startImport).mockRejectedValue(
        new BeetsImportApiError('Album already in library', 409, 'ALBUM_ALREADY_EXISTS', {
          existing: {
            albumId: 7,
            artist: 'Test Artist',
            album: 'Album 1',
            matchReason: 'artist_album',
            stats: null,
          },
          incoming: null,
        })
      )

      renderPanel()

      await waitFor(() => {
        expect(screen.getByText('Album 1')).toBeInTheDocument()
      })

      // Select Album 1 → auto-analysis loads candidates and the Import button.
      fireEvent.click(screen.getByText('Album 1'))
      const importButton = await screen.findByTestId('import-button')
      fireEvent.click(importButton)

      // The duplicate dialog appears; deleting removes the import folder using
      // the import-root-relative path and closes the dialog.
      const deleteButton = await screen.findByTestId('upgrade-delete-incoming-button')
      fireEvent.click(deleteButton)

      await waitFor(() => {
        expect(mockDeleteMutateAsync).toHaveBeenCalledWith('Album 1')
      })
      await waitFor(() => {
        expect(screen.queryByTestId('upgrade-delete-incoming-button')).not.toBeInTheDocument()
      })
    })
  })

  // ============================================================================
  // Layout Tests
  // ============================================================================

  describe('Layout', () => {
    it('should apply custom className', async () => {
      await setupDefaultMocks()

      const { container } = render(
        <BeetsImportPanel librarySlug="test-library" className="custom-class" />,
        { wrapper }
      )

      expect(container.firstChild).toHaveClass('custom-class')
    })

    it('should render both album list and details cards', async () => {
      await setupDefaultMocks()

      renderPanel()

      await waitFor(() => {
        // Album list card
        expect(screen.getByText('Albums')).toBeInTheDocument()
        // Details card
        expect(screen.getByText('Candidate Details')).toBeInTheDocument()
      })
    })

    it('should render the middleSlot between the album list and candidate details', async () => {
      await setupDefaultMocks()

      render(
        <BeetsImportPanel
          librarySlug="test-library"
          middleSlot={<div data-testid="middle-slot">slot content</div>}
        />,
        { wrapper }
      )

      await waitFor(() => {
        expect(screen.getByTestId('middle-slot')).toBeInTheDocument()
      })
    })

    it('should report selection via onSelectPath when controlled', async () => {
      await setupDefaultMocks()

      const onSelectPath = vi.fn()
      render(
        <BeetsImportPanel
          librarySlug="test-library"
          selectedPath={null}
          onSelectPath={onSelectPath}
        />,
        { wrapper }
      )

      const firstAlbum = await screen.findAllByTestId('album-list-item')
      await act(async () => {
        fireEvent.click(firstAlbum[0])
      })

      // Controlled mode: the panel asks the parent to update selection with an
      // absolute path (importPath "/import" + the album's relative path).
      expect(onSelectPath).toHaveBeenCalledWith('/import/Album 1')
    })

    it('renders the Analyze All button inside the album list card', async () => {
      await setupDefaultMocks()

      renderPanel()

      await waitFor(() => {
        const card = screen.getByTestId('album-list-card')
        expect(within(card).getByTestId('analyze-all-button')).toBeInTheDocument()
      })
    })

    it('notifies onAnalysisChange (null before any album is analyzed)', async () => {
      await setupDefaultMocks()

      const onAnalysisChange = vi.fn()
      render(
        <BeetsImportPanel
          librarySlug="test-library"
          onAnalysisChange={onAnalysisChange}
        />,
        { wrapper }
      )

      await waitFor(() => {
        expect(onAnalysisChange).toHaveBeenCalledWith(null)
      })
    })
  })

  // ============================================================================
  // Complete Workflow Test
  // ============================================================================

  describe('Complete Workflow', () => {
    it('should complete full workflow: load albums -> select album -> trigger analysis -> view results', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate } = await import(
        '@/hooks/useBeetsAnalysis'
      )

      const mockMutateAsync = vi.fn().mockResolvedValue(mockAnalysisResponse)
      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as any)

      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)

      renderPanel()

      // 1. Verify albums are displayed
      await waitFor(() => {
        expect(screen.getByText('Album 1')).toBeInTheDocument()
        expect(screen.getByText('Album 2')).toBeInTheDocument()
        expect(screen.getByText('Album 3')).toBeInTheDocument()
      })

      // 2. Verify empty state in details card
      expect(screen.getByText('No Album Selected')).toBeInTheDocument()

      // 3. Trigger analysis by clicking disc
      const analyzeButtons = screen.getAllByRole('button', { name: 'Analyze album' })

      await act(async () => {
        fireEvent.click(analyzeButtons[0])
        await mockMutateAsync({ albumPath: '/import/Album 1', force: false })
      })

      // 4. Verify analysis results are displayed
      await waitFor(() => {
        expect(screen.getByText('/import/Album 1')).toBeInTheDocument()
        expect(screen.getByText('Test Artist')).toBeInTheDocument()
        expect(screen.getByText('MusicBrainz')).toBeInTheDocument()
        expect(screen.getByText('95.0%')).toBeInTheDocument()
      })

      // 5. Verify the album is now selected
      const albumRows = screen.getAllByRole('button')
      const album1Row = albumRows.find((row) => row.textContent?.includes('Album 1'))
      expect(album1Row).toHaveAttribute('aria-selected', 'true')
    })
  })

  // ============================================================================
  // Analyze All Button Tests
  // ============================================================================

  describe('Analyze All Button', () => {
    it('should render Analyze All button', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate, useAnalysisQueue, useAnalyzeFolder } = await import(
        '@/hooks/useBeetsAnalysis'
      )

      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn().mockResolvedValue(mockAnalysisResponse),
        isPending: false,
      } as any)
      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)
      vi.mocked(useAnalysisQueue).mockReturnValue({
        data: { queueDepth: 0, activeCount: 0, maxConcurrent: 2, queuedItems: [], activeItems: [] },
        isLoading: false,
        isSuccess: true,
      } as any)
      vi.mocked(useAnalyzeFolder).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)

      renderPanel()

      await waitFor(() => {
        expect(screen.getByTestId('analyze-all-button')).toBeInTheDocument()
        expect(screen.getByText('Analyze All')).toBeInTheDocument()
      })
    })

    it('should call analyzeFolder mutation when Analyze All is clicked', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate, useAnalysisQueue, useAnalyzeFolder } = await import(
        '@/hooks/useBeetsAnalysis'
      )

      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)
      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)
      vi.mocked(useAnalysisQueue).mockReturnValue({
        data: { queueDepth: 0, activeCount: 0, maxConcurrent: 2, queuedItems: [], activeItems: [] },
        isLoading: false,
        isSuccess: true,
      } as any)

      const mockMutateAsync = vi.fn().mockResolvedValue({
        enqueued: 15,
        dispatched: 2,
        alreadyCached: 8,
        total: 25,
        message: 'Enqueued 15 albums',
      } as AnalyzeFolderResponse)

      vi.mocked(useAnalyzeFolder).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as any)

      renderPanel()

      await waitFor(() => {
        expect(screen.getByTestId('analyze-all-button')).toBeInTheDocument()
      })

      const analyzeAllButton = screen.getByTestId('analyze-all-button')

      await act(async () => {
        fireEvent.click(analyzeAllButton)
      })

      expect(mockMutateAsync).toHaveBeenCalledWith({ force: false })
    })

    it('should be disabled when no albums exist', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: { importPath: '/import', children: [] },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate, useAnalysisQueue, useAnalyzeFolder } = await import(
        '@/hooks/useBeetsAnalysis'
      )

      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)
      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)
      vi.mocked(useAnalysisQueue).mockReturnValue({
        data: { queueDepth: 0, activeCount: 0, maxConcurrent: 2, queuedItems: [], activeItems: [] },
        isLoading: false,
        isSuccess: true,
      } as any)
      vi.mocked(useAnalyzeFolder).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)

      renderPanel()

      await waitFor(() => {
        const analyzeAllButton = screen.getByTestId('analyze-all-button')
        expect(analyzeAllButton).toBeDisabled()
      })
    })
  })

  // ============================================================================
  // Queue Depth Indicator Tests
  // ============================================================================

  describe('Queue Depth Indicator', () => {
    it('should show queue depth indicator when items are queued', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate, useAnalysisQueue, useAnalyzeFolder } = await import(
        '@/hooks/useBeetsAnalysis'
      )

      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)
      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)
      vi.mocked(useAnalysisQueue).mockReturnValue({
        data: {
          queueDepth: 5,
          activeCount: 2,
          maxConcurrent: 2,
          queuedItems: [
            { albumPath: '/import/Album 1', position: 1, queuedAt: '2026-02-28T10:30:00Z' },
          ],
          activeItems: [],
        } as AnalyzeQueueResponse,
        isLoading: false,
        isSuccess: true,
      } as any)
      vi.mocked(useAnalyzeFolder).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)

      renderPanel()

      await waitFor(() => {
        expect(screen.getByTestId('queue-depth-indicator')).toBeInTheDocument()
        expect(screen.getByText(/5 queued/)).toBeInTheDocument()
        expect(screen.getByText(/2 analyzing/)).toBeInTheDocument()
      })
    })

    it('should not show queue depth indicator when queue is empty', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const { useAnalyzeAlbum, useBeetsAnalysisCache, useCacheStatus, useAddManualCandidate, useAnalysisQueue, useAnalyzeFolder } = await import(
        '@/hooks/useBeetsAnalysis'
      )

      vi.mocked(useAnalyzeAlbum).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)
      vi.mocked(useBeetsAnalysisCache).mockReturnValue({
        getCached: vi.fn().mockReturnValue(undefined),
        hasCached: vi.fn().mockReturnValue(false),
        invalidate: vi.fn(),
        invalidateAll: vi.fn(),
      })
      vi.mocked(useCacheStatus).mockReturnValue({
        data: { cacheStatus: {} },
        isLoading: false,
      } as any)
      vi.mocked(useAddManualCandidate).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
        isSuccess: false,
        isError: false,
        error: null,
        reset: vi.fn(),
      } as any)
      vi.mocked(useAnalysisQueue).mockReturnValue({
        data: { queueDepth: 0, activeCount: 0, maxConcurrent: 2, queuedItems: [], activeItems: [] },
        isLoading: false,
        isSuccess: true,
      } as any)
      vi.mocked(useAnalyzeFolder).mockReturnValue({
        mutate: vi.fn(),
        mutateAsync: vi.fn(),
        isPending: false,
      } as any)

      renderPanel()

      await waitFor(() => {
        expect(screen.queryByTestId('queue-depth-indicator')).not.toBeInTheDocument()
      })
    })
  })
})
