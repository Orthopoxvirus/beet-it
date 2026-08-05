import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConvertWavDialog } from './ConvertWavDialog'

// Mock the mutation hook the dialog depends on.
const mockConvertMutate = vi.fn()
const mockReset = vi.fn()
let mockIsPending = false

vi.mock('@/hooks/useAlbums', () => ({
  useConvertAlbumWav: vi.fn(() => ({
    mutateAsync: mockConvertMutate,
    isPending: mockIsPending,
    reset: mockReset,
  })),
}))

describe('ConvertWavDialog', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    vi.clearAllMocks()
    mockIsPending = false
    mockConvertMutate.mockResolvedValue({ converted: 3, deleted: 3 })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  const defaultProps = {
    slug: 'jazz',
    albumId: 7,
    albumTitle: 'Kind of Blue',
    albumArtist: 'Miles Davis',
    wavTrackCount: 3,
    isOpen: true,
    onClose: vi.fn(),
  }

  const renderDialog = (props: Partial<typeof defaultProps> = {}) =>
    render(
      <QueryClientProvider client={queryClient}>
        <ConvertWavDialog {...defaultProps} {...props} />
      </QueryClientProvider>
    )

  it('runs the conversion with delete-originals on by default and shows the result', async () => {
    const user = userEvent.setup()
    renderDialog()

    expect(screen.getByText(/3 WAV tracks/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /convert to flac/i }))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        '3 tracks converted, 3 WAVs deleted.'
      )
    )
    expect(mockConvertMutate).toHaveBeenCalledWith({
      slug: 'jazz',
      albumId: 7,
      deleteOriginals: true,
    })
  })

  it('passes deleteOriginals=false when the checkbox is unticked', async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByTestId('delete-originals-checkbox'))
    await user.click(screen.getByRole('button', { name: /convert to flac/i }))

    await waitFor(() =>
      expect(mockConvertMutate).toHaveBeenCalledWith({
        slug: 'jazz',
        albumId: 7,
        deleteOriginals: false,
      })
    )
  })

  it('stays open and shows the error when the conversion fails', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    mockConvertMutate.mockRejectedValue(new Error('ffmpeg exploded'))
    renderDialog({ onClose })

    await user.click(screen.getByRole('button', { name: /convert to flac/i }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('ffmpeg exploded')
    )
    expect(onClose).not.toHaveBeenCalled()
  })

  it('flags partial failures in the result summary', async () => {
    const user = userEvent.setup()
    mockConvertMutate.mockResolvedValue({ converted: 2, deleted: 2, failed: 1 })
    renderDialog()

    await user.click(screen.getByRole('button', { name: /convert to flac/i }))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('1 failed')
    )
  })

  it('closes via the Close button after a successful run', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderDialog({ onClose })

    await user.click(screen.getByRole('button', { name: /convert to flac/i }))
    await waitFor(() => screen.getByRole('status'))

    await user.click(screen.getByTestId('convert-dialog-close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('disables cancel and convert while the conversion runs', () => {
    mockIsPending = true
    renderDialog()

    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /convert to flac/i })).toBeDisabled()
    expect(screen.getByText(/converting/i)).toBeInTheDocument()
  })
})
