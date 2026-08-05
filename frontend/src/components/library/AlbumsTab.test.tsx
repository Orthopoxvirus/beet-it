import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import AlbumsTab from './AlbumsTab'
import { DownloadGatherProvider } from '@/contexts/DownloadGatherContext'
import type { Library } from '@/api/libraries'
import type { AlbumListResponse } from '@/api/albums'
import type { LibraryTreeResponse } from '@/types/library-tree'

// Mock the albums API
vi.mock('@/api/albums', async () => {
  const actual = await vi.importActual<typeof import('@/api/albums')>('@/api/albums')
  return {
    ...actual,
    fetchLibraryAlbums: vi.fn(),
    fetchAlbumLetters: vi.fn(),
  }
})

// Mock the library-tree API (drives the Folders view + folder filter)
vi.mock('@/api/libraryTree', () => ({
  getLibraryTree: vi.fn(),
}))

// Mock the downloads API so the select-mode size lookup doesn't hit the network
vi.mock('@/api/downloads', async () => {
  const actual = await vi.importActual<typeof import('@/api/downloads')>('@/api/downloads')
  return {
    ...actual,
    fetchAlbumSize: vi.fn().mockResolvedValue({ size_bytes: 123, track_count: 1 }),
  }
})

// Surfaces the current location's query string so tests can assert that
// view/filter state is reflected in the URL (issue #98).
function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-search">{location.search}</div>
}

// Mock IntersectionObserver
const mockIntersectionObserver = vi.fn()
const mockObserve = vi.fn()
const mockUnobserve = vi.fn()
const mockDisconnect = vi.fn()

