import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import BatchEditTab from '../BatchEditTab'
import type { Library } from '@/api/libraries'
import type { LibraryTreeResponse } from '@/types/library-tree'
import type { LibraryItemsResponse } from '@/api/libraryItems'

// ---------------------------------------------------------------------------
// Test harness
// ---------------------------------------------------------------------------
//
// BatchEditTab composes three async data sources:
//   - useLibraryTree(slug) for the folder picker
//   - useLibraryItems(slug, { albumIds }) for the tracks table
//   - useLibraryItemsPreview / useLibraryBatchTagUpdate inside the form
//
// We mock all three so the tests stay fast + deterministic. The tree component
// itself is tested separately in LibraryFolderTree.test.tsx.
// ---------------------------------------------------------------------------

vi.mock('@/hooks/useLibraryTree', () => ({
  libraryTreeKeys: { all: ['library-tree'], byLibrary: (s: string) => ['library-tree', s] },
  useLibraryTree: vi.fn(),
}))

vi.mock('@/hooks/useLibraryItems', async () => {
  const actual = await vi.importActual<typeof import('@/hooks/useLibraryItems')>(
    '@/hooks/useLibraryItems'
  )
  return {
    ...actual,
    useLibraryItems: vi.fn(),
    useLibraryItemsPreview: vi.fn(),
    useLibraryBatchTagUpdate: vi.fn(),
  }
})

class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver
})

const library: Library = {
  id: 1,
  name: 'Test Library',
  slug: 'test',
  database_path: '/data/databases/test.db',
  import_path: '/data/import/test',
  config_path: '/config/test.yaml',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

// A tree with two top-level artist folders, each with one album. The test
// uses this to assert that selecting a branch loads the right album ids.
const tree: LibraryTreeResponse = {
  libraryPath: '/data/libraries/test',
  root: {
    name: 'test',
    path: '',
    isAlbum: false,
    albumIds: [1, 2],
    children: [
      {
        name: 'Artist A',
        path: 'Artist A',
        isAlbum: false,
        albumIds: [1],
        children: [
          { name: 'Album One', path: 'Artist A/Album One', isAlbum: true, albumIds: [1], children: [] },
        ],
      },
      {
        name: 'Artist B',
        path: 'Artist B',
        isAlbum: false,
        albumIds: [2],
        children: [
          { name: 'Album Two', path: 'Artist B/Album Two', isAlbum: true, albumIds: [2], children: [] },
        ],
      },
    ],
  },
}

const items = (): LibraryItemsResponse => ({
  items: [
    {
      id: 1,
      title: 'Track 1',
      artist: 'Artist A',
      album: 'Album One',
      album_artist: 'Artist A',
      album_id: 1,
      track_number: 1,
      disc_number: null,
      genre: null,
      path: '/data/libraries/test/Artist A/Album One/01 Track 1.mp3',
      duration: 180,
      format: 'MP3',
      bitrate: 320,
    },
    {
      id: 2,
      title: 'Track 2',
      artist: 'Artist B',
      album: 'Album Two',
      album_artist: 'Artist B',
      album_id: 2,
      track_number: 1,
      disc_number: null,
      genre: null,
      path: '/data/libraries/test/Artist B/Album Two/01 Track 2.mp3',
      duration: 200,
      format: 'MP3',
      bitrate: 320,
    },
  ],
  total: 2,
  page: 1,
  per_page: 500,
  page_size: 500,
  total_pages: 1,
  album_filter: null,
})

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <BatchEditTab library={library} />
    </QueryClientProvider>
  )
}

