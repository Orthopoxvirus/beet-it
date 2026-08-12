import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import MissingCoverTab from '../MissingCoverTab'

const h = vi.hoisted(() => ({
  missing: null as unknown,
  searchCoverArt: vi.fn(),
  downloadCoverArtFromUrl: vi.fn(),
  removeGhost: vi.fn(),
}))

vi.mock('@/hooks/useMaintenance', () => ({
  useMissingCover: () => h.missing,
  useRemoveGhostAlbum: () => ({ mutateAsync: h.removeGhost }),
}))

vi.mock('@/api/albums', () => {
  class AlbumApiError extends Error {
    status: number
    constructor(message: string, status: number) {
      super(message)
      this.name = 'AlbumApiError'
      this.status = status
    }
  }
  return {
    AlbumApiError,
    searchCoverArt: h.searchCoverArt,
    downloadCoverArtFromUrl: h.downloadCoverArtFromUrl,
  }
})

// The dialog drags in react-query hooks we don't exercise here; stub it.
vi.mock('@/components/album/CoverArtUpload', () => ({
  CoverArtUpload: () => null,
}))

const twoAlbums = {
  data: {
    total: 2,
    items: [
      {
        album_id: 1,
        title: 'Kind of Blue',
        artist: 'Miles Davis',
        folder_missing: false,
      },
      {
        album_id: 2,
        title: 'Blue Train',
        artist: 'John Coltrane',
        folder_missing: false,
      },
    ],
  },
  isLoading: false,
  isError: false,
  error: null,
}

// One healthy row + one ghost (folder gone from disk, issue #207).
const withGhost = {
  data: {
    total: 2,
    items: [
      {
        album_id: 1,
        title: 'Kind of Blue',
        artist: 'Miles Davis',
        folder_missing: false,
      },
      {
        album_id: 7,
        title: 'Geissbock Chärly reist um die Welt',
        artist: '',
        folder_missing: true,
      },
    ],
  },
  isLoading: false,
  isError: false,
  error: null,
}

const candidate = {
  url: 'https://is1-ssl.mzstatic.com/cover-1200.jpg',
  source: 'is1-ssl.mzstatic.com',
  width: 1200,
  height: 1200,
}

describe('MissingCoverTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.missing = twoAlbums
  })

  it('renders artist and album for each missing row', () => {
    render(<MissingCoverTab slug="jazz" />)
    expect(screen.getByText('Miles Davis')).toBeInTheDocument()
    expect(screen.getByText('Kind of Blue')).toBeInTheDocument()
    expect(screen.getByText('John Coltrane')).toBeInTheDocument()
  })

  it('searches every album when "Search all online" is clicked', async () => {
    h.searchCoverArt.mockResolvedValue({ query: 'q', results: [candidate] })
    render(<MissingCoverTab slug="jazz" />)

    fireEvent.click(screen.getByRole('button', { name: /search all online/i }))

    await waitFor(() => {
      expect(h.searchCoverArt).toHaveBeenCalledWith('jazz', 1)
      expect(h.searchCoverArt).toHaveBeenCalledWith('jazz', 2)
    })

    // Candidates render inline with resolution + (friendly) source.
    expect(
      (await screen.findAllByText(/1200×1200 · iTunes/)).length
    ).toBeGreaterThan(0)
  })

  it('applies the chosen candidate and greys the row in place', async () => {
    h.searchCoverArt.mockResolvedValue({ query: 'q', results: [candidate] })
    h.downloadCoverArtFromUrl.mockResolvedValue({})
    render(<MissingCoverTab slug="jazz" />)

    fireEvent.click(screen.getByRole('button', { name: /search all online/i }))

    const buttons = await screen.findAllByRole('button', {
      name: /use this itunes cover/i,
    })
    fireEvent.click(buttons[0])

    await waitFor(() => {
      expect(h.downloadCoverArtFromUrl).toHaveBeenCalledWith(
        'jazz',
        1,
        candidate.url
      )
    })

    // Row stays in the table (not removed) and shows the applied state.
    expect(await screen.findByText(/cover applied/i)).toBeInTheDocument()
    expect(screen.getByText('Miles Davis')).toBeInTheDocument()
    expect(screen.getByText(/1 resolved this session/i)).toBeInTheDocument()
  })

  it('shows a no-matches message when a search returns nothing', async () => {
    h.searchCoverArt.mockResolvedValue({ query: 'q', results: [] })
    render(<MissingCoverTab slug="jazz" />)

    fireEvent.click(screen.getByRole('button', { name: /search all online/i }))

    expect((await screen.findAllByText(/no matches found/i)).length).toBe(2)
  })

  it('shows a friendly toast when applying a candidate hits a 404', async () => {
    const { AlbumApiError } = await import('@/api/albums')
    h.searchCoverArt.mockResolvedValue({ query: 'q', results: [candidate] })
    h.downloadCoverArtFromUrl.mockRejectedValue(
      new AlbumApiError('Album folder not found on disk: /tmp/x', 404)
    )
    render(<MissingCoverTab slug="jazz" />)

    fireEvent.click(screen.getByRole('button', { name: /search all online/i }))
    const buttons = await screen.findAllByRole('button', {
      name: /use this itunes cover/i,
    })
    fireEvent.click(buttons[0])

    // Raw API detail (with the server path) is never surfaced.
    expect(
      (
        await screen.findAllByText(
          /album folder not found on disk — the files may have been moved or deleted/i
        )
      ).length
    ).toBeGreaterThan(0)
    expect(screen.queryByText(/\/tmp\/x/)).not.toBeInTheDocument()
  })

  it('offers removal instead of cover search for ghost albums', async () => {
    h.missing = withGhost
    h.removeGhost.mockResolvedValue({})
    render(<MissingCoverTab slug="jazz" />)

    expect(
      screen.getByText(/files missing on disk — cover search unavailable/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/1 with files missing on disk/i)).toBeInTheDocument()
    // The ghost row has no per-row Search / Change-cover actions.
    expect(screen.getAllByRole('button', { name: /^search$/i }).length).toBe(1)
    expect(
      screen.getAllByRole('button', { name: /change cover art/i }).length
    ).toBe(1)

    fireEvent.click(
      screen.getByRole('button', { name: /remove from library/i })
    )
    await waitFor(() => {
      expect(h.removeGhost).toHaveBeenCalledWith(7)
    })
    expect(
      await screen.findByText(/removed from library/i)
    ).toBeInTheDocument()
  })

  it('skips ghost albums in "Search all online"', async () => {
    h.missing = withGhost
    h.searchCoverArt.mockResolvedValue({ query: 'q', results: [] })
    render(<MissingCoverTab slug="jazz" />)

    fireEvent.click(screen.getByRole('button', { name: /search all online/i }))

    await waitFor(() => {
      expect(h.searchCoverArt).toHaveBeenCalledWith('jazz', 1)
    })
    expect(h.searchCoverArt).not.toHaveBeenCalledWith('jazz', 7)
  })
})
