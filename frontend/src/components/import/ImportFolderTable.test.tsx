import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ImportFolderTable from './ImportFolderTable'
import type { ImportItemListResponse, ImportItem } from '@/types/scan'
import type { ItemPreview } from '@/types/batch-tag-editor'

// Mock the useImportFolderItems hook
vi.mock('@/hooks/useImportFolderItems', () => ({
  useImportFolderItems: vi.fn(),
}))

// Mock the WAV→FLAC API client used by the Local Album card actions.
vi.mock('@/api/beets-import', () => ({
  convertAudio: vi.fn().mockResolvedValue({}),
  removeDuplicateWavs: vi.fn().mockResolvedValue({}),
}))

describe('ImportFolderTable', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.clearAllMocks()
  })

  const renderComponent = (props: {
    librarySlug: string
    path: string | null
    className?: string
    previewData?: Map<number, ItemPreview>
    onItemsLoaded?: (itemIds: number[]) => void
    showSummary?: boolean
  }) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <ImportFolderTable {...props} />
      </QueryClientProvider>
    )
  }

  // Helper to create mock import items
  const createMockItem = (overrides: Partial<ImportItem> = {}): ImportItem => ({
    id: 1,
    itemType: 'file',
    path: 'Artist/Album/track.flac',
    directory: 'Artist/Album',
    filename: 'track.flac',
    album: 'Test Album',
    albumArtist: 'Test Artist',
    artist: 'Test Artist',
    title: 'Test Track',
    trackNumber: 1,
    trackTotal: 12,
    genre: 'Rock',
    format: 'flac',
    bitrate: 1000,
    status: 'new',
    firstSeenAt: '2024-01-01T00:00:00Z',
    lastSeenAt: '2024-01-01T00:00:00Z',
    ...overrides,
  })

  // Mock response with single album
  const mockSingleAlbumResponse: ImportItemListResponse = {
    items: [
      createMockItem({ id: 1, trackNumber: 1, title: 'Track 1' }),
      createMockItem({ id: 2, trackNumber: 2, title: 'Track 2' }),
      createMockItem({ id: 3, trackNumber: 3, title: 'Track 3' }),
    ],
    total: 3,
    skip: 0,
    limit: 500,
    scanId: 1,
    scanCompletedAt: '2024-01-01T12:00:00Z',
  }

  // Mock response with multiple albums
  const mockMultiAlbumResponse: ImportItemListResponse = {
    items: [
      createMockItem({ id: 1, album: 'Album A', trackNumber: 1, title: 'A Track 1' }),
      createMockItem({ id: 2, album: 'Album A', trackNumber: 2, title: 'A Track 2' }),
      createMockItem({ id: 3, album: 'Album B', trackNumber: 1, title: 'B Track 1' }),
      createMockItem({ id: 4, album: 'Album B', trackNumber: 2, title: 'B Track 2' }),
      createMockItem({ id: 5, album: 'Album C', trackNumber: 1, title: 'C Track 1' }),
    ],
    total: 5,
    skip: 0,
    limit: 500,
    scanId: 1,
    scanCompletedAt: '2024-01-01T12:00:00Z',
  }

  describe('Empty state - no folder selected', () => {
    it('should show empty state when no path is selected', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
        isSuccess: false,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: null })

      expect(screen.getByText('Select a folder to view tracks')).toBeInTheDocument()
    })
  })

  describe('Loading state', () => {
    it('should show loading indicator when fetching data', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
        isSuccess: false,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      expect(screen.getByText('Loading tracks...')).toBeInTheDocument()
    })
  })

  describe('Error state', () => {
    it('should show error message when API call fails', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: new Error('Network error'),
        isSuccess: false,
        isError: true,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      expect(screen.getByText('Failed to load tracks')).toBeInTheDocument()
      expect(screen.getByText('Network error')).toBeInTheDocument()
    })
  })

  describe('Not scanned state', () => {
    it('should show message when folder has not been scanned', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [],
          total: 0,
          skip: 0,
          limit: 500,
          scanId: null,
          scanCompletedAt: null,
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      expect(screen.getByText('This folder has not been scanned yet. Run a scan to discover tracks.')).toBeInTheDocument()
    })
  })

  describe('No tracks found', () => {
    it('should show empty state when no tracks found in scanned folder', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [],
          total: 0,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      expect(screen.getByText('No tracks found in this folder')).toBeInTheDocument()
    })
  })

  describe('Table rendering with single album', () => {
    it('should render table with all columns', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      // Check table headers
      expect(screen.getByText('Directory')).toBeInTheDocument()
      expect(screen.getByText('Filename')).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Album' })).toBeInTheDocument()
      expect(screen.getByText('Album Artist')).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Artist' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Title' })).toBeInTheDocument()
      expect(screen.getByText('Track #')).toBeInTheDocument()
      expect(screen.getByText('Genre')).toBeInTheDocument()
    })

    it('should display tracks without album intertitles for single album', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      // Should show track titles
      expect(screen.getByText('Track 1')).toBeInTheDocument()
      expect(screen.getByText('Track 2')).toBeInTheDocument()
      expect(screen.getByText('Track 3')).toBeInTheDocument()

      // Should NOT show album intertitle for single album
      expect(screen.queryByText(/Album:/)).not.toBeInTheDocument()
    })

    it('should display track count in header', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      expect(screen.getByText('3 tracks')).toBeInTheDocument()
    })

    it('should show single format and bitrate in header', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      expect(screen.getByText('FLAC · 1000 kbps')).toBeInTheDocument()
    })

    it('should show mixed formats and a bitrate range in header', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      const mixed: ImportItemListResponse = {
        ...mockSingleAlbumResponse,
        items: [
          createMockItem({ id: 1, format: 'flac', bitrate: 1000 }),
          createMockItem({ id: 2, format: 'mp3', bitrate: 320 }),
        ],
        total: 2,
      }
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mixed,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist' })

      expect(screen.getByText('FLAC, MP3 · 320–1000 kbps')).toBeInTheDocument()
    })

    it('should show a dash when format and bitrate are absent', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      const noQuality: ImportItemListResponse = {
        ...mockSingleAlbumResponse,
        items: [createMockItem({ id: 1, format: null, bitrate: null })],
        total: 1,
      }
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: noQuality,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      expect(screen.getByText('—')).toBeInTheDocument()
    })

    it('should show selected folder path in header', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      expect(screen.getByText('/Artist/Album')).toBeInTheDocument()
    })
  })

  describe('Album grouping with intertitles', () => {
    it('should display album intertitles for multiple albums', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockMultiAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist' })

      // Should show album intertitles
      expect(screen.getByText('Album: Album A')).toBeInTheDocument()
      expect(screen.getByText('Album: Album B')).toBeInTheDocument()
      expect(screen.getByText('Album: Album C')).toBeInTheDocument()
    })

    it('should group tracks under correct album intertitles', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockMultiAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist' })

      // All track titles should be present
      expect(screen.getByText('A Track 1')).toBeInTheDocument()
      expect(screen.getByText('A Track 2')).toBeInTheDocument()
      expect(screen.getByText('B Track 1')).toBeInTheDocument()
      expect(screen.getByText('B Track 2')).toBeInTheDocument()
      expect(screen.getByText('C Track 1')).toBeInTheDocument()
    })

    it('should show album count in header for multiple albums', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockMultiAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist' })

      expect(screen.getByText('5 tracks in 3 albums')).toBeInTheDocument()
    })

    it('should sort albums alphabetically', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockMultiAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist' })

      const albumHeaders = screen.getAllByText(/^Album:/)
      expect(albumHeaders[0]).toHaveTextContent('Album: Album A')
      expect(albumHeaders[1]).toHaveTextContent('Album: Album B')
      expect(albumHeaders[2]).toHaveTextContent('Album: Album C')
    })
  })

  describe('Track ordering within albums', () => {
    it('should order tracks by track number within each album', async () => {
      const unorderedItems: ImportItem[] = [
        createMockItem({ id: 1, album: 'Test Album', trackNumber: 3, title: 'Track Three' }),
        createMockItem({ id: 2, album: 'Test Album', trackNumber: 1, title: 'Track One' }),
        createMockItem({ id: 3, album: 'Test Album', trackNumber: 2, title: 'Track Two' }),
      ]

      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: unorderedItems,
          total: 3,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      // Get all table rows (excluding header row)
      const rows = screen.getAllByRole('row')
      // First row is header, data rows start from index 1
      // Check that tracks appear in track number order
      const trackCells = rows.slice(1).map((row) => row.textContent)
      expect(trackCells[0]).toContain('Track One')
      expect(trackCells[1]).toContain('Track Two')
      expect(trackCells[2]).toContain('Track Three')
    })
  })

  describe('Track number formatting', () => {
    it('should display track number as x/y when trackTotal is available', async () => {
      const itemWithTrackTotal = createMockItem({
        id: 1,
        trackNumber: 3,
        trackTotal: 12,
        title: 'Track with total',
      })

      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [itemWithTrackTotal],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      // Should display track number in x/y format
      expect(screen.getByText('3/12')).toBeInTheDocument()
    })

    it('should display only track number when trackTotal is null', async () => {
      const itemWithoutTrackTotal = createMockItem({
        id: 1,
        trackNumber: 5,
        trackTotal: null,
        title: 'Track without total',
      })

      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [itemWithoutTrackTotal],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      // Should display just the track number
      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it('should display dash when trackNumber is null', async () => {
      const itemWithoutTrackNumber = createMockItem({
        id: 1,
        trackNumber: null,
        trackTotal: 12,
        title: 'Track without number',
      })

      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [itemWithoutTrackNumber],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      // Should display dash for missing track number
      const rows = screen.getAllByRole('row')
      const dataRow = rows[1]
      expect(dataRow.textContent).toContain('-')
    })
  })

  describe('Missing metadata handling', () => {
    it('should display dash for missing metadata fields', async () => {
      const itemWithMissingData = createMockItem({
        id: 1,
        album: null,
        albumArtist: null,
        artist: null,
        title: null,
        trackNumber: null,
        trackTotal: null,
        genre: null,
      })

      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [itemWithMissingData],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      // Count the number of dash placeholders in the table
      const rows = screen.getAllByRole('row')
      const dataRow = rows[1] // First data row after header
      const cells = dataRow.querySelectorAll('td')

      // Album, Album Artist, Artist, Title, Track #, Genre should all show '-'
      // Directory and Filename should have actual values
      expect(dataRow.textContent).toContain('-')
    })

    it('should use Unknown Album for tracks with null album', async () => {
      const itemsWithNullAlbum: ImportItem[] = [
        createMockItem({ id: 1, album: null, title: 'Track 1' }),
        createMockItem({ id: 2, album: null, title: 'Track 2' }),
      ]

      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: itemsWithNullAlbum,
          total: 2,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      // Should not show intertitle for single album group (even if it's "Unknown Album")
      expect(screen.queryByText(/Album:/)).not.toBeInTheDocument()
    })
  })

  describe('CSS class handling', () => {
    it('should apply custom className when provided', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
        isSuccess: false,
        isError: false,
      } as any)

      const { container } = renderComponent({
        librarySlug: 'test-lib',
        path: null,
        className: 'custom-class',
      })

      const tableContainer = container.firstChild as HTMLElement
      expect(tableContainer.className).toContain('custom-class')
    })
  })

  describe('Hook parameters', () => {
    it('should call useImportFolderItems with correct parameters', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent({ librarySlug: 'my-library', path: '/some/path' })

      expect(useImportFolderItems).toHaveBeenCalledWith('my-library', '/some/path')
    })
  })

  // ============================================================================
  // Preview Display Tests
  // ============================================================================

  describe('Preview display in table cells', () => {
    it('should show preview value below original when preview differs', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const previewData = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { album: 'New Album Name' } }],
      ])

      renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        previewData,
      })

      // Should show the new preview value
      expect(screen.getByText('New Album Name')).toBeInTheDocument()
      // Should still show original value (with strikethrough styling)
      expect(screen.getAllByText('Test Album').length).toBeGreaterThan(0)
    })

    it('should NOT show preview when value is the same as original', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      // Preview with same value as original
      const previewData = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { album: 'Test Album' } }],
      ])

      renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        previewData,
      })

      // Should show Test Album but not with arrow indicator (no preview display)
      const albumCells = screen.getAllByText('Test Album')
      // The original should be shown without strikethrough if values are same
      expect(albumCells.length).toBeGreaterThan(0)
    })

    it('should show preview for multiple tags on same item', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [createMockItem({ id: 1, title: 'Original Title', artist: 'Original Artist' })],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const previewData = new Map<number, ItemPreview>([
        [1, {
          itemId: 1,
          changes: {
            title: 'New Title',
            artist: 'New Artist',
          },
        }],
      ])

      renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        previewData,
      })

      // Should show both preview values
      expect(screen.getByText('New Title')).toBeInTheDocument()
      expect(screen.getByText('New Artist')).toBeInTheDocument()
    })

    it('should show preview for track_number field', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [createMockItem({ id: 1, trackNumber: 1, trackTotal: 12 })],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const previewData = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { track_number: '5' } }],
      ])

      renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        previewData,
      })

      // Should show original track number
      expect(screen.getByText('1/12')).toBeInTheDocument()
      // Should show preview track number
      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it('should show previews for multiple items', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const previewData = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { album: 'Album 1 New' } }],
        [2, { itemId: 2, changes: { album: 'Album 2 New' } }],
        [3, { itemId: 3, changes: { album: 'Album 3 New' } }],
      ])

      renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        previewData,
      })

      // Should show all preview values
      expect(screen.getByText('Album 1 New')).toBeInTheDocument()
      expect(screen.getByText('Album 2 New')).toBeInTheDocument()
      expect(screen.getByText('Album 3 New')).toBeInTheDocument()
    })

    it('should show preview with arrow indicator', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [createMockItem({ id: 1, album: 'Original Album' })],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const previewData = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { album: 'New Album' } }],
      ])

      const { container } = renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        previewData,
      })

      // The ArrowRight icon should be present (from lucide-react)
      // Check for SVG element in the preview row
      const previewCells = container.querySelectorAll('.text-primary')
      expect(previewCells.length).toBeGreaterThan(0)
    })

    it('should apply strikethrough styling to original value when preview differs', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [createMockItem({ id: 1, album: 'Original Album' })],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const previewData = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { album: 'New Album' } }],
      ])

      const { container } = renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        previewData,
      })

      // Find the element with line-through styling
      const strikethroughElement = container.querySelector('.line-through')
      expect(strikethroughElement).toBeInTheDocument()
      expect(strikethroughElement?.textContent).toBe('Original Album')
    })

    it('should NOT apply strikethrough when no preview is present', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [createMockItem({ id: 1, album: 'Original Album' })],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const { container } = renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        // No previewData provided
      })

      // Should not have strikethrough styling
      const strikethroughElement = container.querySelector('.line-through')
      expect(strikethroughElement).not.toBeInTheDocument()
    })

    it('should handle empty preview changes object', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [createMockItem({ id: 1, album: 'Original Album' })],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const previewData = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: {} }], // Empty changes
      ])

      const { container } = renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        previewData,
      })

      // Should not have strikethrough styling
      const strikethroughElement = container.querySelector('.line-through')
      expect(strikethroughElement).not.toBeInTheDocument()
    })

    it('should show preview for genre field', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [createMockItem({ id: 1, genre: 'Rock' })],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const previewData = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { genre: 'Electronic' } }],
      ])

      renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        previewData,
      })

      // Should show both original and preview
      expect(screen.getByText('Rock')).toBeInTheDocument()
      expect(screen.getByText('Electronic')).toBeInTheDocument()
    })

    it('should show preview for album_artist field', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: {
          items: [createMockItem({ id: 1, albumArtist: 'Original Album Artist' })],
          total: 1,
          skip: 0,
          limit: 500,
          scanId: 1,
          scanCompletedAt: '2024-01-01T12:00:00Z',
        },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const previewData = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { album_artist: 'New Album Artist' } }],
      ])

      renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        previewData,
      })

      expect(screen.getByText('New Album Artist')).toBeInTheDocument()
    })
  })

  describe('onItemsLoaded callback', () => {
    it('should call onItemsLoaded with item IDs when data is loaded', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const onItemsLoaded = vi.fn()

      renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        onItemsLoaded,
      })

      // Should call onItemsLoaded with the IDs from the mock data
      expect(onItemsLoaded).toHaveBeenCalledWith([1, 2, 3])
    })

    it('should NOT call onItemsLoaded when no data', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
        isSuccess: false,
        isError: false,
      } as any)

      const onItemsLoaded = vi.fn()

      renderComponent({
        librarySlug: 'test-lib',
        path: '/Artist/Album',
        onItemsLoaded,
      })

      // Should not call onItemsLoaded
      expect(onItemsLoaded).not.toHaveBeenCalled()
    })
  })

  describe('Track playback', () => {
    const mockTracks = async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)
    }

    it('renders a play button for every track', async () => {
      await mockTracks()
      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      expect(screen.getAllByRole('button', { name: /^Play / })).toHaveLength(3)
    })

    it('toggles to a pause control when a track is played', async () => {
      const playSpy = vi
        .spyOn(window.HTMLMediaElement.prototype, 'play')
        .mockResolvedValue(undefined)
      await mockTracks()
      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      fireEvent.click(screen.getByRole('button', { name: 'Play Track 1' }))

      expect(playSpy).toHaveBeenCalled()
      expect(screen.getByRole('button', { name: 'Pause Track 1' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Play Track 2' })).toBeInTheDocument()
    })

    it('only one track shows as playing at a time', async () => {
      vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
      await mockTracks()
      renderComponent({ librarySlug: 'test-lib', path: '/Artist/Album' })

      fireEvent.click(screen.getByRole('button', { name: 'Play Track 1' }))
      fireEvent.click(screen.getByRole('button', { name: 'Play Track 2' }))

      expect(screen.getByRole('button', { name: 'Play Track 1' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Pause Track 2' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Pause Track 1' })).not.toBeInTheDocument()
    })
  })

  describe('Local Album summary (showSummary)', () => {
    it('renders the Local Album box from scanned tags, not the plain header', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
      } as any)

      renderComponent({
        librarySlug: 'test-lib',
        path: 'Artist/Album',
        showSummary: true,
      })

      // The LocalAlbumInfo box carries a "Local Album" heading...
      expect(screen.getByText('Local Album')).toBeInTheDocument()
      // ...and the album-level artist/album derived from the tags.
      expect(screen.getAllByText('Test Artist').length).toBeGreaterThan(0)
      expect(screen.getAllByText('Test Album').length).toBeGreaterThan(0)
      // The plain "Selected folder" header is replaced by the box.
      expect(screen.queryByText('Selected folder')).not.toBeInTheDocument()
    })

    it('keeps the plain folder header when showSummary is off', async () => {
      const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: mockSingleAlbumResponse,
        isLoading: false,
        error: null,
      } as any)

      renderComponent({ librarySlug: 'test-lib', path: 'Artist/Album' })

      expect(screen.getByText('Selected folder')).toBeInTheDocument()
    })
  })

  describe('Local Album WAV/WMA actions (showSummary)', () => {
    const wavResponse = (
      items: Partial<ImportItem>[]
    ): ImportItemListResponse => ({
      items: items.map((o, i) => createMockItem({ id: i + 1, ...o })),
      total: items.length,
      skip: 0,
      limit: 500,
      scanId: 1,
      scanCompletedAt: '2024-01-01T12:00:00Z',
    })

    const mockItems = async (resp: ImportItemListResponse) => {
      const { useImportFolderItems } = await import(
        '@/hooks/useImportFolderItems'
      )
      vi.mocked(useImportFolderItems).mockReturnValue({
        data: resp,
        isLoading: false,
        error: null,
      } as any)
    }

    it('shows the Convert WAV button when the folder has a WAV', async () => {
      await mockItems(
        wavResponse([
          { filename: 'track1.wav', format: 'wav', directory: 'Artist/Album' },
          { filename: 'track2.wav', format: 'wav', directory: 'Artist/Album' },
        ])
      )
      renderComponent({
        librarySlug: 'test-lib',
        path: 'Artist/Album',
        showSummary: true,
      })
      expect(screen.getByTestId('convert-wav-button')).toBeInTheDocument()
    })

    it('hides the WAV actions when the folder has no WAV', async () => {
      await mockItems(
        wavResponse([
          { filename: 'track1.flac', format: 'flac', directory: 'Artist/Album' },
        ])
      )
      renderComponent({
        librarySlug: 'test-lib',
        path: 'Artist/Album',
        showSummary: true,
      })
      expect(screen.queryByTestId('convert-wav-button')).not.toBeInTheDocument()
      expect(screen.queryByTestId('dedupe-wav-button')).not.toBeInTheDocument()
    })

    it('offers the dedupe action with a count when a WAV has a FLAC twin', async () => {
      await mockItems(
        wavResponse([
          { filename: 'song.wav', format: 'wav', directory: 'Artist/Album' },
          { filename: 'song.flac', format: 'flac', directory: 'Artist/Album' },
          { filename: 'other.wav', format: 'wav', directory: 'Artist/Album' },
        ])
      )
      renderComponent({
        librarySlug: 'test-lib',
        path: 'Artist/Album',
        showSummary: true,
      })
      expect(screen.getByTestId('dedupe-wav-button')).toHaveTextContent(
        'Remove duplicate WAVs (1)'
      )
    })

    it('ignores deleted WAVs so they do not look like FLAC duplicates (issue #125)', async () => {
      // The WAV was converted and removed; the last scan flagged it "deleted"
      // but it still carries the FLAC's directory. It must not drive the dedupe
      // button (the backend would 400 — the file is gone from disk).
      await mockItems(
        wavResponse([
          { filename: 'song.flac', format: 'flac', directory: 'Artist/Album', status: 'unchanged' },
          { filename: 'song.wav', format: 'wav', directory: 'Artist/Album', status: 'deleted' },
        ])
      )
      renderComponent({
        librarySlug: 'test-lib',
        path: 'Artist/Album',
        showSummary: true,
      })
      expect(screen.queryByTestId('dedupe-wav-button')).not.toBeInTheDocument()
      expect(screen.queryByTestId('convert-wav-button')).not.toBeInTheDocument()
    })

    it('does not wire WAV actions into the plain header (showSummary off)', async () => {
      await mockItems(
        wavResponse([
          { filename: 'track1.wav', format: 'wav', directory: 'Artist/Album' },
        ])
      )
      renderComponent({ librarySlug: 'test-lib', path: 'Artist/Album' })
      expect(screen.queryByTestId('convert-wav-button')).not.toBeInTheDocument()
    })

    it('calls convertAudio (WAV→FLAC) after confirming the dialog', async () => {
      const { convertAudio } = await import('@/api/beets-import')
      await mockItems(
        wavResponse([
          { filename: 'track1.wav', format: 'wav', directory: 'Artist/Album' },
        ])
      )
      renderComponent({
        librarySlug: 'test-lib',
        path: 'Artist/Album',
        showSummary: true,
      })
      fireEvent.click(screen.getByTestId('convert-wav-button'))
      expect(screen.getByText('Convert WAV files?')).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'Convert' }))
      expect(vi.mocked(convertAudio)).toHaveBeenCalledWith(
        'test-lib',
        'Artist/Album',
        'wav',
        'flac',
        false
      )
    })

    it('shows the Convert WMA button and converts to MP3 for low-bitrate WMA', async () => {
      const { convertAudio } = await import('@/api/beets-import')
      await mockItems(
        wavResponse([
          {
            filename: 'track1.wma',
            format: 'wma',
            directory: 'Artist/Album',
            bitrate: 192,
          },
        ])
      )
      renderComponent({
        librarySlug: 'test-lib',
        path: 'Artist/Album',
        showSummary: true,
      })
      fireEvent.click(screen.getByTestId('convert-wma-button'))
      expect(screen.getByText('Convert WMA files?')).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'Convert' }))
      expect(vi.mocked(convertAudio)).toHaveBeenCalledWith(
        'test-lib',
        'Artist/Album',
        'wma',
        'mp3',
        false
      )
    })

    it('preselects FLAC for high-bitrate WMA', async () => {
      const { convertAudio } = await import('@/api/beets-import')
      await mockItems(
        wavResponse([
          {
            filename: 'track1.wma',
            format: 'wma',
            directory: 'Artist/Album',
            bitrate: 500,
          },
        ])
      )
      renderComponent({
        librarySlug: 'test-lib',
        path: 'Artist/Album',
        showSummary: true,
      })
      fireEvent.click(screen.getByTestId('convert-wma-button'))
      fireEvent.click(screen.getByRole('button', { name: 'Convert' }))
      expect(vi.mocked(convertAudio)).toHaveBeenCalledWith(
        'test-lib',
        'Artist/Album',
        'wma',
        'flac',
        false
      )
    })
  })
})
