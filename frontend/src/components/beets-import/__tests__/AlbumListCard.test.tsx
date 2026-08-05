import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AlbumListCard from '../AlbumListCard'
import type { AlbumListItem } from '@/types/beets-import'

describe('AlbumListCard', () => {
  const createMockAlbum = (overrides: Partial<AlbumListItem> = {}): AlbumListItem => ({
    id: '1',
    path: '/import/Album 1',
    name: 'Album 1',
    artist: 'Test Artist',
    album: 'Test Album',
    stage: 'none',
    isAnalyzing: false,
    ...overrides,
  })

  const defaultProps = {
    albums: [] as AlbumListItem[],
    selectedPath: null,
    onAlbumSelect: vi.fn(),
    onAnalyzeClick: vi.fn(),
  }

  describe('Album list rendering', () => {
    it('should render card header with title', () => {
      render(<AlbumListCard {...defaultProps} />)

      expect(screen.getByText('Albums')).toBeInTheDocument()
    })

    it('should show instruction text', () => {
      render(<AlbumListCard {...defaultProps} />)

      expect(
        screen.getByText(
          /Click an album to view details\. Click the disc to analyze, the\s+download icon to import as-is, the trash icon to delete\./
        )
      ).toBeInTheDocument()
    })

    it('should render album list with album names', () => {
      const albums = [
        createMockAlbum({ id: '1', path: '/import/Album 1', name: 'Album 1' }),
        createMockAlbum({ id: '2', path: '/import/Album 2', name: 'Album 2' }),
      ]

      render(<AlbumListCard {...defaultProps} albums={albums} />)

      expect(screen.getByText('Album 1')).toBeInTheDocument()
      expect(screen.getByText('Album 2')).toBeInTheDocument()
    })

    it('should display artist and album metadata', () => {
      const albums = [
        createMockAlbum({
          artist: 'Pink Floyd',
          album: 'The Dark Side of the Moon',
        }),
      ]

      render(<AlbumListCard {...defaultProps} albums={albums} />)

      expect(screen.getByText('Pink Floyd - The Dark Side of the Moon')).toBeInTheDocument()
    })

    it('should display only artist when album is null', () => {
      const albums = [
        createMockAlbum({
          artist: 'Pink Floyd',
          album: null,
        }),
      ]

      render(<AlbumListCard {...defaultProps} albums={albums} />)

      expect(screen.getByText('Pink Floyd')).toBeInTheDocument()
    })

    it('should display only album when artist is null', () => {
      const albums = [
        createMockAlbum({
          artist: null,
          album: 'The Dark Side of the Moon',
        }),
      ]

      render(<AlbumListCard {...defaultProps} albums={albums} />)

      expect(screen.getByText('The Dark Side of the Moon')).toBeInTheDocument()
    })

    it('should show album count badge when albums exist', () => {
      const albums = [
        createMockAlbum({ id: '1', path: '/import/Album 1', name: 'Album 1' }),
        createMockAlbum({ id: '2', path: '/import/Album 2', name: 'Album 2' }),
        createMockAlbum({ id: '3', path: '/import/Album 3', name: 'Album 3' }),
      ]

      render(<AlbumListCard {...defaultProps} albums={albums} />)

      expect(screen.getByText('3')).toBeInTheDocument()
    })

    it('should not show count badge when albums is empty', () => {
      render(<AlbumListCard {...defaultProps} albums={[]} />)

      // Only "Albums" text should be present, no number badge
      const albumsHeader = screen.getByText('Albums')
      expect(albumsHeader).toBeInTheDocument()
      // Check there's no badge sibling
      expect(screen.queryByText('0')).not.toBeInTheDocument()
    })
  })

  describe('Empty state', () => {
    it('should show empty state when no albums', () => {
      render(<AlbumListCard {...defaultProps} albums={[]} />)

      expect(
        screen.getByText('No album folders found in the import directory.')
      ).toBeInTheDocument()
      expect(
        screen.getByText('Run a scan to discover albums, or upload files to the import folder.')
      ).toBeInTheDocument()
    })
  })

  describe('Loading state', () => {
    it('should show skeleton when loading', () => {
      const { container } = render(<AlbumListCard {...defaultProps} isLoading />)

      // Should show animated pulse elements
      const skeletonElements = container.querySelectorAll('.animate-pulse')
      expect(skeletonElements.length).toBeGreaterThan(0)
    })

    it('should not show albums list when loading', () => {
      const albums = [createMockAlbum()]

      render(<AlbumListCard {...defaultProps} albums={albums} isLoading />)

      expect(screen.queryByText('Album 1')).not.toBeInTheDocument()
    })
  })

  describe('Error state', () => {
    it('should show error message when error is provided', () => {
      render(
        <AlbumListCard
          {...defaultProps}
          error="Failed to load albums: Network error"
        />
      )

      expect(screen.getByText('Failed to load albums: Network error')).toBeInTheDocument()
    })

    it('should not show albums when error is present', () => {
      const albums = [createMockAlbum()]

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          error="Something went wrong"
        />
      )

      expect(screen.queryByText('Album 1')).not.toBeInTheDocument()
    })
  })

  describe('Album selection', () => {
    it('should call onAlbumSelect when album is clicked', () => {
      const onAlbumSelect = vi.fn()
      const albums = [createMockAlbum({ path: '/import/test-album' })]

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          onAlbumSelect={onAlbumSelect}
        />
      )

      const albumRow = screen.getByRole('button', { name: /Album 1/i })
      fireEvent.click(albumRow)

      expect(onAlbumSelect).toHaveBeenCalledWith('/import/test-album')
    })

    it('should highlight selected album', () => {
      const albums = [
        createMockAlbum({ id: '1', path: '/import/Album 1', name: 'Album 1' }),
        createMockAlbum({ id: '2', path: '/import/Album 2', name: 'Album 2' }),
      ]

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          selectedPath="/import/Album 1"
        />
      )

      // Find album rows by their text content within buttons
      const albumRows = screen.getAllByRole('button')
      const album1Row = albumRows.find((row) => row.textContent?.includes('Album 1'))
      const album2Row = albumRows.find((row) => row.textContent?.includes('Album 2'))

      expect(album1Row).toHaveAttribute('aria-selected', 'true')
      expect(album2Row).toHaveAttribute('aria-selected', 'false')
    })

    it('should support keyboard navigation with Enter key', () => {
      const onAlbumSelect = vi.fn()
      const albums = [createMockAlbum({ path: '/import/test-album' })]

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          onAlbumSelect={onAlbumSelect}
        />
      )

      const albumRow = screen.getByRole('button', { name: /Album 1/i })
      fireEvent.keyDown(albumRow, { key: 'Enter' })

      expect(onAlbumSelect).toHaveBeenCalledWith('/import/test-album')
    })

    it('should support keyboard navigation with Space key', () => {
      const onAlbumSelect = vi.fn()
      const albums = [createMockAlbum({ path: '/import/test-album' })]

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          onAlbumSelect={onAlbumSelect}
        />
      )

      const albumRow = screen.getByRole('button', { name: /Album 1/i })
      fireEvent.keyDown(albumRow, { key: ' ' })

      expect(onAlbumSelect).toHaveBeenCalledWith('/import/test-album')
    })
  })

  describe('Analysis trigger', () => {
    it('should call onAnalyzeClick when disc icon is clicked', () => {
      const onAnalyzeClick = vi.fn()
      const albums = [createMockAlbum({ path: '/import/test-album', stage: 'none' })]

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          onAnalyzeClick={onAnalyzeClick}
        />
      )

      // Find the analyze button within the StageIndicator
      const analyzeButton = screen.getByRole('button', { name: 'Analyze album' })
      fireEvent.click(analyzeButton)

      expect(onAnalyzeClick).toHaveBeenCalledWith('/import/test-album')
    })

    it('should show spinner for album being analyzed', () => {
      const albums = [
        createMockAlbum({
          path: '/import/test-album',
          stage: 'none',
          isAnalyzing: true,
        }),
      ]

      render(<AlbumListCard {...defaultProps} albums={albums} />)

      // Should show analyzing spinner
      expect(screen.getByLabelText('Analyzing...')).toBeInTheDocument()
    })
  })

  describe('Stage indicator', () => {
    it('should show stage indicator for each album', () => {
      const albums = [
        createMockAlbum({ id: '1', stage: 'none' }),
        createMockAlbum({ id: '2', stage: 'analyzed' }),
      ]

      render(<AlbumListCard {...defaultProps} albums={albums} />)

      // First album should have "Analyze album" button
      expect(screen.getByRole('button', { name: 'Analyze album' })).toBeInTheDocument()

      // Second album should have "Re-analyze album" button
      expect(screen.getByRole('button', { name: 'Re-analyze album' })).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('should apply custom className', () => {
      const { container } = render(
        <AlbumListCard {...defaultProps} className="custom-class" />
      )

      expect(container.firstChild).toHaveClass('custom-class')
    })
  })

  describe('Queue status', () => {
    it('should show queue badge when album is queued', () => {
      const albums = [createMockAlbum({ path: '/import/album-1', stage: 'none' })]
      const queueStatus = { '/import/album-1': 3 }

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          queueStatus={queueStatus}
        />
      )

      // Queue badge should be visible with position
      const queueBadge = screen.getByTestId('queue-badge')
      expect(queueBadge).toBeInTheDocument()
      expect(queueBadge).toHaveTextContent('#3')
    })

    it('should show analyze button when album is not queued', () => {
      const albums = [createMockAlbum({ path: '/import/album-1', stage: 'none' })]
      const queueStatus = {} // Not queued

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          queueStatus={queueStatus}
        />
      )

      // Analyze button should be present
      expect(screen.getByRole('button', { name: 'Analyze album' })).toBeInTheDocument()
      expect(screen.queryByTestId('queue-badge')).not.toBeInTheDocument()
    })

    it('should apply amber styling to queued album row', () => {
      const albums = [createMockAlbum({ path: '/import/album-1', stage: 'none' })]
      const queueStatus = { '/import/album-1': 1 }

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          queueStatus={queueStatus}
        />
      )

      const albumRow = screen.getByTestId('album-list-item')
      // Should have amber styling for queued state
      expect(albumRow.className).toContain('amber')
    })

    it('should handle multiple queued albums with different positions', () => {
      const albums = [
        createMockAlbum({ id: '1', path: '/import/album-1', name: 'Album 1', stage: 'none' }),
        createMockAlbum({ id: '2', path: '/import/album-2', name: 'Album 2', stage: 'none' }),
        createMockAlbum({ id: '3', path: '/import/album-3', name: 'Album 3', stage: 'none' }),
      ]
      const queueStatus = {
        '/import/album-1': 1,
        '/import/album-3': 2,
      }

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          queueStatus={queueStatus}
        />
      )

      const queueBadges = screen.getAllByTestId('queue-badge')
      expect(queueBadges).toHaveLength(2)
      expect(queueBadges[0]).toHaveTextContent('#1')
      expect(queueBadges[1]).toHaveTextContent('#2')
    })

  })

  describe('Delete action', () => {
    it('should not render delete buttons without onDeleteAlbum', () => {
      const albums = [createMockAlbum()]

      render(<AlbumListCard {...defaultProps} albums={albums} />)

      expect(screen.queryByTestId('album-delete-button')).not.toBeInTheDocument()
    })

    it('should render a delete button per album when onDeleteAlbum is provided', () => {
      const albums = [
        createMockAlbum({ id: '1', path: '/import/Album 1', name: 'Album 1' }),
        createMockAlbum({ id: '2', path: '/import/Album 2', name: 'Album 2' }),
      ]

      render(
        <AlbumListCard {...defaultProps} albums={albums} onDeleteAlbum={vi.fn()} />
      )

      expect(screen.getAllByTestId('album-delete-button')).toHaveLength(2)
    })

    it('should open a confirmation dialog naming the album, without selecting the row', () => {
      const onAlbumSelect = vi.fn()
      const albums = [createMockAlbum({ name: 'Doomed Album' })]

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          onAlbumSelect={onAlbumSelect}
          onDeleteAlbum={vi.fn()}
        />
      )

      fireEvent.click(screen.getByTestId('album-delete-button'))

      expect(screen.getByText('Delete album')).toBeInTheDocument()
      // Album name appears in the row and again in the dialog description
      expect(screen.getAllByText('Doomed Album').length).toBeGreaterThanOrEqual(2)
      // Clicking the trash icon must not select the album row
      expect(onAlbumSelect).not.toHaveBeenCalled()
    })

    it('should call onDeleteAlbum with the album path only after confirmation', async () => {
      const onDeleteAlbum = vi.fn().mockResolvedValue(undefined)
      const albums = [createMockAlbum({ path: '/import/test-album' })]

      render(
        <AlbumListCard {...defaultProps} albums={albums} onDeleteAlbum={onDeleteAlbum} />
      )

      fireEvent.click(screen.getByTestId('album-delete-button'))
      expect(onDeleteAlbum).not.toHaveBeenCalled()

      fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

      expect(onDeleteAlbum).toHaveBeenCalledWith('/import/test-album')
      // Dialog closes after the promise resolves
      await screen.findByText('Album 1')
      expect(screen.queryByText('Delete album')).not.toBeInTheDocument()
    })

    it('should not call onDeleteAlbum when cancelled', () => {
      const onDeleteAlbum = vi.fn()
      const albums = [createMockAlbum()]

      render(
        <AlbumListCard {...defaultProps} albums={albums} onDeleteAlbum={onDeleteAlbum} />
      )

      fireEvent.click(screen.getByTestId('album-delete-button'))
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(onDeleteAlbum).not.toHaveBeenCalled()
    })

    it('should disable the delete button while the album is queued or analyzing', () => {
      const onDeleteAlbum = vi.fn()
      const albums = [
        createMockAlbum({ id: '1', path: '/import/a1', name: 'Analyzing', isAnalyzing: true }),
        createMockAlbum({ id: '2', path: '/import/a2', name: 'Queued' }),
      ]

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          onDeleteAlbum={onDeleteAlbum}
          queueStatus={{ '/import/a2': 1 }}
        />
      )

      const deleteButtons = screen.getAllByTestId('album-delete-button')
      expect(deleteButtons[0]).toBeDisabled()
      expect(deleteButtons[1]).toBeDisabled()

      fireEvent.click(deleteButtons[0])
      fireEvent.click(deleteButtons[1])
      expect(onDeleteAlbum).not.toHaveBeenCalled()
      expect(screen.queryByText('Delete album')).not.toBeInTheDocument()
    })

    it('should show an error and keep the dialog open when deletion fails', async () => {
      const onDeleteAlbum = vi.fn().mockRejectedValue(new Error('Folder not found'))
      const albums = [createMockAlbum()]

      render(
        <AlbumListCard {...defaultProps} albums={albums} onDeleteAlbum={onDeleteAlbum} />
      )

      fireEvent.click(screen.getByTestId('album-delete-button'))
      fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

      expect(await screen.findByText('Folder not found')).toBeInTheDocument()
      expect(screen.getByText('Delete album')).toBeInTheDocument()
    })
  })

  describe('Import as-is', () => {
    it('should not render the as-is button when onImportAsIs is not provided', () => {
      render(<AlbumListCard {...defaultProps} albums={[createMockAlbum()]} />)

      expect(
        screen.queryByTestId('album-import-as-is-button')
      ).not.toBeInTheDocument()
    })

    it('should call onImportAsIs with the album path without selecting the row', () => {
      const onImportAsIs = vi.fn()
      const onAlbumSelect = vi.fn()
      const albums = [createMockAlbum({ path: '/import/test-album' })]

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          onAlbumSelect={onAlbumSelect}
          onImportAsIs={onImportAsIs}
        />
      )

      fireEvent.click(screen.getByTestId('album-import-as-is-button'))

      expect(onImportAsIs).toHaveBeenCalledWith('/import/test-album')
      // Clicking the import icon must not select the album row
      expect(onAlbumSelect).not.toHaveBeenCalled()
    })

    it('should disable the as-is button while importing, analyzing, or queued', () => {
      const onImportAsIs = vi.fn()
      const albums = [
        createMockAlbum({ id: '1', path: '/import/a1', name: 'Analyzing', isAnalyzing: true }),
        createMockAlbum({ id: '2', path: '/import/a2', name: 'Queued' }),
        createMockAlbum({ id: '3', path: '/import/a3', name: 'Idle' }),
      ]

      render(
        <AlbumListCard
          {...defaultProps}
          albums={albums}
          onImportAsIs={onImportAsIs}
          isImporting
          queueStatus={{ '/import/a2': 1 }}
        />
      )

      const buttons = screen.getAllByTestId('album-import-as-is-button')
      // isImporting disables every button regardless of stage
      buttons.forEach((btn) => expect(btn).toBeDisabled())

      buttons.forEach((btn) => fireEvent.click(btn))
      expect(onImportAsIs).not.toHaveBeenCalled()
    })
  })

  describe('Folder grouping (issue #80)', () => {
    it('renders no folder heading when albums sit in the import root', () => {
      const albums = [
        createMockAlbum({ id: '1', name: 'Album 1', folder: null }),
        createMockAlbum({ id: '2', name: 'Album 2' }), // folder undefined → root
      ]

      render(<AlbumListCard {...defaultProps} albums={albums} />)

      expect(screen.queryByTestId('album-folder-heading')).not.toBeInTheDocument()
      expect(screen.getByText('Album 1')).toBeInTheDocument()
      expect(screen.getByText('Album 2')).toBeInTheDocument()
    })

    it('groups albums under their parent folder heading', () => {
      const albums = [
        createMockAlbum({ id: '1', name: 'Album A', folder: 'Artist One' }),
        createMockAlbum({ id: '2', name: 'Album B', folder: 'Artist One' }),
        createMockAlbum({ id: '3', name: 'Album C', folder: 'Artist Two' }),
      ]

      render(<AlbumListCard {...defaultProps} albums={albums} />)

      const headings = screen.getAllByTestId('album-folder-heading')
      expect(headings).toHaveLength(2)
      expect(headings[0]).toHaveTextContent('Artist One')
      expect(headings[1]).toHaveTextContent('Artist Two')
      // Two groups: Artist One has 2 albums, Artist Two has 1.
      const groups = screen.getAllByTestId('album-folder-group')
      expect(groups).toHaveLength(2)
    })

    it('clusters albums of the same folder together while preserving order', () => {
      // Interleaved input order; same-folder albums must collapse to one group.
      const albums = [
        createMockAlbum({ id: '1', name: 'Album A', folder: 'Artist One' }),
        createMockAlbum({ id: '2', name: 'Album C', folder: 'Artist Two' }),
        createMockAlbum({ id: '3', name: 'Album B', folder: 'Artist One' }),
      ]

      render(<AlbumListCard {...defaultProps} albums={albums} />)

      const groups = screen.getAllByTestId('album-folder-group')
      expect(groups).toHaveLength(2)
      // First group keeps the folder of the first-seen album.
      expect(groups[0]).toHaveTextContent('Artist One')
      expect(groups[0]).toHaveTextContent('Album A')
      expect(groups[0]).toHaveTextContent('Album B')
    })
  })

  describe('Analyze All header action', () => {
    it('renders the Analyze All button and fires onAnalyzeAll', () => {
      const onAnalyzeAll = vi.fn()
      render(
        <AlbumListCard
          {...defaultProps}
          albums={[createMockAlbum({})]}
          onAnalyzeAll={onAnalyzeAll}
        />
      )

      const button = screen.getByTestId('analyze-all-button')
      expect(button).toBeEnabled()
      fireEvent.click(button)
      expect(onAnalyzeAll).toHaveBeenCalledTimes(1)
    })

    it('disables Analyze All when there are no albums', () => {
      render(
        <AlbumListCard {...defaultProps} albums={[]} onAnalyzeAll={vi.fn()} />
      )
      expect(screen.getByTestId('analyze-all-button')).toBeDisabled()
    })

    it('shows the queue indicator only when there is queue activity', () => {
      const { rerender } = render(
        <AlbumListCard {...defaultProps} albums={[createMockAlbum({})]} />
      )
      expect(screen.queryByTestId('queue-depth-indicator')).not.toBeInTheDocument()

      rerender(
        <AlbumListCard
          {...defaultProps}
          albums={[createMockAlbum({})]}
          queueDepth={2}
          activeCount={1}
        />
      )
      const indicator = screen.getByTestId('queue-depth-indicator')
      expect(indicator).toHaveTextContent('2 queued')
      expect(indicator).toHaveTextContent('1 analyzing')
    })
  })

  describe('Folder actions and selection', () => {
    const folderAlbums = [
      createMockAlbum({ id: '1', name: 'Album A', folder: 'Artist One' }),
      createMockAlbum({ id: '2', name: 'Album B', folder: 'Artist One' }),
    ]

    it('collapses and expands a folder via the toggle', () => {
      render(<AlbumListCard {...defaultProps} albums={folderAlbums} />)

      expect(screen.getByText('Album A')).toBeInTheDocument()
      fireEvent.click(screen.getByTestId('album-folder-toggle'))
      expect(screen.queryByText('Album A')).not.toBeInTheDocument()
      fireEvent.click(screen.getByTestId('album-folder-toggle'))
      expect(screen.getByText('Album A')).toBeInTheDocument()
    })

    it('selecting the folder heading calls onFolderSelect with the folder', () => {
      const onFolderSelect = vi.fn()
      render(
        <AlbumListCard
          {...defaultProps}
          albums={folderAlbums}
          onFolderSelect={onFolderSelect}
        />
      )

      fireEvent.click(screen.getByTestId('album-folder-select'))
      expect(onFolderSelect).toHaveBeenCalledWith('Artist One')
    })

    it('the folder analyze action calls onAnalyzeFolder', () => {
      const onAnalyzeFolder = vi.fn()
      render(
        <AlbumListCard
          {...defaultProps}
          albums={folderAlbums}
          onAnalyzeFolder={onAnalyzeFolder}
        />
      )

      const button = screen.getByTestId('album-folder-analyze-button')
      // Carries the re-analyze affordance matching the per-album disc.
      expect(button).toHaveAttribute(
        'aria-label',
        'Re-analyze all albums in folder Artist One'
      )
      fireEvent.click(button)
      expect(onAnalyzeFolder).toHaveBeenCalledWith('Artist One')
    })

    it('the folder delete action confirms before calling onDeleteFolder', async () => {
      const onDeleteFolder = vi.fn().mockResolvedValue(undefined)
      render(
        <AlbumListCard
          {...defaultProps}
          albums={folderAlbums}
          onDeleteFolder={onDeleteFolder}
        />
      )

      // Opening the action shows a confirmation, not an immediate delete.
      fireEvent.click(screen.getByTestId('album-folder-delete-button'))
      expect(onDeleteFolder).not.toHaveBeenCalled()
      expect(screen.getByText('Delete folder')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
      expect(onDeleteFolder).toHaveBeenCalledWith('Artist One')
    })

    it('highlights the selected folder', () => {
      render(
        <AlbumListCard
          {...defaultProps}
          albums={folderAlbums}
          selectedFolder="Artist One"
          onFolderSelect={vi.fn()}
        />
      )
      expect(screen.getByTestId('album-folder-select')).toHaveAttribute(
        'aria-pressed',
        'true'
      )
    })
  })

  describe('Icon legend and multi-disc marker', () => {
    it('renders the icon legend', () => {
      render(<AlbumListCard {...defaultProps} albums={[createMockAlbum({})]} />)
      const legend = screen.getByTestId('album-list-legend')
      expect(legend).toHaveTextContent('Album')
      expect(legend).toHaveTextContent('Multi-disc')
      expect(legend).toHaveTextContent('Folder')
    })

    it('marks a multi-disc album with a distinct icon', () => {
      render(
        <AlbumListCard
          {...defaultProps}
          albums={[
            createMockAlbum({ id: '1', name: 'Single Disc', isMultiDisc: false }),
            createMockAlbum({ id: '2', name: 'Multi Disc', isMultiDisc: true }),
          ]}
        />
      )
      // Scope to the album rows (the legend also carries a Disc3). The
      // multi-disc row uses lucide's Disc3 ("lucide-disc3"); the single-disc
      // row uses Music ("lucide-music").
      const rows = screen.getAllByTestId('album-list-item')
      const singleRow = rows.find((r) => r.textContent?.includes('Single Disc'))!
      const multiRow = rows.find((r) => r.textContent?.includes('Multi Disc'))!
      expect(multiRow.querySelector('.lucide-disc3')).toBeInTheDocument()
      expect(singleRow.querySelector('.lucide-disc3')).not.toBeInTheDocument()
      expect(singleRow.querySelector('.lucide-music')).toBeInTheDocument()
    })
  })

  describe('Convert spinner (per-album, issue #130)', () => {
    const twoAlbums = [
      createMockAlbum({ id: '1', path: '/import/Album 1', name: 'Album 1' }),
      createMockAlbum({ id: '2', path: '/import/Album 2', name: 'Album 2' }),
    ]

    it('shows a converting spinner only on albums with an active job', () => {
      render(
        <AlbumListCard
          {...defaultProps}
          albums={twoAlbums}
          convertStatus={{ '/import/Album 1': 'running' }}
        />
      )

      const rows = screen.getAllByTestId('album-list-item')
      const row1 = rows.find((r) => r.textContent?.includes('Album 1'))!
      const row2 = rows.find((r) => r.textContent?.includes('Album 2'))!

      // Only the converting album carries the spinner — proving it's keyed
      // per-album, not tied to whichever album is selected.
      expect(
        row1.querySelector('[data-testid="album-converting-spinner"]')
      ).toBeInTheDocument()
      expect(
        row2.querySelector('[data-testid="album-converting-spinner"]')
      ).not.toBeInTheDocument()
    })

    it('labels a queued album distinctly from a running one', () => {
      render(
        <AlbumListCard
          {...defaultProps}
          albums={twoAlbums}
          convertStatus={{
            '/import/Album 1': 'running',
            '/import/Album 2': 'queued',
          }}
        />
      )

      expect(screen.getByLabelText('Converting')).toBeInTheDocument()
      expect(screen.getByLabelText('Queued to convert')).toBeInTheDocument()
    })

    it('shows no spinner when nothing is converting', () => {
      render(<AlbumListCard {...defaultProps} albums={twoAlbums} />)
      expect(
        screen.queryByTestId('album-converting-spinner')
      ).not.toBeInTheDocument()
    })
  })
})
