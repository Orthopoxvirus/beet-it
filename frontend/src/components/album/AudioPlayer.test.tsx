import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AudioPlayer } from './AudioPlayer'
import type { Track } from '@/api/albums'

// A successful stream response. AudioPlayer.fetchAndDecode does
// `res.arrayBuffer()` then `ctx.decodeAudioData(...)`; the global setup.ts
// AudioContext mock resolves decodeAudioData synchronously with a fake buffer,
// so the buffer's actual bytes don't matter.
const successfulStreamResponse = () =>
  ({
    ok: true,
    arrayBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(0)),
  }) as unknown as Response

// Better ResizeObserver mock for Radix UI Slider
class MockResizeObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

describe('AudioPlayer', () => {
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

  const mockOnTrackChange = vi.fn()

  const defaultProps = {
    slug: 'jazz',
    tracks: mockTracks,
    currentTrackIndex: null as number | null,
    onTrackChange: mockOnTrackChange,
  }

  beforeEach(() => {
    vi.clearAllMocks()

    // Mock ResizeObserver globally
    global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver

    // Mock HTMLMediaElement methods that don't exist in jsdom
    window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined)
    window.HTMLMediaElement.prototype.pause = vi.fn()
    window.HTMLMediaElement.prototype.load = vi.fn()

    // AudioPlayer streams audio via fetch() then decodeAudioData; give every
    // fetch a successful arrayBuffer by default. Individual tests can
    // override with vi.mocked(fetch).mockResolvedValueOnce(...).
    vi.mocked(global.fetch).mockResolvedValue(successfulStreamResponse())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  const renderComponent = (props: Partial<typeof defaultProps> = {}) => {
    return render(<AudioPlayer {...defaultProps} {...props} />)
  }

  describe('Initial render', () => {
    it('should render the audio player component', () => {
      renderComponent()
      expect(screen.getByText('No track selected')).toBeInTheDocument()
    })

    it('should display "No track selected" when no track is playing', () => {
      renderComponent()
      expect(screen.getByText('No track selected')).toBeInTheDocument()
    })

    it('should render play/pause button', () => {
      renderComponent()
      expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument()
    })

    it('should render stop button', () => {
      renderComponent()
      expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument()
    })

    it('should render previous track button', () => {
      renderComponent()
      expect(screen.getByRole('button', { name: /previous track/i })).toBeInTheDocument()
    })

    it('should render next track button', () => {
      renderComponent()
      expect(screen.getByRole('button', { name: /next track/i })).toBeInTheDocument()
    })

    it('should render mute button', () => {
      renderComponent()
      expect(screen.getByRole('button', { name: /mute/i })).toBeInTheDocument()
    })

    it('should render sliders for playback', () => {
      renderComponent()
      // Radix UI Slider renders slider role elements (volume slider always present)
      const sliders = screen.getAllByRole('slider')
      expect(sliders.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Now playing info', () => {
    it('should display current track title and artist when playing', () => {
      renderComponent({ currentTrackIndex: 0 })
      expect(screen.getByText('So What')).toBeInTheDocument()
      expect(screen.getByText('Miles Davis')).toBeInTheDocument()
    })

    it('should update display when track changes', () => {
      const { rerender } = renderComponent({ currentTrackIndex: 0 })
      expect(screen.getByText('So What')).toBeInTheDocument()

      rerender(
        <AudioPlayer
          {...defaultProps}
          currentTrackIndex={1}
        />
      )
      expect(screen.getByText('Freddie Freeloader')).toBeInTheDocument()
    })
  })

  describe('Play/Pause controls', () => {
    it('should flip to pause button when a track is selected (auto-plays)', async () => {
      renderComponent({ currentTrackIndex: 0 })
      // loadAndPlayTrack awaits fetchAndDecode; setIsPlaying(true) is the
      // last step, so we wait for the label to flip.
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument()
      })
    })

    it('should keep play button enabled when no track is selected so clicking selects the first track', () => {
      renderComponent()
      const playButton = screen.getByRole('button', { name: /play/i })
      // The play button is only disabled when there's nothing to play
      // (empty tracks list) or a load is in flight; with tracks available it
      // stays enabled so the user can click play to start the first track.
      expect(playButton).not.toBeDisabled()
    })

    it('should show pause button when a track is selected and playback starts', async () => {
      renderComponent({ currentTrackIndex: 0 })
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument()
      })
    })
  })

  describe('Track navigation', () => {
    it('should disable previous button on first track', () => {
      renderComponent({ currentTrackIndex: 0 })
      const prevButton = screen.getByRole('button', { name: /previous track/i })
      expect(prevButton).toBeDisabled()
    })

    it('should enable previous button when not on first track', () => {
      renderComponent({ currentTrackIndex: 1 })
      const prevButton = screen.getByRole('button', { name: /previous track/i })
      expect(prevButton).not.toBeDisabled()
    })

    it('should call onTrackChange with previous index when previous button is clicked', () => {
      renderComponent({ currentTrackIndex: 1 })
      const prevButton = screen.getByRole('button', { name: /previous track/i })
      fireEvent.click(prevButton)
      expect(mockOnTrackChange).toHaveBeenCalledWith(0)
    })

    it('should disable next button on last track', () => {
      renderComponent({ currentTrackIndex: 2 })
      const nextButton = screen.getByRole('button', { name: /next track/i })
      expect(nextButton).toBeDisabled()
    })

    it('should enable next button when not on last track', () => {
      renderComponent({ currentTrackIndex: 0 })
      const nextButton = screen.getByRole('button', { name: /next track/i })
      expect(nextButton).not.toBeDisabled()
    })

    it('should call onTrackChange with next index when next button is clicked', () => {
      renderComponent({ currentTrackIndex: 0 })
      const nextButton = screen.getByRole('button', { name: /next track/i })
      fireEvent.click(nextButton)
      expect(mockOnTrackChange).toHaveBeenCalledWith(1)
    })
  })

  describe('Progress display', () => {
    it('should display time as 0:00 initially', () => {
      renderComponent()
      // There should be two 0:00 displays (current and total)
      const timeDisplays = screen.getAllByText('0:00')
      expect(timeDisplays.length).toBeGreaterThanOrEqual(1)
    })

    it('should have a progress slider', () => {
      renderComponent({ currentTrackIndex: 0 })
      // There are multiple sliders (progress and volume)
      const sliders = screen.getAllByRole('slider')
      expect(sliders.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Volume control', () => {
    it('should render volume slider (as part of sliders)', () => {
      renderComponent()
      // Radix UI Slider doesn't properly expose aria-label to testing-library
      // We just check that a slider exists
      const sliders = screen.getAllByRole('slider')
      expect(sliders.length).toBeGreaterThanOrEqual(1)
    })

    it('should render mute toggle button', () => {
      renderComponent()
      const muteButton = screen.getByRole('button', { name: /mute/i })
      expect(muteButton).toBeInTheDocument()
    })

    it('should toggle mute label when clicked', async () => {
      renderComponent()
      const muteButton = screen.getByRole('button', { name: /mute/i })
      fireEvent.click(muteButton)
      // After clicking, it should change to unmute
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /unmute/i })).toBeInTheDocument()
      })
    })
  })

  describe('Disabled states', () => {
    it('should disable stop button when no track is selected', () => {
      renderComponent()
      const stopButton = screen.getByRole('button', { name: /stop/i })
      expect(stopButton).toBeDisabled()
    })

    it('should enable stop button when a track is selected', () => {
      renderComponent({ currentTrackIndex: 0 })
      const stopButton = screen.getByRole('button', { name: /stop/i })
      expect(stopButton).not.toBeDisabled()
    })

    it('should disable navigation buttons when no track is selected', () => {
      renderComponent()
      const prevButton = screen.getByRole('button', { name: /previous track/i })
      const nextButton = screen.getByRole('button', { name: /next track/i })
      expect(prevButton).toBeDisabled()
      expect(nextButton).toBeDisabled()
    })
  })

  describe('Empty tracks array', () => {
    it('should handle empty tracks array gracefully', () => {
      renderComponent({ tracks: [], currentTrackIndex: null })
      expect(screen.getByText('No track selected')).toBeInTheDocument()
    })

    it('should disable all navigation with empty tracks', () => {
      renderComponent({ tracks: [], currentTrackIndex: null })
      const prevButton = screen.getByRole('button', { name: /previous track/i })
      const nextButton = screen.getByRole('button', { name: /next track/i })
      expect(prevButton).toBeDisabled()
      expect(nextButton).toBeDisabled()
    })
  })

  describe('Accessibility', () => {
    it('should have accessible labels for all buttons', async () => {
      renderComponent({ currentTrackIndex: 0 })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument()
      })
      expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /previous track/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /next track/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /mute/i })).toBeInTheDocument()
    })

    it('should show play button when no track is selected', () => {
      renderComponent({ currentTrackIndex: null })
      expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument()
    })

    it('should have sliders for progress and volume', () => {
      renderComponent()
      // Radix UI Slider renders slider role elements
      const sliders = screen.getAllByRole('slider')
      // At minimum, we should have volume slider (progress may be disabled when no track)
      expect(sliders.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Edge cases', () => {
    it('should handle single track', () => {
      const singleTrack = [mockTracks[0]]
      renderComponent({ tracks: singleTrack, currentTrackIndex: 0 })

      // Both navigation buttons should be disabled
      const prevButton = screen.getByRole('button', { name: /previous track/i })
      const nextButton = screen.getByRole('button', { name: /next track/i })
      expect(prevButton).toBeDisabled()
      expect(nextButton).toBeDisabled()
    })

    it('should handle track index out of bounds', () => {
      // If currentTrackIndex is out of bounds, it should show "No track selected"
      renderComponent({ currentTrackIndex: 10 })
      expect(screen.getByText('No track selected')).toBeInTheDocument()
    })
  })
})