beforeEach(() => {
  mockIntersectionObserver.mockImplementation((callback: IntersectionObserverCallback) => {
    return {
      observe: mockObserve,
      unobserve: mockUnobserve,
      disconnect: mockDisconnect,
    }
  })
  window.IntersectionObserver = mockIntersectionObserver as unknown as typeof IntersectionObserver
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AlbumsTab with Alphabet Navigation', () => {
  let queryClient: QueryClient
  const mockLibrary: Library = {
    id: 1,
    name: 'Test Library',
    slug: 'test-library',
    database_path: '/path/to/db',
    import_path: '/path/to/import',
    config_path: '/path/to/config',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }

  const mockAlbums: AlbumListResponse = {
    items: [
      { id: 1, title: 'Abbey Road', artist: 'The Beatles', cover_art_path: null },
      { id: 2, title: 'Appetite for Destruction', artist: 'Guns N Roses', cover_art_path: null },
      { id: 3, title: 'Back in Black', artist: 'AC/DC', cover_art_path: null },
      { id: 4, title: 'Blue', artist: 'Joni Mitchell', cover_art_path: null },
      { id: 5, title: 'Master of Puppets', artist: 'Metallica', cover_art_path: null },
      { id: 6, title: 'Thriller', artist: 'Michael Jackson', cover_art_path: null },
      { id: 7, title: '21', artist: 'Adele', cover_art_path: null },
    ],
    total: 7,
    skip: 0,
    limit: 50,
  }

  const mockLetters = ['A', 'B', 'M', 'T', '#']

  beforeEach(async () => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    // Default the tree to an empty root so the Folders query never resolves
    // undefined; folder-specific tests override this with `mockTree`.
    const { getLibraryTree } = await import('@/api/libraryTree')
    vi.mocked(getLibraryTree).mockResolvedValue({
      libraryPath: null,
      root: { name: '', path: '', isAlbum: false, albumIds: [], children: [] },
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
    // The gather lives in localStorage; clear it so a select-mode test can't
    // leak into the default normal-mode rendering of other tests.
    localStorage.clear()
  })

  const renderAlbumsTab = (initialEntry = '/') => {
    return render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <QueryClientProvider client={queryClient}>
          <DownloadGatherProvider>
            <AlbumsTab library={mockLibrary} />
            <LocationProbe />
          </DownloadGatherProvider>
        </QueryClientProvider>
      </MemoryRouter>
    )
  }

  // Folder tree exposing two top-level folders mapped to specific albums,
  // used by the Folders view + folder-filter tests.
  const mockTree: LibraryTreeResponse = {
    libraryPath: '/music',
    root: {
      name: '',
      path: '',
      isAlbum: false,
      albumIds: [1, 5],
      children: [
        { name: 'The Beatles', path: 'The Beatles', isAlbum: false, albumIds: [1], children: [] },
        { name: 'Metallica', path: 'Metallica', isAlbum: false, albumIds: [5], children: [] },
      ],
    },
  }

  describe('rendering', () => {
    it('should render loading skeleton while fetching albums', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')

      // Create promises that don't resolve immediately
      let resolveAlbums: (value: AlbumListResponse) => void
      let resolveLetters: (value: string[]) => void
      const pendingAlbums = new Promise<AlbumListResponse>((resolve) => {
        resolveAlbums = resolve
      })
      const pendingLetters = new Promise<string[]>((resolve) => {
        resolveLetters = resolve
      })

      vi.mocked(fetchLibraryAlbums).mockReturnValue(pendingAlbums)
      vi.mocked(fetchAlbumLetters).mockReturnValue(pendingLetters)

      renderAlbumsTab()

      // Should show loading skeleton (animated elements)
      expect(document.querySelector('.animate-pulse')).toBeInTheDocument()

      // Cleanup
      resolveAlbums!(mockAlbums)
      resolveLetters!(mockLetters)
    })

    it('should render albums when data is loaded', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(mockLetters)

      renderAlbumsTab()

      await waitFor(() => {
        expect(screen.getByText('Abbey Road')).toBeInTheDocument()
        expect(screen.getByText('Back in Black')).toBeInTheDocument()
        expect(screen.getByText('Master of Puppets')).toBeInTheDocument()
        expect(screen.getByText('Thriller')).toBeInTheDocument()
      })
    })

    it('should render error state when albums fail to load', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockRejectedValue(new Error('Network error'))
      vi.mocked(fetchAlbumLetters).mockResolvedValue(mockLetters)

      renderAlbumsTab()

      await waitFor(() => {
        expect(screen.getByText('Error Loading Albums')).toBeInTheDocument()
        expect(screen.getByText('Network error')).toBeInTheDocument()
      })
    })

    it('should render empty state when no albums', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue({
        items: [],
        total: 0,
        skip: 0,
        limit: 50,
      })
      vi.mocked(fetchAlbumLetters).mockResolvedValue([])

      renderAlbumsTab()

      await waitFor(() => {
        expect(screen.getByText('No Albums Found')).toBeInTheDocument()
        expect(screen.getByText("This library doesn't have any albums yet.")).toBeInTheDocument()
      })
    })
  })

  describe('alphabet navigation', () => {
    it('should render alphabet navigation when letters are available', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(mockLetters)

      renderAlbumsTab()

      await waitFor(() => {
        const nav = screen.getByRole('navigation', { name: 'Alphabet navigation' })
        expect(nav).toBeInTheDocument()
      })
    })

    it('should not render alphabet navigation when no letters are available', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue([])

      renderAlbumsTab()

      await waitFor(() => {
        expect(screen.getByText('Abbey Road')).toBeInTheDocument()
      })

      // Alphabet nav should not be present
      expect(screen.queryByRole('navigation', { name: 'Alphabet navigation' })).not.toBeInTheDocument()
    })

    it('should show available letters as enabled', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(['A', 'B', 'M'])

      renderAlbumsTab()

      await waitFor(() => {
        const nav = screen.getByRole('navigation', { name: 'Alphabet navigation' })
        const aButton = within(nav).getByRole('button', { name: 'A' })
        const bButton = within(nav).getByRole('button', { name: 'B' })
        const mButton = within(nav).getByRole('button', { name: 'M' })

        expect(aButton).not.toBeDisabled()
        expect(bButton).not.toBeDisabled()
        expect(mButton).not.toBeDisabled()
      })
    })

    it('should show unavailable letters as disabled', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(['A'])

      renderAlbumsTab()

      await waitFor(() => {
        const nav = screen.getByRole('navigation', { name: 'Alphabet navigation' })
        const zButton = within(nav).getByRole('button', { name: 'Z' })

        expect(zButton).toBeDisabled()
      })
    })
  })

  describe('letter anchors', () => {
    it('should render letter anchor elements for each group', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(mockLetters)

      renderAlbumsTab()

      await waitFor(() => {
        // Check for letter anchor elements
        expect(document.getElementById('letter-A')).toBeInTheDocument()
        expect(document.getElementById('letter-B')).toBeInTheDocument()
        expect(document.getElementById('letter-M')).toBeInTheDocument()
        expect(document.getElementById('letter-T')).toBeInTheDocument()
      })
    })

    it('should render # anchor for albums starting with numbers', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(['#'])

      renderAlbumsTab()

      await waitFor(() => {
        // The "21" album should create a # anchor
        expect(document.getElementById('letter-#')).toBeInTheDocument()
      })
    })
  })

  describe('album sorting', () => {
    it('should display albums sorted alphabetically', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      const unsortedAlbums: AlbumListResponse = {
        items: [
          { id: 1, title: 'Zeppelin IV', artist: 'Led Zeppelin', cover_art_path: null },
          { id: 2, title: 'Abbey Road', artist: 'The Beatles', cover_art_path: null },
          { id: 3, title: 'Master of Puppets', artist: 'Metallica', cover_art_path: null },
        ],
        total: 3,
        skip: 0,
        limit: 50,
      }

      vi.mocked(fetchLibraryAlbums).mockResolvedValue(unsortedAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(['A', 'M', 'Z'])

      renderAlbumsTab()

      await waitFor(() => {
        const allCards = screen.getAllByRole('heading', { level: 3 })
        const titles = allCards.map((card) => card.textContent)

        // Should be sorted alphabetically
        expect(titles).toEqual(['Abbey Road', 'Master of Puppets', 'Zeppelin IV'])
      })
    })
  })

  describe('scroll interaction', () => {
    it('should call scrollIntoView when a letter is clicked', async () => {
      const user = userEvent.setup()
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(['A', 'M'])

      renderAlbumsTab()

      await waitFor(() => {
        expect(screen.getByRole('navigation', { name: 'Alphabet navigation' })).toBeInTheDocument()
      })

      // Mock scrollIntoView on the anchor element
      const mAnchor = document.getElementById('letter-M')!
      const scrollIntoViewMock = vi.fn()
      mAnchor.scrollIntoView = scrollIntoViewMock

      // Click on M letter
      const nav = screen.getByRole('navigation', { name: 'Alphabet navigation' })
      const mButton = within(nav).getByRole('button', { name: 'M' })
      await user.click(mButton)

      expect(scrollIntoViewMock).toHaveBeenCalledWith({
        behavior: 'smooth',
        block: 'start',
      })
    })
  })

  describe('album card rendering', () => {
    it('should render album cards with title and artist', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(mockLetters)

      renderAlbumsTab()

      await waitFor(() => {
        // Check album titles
        expect(screen.getByText('Abbey Road')).toBeInTheDocument()
        expect(screen.getByText('Back in Black')).toBeInTheDocument()

        // Check artists
        expect(screen.getByText('The Beatles')).toBeInTheDocument()
        expect(screen.getByText('AC/DC')).toBeInTheDocument()
      })
    })

    it('should show placeholder icon for albums without cover art', async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(mockLetters)

      renderAlbumsTab()

      await waitFor(() => {
        // Albums without cover_art_path should show the Music icon placeholder
        // We can check by looking for the muted background divs that contain the icon
        const placeholders = document.querySelectorAll('.bg-muted')
        expect(placeholders.length).toBeGreaterThan(0)
      })
    })
  })

  // ==========================================================================
  // URL-driven view + filters (issue #98): the active view and folder/artist
  // drill-down live in the query string so back/refresh/share restore them.
  // ==========================================================================
  describe('URL-driven view + filters', () => {
    beforeEach(async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      const { getLibraryTree } = await import('@/api/libraryTree')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(mockLetters)
      vi.mocked(getLibraryTree).mockResolvedValue(mockTree)
    })

    it('honours ?view=folders by selecting the Folders tab and listing folders', async () => {
      renderAlbumsTab('/?view=folders')

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: 'Folders' })).toHaveAttribute(
          'aria-selected',
          'true'
        )
      })
      // Folder cards from the mocked tree are rendered.
      expect(
        screen.getByRole('button', { name: /Folder The Beatles/ })
      ).toBeInTheDocument()
    })

    it('honours ?view=albums&artist=… by filtering the grid to that artist', async () => {
      renderAlbumsTab('/?view=albums&artist=The+Beatles')

      await waitFor(() => {
        expect(screen.getByText('Abbey Road')).toBeInTheDocument()
      })
      // Other artists' albums are filtered out, and the active chip shows.
      expect(screen.queryByText('Thriller')).not.toBeInTheDocument()
      expect(screen.getByText('Artist:')).toBeInTheDocument()
    })

    it('honours ?view=albums&folder=… by filtering the grid to that folder', async () => {
      renderAlbumsTab('/?view=albums&folder=The+Beatles')

      await waitFor(() => {
        expect(screen.getByText('Abbey Road')).toBeInTheDocument()
      })
      expect(screen.queryByText('Master of Puppets')).not.toBeInTheDocument()
      expect(screen.getByText('Folder:')).toBeInTheDocument()
    })

    it('writes the folder drill-down into the URL when a folder card is clicked', async () => {
      const user = userEvent.setup()
      renderAlbumsTab('/?view=folders')

      const folderCard = await screen.findByRole('button', {
        name: /Folder The Beatles/,
      })
      await user.click(folderCard)

      // The grid is now filtered and the URL reflects the drill-down so that
      // navigating into an album and back restores this exact view.
      await waitFor(() => {
        const search = screen.getByTestId('location-search').textContent ?? ''
        const params = new URLSearchParams(search)
        expect(params.get('view')).toBe('albums')
        expect(params.get('folder')).toBe('The Beatles')
      })
      expect(screen.queryByText('Master of Puppets')).not.toBeInTheDocument()
    })

    it('clears the folder filter from the URL via the chip', async () => {
      const user = userEvent.setup()
      renderAlbumsTab('/?view=albums&folder=The+Beatles')

      const chip = await screen.findByTitle('Clear folder filter')
      await user.click(chip)

      await waitFor(() => {
        const search = screen.getByTestId('location-search').textContent ?? ''
        expect(new URLSearchParams(search).get('folder')).toBeNull()
      })
      // Filter gone → full album set is back.
      expect(screen.getByText('Master of Puppets')).toBeInTheDocument()
    })
  })

  describe('select mode (download gathering)', () => {
    beforeEach(async () => {
      const { fetchLibraryAlbums, fetchAlbumLetters } = await import('@/api/albums')
      vi.mocked(fetchLibraryAlbums).mockResolvedValue(mockAlbums)
      vi.mocked(fetchAlbumLetters).mockResolvedValue(mockLetters)
      // Seed the gather so count > 0 → cards render in select mode.
      localStorage.setItem(
        'download-gather',
        JSON.stringify({
          slug: 'test-library',
          items: [{ id: 1, title: 'Abbey Road', artist: 'The Beatles', sizeBytes: 100 }],
        })
      )
    })

    it('shows select checkboxes instead of the actions menu', async () => {
      renderAlbumsTab()
      await screen.findByText('Abbey Road')

      // Cover is now a select toggle for every album…
      expect(screen.getByLabelText('Deselect Abbey Road for download')).toBeInTheDocument()
      expect(screen.getByLabelText('Select Back in Black for download')).toBeInTheDocument()
      // …and the 3-dots actions menu is gone.
      expect(screen.queryByLabelText('Actions for Abbey Road')).not.toBeInTheDocument()
    })

    it('reflects gathered state on the right album', async () => {
      renderAlbumsTab()
      await screen.findByText('Abbey Road')

      expect(screen.getByLabelText('Deselect Abbey Road for download')).toHaveAttribute(
        'aria-pressed',
        'true'
      )
      expect(screen.getByLabelText('Select Thriller for download')).toHaveAttribute(
        'aria-pressed',
        'false'
      )
    })

    it('toggles selection when a cover is clicked', async () => {
      const user = userEvent.setup()
      renderAlbumsTab()
      await screen.findByText('Abbey Road')

      await user.click(screen.getByLabelText('Select Back in Black for download'))
      expect(
        await screen.findByLabelText('Deselect Back in Black for download')
      ).toBeInTheDocument()
    })

    it('still links the title/artist section to the album detail', async () => {
      renderAlbumsTab()
      await screen.findByText('Abbey Road')

      const detailLinks = screen
        .getAllByRole('link')
        .filter((a) => a.getAttribute('href') === '/libraries/test-library/albums/1')
      expect(detailLinks.length).toBeGreaterThan(0)
    })
  })
})
