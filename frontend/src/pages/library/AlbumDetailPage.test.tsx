import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AlbumDetailPage from './AlbumDetailPage'
import type { AlbumDetail, Track } from '@/api/albums'

// Mock the hooks
vi.mock('@/hooks/useAlbums', () => ({
  useAlbumDetail: vi.fn(),
  useAlbumTracks: vi.fn(),
  useUploadCoverArt: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),
  useDownloadCoverArtFromUrl: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),
}))

// Mock the AudioPlayer component to simplify testing
vi.mock('@/components/album', () => ({
  AudioPlayer: vi.fn(({ tracks, currentTrackIndex }) => (
    <div data-testid="audio-player">
      {currentTrackIndex !== null && tracks[currentTrackIndex] ? (
        <span>Playing: {tracks[currentTrackIndex].title}</span>
      ) : (
        <span>No track selected</span>
      )}
    </div>
  )),
  CoverArtUpload: vi.fn(({ isOpen, onClose }) =>
    isOpen ? (
      <div data-testid="cover-art-upload-dialog">
        <button onClick={onClose}>Close</button>
      </div>
    ) : null
  ),
  MoveAlbumDialog: vi.fn(({ isOpen, onClose }) =>
    isOpen ? (
      <div data-testid="move-album-dialog">
        <button onClick={onClose}>Close</button>
      </div>
    ) : null
  ),
  ConvertWavDialog: vi.fn(({ isOpen, onClose, wavTrackCount }) =>
    isOpen ? (
      <div data-testid="convert-wav-dialog">
        <span>{wavTrackCount} WAV tracks</span>
        <button onClick={onClose}>Close</button>
      </div>
    ) : null
  ),
}))

