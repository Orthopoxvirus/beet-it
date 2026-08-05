import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import LibraryFolderTree from './LibraryFolderTree'
import type { LibraryFolderNode } from '@/types/library-tree'

const mutateAsync = vi.fn().mockResolvedValue({
  status: 'deleted',
  album_id: 42,
  mode: 'delete_files',
  files_deleted: true,
  relocated_to: null,
})

vi.mock('@/hooks/useLibraryTree', async () => {
  const actual = await vi.importActual<typeof import('@/hooks/useLibraryTree')>(
    '@/hooks/useLibraryTree'
  )
  return { ...actual, useLibraryTree: vi.fn() }
})

vi.mock('@/hooks/useAlbums', () => ({
  useDeleteAlbum: () => ({ mutateAsync, isPending: false }),
}))

vi.mock('@/components/ui/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import { useLibraryTree } from '@/hooks/useLibraryTree'
import { toast } from '@/components/ui/toast'

const albumNode: LibraryFolderNode = {
  name: 'Abbey Road',
  path: 'The Beatles/Abbey Road',
  isAlbum: true,
  albumIds: [42],
  children: [],
}

const tree = {
  libraryPath: '/music',
  root: {
    name: '',
    path: '',
    isAlbum: false,
    albumIds: [42],
    children: [albumNode],
  } as LibraryFolderNode,
}

beforeEach(() => {
  mutateAsync.mockReset()
  mutateAsync.mockResolvedValue({
    status: 'deleted',
    album_id: 42,
    mode: 'delete_files',
    files_deleted: true,
    relocated_to: null,
  })
  vi.mocked(toast.error).mockClear()
  vi.mocked(toast.success).mockClear()
  vi.mocked(useLibraryTree).mockReturnValue({
    data: tree,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useLibraryTree>)
})

describe('LibraryFolderTree delete album', () => {
  it('renders a delete button on a single-album node and deletes on confirm', async () => {
    const user = userEvent.setup()
    render(<LibraryFolderTree librarySlug="test-library" />)

    await user.click(screen.getByLabelText('Delete album Abbey Road'))

    // Dialog offers both disposal choices.
    expect(screen.getByText('Delete album')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Move to import/ })).toBeInTheDocument()
    const deleteBtn = screen.getByRole('button', { name: /Delete files/ })

    await user.click(deleteBtn)

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        slug: 'test-library',
        albumId: 42,
        mode: 'delete_files',
      })
    )
  })

  it('passes move_to_import mode when that choice is taken', async () => {
    const user = userEvent.setup()
    render(<LibraryFolderTree librarySlug="test-library" />)

    await user.click(screen.getByLabelText('Delete album Abbey Road'))
    await user.click(screen.getByRole('button', { name: /Move to import/ }))

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        slug: 'test-library',
        albumId: 42,
        mode: 'move_to_import',
      })
    )
  })

  it('shows an error toast and keeps the dialog open when the delete fails', async () => {
    const user = userEvent.setup()
    mutateAsync.mockRejectedValueOnce(new Error("Import folder already has 'Solo/Only'"))
    render(<LibraryFolderTree librarySlug="test-library" />)

    await user.click(screen.getByLabelText('Delete album Abbey Road'))
    await user.click(screen.getByRole('button', { name: /Delete files/ }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    // Dialog stays open so the user can retry or cancel.
    expect(screen.getByText('Delete album')).toBeInTheDocument()
  })

  it('does not render a delete button on multi-album folders', () => {
    vi.mocked(useLibraryTree).mockReturnValue({
      data: {
        libraryPath: '/music',
        root: {
          name: '',
          path: '',
          isAlbum: false,
          albumIds: [1, 2],
          children: [
            {
              name: 'The Beatles',
              path: 'The Beatles',
              isAlbum: false,
              albumIds: [1, 2],
              children: [],
            },
          ],
        } as LibraryFolderNode,
      },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useLibraryTree>)

    render(<LibraryFolderTree librarySlug="test-library" />)
    expect(screen.queryByLabelText(/Delete album/)).not.toBeInTheDocument()
  })
})
