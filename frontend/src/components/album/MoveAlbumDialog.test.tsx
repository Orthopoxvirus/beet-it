import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MoveAlbumDialog } from './MoveAlbumDialog'

// Mock the data hooks the dialog depends on.
const mockMoveMutate = vi.fn()
const mockReset = vi.fn()

vi.mock('@/hooks/useLibraries', () => ({
  useLibraries: vi.fn(() => ({
    data: {
      items: [
        { slug: 'jazz', name: 'Jazz' },
        { slug: 'pop', name: 'Pop' },
      ],
    },
    isLoading: false,
  })),
}))

vi.mock('@/hooks/useAlbums', () => ({
  useMoveAlbumToLibrary: vi.fn(() => ({
    mutateAsync: mockMoveMutate,
    isPending: false,
    reset: mockReset,
  })),
}))

describe('MoveAlbumDialog', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    vi.clearAllMocks()
    mockMoveMutate.mockResolvedValue({ status: 'queued' })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  const defaultProps = {
    sourceSlug: 'jazz',
    albumId: 7,
    albumTitle: 'Kind of Blue',
    albumArtist: 'Miles Davis',
    isOpen: true,
    onClose: vi.fn(),
  }

  const renderDialog = (props: Partial<typeof defaultProps & { onMoved: () => void }> = {}) =>
    render(
      <QueryClientProvider client={queryClient}>
        <MoveAlbumDialog {...defaultProps} {...props} />
      </QueryClientProvider>
    )

  // Pick a target library through the Radix Select.
  const chooseTarget = async (user: ReturnType<typeof userEvent.setup>, label: RegExp) => {
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: label }))
  }

  it('queues the move with the chosen target, closes, then calls onMoved', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const onMoved = vi.fn()
    renderDialog({ onClose, onMoved })

    await chooseTarget(user, /Pop/)
    await user.click(screen.getByRole('button', { name: /queue move/i }))

    await waitFor(() => expect(onMoved).toHaveBeenCalledTimes(1))
    expect(mockMoveMutate).toHaveBeenCalledWith({
      slug: 'jazz',
      albumId: 7,
      targetLibrarySlug: 'pop',
    })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not throw when onMoved is omitted (overview stays put)', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderDialog({ onClose })

    await chooseTarget(user, /Pop/)
    await user.click(screen.getByRole('button', { name: /queue move/i }))

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(mockMoveMutate).toHaveBeenCalledTimes(1)
  })

  it('excludes the source library from the target options', async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('combobox'))
    expect(await screen.findByRole('option', { name: /Pop/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Jazz/ })).not.toBeInTheDocument()
  })

  it('refuses to submit without a target and does not call the mutation', async () => {
    const user = userEvent.setup()
    const onMoved = vi.fn()
    renderDialog({ onMoved })

    // Button is disabled until a target is picked; force the guard path by
    // asserting nothing fires while no selection exists.
    expect(screen.getByRole('button', { name: /queue move/i })).toBeDisabled()
    expect(mockMoveMutate).not.toHaveBeenCalled()
    expect(onMoved).not.toHaveBeenCalled()
  })
})