describe('AlbumDetailPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.clearAllMocks()
  })

  const mockAlbum: AlbumDetail = {
    id: 1,
    title: 'Kind of Blue',
    artist: 'Miles Davis',
    year: 1959,
    genre: 'Jazz',
    label: 'Columbia',
    total_tracks: 5,
    total_duration: 2760, // 46 minutes
    cover_art_path: '/covers/kind-of-blue.jpg',
    disc_count: 1,
    added: '2024-01-01T00:00:00Z',
    album_type: 'album',
    mb_albumid: null,
  }

  const mockTracks: Track[] = [
    {
      id: 1,
      title: 'So What',
      artist: 'Miles Davis',
      album_id: 1,
      track_number: 1,
      disc_number: 1,
      duration: 561,
      format: 'FLAC',
      bitrate: 1411,
      sample_rate: 44100,
      channels: 2,
      mb_trackid: null,
    },
    {
      id: 2,
      title: 'Freddie Freeloader',
      artist: 'Miles Davis',
      album_id: 1,
      track_number: 2,
      disc_number: 1,
      duration: 588,
      format: 'FLAC',
      bitrate: 1411,
      sample_rate: 44100,
      channels: 2,
      mb_trackid: null,
    },
    {
      id: 3,
      title: 'Blue in Green',
      artist: 'Miles Davis',
      album_id: 1,
      track_number: 3,
      disc_number: 1,
      duration: 327,
      format: 'FLAC',
      bitrate: 1411,
      sample_rate: 44100,
      channels: 2,
      mb_trackid: null,
    },
  ]

  const renderPage = (slug: string = 'jazz', albumId: string = '1') => {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/libraries/${slug}/albums/${albumId}`]}>
          <Routes>
            <Route path="/libraries/:slug/albums/:albumId" element={<AlbumDetailPage />} />
            <Route path="/libraries/:slug/albums" element={<div>Album List</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )
  }

  describe('Loading state', () => {
    it('should show loading skeleton while fetching album data', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
        isSuccess: false,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
        isSuccess: false,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      // Should show loading skeleton with animated elements
      const skeletons = document.querySelectorAll('.animate-pulse')
      expect(skeletons.length).toBeGreaterThan(0)
    })
  })

  describe('Error states', () => {
    it('should show error message when album fetch fails', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: new Error('Failed to fetch album'),
        isSuccess: false,
        isError: true,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
        isSuccess: false,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Error Loading Album')).toBeInTheDocument()
        expect(screen.getByText('Failed to fetch album')).toBeInTheDocument()
      })
    })

    it('should show album not found message for 404 error', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      const notFoundError = new Error('Not found') as Error & { status: number }
      notFoundError.status = 404

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: notFoundError,
        isSuccess: false,
        isError: true,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
        isSuccess: false,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Album Not Found')).toBeInTheDocument()
      })
    })

    it('should show back button to album list when error occurs', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: new Error('Album not found'),
        isSuccess: false,
        isError: true,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
        isSuccess: false,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        const backLink = screen.getByRole('link', { name: /back to albums/i })
        expect(backLink).toHaveAttribute('href', '/libraries/jazz/albums')
      })
    })

    it('should show invalid album error for invalid album ID', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
        isSuccess: false,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
        isSuccess: false,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage('jazz', 'invalid')

      await waitFor(() => {
        expect(screen.getByText('Invalid Album')).toBeInTheDocument()
        expect(screen.getByText('The album ID is not valid.')).toBeInTheDocument()
      })
    })
  })

  describe('Album metadata display', () => {
    const setupMocks = async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: mockTracks, total: mockTracks.length },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)
    }

    it('should display album title and artist', async () => {
      await setupMocks()
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Kind of Blue')).toBeInTheDocument()
        // Miles Davis appears multiple times (artist header + track rows)
        const artistElements = screen.getAllByText('Miles Davis')
        expect(artistElements.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('should display album year', async () => {
      await setupMocks()
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('1959')).toBeInTheDocument()
      })
    })

    it('should display album genre', async () => {
      await setupMocks()
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Jazz')).toBeInTheDocument()
      })
    })

    it('should display album label', async () => {
      await setupMocks()
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Columbia')).toBeInTheDocument()
      })
    })

    it('should display track count', async () => {
      await setupMocks()
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('5 tracks')).toBeInTheDocument()
      })
    })

    it('should display total duration', async () => {
      await setupMocks()
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('46 min')).toBeInTheDocument()
      })
    })
  })

  describe('Track listing', () => {
    beforeEach(async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: mockTracks, total: mockTracks.length },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)
    })

    it('should display track list heading', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Tracks')).toBeInTheDocument()
      })
    })

    it('should display track titles', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('So What')).toBeInTheDocument()
        expect(screen.getByText('Freddie Freeloader')).toBeInTheDocument()
        expect(screen.getByText('Blue in Green')).toBeInTheDocument()
      })
    })

    it('should display track table headers', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('#')).toBeInTheDocument()
        expect(screen.getByText('Title')).toBeInTheDocument()
        expect(screen.getByText('Artist')).toBeInTheDocument()
        expect(screen.getByText('Duration')).toBeInTheDocument()
      })
    })

    it('should display track durations in correct format', async () => {
      renderPage()

      await waitFor(() => {
        // 561 seconds = 9:21
        expect(screen.getByText('9:21')).toBeInTheDocument()
        // 588 seconds = 9:48
        expect(screen.getByText('9:48')).toBeInTheDocument()
        // 327 seconds = 5:27
        expect(screen.getByText('5:27')).toBeInTheDocument()
      })
    })

    it('should show empty state when no tracks are found', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: [], total: 0 },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('No tracks found for this album.')).toBeInTheDocument()
      })
    })
  })

  describe('Multi-disc album display', () => {
    it('should display disc number column for multi-disc albums', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      const multiDiscAlbum = { ...mockAlbum, disc_count: 2 }
      const multiDiscTracks: Track[] = [
        { ...mockTracks[0], disc_number: 1 },
        { ...mockTracks[1], disc_number: 1 },
        { ...mockTracks[2], disc_number: 2 },
      ]

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: multiDiscAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: multiDiscTracks, total: multiDiscTracks.length },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Disc')).toBeInTheDocument()
        expect(screen.getByText('5 tracks (2 discs)')).toBeInTheDocument()
      })
    })
  })

  describe('Navigation', () => {
    it('should have back button that links to album list', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: mockTracks, total: mockTracks.length },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        const backLink = screen.getByRole('link', { name: /back to albums/i })
        expect(backLink).toHaveAttribute('href', '/libraries/jazz/albums')
      })
    })

    it('should return to the originating filtered grid when arrived via a card', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: mockTracks, total: mockTracks.length },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      // Arrived from a folder-filtered grid — the card passes that URL as
      // router state (issue #98), so "Back to Albums" returns to it.
      const from = '/libraries/jazz/albums?view=albums&folder=Miles+Davis'
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter
            initialEntries={[{ pathname: '/libraries/jazz/albums/1', state: { from } }]}
          >
            <Routes>
              <Route path="/libraries/:slug/albums/:albumId" element={<AlbumDetailPage />} />
              <Route path="/libraries/:slug/albums" element={<div>Album List</div>} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      )

      await waitFor(() => {
        const backLink = screen.getByRole('link', { name: /back to albums/i })
        expect(backLink).toHaveAttribute('href', from)
      })
    })
  })

  describe('Cover art display', () => {
    it('should display cover art image when available', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: mockTracks, total: mockTracks.length },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        const img = screen.getByRole('img', { name: /kind of blue by miles davis/i })
        expect(img).toBeInTheDocument()
        expect(img).toHaveAttribute('src', expect.stringContaining('/api/v1/libraries/jazz/albums/1/cover'))
      })
    })

    it('should show Change Cover button', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: mockTracks, total: mockTracks.length },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /change cover/i })).toBeInTheDocument()
      })
    })

    it('should open cover art upload dialog when Change Cover is clicked', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: mockTracks, total: mockTracks.length },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        const changeButton = screen.getByRole('button', { name: /change cover/i })
        fireEvent.click(changeButton)
      })

      await waitFor(() => {
        expect(screen.getByTestId('cover-art-upload-dialog')).toBeInTheDocument()
      })
    })
  })

  describe('Audio player integration', () => {
    it('should render audio player when tracks are available', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: mockTracks, total: mockTracks.length },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        expect(screen.getByTestId('audio-player')).toBeInTheDocument()
      })
    })

    it('should not render audio player when no tracks are available', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: [], total: 0 },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        expect(screen.queryByTestId('audio-player')).not.toBeInTheDocument()
      })
    })
  })

  describe('Track row click to play', () => {
    it('should update audio player when track row is clicked', async () => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: mockTracks, total: mockTracks.length },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('So What')).toBeInTheDocument()
      })

      // Click on a track row
      const trackRow = screen.getByText('So What').closest('tr')
      expect(trackRow).not.toBeNull()
      fireEvent.click(trackRow!)

      // Audio player should reflect the playing track
      await waitFor(() => {
        expect(screen.getByTestId('audio-player')).toHaveTextContent('Playing: So What')
      })
    })
  })

  describe('WAV to FLAC conversion', () => {
    const setupMocks = async (tracks: Track[]) => {
      const { useAlbumDetail, useAlbumTracks } = await import('@/hooks/useAlbums')

      vi.mocked(useAlbumDetail).mockReturnValue({
        data: mockAlbum,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumDetail>)

      vi.mocked(useAlbumTracks).mockReturnValue({
        data: { items: tracks, total: tracks.length },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as ReturnType<typeof useAlbumTracks>)
    }

    const wavTracks: Track[] = mockTracks.map((track, index) => ({
      ...track,
      // Mixed album: two WAVs, one FLAC — the button must show for mixed too.
      format: index < 2 ? 'WAV' : 'FLAC',
    }))

    it('shows the convert button when the album has WAV tracks', async () => {
      await setupMocks(wavTracks)
      renderPage()

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /convert wav to flac/i })
        ).toBeInTheDocument()
      })
    })

    it('hides the convert button when the album has no WAV tracks', async () => {
      await setupMocks(mockTracks)
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Kind of Blue')).toBeInTheDocument()
      })
      expect(
        screen.queryByRole('button', { name: /convert wav to flac/i })
      ).not.toBeInTheDocument()
    })

    it('opens the conversion dialog with the WAV track count', async () => {
      await setupMocks(wavTracks)
      renderPage()

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /convert wav to flac/i })
        ).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /convert wav to flac/i }))

      await waitFor(() => {
        expect(screen.getByTestId('convert-wav-dialog')).toHaveTextContent(
          '2 WAV tracks'
        )
      })
    })
  })
})
