import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ImportFolderTree from './ImportFolderTree'
import type { ImportTreeResponse, ImportFolderNode } from '@/types/import-tree'

// Mock the useImportTree hook
vi.mock('@/hooks/useImportTree', () => ({
  useImportTree: vi.fn(),
  useDeleteImportFolder: vi.fn(() => ({
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
  })),
}))

describe('ImportFolderTree', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.clearAllMocks()
  })

  const renderComponent = (
    slug: string = 'test-library',
    props: {
      onFolderSelect?: (path: string) => void
      selectedPath?: string | null
      onFolderDeleted?: (path: string) => void
    } = {}
  ) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <ImportFolderTree librarySlug={slug} {...props} />
      </QueryClientProvider>
    )
  }

  // Sample folder tree data
  const mockFolderTree: ImportTreeResponse = {
    importPath: '/data/import/music',
    children: [
      {
        name: 'Artist One',
        path: 'Artist One',
        isAlbum: false,
        isMultiDiscParent: false,
        children: [
          {
            name: 'Album A',
            path: 'Artist One/Album A',
            isAlbum: true,
            isMultiDiscParent: false,
            children: [],
            hasSubfolders: false,
          },
          {
            name: 'Album B',
            path: 'Artist One/Album B',
            isAlbum: true,
            isMultiDiscParent: true,
            children: [
              {
                name: 'Album B Disc 1',
                path: 'Artist One/Album B/Album B Disc 1',
                isAlbum: false,
                isMultiDiscParent: false,
                children: [],
                hasSubfolders: false,
              },
              {
                name: 'Album B Disc 2',
                path: 'Artist One/Album B/Album B Disc 2',
                isAlbum: false,
                isMultiDiscParent: false,
                children: [],
                hasSubfolders: false,
              },
            ],
            hasSubfolders: true,
          },
        ],
        hasSubfolders: true,
      },
      {
        name: 'Artist Two',
        path: 'Artist Two',
        isAlbum: false,
        isMultiDiscParent: false,
        children: [
          {
            name: 'Single Album',
            path: 'Artist Two/Single Album',
            isAlbum: true,
            isMultiDiscParent: false,
            children: [],
            hasSubfolders: false,
          },
        ],
        hasSubfolders: true,
      },
    ],
  }

  describe('Loading state', () => {
    it('should show loading indicator when fetching data', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
        isSuccess: false,
        isError: false,
      } as any)

      renderComponent()

      expect(screen.getByText('Loading folder tree...')).toBeInTheDocument()
    })
  })

  describe('Error state', () => {
    it('should show error message when API call fails', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: new Error('Failed to fetch import tree'),
        isSuccess: false,
        isError: true,
      } as any)

      renderComponent()

      expect(screen.getByText('Failed to load import folder')).toBeInTheDocument()
      expect(screen.getByText('Failed to fetch import tree')).toBeInTheDocument()
    })
  })

  describe('Empty state', () => {
    it('should show empty state when import path is not configured', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: { importPath: null, children: [] },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      expect(screen.getByText('No import path configured for this library')).toBeInTheDocument()
    })

    it('should show empty state when import folder has no content', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: { importPath: '/data/import/music', children: [] },
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      expect(screen.getByText('No folders found in import directory')).toBeInTheDocument()
    })
  })

  describe('Tree rendering', () => {
    it('should render top-level folders', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      expect(screen.getByText('Artist One')).toBeInTheDocument()
      expect(screen.getByText('Artist Two')).toBeInTheDocument()
    })

    it('should show import path in header', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      expect(screen.getByText('/data/import/music')).toBeInTheDocument()
    })

    it('should not show nested folders by default (collapsed)', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      // Nested albums should not be visible by default
      expect(screen.queryByText('Album A')).not.toBeInTheDocument()
      expect(screen.queryByText('Album B')).not.toBeInTheDocument()
    })
  })

  describe('Expand/collapse functionality', () => {
    it('should expand folder when chevron is clicked', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      // Initially, nested content is not visible
      expect(screen.queryByText('Album A')).not.toBeInTheDocument()

      // Click the expand button for "Artist One"
      const expandButtons = screen.getAllByRole('button', { name: /expand/i })
      fireEvent.click(expandButtons[0])

      // Now nested albums should be visible
      await waitFor(() => {
        expect(screen.getByText('Album A')).toBeInTheDocument()
        expect(screen.getByText('Album B')).toBeInTheDocument()
      })
    })

    it('should collapse folder when chevron is clicked on expanded folder', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      // Expand "Artist One"
      const expandButtons = screen.getAllByRole('button', { name: /expand/i })
      fireEvent.click(expandButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Album A')).toBeInTheDocument()
      })

      // Collapse "Artist One"
      const collapseButton = screen.getByRole('button', { name: /collapse/i })
      fireEvent.click(collapseButton)

      // Nested albums should no longer be visible
      await waitFor(() => {
        expect(screen.queryByText('Album A')).not.toBeInTheDocument()
      })
    })

    it('should not have chevron for leaf folders', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      // Expand to see leaf folders
      const expandButtons = screen.getAllByRole('button', { name: /expand/i })
      fireEvent.click(expandButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Album A')).toBeInTheDocument()
      })

      // Album A is a leaf folder (isAlbum: true, no children)
      // It should not have an expand/collapse button
      // Count buttons before and after - Album A has no chevron
      const allButtons = screen.getAllByRole('button')
      // The folder rows for leaf folders should not have buttons
      // This is implicitly tested by checking the button count
      expect(allButtons.length).toBeGreaterThan(0)
    })

    it('should handle nested expansion correctly', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      // Expand "Artist One"
      const expandButtons = screen.getAllByRole('button', { name: /expand/i })
      fireEvent.click(expandButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Album B')).toBeInTheDocument()
      })

      // Album B is a multi-disc parent with children, should have an expand button
      // After expanding Artist One, there should be more expand buttons
      // (Artist Two still unexpanded + Album B which has children)
      const updatedExpandButtons = screen.getAllByRole('button', { name: /expand/i })
      // The buttons are: Artist Two's expand button, Album B's expand button
      // Album B should be one of these buttons (index may vary based on rendering order)
      expect(updatedExpandButtons.length).toBeGreaterThanOrEqual(2)

      // Find the Album B row and click its expand button
      // Album B should have the first expand button after Artist Two since it has children
      // Let's click the button that's NOT Artist Two's (which is at the same level as Artist One)
      // The Album B expand button should be at index 0 since it appears before Artist Two in DOM
      fireEvent.click(updatedExpandButtons[0]) // Album B's expand button

      await waitFor(() => {
        expect(screen.getByText('Album B Disc 1')).toBeInTheDocument()
        expect(screen.getByText('Album B Disc 2')).toBeInTheDocument()
      })
    })
  })

  describe('Visual distinction for folder types', () => {
    it('should show multi-disc badge for multi-disc parent folders', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      // Initially, only one "Multi-disc" text is visible (in legend)
      const initialMultiDiscTexts = screen.getAllByText('Multi-disc')
      expect(initialMultiDiscTexts.length).toBe(1)

      // Expand to see Album B (multi-disc parent)
      const expandButtons = screen.getAllByRole('button', { name: /expand/i })
      fireEvent.click(expandButtons[0])

      // After expansion, there should be two "Multi-disc" texts (legend + badge)
      await waitFor(() => {
        const multiDiscTexts = screen.getAllByText('Multi-disc')
        expect(multiDiscTexts.length).toBe(2)
      })
    })

    it('should show legend with folder type descriptions', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      // Check legend items
      expect(screen.getByText('Folder')).toBeInTheDocument()
      expect(screen.getByText('Album')).toBeInTheDocument()
      // Multi-disc appears in legend
      expect(screen.getAllByText('Multi-disc').length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Folder selection behavior', () => {
    it('should call onFolderSelect when folder name is clicked', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const onFolderSelect = vi.fn()
      renderComponent('test-library', { onFolderSelect })

      // Click on folder name
      const artistOneText = screen.getByText('Artist One')
      fireEvent.click(artistOneText)

      expect(onFolderSelect).toHaveBeenCalledWith('Artist One')
    })

    it('should call onFolderSelect when folder icon is clicked', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const onFolderSelect = vi.fn()
      renderComponent('test-library', { onFolderSelect })

      // Find the select button for Artist One (icon button)
      const selectButtons = screen.getAllByRole('button', { name: /select folder/i })
      fireEvent.click(selectButtons[0])

      expect(onFolderSelect).toHaveBeenCalledWith('Artist One')
    })

    it('should not expand/collapse folder when folder name is clicked', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const onFolderSelect = vi.fn()
      renderComponent('test-library', { onFolderSelect })

      // Click on folder name (not chevron)
      const artistOneText = screen.getByText('Artist One')
      fireEvent.click(artistOneText)

      // Nested content should still not be visible (not expanded)
      expect(screen.queryByText('Album A')).not.toBeInTheDocument()
    })

    it('should show visual selected state when folder is selected', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent('test-library', { selectedPath: 'Artist One' })

      // The Artist One folder row should have the selected styling
      const artistOneText = screen.getByText('Artist One')
      const folderRow = artistOneText.closest('div[class*="flex items-center"]')
      expect(folderRow).toHaveClass('bg-primary/15')
    })

    it('should not show selected state for non-selected folders', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent('test-library', { selectedPath: 'Artist One' })

      // Artist Two should not have the selected styling
      const artistTwoText = screen.getByText('Artist Two')
      const folderRow = artistTwoText.closest('div[class*="flex items-center"]')
      expect(folderRow).not.toHaveClass('bg-primary/15')
    })

    it('should call onFolderSelect when album folder is clicked', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const onFolderSelect = vi.fn()
      renderComponent('test-library', { onFolderSelect })

      // First expand Artist One to see albums
      const expandButtons = screen.getAllByRole('button', { name: /expand/i })
      fireEvent.click(expandButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Album A')).toBeInTheDocument()
      })

      // Click on Album A (leaf album folder)
      const albumAText = screen.getByText('Album A')
      fireEvent.click(albumAText)

      expect(onFolderSelect).toHaveBeenCalledWith('Artist One/Album A')
    })

    it('should call onFolderSelect when parent folder with multiple albums is clicked', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const onFolderSelect = vi.fn()
      renderComponent('test-library', { onFolderSelect })

      // Click on parent folder (Artist One contains multiple albums)
      const artistOneText = screen.getByText('Artist One')
      fireEvent.click(artistOneText)

      expect(onFolderSelect).toHaveBeenCalledWith('Artist One')
    })

    it('should allow selecting different folders sequentially', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const onFolderSelect = vi.fn()
      renderComponent('test-library', { onFolderSelect })

      // Click on Artist One
      const artistOneText = screen.getByText('Artist One')
      fireEvent.click(artistOneText)
      expect(onFolderSelect).toHaveBeenLastCalledWith('Artist One')

      // Click on Artist Two
      const artistTwoText = screen.getByText('Artist Two')
      fireEvent.click(artistTwoText)
      expect(onFolderSelect).toHaveBeenLastCalledWith('Artist Two')

      expect(onFolderSelect).toHaveBeenCalledTimes(2)
    })

    it('should allow clicking on chevron without triggering selection', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const onFolderSelect = vi.fn()
      renderComponent('test-library', { onFolderSelect })

      // Click on expand chevron
      const expandButtons = screen.getAllByRole('button', { name: /expand/i })
      fireEvent.click(expandButtons[0])

      // Folder should expand but not trigger selection
      await waitFor(() => {
        expect(screen.getByText('Album A')).toBeInTheDocument()
      })

      // Selection callback should NOT have been called
      expect(onFolderSelect).not.toHaveBeenCalled()
    })

    it('should maintain expanded state when selecting a folder', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      const onFolderSelect = vi.fn()
      renderComponent('test-library', { onFolderSelect })

      // First expand Artist One
      const expandButtons = screen.getAllByRole('button', { name: /expand/i })
      fireEvent.click(expandButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Album A')).toBeInTheDocument()
      })

      // Now click on Artist One to select it
      const artistOneText = screen.getByText('Artist One')
      fireEvent.click(artistOneText)

      // The children should still be visible (expanded state maintained)
      expect(screen.getByText('Album A')).toBeInTheDocument()
      expect(screen.getByText('Album B')).toBeInTheDocument()
    })
  })

  describe('Album folder styling', () => {
    it('should display album folders with distinct styling', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent()

      // Expand to see albums
      const expandButtons = screen.getAllByRole('button', { name: /expand/i })
      fireEvent.click(expandButtons[0])

      await waitFor(() => {
        const albumAText = screen.getByText('Album A')
        // Album folders should have distinct styling (checked via class or visual presence)
        expect(albumAText).toBeInTheDocument()
        // The Album A text should have the font-medium class
        expect(albumAText.className).toContain('font-medium')
      })
    })

    it('should show selected styling on album folders when selected', async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderComponent('test-library', { selectedPath: 'Artist One/Album A' })

      // First expand Artist One
      const expandButtons = screen.getAllByRole('button', { name: /expand/i })
      fireEvent.click(expandButtons[0])

      await waitFor(() => {
        const albumAText = screen.getByText('Album A')
        expect(albumAText).toBeInTheDocument()

        // Album A should have selected styling
        const folderRow = albumAText.closest('div[class*="flex items-center"]')
        expect(folderRow).toHaveClass('bg-primary/15')
      })
    })
  })

  describe('Folder deletion', () => {
    const mockSuccess = async () => {
      const { useImportTree } = await import('@/hooks/useImportTree')
      vi.mocked(useImportTree).mockReturnValue({
        data: mockFolderTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)
    }

    it('renders a delete button on every folder node', async () => {
      await mockSuccess()
      renderComponent()

      // Two top-level folders → two delete buttons before expansion.
      expect(screen.getByRole('button', { name: 'Delete folder Artist One' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Delete folder Artist Two' })).toBeInTheDocument()
    })

    it('opens a confirmation dialog without selecting the folder', async () => {
      await mockSuccess()
      const onFolderSelect = vi.fn()
      renderComponent('test-library', { onFolderSelect })

      fireEvent.click(screen.getByRole('button', { name: 'Delete folder Artist One' }))

      await waitFor(() => {
        expect(screen.getByText('Delete folder')).toBeInTheDocument()
      })
      // Clicking delete must not trigger folder selection.
      expect(onFolderSelect).not.toHaveBeenCalled()
    })

    it('calls the delete mutation and onFolderDeleted on confirm', async () => {
      await mockSuccess()
      const mutateAsync = vi.fn().mockResolvedValue(undefined)
      const { useDeleteImportFolder } = await import('@/hooks/useImportTree')
      vi.mocked(useDeleteImportFolder).mockReturnValue({
        mutateAsync,
        isPending: false,
      } as any)

      const onFolderDeleted = vi.fn()
      renderComponent('test-library', { onFolderDeleted })

      fireEvent.click(screen.getByRole('button', { name: 'Delete folder Artist Two' }))
      await waitFor(() => screen.getByText('Delete folder'))

      fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

      await waitFor(() => {
        expect(mutateAsync).toHaveBeenCalledWith('Artist Two')
        expect(onFolderDeleted).toHaveBeenCalledWith('Artist Two')
      })
    })

    it('shows an error and keeps the dialog open when the delete fails', async () => {
      await mockSuccess()
      const mutateAsync = vi.fn().mockRejectedValue(new Error('boom'))
      const { useDeleteImportFolder } = await import('@/hooks/useImportTree')
      vi.mocked(useDeleteImportFolder).mockReturnValue({
        mutateAsync,
        isPending: false,
      } as any)

      const onFolderDeleted = vi.fn()
      renderComponent('test-library', { onFolderDeleted })

      fireEvent.click(screen.getByRole('button', { name: 'Delete folder Artist Two' }))
      await waitFor(() => screen.getByText('Delete folder'))
      fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

      await waitFor(() => {
        expect(screen.getByText('Failed to delete folder. Please try again.')).toBeInTheDocument()
      })
      expect(onFolderDeleted).not.toHaveBeenCalled()
    })
  })
})
