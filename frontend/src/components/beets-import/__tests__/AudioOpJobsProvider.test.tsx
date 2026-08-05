import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { AudioOpJobsProvider, useAudioOpJobs } from '../AudioOpJobsProvider'
import { Toaster } from '@/components/ui/toast'
import * as api from '@/api/beets-import'
import type { ConvertAudioParams } from '@/types/beets-import'

vi.mock('@/api/beets-import', () => ({
  startConvertAudio: vi.fn(),
  startDedupeWav: vi.fn(),
  getAudioOpStatus: vi.fn(),
}))

const CONVERT_PARAMS: ConvertAudioParams = {
  sourceFormat: 'wav',
  targetFormat: 'flac',
  deleteOriginals: false,
}

/** Test harness exposing the registry API as buttons + status readouts. */
function Harness() {
  const jobs = useAudioOpJobs()!
  return (
    <div>
      <button onClick={() => jobs.startConvert('/base/A', CONVERT_PARAMS)}>start-A</button>
      <button onClick={() => jobs.startConvert('/base/B', CONVERT_PARAMS)}>start-B</button>
      <div data-testid="status-A">{jobs.statusFor('/base/A') ?? 'idle'}</div>
      <div data-testid="status-B">{jobs.statusFor('/base/B') ?? 'idle'}</div>
    </div>
  )
}

function renderProvider(onSelect = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <AudioOpJobsProvider
        librarySlug="lib"
        importBasePath="/base"
        onSelectAlbum={onSelect}
      >
        <Harness />
      </AudioOpJobsProvider>
      <Toaster />
    </QueryClientProvider>
  )
  return { onSelect }
}

describe('AudioOpJobsProvider (issue #130)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it('drives a job queued → running → completed and toasts with a clickable album link', async () => {
    vi.mocked(api.startConvertAudio).mockResolvedValue({
      jobId: 'job-A',
      albumPath: '/base/A',
      status: 'queued',
      message: 'queued',
    })
    vi.mocked(api.getAudioOpStatus)
      .mockResolvedValueOnce({ jobId: 'job-A', status: 'running' })
      .mockResolvedValueOnce({ jobId: 'job-A', status: 'completed', result: {} })

    const { onSelect } = renderProvider()

    // Click → instant optimistic "queued" so the UI never looks hung.
    await act(async () => {
      fireEvent.click(screen.getByText('start-A'))
    })
    expect(screen.getByTestId('status-A')).toHaveTextContent('queued')

    // First poll flips it to running…
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600)
    })
    expect(screen.getByTestId('status-A')).toHaveTextContent('running')

    // …second poll completes it: entry cleared + completion toast shown.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600)
    })
    expect(screen.getByTestId('status-A')).toHaveTextContent('idle')

    const link = screen.getByTestId('audio-op-toast-album')
    expect(link).toHaveTextContent('A')
    // Clicking the bold album name selects it in the tree.
    fireEvent.click(link)
    expect(onSelect).toHaveBeenCalledWith('/base/A')
  })

  it('tracks two albums independently (real background concurrency)', async () => {
    vi.mocked(api.startConvertAudio).mockImplementation(async (_slug, albumPath) => ({
      jobId: `job-${albumPath}`,
      albumPath,
      status: 'queued',
      message: 'queued',
    }))
    // Both stay running across the polls we advance through.
    vi.mocked(api.getAudioOpStatus).mockResolvedValue({
      jobId: 'job',
      status: 'running',
    })

    renderProvider()

    await act(async () => {
      fireEvent.click(screen.getByText('start-A'))
      fireEvent.click(screen.getByText('start-B'))
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600)
    })

    // Each album carries its own active entry — neither blocks the other.
    expect(screen.getByTestId('status-A')).toHaveTextContent('running')
    expect(screen.getByTestId('status-B')).toHaveTextContent('running')
  })

  it('ignores a second start for an album already in flight', async () => {
    vi.mocked(api.startConvertAudio).mockResolvedValue({
      jobId: 'job-A',
      albumPath: '/base/A',
      status: 'queued',
      message: 'queued',
    })
    vi.mocked(api.getAudioOpStatus).mockResolvedValue({
      jobId: 'job-A',
      status: 'running',
    })

    renderProvider()

    await act(async () => {
      fireEvent.click(screen.getByText('start-A'))
      fireEvent.click(screen.getByText('start-A'))
    })

    expect(api.startConvertAudio).toHaveBeenCalledTimes(1)
  })

  it('surfaces a failed job as an error toast and clears the entry', async () => {
    vi.mocked(api.startConvertAudio).mockResolvedValue({
      jobId: 'job-A',
      albumPath: '/base/A',
      status: 'queued',
      message: 'queued',
    })
    vi.mocked(api.getAudioOpStatus).mockResolvedValueOnce({
      jobId: 'job-A',
      status: 'failed',
      error: 'ffmpeg blew up',
    })

    renderProvider()

    await act(async () => {
      fireEvent.click(screen.getByText('start-A'))
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600)
    })

    expect(screen.getByTestId('status-A')).toHaveTextContent('idle')
    expect(screen.getByText(/ffmpeg blew up/)).toBeInTheDocument()
  })
})
