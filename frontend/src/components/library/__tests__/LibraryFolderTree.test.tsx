import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import LibraryFolderTree from '../LibraryFolderTree'
import type { LibraryTreeResponse, LibraryFolderNode } from '@/types/library-tree'

vi.mock('@/hooks/useLibraryTree', () => ({
  libraryTreeKeys: { all: ['library-tree'], byLibrary: (s: string) => ['library-tree', s] },
  useLibraryTree: vi.fn(),
}))

// Radix ScrollArea uses ResizeObserver; stub a real class (not vi.fn) so
// vi.restoreAllMocks() in sibling suites can't strip the implementation.
class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver
})

const tree: LibraryTreeResponse = {
  libraryPath: '/data/libraries/test',
  root: {
    name: 'test',
    path: '',
    isAlbum: false,
    albumIds: [1, 2, 3],
    children: [
      {
        name: 'Artist A',
        path: 'Artist A',
        isAlbum: false,
        albumIds: [1, 2],
        children: [
          { name: 'Album One', path: 'Artist A/Album One', isAlbum: true, albumIds: [1], children: [] },
          { name: 'Album Two', path: 'Artist A/Album Two', isAlbum: true, albumIds: [2], children: [] },
        ],
      },
      {
        name: 'Artist B',
        path: 'Artist B',
        isAlbum: true,
        albumIds: [3],
        children: [],
      },
    ],
  },
}

function renderTree(onSelect: (node: LibraryFolderNode | null) => void, selectedPath?: string | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <LibraryFolderTree
        librarySlug="test"
        onSelect={onSelect}
        selectedPath={selectedPath ?? null}
      />
    </QueryClientProvider>
  )
}

describe('LibraryFolderTree', () => {
  beforeEach(async () => {
    const { useLibraryTree } = await import('@/hooks/useLibraryTree')
    vi.mocked(useLibraryTree).mockReturnValue({
      data: tree,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLibraryTree>)
  })

  it('renders each top-level folder with album counts', () => {
    renderTree(vi.fn())

    expect(screen.getByText('Artist A')).toBeInTheDocument()
    expect(screen.getByText('Artist B')).toBeInTheDocument()
    expect(screen.getByText('2 albums')).toBeInTheDocument() // Artist A branch
    // Artist B is a terminal 1-album leaf
    expect(screen.getByText('1 album')).toBeInTheDocument()
  })

  it('expands a folder when the chevron is clicked', () => {
    renderTree(vi.fn())

    // Album One is nested under Artist A, so it shouldn't be visible yet.
    expect(screen.queryByText('Album One')).not.toBeInTheDocument()

    // Expand Artist A
    const expandButton = screen.getAllByLabelText('Expand folder')[0]
    fireEvent.click(expandButton)

    expect(screen.getByText('Album One')).toBeInTheDocument()
    expect(screen.getByText('Album Two')).toBeInTheDocument()
  })

  it('clicking a branch folder name selects it', () => {
    const onSelect = vi.fn()
    renderTree(onSelect)

    // Click the Artist A folder name (selects the branch — union of its albums).
    fireEvent.click(screen.getByText('Artist A'))

    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect.mock.calls[0][0]).toMatchObject({
      path: 'Artist A',
      isAlbum: false,
      albumIds: [1, 2],
    })
  })

  it('clicking a terminal album folder selects just that album', () => {
    const onSelect = vi.fn()
    renderTree(onSelect)

    fireEvent.click(screen.getByText('Artist B'))

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ path: 'Artist B', albumIds: [3], isAlbum: true })
    )
  })

  it('"All N" button selects the root with every album id', () => {
    const onSelect = vi.fn()
    renderTree(onSelect)

    fireEvent.click(screen.getByText('All 3'))

    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ path: '', albumIds: [1, 2, 3] }))
  })

  it('highlights the currently-selected folder', () => {
    renderTree(vi.fn(), 'Artist A')
    // The selected row has the primary/ring accent class. We check the
    // parent row of "Artist A" rather than matching the class literally so
    // Tailwind class changes don't break this test.
    const row = screen.getByText('Artist A').closest('div')
    expect(row?.className).toMatch(/bg-primary/)
  })

  it('shows an empty state when the library has no albums', async () => {
    const { useLibraryTree } = await import('@/hooks/useLibraryTree')
    vi.mocked(useLibraryTree).mockReturnValue({
      data: {
        libraryPath: '/data/libraries/test',
        root: { name: 'test', path: '', isAlbum: false, albumIds: [], children: [] },
      },
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLibraryTree>)

    renderTree(vi.fn())

    expect(screen.getByText('No albums in this library yet')).toBeInTheDocument()
  })

  it('shows a loading state while the tree query is fetching', async () => {
    const { useLibraryTree } = await import('@/hooks/useLibraryTree')
    vi.mocked(useLibraryTree).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useLibraryTree>)

    renderTree(vi.fn())

    expect(screen.getByText(/Loading library tree/)).toBeInTheDocument()
  })
})