describe('BatchEditTab', () => {
  it('renders the library folder tree instead of a flat album picker', async () => {
    const { useLibraryTree } = await import('@/hooks/useLibraryTree')
    const { useLibraryItems, useLibraryItemsPreview, useLibraryBatchTagUpdate } = await import(
      '@/hooks/useLibraryItems'
    )

    vi.mocked(useLibraryTree).mockReturnValue({
      data: tree,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLibraryTree>)
    vi.mocked(useLibraryItems).mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      error: null,
    } as unknown as ReturnType<typeof useLibraryItems>)
    vi.mocked(useLibraryItemsPreview).mockReturnValue({
      data: undefined,
      isFetching: false,
      error: null,
      previewMap: new Map(),
      getPreviewValue: vi.fn(),
      hasChanges: false,
    } as unknown as ReturnType<typeof useLibraryItemsPreview>)
    vi.mocked(useLibraryBatchTagUpdate).mockReturnValue({
      state: { isUpdating: false, isComplete: false, itemsProcessed: 0, itemsTotal: 0, progress: 0 },
      execute: vi.fn(),
      reset: vi.fn(),
    } as unknown as ReturnType<typeof useLibraryBatchTagUpdate>)

    renderTab()

    expect(screen.getByText('/data/libraries/test')).toBeInTheDocument()
    expect(screen.getByText('Artist A')).toBeInTheDocument()
    expect(screen.getByText('Artist B')).toBeInTheDocument()
    expect(screen.getByText('All 2')).toBeInTheDocument()
  })

  it('selecting the root "All" button loads every album in the library', async () => {
    const user = userEvent.setup()
    const { useLibraryTree } = await import('@/hooks/useLibraryTree')
    const { useLibraryItems, useLibraryItemsPreview, useLibraryBatchTagUpdate } = await import(
      '@/hooks/useLibraryItems'
    )

    vi.mocked(useLibraryTree).mockReturnValue({
      data: tree,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLibraryTree>)
    const useItems = vi.mocked(useLibraryItems)
    useItems.mockReturnValue({
      data: items(),
      isLoading: false,
      isFetching: false,
      error: null,
    } as unknown as ReturnType<typeof useLibraryItems>)
    vi.mocked(useLibraryItemsPreview).mockReturnValue({
      data: undefined,
      isFetching: false,
      error: null,
      previewMap: new Map(),
      getPreviewValue: vi.fn(),
      hasChanges: false,
    } as unknown as ReturnType<typeof useLibraryItemsPreview>)
    vi.mocked(useLibraryBatchTagUpdate).mockReturnValue({
      state: { isUpdating: false, isComplete: false, itemsProcessed: 0, itemsTotal: 0, progress: 0 },
      execute: vi.fn(),
      reset: vi.fn(),
    } as unknown as ReturnType<typeof useLibraryBatchTagUpdate>)

    renderTab()
    await user.click(screen.getByText('All 2'))

    // When the user clicks "All", BatchEditTab re-renders with the root node
    // selected, and useLibraryItems gets called with albumIds = [1, 2].
    await waitFor(() => {
      const lastCall = useItems.mock.calls.at(-1)
      expect(lastCall?.[1]?.albumIds).toEqual([1, 2])
    })
  })

  it('does not fetch items when no folder is selected', async () => {
    const { useLibraryTree } = await import('@/hooks/useLibraryTree')
    const { useLibraryItems, useLibraryItemsPreview, useLibraryBatchTagUpdate } = await import(
      '@/hooks/useLibraryItems'
    )

    vi.mocked(useLibraryTree).mockReturnValue({
      data: tree,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLibraryTree>)
    const useItems = vi.mocked(useLibraryItems)
    useItems.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      error: null,
    } as unknown as ReturnType<typeof useLibraryItems>)
    vi.mocked(useLibraryItemsPreview).mockReturnValue({
      data: undefined,
      isFetching: false,
      error: null,
      previewMap: new Map(),
      getPreviewValue: vi.fn(),
      hasChanges: false,
    } as unknown as ReturnType<typeof useLibraryItemsPreview>)
    vi.mocked(useLibraryBatchTagUpdate).mockReturnValue({
      state: { isUpdating: false, isComplete: false, itemsProcessed: 0, itemsTotal: 0, progress: 0 },
      execute: vi.fn(),
      reset: vi.fn(),
    } as unknown as ReturnType<typeof useLibraryBatchTagUpdate>)

    renderTab()

    // useLibraryItems is always called, but with `enabled: false` on initial
    // render (no selected folder). Verify that `enabled` is the gate.
    const firstCall = useItems.mock.calls[0]
    expect(firstCall?.[1]?.enabled).toBe(false)
  })

  // Shared mock wiring for the "use as template" tests: a tree, two tracks
  // (two distinct artists, no genre), and idle preview/update hooks.
  async function mockHooksWithItems() {
    const { useLibraryTree } = await import('@/hooks/useLibraryTree')
    const { useLibraryItems, useLibraryItemsPreview, useLibraryBatchTagUpdate } =
      await import('@/hooks/useLibraryItems')

    vi.mocked(useLibraryTree).mockReturnValue({
      data: tree,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLibraryTree>)
    vi.mocked(useLibraryItems).mockReturnValue({
      data: items(),
      isLoading: false,
      isFetching: false,
      error: null,
    } as unknown as ReturnType<typeof useLibraryItems>)
    vi.mocked(useLibraryItemsPreview).mockReturnValue({
      data: undefined,
      isFetching: false,
      error: null,
      previewMap: new Map(),
      getPreviewValue: vi.fn(),
      hasChanges: false,
    } as unknown as ReturnType<typeof useLibraryItemsPreview>)
    vi.mocked(useLibraryBatchTagUpdate).mockReturnValue({
      state: { isUpdating: false, isComplete: false, itemsProcessed: 0, itemsTotal: 0, progress: 0 },
      execute: vi.fn(),
      reset: vi.fn(),
    } as unknown as ReturnType<typeof useLibraryBatchTagUpdate>)
  }

  it('seeds the batch editor with a distinct value as a fixed value', async () => {
    const user = userEvent.setup()
    await mockHooksWithItems()

    renderTab()
    await user.click(screen.getByText('All 2'))

    // Use "Artist A" (one of two distinct artists) as a fixed-value template.
    await user.click(
      screen.getByRole('button', { name: /Use "Artist A" as the fixed Artist value/i })
    )

    const input = await screen.findByLabelText('Fixed Value')
    expect(input).toHaveValue('Artist A')
  })

  it('seeds an empty fixed value for an empty distinct value (clears the tag)', async () => {
    const user = userEvent.setup()
    await mockHooksWithItems()

    renderTab()
    await user.click(screen.getByText('All 2'))

    // Both tracks have no genre → a single "(empty)" entry; its arrow seeds
    // an empty fixed value, which clears the tag when applied.
    await user.click(
      screen.getByRole('button', { name: /as the fixed Genre value/i })
    )

    const input = await screen.findByLabelText('Fixed Value')
    expect(input).toHaveValue('')
  })
})
