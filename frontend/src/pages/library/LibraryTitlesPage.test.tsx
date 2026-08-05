import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

import LibraryTitlesPage from './LibraryTitlesPage'
import { DownloadGatherProvider } from '@/contexts/DownloadGatherContext'

const h = vi.hoisted(() => ({
  titles: null as unknown,
  artists: { data: { in_result: [], others: [], total: 0 }, isLoading: false } as unknown,
  fetchTitleIds: vi.fn(),
}))

vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useOutletContext: () => ({ library: { slug: 'jazz', name: 'Jazz' } }),
}))

vi.mock('@/hooks/useTitles', () => ({
  useTitles: () => h.titles,
  useTitleArtists: () => h.artists,
}))

vi.mock('@/api/titles', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/titles')>()),
  fetchTitleIds: (...args: unknown[]) => h.fetchTitleIds(...args),
}))

const row = (id: number, extra: Record<string, unknown> = {}) => ({
  id,
  title: `Song ${id}`,
  artist: 'Artist',
  albumartist: 'Die Ärzte',
  album: 'Album',
  album_id: 1,
  bpm: 155,
  length: 200,
  format: 'MP3',
  bitrate: 320,
  ...extra,
})

const loaded = (items: unknown[], total = items.length) => ({
  data: { items, total, page: 1, per_page: 100 },
  isLoading: false,
  isError: false,
  error: null,
  isFetching: false,
})

function LocationSpy() {
  const location = useLocation()
  return <div data-testid="location-search">{location.search}</div>
}

function renderPage(initialEntry = '/') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <DownloadGatherProvider>
        <LibraryTitlesPage />
        <LocationSpy />
      </DownloadGatherProvider>
    </MemoryRouter>
  )
}

describe('LibraryTitlesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    // jsdom doesn't implement media playback — stub it so the inline player
    // can call play()/pause()/load() without throwing "Not implemented".
    vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
    vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
    vi.spyOn(window.HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  })

  it('renders titles with BPM and a direct-download link', () => {
    h.titles = loaded([row(1), row(2, { bpm: null })])
    renderPage()

    expect(screen.getByText('Song 1')).toBeInTheDocument()
    expect(screen.getByText('155')).toBeInTheDocument()
    const link = screen.getByLabelText('Download Song 1') as HTMLAnchorElement
    expect(link.href).toContain('/tracks/1/stream?download=true')
  })

  it('shows both artist and album-artist columns', () => {
    h.titles = loaded([row(1)])
    renderPage()

    expect(screen.getByRole('columnheader', { name: 'Artist' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Album Artist' })).toBeInTheDocument()
    expect(screen.getByText('Die Ärzte')).toBeInTheDocument()
  })

  it('offers the album-artist filter trigger', () => {
    h.titles = loaded([row(1)])
    renderPage()
    expect(screen.getByLabelText('Filter by album artist')).toBeInTheDocument()
  })

  it('marks a title for download and reflects the gathered state', () => {
    h.titles = loaded([row(1)])
    renderPage()

    fireEvent.click(screen.getByLabelText('Mark Song 1 for download'))
    expect(screen.getByLabelText('Remove Song 1 from selection')).toBeInTheDocument()
  })

  it('marks all filtered results via the ids endpoint', async () => {
    h.titles = loaded([row(1)], 42)
    h.fetchTitleIds.mockResolvedValue({
      items: [
        { id: 1, title: 'Song 1', artist: 'Artist' },
        { id: 2, title: 'Song 2', artist: 'Artist' },
      ],
      total: 42,
    })
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /mark all 42 for download/i }))
    await waitFor(() => expect(h.fetchTitleIds).toHaveBeenCalled())
    // Both returned tracks are now gathered.
    expect(screen.getByLabelText('Remove Song 1 from selection')).toBeInTheDocument()
  })

  it('shows the empty state without filters', () => {
    h.titles = loaded([], 0)
    renderPage()
    expect(screen.getByText('No titles found')).toBeInTheDocument()
  })

  it('renders a play button per row and toggles to pause on click', () => {
    h.titles = loaded([row(1)])
    renderPage()

    const play = screen.getByLabelText('Play Song 1')
    expect(play).toBeInTheDocument()
    fireEvent.click(play)
    expect(screen.getByLabelText('Pause Song 1')).toBeInTheDocument()
  })

  it('exposes a volume slider defaulting to 30%', () => {
    h.titles = loaded([row(1)])
    renderPage()

    const volume = screen.getByLabelText('Playback volume')
    expect(volume).toBeInTheDocument()
    expect(volume.querySelector('[role="slider"]')?.getAttribute('aria-valuenow')).toBe('0.3')
  })

  it('restores search, BPM filter and page from the URL', () => {
    h.titles = loaded([row(1)], 250)
    renderPage('/?q=gr%C3%B6%C3%9Fe&bpmMin=100&bpmMax=140&halfDouble=1&artist=Die+%C3%84rzte&page=2')

    expect(screen.getByLabelText('Search titles')).toHaveValue('größe')
    expect(screen.getByLabelText('BPM min')).toHaveValue(100)
    expect(screen.getByLabelText('BPM max')).toHaveValue(140)
    expect(screen.getByLabelText(/half\/double tempo/)).toBeChecked()
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
  })

  it('mirrors filter changes into the URL', async () => {
    h.titles = loaded([row(1)])
    renderPage()

    fireEvent.change(screen.getByLabelText('Search titles'), { target: { value: 'Motörhead' } })
    fireEvent.change(screen.getByLabelText('BPM min'), { target: { value: '90' } })
    await waitFor(() => {
      const search = screen.getByTestId('location-search').textContent ?? ''
      expect(search).toContain(`q=${encodeURIComponent('Motörhead')}`)
      expect(search).toContain('bpmMin=90')
    })
  })

  it('drops the page param when filters change (reset to page 1)', async () => {
    h.titles = loaded([row(1)], 250)
    renderPage('/?page=2')

    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search titles'), { target: { value: 'jazz' } })
    await waitFor(() => {
      const search = screen.getByTestId('location-search').textContent ?? ''
      expect(search).not.toContain('page=')
      expect(search).toContain('q=jazz')
    })
  })
})
