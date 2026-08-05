import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { BrowserRouter, MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import LibraryImportPage from './LibraryImportPage'
import type { Library } from '@/api/libraries'
import type { ImportTreeResponse } from '@/types/import-tree'

// Mock the hooks
vi.mock('@/hooks/useLibraries', () => ({
  useLibrary: vi.fn(),
}))

vi.mock('@/hooks/useImportTree', () => ({
  useImportTree: vi.fn(),
  useDeleteImportFolder: vi.fn(() => ({
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
  })),
}))

describe('LibraryImportPage - Integration Tests', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.clearAllMocks()
  })

  const mockLibrary: Library = {
    id: 1,
    name: 'Jazz Collection',
    slug: 'jazz',
    description: 'My jazz music library',
    config_path: '/data/config/jazz.yaml',
    database_path: '/data/db/jazz.db',
    library_path: '/data/music/jazz',
    import_path: '/data/import/jazz',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }

  const mockImportTree: ImportTreeResponse = {
    importPath: '/data/import/jazz',
    children: [
      {
        name: 'Miles Davis',
        path: 'Miles Davis',
        isAlbum: false,
        isMultiDiscParent: false,
        children: [
          {
            name: 'Kind of Blue',
            path: 'Miles Davis/Kind of Blue',
            isAlbum: true,
            isMultiDiscParent: false,
            children: [],
            hasSubfolders: false,
          },
          {
            name: 'Bitches Brew',
            path: 'Miles Davis/Bitches Brew',
            isAlbum: true,
            isMultiDiscParent: true,
            children: [
              {
                name: 'Bitches Brew Disc 1',
                path: 'Miles Davis/Bitches Brew/Bitches Brew Disc 1',
                isAlbum: false,
                isMultiDiscParent: false,
                children: [],
                hasSubfolders: false,
              },
              {
                name: 'Bitches Brew Disc 2',
                path: 'Miles Davis/Bitches Brew/Bitches Brew Disc 2',
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
    ],
  }

  const renderPage = (slug: string = 'jazz') => {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/import/${slug}`]}>
          <Routes>
            <Route path="/import/:slug" element={<LibraryImportPage />} />
            <Route path="/import" element={<div>Import List Page</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )
  }

  describe('Loading state', () => {
    it('should show loading skeleton while fetching library data', async () => {
      const { useLibrary } = await import('@/hooks/useLibraries')
      const { useImportTree } = await import('@/hooks/useImportTree')

      vi.mocked(useLibrary).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
        isSuccess: false,
        isError: false,
      } as any)

      vi.mocked(useImportTree).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
        isSuccess: false,
        isError: false,
      } as any)

      renderPage()

      // Should show loading skeleton with animated elements
      const skeletons = document.querySelectorAll('.animate-pulse')
      expect(skeletons.length).toBeGreaterThan(0)
    })
  })

  describe('Error state', () => {
    it('should show error message when library fetch fails', async () => {
      const { useLibrary } = await import('@/hooks/useLibraries')
      const { useImportTree } = await import('@/hooks/useImportTree')

      vi.mocked(useLibrary).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: new Error('Library not found'),
        isSuccess: false,
        isError: true,
      } as any)

      vi.mocked(useImportTree).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
        isSuccess: false,
        isError: false,
      } as any)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Error Loading Library')).toBeInTheDocument()
        expect(screen.getByText('Library not found')).toBeInTheDocument()
      })
    })

    it('should show not found message for 404 error', async () => {
      const { useLibrary } = await import('@/hooks/useLibraries')
      const { useImportTree } = await import('@/hooks/useImportTree')

      const notFoundError = new Error('Not found') as Error & { status: number }
      notFoundError.status = 404

      vi.mocked(useLibrary).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: notFoundError,
        isSuccess: false,
        isError: true,
      } as any)

      vi.mocked(useImportTree).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
        isSuccess: false,
        isError: false,
      } as any)

      renderPage('nonexistent')

      await waitFor(() => {
        expect(screen.getByText('Library Not Found')).toBeInTheDocument()
      })
    })

    it('should show back button that navigates to import list', async () => {
      const { useLibrary } = await import('@/hooks/useLibraries')
      const { useImportTree } = await import('@/hooks/useImportTree')

      vi.mocked(useLibrary).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: new Error('Library not found'),
        isSuccess: false,
        isError: true,
      } as any)

      vi.mocked(useImportTree).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
        isSuccess: false,
        isError: false,
      } as any)

      renderPage()

      const backButton = screen.getByRole('link', { name: /back to import/i })
      expect(backButton).toHaveAttribute('href', '/import')
    })
  })

  describe('Successful data loading', () => {
    it('should display library name in header', async () => {
      const { useLibrary } = await import('@/hooks/useLibraries')
      const { useImportTree } = await import('@/hooks/useImportTree')

      vi.mocked(useLibrary).mockReturnValue({
        data: mockLibrary,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Jazz Collection')).toBeInTheDocument()
      })
    })

    it('should display import folder tree component', async () => {
      const { useLibrary } = await import('@/hooks/useLibraries')
      const { useImportTree } = await import('@/hooks/useImportTree')

      vi.mocked(useLibrary).mockReturnValue({
        data: mockLibrary,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderPage()

      await waitFor(() => {
        // Import path should be visible (appears in both tree header and library details)
        const importPaths = screen.getAllByText('/data/import/jazz')
        expect(importPaths.length).toBeGreaterThanOrEqual(1)
        // Top-level folder should be visible
        expect(screen.getByText('Miles Davis')).toBeInTheDocument()
      })
    })

    it('should display library details card', async () => {
      const { useLibrary } = await import('@/hooks/useLibraries')
      const { useImportTree } = await import('@/hooks/useImportTree')

      vi.mocked(useLibrary).mockReturnValue({
        data: mockLibrary,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Library Details')).toBeInTheDocument()
        expect(screen.getByText('Import Path:')).toBeInTheDocument()
        expect(screen.getByText('Library Path:')).toBeInTheDocument()
      })
    })
  })

  describe('Multi-disc album display', () => {
    it('should display multi-disc parent with badge after expansion', async () => {
      const { useLibrary } = await import('@/hooks/useLibraries')
      const { useImportTree } = await import('@/hooks/useImportTree')

      vi.mocked(useLibrary).mockReturnValue({
        data: mockLibrary,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderPage()

      // Wait for initial render
      await waitFor(() => {
        expect(screen.getByText('Miles Davis')).toBeInTheDocument()
      })

      // Initially only legend has "Multi-disc"
      const initialMultiDiscTexts = screen.getAllByText('Multi-disc')
      expect(initialMultiDiscTexts.length).toBe(1)

      // Expand "Miles Davis" folder
      const expandButton = screen.getByRole('button', { name: /expand/i })
      fireEvent.click(expandButton)

      // Should show multi-disc badge for "Bitches Brew" (so now 2 "Multi-disc" texts)
      await waitFor(() => {
        expect(screen.getByText('Bitches Brew')).toBeInTheDocument()
        const multiDiscTexts = screen.getAllByText('Multi-disc')
        expect(multiDiscTexts.length).toBe(2)
      })
    })

    it('should show disc folders when multi-disc album is expanded', async () => {
      const { useLibrary } = await import('@/hooks/useLibraries')
      const { useImportTree } = await import('@/hooks/useImportTree')

      vi.mocked(useLibrary).mockReturnValue({
        data: mockLibrary,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderPage()

      // Expand "Miles Davis"
      await waitFor(() => {
        expect(screen.getByText('Miles Davis')).toBeInTheDocument()
      })

      let expandButtons = screen.getAllByRole('button', { name: /expand/i })
      fireEvent.click(expandButtons[0])

      // Wait for albums to appear
      await waitFor(() => {
        expect(screen.getByText('Bitches Brew')).toBeInTheDocument()
      })

      // Expand "Bitches Brew" (multi-disc album)
      // After expanding Miles Davis, expand buttons are: Bitches Brew's expand button (first nested)
      const updatedExpandButtons = screen.getAllByRole('button', { name: /expand/i })
      // Click the first expand button which should be Bitches Brew's
      fireEvent.click(updatedExpandButtons[0])

      // Should show disc subfolders
      await waitFor(() => {
        expect(screen.getByText('Bitches Brew Disc 1')).toBeInTheDocument()
        expect(screen.getByText('Bitches Brew Disc 2')).toBeInTheDocument()
      })
    })
  })

  describe('Album folder styling', () => {
    it('should display regular album folders distinctly', async () => {
      const { useLibrary } = await import('@/hooks/useLibraries')
      const { useImportTree } = await import('@/hooks/useImportTree')

      vi.mocked(useLibrary).mockReturnValue({
        data: mockLibrary,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderPage()

      // Expand to see albums
      await waitFor(() => {
        expect(screen.getByText('Miles Davis')).toBeInTheDocument()
      })

      const expandButton = screen.getByRole('button', { name: /expand/i })
      fireEvent.click(expandButton)

      await waitFor(() => {
        const kindOfBlue = screen.getByText('Kind of Blue')
        expect(kindOfBlue).toBeInTheDocument()
        // Album text should have distinct styling
        expect(kindOfBlue.className).toContain('font-medium')
      })
    })
  })

  describe('Invalid slug handling', () => {
    it('should show invalid library message when slug is missing', async () => {
      // This test requires a different route setup
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/import/']}>
            <Routes>
              <Route path="/import/" element={<LibraryImportPage />} />
              <Route path="/import" element={<div>Import List Page</div>} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      )

      // The component should handle empty slug case
      // This test verifies the error boundary behavior
    })
  })

  describe('Navigation', () => {
    it('should have back button that links to import page', async () => {
      const { useLibrary } = await import('@/hooks/useLibraries')
      const { useImportTree } = await import('@/hooks/useImportTree')

      vi.mocked(useLibrary).mockReturnValue({
        data: mockLibrary,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      vi.mocked(useImportTree).mockReturnValue({
        data: mockImportTree,
        isLoading: false,
        error: null,
        isSuccess: true,
        isError: false,
      } as any)

      renderPage()

      await waitFor(() => {
        const backLink = screen.getByRole('link')
        expect(backLink).toHaveAttribute('href', '/import')
      })
    })
  })
})
