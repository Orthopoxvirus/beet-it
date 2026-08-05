import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useBeetsImport } from './useBeetsImport'
import { importTreeKeys } from './useImportTree'
import { scanKeys } from './useScanStatus'
import * as beetsImportApi from '@/api/beets-import'
import type { Candidate, ImportJobStatus } from '@/types/beets-import'

// Partial mock: keep BeetsImportApiError (imported by the hook) but stub the
// network calls so we can drive job status from the test.
vi.mock('@/api/beets-import', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/beets-import')>()
  return {
    ...actual,
    startImport: vi.fn(),
    getImportJobStatus: vi.fn(),
    getBulkImportStatus: vi.fn(),
  }
})

const SLUG = 'jazz'
const ALBUM_PATH = '/data/import/jazz/Miles Davis/Kind of Blue'

const candidate: Candidate = {
  source: 'musicbrainz',
  sourceId: 'mb-1',
  artist: 'Miles Davis',
  album: 'Kind of Blue',
  year: 1959,
  tracks: [],
}

describe('useBeetsImport — list reconciliation on terminal job (#126)', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    vi.clearAllMocks()
    vi.mocked(beetsImportApi.getBulkImportStatus).mockResolvedValue({
      albums: {},
      counts: { pending: 0, in_progress: 0, done: 0 },
      import_mode: 'copy',
    })
    vi.mocked(beetsImportApi.startImport).mockResolvedValue({
      jobId: 'job-1',
      status: 'pending',
      albumPath: ALBUM_PATH,
    })
  })

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  // The folder/file lists are keyed off the import tree and import-items
  // queries. Before #126 a finished import only refreshed bulk-status, so those
  // lists went stale whenever the import didn't move the current selection
  // (most visibly on the in-place upgrade path). Assert that a terminal job now
  // invalidates them so the imported entries reconcile with disk.
  it.each<ImportJobStatus>(['completed', 'failed'])(
    'invalidates the import tree + import-items when a job reaches "%s"',
    async (terminalStatus) => {
      vi.mocked(beetsImportApi.getImportJobStatus).mockResolvedValue({
        jobId: 'job-1',
        status: terminalStatus,
        albumPath: ALBUM_PATH,
        startedAt: null,
        completedAt: null,
      })
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

      const { result } = renderHook(() => useBeetsImport(SLUG), { wrapper })

      act(() => {
        result.current.startImport({ albumPath: ALBUM_PATH, candidate })
      })

      await waitFor(() => {
        expect(invalidateSpy).toHaveBeenCalledWith({
          queryKey: importTreeKeys.byLibrary(SLUG),
        })
      })
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: [...scanKeys.importItems(), SLUG],
      })
    }
  )
})
